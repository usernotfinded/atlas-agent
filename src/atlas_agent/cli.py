# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli.py
# PURPOSE: The main CLI: argument parser, command dispatch, and the run-once agent
#          entry point. Every command that is not one of the four configless
#          trust-contract commands (see cli_bootstrap.py) arrives here.
# DEPS:    cli_commands/ (the handlers), config, brokers, risk, safety, agent
#
# WARNING: THE TRUST CONTRACTS ARE PINNED TO THIS FILE. The command surface here is
#          asserted against by scripts/check_cli_command_compatibility.py and the
#          release checkers — renaming a command, changing a flag, or altering an
#          output envelope will trip them. Treat the public surface as a contract,
#          not as code.
#
# WARNING: At ~5.9k lines this file is a decomposition candidate, and the migration
#          is already under way: cli_commands/ + cli_registry.py exist precisely so
#          handlers can be moved out one at a time. New commands belong in
#          cli_commands/, not here.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # noqa: F401  (tests patch atlas_agent.cli.subprocess; used by handlers via cli)
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# --- CONFIGURATIONS & CONSTANTS ---

YELLOW = "\033[93m"
RESET = "\033[0m"

from atlas_agent import __version__
from atlas_agent.backtest import (
    BacktestConfig,
    BacktestEngine,
    describe_strategy,
    list_strategies,
    load_market_data,
    build_paper_strategy_evaluation,
    parse_strategy_list,
    render_json_report,
    render_markdown_report,
    write_strategy_evaluation_reports,
    validate_strategy,
    write_report_from_result,
)
from atlas_agent.backtest.sensitivity import (
    build_paper_strategy_sensitivity,
    write_strategy_sensitivity_reports,
)
from atlas_agent.backtest.walk_forward import build_paper_strategy_walk_forward, write_strategy_walk_forward_reports
from atlas_agent.backtest.robustness import (
    build_paper_strategy_robustness,
    parse_fixture_list,
    write_strategy_robustness_reports,
)
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.cli_commands import build_core_command_registry
from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_io import display_path, emit_cli_error, emit_cli_success
from atlas_agent.config import AtlasConfig
from atlas_agent.config.errors import AtlasConfigError
from atlas_agent.execution.approval import ApprovalManager
from atlas_agent.execution.audit import AuditLogger
from atlas_agent.execution.order import Order, OrderResult
from atlas_agent.execution.order_router import OrderRouter
from atlas_agent.events import (
    EventLogger,
    generate_run_id,
)
from atlas_agent.market_data.csv_provider import CSVMarketDataProvider
from atlas_agent.market_data.sample_data import ensure_sample_data
from atlas_agent.portfolio.journal import TradeJournal
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.research.command_specs import (
    CONFIGLESS_RESEARCH_COMMANDS,
    RESEARCH_COMMAND_ALIAS_MAP,
    add_research_subparsers,
)
from atlas_agent.risk.manager import RiskManager
from atlas_agent.routines.engine import ROUTINE_NAMES
from atlas_agent.scheduler.runner import VALID_ROUTINES
from atlas_agent.output import emit_json, error_envelope, success_envelope
from atlas_agent.cli_safety import (
    _effective_config_with_runtime_kill_switch,
    _kill_switch_controller,
)
from atlas_agent.safety import (
    deadman_heartbeat_path,
    write_deadman_heartbeat,
)
from atlas_agent.safety.totp import verify_totp
from atlas_agent.strategies.moving_average import MovingAverageStrategy
from atlas_agent.update import AUTO_CHECK_VALUES
from atlas_agent.workspace import (
    DEFAULT_TEMPLATE,
    WorkspaceInitError,
    WorkspaceResolution,
    init_workspace,
    is_workspace,
    resolve_workspace,
    set_default_workspace,
)


# ==============================================================================
# ARGUMENT PARSER
# ==============================================================================
#
# This function defines the ENTIRE public command surface of `atlas`. It is what
# check_cli_command_compatibility.py diffs against, so every subparser, flag and
# default below is part of the trust contract. Adding is safe; renaming and removing
# are not.

def build_parser() -> argparse.ArgumentParser:
    description = r"""
      ___ _____ _      _   ___      _   ___ ___ _  _ _____
     / _ \_   _| |    /_\ / __|    /_\ / __| __| \| |_   _|
    / ___ \| | | |__ / _ \\__ \   / _ \ (_ | _|| .` | | |
   /_/   \_|_| |____/_/ \_\___/  /_/ \_\___|___|_|\_| |_|

Atlas Agent is a broker-neutral supervised trading workspace.
It provides market research, paper workflows, and deterministic risk gates.

"""
    epilog = """
Core Commands:
  atlas init          - Initialize a new workspace
  atlas setup         - Guided end-to-end setup (provider, discipline, symbol, readiness)
  atlas validate      - Check configuration and safety gates
  atlas agent status  - Show current agent state and mode
  atlas agent plan    - Explain the next agent cycle
  atlas agent run     - Start the autonomous agent cycle

Safety First:
  Atlas Agent is not financial advice. Trading involves risk.
  Live trading is never enabled by default. Use 'atlas agent status'
  to verify your current safety gates and trading mode.
"""
    parser = argparse.ArgumentParser(
        prog="atlas",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--workspace", help="Path to an Atlas workspace")
    subparsers = parser.add_subparsers(dest="command")
    init = subparsers.add_parser("init")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--template", default=DEFAULT_TEMPLATE)
    init.add_argument("--force", action="store_true")
    init.add_argument("--set-default", action="store_true", help="Set this workspace as the default")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--json", action="store_true", help="Output readiness report as JSON")
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when readiness checks fail.",
    )
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Inspect local broker/provider readiness without network or execution.",
        description=(
            "Inspect local broker/provider configuration, credential presence, "
            "optional dependencies, and safety blocks. Read-only: no network, "
            "provider calls, broker clients, or execution."
        ),
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Output a deterministic, secret-redacted JSON report.",
    )
    subparsers.add_parser("configure")
    subparsers.add_parser("setup")

    config_parser = subparsers.add_parser("config")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_show = config_sub.add_parser("show")
    config_show.add_argument("--effective", action="store_true")
    config_get = config_sub.add_parser("get")
    config_get.add_argument("--effective", action="store_true")
    config_get.add_argument("key")
    config_set = config_sub.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_unset = config_sub.add_parser("unset")
    config_unset.add_argument("key")
    config_sub.add_parser("migrate")
    config_sub.add_parser("doctor")
    config_sub.add_parser("paths")
    config_sub.add_parser("edit")
    config_check = config_sub.add_parser("check")
    config_check.add_argument("--json", action="store_true")

    model_parser = subparsers.add_parser("model")
    model_sub = model_parser.add_subparsers(dest="model_command")
    model_list = model_sub.add_parser("list")
    model_list.add_argument("--provider", help="Filter models by provider ID")
    model_providers = model_sub.add_parser("providers")
    model_providers.add_argument("--include-legacy", action="store_true", help="Include legacy providers like local_command")
    model_providers.add_argument("--include-internal", action="store_true", help="Include internal providers like null")
    model_sub.add_parser("current")
    model_set = model_sub.add_parser("set")
    model_set.add_argument("model_id")
    model_set.add_argument("model", nargs="?", default=None, help="Model ID (optional if model_id contains provider prefix)")
    model_sub.add_parser("configure")

    workspace = subparsers.add_parser("workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_command")
    workspace_sub.add_parser("show")
    workspace_set = workspace_sub.add_parser("set")
    workspace_set.add_argument("path")
    workspace_sub.add_parser("clear")
    workspace_doctor = workspace_sub.add_parser("doctor")
    workspace_doctor.add_argument("--json", action="store_true")

    subparsers.add_parser("status")
    subparsers.add_parser("plan")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--mode", choices=("auto", "paper", "live"), default="auto")
    run_parser.add_argument("--symbol", help="Trading symbol (defaults to market.symbol config)")
    run_parser.add_argument("--continuous", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the offline null provider for this run. No API key or network required.",
    )
    run_parser.add_argument("--interval", type=int, default=60)
    run_parser.add_argument("--max-cycles", type=int, default=None)

    update = subparsers.add_parser("update")
    update_sub = update.add_subparsers(dest="update_command")
    update_check = update_sub.add_parser("check")
    update_check.add_argument("--dry-run", action="store_true", help="Perform a dry-run check without applying updates.")
    update_sub.add_parser("status")
    update_apply = update_sub.add_parser("apply")
    update_apply.add_argument("--force", action="store_true")
    update_rollback = update_sub.add_parser("rollback")
    update_rollback.add_argument(
        "--yes",
        action="store_true",
        help="Confirm rollback. Rollback is a destructive operation.",
    )
    update_config = update_sub.add_parser("config")
    update_config.add_argument("--auto-check", choices=sorted(AUTO_CHECK_VALUES))
    update_config.add_argument("--auto-apply", choices=("on", "off"))

    providers = subparsers.add_parser("providers")
    providers_sub = providers.add_subparsers(dest="providers_command")
    providers_sub.add_parser("list")
    providers_preflight = providers_sub.add_parser(
        "preflight",
        help="Generate a local dry-run provider call-plan artifact. No network or provider call made.",
        description="Generate a local dry-run provider call-plan artifact. No provider calls, no network, no credentials.",
    )
    providers_preflight.add_argument("--provider", required=True, help="Provider ID (e.g., openrouter, anthropic)")
    providers_preflight.add_argument("--model", required=True, help="Model ID")
    providers_preflight.add_argument("--purpose", required=True, help="Purpose of the call")
    providers_preflight.add_argument("--max-context-chars", type=int, default=4000, help="Maximum context characters")
    providers_preflight.add_argument("--output", type=Path, help="Output file path (default: artifacts/provider_preflight/<timestamp>-call-plan.json)")
    providers_preflight.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    providers_validate = providers_sub.add_parser(
        "validate-preflight",
        help="Validate a provider preflight call-plan artifact",
        description="Validates that a local call-plan artifact meets strict safety requirements.",
    )
    providers_validate.add_argument("artifact_path", help="Path to the JSON artifact to validate")
    providers_validate.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    providers_bundle = providers_sub.add_parser(
        "bundle-preflight",
        help="Create a local audit evidence bundle for a provider preflight artifact",
        description="Create a local-only evidence bundle after validating a provider preflight call-plan artifact. No provider calls, no network, no credentials.",
    )
    providers_bundle.add_argument("artifact_path", help="Path to the JSON artifact to bundle")
    providers_bundle.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory for the evidence bundle",
    )
    providers_bundle.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    providers_verify_bundle = providers_sub.add_parser(
        "verify-preflight-bundle",
        help="Verify a local provider preflight evidence bundle",
        description="Verify a local-only provider preflight evidence bundle. No provider calls, no network, no credentials.",
    )
    providers_verify_bundle.add_argument("bundle_dir", help="Path to the evidence bundle directory")
    providers_verify_bundle.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    providers_smoke = providers_sub.add_parser(
        "smoke-preflight-chain",
        help="Run the local dry-run provider preflight chain end-to-end",
        description=(
            "Run the local-only dry-run provider preflight safety chain: "
            "generate call-plan, validate call-plan, create evidence bundle, "
            "and verify bundle. No provider calls, no network, no credentials."
        ),
    )
    providers_smoke.add_argument("--provider", required=True, help="Provider ID (e.g., openrouter, anthropic)")
    providers_smoke.add_argument("--model", required=True, help="Model ID")
    providers_smoke.add_argument("--purpose", required=True, help="Purpose of the call")
    providers_smoke.add_argument("--max-context-chars", type=int, default=4000, help="Maximum context characters")
    providers_smoke.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory for smoke-chain artifacts",
    )
    providers_smoke.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    providers_audit_pack = providers_sub.add_parser(
        "audit-pack",
        help="Create a local provider preflight audit pack",
        description=(
            "Create a local-only, non-authorizing provider audit pack: dry-run "
            "preflight chain, evidence index, Markdown report, compact summary, "
            "and audit pack manifest. No provider calls, no network, no credentials."
        ),
    )
    providers_audit_pack.add_argument("--provider", required=True, help="Provider ID (e.g., openrouter, anthropic)")
    providers_audit_pack.add_argument("--model", required=True, help="Model ID")
    providers_audit_pack.add_argument("--purpose", required=True, help="Purpose of the call")
    providers_audit_pack.add_argument("--max-context-chars", type=int, default=4000, help="Maximum context characters")
    providers_audit_pack.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory for audit-pack artifacts",
    )
    providers_audit_pack.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    providers_verify_audit_pack = providers_sub.add_parser(
        "verify-audit-pack",
        help="Verify a local provider audit pack",
        description="Verify a complete provider audit pack for safety and correctness. Local-only.",
    )
    providers_verify_audit_pack.add_argument("pack_dir", type=Path, help="Path to the audit pack directory")
    providers_verify_audit_pack.add_argument("--json", action="store_true", help="Emit result as JSON")

    providers_capability = providers_sub.add_parser(
        "capability-inventory",
        help="Generate a local provider capability inventory.",
        description="Generate a local capability inventory for providers. No network or credentials.",
    )
    providers_capability.add_argument("--output", type=Path, help="Output file path.")
    providers_capability.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    providers_readiness = providers_sub.add_parser(
        "readiness-check",
        help="Evaluate a provider request against the safety policy.",
        description="Evaluate a hypothetical provider request against the safety policy. Local-only. No network.",
    )
    providers_readiness.add_argument("--provider", required=True, help="Provider ID (e.g., openrouter, anthropic)")
    providers_readiness.add_argument("--model", required=True, help="Model ID")
    providers_readiness.add_argument("--purpose", required=True, help="Purpose of the call")
    providers_readiness.add_argument("--max-context-chars", type=int, default=4000, help="Maximum context characters")
    providers_readiness.add_argument("--output", type=Path, help="Output file path.")
    providers_readiness.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    providers_evidence = providers_sub.add_parser("evidence-index", help="Manage provider evidence index.")
    evidence_sub = providers_evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_build = evidence_sub.add_parser("build", help="Build a provider evidence index.")
    evidence_build.add_argument("--root", required=True, type=Path, help="Root directory to scan")
    evidence_build.add_argument("--output", type=Path, help="Output JSON file path")
    evidence_build.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    evidence_inspect = evidence_sub.add_parser("inspect", help="Inspect a provider evidence index.")
    evidence_inspect.add_argument("index_path", type=Path, help="Path to the index JSON")
    evidence_inspect.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    evidence_report = evidence_sub.add_parser("report", help="Generate a human-readable Markdown report from the evidence index.")
    evidence_report.add_argument("index_path", type=Path, help="Path to the index JSON")
    evidence_report.add_argument("--output", required=True, type=Path, help="Output Markdown report path")
    evidence_report.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    evidence_export_summary = evidence_sub.add_parser("export-summary", help="Export a compact machine-readable summary of the evidence index.")
    evidence_export_summary.add_argument("index_path", type=Path, help="Path to the index JSON")
    evidence_export_summary.add_argument("--output", required=True, type=Path, help="Output JSON summary path")
    evidence_export_summary.add_argument("--json", action="store_true", help="Emit result as JSON envelope")

    brokers = subparsers.add_parser("broker")
    brokers_sub = brokers.add_subparsers(dest="brokers_command")
    brokers_sub.add_parser("list")
    brokers_status = brokers_sub.add_parser(
        "status",
        help="Show broker support inventory and runtime status",
        description="Show broker support inventory and runtime status. Read-only. No broker API calls.",
    )
    brokers_status.add_argument("--json", action="store_true", help="Emit result as JSON envelope")
    brokers_sync = brokers_sub.add_parser("sync")
    brokers_sync.add_argument("--mode", choices=("paper", "live"), default="paper")
    brokers_sync.add_argument("--json", action="store_true")
    brokers_opt_in = brokers_sub.add_parser("opt-in")
    brokers_opt_in.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
    brokers_opt_out = brokers_sub.add_parser("opt-out")

    backtest = subparsers.add_parser("backtest")
    backtest_sub = backtest.add_subparsers(dest="backtest_command")
    backtest_run = backtest_sub.add_parser("run")
    backtest_run.add_argument("--strategy", default=None)
    backtest_run.add_argument(
        "--strategy-param",
        action="append",
        default=[],
        help="Strategy parameter override as key=value. Can be repeated.",
    )
    backtest_run.add_argument("--benchmark", choices=("buy_and_hold", "spy"), default=None)
    backtest_run.add_argument("--benchmark-symbol", default=None)
    backtest_run.add_argument("--benchmark-data", default=None)
    backtest_run.add_argument("--symbol", required=True)
    backtest_run.add_argument("--data", required=True)
    backtest_run.add_argument("--initial-equity", type=float, default=10000.0)
    backtest_run.add_argument("--slippage-bps", type=float, default=0.0)
    backtest_run.add_argument("--commission-bps", type=float, default=0.0)
    backtest_run.add_argument("--start-date", default=None, help="ISO or YYYY-MM-DD date to begin the backtest (inclusive).")
    backtest_run.add_argument("--end-date", default=None, help="ISO or YYYY-MM-DD date to end the backtest (inclusive).")
    backtest_run.add_argument("--report", choices=("json", "markdown"), default=None, help="Generate a report summary in the specified format.")
    backtest_run.add_argument("--json", action="store_true")
    backtest_compare = backtest_sub.add_parser(
        "compare",
        help="Compare backtest strategies through a deterministic paper-only evaluation gate.",
        description=(
            "Compare strategies against local OHLCV data and write paper-only "
            "strategy-evaluation.json and strategy-evaluation.md artifacts. "
            "No provider, broker, network, or live trading path is used."
        ),
    )
    backtest_compare.add_argument("--symbol", required=True)
    backtest_compare.add_argument("--data", required=True)
    backtest_compare.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_compare.add_argument("--output-dir", required=True)
    backtest_compare.add_argument("--initial-equity", type=float, default=10000.0)
    backtest_compare.add_argument("--slippage-bps", type=float, default=0.0)
    backtest_compare.add_argument("--commission-bps", type=float, default=0.0)
    backtest_compare.add_argument("--start-date", default=None)
    backtest_compare.add_argument("--end-date", default=None)
    backtest_compare.add_argument("--json", action="store_true")
    backtest_sensitivity = backtest_sub.add_parser(
        "sensitivity",
        help="Evaluate parameter sensitivity through a deterministic paper-only gate.",
        description=(
            "Evaluate strategies across parameter variants against local OHLCV data "
            "and write paper-only strategy-sensitivity.json and .md artifacts. "
            "No provider, broker, network, or live trading path is used."
        ),
    )
    backtest_sensitivity.add_argument("--symbol", required=True)
    backtest_sensitivity.add_argument("--data", required=True)
    backtest_sensitivity.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_sensitivity.add_argument("--output-dir", required=True)
    backtest_sensitivity.add_argument("--initial-equity", type=float, default=10000.0)
    backtest_sensitivity.add_argument("--slippage-bps", type=float, default=0.0)
    backtest_sensitivity.add_argument("--commission-bps", type=float, default=0.0)
    backtest_sensitivity.add_argument("--start-date", default=None)
    backtest_sensitivity.add_argument("--end-date", default=None)
    backtest_sensitivity.add_argument("--json", action="store_true")
    backtest_walk_forward = backtest_sub.add_parser(
        "walk-forward",
        help="Evaluate multi-window paper strategy walk-forward stability through a deterministic gate.",
        description=(
            "Evaluate strategies and parameter variants across chronological windows "
            "and write paper-only strategy-walk-forward.json and .md artifacts. "
            "No provider, broker, network, or live trading path is used."
        ),
    )
    backtest_walk_forward.add_argument("--symbol", required=True)
    backtest_walk_forward.add_argument("--data", required=True)
    backtest_walk_forward.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_walk_forward.add_argument("--window-size", type=int, default=60)
    backtest_walk_forward.add_argument("--step-size", type=int, default=30)
    backtest_walk_forward.add_argument("--output-dir", required=True)
    backtest_walk_forward.add_argument("--initial-equity", type=float, default=10000.0)
    backtest_walk_forward.add_argument("--slippage-bps", type=float, default=0.0)
    backtest_walk_forward.add_argument("--commission-bps", type=float, default=0.0)
    backtest_walk_forward.add_argument("--json", action="store_true")

    backtest_robustness = backtest_sub.add_parser(
        "robustness",
        help="Evaluate multi-regime paper strategy robustness through a deterministic gate.",
        description=(
            "Evaluate strategies and parameter variants across local synthetic OHLCV "
            "regime fixtures and write paper-only strategy-robustness.json and .md "
            "artifacts. No provider, broker, network, or live trading path is used."
        ),
    )
    backtest_robustness.add_argument("--symbol", required=True)
    backtest_robustness.add_argument(
        "--fixtures",
        required=True,
        help="Comma-separated local OHLCV fixture paths for deterministic regimes.",
    )
    backtest_robustness.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_robustness.add_argument("--output-dir", required=True)
    backtest_robustness.add_argument("--initial-equity", type=float, default=10000.0)
    backtest_robustness.add_argument("--slippage-bps", type=float, default=0.0)
    backtest_robustness.add_argument("--commission-bps", type=float, default=0.0)
    backtest_robustness.add_argument("--start-date", default=None)
    backtest_robustness.add_argument("--end-date", default=None)
    backtest_robustness.add_argument("--json", action="store_true")

    backtest_scorecard = backtest_sub.add_parser(
        "scorecard",
        help="Evaluate a deterministic paper-only strategy candidate scorecard.",
        description=(
            "Evaluate strategies across evaluation, sensitivity, robustness, and walk-forward "
            "paper gates to build a paper candidate scorecard. No provider, broker, network, "
            "or live trading path is used."
        ),
    )
    backtest_scorecard.add_argument("--symbol", required=True)
    backtest_scorecard.add_argument("--data", required=True)
    backtest_scorecard.add_argument(
        "--fixtures",
        default=None,
        help="Comma-separated local OHLCV fixture paths for deterministic regimes. If provided, robustness is evaluated.",
    )
    backtest_scorecard.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_scorecard.add_argument("--window-size", type=int, default=60)
    backtest_scorecard.add_argument("--step-size", type=int, default=30)
    backtest_scorecard.add_argument("--output-dir", required=True)
    backtest_scorecard.add_argument("--initial-equity", type=float, default=10000.0)
    backtest_scorecard.add_argument("--slippage-bps", type=float, default=0.0)
    backtest_scorecard.add_argument("--commission-bps", type=float, default=0.0)
    backtest_scorecard.add_argument("--json", action="store_true")

    backtest_portfolio = backtest_sub.add_parser(
        "portfolio-proposal",
        help="Evaluate a deterministic paper-only portfolio proposal sandbox.",
        description=(
            "Evaluate strategies across evaluation, sensitivity, robustness, and walk-forward "
            "paper gates to build a paper portfolio proposal allocation sandbox. No provider, "
            "broker, network, or live trading path is used."
        ),
    )
    backtest_portfolio.add_argument("--symbol", required=True)
    backtest_portfolio.add_argument("--data", required=True)
    backtest_portfolio.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_portfolio.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio.add_argument("--output-dir", required=True)
    backtest_portfolio.add_argument("--json", action="store_true")

    backtest_portfolio_stress = backtest_sub.add_parser(
        "portfolio-stress",
        help="Evaluate deterministic paper-only portfolio stress constraints.",
        description=(
            "Generate a paper portfolio proposal and evaluate deterministic synthetic stress "
            "constraints. No provider, broker, network, live trading, or order path is used."
        ),
    )
    backtest_portfolio_stress.add_argument("--symbol", required=True)
    backtest_portfolio_stress.add_argument("--data", required=True)
    backtest_portfolio_stress.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_portfolio_stress.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_stress.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_stress.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_stress.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_stress.add_argument("--output-dir", required=True)
    backtest_portfolio_stress.add_argument("--json", action="store_true")

    backtest_portfolio_monitor = backtest_sub.add_parser(
        "portfolio-monitor",
        help="Simulate deterministic paper-only portfolio monitoring windows.",
        description=(
            "Simulate paper-only monitoring windows over local sample data using "
            "paper portfolio proposal and stress artifacts. No provider, broker, "
            "network, live trading, notification, or order path is used."
        ),
    )
    backtest_portfolio_monitor.add_argument("--symbol", required=True)
    backtest_portfolio_monitor.add_argument("--data", required=True)
    backtest_portfolio_monitor.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_portfolio_monitor.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_monitor.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_monitor.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_monitor.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_monitor.add_argument("--monitor-window", type=int, default=20)
    backtest_portfolio_monitor.add_argument("--recheck-threshold", type=float, default=0.05)
    backtest_portfolio_monitor.add_argument("--output-dir", required=True)
    backtest_portfolio_monitor.add_argument("--json", action="store_true")

    backtest_portfolio_recheck = backtest_sub.add_parser(
        "portfolio-recheck",
        help=(
            "Generate a deterministic paper-only portfolio recheck ledger and human "
            "review queue using proposal, stress, and monitor artifacts. "
            "No provider, broker, network, live trading, notification, or order path is used."
        ),
    )
    backtest_portfolio_recheck.add_argument("--symbol", required=True)
    backtest_portfolio_recheck.add_argument("--data", required=True)
    backtest_portfolio_recheck.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_portfolio_recheck.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_recheck.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_recheck.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_recheck.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_recheck.add_argument("--monitor-window", type=int, default=20)
    backtest_portfolio_recheck.add_argument("--recheck-threshold", type=float, default=0.05)
    backtest_portfolio_recheck.add_argument("--output-dir", required=True)
    backtest_portfolio_recheck.add_argument("--json", action="store_true")

    backtest_portfolio_dossier = backtest_sub.add_parser(
        "portfolio-dossier",
        help=(
            "Generate a deterministic paper-only portfolio reviewer dossier. "
            "No provider, broker, network, live trading, notification, or order path is used."
        ),
    )
    backtest_portfolio_dossier.add_argument("--symbol", required=True)
    backtest_portfolio_dossier.add_argument("--data", required=True)
    backtest_portfolio_dossier.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_portfolio_dossier.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_dossier.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_dossier.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_dossier.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_dossier.add_argument("--monitor-window", type=int, default=20)
    backtest_portfolio_dossier.add_argument("--recheck-threshold", type=float, default=0.05)
    backtest_portfolio_dossier.add_argument("--output-dir", required=True)
    backtest_portfolio_dossier.add_argument("--json", action="store_true")

    backtest_portfolio_replay = backtest_sub.add_parser(
        "portfolio-replay",
        help=(
            "Generate a deterministic paper-only portfolio evidence replay and regression gate. "
            "No provider, broker, network, live trading, notification, or order path is used."
        ),
    )
    backtest_portfolio_replay.add_argument("--symbol", required=True)
    backtest_portfolio_replay.add_argument("--data", required=True)
    backtest_portfolio_replay.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_portfolio_replay.add_argument("--repeat", type=int, default=2)
    backtest_portfolio_replay.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_replay.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_replay.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_replay.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_replay.add_argument("--monitor-window", type=int, default=20)
    backtest_portfolio_replay.add_argument("--recheck-threshold", type=float, default=0.05)
    backtest_portfolio_replay.add_argument("--output-dir", required=True)
    backtest_portfolio_replay.add_argument("--json", action="store_true")

    backtest_portfolio_review_pack = backtest_sub.add_parser(
        "portfolio-review-pack",
        help=(
            "Generate a deterministic paper-only human review pack. "
            "No provider, broker, network, live trading, notification, or order path is used."
        ),
    )
    backtest_portfolio_review_pack.add_argument("--symbol", required=True)
    backtest_portfolio_review_pack.add_argument("--data", required=True)
    backtest_portfolio_review_pack.add_argument(
        "--strategies",
        default=None,
        help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.",
    )
    backtest_portfolio_review_pack.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_review_pack.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_review_pack.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_review_pack.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_review_pack.add_argument("--monitor-window", type=int, default=20)
    backtest_portfolio_review_pack.add_argument("--recheck-threshold", type=float, default=0.05)
    backtest_portfolio_review_pack.add_argument("--output-dir", required=True)
    backtest_portfolio_review_pack.add_argument("--json", action="store_true")

    backtest_portfolio_review_ledger = backtest_sub.add_parser(
        "portfolio-review-ledger",
        help=(
            "Generate a deterministic paper-only human review decision ledger. "
            "No provider, broker, network, live trading, notification, order, or real human approval path is used."
        ),
    )
    backtest_portfolio_review_ledger.add_argument("--review-pack", default=None, help="Path to a paper-human-review-pack.json artifact. If omitted, the ledger builds a review pack from the other arguments.")
    backtest_portfolio_review_ledger.add_argument("--symbol", default=None)
    backtest_portfolio_review_ledger.add_argument("--data", default=None)
    backtest_portfolio_review_ledger.add_argument("--strategies", default=None, help="Comma-separated strategy IDs. Defaults to all registered backtest strategies.")
    backtest_portfolio_review_ledger.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_review_ledger.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_review_ledger.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_review_ledger.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_review_ledger.add_argument("--monitor-window", type=int, default=20)
    backtest_portfolio_review_ledger.add_argument("--recheck-threshold", type=float, default=0.05)
    backtest_portfolio_review_ledger.add_argument("--output-dir", required=True)
    backtest_portfolio_review_ledger.add_argument("--json", action="store_true")

    backtest_portfolio_review_policy = backtest_sub.add_parser(
        "portfolio-review-policy",
        help=(
            "Run a deterministic paper-only policy simulation against a review pack and ledger. "
            "No provider, broker, network, live trading, notification, order, or real human approval path is used."
        ),
    )
    backtest_portfolio_review_policy.add_argument("--review-pack", default=None, help="Path to paper-human-review-pack.json. If omitted with --review-ledger, builds upstream artifacts from other args.")
    backtest_portfolio_review_policy.add_argument("--review-ledger", default=None)
    backtest_portfolio_review_policy.add_argument("--symbol", default=None)
    backtest_portfolio_review_policy.add_argument("--data", default=None)
    backtest_portfolio_review_policy.add_argument("--strategies", default=None)
    backtest_portfolio_review_policy.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_review_policy.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_review_policy.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_review_policy.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_review_policy.add_argument("--monitor-window", type=int, default=20)
    backtest_portfolio_review_policy.add_argument("--recheck-threshold", type=float, default=0.05)
    backtest_portfolio_review_policy.add_argument("--output-dir", required=True)
    backtest_portfolio_review_policy.add_argument("--json", action="store_true")

    backtest_portfolio_review_replay = backtest_sub.add_parser(
        "portfolio-review-replay",
        help=(
            "Run a deterministic paper-only replay/regression gate over the full review chain. "
            "No provider, broker, network, live trading, notification, order, or real human approval path is used."
        ),
    )
    backtest_portfolio_review_replay.add_argument("--review-pack", default=None, help="Path to paper-human-review-pack.json. If omitted with --review-ledger and --review-policy, builds upstream artifacts from other args.")
    backtest_portfolio_review_replay.add_argument("--review-ledger", default=None)
    backtest_portfolio_review_replay.add_argument("--review-policy", default=None)
    backtest_portfolio_review_replay.add_argument("--symbol", default=None)
    backtest_portfolio_review_replay.add_argument("--data", default=None)
    backtest_portfolio_review_replay.add_argument("--strategies", default=None)
    backtest_portfolio_review_replay.add_argument("--max-strategy-weight", type=float, default=0.40)
    backtest_portfolio_review_replay.add_argument("--min-cash-weight", type=float, default=0.10)
    backtest_portfolio_review_replay.add_argument("--max-stressed-drawdown", type=float, default=0.25)
    backtest_portfolio_review_replay.add_argument("--max-single-scenario-loss", type=float, default=0.20)
    backtest_portfolio_review_replay.add_argument("--monitor-window", type=int, default=20)
    backtest_portfolio_review_replay.add_argument("--recheck-threshold", type=float, default=0.05)
    backtest_portfolio_review_replay.add_argument("--output-dir", required=True)
    backtest_portfolio_review_replay.add_argument("--json", action="store_true")

    backtest_list = backtest_sub.add_parser("list-strategies")
    backtest_list.add_argument("--json", action="store_true")
    backtest_runs = backtest_sub.add_parser("runs")
    backtest_runs.add_argument("--json", action="store_true")
    backtest_runs.add_argument("--validate", action="store_true", help="Validate each report against the schema contract and show status.")
    backtest_describe = backtest_sub.add_parser("describe")
    backtest_describe.add_argument("strategy")
    backtest_describe.add_argument("--json", action="store_true")
    backtest_validate = backtest_sub.add_parser("validate")
    backtest_validate.add_argument("strategy")
    backtest_validate.add_argument(
        "--strategy-param",
        action="append",
        default=[],
        help="Strategy parameter override as key=value. Can be repeated.",
    )
    backtest_validate.add_argument("--symbol")
    backtest_validate.add_argument("--data")
    backtest_validate.add_argument("--initial-equity", type=float, default=10000.0)
    backtest_validate.add_argument("--json", action="store_true")

    run_once_parser = subparsers.add_parser("run-once")
    run_once_parser.add_argument("--mode", choices=("paper", "live"), default="paper")
    run_once_parser.add_argument("--symbol", help="Trading symbol (defaults to market.symbol config)")

    agent = subparsers.add_parser("agent")
    agent_sub = agent.add_subparsers(dest="agent_command")
    agent_run = agent_sub.add_parser("run")
    agent_run.add_argument("--mode", choices=("auto", "paper", "live"), default="auto")
    agent_run.add_argument("--symbol", help="Trading symbol (defaults to market.symbol config)")
    agent_run.add_argument("--once", action="store_true")
    agent_run.add_argument("--continuous", action="store_true")
    agent_run.add_argument(
        "--offline",
        action="store_true",
        help="Use the offline null provider for this run. No API key or network required.",
    )
    agent_run.add_argument("--interval", type=int, default=60)
    agent_run.add_argument("--max-cycles", type=int, default=None)
    agent_status = agent_sub.add_parser("status")
    agent_status.add_argument("--json", action="store_true")
    agent_plan = agent_sub.add_parser("plan")
    agent_plan.add_argument("--json", action="store_true")
    agent_autonomous_paper = agent_sub.add_parser(
        "autonomous-paper",
        help="Run a deterministic, paper-only autonomous decision loop without human step-by-step intervention.",
    )
    agent_autonomous_paper.add_argument("--symbol", help="Trading symbol (defaults to market.symbol config)")
    agent_autonomous_paper.add_argument(
        "--strategy",
        default="moving_average_cross",
        help="Built-in backtest strategy id to use for decisions (default: moving_average_cross)",
    )
    agent_autonomous_paper.add_argument(
        "--data-path",
        help="Path to local OHLCV CSV data (defaults to backtest.data_path config)",
    )
    agent_autonomous_paper.add_argument(
        "--max-cycles",
        type=int,
        default=1,
        help="Maximum number of bars to process (default: 1; 0 means all bars)",
    )
    agent_autonomous_paper.add_argument(
        "--evidence-dir",
        help="If provided, copy the decisions and manifest into an evidence bundle under this directory.",
    )
    agent_autonomous_paper.add_argument("--json", action="store_true", help="Emit result as JSON")
    agent_autonomous_paper.add_argument(
        "--state-dir",
        default=None,
        help="Directory to persist stateful paper runner state and checkpoints.",
    )
    agent_autonomous_paper.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing state in --state-dir if present.",
    )
    agent_autonomous_paper.add_argument(
        "--initial-cash",
        type=float,
        default=None,
        help="Initial cash for stateful paper runner (default from config).",
    )
    agent_autonomous_paper.add_argument(
        "--commission-bps",
        type=float,
        default=None,
        help="Commission in basis points for simulated fills.",
    )
    agent_autonomous_paper.add_argument(
        "--slippage-bps",
        type=float,
        default=None,
        help="Slippage in basis points for simulated fills.",
    )
    agent_autonomous_paper.add_argument(
        "--fill-timing",
        choices=["same_bar", "next_bar"],
        default="next_bar",
        help="Deterministic fill timing model (default: next_bar).",
    )
    agent_autonomous_paper.add_argument(
        "--strategy-param",
        action="append",
        default=[],
        help="Strategy parameter override as key=value. Can be repeated.",
    )
    agent_autonomous_scorecard = agent_sub.add_parser(
        "autonomous-scorecard",
        help="Evaluate autonomous-paper decision artifacts and produce a promotion scorecard.",
    )
    agent_autonomous_scorecard.add_argument("--decisions", required=True, help="Path to decisions.jsonl")
    agent_autonomous_scorecard.add_argument("--manifest", required=True, help="Path to manifest.json")
    agent_autonomous_scorecard.add_argument("--replay-decisions", help="Optional second decisions file for replay comparison")
    agent_autonomous_scorecard.add_argument("--output-dir", help="Directory for scorecard JSON/Markdown reports")
    agent_autonomous_scorecard.add_argument("--json", action="store_true", help="Emit scorecard as JSON")
    agent_autonomous_quality = agent_sub.add_parser(
        "autonomous-paper-quality",
        help="Evaluate stateful autonomous-paper trading behavior against a quality gate (paper-only, offline).",
    )
    agent_autonomous_quality.add_argument("--metrics", required=True, help="Path to metrics.json")
    agent_autonomous_quality.add_argument("--decisions", required=True, help="Path to decisions.jsonl")
    agent_autonomous_quality.add_argument("--fills", required=True, help="Path to fills.jsonl")
    agent_autonomous_quality.add_argument("--state", help="Path to state.json (optional)")
    agent_autonomous_quality.add_argument("--scorecard", help="Path to autonomous-paper-scorecard.json (optional)")
    agent_autonomous_quality.add_argument("--threshold-policy", help="Path to threshold policy JSON (optional)")
    agent_autonomous_quality.add_argument("--data-path", help="Path to OHLCV CSV for benchmark comparison (optional)")
    agent_autonomous_quality.add_argument("--symbol", help="Trading symbol evaluated by the paper runner (optional)")
    agent_autonomous_quality.add_argument("--output-dir", help="Directory for trading-quality-gate.json and trading-quality-report.md")
    agent_autonomous_quality.add_argument("--json", action="store_true", help="Emit result as JSON")
    agent_shadow_live = agent_sub.add_parser(
        "shadow-live",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="read-only fixture-first comparison of paper state against a recorded broker snapshot",
        description=(
            "read-only fixture-first comparison.\n"
            "does not submit orders or call broker APIs.\n"
            "does not load credentials.\n"
            "does not implement live trading or live readiness."
        ),
    )
    agent_shadow_live.add_argument("--quality-gate", required=True, help="path to trading-quality-gate.json")
    agent_shadow_live.add_argument("--broker-snapshot", required=True, help="path to local broker snapshot JSON fixture")
    agent_shadow_live.add_argument("--output-dir", required=True, help="directory for shadow-live artifacts")
    agent_shadow_live.add_argument("--state", default=None, help="optional persisted runner state JSON")
    agent_shadow_live.add_argument("--metrics", default=None, help="optional metrics JSON")
    agent_shadow_live.add_argument("--decisions", default=None, help="optional decisions jsonl")
    agent_shadow_live.add_argument("--fills", default=None, help="optional fills jsonl")
    agent_shadow_live.add_argument("--max-snapshot-age-seconds", type=int, default=300, help="max snapshot age in seconds")
    agent_shadow_live.add_argument("--json", action="store_true", help="print comparison JSON to stdout")
    from atlas_agent.agent.gated_submit_conformance_cli import (
        CLI_DESCRIPTION as _GSC_DESCRIPTION,
    )
    from atlas_agent.agent.runtime_readiness_envelope_cli import (
        CLI_DESCRIPTION as _RE_DESCRIPTION,
    )
    from atlas_agent.agent.operator_approval_gate_cli import (
        CLI_DESCRIPTION as _OAG_DESCRIPTION,
    )
    from atlas_agent.agent.bounded_live_autonomy_readiness_cli import (
        CLI_DESCRIPTION as _BLAR_DESCRIPTION,
    )

    def _run_readiness_envelope_legacy_help(_args: argparse.Namespace) -> int:
        print("Runtime readiness envelope (CAND-007) is implemented configlessly as:")
        print("  atlas agent readiness-envelope ...")
        print("Use the configless form above; this delegated form is for --workspace compatibility only.")
        return 2

    agent_submit_conformance = agent_sub.add_parser(
        "submit-conformance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Gated submit conformance rehearsal (CAND-006) — simulated only.",
        description=_GSC_DESCRIPTION,
    )
    agent_submit_conformance.add_argument("--quality-gate", required=True)
    agent_submit_conformance.add_argument("--shadow-comparison", required=True)
    agent_submit_conformance.add_argument("--order-intent", required=True)
    agent_submit_conformance.add_argument("--kill-switch", required=True)
    agent_submit_conformance.add_argument("--risk-envelope", required=True)
    agent_submit_conformance.add_argument("--approval", required=True)
    agent_submit_conformance.add_argument("--output-dir", required=True)
    agent_submit_conformance.add_argument("--as-of", required=True)
    agent_submit_conformance.add_argument("--json", action="store_true")

    agent_readiness_envelope = agent_sub.add_parser(
        "readiness-envelope",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Runtime readiness envelope evaluation (CAND-007) — simulated only.",
        description=_RE_DESCRIPTION,
    )
    agent_readiness_envelope.add_argument("--quality-gate", help="Path to CAND-004 trading-quality-gate.json.")
    agent_readiness_envelope.add_argument("--shadow-comparison", help="Path to CAND-005 shadow-live-comparison.json.")
    agent_readiness_envelope.add_argument("--submit-conformance", help="Path to CAND-006 gated-submit-conformance.json.")
    agent_readiness_envelope.add_argument("--runtime-envelope", help="Path to the runtime envelope fixture.")
    agent_readiness_envelope.add_argument("--broker-capabilities", help="Path to the broker capability manifest fixture.")
    agent_readiness_envelope.add_argument("--operator-policy", help="Path to the operator policy fixture.")
    agent_readiness_envelope.add_argument("--kill-switch-policy", help="Path to the kill-switch policy fixture.")
    agent_readiness_envelope.add_argument("--audit-policy", help="Path to the audit policy fixture.")
    agent_readiness_envelope.add_argument("--output-dir", help="Output directory for artifacts.")
    agent_readiness_envelope.add_argument("--as-of", help="ISO-8601 UTC timestamp.")
    agent_readiness_envelope.add_argument("--json", action="store_true", help="Emit JSON on stdout.")
    agent_readiness_envelope.set_defaults(func=_run_readiness_envelope_legacy_help)

    def _run_operator_approval_gate_legacy_help(_args: argparse.Namespace) -> int:
        print("Operator approval gate (CAND-008) is implemented configlessly as:")
        print("  atlas agent operator-approval-gate ...")
        print("Use the configless form above; this delegated form is for --workspace compatibility only.")
        return 2

    agent_operator_approval_gate = agent_sub.add_parser(
        "operator-approval-gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Operator approval gate evaluation (CAND-008) — evidence-only, simulated-only.",
        description=_OAG_DESCRIPTION,
    )
    agent_operator_approval_gate.add_argument("--quality-gate", help="Path to CAND-004 trading-quality-gate.json.")
    agent_operator_approval_gate.add_argument("--shadow-comparison", help="Path to CAND-005 shadow-live-comparison.json.")
    agent_operator_approval_gate.add_argument("--submit-conformance", help="Path to CAND-006 gated-submit-conformance.json.")
    agent_operator_approval_gate.add_argument("--readiness-envelope", help="Path to CAND-007 runtime-readiness-envelope.json.")
    agent_operator_approval_gate.add_argument("--operator-identity", help="Path to the operator identity fixture.")
    agent_operator_approval_gate.add_argument("--approval-policy", help="Path to the approval policy fixture.")
    agent_operator_approval_gate.add_argument("--kill-switch-observation", help="Path to the kill-switch observation fixture.")
    agent_operator_approval_gate.add_argument("--operator-acknowledgment", help="Path to the operator acknowledgment fixture.")
    agent_operator_approval_gate.add_argument("--audit-policy", help="Path to the audit policy fixture.")
    agent_operator_approval_gate.add_argument("--output-dir", help="Output directory for artifacts.")
    agent_operator_approval_gate.add_argument("--as-of", help="ISO-8601 UTC timestamp.")
    agent_operator_approval_gate.add_argument("--json", action="store_true", help="Emit JSON on stdout.")
    agent_operator_approval_gate.set_defaults(func=_run_operator_approval_gate_legacy_help)

    def _run_bounded_live_readiness_legacy_help(_args: argparse.Namespace) -> int:
        print("Bounded live autonomy readiness (CAND-015) is implemented configlessly as:")
        print("  atlas agent bounded-live-readiness ...")
        print("Use the configless form above; this delegated form is for --workspace compatibility only.")
        return 2

    agent_bounded_live_readiness = agent_sub.add_parser(
        "bounded-live-readiness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Bounded live autonomy readiness evaluation (CAND-015) — evidence-only, simulated-only.",
        description=_BLAR_DESCRIPTION,
    )
    agent_bounded_live_readiness.add_argument("--quality-gate", help="Path to CAND-004 trading-quality-gate.json.")
    agent_bounded_live_readiness.add_argument("--shadow-comparison", help="Path to CAND-005 shadow-live-comparison.json.")
    agent_bounded_live_readiness.add_argument("--submit-conformance", help="Path to CAND-006 gated-submit-conformance.json.")
    agent_bounded_live_readiness.add_argument("--readiness-envelope", help="Path to CAND-007 runtime-readiness-envelope.json.")
    agent_bounded_live_readiness.add_argument("--operator-approval-gate", help="Path to CAND-008 operator-approval-gate.json.")
    agent_bounded_live_readiness.add_argument("--bounded-autonomy-policy", help="Path to the bounded autonomy policy fixture.")
    agent_bounded_live_readiness.add_argument("--risk-limit", help="Path to the risk limit fixture.")
    agent_bounded_live_readiness.add_argument("--symbol-allowlist", help="Path to the symbol allowlist fixture.")
    agent_bounded_live_readiness.add_argument("--heartbeat-deadman", help="Path to the heartbeat/deadman fixture.")
    agent_bounded_live_readiness.add_argument("--audit-redaction", help="Path to the audit redaction fixture.")
    agent_bounded_live_readiness.add_argument("--output-dir", help="Output directory for artifacts.")
    agent_bounded_live_readiness.add_argument("--as-of", help="ISO-8601 UTC timestamp.")
    agent_bounded_live_readiness.add_argument("--json", action="store_true", help="Emit JSON on stdout.")
    agent_bounded_live_readiness.set_defaults(func=_run_bounded_live_readiness_legacy_help)

    agent_sub.add_parser("learn")
    agent_sub.add_parser("reflect")

    skills = subparsers.add_parser("skills")
    skills_sub = skills.add_subparsers(dest="skills_command")
    skills_list = skills_sub.add_parser("list")
    skills_list.add_argument("--json", action="store_true")
    skills_sub.add_parser("propose")
    skills_sub.add_parser("create-from-journal")
    skills_sub.add_parser("improve")
    skills_approve = skills_sub.add_parser("approve")
    skills_approve.add_argument("skill_name")
    skills_archive = skills_sub.add_parser("archive")
    skills_archive.add_argument("skill_name")
    skills_show = skills_sub.add_parser("show")
    skills_show.add_argument("skill_name")
    skills_diff = skills_sub.add_parser("diff")
    skills_diff.add_argument("skill_name")

    # Skill candidate subcommands
    skills_create_candidate = skills_sub.add_parser(
        "create-candidate",
        help="Create a skill candidate from a local input file or reflection.",
    )
    skills_create_candidate.add_argument("--input", required=True, type=Path, help="Path to input artifact")
    skills_create_candidate.add_argument("--kind", choices=("report", "backtest", "research", "audit", "note", "reflection"), default=None, help="Input kind")
    skills_create_candidate.add_argument("--dry-run", action="store_true", default=True, help="Use static fallback (default)")
    skills_create_candidate.add_argument("--json", action="store_true", help="Emit as JSON")

    skills_list_candidates = skills_sub.add_parser("list-candidates", help="List skill candidates")
    skills_list_candidates.add_argument("--status", choices=("draft", "pending_review", "approved", "rejected", "archived", "promoted"), default=None, help="Filter by status")
    skills_list_candidates.add_argument("--json", action="store_true", help="Emit as JSON")

    skills_show_candidate = skills_sub.add_parser("show-candidate", help="Show a skill candidate")
    skills_show_candidate.add_argument("candidate_id", help="Candidate ID")
    skills_show_candidate.add_argument("--json", action="store_true", help="Emit as JSON")

    skills_submit_candidate = skills_sub.add_parser("submit-candidate", help="Submit a draft candidate for review")
    skills_submit_candidate.add_argument("candidate_id", help="Candidate ID")

    skills_approve_candidate = skills_sub.add_parser("approve-candidate", help="Approve a pending candidate")
    skills_approve_candidate.add_argument("candidate_id", help="Candidate ID")
    skills_approve_candidate.add_argument("--reason", default="", help="Approval reason")

    skills_reject_candidate = skills_sub.add_parser("reject-candidate", help="Reject a pending candidate")
    skills_reject_candidate.add_argument("candidate_id", help="Candidate ID")
    skills_reject_candidate.add_argument("--reason", required=True, help="Rejection reason")

    skills_archive_candidate = skills_sub.add_parser("archive-candidate", help="Archive an approved or rejected candidate")
    skills_archive_candidate.add_argument("candidate_id", help="Candidate ID")
    skills_archive_candidate.add_argument("--reason", default="", help="Archive reason")

    skills_promote_candidate = skills_sub.add_parser("promote-candidate", help="Promote an approved candidate to the skill library")
    skills_promote_candidate.add_argument("candidate_id", help="Candidate ID")

    skills_list_library = skills_sub.add_parser("list-library", help="List promoted skills in the library")
    skills_list_library.add_argument("--json", action="store_true", help="Emit as JSON")

    skills_show_library = skills_sub.add_parser("show-library", help="Show a promoted skill")
    skills_show_library.add_argument("skill_id", help="Skill ID")
    skills_show_library.add_argument("--json", action="store_true", help="Emit as JSON")

    memory = subparsers.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="memory_command")
    memory_ingest = memory_sub.add_parser("ingest")
    memory_ingest.add_argument("--file", type=Path, required=True)
    memory_search = memory_sub.add_parser("search")
    memory_search.add_argument("query")
    memory_search.add_argument("--json", action="store_true")
    memory_sub.add_parser("rebuild-index")
    memory_sub.add_parser("summarize")
    memory_sub.add_parser("nudge")
    memory_doctor = memory_sub.add_parser("doctor")
    memory_doctor.add_argument("--json", action="store_true")

    user = subparsers.add_parser("user")
    user_sub = user.add_subparsers(dest="user_command")
    user_sub.add_parser("show")
    user_remember = user_sub.add_parser("remember")
    user_remember.add_argument("text")
    user_forget = user_sub.add_parser("forget")
    user_forget.add_argument("query")
    user_sub.add_parser("update-from-reflection")

    learning = subparsers.add_parser("learning", help="Local learning suggestions. Offline, advisory-only.")
    learning_sub = learning.add_subparsers(dest="learning_command")
    learning_suggest = learning_sub.add_parser("suggest", help="Create a learning suggestion from a local input file")
    learning_suggest.add_argument("--input", required=True, type=Path, help="Path to input artifact")
    learning_suggest.add_argument("--kind", choices=("report", "backtest", "research", "audit", "note", "reflection", "skill"), default=None, help="Input kind")
    learning_suggest.add_argument("--dry-run", action="store_true", default=True, help="Use static fallback (default)")
    learning_suggest.add_argument("--json", action="store_true", help="Emit as JSON")
    learning_sub.add_parser("suggest-from-reflection", help="Create a suggestion from a reflection artifact")
    learning_sub.add_parser("suggest-from-skill", help="Create a suggestion from an approved skill")
    learning_list = learning_sub.add_parser("list-suggestions", help="List learning suggestions")
    learning_list.add_argument("--status", choices=("draft", "pending_review", "accepted", "rejected", "archived"), default=None, help="Filter by status")
    learning_list.add_argument("--json", action="store_true", help="Emit as JSON")
    learning_show = learning_sub.add_parser("show-suggestion", help="Show a learning suggestion")
    learning_show.add_argument("suggestion_id", help="Suggestion ID")
    learning_show.add_argument("--json", action="store_true", help="Emit as JSON")
    learning_submit = learning_sub.add_parser("submit-suggestion", help="Submit a draft suggestion for review")
    learning_submit.add_argument("suggestion_id", help="Suggestion ID")
    learning_accept = learning_sub.add_parser("accept-suggestion", help="Accept a pending suggestion")
    learning_accept.add_argument("suggestion_id", help="Suggestion ID")
    learning_accept.add_argument("--reason", default="", help="Acceptance reason")
    learning_reject = learning_sub.add_parser("reject-suggestion", help="Reject a pending suggestion")
    learning_reject.add_argument("suggestion_id", help="Suggestion ID")
    learning_reject.add_argument("--reason", required=True, help="Rejection reason")
    learning_archive = learning_sub.add_parser("archive-suggestion", help="Archive an accepted or rejected suggestion")
    learning_archive.add_argument("suggestion_id", help="Suggestion ID")
    learning_archive.add_argument("--reason", default="", help="Archive reason")

    discipline_parser = subparsers.add_parser("discipline")
    discipline_sub = discipline_parser.add_subparsers(dest="discipline_command")
    discipline_sub.add_parser("show")
    discipline_sub.add_parser("validate")
    discipline_set = discipline_sub.add_parser("set")
    discipline_set.add_argument("text", nargs="+", help="Freeform discipline text")
    discipline_sub.add_parser("generate")
    discipline_sub.add_parser("reset")
    discipline_setup = discipline_sub.add_parser("setup")
    discipline_setup.add_argument("--manual", action="store_true", help="Create from the default template with explicit confirmation")
    discipline_setup.add_argument("--yes", action="store_true", help="Non-interactive confirmation for manual setup")
    discipline_sub.add_parser("doctor")

    telegram = subparsers.add_parser("telegram")
    telegram_sub = telegram.add_subparsers(dest="telegram_command")
    telegram_sub.add_parser("run")
    telegram_sub.add_parser("test")
    telegram_kill = telegram_sub.add_parser("kill")
    telegram_kill.add_argument("--mode", choices=("soft", "cancel", "flatten"), default="soft")
    telegram_kill.add_argument("--reason", default="")
    telegram_resume = telegram_sub.add_parser("resume")
    telegram_resume.add_argument("--totp", default=None)
    telegram_resume.add_argument("--reason", default="")
    telegram_heartbeat = telegram_sub.add_parser("heartbeat")
    telegram_heartbeat.add_argument("--source", default="telegram")
    telegram_heartbeat.add_argument("--actor", default="telegram:user")

    deploy = subparsers.add_parser("deploy")
    deploy_sub = deploy.add_subparsers(dest="deploy_command")
    deploy_sub.add_parser("vps")
    deploy_sub.add_parser("systemd")
    deploy_sub.add_parser("docker")
    deploy_sub.add_parser("serverless")

    routine = subparsers.add_parser("routine")
    routine_sub = routine.add_subparsers(dest="routine_command")
    routine_run = routine_sub.add_parser("run")
    routine_run.add_argument("name", choices=sorted(ROUTINE_NAMES))
    routine_run.add_argument("--mode", choices=("paper", "live"), default="paper")
    routine_run.add_argument("--symbol", help="Trading symbol (defaults to market.symbol config)")
    routine_sub.add_parser("unlock")
    routine_sub.add_parser("status")

    scheduler = subparsers.add_parser("scheduler")
    scheduler_sub = scheduler.add_subparsers(dest="scheduler_command")
    scheduler_run = scheduler_sub.add_parser("run")
    scheduler_run.add_argument("--routine", default="market_open", choices=sorted(VALID_ROUTINES))
    scheduler_run.add_argument("--mode", choices=("paper", "live"), default="paper")

    report = subparsers.add_parser("report")
    report_sub = report.add_subparsers(dest="report_command")
    report_sub.add_parser("daily")
    report_generate = report_sub.add_parser(
        "generate",
        help="Generate a research report. Outputs a backtest summary or placeholder.",
    )
    report_generate.add_argument(
        "--type",
        choices=("daily", "weekly", "ad-hoc"),
        default="daily",
        help="Report type. Default: daily.",
    )
    report_generate.add_argument(
        "--format",
        choices=("json", "markdown", "text"),
        default="text",
        help="Output format. Default: text.",
    )
    report_generate.add_argument(
        "--output",
        default="stdout",
        help="Output path or 'stdout'. Default: stdout.",
    )
    report_generate.add_argument(
        "--run-id",
        default=None,
        help="Backtest run ID to generate a backtest summary for (legacy).",
    )

    portfolio = subparsers.add_parser("portfolio")
    portfolio_sub = portfolio.add_subparsers(dest="portfolio_command")
    portfolio_show = portfolio_sub.add_parser("show")
    portfolio_show.add_argument("--json", action="store_true")

    risk = subparsers.add_parser("risk")
    risk_sub = risk.add_subparsers(dest="risk_command")
    risk_sub.add_parser("check")
    risk_sub.add_parser("status")

    kill = subparsers.add_parser("kill")
    kill_sub = kill.add_subparsers(dest="kill_command")
    kill_sub.add_parser("status")
    kill_sub.add_parser("soft-pause")
    kill_sub.add_parser("cancel-all")
    kill_sub.add_parser("flatten-all")
    kill_sub.add_parser("lock")
    kill_sub.add_parser("reset")
    kill_sub.add_parser("heartbeat")
    kill_plan = kill_sub.add_parser("plan")
    kill_plan.add_argument("--mode", choices=("cancel-all", "flatten-all"), help="Simulate a specific mode")
    kill_plan.add_argument("--json", action="store_true", help="Emit plan as JSON")
    kill_exec = kill_sub.add_parser("execute-plan")
    kill_exec.add_argument("--plan", required=True, help="Path to safety action plan JSON")
    kill_exec.add_argument("--approved", action="store_true", help="Explicitly approve the plan")
    kill_exec.add_argument("--paper", action="store_true", help="Force paper mode simulation")

    kill_switch = subparsers.add_parser("kill-switch")
    kill_sub = kill_switch.add_subparsers(dest="kill_command")
    kill_enable = kill_sub.add_parser("enable")
    kill_enable.add_argument("--mode", choices=("soft", "cancel", "flatten"), default="soft")
    kill_enable.add_argument("--reason", default="")
    kill_disable = kill_sub.add_parser("disable")
    kill_disable.add_argument("--require-2fa", action="store_true")
    kill_disable.add_argument("--totp", default=None)
    kill_disable.add_argument("--reason", default="")
    kill_sub.add_parser("status")

    heartbeat = subparsers.add_parser("heartbeat")
    heartbeat.add_argument("--source", default="cli")
    heartbeat.add_argument("--actor", default="cli:user")

    approve = subparsers.add_parser("approve-order")
    approve.add_argument("order_id")

    submit = subparsers.add_parser("submit-approved-order")
    submit.add_argument("order_id")
    submit.add_argument("--dry-run", action="store_true")
    submit.add_argument("--reconcile", action="store_true")
    submit.add_argument("--json", action="store_true")

    research = subparsers.add_parser(
        "research",
        help="Paper-only research commands. Analysis-only. Does not submit orders.",
    )
    research_sub = research.add_subparsers(dest="research_command")
    research_market = research_sub.add_parser("market")
    research_market.add_argument("--symbol", required=True)
    research_market.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_run = research_sub.add_parser(
        "run",
        help="Run a paper-only research session and create a local artifact. Does not submit orders.",
    )
    research_run.add_argument("--symbol", required=True, help="Symbol to research (alphanumeric, dash, underscore, dot).")
    research_run.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_run.add_argument(
        "--provider",
        default="deterministic",
        help="Research provider. Only 'deterministic' is supported. Default: deterministic.",
    )
    research_run.add_argument(
        "--no-memory",
        action="store_true",
        help="Skip memory index lookup.",
    )

    research_list = research_sub.add_parser(
        "list",
        help="List local research artifacts. Read-only. Does not submit orders.",
    )
    research_list.add_argument("--symbol", help="Filter by symbol.")
    research_list.add_argument("--limit", type=int, default=20, help="Maximum items to show. Default: 20.")
    research_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_show = research_sub.add_parser(
        "show",
        help="Show a research artifact by run_id. Read-only. Does not submit orders.",
    )
    research_show.add_argument("run_id", help="Artifact run_id.")
    research_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_plan = research_sub.add_parser(
        "plan",
        help="Create a paper-only plan from a research artifact. Does not submit orders.",
    )
    research_plan.add_argument("run_id", help="Source research artifact run_id.")
    research_plan.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_plan.add_argument(
        "--provider",
        default="deterministic",
        help="Research provider. Only 'deterministic' is supported. Default: deterministic.",
    )

    research_summary = research_sub.add_parser(
        "summary",
        help="Summarize local research artifacts and paper plans. Read-only. Does not submit orders.",
        description="Summarize local research artifacts and paper plans. Read-only. Does not create artifacts, pending orders, or approvals.",
    )
    research_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_verify = research_sub.add_parser(
        "verify",
        help="Verify a paper plan artifact and create a verification artifact. Paper-only. Does not submit orders.",
        description="Verify a paper plan artifact and create a verification artifact. Paper-only. Does not create pending orders or approvals.",
    )
    research_verify.add_argument("plan_id", help="Plan ID to verify.")
    research_verify.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_verify.add_argument(
        "--provider",
        default="deterministic",
        help="Research provider. Only 'deterministic' is supported. Default: deterministic.",
    )

    research_evaluate = research_sub.add_parser(
        "evaluate",
        help="Evaluate a paper plan against local data and create an evaluation artifact. Paper-only. Does not submit orders.",
        description="Evaluate a paper plan against local data and create an evaluation artifact. Paper-only. Does not create pending orders or approvals.",
    )
    research_evaluate.add_argument("plan_id", help="Plan ID to evaluate.")
    research_evaluate.add_argument("--data", required=True, type=Path, help="Path to local OHLCV CSV data file.")
    research_evaluate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_evaluate.add_argument(
        "--provider",
        default="deterministic",
        help="Research provider. Only 'deterministic' is supported. Default: deterministic.",
    )

    research_check = research_sub.add_parser(
        "check-artifacts",
        help="Check local research artifact health. Read-only. Does not modify artifacts.",
        description="Check local research artifact health. Read-only. Does not modify artifacts, create pending orders, or approvals.",
    )
    research_check.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_check.add_argument("--symbol", help="Filter by symbol.")
    research_check.add_argument("--strict", action="store_true", help="Exit with code 2 if any issue is found.")

    research_timeline = research_sub.add_parser(
        "timeline",
        help="Show read-only research artifact lineage/timeline. Does not modify artifacts.",
        description="Show read-only research artifact lineage/timeline. Reconstructs relationships between research artifacts, paper plans, verifications, evaluations, prompt packets, provider responses, response reviews, and dossiers. Does not modify artifacts.",
    )
    research_timeline.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_timeline.add_argument("--symbol", help="Filter by symbol.")
    research_timeline.add_argument("--run-id", help="Filter by research run_id.")
    research_timeline.add_argument("--limit", type=int, default=20, help="Maximum entries. Default: 20, max: 100.")

    research_providers = research_sub.add_parser(
        "providers",
        help="List research providers. Read-only. Does not call providers or read API keys.",
        description="List research providers. Read-only discovery. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_providers.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_prompt = research_sub.add_parser(
        "prompt",
        help="Generate a sanitized prompt packet from a research artifact. Local-only. Does not call LLMs or network.",
        description="Generate a sanitized, bounded prompt packet artifact from an existing research artifact. Local-only. Does not call LLMs, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_prompt.add_argument("run_id", help="Source research artifact run_id.")
    research_prompt.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_prompt.add_argument(
        "--max-context-chars",
        type=int,
        default=8000,
        help="Maximum characters for user context. Default: 8000, max: 20000.",
    )

    research_sandbox = research_sub.add_parser(
        "sandbox",
        help="Build a local LLM sandbox request artifact from a prompt packet. Local-only. Does not call LLMs or network.",
        description="Build a bounded, local, replayable LLM sandbox request artifact from an existing prompt packet. Local-only. Does not call LLMs, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_sandbox.add_argument("prompt_packet_id", help="Source prompt packet ID.")
    research_sandbox.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_sandbox_list = research_sub.add_parser(
        "sandbox-list",
        help="List sandbox request artifacts. Read-only. Does not call providers or network.",
        description="List local sandbox request artifacts. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_sandbox_list.add_argument("--symbol", help="Filter by symbol.")
    research_sandbox_list.add_argument("--limit", type=int, default=20, help="Maximum items to show. Default: 20, max: 100.")
    research_sandbox_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_sandbox_show = research_sub.add_parser(
        "sandbox-show",
        help="Show a sandbox request artifact. Read-only. Does not call providers or network.",
        description="Show one local sandbox request artifact by ID. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_sandbox_show.add_argument("sandbox_request_id", help="Sandbox request ID.")
    research_sandbox_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_sandbox_validate = research_sub.add_parser(
        "sandbox-validate",
        help="Validate a sandbox request artifact against the local contract. Read-only.",
        description="Validate a sandbox request artifact against the local contract. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_sandbox_validate.add_argument("sandbox_request_id", help="Sandbox request ID.")
    research_sandbox_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_sandbox_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_sandbox_replay = research_sub.add_parser(
        "sandbox-replay",
        help="Replay a sandbox request from its source prompt packet and compare hashes. Read-only by default.",
        description="Rebuild the sandbox request from its source prompt packet and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_sandbox_replay.add_argument("sandbox_request_id", help="Sandbox request ID.")
    research_sandbox_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_sandbox_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")
    research_sandbox_replay.add_argument("--write", action="store_true", help="Write a new artifact on replay. Default is read-only.")

    research_import_provider = research_sub.add_parser(
        "import-provider-response",
        help="Import a local provider response JSON file. No network. No API keys.",
        description="Import a local provider response JSON file produced externally. No network. No API keys. No provider SDK. Validates payload and creates a provider response artifact only if safe.",
    )
    research_import_provider.add_argument("sandbox_request_id", help="Source sandbox request ID.")
    research_import_provider.add_argument("--file", type=Path, required=True, help="Path to local provider response JSON file.")
    research_import_provider.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_targets = research_sub.add_parser(
        "provider-targets",
        help="List disabled provider call targets. Read-only. No network.",
        description="List disabled provider call targets. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_targets.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    add_research_subparsers(research_sub)

    research_provider_execution_chain_doctor = research_sub.add_parser(
        "provider-execution-chain-doctor",
        help="Diagnose the provider execution chain for a research run. Read-only.",
        description="Read-only diagnostic of the provider execution chain for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_chain_doctor.add_argument("run_id", help="Research run ID.")
    research_provider_execution_chain_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_intake_policy = research_sub.add_parser(
        "provider-response-intake-policy",
        help="Create a provider response intake policy from a payload preview. Local-only. No network.",
        description="Create a provider response intake policy artifact from an existing provider outbound payload preview. Local-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_intake_policy.add_argument("provider_outbound_payload_preview_id", help="Provider outbound payload preview ID.")
    research_provider_response_intake_policy.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_intake_policy_list = research_sub.add_parser(
        "provider-response-intake-policy-list",
        help="List provider response intake policy artifacts. Read-only.",
        description="List provider response intake policy artifacts. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_intake_policy_list.add_argument("--symbol", help="Filter by symbol.")
    research_provider_response_intake_policy_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_intake_policy_show = research_sub.add_parser(
        "provider-response-intake-policy-show",
        help="Show a provider response intake policy artifact. Read-only.",
        description="Show a provider response intake policy artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_intake_policy_show.add_argument("provider_response_intake_policy_id", help="Provider response intake policy ID.")
    research_provider_response_intake_policy_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_intake_policy_validate = research_sub.add_parser(
        "provider-response-intake-policy-validate",
        help="Validate a provider response intake policy artifact. Read-only.",
        description="Validate a provider response intake policy artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_intake_policy_validate.add_argument("provider_response_intake_policy_id", help="Provider response intake policy ID.")
    research_provider_response_intake_policy_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_response_intake_policy_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_provider_response_intake_policy_replay = research_sub.add_parser(
        "provider-response-intake-policy-replay",
        help="Replay a provider response intake policy artifact. Read-only.",
        description="Replay a provider response intake policy artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_intake_policy_replay.add_argument("provider_response_intake_policy_id", help="Provider response intake policy ID.")
    research_provider_response_intake_policy_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_response_intake_policy_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")

    research_provider_response_intake_policy_summary = research_sub.add_parser(
        "provider-response-intake-policy-summary",
        help="Summarize the provider response intake policy state for a research run. Read-only.",
        description="Read-only summary of the provider response intake policy state for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_intake_policy_summary.add_argument("run_id", help="Research run ID.")
    research_provider_response_intake_policy_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_request_response_pairing = research_sub.add_parser(
        "provider-request-response-pairing",
        help="Create a provider request/response pairing contract from a response intake policy. Local-only. No network.",
        description="Create a provider request/response pairing contract artifact from an existing provider response intake policy. Local-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_request_response_pairing.add_argument("intake_policy_id", help="Source provider response intake policy ID.")
    research_provider_request_response_pairing.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_request_response_pairing_list = research_sub.add_parser(
        "provider-request-response-pairing-list",
        help="List provider request/response pairing contract artifacts. Read-only.",
        description="List provider request/response pairing contract artifacts. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_request_response_pairing_list.add_argument("--symbol", default="", help="Filter by symbol.")
    research_provider_request_response_pairing_list.add_argument("--limit", type=int, default=20, help="Max items. Default 20, max 100.")
    research_provider_request_response_pairing_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_request_response_pairing_show = research_sub.add_parser(
        "provider-request-response-pairing-show",
        help="Show a provider request/response pairing contract artifact. Read-only.",
        description="Show a provider request/response pairing contract artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_request_response_pairing_show.add_argument("pairing_id", help="Provider request/response pairing ID.")
    research_provider_request_response_pairing_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_request_response_pairing_validate = research_sub.add_parser(
        "provider-request-response-pairing-validate",
        help="Validate a provider request/response pairing contract artifact. Read-only.",
        description="Validate a provider request/response pairing contract artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_request_response_pairing_validate.add_argument("pairing_id", help="Provider request/response pairing ID.")
    research_provider_request_response_pairing_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_request_response_pairing_validate.add_argument("--strict", action="store_true", help="Exit nonzero if validation fails.")

    research_provider_request_response_pairing_replay = research_sub.add_parser(
        "provider-request-response-pairing-replay",
        help="Replay a provider request/response pairing contract artifact. Read-only.",
        description="Replay a provider request/response pairing contract artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_request_response_pairing_replay.add_argument("pairing_id", help="Provider request/response pairing ID.")
    research_provider_request_response_pairing_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_request_response_pairing_replay.add_argument("--strict", action="store_true", help="Exit nonzero if replay mismatch.")

    research_provider_request_response_pairing_summary = research_sub.add_parser(
        "provider-request-response-pairing-summary",
        help="Summarize the provider request/response pairing contract state for a research run. Read-only.",
        description="Read-only summary of the provider request/response pairing contract state for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_request_response_pairing_summary.add_argument("run_id", help="Research run ID.")
    research_provider_request_response_pairing_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_request_response_pairing_doctor = research_sub.add_parser(
        "provider-request-response-pairing-doctor",
        help="Diagnose the provider request/response pairing chain for a research run. Read-only.",
        description="Read-only diagnostic of the provider request/response pairing chain for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_request_response_pairing_doctor.add_argument("run_id", help="Research run ID.")
    research_provider_request_response_pairing_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_schema_contract = research_sub.add_parser(
        "provider-response-schema-contract",
        help="Create a provider response schema contract from a request/response pairing. Local-only. No network.",
        description="Create a provider response schema contract artifact from an existing provider request/response pairing. Local-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_schema_contract.add_argument("pairing_id", help="Source provider request/response pairing ID.")
    research_provider_response_schema_contract.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_schema_contract_list = research_sub.add_parser(
        "provider-response-schema-contract-list",
        help="List provider response schema contract artifacts. Read-only.",
        description="List provider response schema contract artifacts. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_schema_contract_list.add_argument("--symbol", default="", help="Filter by symbol.")
    research_provider_response_schema_contract_list.add_argument("--limit", type=int, default=20, help="Max items. Default 20, max 100.")
    research_provider_response_schema_contract_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_schema_contract_show = research_sub.add_parser(
        "provider-response-schema-contract-show",
        help="Show a provider response schema contract artifact. Read-only.",
        description="Show a provider response schema contract artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_schema_contract_show.add_argument("contract_id", help="Provider response schema contract ID.")
    research_provider_response_schema_contract_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_schema_contract_validate = research_sub.add_parser(
        "provider-response-schema-contract-validate",
        help="Validate a provider response schema contract artifact. Read-only.",
        description="Validate a provider response schema contract artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_schema_contract_validate.add_argument("contract_id", help="Provider response schema contract ID.")
    research_provider_response_schema_contract_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_response_schema_contract_validate.add_argument("--strict", action="store_true", help="Exit nonzero if validation fails.")

    research_provider_response_schema_contract_replay = research_sub.add_parser(
        "provider-response-schema-contract-replay",
        help="Replay a provider response schema contract artifact. Read-only.",
        description="Replay a provider response schema contract artifact. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_schema_contract_replay.add_argument("contract_id", help="Provider response schema contract ID.")
    research_provider_response_schema_contract_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_response_schema_contract_replay.add_argument("--strict", action="store_true", help="Exit nonzero if replay mismatch.")

    research_provider_response_schema_contract_summary = research_sub.add_parser(
        "provider-response-schema-contract-summary",
        help="Summarize the provider response schema contract state for a research run. Read-only.",
        description="Read-only summary of the provider response schema contract state for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_schema_contract_summary.add_argument("run_id", help="Research run ID.")
    research_provider_response_schema_contract_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_schema_contract_doctor = research_sub.add_parser(
        "provider-response-schema-contract-doctor",
        help="Diagnose the provider response schema contract chain for a research run. Read-only.",
        description="Read-only diagnostic of the provider response schema contract chain for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_schema_contract_doctor.add_argument("run_id", help="Research run ID.")
    research_provider_response_schema_contract_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_review_result = research_sub.add_parser(
        "provider-response-review-result",
        help="Create a provider response review result contract artifact from a schema contract. Local-only.",
        description="Create a local provider response review result contract artifact from a provider response schema contract. Local-only. Does not call providers, read API keys, load .env.atlas, read os.environ, modify config, or authorize live trading.",
    )
    research_provider_response_review_result.add_argument("schema_contract_id", help="Source provider response schema contract ID.")
    research_provider_response_review_result.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_review_result_list = research_sub.add_parser(
        "provider-response-review-result-list",
        help="List provider response review result artifacts. Read-only.",
        description="List local provider response review result artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_review_result_list.add_argument("--symbol", default="", help="Filter by symbol.")
    research_provider_response_review_result_list.add_argument("--limit", type=int, default=20, help="Max items. Default 20, max 100.")
    research_provider_response_review_result_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_review_result_show = research_sub.add_parser(
        "provider-response-review-result-show",
        help="Show one provider response review result artifact. Read-only.",
        description="Show one provider response review result artifact. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_review_result_show.add_argument("review_result_id", help="Provider response review result ID.")
    research_provider_response_review_result_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_review_result_validate = research_sub.add_parser(
        "provider-response-review-result-validate",
        help="Validate a provider response review result artifact. Read-only.",
        description="Validate a provider response review result artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_review_result_validate.add_argument("review_result_id", help="Provider response review result ID.")
    research_provider_response_review_result_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_response_review_result_validate.add_argument("--strict", action="store_true", help="Exit nonzero if validation fails.")

    research_provider_response_review_result_replay = research_sub.add_parser(
        "provider-response-review-result-replay",
        help="Replay a provider response review result artifact from its source schema contract and compare hashes. Read-only by default.",
        description="Rebuild the provider response review result artifact from its source schema contract and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_response_review_result_replay.add_argument("review_result_id", help="Provider response review result ID.")
    research_provider_response_review_result_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_response_review_result_replay.add_argument("--strict", action="store_true", help="Exit nonzero if replay does not match.")

    research_provider_response_review_result_summary = research_sub.add_parser(
        "provider-response-review-result-summary",
        help="Summarize the provider response review result state for a research run. Read-only.",
        description="Read-only summary of the provider response review result state for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_review_result_summary.add_argument("run_id", help="Research run ID.")
    research_provider_response_review_result_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_response_review_result_doctor = research_sub.add_parser(
        "provider-response-review-result-doctor",
        help="Diagnose the provider response review result chain for a research run. Read-only.",
        description="Read-only diagnostic of the provider response review result chain for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_response_review_result_doctor.add_argument("run_id", help="Research run ID.")
    research_provider_response_review_result_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_unlock_state = research_sub.add_parser(
        "provider-execution-unlock-state",
        help="Create a provider execution unlock state artifact from a review result. Local-only.",
        description="Create a local provider execution unlock state artifact from a provider response review result. Local-only. Does not call providers, read API keys, load .env.atlas, read os.environ, modify config, or authorize live trading.",
    )
    research_provider_execution_unlock_state.add_argument("review_result_id", help="Source provider response review result ID.")
    research_provider_execution_unlock_state.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_unlock_state_list = research_sub.add_parser(
        "provider-execution-unlock-state-list",
        help="List provider execution unlock state artifacts. Read-only.",
        description="List local provider execution unlock state artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_unlock_state_list.add_argument("--symbol", default="", help="Filter by symbol.")
    research_provider_execution_unlock_state_list.add_argument("--limit", type=int, default=20, help="Max items. Default 20, max 100.")
    research_provider_execution_unlock_state_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_unlock_state_show = research_sub.add_parser(
        "provider-execution-unlock-state-show",
        help="Show one provider execution unlock state artifact. Read-only.",
        description="Show one provider execution unlock state artifact. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_unlock_state_show.add_argument("unlock_state_id", help="Provider execution unlock state ID.")
    research_provider_execution_unlock_state_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_unlock_state_validate = research_sub.add_parser(
        "provider-execution-unlock-state-validate",
        help="Validate a provider execution unlock state artifact. Read-only.",
        description="Validate a provider execution unlock state artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_unlock_state_validate.add_argument("unlock_state_id", help="Provider execution unlock state ID.")
    research_provider_execution_unlock_state_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_unlock_state_validate.add_argument("--strict", action="store_true", help="Exit nonzero if validation fails.")

    research_provider_execution_unlock_state_replay = research_sub.add_parser(
        "provider-execution-unlock-state-replay",
        help="Replay a provider execution unlock state artifact from its source review result and compare hashes. Read-only by default.",
        description="Rebuild the provider execution unlock state artifact from its source review result and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_unlock_state_replay.add_argument("unlock_state_id", help="Provider execution unlock state ID.")
    research_provider_execution_unlock_state_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_unlock_state_replay.add_argument("--strict", action="store_true", help="Exit nonzero if replay does not match.")

    research_provider_execution_unlock_state_summary = research_sub.add_parser(
        "provider-execution-unlock-state-summary",
        help="Summarize the provider execution unlock state for a research run. Read-only.",
        description="Read-only summary of the provider execution unlock state for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_unlock_state_summary.add_argument("run_id", help="Research run ID.")
    research_provider_execution_unlock_state_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_unlock_state_doctor = research_sub.add_parser(
        "provider-execution-unlock-state-doctor",
        help="Diagnose the provider execution unlock state chain for a research run. Read-only.",
        description="Read-only diagnostic of the provider execution unlock state chain for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_unlock_state_doctor.add_argument("run_id", help="Research run ID.")
    research_provider_execution_unlock_state_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_adapter_interface_contract = research_sub.add_parser(
        "provider-adapter-interface-contract",
        help="Create a provider adapter interface contract artifact from an unlock state. Local-only.",
        description="Create a local provider adapter interface contract artifact from a provider execution unlock state. Local-only. Does not implement real providers, call network, read API keys, load .env.atlas, read os.environ, modify config, or authorize live trading.",
    )
    research_provider_adapter_interface_contract.add_argument("unlock_state_id", help="Source provider execution unlock state ID.")
    research_provider_adapter_interface_contract.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_adapter_interface_contract_list = research_sub.add_parser(
        "provider-adapter-interface-contract-list",
        help="List provider adapter interface contract artifacts. Read-only.",
        description="List local provider adapter interface contract artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_adapter_interface_contract_list.add_argument("--symbol", default="", help="Filter by symbol.")
    research_provider_adapter_interface_contract_list.add_argument("--limit", type=int, default=20, help="Max items. Default 20, max 100.")
    research_provider_adapter_interface_contract_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_adapter_interface_contract_show = research_sub.add_parser(
        "provider-adapter-interface-contract-show",
        help="Show one provider adapter interface contract artifact. Read-only.",
        description="Show one provider adapter interface contract artifact. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_adapter_interface_contract_show.add_argument("contract_id", help="Provider adapter interface contract ID.")
    research_provider_adapter_interface_contract_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_adapter_interface_contract_validate = research_sub.add_parser(
        "provider-adapter-interface-contract-validate",
        help="Validate a provider adapter interface contract artifact. Read-only.",
        description="Validate a provider adapter interface contract artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_adapter_interface_contract_validate.add_argument("contract_id", help="Provider adapter interface contract ID.")
    research_provider_adapter_interface_contract_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_adapter_interface_contract_validate.add_argument("--strict", action="store_true", help="Exit nonzero if validation fails.")

    research_provider_adapter_interface_contract_replay = research_sub.add_parser(
        "provider-adapter-interface-contract-replay",
        help="Replay a provider adapter interface contract artifact from its source unlock state and compare hashes. Read-only by default.",
        description="Rebuild the provider adapter interface contract artifact from its source unlock state and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_adapter_interface_contract_replay.add_argument("contract_id", help="Provider adapter interface contract ID.")
    research_provider_adapter_interface_contract_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_adapter_interface_contract_replay.add_argument("--strict", action="store_true", help="Exit nonzero if replay does not match.")

    research_provider_adapter_interface_contract_summary = research_sub.add_parser(
        "provider-adapter-interface-contract-summary",
        help="Summarize the provider adapter interface contract for a research run. Read-only.",
        description="Read-only summary of the provider adapter interface contract for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_adapter_interface_contract_summary.add_argument("run_id", help="Research run ID.")
    research_provider_adapter_interface_contract_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_adapter_interface_contract_doctor = research_sub.add_parser(
        "provider-adapter-interface-contract-doctor",
        help="Diagnose the provider adapter interface contract chain for a research run. Read-only.",
        description="Read-only diagnostic of the provider adapter interface contract chain for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_adapter_interface_contract_doctor.add_argument("run_id", help="Research run ID.")
    research_provider_adapter_interface_contract_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_adapter_disabled_smoke = research_sub.add_parser(
        "provider-adapter-disabled-smoke",
        help="Exercise the disabled adapter harness and prove it cannot call providers. Read-only.",
        description="Exercise the disabled adapter harness and prove it cannot call providers. Read-only. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_adapter_disabled_smoke.add_argument("contract_id", help="Provider adapter interface contract ID.")
    research_provider_adapter_disabled_smoke.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_simulate = research_sub.add_parser(
        "provider-mock-response-simulate",
        help="Create a provider mock response simulation artifact from an adapter interface contract. Configless.",
        description="Create a provider mock response simulation artifact from an existing adapter interface contract. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_simulate.add_argument("contract_id", help="Source provider adapter interface contract ID.")
    research_provider_mock_response_simulate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_list = research_sub.add_parser(
        "provider-mock-response-list",
        help="List provider mock response simulation artifacts. Configless.",
        description="List provider mock response simulation artifacts. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_list.add_argument("--symbol", default=None, help="Filter by symbol.")
    research_provider_mock_response_list.add_argument("--limit", type=int, default=100, help="Limit results. Default 100.")
    research_provider_mock_response_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_show = research_sub.add_parser(
        "provider-mock-response-show",
        help="Show a provider mock response simulation artifact. Configless.",
        description="Show a provider mock response simulation artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_show.add_argument("simulation_id", help="Provider mock response simulation ID.")
    research_provider_mock_response_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_validate = research_sub.add_parser(
        "provider-mock-response-validate",
        help="Validate a provider mock response simulation artifact. Configless.",
        description="Validate a provider mock response simulation artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_validate.add_argument("simulation_id", help="Provider mock response simulation ID.")
    research_provider_mock_response_validate.add_argument("--strict", action="store_true", help="Exit non-zero on any failed check.")
    research_provider_mock_response_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_replay = research_sub.add_parser(
        "provider-mock-response-replay",
        help="Replay a provider mock response simulation artifact. Configless.",
        description="Replay a provider mock response simulation artifact deterministically. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_replay.add_argument("simulation_id", help="Provider mock response simulation ID.")
    research_provider_mock_response_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay hash does not match.")
    research_provider_mock_response_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_summary = research_sub.add_parser(
        "provider-mock-response-summary",
        help="Summarize the latest provider mock response simulation for a run. Configless.",
        description="Summarize the latest provider mock response simulation for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_summary.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_doctor = research_sub.add_parser(
        "provider-mock-response-doctor",
        help="Diagnose provider mock response simulation readiness for a run. Configless.",
        description="Diagnose provider mock response simulation readiness for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_doctor.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_import_candidate = research_sub.add_parser(
        "provider-mock-response-import-candidate",
        help="Create a provider mock response import candidate from a mock response simulation. Configless.",
        description="Create a provider mock response import candidate artifact from an existing provider mock response simulation. Configless. Does not import real provider responses, read external files, accept stdin, call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_import_candidate.add_argument("simulation_id", help="Source provider mock response simulation ID.")
    research_provider_mock_response_import_candidate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_import_candidate_list = research_sub.add_parser(
        "provider-mock-response-import-candidate-list",
        help="List provider mock response import candidate artifacts. Configless.",
        description="List provider mock response import candidate artifacts. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_import_candidate_list.add_argument("--symbol", default=None, help="Filter by symbol.")
    research_provider_mock_response_import_candidate_list.add_argument("--limit", type=int, default=100, help="Limit results. Default 100.")
    research_provider_mock_response_import_candidate_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_import_candidate_show = research_sub.add_parser(
        "provider-mock-response-import-candidate-show",
        help="Show a provider mock response import candidate artifact. Configless.",
        description="Show a provider mock response import candidate artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_import_candidate_show.add_argument("candidate_id", help="Provider mock response import candidate ID.")
    research_provider_mock_response_import_candidate_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_import_candidate_validate = research_sub.add_parser(
        "provider-mock-response-import-candidate-validate",
        help="Validate a provider mock response import candidate artifact. Configless.",
        description="Validate a provider mock response import candidate artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_import_candidate_validate.add_argument("candidate_id", help="Provider mock response import candidate ID.")
    research_provider_mock_response_import_candidate_validate.add_argument("--strict", action="store_true", help="Exit non-zero on any failed check.")
    research_provider_mock_response_import_candidate_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_import_candidate_replay = research_sub.add_parser(
        "provider-mock-response-import-candidate-replay",
        help="Replay a provider mock response import candidate artifact. Configless.",
        description="Replay a provider mock response import candidate artifact deterministically. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_import_candidate_replay.add_argument("candidate_id", help="Provider mock response import candidate ID.")
    research_provider_mock_response_import_candidate_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay hash does not match.")
    research_provider_mock_response_import_candidate_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_import_candidate_summary = research_sub.add_parser(
        "provider-mock-response-import-candidate-summary",
        help="Summarize the latest provider mock response import candidate for a run. Configless.",
        description="Summarize the latest provider mock response import candidate for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_import_candidate_summary.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_import_candidate_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_import_candidate_doctor = research_sub.add_parser(
        "provider-mock-response-import-candidate-doctor",
        help="Diagnose provider mock response import candidate readiness for a run. Configless.",
        description="Diagnose provider mock response import candidate readiness for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_import_candidate_doctor.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_import_candidate_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_review_sandbox = research_sub.add_parser(
        "provider-mock-response-review-sandbox",
        help="Create a provider mock response review sandbox from a mock response import candidate. Configless.",
        description="Create a provider mock response review sandbox artifact from an existing provider mock response import candidate. Configless. Does not review real provider responses, read external files, accept stdin, call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_review_sandbox.add_argument("import_candidate_id", help="Source provider mock response import candidate ID.")
    research_provider_mock_response_review_sandbox.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_review_sandbox_list = research_sub.add_parser(
        "provider-mock-response-review-sandbox-list",
        help="List provider mock response review sandbox artifacts. Configless.",
        description="List provider mock response review sandbox artifacts. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_review_sandbox_list.add_argument("--symbol", default=None, help="Filter by symbol.")
    research_provider_mock_response_review_sandbox_list.add_argument("--limit", type=int, default=100, help="Limit results. Default 100.")
    research_provider_mock_response_review_sandbox_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_review_sandbox_show = research_sub.add_parser(
        "provider-mock-response-review-sandbox-show",
        help="Show a provider mock response review sandbox artifact. Configless.",
        description="Show a provider mock response review sandbox artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_review_sandbox_show.add_argument("sandbox_id", help="Provider mock response review sandbox ID.")
    research_provider_mock_response_review_sandbox_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_review_sandbox_validate = research_sub.add_parser(
        "provider-mock-response-review-sandbox-validate",
        help="Validate a provider mock response review sandbox artifact. Configless.",
        description="Validate a provider mock response review sandbox artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_review_sandbox_validate.add_argument("sandbox_id", help="Provider mock response review sandbox ID.")
    research_provider_mock_response_review_sandbox_validate.add_argument("--strict", action="store_true", help="Exit non-zero on any failed check.")
    research_provider_mock_response_review_sandbox_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_review_sandbox_replay = research_sub.add_parser(
        "provider-mock-response-review-sandbox-replay",
        help="Replay a provider mock response review sandbox artifact. Configless.",
        description="Replay a provider mock response review sandbox artifact deterministically. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_review_sandbox_replay.add_argument("sandbox_id", help="Provider mock response review sandbox ID.")
    research_provider_mock_response_review_sandbox_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay hash does not match.")
    research_provider_mock_response_review_sandbox_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_review_sandbox_summary = research_sub.add_parser(
        "provider-mock-response-review-sandbox-summary",
        help="Summarize the latest provider mock response review sandbox for a run. Configless.",
        description="Summarize the latest provider mock response review sandbox for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_review_sandbox_summary.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_review_sandbox_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_review_sandbox_doctor = research_sub.add_parser(
        "provider-mock-response-review-sandbox-doctor",
        help="Diagnose provider mock response review sandbox readiness for a run. Configless.",
        description="Diagnose provider mock response review sandbox readiness for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_review_sandbox_doctor.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_review_sandbox_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_trust_decision_blocker = research_sub.add_parser(
        "provider-mock-response-trust-decision-blocker",
        help="Create a provider mock response trust decision blocker from a review sandbox. Configless.",
        description="Create a provider mock response trust decision blocker artifact from an existing provider mock response review sandbox. Configless. Does not create trust decisions, upgrade trust, grant approvals, call providers, read API keys, perform network requests, submit orders, or authorize live trading.",
    )
    research_provider_mock_response_trust_decision_blocker.add_argument("review_sandbox_id", help="Source provider mock response review sandbox ID.")
    research_provider_mock_response_trust_decision_blocker.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_trust_decision_blocker_list = research_sub.add_parser(
        "provider-mock-response-trust-decision-blocker-list",
        help="List provider mock response trust decision blocker artifacts. Configless.",
        description="List provider mock response trust decision blocker artifacts. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_trust_decision_blocker_list.add_argument("--symbol", default=None, help="Filter by symbol.")
    research_provider_mock_response_trust_decision_blocker_list.add_argument("--limit", type=int, default=20, help="Limit results. Default 20, max 100.")
    research_provider_mock_response_trust_decision_blocker_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_trust_decision_blocker_show = research_sub.add_parser(
        "provider-mock-response-trust-decision-blocker-show",
        help="Show a provider mock response trust decision blocker artifact. Configless.",
        description="Show a provider mock response trust decision blocker artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_trust_decision_blocker_show.add_argument("blocker_id", help="Provider mock response trust decision blocker ID.")
    research_provider_mock_response_trust_decision_blocker_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_trust_decision_blocker_validate = research_sub.add_parser(
        "provider-mock-response-trust-decision-blocker-validate",
        help="Validate a provider mock response trust decision blocker artifact. Configless.",
        description="Validate a provider mock response trust decision blocker artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_trust_decision_blocker_validate.add_argument("blocker_id", help="Provider mock response trust decision blocker ID.")
    research_provider_mock_response_trust_decision_blocker_validate.add_argument("--strict", action="store_true", help="Exit non-zero on any failed check.")
    research_provider_mock_response_trust_decision_blocker_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_trust_decision_blocker_replay = research_sub.add_parser(
        "provider-mock-response-trust-decision-blocker-replay",
        help="Replay a provider mock response trust decision blocker artifact. Configless.",
        description="Replay a provider mock response trust decision blocker artifact deterministically. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_trust_decision_blocker_replay.add_argument("blocker_id", help="Provider mock response trust decision blocker ID.")
    research_provider_mock_response_trust_decision_blocker_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay hash does not match.")
    research_provider_mock_response_trust_decision_blocker_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_trust_decision_blocker_summary = research_sub.add_parser(
        "provider-mock-response-trust-decision-blocker-summary",
        help="Summarize the latest provider mock response trust decision blocker for a run. Configless.",
        description="Summarize the latest provider mock response trust decision blocker for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_trust_decision_blocker_summary.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_trust_decision_blocker_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_trust_decision_blocker_doctor = research_sub.add_parser(
        "provider-mock-response-trust-decision-blocker-doctor",
        help="Diagnose provider mock response trust decision blocker readiness for a run. Configless.",
        description="Diagnose provider mock response trust decision blocker readiness for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_trust_decision_blocker_doctor.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_trust_decision_blocker_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_final_safety_seal = research_sub.add_parser(
        "provider-mock-response-final-safety-seal",
        help="Create a provider mock response final safety seal from a trust decision blocker. Configless.",
        description="Create a provider mock response final safety seal artifact from an existing provider mock response trust decision blocker. Configless. Does not create trust decisions, upgrade trust, grant approvals, call providers, read API keys, perform network requests, submit orders, or authorize live trading.",
    )
    research_provider_mock_response_final_safety_seal.add_argument("blocker_id", help="Source provider mock response trust decision blocker ID.")
    research_provider_mock_response_final_safety_seal.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_final_safety_seal_list = research_sub.add_parser(
        "provider-mock-response-final-safety-seal-list",
        help="List provider mock response final safety seal artifacts. Configless.",
        description="List provider mock response final safety seal artifacts. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_final_safety_seal_list.add_argument("--symbol", default=None, help="Filter by symbol.")
    research_provider_mock_response_final_safety_seal_list.add_argument("--limit", type=int, default=20, help="Limit results. Default 20, max 100.")
    research_provider_mock_response_final_safety_seal_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_final_safety_seal_show = research_sub.add_parser(
        "provider-mock-response-final-safety-seal-show",
        help="Show a provider mock response final safety seal artifact. Configless.",
        description="Show a provider mock response final safety seal artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_final_safety_seal_show.add_argument("seal_id", help="Provider mock response final safety seal ID.")
    research_provider_mock_response_final_safety_seal_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_final_safety_seal_validate = research_sub.add_parser(
        "provider-mock-response-final-safety-seal-validate",
        help="Validate a provider mock response final safety seal artifact. Configless.",
        description="Validate a provider mock response final safety seal artifact. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_final_safety_seal_validate.add_argument("seal_id", help="Provider mock response final safety seal ID.")
    research_provider_mock_response_final_safety_seal_validate.add_argument("--strict", action="store_true", help="Exit non-zero on any failed check.")
    research_provider_mock_response_final_safety_seal_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_final_safety_seal_replay = research_sub.add_parser(
        "provider-mock-response-final-safety-seal-replay",
        help="Replay a provider mock response final safety seal artifact. Configless.",
        description="Replay a provider mock response final safety seal artifact deterministically. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_final_safety_seal_replay.add_argument("seal_id", help="Provider mock response final safety seal ID.")
    research_provider_mock_response_final_safety_seal_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay hash does not match.")
    research_provider_mock_response_final_safety_seal_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_final_safety_seal_summary = research_sub.add_parser(
        "provider-mock-response-final-safety-seal-summary",
        help="Summarize the latest provider mock response final safety seal for a run. Configless.",
        description="Summarize the latest provider mock response final safety seal for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_final_safety_seal_summary.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_final_safety_seal_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_mock_response_final_safety_seal_doctor = research_sub.add_parser(
        "provider-mock-response-final-safety-seal-doctor",
        help="Diagnose provider mock response final safety seal readiness for a run. Configless.",
        description="Diagnose provider mock response final safety seal readiness for a run. Configless. Does not call providers, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_provider_mock_response_final_safety_seal_doctor.add_argument("run_id", help="Run ID.")
    research_provider_mock_response_final_safety_seal_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier = research_sub.add_parser(
        "provider-safety-dossier", help="Create a provider safety dossier."
    )
    research_provider_safety_dossier.add_argument("seal_id", help="Source provider mock response final safety seal ID.")
    research_provider_safety_dossier.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier_list = research_sub.add_parser(
        "provider-safety-dossier-list", help="List provider safety dossiers."
    )
    research_provider_safety_dossier_list.add_argument("--symbol", default=None, help="Filter by symbol.")
    research_provider_safety_dossier_list.add_argument("--status", default=None, help="Filter by safe status: sandbox_chain_complete, chain_incomplete, chain_invalid, unsafe_tamper_detected.")
    research_provider_safety_dossier_list.add_argument("--limit", type=int, default=20, help="Limit results. Default 20, max 100.")
    research_provider_safety_dossier_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier_latest = research_sub.add_parser(
        "provider-safety-dossier-latest", help="Get the latest valid provider safety dossier. Configless."
    )
    research_provider_safety_dossier_latest.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier_show = research_sub.add_parser(
        "provider-safety-dossier-show", help="Show a provider safety dossier."
    )
    research_provider_safety_dossier_show.add_argument("dossier_id", help="Provider safety dossier ID.")
    research_provider_safety_dossier_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier_validate = research_sub.add_parser(
        "provider-safety-dossier-validate", help="Validate a provider safety dossier."
    )
    research_provider_safety_dossier_validate.add_argument("dossier_id", help="Provider safety dossier ID.")
    research_provider_safety_dossier_validate.add_argument("--strict", action="store_true", help="Exit non-zero on any failed check.")
    research_provider_safety_dossier_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier_replay = research_sub.add_parser(
        "provider-safety-dossier-replay", help="Replay a provider safety dossier."
    )
    research_provider_safety_dossier_replay.add_argument("dossier_id", help="Provider safety dossier ID.")
    research_provider_safety_dossier_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay hash does not match.")
    research_provider_safety_dossier_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier_summary = research_sub.add_parser(
        "provider-safety-dossier-summary", help="Summarize a provider safety dossier."
    )
    research_provider_safety_dossier_summary.add_argument("run_id", help="Run ID.")
    research_provider_safety_dossier_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier_doctor = research_sub.add_parser(
        "provider-safety-dossier-doctor", help="Doctor a provider safety dossier."
    )
    research_provider_safety_dossier_doctor.add_argument("run_id", help="Run ID.")
    research_provider_safety_dossier_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_safety_dossier_export = research_sub.add_parser(
        "provider-safety-dossier-export", help="Export a provider safety dossier to Markdown. Configless."
    )
    research_provider_safety_dossier_export.add_argument("dossier_id", help="Provider safety dossier ID.")
    research_provider_safety_dossier_export.add_argument("--output", required=True, help="Output Markdown file path.")
    research_provider_safety_dossier_export.add_argument("--format", default="markdown", help="Export format. Default: markdown.")
    research_provider_safety_dossier_export.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_readiness = research_sub.add_parser(
        "release-candidate-readiness", help="Create a release candidate readiness report."
    )
    research_release_candidate_readiness.add_argument("--symbol", default="ATLAS-DEMO", help="Symbol to tag the report. Default: ATLAS-DEMO.")
    research_release_candidate_readiness.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_readiness_list = research_sub.add_parser(
        "release-candidate-readiness-list", help="List release candidate readiness reports."
    )
    research_release_candidate_readiness_list.add_argument("--symbol", default=None, help="Filter by symbol.")
    research_release_candidate_readiness_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_readiness_show = research_sub.add_parser(
        "release-candidate-readiness-show", help="Show a release candidate readiness report."
    )
    research_release_candidate_readiness_show.add_argument("report_id", help="Report ID.")
    research_release_candidate_readiness_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_readiness_validate = research_sub.add_parser(
        "release-candidate-readiness-validate", help="Validate a release candidate readiness report."
    )
    research_release_candidate_readiness_validate.add_argument("report_id", help="Report ID.")
    research_release_candidate_readiness_validate.add_argument("--strict", action="store_true", help="Exit non-zero for invalid reports.")
    research_release_candidate_readiness_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_readiness_summary = research_sub.add_parser(
        "release-candidate-readiness-summary", help="Summarize a release candidate readiness report."
    )
    research_release_candidate_readiness_summary.add_argument("report_id", help="Report ID.")
    research_release_candidate_readiness_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_readiness_doctor = research_sub.add_parser(
        "release-candidate-readiness-doctor", help="Doctor a release candidate readiness report."
    )
    research_release_candidate_readiness_doctor.add_argument("report_id", help="Report ID.")
    research_release_candidate_readiness_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_cutover = research_sub.add_parser(
        "release-candidate-cutover-dry-run",
        help="Create a local release candidate cutover dry-run report.",
    )
    research_release_candidate_cutover.add_argument("--target-version", required=True, help="Target RC tag, for example v0.5.7-rc1.")
    research_release_candidate_cutover.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_cutover_list = research_sub.add_parser(
        "release-candidate-cutover-dry-run-list",
        help="List release candidate cutover dry-run reports.",
    )
    research_release_candidate_cutover_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_cutover_validate = research_sub.add_parser(
        "release-candidate-cutover-dry-run-validate",
        help="Validate a release candidate cutover dry-run report.",
    )
    research_release_candidate_cutover_validate.add_argument("report_id", help="Dry-run report ID.")
    research_release_candidate_cutover_validate.add_argument("--strict", action="store_true", help="Exit non-zero for invalid reports.")
    research_release_candidate_cutover_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_cutover_summary = research_sub.add_parser(
        "release-candidate-cutover-dry-run-summary",
        help="Summarize a release candidate cutover dry-run report.",
    )
    research_release_candidate_cutover_summary.add_argument("report_id", help="Dry-run report ID.")
    research_release_candidate_cutover_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_release_candidate_cutover_doctor = research_sub.add_parser(
        "release-candidate-cutover-dry-run-doctor",
        help="Doctor a release candidate cutover dry-run report.",
    )
    research_release_candidate_cutover_doctor.add_argument("report_id", help="Dry-run report ID.")
    research_release_candidate_cutover_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_mock_response_final_safety_seal = research_sub.add_parser(
        "mock-response-final-safety-seal",
        help="Create/show/list/validate/replay mock response final safety seals. Configless.",
        description="Compatibility command for mock response final safety seal create/show/list/validate/replay. Configless and non-authorizing.",
    )
    research_mock_response_final_safety_seal.add_argument("mock_response_final_safety_seal_args", nargs="*", help="Action and optional artifact ID.")
    research_mock_response_final_safety_seal.add_argument("--symbol", default=None, help="Filter list by symbol.")
    research_mock_response_final_safety_seal.add_argument("--limit", type=int, default=20, help="Limit list results. Default 20, max 100.")
    research_mock_response_final_safety_seal.add_argument("--strict", action="store_true", help="Exit non-zero for failed validate/replay.")
    research_mock_response_final_safety_seal.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")


    research_simulate = research_sub.add_parser(
        "simulate-provider",
        help="Simulate a deterministic provider response from a prompt packet. Local-only. Does not call LLMs or network.",
        description="Simulate a deterministic provider response from an existing prompt packet artifact. Local-only. Does not call LLMs, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_simulate.add_argument("prompt_packet_id", help="Source prompt packet ID.")
    research_simulate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_simulate.add_argument(
        "--provider",
        default="deterministic-mock",
        help="Simulation provider. Only 'deterministic-mock' is supported. Default: deterministic-mock.",
    )

    research_review = research_sub.add_parser(
        "review-response",
        help="Review a provider response artifact deterministically. Local-only. Does not call LLMs or network.",
        description="Review an existing provider response artifact with deterministic local checks. Local-only. Does not call LLMs, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_review.add_argument("provider_response_id", help="Source provider response ID.")
    research_review.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_dossier = research_sub.add_parser(
        "dossier",
        help="Build a deterministic dossier consolidating a research chain. Local-only. Does not call LLMs or network.",
        description="Build a local deterministic dossier that consolidates the paper-only research chain into one bounded, safe summary artifact. Local-only. Does not call LLMs, read API keys, perform network requests, submit orders, create approvals, or authorize live trading.",
    )
    research_dossier.add_argument("run_id", help="Source research run ID.")
    research_dossier.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    notify = subparsers.add_parser("notify")
    notify_sub = notify.add_subparsers(dest="notify_command")
    notify_clickup = notify_sub.add_parser("clickup")
    notify_clickup.add_argument("--file", type=Path, required=True)

    notifications = subparsers.add_parser("notifications")
    notifications_sub = notifications.add_subparsers(dest="notifications_command")
    notifications_test = notifications_sub.add_parser("test")
    notifications_test.add_argument("--transport", choices=("disabled", "dry_run", "slack"), default="dry_run")
    notifications_test.add_argument("--severity", choices=("info", "warning", "error", "critical"), default="info")
    notifications_test.add_argument("--message", default="Test notification from Atlas Agent")
    notifications_test.add_argument("--title", default="Test Notification")
    notifications_test.add_argument("--dry-run", action="store_true", default=True, help="Force dry-run mode (default)")
    notifications_send = notifications_sub.add_parser("send")
    notifications_send.add_argument("--transport", choices=("disabled", "dry_run", "slack"), default="dry_run")
    notifications_send.add_argument("--severity", choices=("info", "warning", "error", "critical"), default="info")
    notifications_send.add_argument("--message", required=True)
    notifications_send.add_argument("--title", default="")
    notifications_send.add_argument("--source", default="cli")
    notifications_send.add_argument("--dry-run", action="store_true", default=True, help="Force dry-run mode (default)")

    git_sync = subparsers.add_parser("git-sync")
    git_sub = git_sync.add_subparsers(dest="git_command")
    git_commit = git_sub.add_parser("commit")
    git_commit.add_argument("--message", required=True)
    git_sub.add_parser("push")

    schedule = subparsers.add_parser("schedule")
    schedule_sub = schedule.add_subparsers(dest="schedule_command")
    schedule_github = schedule_sub.add_parser("github-actions")
    schedule_github.add_argument("--template", default=DEFAULT_TEMPLATE)

    events = subparsers.add_parser("events")
    events_sub = events.add_subparsers(dest="events_command")
    events_list = events_sub.add_parser("list")
    events_list.add_argument("--json", action="store_true")
    events_list.add_argument("--limit", type=int, default=30)
    events_tail = events_sub.add_parser("tail")
    events_tail.add_argument("--limit", type=int, default=20)
    events_sub.add_parser("doctor")

    replay = subparsers.add_parser("replay")
    replay.add_argument("target", nargs="?", default=None)
    replay.add_argument("--last", action="store_true")

    demo = subparsers.add_parser("demo")
    demo_sub = demo.add_subparsers(dest="demo_command")
    demo_seed = demo_sub.add_parser("seed")
    demo_seed.add_argument("--force", action="store_true")

    audit = subparsers.add_parser("audit")
    audit_sub = audit.add_subparsers(dest="audit_command")
    audit_verify = audit_sub.add_parser("verify")
    audit_verify.add_argument("--path", help="Path to audit log file")
    audit_verify.add_argument("--manifest", help="Path to audit manifest file")
    audit_verify.add_argument("--all", action="store_true", help="Verify all manifests")

    dashboard = subparsers.add_parser("dashboard")
    dashboard.add_argument("--json", action="store_true", help="Emit dashboard snapshot as JSON")
    dashboard.add_argument("--format", choices=("markdown", "html"), default="html", help="Output format (default: html)")
    dashboard.add_argument("--open", action="store_true", help="Open dashboard in browser")

    reflection = subparsers.add_parser(
        "reflection",
        help="Local reflection artifacts. Offline, provider-disabled by default.",
    )
    reflection_sub = reflection.add_subparsers(dest="reflection_command")
    reflection_create = reflection_sub.add_parser(
        "create",
        help="Create a reflection artifact from a local input file.",
    )
    reflection_create.add_argument("--input", required=True, type=Path, help="Path to input artifact")
    reflection_create.add_argument("--kind", choices=("report", "backtest", "research", "audit", "note"), default=None, help="Input kind")
    reflection_create.add_argument("--dry-run", action="store_true", default=True, help="Use static fallback (default)")
    reflection_create.add_argument("--output", default="stdout", help="Output path or 'stdout'")
    reflection_create.add_argument("--json", action="store_true", help="Emit as JSON envelope")

    reflection_list = reflection_sub.add_parser("list", help="List reflection artifacts")
    reflection_list.add_argument("--status", choices=("draft", "pending_review", "approved", "rejected", "archived"), default=None, help="Filter by status")
    reflection_list.add_argument("--json", action="store_true", help="Emit as JSON")

    reflection_show = reflection_sub.add_parser("show", help="Show a reflection artifact")
    reflection_show.add_argument("reflection_id", help="Reflection ID")
    reflection_show.add_argument("--json", action="store_true", help="Emit as JSON")

    reflection_submit = reflection_sub.add_parser("submit", help="Submit a draft reflection for review")
    reflection_submit.add_argument("reflection_id", help="Reflection ID")

    reflection_approve = reflection_sub.add_parser("approve", help="Approve a pending reflection")
    reflection_approve.add_argument("reflection_id", help="Reflection ID")
    reflection_approve.add_argument("--reason", default="", help="Approval reason")

    reflection_reject = reflection_sub.add_parser("reject", help="Reject a pending reflection")
    reflection_reject.add_argument("reflection_id", help="Reflection ID")
    reflection_reject.add_argument("--reason", required=True, help="Rejection reason")

    reflection_archive = reflection_sub.add_parser("archive", help="Archive an approved or rejected reflection")
    reflection_archive.add_argument("reflection_id", help="Reflection ID")
    reflection_archive.add_argument("--reason", default="", help="Archive reason")

    return parser


# ==============================================================================
# AGENT EXECUTION (run-once)
# ==============================================================================
#
# The single-cycle agent entry point: load context, ask the model, risk-check the
# decision, route the order. `mode` selects paper or live, and it is the only lever
# that changes which broker the OrderRouter is handed — every gate below applies
# identically in both.

def run_once(
    mode: str,
    config: AtlasConfig | None = None,
    event_logger: EventLogger | None = None,
    run_id: str | None = None,
    command: str = "atlas run-once",
    symbol: str | None = None,
) -> OrderResult:
    from atlas_agent.ai.discipline import (
        DisciplineNotConfiguredError,
        InvalidDisciplineProfileError,
        require_user_discipline,
    )

    config = config or AtlasConfig.from_env()
    # Discipline gate: run_once is agentic and requires an explicit user discipline profile.
    workspace = config.memory_dir.parent
    try:
        require_user_discipline(workspace)
    except (DisciplineNotConfiguredError, InvalidDisciplineProfileError) as exc:
        return OrderResult(False, False, "discipline_gate", "error", str(exc))
    config = _effective_config_with_runtime_kill_switch(config)
    config.ensure_dirs()
    effective_symbol = symbol or config.market.symbol or config.backtest.default_symbol
    if not effective_symbol:
        return OrderResult(
            False, False, "missing_symbol", "error",
            "No trading symbol configured. Set one with `atlas config set market.symbol <SYMBOL>` or pass `--symbol <SYMBOL>`.",
        )
    ensure_sample_data(config.data_path)
    bars = CSVMarketDataProvider(config.data_path).load_bars(effective_symbol)
    decision = MovingAverageStrategy().decide(bars)
    latest = bars[-1]
    if event_logger is not None and run_id is not None:
        event_logger.write(
            "decision_proposed",
            run_id=run_id,
            command=command,
            mode=mode,
            payload={
                "symbol": decision.symbol,
                "confidence": decision.confidence,
                "action": decision.proposed_order.side if decision.proposed_order else "hold",
            },
        )
    if decision.proposed_order is None:
        return OrderResult(False, False, "none", "held", "strategy proposed hold")

    budget = min(config.max_order_notional, config.max_position_size)
    quantity = budget / latest.close
    order = Order(
        symbol=decision.symbol,
        side=decision.proposed_order.side,
        quantity=quantity,
        order_type=decision.proposed_order.order_type,
        limit_price=latest.close,
        confidence=decision.confidence,
        stop_loss=latest.close * 0.95 if mode == "live" else None,
        source="strategy",
    )
    audit = AuditLogger(config.audit_dir)

    # Live analysis-only path: sync real portfolio, evaluate risk, no submit
    if mode == "live":
        return _run_once_live_analysis(
            order=order,
            config=config,
            audit=audit,
            event_logger=event_logger,
            run_id=run_id,
            command=command,
            market_price=latest.close,
        )

    portfolio = PortfolioState(cash=config.starting_cash)
    try:
        broker = _broker_for_mode(mode, config, portfolio, audit)
    except BrokerConfigurationError as exc:
        return OrderResult(
            accepted=False,
            filled=False,
            order_id=order.id,
            status="rejected",
            message=str(exc),
            reasons=("broker_configuration_error",),
        )
    router = OrderRouter(
        config=config,
        risk_manager=RiskManager.from_config(config, audit),
        approval_manager=ApprovalManager(config.pending_orders_dir),
        audit=audit,
    )
    audit.write("ai_decision", {"decision": decision, "order_id": order.id})
    return router.route(
        order,
        mode=mode,
        broker=broker,
        portfolio=portfolio,
        market_price=latest.close,
        event_logger=event_logger,
        run_id=run_id,
        command=command,
    )


# ==============================================================================
# BROKER SELECTION
# ==============================================================================

def _broker_for_mode(
    mode: str,
    config: AtlasConfig,
    portfolio: PortfolioState,
    audit: AuditLogger,
):
    from atlas_agent.brokers.resolver import BrokerResolver

    resolver = BrokerResolver(config)
    resolution = resolver.resolve_execution_broker(mode)

    # Live mode RAISES when the resolved broker may not submit, rather than silently
    # falling back to paper. A user who asked for live and got a simulated fill —
    # believing it was real — is the worst outcome this whole system can produce.
    if mode == "live" and not resolution.status.can_submit:
        raise BrokerConfigurationError(resolution.status.message)

    if mode == "paper":
        return PaperBroker(
            portfolio,
            audit=audit,
            journal=TradeJournal(config.memory_dir / "trade_journal.md"),
        )

    if resolution.execution_broker is not None:
        return resolution.execution_broker

    raise BrokerConfigurationError(f"no execution broker available for mode: {mode}")


def _run_once_live_analysis(
    order: Order,
    config: AtlasConfig,
    audit: AuditLogger,
    event_logger: EventLogger | None,
    run_id: str | None,
    command: str,
    market_price: float,
) -> OrderResult:
    """Live analysis-only path: sync real portfolio, evaluate risk, never submit."""
    from atlas_agent.brokers.live_sync_validation import validate_live_sync
    from atlas_agent.brokers.resolver import BrokerResolver
    from atlas_agent.brokers.sync import BrokerSyncService
    from atlas_agent.risk.limits import RiskLimits
    from atlas_agent.risk.manager import RiskManager
    from atlas_agent.risk.models import OrderRiskInput

    # 1. Live opt-in gate
    if not config.enable_live_trading:
        audit.write("run_once_live_disabled", {"order_id": order.id, "mode": "live"})
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "run_once_live_disabled",
                run_id=run_id,
                command=command,
                mode="live",
                payload={"order_id": order.id},
            )
        return OrderResult(
            accepted=False,
            filled=False,
            order_id=order.id,
            status="rejected",
            message="Live trading is not enabled. Set enable_live_trading=true to use live analysis mode.",
            reasons=("live_trading_disabled",),
        )

    resolver = BrokerResolver(config)

    # 2. Resolve broker status
    status = resolver.resolve_status("live")
    if not status.can_sync:
        audit.write("run_once_live_sync_failed", {"order_id": order.id, "mode": "live", "reason": "can_sync_false"})
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "run_once_live_sync_failed",
                run_id=run_id,
                command=command,
                mode="live",
                payload={"order_id": order.id, "reason": "can_sync_false"},
            )
        return OrderResult(
            accepted=False,
            filled=False,
            order_id=order.id,
            status="rejected",
            message=status.message,
            reasons=("broker_sync_unavailable",),
        )

    # 3. Resolve sync provider
    resolution = resolver.resolve_sync_provider("live")
    if resolution.sync_provider is None:
        audit.write("run_once_live_sync_failed", {"order_id": order.id, "mode": "live", "reason": "no_sync_provider"})
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "run_once_live_sync_failed",
                run_id=run_id,
                command=command,
                mode="live",
                payload={"order_id": order.id, "reason": "no_sync_provider"},
            )
        return OrderResult(
            accepted=False,
            filled=False,
            order_id=order.id,
            status="rejected",
            message=resolution.status.message,
            reasons=("broker_sync_unavailable",),
        )

    audit.write("run_once_live_sync_started", {"order_id": order.id, "mode": "live", "broker_id": status.broker_id})
    if event_logger is not None and run_id is not None:
        event_logger.write(
            "run_once_live_sync_started",
            run_id=run_id,
            command=command,
            mode="live",
            payload={"order_id": order.id, "broker_id": status.broker_id},
        )

    # 4. Sync
    sync_service = BrokerSyncService(
        broker=resolution.sync_provider,
        audit_writer=None,
        run_id=run_id or "unknown",
    )
    sync_result = sync_service.sync()

    # 5. Validate sync result
    sync_warnings, sync_error = validate_live_sync(sync_result, resolution.status)
    if sync_error is not None:
        failed_operations = sync_error["diagnostics"].get("failed_operations", [])
        audit.write(
            "run_once_live_sync_failed",
            {"order_id": order.id, "mode": "live", "failed_operations": failed_operations},
        )
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "run_once_live_sync_failed",
                run_id=run_id,
                command=command,
                mode="live",
                payload={"order_id": order.id, "failed_operations": failed_operations},
            )
        return OrderResult(
            accepted=False,
            filled=False,
            order_id=order.id,
            status="rejected",
            message=sync_error["errors"][0],
            reasons=tuple(str(op) for op in failed_operations),
        )

    # 6. Build PortfolioSnapshot
    portfolio_snapshot = sync_service.get_portfolio_snapshot(
        sync_result, broker_id=resolution.status.broker_id
    )

    # 7. Build OrderRiskInput
    effective_price = order.limit_price if order.limit_price is not None else market_price
    risk_input = OrderRiskInput(
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        price=effective_price,
        notional=order.quantity * effective_price,
        leverage=getattr(order, "leverage", 1.0),
        confidence=order.confidence,
        stop_loss=order.stop_loss,
    )

    # 8. Evaluate risk
    risk_limits = RiskLimits(
        max_position_notional=config.max_position_size,
        max_single_trade_notional=config.max_order_notional,
        allowed_symbols=config.symbol_allowlist,
        blocked_symbols=config.symbol_blocklist or set(),
        live_trading_enabled=config.enable_live_trading,
        paper_only=not config.enable_live_trading,
        require_stop_loss_live=config.require_stop_loss_live,
    )
    risk_manager = RiskManager(
        limits=risk_limits,
        audit_writer=None,
        run_id=run_id or "unknown",
    )
    decision = risk_manager.evaluate_order(risk_input, portfolio_snapshot, mode="live")

    audit.write(
        "run_once_live_risk_evaluated",
        {
            "order_id": order.id,
            "mode": "live",
            "allowed": decision.allowed,
            "violations_count": len(decision.violations),
            "classification": decision.classification,
        },
    )
    if event_logger is not None and run_id is not None:
        event_logger.write(
            "run_once_live_risk_evaluated",
            run_id=run_id,
            command=command,
            mode="live",
            payload={
                "order_id": order.id,
                "allowed": decision.allowed,
                "violations_count": len(decision.violations),
                "classification": decision.classification,
            },
        )

    if not decision.allowed:
        audit.write(
            "run_once_live_rejected",
            {
                "order_id": order.id,
                "mode": "live",
                "reasons": [v.rule for v in decision.violations],
            },
        )
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "run_once_live_rejected",
                run_id=run_id,
                command=command,
                mode="live",
                payload={
                    "order_id": order.id,
                    "reasons": [v.rule for v in decision.violations],
                },
            )
        return OrderResult(
            accepted=False,
            filled=False,
            order_id=order.id,
            status="rejected",
            message="risk manager rejected order",
            reasons=tuple(v.rule for v in decision.violations),
        )

    # 9. Analysis-only success
    warning_reasons: list[str] = []
    message = "Risk check passed. Live order submission is deferred."
    if sync_warnings:
        warning_names = [w["operation"] for w in sync_warnings]
        message += f" Sync warning(s): {', '.join(warning_names)}."
        warning_reasons = [f"{w['operation']}_warning" for w in sync_warnings]

    reasons: tuple[str, ...] = ("live_submit_deferred",)
    if warning_reasons:
        reasons = ("live_submit_deferred",) + tuple(warning_reasons)

    audit.write(
        "run_once_live_analysis_only",
        {"order_id": order.id, "mode": "live", "message": message},
    )
    if event_logger is not None and run_id is not None:
        event_logger.write(
            "run_once_live_analysis_only",
            run_id=run_id,
            command=command,
            mode="live",
            payload={"order_id": order.id, "message": message},
        )

    return OrderResult(
        accepted=False,
        filled=False,
        order_id=order.id,
        status="live_analysis_only",
        message=message,
        reasons=reasons,
    )


# ==============================================================================
# KILL SWITCH SECOND FACTOR
# ==============================================================================

def _requires_kill_switch_totp(
    *,
    state_mode: str,
    explicit_2fa: bool,
) -> bool:
    """Does this kill-switch operation need a TOTP code?"""
    # `flatten` is the only mode that TRADES — it sells to close positions. Cancelling
    # or pausing merely stops the agent, which is always safe; liquidating a book is
    # not, so it is the one that demands a second factor by default.
    if explicit_2fa:
        return True
    return state_mode == "flatten"


def _verify_totp_for_kill_switch(code: str | None) -> tuple[bool, str]:
    secret = os.getenv("ATLAS_TOTP_SECRET", "").strip()
    if not secret:
        return False, "2FA secret missing: set ATLAS_TOTP_SECRET"
    effective_code = code
    if effective_code is None:
        try:
            effective_code = input("Enter TOTP code: ").strip()
        except EOFError:
            effective_code = ""
    if not verify_totp(secret, effective_code):
        return False, "invalid TOTP code"
    return True, ""


def _heartbeat_path_for_config(config: AtlasConfig) -> Path:
    return deadman_heartbeat_path(config.memory_dir)


def _emit_config_error(exc: Exception | None) -> int:
    print("Configuration error. Check your config and try again.", file=sys.stderr)
    return 1


def _readiness_passed(report: Any) -> bool:
    checks = getattr(report, "checks", []) or []
    return all(getattr(check, "status", None) != "fail" for check in checks)


# ==============================================================================
# PRE-FLIGHT GUARDS
# ==============================================================================

def _check_discipline_or_exit(config: AtlasConfig) -> None:
    """Exit with an error if the user discipline profile is missing or invalid."""
    # sys.exit, not a return value. Every agentic command must be unable to proceed
    # without a validated discipline profile, and a guard that a caller could forget
    # to check would be no guard at all.
    from atlas_agent.ai.discipline import (
        DisciplineNotConfiguredError,
        InvalidDisciplineProfileError,
        require_user_discipline,
    )

    workspace = config.memory_dir.parent
    try:
        require_user_discipline(workspace)
    except (DisciplineNotConfiguredError, InvalidDisciplineProfileError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)


def _resolve_symbol(config: AtlasConfig, args_symbol: str | None = None) -> str:
    """Resolve trading symbol from CLI arg, config market.symbol, or backtest.default_symbol."""
    symbol = args_symbol or config.market.symbol or config.backtest.default_symbol
    if not symbol:
        print(
            "No trading symbol configured. Set one with `atlas config set market.symbol <SYMBOL>` "
            "or pass `--symbol <SYMBOL>`.",
            file=sys.stderr,
        )
        sys.exit(2)
    return symbol


def _portfolio_payload(config: AtlasConfig) -> dict[str, Any]:
    workspace = config.memory_dir.parent
    return {
        "workspace": str(workspace),
        "trading_mode": config.trading_mode,
        "live_enabled": config.enable_live_trading,
        "broker": config.live_broker if config.trading_mode == "live" else "paper",
        "pending_orders": len(list(config.pending_orders_dir.glob("*.json"))),
        "files": {
            "portfolio": str(config.memory_dir / "portfolio.md"),
            "open_positions": str(config.memory_dir / "open_positions.md"),
            "trade_journal": str(config.memory_dir / "trade_journal.md"),
        },
    }


def config_has_workspace_context(config: AtlasConfig) -> bool:
    workspace_paths = (
        config.memory_dir,
        config.reports_dir,
        config.events_dir,
        config.pending_orders_dir,
        config.audit_dir,
    )
    if any(path.is_absolute() for path in workspace_paths):
        return True
    if is_workspace(Path.cwd()):
        return True
    existing = sum(path.exists() for path in workspace_paths)
    return existing >= 2


def _command_requires_workspace(args: argparse.Namespace) -> bool:
    if args.command is None:
        return False
    if args.command in {"init", "workspace", "models", "validate", "doctor", "deploy", "configure", "setup", "discipline"}:
        return False
    if args.command == "providers" and args.providers_command in (
        "list",
        "preflight",
        "validate-preflight",
        "bundle-preflight",
        "verify-preflight-bundle",
        "smoke-preflight-chain",
        "audit-pack",
        "capability-inventory",
        "readiness-check",
        "evidence-index",
    ):
        return False
    if args.command == "broker" and args.brokers_command == "list":
        return False
    if args.command == "telegram" and args.telegram_command == "test":
        return False
    return True


def _run_provider_bundle_preflight(args: argparse.Namespace) -> int:
    from atlas_agent.providers.provider_preflight import (
        PreflightValidationError,
        create_preflight_evidence_bundle,
    )

    command = "atlas providers bundle-preflight"
    try:
        result = create_preflight_evidence_bundle(
            artifact_path=Path(args.artifact_path),
            output_dir=args.output_dir,
        )
    except FileNotFoundError:
        message = f"File not found: {args.artifact_path}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="file_not_found", message=message)
        print(message, file=sys.stderr)
        return 2
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        message = f"Invalid JSON: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="json_parse_error", message=message)
        print(message, file=sys.stderr)
        return 2
    except PreflightValidationError as exc:
        message = f"Validation failed: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(
                command,
                code="preflight_validation_error",
                message=message,
            )
        print(message, file=sys.stderr)
        return 1
    except OSError as exc:
        message = f"Unable to create evidence bundle: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="bundle_write_error", message=message)
        print(message, file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        return emit_cli_success(command, result)

    print(f"Provider preflight evidence bundle created at {display_path(Path(result['bundle_dir']))}")
    return 0


def _run_provider_verify_preflight_bundle(args: argparse.Namespace) -> int:
    from atlas_agent.providers.provider_preflight import (
        PreflightBundleVerificationError,
        verify_preflight_evidence_bundle,
    )

    command = "atlas providers verify-preflight-bundle"
    try:
        result = verify_preflight_evidence_bundle(Path(args.bundle_dir))
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        message = f"Unable to read bundle: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="bundle_input_error", message=message)
        print(f"Provider preflight evidence bundle verification failed: {message}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        message = f"Malformed JSON: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="json_parse_error", message=message)
        print(f"Provider preflight evidence bundle verification failed: {message}", file=sys.stderr)
        return 2
    except PreflightBundleVerificationError as exc:
        message = str(exc)
        if getattr(args, "json", False):
            emit_json(error_envelope(command, code="bundle_verification_failed", message=message))
            return 1
        print(f"Provider preflight evidence bundle verification failed: {message}", file=sys.stderr)
        return 1
    except OSError as exc:
        message = f"Unable to read bundle: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="bundle_input_error", message=message)
        print(f"Provider preflight evidence bundle verification failed: {message}", file=sys.stderr)
        return 2

    if getattr(args, "json", False):
        return emit_cli_success(command, result)

    print("Provider preflight evidence bundle is valid.")
    return 0


def _run_provider_smoke_preflight_chain(args: argparse.Namespace) -> int:
    from atlas_agent.providers.provider_preflight import (
        PreflightSmokeChainError,
        PreflightValidationError,
        run_preflight_smoke_chain,
    )

    command = "atlas providers smoke-preflight-chain"
    try:
        result = run_preflight_smoke_chain(
            provider_id=args.provider,
            model_id=args.model,
            purpose=args.purpose,
            max_context_chars=args.max_context_chars,
            output_dir=args.output_dir,
        )
    except PreflightValidationError as exc:
        message = f"Provider preflight smoke chain failed: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(
                command,
                code="preflight_smoke_input_error",
                message=message,
            )
        print(message, file=sys.stderr)
        return 2
    except PreflightSmokeChainError as exc:
        message = f"Provider preflight smoke chain failed: {exc}"
        if getattr(args, "json", False):
            emit_json(
                error_envelope(
                    command,
                    code="preflight_smoke_chain_failed",
                    message=message,
                )
            )
            return 1
        print(message, file=sys.stderr)
        return 1
    except OSError as exc:
        message = f"Provider preflight smoke chain failed: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(
                command,
                code="preflight_smoke_output_error",
                message=message,
            )
        print(message, file=sys.stderr)
        return 2

    data = {
        "valid": result["valid"],
        "output_dir": result["output_dir"],
        "stages": result["stages"],
    }
    if getattr(args, "json", False):
        return emit_cli_success(command, data)

    print(
        "Provider preflight smoke chain completed successfully at "
        f"{display_path(Path(result['output_dir']))}"
    )
    return 0



def _run_provider_verify_audit_pack(args: argparse.Namespace) -> int:
    from atlas_agent.providers.provider_audit_pack import (
        AuditPackVerificationError,
        ProviderAuditPackIOError,
        verify_provider_audit_pack,
    )

    command = "atlas providers verify-audit-pack"
    try:
        result = verify_provider_audit_pack(args.pack_dir)
    except ProviderAuditPackIOError as exc:
        message = f"Provider audit pack verification failed: {exc}"
        if getattr(args, "json", False):
            emit_json({"valid": False, "accepted_for_external_review": False, "findings": [message]})
            return 2
        print(message, file=sys.stderr)
        return 2
    except AuditPackVerificationError as exc:
        message = f"Provider audit pack verification failed: {exc}"
        if getattr(args, "json", False):
            emit_json({"valid": False, "accepted_for_external_review": False, "findings": [message]})
            return 1
        print(message, file=sys.stderr)
        return 1
    except Exception as exc:
        message = f"Provider audit pack verification failed: {exc}"
        if getattr(args, "json", False):
            emit_json({"valid": False, "accepted_for_external_review": False, "findings": [message]})
            return 2
        print(message, file=sys.stderr)
        return 2

    if not result.get("valid") or not result.get("accepted_for_external_review"):
        if getattr(args, "json", False):
            emit_json(result)
            return 1

        findings = result.get("findings", [])
        if findings:
            reason = findings[0]
        else:
            reason = "validation failed"
        print(f"Provider audit pack verification failed: {reason}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        emit_json(result)
        return 0

    print("Provider audit pack is valid and accepted for external review.")
    return 0


def _run_provider_audit_pack(args: argparse.Namespace) -> int:
    from atlas_agent.providers.provider_audit_pack import (
        ProviderAuditPackIOError,
        ProviderAuditPackInputError,
        ProviderAuditPackStageError,
        create_provider_audit_pack,
    )

    command = "atlas providers audit-pack"
    try:
        result = create_provider_audit_pack(
            provider_id=args.provider,
            model_id=args.model,
            purpose=args.purpose,
            max_context_chars=args.max_context_chars,
            output_dir=args.output_dir,
        )
    except ProviderAuditPackInputError as exc:
        message = f"Provider audit pack creation failed: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="audit_pack_input_error", message=message)
        print(message, file=sys.stderr)
        return 2
    except ProviderAuditPackStageError as exc:
        message = f"Provider audit pack creation failed: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="audit_pack_stage_error", message=message)
        print(message, file=sys.stderr)
        return 1
    except ProviderAuditPackIOError as exc:
        message = f"Provider audit pack creation failed: {exc}"
        if getattr(args, "json", False):
            return emit_cli_error(command, code="audit_pack_output_error", message=message)
        print(message, file=sys.stderr)
        return 2

    data = {
        "valid": result["valid"],
        "output_dir": result["output_dir"],
        "files": result["files"],
        "stages": result["stages"],
    }
    if getattr(args, "json", False):
        return emit_cli_success(command, data)

    print(f"Provider audit pack created at {display_path(Path(result['output_dir']))}")
    return 0


def _load_config_for_command(
    args: argparse.Namespace,
    *,
    require_workspace: bool,
) -> tuple[AtlasConfig | None, WorkspaceResolution, str | None]:
    resolution = resolve_workspace(getattr(args, "workspace", None))
    if resolution.path is not None:
        os.chdir(resolution.path)
    try:
        config = AtlasConfig.from_env()
    except AtlasConfigError as exc:
        return None, resolution, f"Configuration error: {exc}"
    except ValueError as exc:
        return None, resolution, f"Configuration error: {exc}"

    if not require_workspace:
        return config, resolution, None
    if resolution.path is not None:
        return config, resolution, None
    if config_has_workspace_context(config):
        return config, resolution, None
    return config, resolution, "workspace_not_configured"


def _print_workspace_setup_guidance(*, warning: str | None = None, stream=None) -> None:
    output = stream if stream is not None else sys.stdout
    if warning:
        print(f"Workspace resolution warning: {warning}", file=output)
        print("", file=output)
    print("Atlas Agent needs a workspace before it can run.", file=output)
    print("", file=output)
    print("Create one:", file=output)
    print("  atlas init my-trader --template routine-trader --set-default", file=output)
    print("  cd my-trader", file=output)
    print("  atlas setup", file=output)
    print("", file=output)
    print("Or set a default workspace:", file=output)
    print("  atlas workspace set <path>", file=output)


def _print_replay(summary) -> None:
    print("Replay")
    print(f"Source: {summary.source}")
    print(f"Run ID: {summary.run_id or 'n/a'}")
    print("")
    print("inputs/context")
    for line in summary.inputs_context or ["- none"]:
        print(f"- {line}")
    print("market state")
    for line in summary.market_state or ["- none"]:
        print(f"- {line}")
    print("decision")
    for line in summary.decision or ["- none"]:
        print(f"- {line}")
    print("risk outcome")
    for line in summary.risk_outcome or ["- none"]:
        print(f"- {line}")
    print("order outcome")
    for line in summary.order_outcome or ["- none"]:
        print(f"- {line}")
    print("memory/report artifacts")
    for line in summary.artifacts or ["- none"]:
        print(f"- {line}")
    print("errors/warnings")
    for line in summary.warnings or ["- none"]:
        print(f"- {line}")




def _check_for_updates() -> str | None:
    """Check for updates on GitHub. Returns version string if update is available."""
    url = "https://raw.githubusercontent.com/usernotfinded/atlas-agent/main/src/atlas_agent/__init__.py"
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            content = response.read().decode("utf-8")
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                remote_version = match.group(1)
                if remote_version != __version__:
                    return remote_version
    except Exception:
        # Fail silently to avoid blocking startup or showing errors if offline
        pass
    return None


from atlas_agent.ui.banner import ATLAS_ASCII_BANNER, ATLAS_TAGLINE

def _print_welcome() -> None:
    print(ATLAS_ASCII_BANNER)
    print(ATLAS_TAGLINE)
    print("")
    update = _check_for_updates()

    if update:
        print(f"NOTICE: A newer version of Atlas Agent is available: {update} (current: {__version__})")
        print(f"Run: {YELLOW}atlas update{RESET}")
        print("")


def _has_non_empty_file(path: Path) -> bool:
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _provider_configured(workspace_path: Path | None) -> bool:
    provider_env_keys = (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
    )
    if any(bool(os.getenv(key, "").strip()) for key in provider_env_keys):
        return True
    if workspace_path is None:
        return False
    return any(
        _has_non_empty_file(workspace_path / rel)
        for rel in ("configs/providers.yaml", "configs/providers.json")
    )


def _display_live_status(config: AtlasConfig | None) -> tuple[bool, bool, str]:
    """Read-only, side-effect-free live broker status for CLI display.

    Returns (credentials_configured, can_submit, message).  No broker or
    kill-switch controller is instantiated, so no directories are created
    and no state files are written merely to print status.
    """
    if config is None:
        return False, False, "live broker is not configured"

    broker_id = config.live_broker
    if broker_id in {"", "none"}:
        return False, False, "live broker is not configured"

    known_brokers = {"alpaca", "binance", "ccxt", "ibkr_stub"}
    if broker_id not in known_brokers:
        return False, False, "live broker is not supported"

    # Credentials presence check only; values are never loaded or decrypted.
    if broker_id == "alpaca":
        creds_ok = bool(os.getenv("ALPACA_API_KEY")) and bool(os.getenv("ALPACA_SECRET_KEY"))
    elif broker_id == "binance":
        creds_ok = bool(os.getenv("BINANCE_API_KEY")) or bool(os.getenv("BINANCE_TESTNET_API_KEY"))
    elif broker_id == "ccxt":
        creds_ok = bool(os.getenv("CCXT_API_KEY")) or bool(os.getenv("EXCHANGE_API_KEY"))
    else:  # ibkr_stub
        creds_ok = True

    if not creds_ok:
        return False, False, "live broker credentials are missing"

    # Config-flag gates (read-only).
    if not config.broker.enable_live_submit:
        return creds_ok, False, "broker.enable_live_submit is false"
    if not config.broker.enable_live_trading:
        return creds_ok, False, "broker.enable_live_trading is false"
    if config.trading_mode != "live":
        return creds_ok, False, f"trading_mode is {config.trading_mode}"
    if config.safety.order_approval_mode == "disabled_live":
        return creds_ok, False, "order_approval_mode disables live trading"
    if config.risk.allow_leverage:
        return creds_ok, False, "allow_leverage is true"

    # Read kill-switch state directly without instantiating KillSwitchController.
    ks_path = Path(config.memory_dir) / "kill_switch_state.json"
    ks_enabled_flag = Path(config.memory_dir) / "kill_switch.enabled"
    ks_enabled = False
    ks_mode = "soft"
    if ks_path.exists():
        try:
            raw = json.loads(ks_path.read_text(encoding="utf-8"))
            ks_enabled = bool(raw.get("enabled", False))
            ks_mode = str(raw.get("mode", "soft")).strip().lower()
        except (json.JSONDecodeError, OSError, ValueError):
            return creds_ok, False, "kill switch state is unreadable"
    elif ks_enabled_flag.exists():
        ks_enabled = True
        ks_mode = "soft"

    if ks_enabled and ks_mode != "normal":
        return creds_ok, False, f"kill switch is {ks_mode}"

    # Opt-in record check (read-only file read via existing helper).
    from atlas_agent.brokers.resolver import _live_submit_opt_in_status

    opt_in = _live_submit_opt_in_status(config)
    if not opt_in.valid:
        return creds_ok, False, opt_in.message

    return creds_ok, True, "ready"


def _print_first_run_onboarding(
    *,
    config: AtlasConfig | None,
    config_error: str | None,
    resolution: WorkspaceResolution,
) -> None:
    _print_welcome()
    workspace_configured = resolution.path is not None
    provider_configured = _provider_configured(resolution.path)

    if config_error:
        broker_mode = "not configured"
    elif config is not None:
        broker_mode = config.live_broker if config.live_broker not in {"", "none"} else "paper"
    else:
        broker_mode = "not configured"

    live_creds, can_submit, live_message = _display_live_status(config)

    if not workspace_configured:
        effective_mode = "paper (no workspace)"
    elif config_error or config is None or broker_mode == "not configured":
        effective_mode = "not configured"
    elif broker_mode == "paper":
        effective_mode = "paper"
    else:
        effective_mode = f"{broker_mode} (live config)"

    print("Current setup status:")
    print(f"- workspace configured: {'yes' if workspace_configured else 'no'}")
    print(f"- provider configured: {'yes' if provider_configured else 'no'}")
    print(f"- broker mode: {broker_mode}")
    print(f"- live broker credentials: {'configured' if live_creds else 'not configured'}")
    print(f"- effective mode: {effective_mode}")
    if config is not None and config.enable_live_trading and not can_submit:
        print("- live trading config flag: set")
        print(f"- live submit possible: no (missing: {live_message})")
    else:
        print(f"- live submit possible: {'yes' if can_submit else 'no'}")
    if config_error:
        print(f"- config warning: {config_error}")
    if resolution.warning:
        print(f"- workspace warning: {resolution.warning}")

    print("")
    if workspace_configured:
        print("Next commands:")
        print("  atlas setup")
        print("  atlas validate")
        print("  atlas run --mode paper")
        print(f"  {YELLOW}atlas update{RESET}")
        print("")
        print("Optional:")
        print("  atlas configure")
    else:
        print("Next commands:")
        print("  atlas init <workspace>")
        print("  cd <workspace>")
        print("  atlas setup")
        print("  atlas validate")
        print("  atlas run --mode paper")
        print(f"  {YELLOW}atlas update{RESET}")
    print("")
    print("Bare `atlas` no longer starts autonomous execution. Use `atlas run` explicitly.")


def _prompt_yes_no(question: str, *, default_no: bool = True) -> bool:
    suffix = " [y/N]: " if default_no else " [Y/n]: "
    try:
        value = input(question + suffix).strip().lower()
    except (EOFError, OSError):
        return not default_no
    if not value:
        return not default_no
    return value in {"y", "yes"}


def _ensure_workspace_for_setup(resolution: WorkspaceResolution) -> tuple[WorkspaceResolution, int | None]:
    """Ensure setup runs inside a workspace.

    Returns updated resolution and optional early return code.
    """
    if resolution.path is not None:
        return resolution, None

    from atlas_agent.setup.wizard import is_interactive

    if not is_interactive():
        _print_workspace_setup_guidance(warning=resolution.warning, stream=sys.stdout)
        return resolution, 2

    print("No Atlas workspace is currently configured for this directory.")
    if not _prompt_yes_no("Initialize the current directory as an Atlas workspace using template 'routine-trader'?"):
        print("Setup cancelled before workspace initialization.")
        return resolution, 2

    try:
        init_result = init_workspace(".", template=DEFAULT_TEMPLATE, force=False)
    except WorkspaceInitError as exc:
        print(f"Workspace initialization failed: {exc}")
        return resolution, 2

    if init_result.path is not None:
        os.chdir(init_result.path)
    print(f"Workspace ready: {init_result.path}")
    return resolve_workspace(None), None


def _configure_discipline_for_setup(workspace_root: Path) -> tuple[bool, str]:
    from atlas_agent.ai.discipline import (
        default_discipline_text,
        discipline_status,
        sanitize_discipline_text,
        validate_discipline_text,
        write_user_discipline,
    )

    status = discipline_status(workspace_root)
    if status["configured"] and status["valid"]:
        return True, "existing"

    print("Discipline profile is required for agentic workflows.")
    print("You must define the agent's discipline/personality/mental model before paper run workflows.")
    print("Options:")
    print("  1. Create a safe template now (you must review/customize it).")
    print("  2. Paste a full discipline markdown profile now.")
    print("  3. Cancel setup.")

    while True:
        try:
            choice = input("Select option [1/2/3]: ").strip()
        except (EOFError, OSError):
            return False, "cancelled"
        if choice == "1":
            template = default_discipline_text()
            write_user_discipline(workspace_root, template)
            ok, errors = validate_discipline_text(template)
            if not ok:
                print("Template discipline validation failed:")
                for err in errors:
                    print(f"- {err}")
                return False, "invalid_template"
            print("Discipline template written to .atlas/discipline.md")
            print("Review and customize this file before production usage.")
            return True, "template"
        if choice == "2":
            print("Paste discipline markdown. End input with a single line containing only `.`")
            lines: list[str] = []
            while True:
                try:
                    line = input()
                except (EOFError, OSError):
                    line = "."
                if line.strip() == ".":
                    break
                lines.append(line)
            raw_text = "\n".join(lines).strip()
            if not raw_text:
                print("Discipline text cannot be empty.")
                continue
            content = sanitize_discipline_text(raw_text)
            ok, errors = validate_discipline_text(content)
            if not ok:
                print("Discipline profile is invalid:")
                for err in errors:
                    print(f"- {err}")
                print("Please retry.")
                continue
            write_user_discipline(workspace_root, content)
            print("Discipline profile saved to .atlas/discipline.md")
            return True, "manual"
        if choice == "3":
            return False, "cancelled"
        print("Invalid selection. Choose 1, 2, or 3.")


def _configure_symbol_for_setup(config: AtlasConfig, provided_symbol: str | None = None) -> tuple[bool, str]:
    from atlas_agent.config import set_raw_value

    current_symbol = (config.market.symbol or "").strip()
    if provided_symbol:
        symbol = provided_symbol.strip().upper()
        if not symbol or symbol == "DEMO-SYMBOL":
            return False, "invalid_symbol"
        set_raw_value("market.symbol", symbol)
        return True, symbol

    if current_symbol and current_symbol != "DEMO-SYMBOL":
        if _prompt_yes_no(f"Keep current trading symbol '{current_symbol}'?", default_no=False):
            return True, current_symbol

    while True:
        try:
            symbol = input("Enter trading symbol (example: AAPL): ").strip().upper()
        except (EOFError, OSError):
            return False, "cancelled"
        if not symbol:
            print("Symbol is required.")
            continue
        if symbol == "DEMO-SYMBOL":
            print("DEMO-SYMBOL is reserved for tests/CI. Please enter a real symbol.")
            continue
        set_raw_value("market.symbol", symbol)
        return True, symbol


def _print_setup_readiness_summary(config: AtlasConfig) -> None:
    from atlas_agent.diagnostics.readiness import run_diagnostics

    report = run_diagnostics(config)
    by_id = {check.id: check for check in report.checks}

    def label(status: str) -> str:
        if status == "pass":
            return "[✓]"
        if status == "warn":
            return "[!]"
        if status == "info":
            return "[i]"
        return "[x]"

    provider_ok = by_id.get("provider.configured")
    auth_ok = by_id.get("provider.api_key")
    discipline_ok = by_id.get("discipline.configured")
    symbol_ok = by_id.get("market.symbol")
    audit_ok = by_id.get("audit.enabled")
    risk_ok = by_id.get("risk.configured")
    live_ok = by_id.get("live.disabled_by_default") or by_id.get("live.enabled")
    workspace_ok = by_id.get("workspace.initialized")

    print("\nSetup readiness summary:")
    if workspace_ok:
        print(f"{label(workspace_ok.status)} workspace: {workspace_ok.message}")
    if provider_ok:
        model_desc = f"{config.model.provider}/{config.model.model or '(missing model)'}"
        print(f"{label(provider_ok.status)} provider/model: {model_desc}")
    if auth_ok:
        print(f"{label(auth_ok.status)} auth: {auth_ok.message}")
    if discipline_ok:
        print(f"{label(discipline_ok.status)} discipline: {discipline_ok.message}")
    if symbol_ok:
        print(f"{label(symbol_ok.status)} symbol: {symbol_ok.message}")
    if audit_ok:
        print(f"{label(audit_ok.status)} audit safety: {audit_ok.message}")
    if risk_ok:
        print(f"{label(risk_ok.status)} risk gates: {risk_ok.message}")
    if live_ok:
        print(f"{label(live_ok.status)} live trading disabled: {live_ok.message}")


def _run_guided_setup(*, args: argparse.Namespace) -> int:
    from atlas_agent.setup.state import WizardState
    from atlas_agent.setup.wizard import is_interactive, run_wizard
    from atlas_agent.config import get_config, set_raw_value

    resolution = resolve_workspace(getattr(args, "workspace", None))
    resolution, early_code = _ensure_workspace_for_setup(resolution)
    if early_code is not None:
        return early_code
    if resolution.path is not None:
        os.chdir(resolution.path)

    if not is_interactive():
        print("Non-interactive mode detected. `atlas setup` requires an interactive terminal.")
        return 2

    config_path = Path(".atlas/config.json")
    state = WizardState.load(config_path)
    if not run_wizard(state):
        print("Setup cancelled.")
        return 2

    try:
        state.save(config_path)
    except ValueError as exc:
        print(f"Setup failed: {exc}")
        return 2

    workspace_root = Path(".")
    discipline_ok, discipline_reason = _configure_discipline_for_setup(workspace_root)
    if not discipline_ok:
        print(f"Setup stopped: discipline step incomplete ({discipline_reason}).")
        return 2

    config_after_wizard = get_config()
    symbol_ok, symbol_value = _configure_symbol_for_setup(config_after_wizard)
    if not symbol_ok:
        print(f"Setup stopped: symbol step incomplete ({symbol_value}).")
        return 2

    # Setup must never enable live trading by default.
    set_raw_value("trading_mode", "paper")
    set_raw_value("broker.enable_live_trading", False)

    final_config = AtlasConfig.from_env()
    _print_setup_readiness_summary(final_config)
    return 0


def _cmd_broker_opt_in(args: argparse.Namespace, config: AtlasConfig) -> int:
    """Handle `atlas broker opt-in live-submit`."""
    from atlas_agent.brokers.resolver import _compute_live_submit_fingerprint

    # --yes is not allowed for live submit opt-in; typed confirmation is mandatory.
    if getattr(args, "yes", False):
        print("ERROR: Typed broker-name confirmation is required for live submit opt-in.")
        return 2

    # Prerequisites
    if not config.broker.enable_live_submit:
        print("ERROR: broker.enable_live_submit must be true in config.")
        return 2
    if not config.broker.enable_live_trading:
        print("ERROR: broker.enable_live_trading must be true.")
        return 2
    if config.trading_mode != "live":
        print(f"ERROR: trading_mode must be 'live' (currently '{config.trading_mode}').")
        return 2

    # Kill switch check
    from atlas_agent.safety.kill_switch import KillSwitchController
    try:
        ks = KillSwitchController(
            state_path=Path(config.memory_dir) / "kill_switch_state.json",
            enabled_flag_path=Path(config.memory_dir) / "kill_switch.enabled",
        )
        ks_status = ks.status()
        if ks_status.enabled and ks_status.mode != "normal":
            print(f"ERROR: Kill switch is active (mode={ks_status.mode}).")
            return 2
    except Exception:
        print("ERROR: Kill switch state is unreadable.")
        return 2

    broker_id = config.broker.provider
    if broker_id in {"", "none"}:
        print("ERROR: No live broker configured.")
        return 2

    # Credentials check
    from atlas_agent.brokers.resolver import BrokerResolver
    resolver = BrokerResolver(config)
    if not resolver._credentials_configured(broker_id):
        print("ERROR: Live broker credentials are missing.")
        return 2

    # Confirmation prompt
    if not getattr(args, "yes", False):
        print(f"WARNING: You are about to enable live order submission for broker '{broker_id}'.")
        print("This allows the agent to place real orders with real money.")
        print("Type the broker name exactly to confirm, or press Ctrl-C to abort.")
        try:
            confirmation = input(f"Confirm [{broker_id}]: ")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 1
        if confirmation.strip() != broker_id:
            print("ERROR: Confirmation did not match. Aborted.")
            return 2

    # Write opt-in record
    opt_in_path = Path(config.audit_dir) / "live_submit_opt_in.jsonl"
    opt_in_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = _compute_live_submit_fingerprint(config)
    record = {
        "event_type": "live_submit_opt_in_enabled",
        "opt_in": True,
        "broker_id": broker_id,
        "config_fingerprint": fingerprint,
        "created_at": datetime.now(UTC).isoformat(),
        "expiry_hours": 24,
    }
    with open(opt_in_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    # Write to audit log
    try:
        from atlas_agent.audit import AuditWriter
        audit_writer = AuditWriter(config.audit_dir / "audit.log")
        audit_writer.write_event(
            "live_submit_opt_in_enabled",
            run_id="cli-opt-in",
            payload={
                "broker_id": broker_id,
                "config_fingerprint": fingerprint,
                "opt_in_path": str(opt_in_path),
            },
        )
    except Exception:
        pass  # Best-effort audit logging

    print(f"Live submit opt-in recorded for broker '{broker_id}'.")
    print(f"Config fingerprint: {fingerprint}")
    print("The opt-in expires in 24 hours.")
    return 0


def _cmd_broker_opt_out(args: argparse.Namespace, config: AtlasConfig) -> int:
    """Handle `atlas broker opt-out live-submit`."""
    opt_in_path = Path(config.audit_dir) / "live_submit_opt_in.jsonl"
    opt_in_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event_type": "live_submit_opt_in_disabled",
        "opt_in": False,
        "broker_id": config.broker.provider,
        "created_at": datetime.now(UTC).isoformat(),
    }
    with open(opt_in_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    try:
        from atlas_agent.audit import AuditWriter
        audit_writer = AuditWriter(config.audit_dir / "audit.log")
        audit_writer.write_event(
            "live_submit_opt_in_disabled",
            run_id="cli-opt-out",
            payload={"broker_id": config.broker.provider},
        )
    except Exception:
        pass

    print(f"Live submit opt-out recorded for broker '{config.broker.provider}'.")
    return 0


def _parse_strategy_parameter_overrides(raw_items: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in raw_items:
        if "=" not in item:
            raise ValueError(f"Invalid strategy parameter override: {item!r}. Use key=value.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid strategy parameter override: {item!r}. Key is required.")
        parsed[key] = value.strip()
    return parsed


def _configured_strategy_parameters(config: AtlasConfig, raw_items: list[str]) -> dict[str, object]:
    configured = dict(getattr(config.backtest, "strategy_parameters", {}) or {})
    configured.update(_parse_strategy_parameter_overrides(raw_items))
    return configured


def _latest_stateful_run_id(state_dir: str | Path) -> str | None:
    """Return the run_id from the most recent *-state.json in ``state_dir``.

    Used by ``--resume`` to continue the latest stateful paper run rather than
    starting a fresh run_id.
    """
    state_path = Path(state_dir)
    if not state_path.exists():
        return None
    state_files = sorted(
        (p for p in state_path.iterdir() if p.is_file() and p.name.endswith("-state.json")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not state_files:
        return None
    run_id = state_files[0].name[:-len("-state.json")]
    return run_id if run_id else None


def _list_backtest_runs(*, validate: bool = False) -> list[dict]:
    from pathlib import Path
    import json
    runs_dir = Path(".atlas/backtests")
    if not runs_dir.exists():
        return []
    runs = []
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        result_path = run_dir / "result.json"
        if not result_path.exists():
            continue
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            if not validate:
                continue
            from atlas_agent.backtest.report_schema import unreadable_schema_result

            validation = unreadable_schema_result(f"unreadable: {exc}")
            runs.append(
                {
                    "run_id": run_dir.name,
                    "symbol": "?",
                    "strategy": "?",
                    "status": "?",
                    "return_pct": 0.0,
                    "date": run_dir.name.replace("bt-", ""),
                    "schema_status": validation.status,
                    "schema_valid": validation.valid,
                    "schema_error": validation.error,
                    "schema_errors": validation.errors,
                    "schema_version": validation.schema_version,
                }
            )
            continue
        config = data.get("config", {})
        metrics = data.get("metrics", {})
        run = {
            "run_id": data.get("run_id", run_dir.name),
            "symbol": config.get("symbol", "?"),
            "strategy": config.get("strategy_mode", "?"),
            "status": data.get("status", "?"),
            "return_pct": metrics.get("total_return_pct", 0.0),
            "date": config.get("run_id", "").replace("bt-", ""),
        }
        if validate:
            validation = _validate_report_file(data)
            run["schema_status"] = validation.status
            run["schema_valid"] = validation.valid
            run["schema_error"] = validation.error
            run["schema_errors"] = validation.errors
            run["schema_version"] = validation.schema_version
        runs.append(run)
    return runs


def _validate_report_file(data: dict):
    from atlas_agent.backtest.report_schema import get_schema_validation_result
    return get_schema_validation_result(data)


def cmd_agent_shadow_live(args: argparse.Namespace) -> int:
    """Run the read-only shadow-live comparison CLI."""
    from atlas_agent.agent.autonomous_paper_shadow_live import (
        ShadowLiveThresholdPolicy,
        build_shadow_live_comparison,
    )

    policy = ShadowLiveThresholdPolicy(max_snapshot_age_seconds=args.max_snapshot_age_seconds)
    report = build_shadow_live_comparison(
        quality_gate_path=args.quality_gate,
        broker_snapshot_path=args.broker_snapshot,
        output_dir=args.output_dir,
        state_path=args.state,
        metrics_path=args.metrics,
        decisions_path=args.decisions,
        fills_path=args.fills,
        policy=policy,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"shadow-live: {report['status']}")
        print(f"  output dir: {args.output_dir}")
        for blocker in report.get("blockers", []):
            print(f"  blocker: {blocker}")
    return 0 if report.get("status") in ("matched", "minor_divergence") else 2


# ==============================================================================
# DISPATCH
# ==============================================================================

def main(argv: list[str] | None = None) -> int:
    import json

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits with 0 on --help/--version. Converting that back into a normal
        # return keeps `atlas --help` from looking like a crash to a caller that wraps
        # main() rather than the process.
        if exc.code == 0:
            return 0
        raise

    # Normalize research command aliases so handlers receive canonical names.
    _research_cmd = getattr(args, "research_command", None)
    if _research_cmd in RESEARCH_COMMAND_ALIAS_MAP:
        args.research_command = RESEARCH_COMMAND_ALIAS_MAP[_research_cmd]

    # --- Configless commands ---------------------------------------------------
    # These run with `config=None` BEFORE any config is loaded, because they are how a
    # user fixes a broken config in the first place. `atlas config set` must work on a
    # workspace whose config.toml does not parse — otherwise a typo would lock the user
    # out of the only command that could repair it.
    if args.command == "config":
        from atlas_agent.cli_commands.config import handle_config

        _handled = handle_config(CLIContext(args=args, config=None, resolution=None))
        if _handled is not None:
            return _handled

    if args.command == "model":
        from atlas_agent.cli_commands.model import handle_model

        _handled = handle_model(CLIContext(args=args, config=None, resolution=None))
        if _handled is not None:
            return _handled

    if args.command == "init":
        try:
            result = init_workspace(
                args.path,
                template=args.template,
                force=args.force,
            )
            if args.set_default:
                set_default_workspace(result.path)
        except WorkspaceInitError as exc:
            print(f"init refused: {exc}")
            return 2
        action = "overwritten" if result.overwritten else "created"
        print(
            f"Atlas Agent workspace {action}: "
            f"{result.path} (template: {result.template})"
        )
        if args.set_default:
            print(f"Set as default workspace: {result.path}")
        return 0

    if args.command is None:
        from atlas_agent.setup.wizard import run_wizard, is_interactive
        from atlas_agent.setup.state import WizardState

        resolution = resolve_workspace(getattr(args, "workspace", None))
        if resolution.path:
            os.chdir(resolution.path)

        config_path = Path(".atlas/config.json")
        state = WizardState.load(config_path)

        if not state.is_complete:
            if not is_interactive():
                print("Atlas provider credentials are missing. Run `atlas configure` in an interactive terminal or set the required environment variable.")
                return 2

            _print_welcome()
            print("First-time setup required.\n")
            success = run_wizard(state)
            if success:
                try:
                    state.save(config_path)
                except ValueError as exc:
                    print(f"Setup failed: {exc}")
                    return 2
                print(f"\nConfiguration saved to {config_path}")

                # Reload config and show final status
                resolution = resolve_workspace(getattr(args, "workspace", None))
                config = None
                try:
                    config = AtlasConfig.from_env()
                except ValueError:
                    pass

                print("\nSetup completed successfully.\n")
                _print_first_run_onboarding(
                    config=config,
                    config_error=None,
                    resolution=resolution,
                )
                return 0
            else:
                print("\nSetup cancelled. Atlas is not configured yet.")
                return 130

        config_error: str | None = None
        config: AtlasConfig | None = None
        try:
            config = AtlasConfig.from_env()
        except ValueError as exc:
            config_error = f"Configuration error: {exc}"
        _print_first_run_onboarding(
            config=config,
            config_error=config_error,
            resolution=resolution,
        )
        return 0

    # Configless local provider evidence command: resolve workspace only, never load credentials.
    if args.command == "providers" and getattr(args, "providers_command", None) == "bundle-preflight":
        resolution = resolve_workspace(getattr(args, "workspace", None))
        if resolution.path is not None:
            os.chdir(resolution.path)
        return _run_provider_bundle_preflight(args)
    if args.command == "providers" and getattr(args, "providers_command", None) == "verify-preflight-bundle":
        resolution = resolve_workspace(getattr(args, "workspace", None))
        if resolution.path is not None:
            os.chdir(resolution.path)
        return _run_provider_verify_preflight_bundle(args)
    if args.command == "providers" and getattr(args, "providers_command", None) == "smoke-preflight-chain":
        resolution = resolve_workspace(getattr(args, "workspace", None))
        if resolution.path is not None:
            os.chdir(resolution.path)
        return _run_provider_smoke_preflight_chain(args)
    if args.command == "providers" and getattr(args, "providers_command", None) == "audit-pack":
        resolution = resolve_workspace(getattr(args, "workspace", None))
        if resolution.path is not None:
            os.chdir(resolution.path)
        return _run_provider_audit_pack(args)
    if args.command == "providers" and getattr(args, "providers_command", None) == "verify-audit-pack":
        resolution = resolve_workspace(getattr(args, "workspace", None))
        if resolution.path is not None:
            os.chdir(resolution.path)
        return _run_provider_verify_audit_pack(args)

    # Configless local research commands: resolve workspace only, never load secrets
    _CONFIGLESS_RESEARCH_COMMANDS = CONFIGLESS_RESEARCH_COMMANDS
    if args.command == "research" and getattr(args, "research_command", None) in _CONFIGLESS_RESEARCH_COMMANDS:
        resolution = resolve_workspace(getattr(args, "workspace", None))
        if resolution.path is not None:
            os.chdir(resolution.path)
        if resolution.path is None:
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas",
                    code="workspace_not_configured",
                    message="Atlas Agent needs a workspace before it can run.",
                    details={
                        "resolution_source": resolution.source,
                        "warning": resolution.warning,
                    },
                )
            _print_workspace_setup_guidance(
                warning=resolution.warning,
                stream=sys.stderr,
            )
            return 2
        config = None
    else:
        require_workspace = _command_requires_workspace(args)
        config, resolution, load_error = _load_config_for_command(
            args,
            require_workspace=require_workspace,
        )
        if load_error == "workspace_not_configured":
            if args.command == "run":
                print(
                    "No Atlas workspace configured. Run `atlas init <name>` first.",
                    file=sys.stderr,
                )
                return 2
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas",
                    code="workspace_not_configured",
                    message="Atlas Agent needs a workspace before it can run.",
                    details={
                        "resolution_source": resolution.source,
                        "warning": resolution.warning,
                    },
                )
            _print_workspace_setup_guidance(
                warning=resolution.warning,
                stream=sys.stderr,
            )
            return 2
        if load_error:
            if args.command in {"validate", "doctor"} and getattr(args, "json", False):
                return emit_cli_error(
                    f"atlas {args.command}",
                    code="config_load_failed",
                    message=load_error,
                )
            print(load_error, file=sys.stderr)
            return 1
        if config is None:
            if args.command in {"validate", "doctor"} and getattr(args, "json", False):
                return emit_cli_error(
                    f"atlas {args.command}",
                    code="config_load_failed",
                    message="Configuration error: unable to load AtlasConfig.",
                )
            print("Configuration error: unable to load AtlasConfig.", file=sys.stderr)
            return 1

    if args.command == "research" and getattr(args, "research_command", None) == "mock-response-final-safety-seal":
        raw = list(getattr(args, "mock_response_final_safety_seal_args", []) or [])
        action_map = {
            "create": "provider-mock-response-final-safety-seal",
            "list": "provider-mock-response-final-safety-seal-list",
            "show": "provider-mock-response-final-safety-seal-show",
            "validate": "provider-mock-response-final-safety-seal-validate",
            "replay": "provider-mock-response-final-safety-seal-replay",
        }
        if raw and raw[0] in action_map:
            action = raw[0]
            rest = raw[1:]
        elif raw:
            action = "create"
            rest = raw
        else:
            action = ""
            rest = []
        if not action or (action != "list" and not rest):
            if getattr(args, "json", False):
                print(json.dumps({"ok": False, "status": "invalid_mock_response_final_safety_seal_command"}, indent=2, sort_keys=True))
            else:
                print("research mock-response-final-safety-seal requires create/show/list/validate/replay")
            return 1
        args.research_command = action_map[action]
        if action == "create":
            args.blocker_id = rest[0]
        elif action in {"show", "validate", "replay"}:
            args.seal_id = rest[0]

            args.run_id = rest[0]

    if args.command == "setup":
        return _run_guided_setup(args=args)

    if args.command == "configure":
        from atlas_agent.setup.wizard import run_wizard, is_interactive
        from atlas_agent.setup.state import WizardState

        if not is_interactive():
            print("Non-interactive mode detected. Cannot run UI wizard.")
            print("Please configure via environment variables or direct config file edits.")
            return 2

        config_path = Path(".atlas/config.json")
        state = WizardState.load(config_path)

        success = run_wizard(state)
        if success:
            try:
                state.save(config_path)
            except ValueError as exc:
                print(f"Setup failed: {exc}")
                return 2
            print(f"Configuration saved to {config_path}")

            # Show final status
            resolution = resolve_workspace(getattr(args, "workspace", None))
            config = None
            try:
                config = AtlasConfig.from_env()
            except ValueError:
                pass

            print("\nConfiguration updated successfully.\n")
            _print_first_run_onboarding(
                config=config,
                config_error=None,
                resolution=resolution,
            )
            return 0
        else:
            print("Setup cancelled. Atlas is not configured yet.")
            return 130

    context = CLIContext(
        args=args,
        config=config,
        resolution=resolution,
        update_checker=_check_for_updates,
    )
    dispatched = build_core_command_registry().dispatch(context)
    if dispatched is not None:
        return dispatched

    if args.command == "kill":
        from atlas_agent.safety.kill_switch import AdvancedKillSwitch
        safety_dir = Path(".atlas/safety")
        safety_dir.mkdir(parents=True, exist_ok=True)
        kill_switch = AdvancedKillSwitch(
            state_path=safety_dir / "kill_switch.json",
            heartbeat_path=safety_dir / "heartbeat.json"
        )

        if args.kill_command == "status":
            decision = kill_switch.evaluate()
            status = kill_switch.state_manager.load()
            print("Kill Switch Status:")
            print(f"  Mode: {status.mode.upper()}")
            print(f"  Status: {decision.status.upper()}")
            print(f"  Reason: {status.reason}")
            print(f"  Actor: {status.actor}")
            print(f"  Updated: {status.updated_at}")
            if decision.action_required:
                print(f"  ACTION REQUIRED: {decision.action_required}")
            return 0

        if args.kill_command == "heartbeat":
            kill_switch.heartbeat_manager.record(source="cli")
            print("Heartbeat recorded.")
            return 0

        mode_map = {
            "soft-pause": "soft_pause",
            "cancel-all": "cancel_all",
            "flatten-all": "flatten_all",
            "lock": "locked_down",
            "reset": "normal"
        }

        if args.kill_command in mode_map:
            new_mode = mode_map[args.kill_command]
            kill_switch.set_mode(new_mode, reason=f"CLI {args.kill_command}", actor="user")
            print(f"Kill switch mode set to: {new_mode}")
            return 0

        if args.kill_command == "plan":
            from atlas_agent.safety.action_plan import SafetyActionPlanner
            from atlas_agent.risk.portfolio import get_portfolio_snapshot

            # Use current state or simulated mode
            ks_mode = kill_switch.state_manager.load().mode
            if args.mode:
                ks_mode = args.mode.replace("-", "_") # type: ignore

            decision = kill_switch.evaluate()
            # Override mode if requested for simulation
            if args.mode:
                from atlas_agent.safety.models import KillSwitchDecision
                decision = KillSwitchDecision(
                    allowed=False,
                    status="blocked" if ks_mode == "soft_pause" else ks_mode.replace("_all", "_required"), # type: ignore
                    mode=ks_mode # type: ignore
                )

            # Load dummy/current portfolio for planning
            portfolio_state = PortfolioState(cash=config.starting_cash)
            portfolio = get_portfolio_snapshot(portfolio_state)

            planner = SafetyActionPlanner(risk_manager=RiskManager())
            plan = planner.create_plan(decision, portfolio, open_order_ids=[], mode="paper")

            if getattr(args, "json", False):
                print(plan.model_dump_json(indent=2))
                return 0

            print(f"Safety Action Plan (Mode: {ks_mode.upper()}):")
            print(f"  Plan ID: {plan.plan_id}")
            print(f"  Status: {plan.status.upper()}")
            print(f"  Reason: {plan.reason}")
            print(f"  Requires Approval: {plan.requires_approval}")
            print("  Actions:")
            for action in plan.actions:
                print(f"    - [{action.type.upper()}] {action.description}")
            return 0

        if args.kill_command == "execute-plan":
            from atlas_agent.safety.models import SafetyActionPlan
            from atlas_agent.safety.executor import SafetyActionExecutor
            from atlas_agent.risk.portfolio import get_portfolio_snapshot
            from atlas_agent.tools.registry import ToolRegistry
            from atlas_agent.tools.builtin import BUILTIN_TOOLS
            from atlas_agent.core.types import Session

            plan_path = Path(args.plan)
            if not plan_path.exists():
                print(f"Plan file not found: {plan_path}")
                return 1

            plan = SafetyActionPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))

            registry = ToolRegistry()
            for tool in BUILTIN_TOOLS:
                registry.register(tool)

            portfolio_state = PortfolioState(cash=config.starting_cash)
            portfolio = get_portfolio_snapshot(portfolio_state)

            executor = SafetyActionExecutor(
                tool_registry=registry,
                kill_switch=kill_switch,
                risk_manager=RiskManager()
            )

            mode = "paper" if args.paper else "live"
            session = Session(id=f"cli_safety_{plan.plan_id}", turn_count=0, has_summarized=False)

            result = executor.execute_plan(
                plan,
                session,
                portfolio,
                mode=mode, # type: ignore
                approved=args.approved
            )

            print(f"Safety Plan Execution Result (Mode: {mode.upper()}):")
            print(f"  Plan ID: {result.plan_id}")
            print(f"  Status: {result.status.upper()}")
            print(f"  Executed: {len(result.executed_actions)}")
            print(f"  Failed: {len(result.failed_actions)}")
            print(f"  Skipped: {len(result.skipped_actions)}")

            if result.errors:
                print("  Errors:")
                for err in result.errors:
                    print(f"    - {err}")

            return 0 if result.status == "completed" else 2

    if args.command == "plan":
        from atlas_agent.agent.planner import get_agent_plan
        print(get_agent_plan(config))
        return 0
    if args.command == "run":
        from atlas_agent.agent.planner import get_agent_plan
        from atlas_agent.agent.runner import run_agent
        if getattr(args, "dry_run", False):
            print(get_agent_plan(config))
            return 0
        if getattr(args, "offline", False):
            config.model.provider = "null"
            config.model.model = "null"
        _check_discipline_or_exit(config)
        resolved_symbol = _resolve_symbol(config, getattr(args, "symbol", None))
        result = run_agent(
            mode=args.mode,
            config=config,
            continuous=args.continuous,
            interval=args.interval,
            max_cycles=args.max_cycles,
            symbol=resolved_symbol,
        )
        if result is None:
            return 0
        # Compatibility check for both RoutineResult and AgentResult
        success_statuses = {
            "filled", "held", "pending_approval", "simulated", "complete",
            "approval_required"
        }
        return 0 if result.status in success_statuses else 2

    if args.command == "validate":
        from atlas_agent.diagnostics.readiness import run_diagnostics, print_readiness_report

        strict = bool(getattr(args, "strict", False))
        try:
            report = run_diagnostics(config)
        except Exception:
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas validate",
                    code="validate_failed",
                    message="Readiness diagnostics failed.",
                )
            print("Readiness diagnostics failed.", file=sys.stderr)
            return 1

        passed = _readiness_passed(report)

        if getattr(args, "json", False):
            payload = {
                "strict": strict,
                "passed": passed,
                "report": report.to_dict(),
            }
            emit_json(success_envelope("atlas validate", payload))
            return 2 if strict and not passed else 0

        print_readiness_report(report)
        if strict and not passed:
            return 2
        return 0
    if args.command == "doctor":
        from atlas_agent.diagnostics.preflight import (
            build_preflight_report,
            render_preflight_report,
        )

        report = build_preflight_report(config)
        if getattr(args, "json", False):
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        print(render_preflight_report(report))
        return 0
    if args.command == "providers":
        from atlas_agent.cli_commands.providers import handle_providers

        _handled = handle_providers(context)
        if _handled is not None:
            return _handled





    if args.command == "broker":
        from atlas_agent.cli_commands.broker import handle_broker

        _handled = handle_broker(context)
        if _handled is not None:
            return _handled
    if args.command == "backtest":
        if args.backtest_command == "compare":
            try:
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_strategy_evaluation(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    initial_equity=getattr(args, "initial_equity", 10000.0),
                    slippage_bps=getattr(args, "slippage_bps", 0.0),
                    commission_bps=getattr(args, "commission_bps", 0.0),
                    start_date=getattr(args, "start_date", None),
                    end_date=getattr(args, "end_date", None),
                )
                json_path, markdown_path = write_strategy_evaluation_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            decisions: dict[str, int] = {}
            for item in report.get("strategies", []):
                decision = item.get("paper_gate", {}).get("decision", "unknown")
                decisions[decision] = decisions.get(decision, 0) + 1
            decision_summary = ", ".join(
                f"{name}={count}" for name, count in sorted(decisions.items())
            )
            print(f"Paper strategy evaluation complete: {report['symbol']}")
            print(f"Strategies evaluated: {len(report['strategies'])}")
            print(f"Paper gate decisions: {decision_summary}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")
            print("No live trading, broker calls, provider calls, or network calls.")
            return 0

        if args.backtest_command == "sensitivity":
            try:
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_strategy_sensitivity(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    initial_equity=getattr(args, "initial_equity", 10000.0),
                    slippage_bps=getattr(args, "slippage_bps", 0.0),
                    commission_bps=getattr(args, "commission_bps", 0.0),
                    start_date=getattr(args, "start_date", None),
                    end_date=getattr(args, "end_date", None),
                )
                json_path, markdown_path = write_strategy_sensitivity_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            decisions: dict[str, int] = {}
            for item in report.get("strategies", []):
                for variant in item.get("variants", []):
                    decision = variant.get("paper_gate", {}).get("decision", "unknown")
                    decisions[decision] = decisions.get(decision, 0) + 1
            decision_summary = ", ".join(
                f"{name}={count}" for name, count in sorted(decisions.items())
            )
            print(f"Paper strategy sensitivity evaluation complete: {report['symbol']}")
            print(f"Strategies evaluated: {len(report['strategies'])}")
            print(f"Paper gate decisions: {decision_summary}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")
            print("No live trading, broker calls, provider calls, or network calls.")
            return 0

        if args.backtest_command == "walk-forward":
            try:
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_strategy_walk_forward(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    window_size=getattr(args, "window_size", 60),
                    step_size=getattr(args, "step_size", 30),
                    strategies=strategy_ids,
                    initial_equity=getattr(args, "initial_equity", 10000.0),
                    slippage_bps=getattr(args, "slippage_bps", 0.0),
                    commission_bps=getattr(args, "commission_bps", 0.0),
                )
                json_path, markdown_path = write_strategy_walk_forward_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            decisions: dict[str, int] = {}
            for item in report.get("strategies", []):
                status = item.get("walk_forward_summary", {}).get("paper_follow_up_status", "unknown")
                decisions[status] = decisions.get(status, 0) + 1
            decision_summary = ", ".join(
                f"{name}={count}" for name, count in sorted(decisions.items())
            )
            print(f"Paper strategy walk-forward evaluation complete: {report['symbol']}")
            print(f"Windows evaluated: {report['windowing']['windows_evaluated']}")
            print(f"Strategies evaluated: {len(report['strategies'])}")
            print(f"Paper walk-forward decisions: {decision_summary}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")

            safety = report.get("safety", {})
            if all(safety.values()):
                print("No live trading, broker calls, provider calls, or network calls.")
            return 0
        if args.backtest_command == "robustness":
            try:
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                fixture_paths = parse_fixture_list(getattr(args, "fixtures"))
                report = build_paper_strategy_robustness(
                    fixture_paths=fixture_paths,
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    initial_equity=getattr(args, "initial_equity", 10000.0),
                    slippage_bps=getattr(args, "slippage_bps", 0.0),
                    commission_bps=getattr(args, "commission_bps", 0.0),
                    start_date=getattr(args, "start_date", None),
                    end_date=getattr(args, "end_date", None),
                )
                json_path, markdown_path = write_strategy_robustness_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            decisions: dict[str, int] = {}
            for item in report.get("strategies", []):
                status = item.get("robustness_summary", {}).get("paper_follow_up_status", "unknown")
                decisions[status] = decisions.get(status, 0) + 1
            decision_summary = ", ".join(
                f"{name}={count}" for name, count in sorted(decisions.items())
            )
            print(f"Paper strategy robustness evaluation complete: {report['symbol']}")
            print(f"Regimes evaluated: {len(report['regimes'])}")
            print(f"Strategies evaluated: {len(report['strategies'])}")
            print(f"Paper robustness decisions: {decision_summary}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")
            print("No live trading, broker calls, provider calls, or network calls.")
            return 0

        if args.backtest_command == "portfolio-proposal":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_proposal, write_portfolio_proposal_reports
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_portfolio_proposal(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    max_strategy_weight=getattr(args, "max_strategy_weight", 0.40),
                    min_cash_weight=getattr(args, "min_cash_weight", 0.10),
                )
                json_path, markdown_path = write_portfolio_proposal_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper portfolio proposal complete: {report['symbol']}")
            print(f"Proposal status: {report['proposal_status']}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")
            print("No live trading, broker calls, provider calls, or network calls.")
            return 0

        if args.backtest_command == "portfolio-stress":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_stress, write_portfolio_stress_reports
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_portfolio_stress(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    max_strategy_weight=getattr(args, "max_strategy_weight", 0.40),
                    min_cash_weight=getattr(args, "min_cash_weight", 0.10),
                    max_stressed_drawdown=getattr(args, "max_stressed_drawdown", 0.25),
                    max_single_scenario_loss=getattr(args, "max_single_scenario_loss", 0.20),
                )
                json_path, markdown_path = write_portfolio_stress_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper portfolio stress complete: {report['symbol']}")
            print(f"Stress status: {report['overall_stress_status']}")
            print(f"Scenarios evaluated: {len(report['stress_results'])}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")
            print("No live trading, broker calls, provider calls, or network calls.")
            return 0

        if args.backtest_command == "portfolio-monitor":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_monitoring, write_portfolio_monitoring_reports
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_portfolio_monitoring(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    max_strategy_weight=getattr(args, "max_strategy_weight", 0.40),
                    min_cash_weight=getattr(args, "min_cash_weight", 0.10),
                    max_stressed_drawdown=getattr(args, "max_stressed_drawdown", 0.25),
                    max_single_scenario_loss=getattr(args, "max_single_scenario_loss", 0.20),
                    monitor_window=getattr(args, "monitor_window", 20),
                    recheck_threshold=getattr(args, "recheck_threshold", 0.05),
                )
                json_path, markdown_path = write_portfolio_monitoring_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper portfolio monitoring complete: {report['symbol']}")
            print(f"Monitoring status: {report['overall_monitoring_status']}")
            print(f"Events evaluated: {len(report['monitoring_events'])}")
            print(f"Human review recommended: {report['human_review_recommended']}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")
            print("No live trading, broker calls, provider calls, network calls, or notifications.")
            return 0

        if args.backtest_command == "portfolio-recheck":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_recheck, write_portfolio_recheck_reports
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_portfolio_recheck(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    max_strategy_weight=getattr(args, "max_strategy_weight", 0.40),
                    min_cash_weight=getattr(args, "min_cash_weight", 0.10),
                    max_stressed_drawdown=getattr(args, "max_stressed_drawdown", 0.25),
                    max_single_scenario_loss=getattr(args, "max_single_scenario_loss", 0.20),
                    monitor_window=getattr(args, "monitor_window", 20),
                    recheck_threshold=getattr(args, "recheck_threshold", 0.05),
                )
                json_path, markdown_path = write_portfolio_recheck_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper portfolio recheck ledger complete: {report['symbol']}")
            print(f"Overall review status: {report['overall_review_status']}")
            print(f"Review items generated: {len(report['review_items'])}")
            print(f"Human review required in queue: {sum(1 for item in report['review_queue'] if item['human_review_required'])}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")
            print("No live trading, broker calls, provider calls, network calls, or notifications.")
            return 0

        if args.backtest_command == "portfolio-dossier":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_dossier, write_portfolio_dossier_reports
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_portfolio_dossier(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    max_strategy_weight=getattr(args, "max_strategy_weight", 0.40),
                    min_cash_weight=getattr(args, "min_cash_weight", 0.10),
                    max_stressed_drawdown=getattr(args, "max_stressed_drawdown", 0.25),
                    max_single_scenario_loss=getattr(args, "max_single_scenario_loss", 0.20),
                    monitor_window=getattr(args, "monitor_window", 20),
                    recheck_threshold=getattr(args, "recheck_threshold", 0.05),
                )
                json_path, md_path, manifest_path = write_portfolio_dossier_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper portfolio reviewer dossier generated: {report['symbol']}")
            print(f"Overall dossier status: {report['overall_dossier_status']}")
            print(f"Artifacts bundled: {len(report['artifacts'])}")
            print(f"Manifest saved to: {manifest_path}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {md_path}")
            print("No live trading, broker calls, provider calls, network calls, or notifications.")
            return 0

        if args.backtest_command == "portfolio-replay":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_replay, write_portfolio_replay_reports
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_portfolio_replay(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    repeat=getattr(args, "repeat", 2),
                    max_strategy_weight=getattr(args, "max_strategy_weight", 0.40),
                    min_cash_weight=getattr(args, "min_cash_weight", 0.10),
                    max_stressed_drawdown=getattr(args, "max_stressed_drawdown", 0.25),
                    max_single_scenario_loss=getattr(args, "max_single_scenario_loss", 0.20),
                    monitor_window=getattr(args, "monitor_window", 20),
                    recheck_threshold=getattr(args, "recheck_threshold", 0.05),
                )
                json_path, md_path, manifest_path = write_portfolio_replay_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper portfolio replay generated: {report['symbol']}")
            print(f"Overall replay status: {report['overall_replay_status']}")
            print(f"Repeat count: {report['repeat']}")
            print(f"Manifest saved to: {manifest_path}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {md_path}")
            print("No live trading, broker calls, provider calls, network calls, or notifications.")
            return 0

        if args.backtest_command == "portfolio-review-pack":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_review_pack, write_portfolio_review_pack_reports
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                report = build_paper_portfolio_review_pack(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    strategies=strategy_ids,
                    max_strategy_weight=getattr(args, "max_strategy_weight", 0.40),
                    min_cash_weight=getattr(args, "min_cash_weight", 0.10),
                    max_stressed_drawdown=getattr(args, "max_stressed_drawdown", 0.25),
                    max_single_scenario_loss=getattr(args, "max_single_scenario_loss", 0.20),
                    monitor_window=getattr(args, "monitor_window", 20),
                    recheck_threshold=getattr(args, "recheck_threshold", 0.05),
                )
                json_path, md_path = write_portfolio_review_pack_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper human review pack generated: {report['symbol']}")
            print(f"Overall review pack status: {report['overall_review_pack_status']}")
            print(f"Review items: {len(report['review_items'])}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {md_path}")
            print("Non-executable. No live trading, broker calls, provider calls, network calls, or notifications.")
            return 0

        if args.backtest_command == "portfolio-review-ledger":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_review_ledger, write_portfolio_review_ledger_reports
                if getattr(args, "review_pack", None):
                    report = build_paper_portfolio_review_ledger(review_pack_path=getattr(args, "review_pack"))
                else:
                    strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                    report = build_paper_portfolio_review_ledger(
                        build_kwargs={
                            "data_path": getattr(args, "data"),
                            "symbol": getattr(args, "symbol"),
                            "strategies": strategy_ids,
                            "max_strategy_weight": getattr(args, "max_strategy_weight", 0.40),
                            "min_cash_weight": getattr(args, "min_cash_weight", 0.10),
                            "max_stressed_drawdown": getattr(args, "max_stressed_drawdown", 0.25),
                            "max_single_scenario_loss": getattr(args, "max_single_scenario_loss", 0.20),
                            "monitor_window": getattr(args, "monitor_window", 20),
                            "recheck_threshold": getattr(args, "recheck_threshold", 0.05),
                        }
                    )
                json_path, md_path = write_portfolio_review_ledger_reports(report, output_dir=getattr(args, "output_dir"))
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper human review ledger generated: {report.get('symbol', 'n/a')}")
            print(f"Overall review ledger status: {report['overall_review_ledger_status']}")
            print(f"Decision entries: {len(report['decision_entries'])}")
            print(f"Live approval granted: {report['gate_summary']['live_approval_granted']}")
            print(f"Broker submission allowed: {report['gate_summary']['broker_submission_allowed']}")
            print(f"Paper follow-up allowed: {report['gate_summary']['paper_follow_up_allowed']}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {md_path}")
            print("Non-executable. No live trading, broker calls, provider calls, network calls, notifications, or real human approval.")
            return 0

        if args.backtest_command == "portfolio-review-policy":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_review_policy, write_portfolio_review_policy_reports
                if getattr(args, "review_pack", None) and getattr(args, "review_ledger", None):
                    report = build_paper_portfolio_review_policy(
                        review_pack_path=getattr(args, "review_pack"),
                        review_ledger_path=getattr(args, "review_ledger"),
                    )
                else:
                    strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                    report = build_paper_portfolio_review_policy(
                        build_kwargs={
                            "data_path": getattr(args, "data"),
                            "symbol": getattr(args, "symbol"),
                            "strategies": strategy_ids,
                            "max_strategy_weight": getattr(args, "max_strategy_weight", 0.40),
                            "min_cash_weight": getattr(args, "min_cash_weight", 0.10),
                            "max_stressed_drawdown": getattr(args, "max_stressed_drawdown", 0.25),
                            "max_single_scenario_loss": getattr(args, "max_single_scenario_loss", 0.20),
                            "monitor_window": getattr(args, "monitor_window", 20),
                            "recheck_threshold": getattr(args, "recheck_threshold", 0.05),
                        }
                    )
                json_path, md_path = write_portfolio_review_policy_reports(report, output_dir=getattr(args, "output_dir"))
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper human review policy simulation generated: {report.get('symbol', 'n/a')}")
            print(f"Overall policy status: {report['overall_policy_status']}")
            print(f"Policy rules evaluated: {len(report['policy_results'])}")
            print(f"Live path blocked: {report['gate_summary']['live_path_blocked']}")
            print(f"Broker submission allowed: {report['gate_summary']['broker_submission_allowed']}")
            print(f"Paper follow-up allowed: {report['gate_summary']['paper_follow_up_allowed']}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {md_path}")
            print("Non-executable. No live trading, broker calls, provider calls, network calls, notifications, orders, or real human approval.")
            return 0

        if args.backtest_command == "portfolio-review-replay":
            try:
                from atlas_agent.backtest.portfolio import build_paper_portfolio_review_replay, write_portfolio_review_replay_reports
                if (
                    getattr(args, "review_pack", None)
                    and getattr(args, "review_ledger", None)
                    and getattr(args, "review_policy", None)
                ):
                    report = build_paper_portfolio_review_replay(
                        review_pack_path=getattr(args, "review_pack"),
                        review_ledger_path=getattr(args, "review_ledger"),
                        review_policy_path=getattr(args, "review_policy"),
                    )
                else:
                    strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                    report = build_paper_portfolio_review_replay(
                        build_kwargs={
                            "data_path": getattr(args, "data"),
                            "symbol": getattr(args, "symbol"),
                            "strategies": strategy_ids,
                            "max_strategy_weight": getattr(args, "max_strategy_weight", 0.40),
                            "min_cash_weight": getattr(args, "min_cash_weight", 0.10),
                            "max_stressed_drawdown": getattr(args, "max_stressed_drawdown", 0.25),
                            "max_single_scenario_loss": getattr(args, "max_single_scenario_loss", 0.20),
                            "monitor_window": getattr(args, "monitor_window", 20),
                            "recheck_threshold": getattr(args, "recheck_threshold", 0.05),
                        }
                    )
                json_path, md_path = write_portfolio_review_replay_reports(report, output_dir=getattr(args, "output_dir"))
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            print(f"Paper human review replay generated: {report.get('symbol', 'n/a')}")
            print(f"Overall replay status: {report['overall_replay_status']}")
            print(f"Regression checks: {len(report['regression_checks'])}")
            print(f"Deterministic replay passed: {report['gate_summary']['deterministic_replay_passed']}")
            print(f"Live path blocked: {report['gate_summary']['live_path_blocked']}")
            print(f"Broker submission allowed: {report['gate_summary']['broker_submission_allowed']}")
            print(f"Paper follow-up allowed: {report['gate_summary']['paper_follow_up_allowed']}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {md_path}")
            print("Non-executable. No live trading, broker calls, provider calls, network calls, notifications, orders, or real human approval.")
            return 0

        if args.backtest_command == "scorecard":
            try:
                from atlas_agent.backtest.scorecard import build_paper_strategy_scorecard, write_strategy_scorecard_reports
                from atlas_agent.backtest.robustness import parse_fixture_list as parse_scorecard_fixtures
                strategy_ids = parse_strategy_list(getattr(args, "strategies", None))
                fixtures = parse_scorecard_fixtures(getattr(args, "fixtures")) if getattr(args, "fixtures", None) else None
                report = build_paper_strategy_scorecard(
                    data_path=getattr(args, "data"),
                    symbol=getattr(args, "symbol"),
                    fixtures=fixtures,
                    strategies=strategy_ids,
                    window_size=getattr(args, "window_size", 60),
                    step_size=getattr(args, "step_size", 30),
                    initial_equity=getattr(args, "initial_equity", 10000.0),
                    slippage_bps=getattr(args, "slippage_bps", 0.0),
                    commission_bps=getattr(args, "commission_bps", 0.0),
                )
                json_path, markdown_path = write_strategy_scorecard_reports(
                    report,
                    output_dir=getattr(args, "output_dir"),
                )
            except Exception as exc:
                print(f"Error: {exc}")
                return 1

            if getattr(args, "json", False):
                import json
                print(json.dumps(report, indent=2, sort_keys=True, default=str))
                return 0

            decisions: dict[str, int] = {}
            for item in report.get("strategies", []):
                status = item.get("scorecard", {}).get("decision", "unknown")
                decisions[status] = decisions.get(status, 0) + 1
            decision_summary = ", ".join(
                f"{name}={count}" for name, count in sorted(decisions.items())
            )
            print(f"Paper strategy scorecard complete: {report['symbol']}")
            print(f"Strategies evaluated: {len(report['strategies'])}")
            print(f"Paper scorecard decisions: {decision_summary}")
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {markdown_path}")
            print("No live trading, broker calls, provider calls, or network calls.")
            return 0

        if args.backtest_command == "list-strategies":
            strategies = list_strategies()
            if getattr(args, "json", False):
                print(json.dumps([item.model_dump(mode="json") for item in strategies], indent=2))
                return 0
            for item in strategies:
                print(f"{item.strategy_id}\t{item.name}\t{item.version}")
            return 0

        if args.backtest_command == "describe":
            try:
                metadata = describe_strategy(args.strategy)
            except KeyError as exc:
                print(f"Error: {exc}")
                return 1
            if getattr(args, "json", False):
                print(metadata.model_dump_json(indent=2))
                return 0
            print(f"Strategy: {metadata.strategy_id}")
            print(f"Name:     {metadata.name}")
            print(f"Version:  {metadata.version}")
            print(f"Summary:  {metadata.description}")
            if metadata.tags:
                print(f"Tags:     {', '.join(metadata.tags)}")
            if metadata.parameters:
                print("Parameters:")
                for name, spec in metadata.parameters.items():
                    default = f" default={spec.default!r}" if spec.default is not None else ""
                    print(f"  {name} ({spec.type}{default}): {spec.description}")
            return 0

        if args.backtest_command == "validate":
            symbol = getattr(args, "symbol", None) or config.backtest.default_symbol
            data_path = str(getattr(args, "data", None) or config.backtest.data_path)
            initial_equity = getattr(args, "initial_equity", config.backtest.initial_cash)
            try:
                strategy_parameters = _configured_strategy_parameters(
                    config,
                    getattr(args, "strategy_param", []),
                )
            except ValueError as exc:
                print(f"Error: {exc}")
                return 1
            bt_config = BacktestConfig(
                symbol=symbol,
                data_path=data_path,
                initial_equity=initial_equity,
                strategy_mode=args.strategy,
                strategy_parameters=strategy_parameters,
            )
            ensure_sample_data(Path(data_path))
            bars = load_market_data(data_path, symbol)
            result = validate_strategy(args.strategy, bars=bars, config=bt_config)
            if getattr(args, "json", False):
                print(result.model_dump_json(indent=2))
                return 0 if result.status == "valid" else 1
            print(f"Strategy validation: {result.strategy_id} ({result.status})")
            for issue in result.issues:
                print(f"{issue.severity}: {issue.code}: {issue.message}")
            return 0 if result.status == "valid" else 1

        if args.backtest_command == "run" or args.backtest_command is None:
            # If no sub-command, use defaults from config
            symbol = getattr(args, "symbol", config.backtest.default_symbol)
            data_path = str(getattr(args, "data", config.backtest.data_path))
            initial_equity = getattr(args, "initial_equity", config.backtest.initial_cash)
            strategy_mode = (
                getattr(args, "strategy", None)
                or getattr(config.backtest, "default_strategy", "buy_and_hold")
            )
            benchmark_mode = (
                getattr(args, "benchmark", None)
                or getattr(config.backtest, "benchmark", "buy_and_hold")
            )
            benchmark_symbol = (
                getattr(args, "benchmark_symbol", None)
                or getattr(config.backtest, "benchmark_symbol", "SPY")
            )
            configured_benchmark_data_path = getattr(config.backtest, "benchmark_data_path", None)
            benchmark_data_path = (
                getattr(args, "benchmark_data", None)
                or (str(configured_benchmark_data_path) if configured_benchmark_data_path else None)
            )
            slippage_bps = getattr(args, "slippage_bps", 0.0)
            commission_bps = getattr(args, "commission_bps", 0.0)
            use_json = getattr(args, "json", False)
            try:
                strategy_parameters = _configured_strategy_parameters(
                    config,
                    getattr(args, "strategy_param", []),
                )
            except ValueError as exc:
                print(f"Error: {exc}")
                return 1

            bt_config = BacktestConfig(
                symbol=symbol,
                data_path=data_path,
                initial_equity=initial_equity,
                strategy_mode=strategy_mode,
                strategy_parameters=strategy_parameters,
                benchmark_mode=benchmark_mode,
                benchmark_symbol=benchmark_symbol,
                benchmark_data_path=benchmark_data_path,
                slippage_bps=slippage_bps,
                commission_bps=commission_bps,
                start_date=getattr(args, "start_date", None),
                end_date=getattr(args, "end_date", None),
            )

            ensure_sample_data(Path(data_path))

            # Use AuditWriter if available
            audit_writer = None
            try:
                from atlas_agent.audit import AuditWriter
                audit_writer = AuditWriter(config.audit_dir / "audit.log")
            except (ImportError, AttributeError):
                pass

            try:
                engine = BacktestEngine(bt_config, audit_writer=audit_writer)
                result = engine.run()
            except (KeyError, ValueError) as exc:
                print(f"Error: {exc}")
                return 1

            if use_json:
                print(result.model_dump_json(indent=2))
                return 0

            report_format = getattr(args, "report", None)
            if report_format == "json":
                print(json.dumps(render_json_report(result), indent=2, sort_keys=True, default=str))
                return 0
            if report_format == "markdown":
                print(render_markdown_report(result))
                return 0

            print(f"Backtest complete: {symbol}")
            # Compatibility mapping for tests
            display_status = "filled" if result.status == "completed" else result.status
            print(f"backtest result: {display_status}")
            print(f"Initial Equity: ${result.metrics.initial_equity:,.2f}")
            print(f"Final Equity:   ${result.metrics.final_equity:,.2f}")
            print(f"Total Return:   {result.metrics.total_return_pct:.2f}%")
            print(f"Max Drawdown:   {result.metrics.max_drawdown_pct:.2f}%")
            print(f"Trade Count:    {result.metrics.trade_count}")

            # Write report files to disk
            report_dir = Path(".atlas/backtests") / result.run_id
            json_path, md_path = write_report_from_result(result, output_dir=report_dir)
            print(f"Report saved to: {json_path}")
            print(f"Markdown saved to: {md_path}")

            return 0
        if args.backtest_command == "runs":
            do_validate = getattr(args, "validate", False)
            runs = _list_backtest_runs(validate=do_validate)
            if getattr(args, "json", False):
                print(json.dumps(runs, indent=2, default=str))
                return 0
            if not runs:
                print("No backtest runs found.")
                return 0
            if do_validate:
                print(f"{'Run ID':<30} {'Symbol':<10} {'Strategy':<20} {'Status':<12} {'Return %':<10} {'Schema':<15} {'Date':<20}")
                for run in runs:
                    schema_display = str(run.get('schema_status', ''))[:15]
                    print(f"{run['run_id']:<30} {run['symbol']:<10} {run['strategy']:<20} {run['status']:<12} {run['return_pct']:<10.2f} {schema_display:<15} {run['date']:<20}")
                    if run.get('schema_error'):
                        print(f"  → {run['schema_error']}")
                        errors = run.get('schema_errors')
                        if errors and len(errors) > 1:
                            print(f"  → ({len(errors)} total errors)")
            else:
                print(f"{'Run ID':<30} {'Symbol':<10} {'Strategy':<20} {'Status':<12} {'Return %':<10} {'Date':<20}")
                for run in runs:
                    print(f"{run['run_id']:<30} {run['symbol']:<10} {run['strategy']:<20} {run['status']:<12} {run['return_pct']:<10.2f} {run['date']:<20}")
            return 0

        else:
            print("Error: Use 'atlas backtest run --help' for usage.")
            return 1
    if args.command == "run-once":
        _check_discipline_or_exit(config)
        event_logger = EventLogger(config.events_dir)
        run_id = generate_run_id()
        event_logger.write(
            "agent_started",
            run_id=run_id,
            command="atlas run-once",
            mode=args.mode,
            payload={"requested_mode": args.mode},
        )
        result = run_once(
            mode=args.mode,
            config=config,
            event_logger=event_logger,
            run_id=run_id,
            command="atlas run-once",
            symbol=getattr(args, "symbol", None),
        )
        event_logger.write(
            "agent_completed" if result.status in {"filled", "held", "pending_approval"} else "agent_failed",
            run_id=run_id,
            command="atlas run-once",
            mode=args.mode,
            payload={"status": result.status, "message": result.message},
        )
        print(f"{args.mode} result: {result.status} - {result.message}")
        if result.reasons:
            print("Reasons:", "; ".join(result.reasons))
        return 0 if result.status in {"filled", "held", "pending_approval"} else 2

    if args.command == "dashboard":
        from atlas_agent.cli_commands.dashboard import handle_dashboard

        _handled = handle_dashboard(context)
        if _handled is not None:
            return _handled

    if args.command == "reflection":
        from atlas_agent.cli_commands.reflection import handle_reflection

        _handled = handle_reflection(context)
        if _handled is not None:
            return _handled

    if args.command == "agent":
        from atlas_agent.agent.planner import get_agent_plan, get_agent_plan_payload
        from atlas_agent.agent.runner import run_agent
        from atlas_agent.agent.status import get_agent_status, get_agent_status_payload
        from atlas_agent.learning import run_learning_cycle, generate_reflection

        if args.agent_command == "status":
            if getattr(args, "json", False):
                return emit_cli_success(
                    "atlas agent status",
                    get_agent_status_payload(config),
                )
            print(get_agent_status(config))
            return 0
        elif args.agent_command == "plan":
            if getattr(args, "json", False):
                return emit_cli_success(
                    "atlas agent plan",
                    get_agent_plan_payload(config),
                )
            print(get_agent_plan(config))
            return 0
        elif args.agent_command == "learn":
            event_logger = EventLogger(config.events_dir)
            run_id = generate_run_id()
            event_logger.write(
                "agent_started",
                run_id=run_id,
                command="atlas agent learn",
                mode="paper",
                payload={"source": "cli"},
            )
            report = run_learning_cycle(
                config.memory_dir,
                config.reports_dir,
                config.memory_dir.parent / "skills",
                event_logger=event_logger,
                run_id=run_id,
                command="atlas agent learn",
                mode="paper",
            )
            event_logger.write(
                "agent_completed",
                run_id=run_id,
                command="atlas agent learn",
                mode="paper",
                payload={"report_path": report},
            )
            print(f"Learning cycle complete. Report: {report}")
            return 0
        elif args.agent_command == "reflect":
            event_logger = EventLogger(config.events_dir)
            run_id = generate_run_id()
            event_logger.write(
                "agent_started",
                run_id=run_id,
                command="atlas agent reflect",
                mode="paper",
                payload={"source": "cli"},
            )
            report = generate_reflection(
                config.memory_dir,
                config.reports_dir,
                event_logger=event_logger,
                run_id=run_id,
                command="atlas agent reflect",
                mode="paper",
            )
            event_logger.write(
                "agent_completed",
                run_id=run_id,
                command="atlas agent reflect",
                mode="paper",
                payload={"report_path": str(report)},
            )
            print(f"Reflection generated: {report}")
            return 0
        elif args.agent_command == "autonomous-paper":
            _check_discipline_or_exit(config)
            from atlas_agent.agent.autonomous_paper import (
                build_autonomous_paper_evidence,
                run_autonomous_paper_loop,
            )

            config = _effective_config_with_runtime_kill_switch(config)
            resolved_symbol = _resolve_symbol(config, getattr(args, "symbol", None))
            strategy_parameters = _configured_strategy_parameters(
                config,
                getattr(args, "strategy_param", []),
            )
            evidence_dir = getattr(args, "evidence_dir", None)
            if getattr(args, "state_dir", None):
                from atlas_agent.agent.autonomous_paper import (
                    run_stateful_autonomous_paper_loop,
                )

                run_id: str | None = None
                if args.resume:
                    run_id = _latest_stateful_run_id(args.state_dir)
                result = run_stateful_autonomous_paper_loop(
                    config=config,
                    symbol=resolved_symbol,
                    strategy_id=args.strategy,
                    strategy_parameters=strategy_parameters,
                    data_path=args.data_path,
                    max_cycles=args.max_cycles,
                    output_dir=evidence_dir,
                    state_dir=args.state_dir,
                    resume=args.resume,
                    initial_cash=args.initial_cash,
                    commission_bps=args.commission_bps,
                    slippage_bps=args.slippage_bps,
                    fill_timing=args.fill_timing,
                    run_id=run_id,
                )
                if getattr(args, "json", False):
                    return emit_cli_success(
                        "atlas agent autonomous-paper",
                        result.model_dump(mode="json"),
                    )
                print(
                    f"autonomous-paper {result.status}: processed "
                    f"{result.bars_processed_this_run} bar(s) "
                    f"({result.total_bars_processed} total)"
                )
                print(f"  checkpoint: {result.checkpoint_path}")
                print(f"  decisions file: {result.decisions_path}")
                print(f"  fills file: {result.fills_path}")
                print(f"  metrics file: {result.metrics_path}")
                print(f"  manifest file: {result.manifest_path}")
                for error in result.errors:
                    print(f"  error: {error}")
                return 0 if result.status in ("completed", "no_new_data") else 2

            result = run_autonomous_paper_loop(
                config=config,
                symbol=resolved_symbol,
                strategy_id=args.strategy,
                data_path=args.data_path,
                max_cycles=args.max_cycles,
            )
            if evidence_dir:
                build_autonomous_paper_evidence(
                    run_id=result.run_id,
                    decisions_path=result.decisions_path,
                    manifest_path=result.manifest_path,
                    output_dir=evidence_dir,
                )
            if getattr(args, "json", False):
                return emit_cli_success(
                    "atlas agent autonomous-paper",
                    result.model_dump(mode="json"),
                )
            print(f"autonomous-paper {result.status}: processed {result.bars_processed} bar(s)")
            print(f"  decisions: {result.decisions}")
            print(f"  trades executed: {result.trades_executed}")
            print(f"  trades blocked: {result.trades_blocked}")
            print(f"  no-trade decisions: {result.no_trade_count}")
            print(f"  decisions file: {result.decisions_path}")
            print(f"  manifest file: {result.manifest_path}")
            for error in result.errors:
                print(f"  error: {error}")
            return 0 if result.status == "completed" else 2
        elif args.agent_command == "autonomous-scorecard":
            from atlas_agent.agent.autonomous_paper_scorecard import (
                build_autonomous_paper_scorecard,
                write_autonomous_paper_scorecard_reports,
            )
            output_dir = getattr(args, "output_dir", None) or str(config.reports_dir / "autonomous_paper_scorecard")
            scorecard = build_autonomous_paper_scorecard(
                decisions_path=args.decisions,
                manifest_path=args.manifest,
                replay_decisions_path=getattr(args, "replay_decisions", None),
            )
            write_autonomous_paper_scorecard_reports(scorecard, output_dir)
            if getattr(args, "json", False):
                return emit_cli_success("atlas agent autonomous-scorecard", scorecard)
            print(f"autonomous-scorecard: {scorecard['promotion_state']}")
            print(f"  output dir: {output_dir}")
            for blocker in scorecard.get("blockers", []):
                print(f"  blocker: {blocker}")
            return 0 if scorecard["promotion_state"] not in ("blocked", "not_evaluated") else 2
        elif args.agent_command == "autonomous-paper-quality":
            from atlas_agent.agent.autonomous_paper_quality import (
                TradingQualityThresholdPolicy,
                build_trading_quality_gate,
                write_trading_quality_artifacts,
            )

            policy = TradingQualityThresholdPolicy()
            if getattr(args, "threshold_policy", None):
                policy_data = json.loads(Path(args.threshold_policy).read_text(encoding="utf-8"))
                policy = TradingQualityThresholdPolicy.from_dict(policy_data)

            output_dir = getattr(args, "output_dir", None) or str(
                config.reports_dir / "autonomous_paper_quality"
            )
            report = build_trading_quality_gate(
                metrics_path=args.metrics,
                decisions_path=args.decisions,
                fills_path=args.fills,
                state_path=getattr(args, "state", None),
                scorecard_path=getattr(args, "scorecard", None),
                data_path=getattr(args, "data_path", None),
                policy=policy,
                symbol=getattr(args, "symbol", None),
            )
            json_path, md_path = write_trading_quality_artifacts(report, output_dir)

            if getattr(args, "json", False):
                return emit_cli_success(
                    "atlas agent autonomous-paper-quality",
                    {
                        "report": report,
                        "json_path": str(json_path),
                        "md_path": str(md_path),
                    },
                )

            print(f"trading-quality-gate: {report['quality_state']}")
            print(f"  json: {json_path}")
            print(f"  md:   {md_path}")
            if report["blockers"]:
                print("  blockers:")
                for blocker in report["blockers"]:
                    print(f"    - {blocker}")
            return 0 if report["quality_state"] in (
                "paper_quality_reviewable",
                "eligible_for_shadow_live_quality_review",
            ) else 2
        elif args.agent_command == "shadow-live":
            return cmd_agent_shadow_live(args)
        elif args.agent_command == "submit-conformance":
            from atlas_agent.agent.gated_submit_conformance_cli import main as gsc_main

            gsc_args = [
                "--quality-gate", args.quality_gate,
                "--shadow-comparison", args.shadow_comparison,
                "--order-intent", args.order_intent,
                "--kill-switch", args.kill_switch,
                "--risk-envelope", args.risk_envelope,
                "--approval", args.approval,
                "--output-dir", args.output_dir,
                "--as-of", args.as_of,
            ]
            if getattr(args, "json", False):
                gsc_args.append("--json")
            return gsc_main(gsc_args)
        elif args.agent_command == "readiness-envelope":
            return args.func(args)
        elif args.agent_command == "operator-approval-gate":
            return args.func(args)
        elif args.agent_command == "bounded-live-readiness":
            return args.func(args)
        elif args.agent_command == "run":
            if getattr(args, "offline", False):
                config.model.provider = "null"
                config.model.model = "null"
            _check_discipline_or_exit(config)
            resolved_symbol = _resolve_symbol(config, getattr(args, "symbol", None))
            result = run_agent(
                mode=args.mode,
                config=config,
                continuous=args.continuous,
                interval=args.interval,
                max_cycles=args.max_cycles,
                symbol=resolved_symbol,
            )
            if not result:
                return 0
            if result.lock_status:
                print(result.lock_status)
            print(f"agent run {args.mode}: {result.status}")
            print(f"Report: {result.report_path}")
            if result.order_status:
                print(f"Order status: {result.order_status}")
            print(f"Notification: {result.notification_status}")
            print(f"Git: {result.git_status}")
            return 0

    if args.command == "skills":
        from atlas_agent.cli_commands.skills import handle_skills

        _handled = handle_skills(context)
        if _handled is not None:
            return _handled

    if args.command == "user":
        from atlas_agent.cli_commands.user import handle_user

        _handled = handle_user(context)
        if _handled is not None:
            return _handled

    if args.command == "learning":
        from atlas_agent.cli_commands.learning import handle_learning

        _handled = handle_learning(context)
        if _handled is not None:
            return _handled

    if args.command == "discipline":
        from atlas_agent.cli_commands.discipline import handle_discipline

        _handled = handle_discipline(context)
        if _handled is not None:
            return _handled

    if args.command == "telegram":
        from atlas_agent.cli_commands.telegram import handle_telegram

        _handled = handle_telegram(context)
        if _handled is not None:
            return _handled

    if args.command == "replay":
        from atlas_agent.cli_commands.replay import handle_replay

        _handled = handle_replay(context)
        if _handled is not None:
            return _handled

    if args.command == "routine":
        from atlas_agent.cli_commands.routine import handle_routine

        _handled = handle_routine(context)
        if _handled is not None:
            return _handled
    if args.command == "scheduler":
        from atlas_agent.cli_commands.scheduler import handle_scheduler

        _handled = handle_scheduler(context)
        if _handled is not None:
            return _handled
    if args.command == "report":
        from atlas_agent.cli_commands.report import handle_report

        _handled = handle_report(context)
        if _handled is not None:
            return _handled
    if args.command == "portfolio":
        from atlas_agent.cli_commands.portfolio import handle_portfolio

        _handled = handle_portfolio(context)
        if _handled is not None:
            return _handled
    if args.command == "kill-switch":
        controller = _kill_switch_controller(config)
        if args.kill_command == "enable":
            mode = args.mode
            runtime_config = _effective_config_with_runtime_kill_switch(config)
            broker = _broker_for_mode(
                runtime_config.trading_mode,
                runtime_config,
                PortfolioState(cash=runtime_config.starting_cash),
                AuditLogger(runtime_config.audit_dir),
            )
            transition = controller.enable(
                mode=mode,
                reason=args.reason,
                actor="cli",
                broker=broker,
            )
            print(
                "Kill switch enabled:"
                f" changed={transition.changed}"
                f" mode={transition.state.mode}"
                f" reason={transition.state.reason or 'n/a'}"
            )
            if transition.cancel_results:
                print(f"Cancel results: {len(transition.cancel_results)}")
            if transition.flatten_result is not None:
                print(
                    "Flatten result: "
                    f"{transition.flatten_result.status} "
                    f"(closed={transition.flatten_result.closed}, "
                    f"failed={transition.flatten_result.failed})"
                )
            return 0
        if args.kill_command == "disable":
            state = controller.status()
            requires_totp = _requires_kill_switch_totp(
                state_mode=state.mode if state.enabled else "soft",
                explicit_2fa=bool(args.require_2fa),
            )
            if requires_totp:
                ok, error = _verify_totp_for_kill_switch(args.totp)
                if not ok:
                    print(f"Kill switch disable refused: {error}")
                    return 2
            transition = controller.disable(reason=args.reason, actor="cli")
            print(
                "Kill switch disabled:"
                f" changed={transition.changed}"
                f" mode={transition.state.mode}"
            )
            return 0
        if args.kill_command == "status":
            state = controller.status()
            print("Kill switch status")
            print(f"enabled={state.enabled}")
            print(f"mode={state.mode}")
            print(f"reason={state.reason or 'n/a'}")
            print(f"actor={state.actor}")
            print(f"updated_at={state.updated_at or 'n/a'}")
            print(f"activated_at={state.activated_at or 'n/a'}")
            print(f"deactivated_at={state.deactivated_at or 'n/a'}")
            return 0
    if args.command == "heartbeat":
        path = _heartbeat_path_for_config(config)
        write_deadman_heartbeat(path, source=args.source, actor=args.actor)
        print(f"Heartbeat recorded: {path}")
        return 0
    if args.command == "approve-order":
        import json

        from atlas_agent.execution.approval import InvalidApprovalIdError, InvalidPendingOrderError

        try:
            path = ApprovalManager(config.pending_orders_dir).approve(args.order_id)
        except InvalidApprovalIdError:
            print("Invalid pending order id.")
            return 2
        except (InvalidPendingOrderError, json.JSONDecodeError):
            print("Pending order file is invalid or corrupted.")
            return 2
        except FileNotFoundError:
            print("Pending order not found.")
            return 2
        print(f"Approved pending order: {path}")
        return 0
    if args.command == "submit-approved-order":
        # --dry-run and --reconcile are mutually exclusive
        if args.dry_run and args.reconcile:
            if args.json:
                return emit_cli_error(
                    "atlas submit-approved-order",
                    code="invalid_args",
                    message="--dry-run and --reconcile are mutually exclusive.",
                )
            print("--dry-run and --reconcile are mutually exclusive.")
            return 2

        if args.reconcile:
            from atlas_agent.execution.approval import InvalidApprovalIdError, InvalidPendingOrderError
            from atlas_agent.execution.submit_reconcile import run_reconcile

            try:
                report = run_reconcile(
                    order_id=args.order_id,
                    config=config,
                    approval_manager=ApprovalManager(config.pending_orders_dir),
                )
            except InvalidApprovalIdError:
                if args.json:
                    return emit_cli_error(
                        "atlas submit-approved-order --reconcile",
                        code="invalid_order_id",
                        message="Invalid pending order id.",
                    )
                print("Invalid pending order id.")
                return 2
            except InvalidPendingOrderError:
                if args.json:
                    return emit_cli_error(
                        "atlas submit-approved-order --reconcile",
                        code="invalid_pending_order",
                        message="Pending order file is invalid or corrupted.",
                    )
                print("Pending order file is invalid or corrupted.")
                return 2
            except FileNotFoundError:
                if args.json:
                    return emit_cli_error(
                        "atlas submit-approved-order --reconcile",
                        code="pending_order_not_found",
                        message="Pending order not found.",
                    )
                print("Pending order not found.")
                return 2
            except Exception:
                if args.json:
                    return emit_cli_error(
                        "atlas submit-approved-order --reconcile",
                        code="reconcile_failed",
                        message="Reconciliation failed. Manual review required.",
                    )
                print("Reconciliation failed. Manual review required.")
                return 2

            if args.json:
                payload = report.to_dict()
                if report.ok:
                    return emit_cli_success("atlas submit-approved-order --reconcile", payload)
                return emit_cli_error(
                    "atlas submit-approved-order --reconcile",
                    code="reconcile_blocked",
                    message=report.message,
                )

            print("Reconcile Report")
            print(f"Order: {report.order_id}")
            print(f"Status: {report.status}")
            if report.broker_order_id:
                print(f"Broker order: {report.broker_order_id}")
            print(report.message)
            return 0 if report.ok else 2

        if args.dry_run:
            from atlas_agent.execution.approval import InvalidApprovalIdError, InvalidPendingOrderError
            from atlas_agent.execution.submit_dry_run import run_submit_dry_run

            try:
                report = run_submit_dry_run(
                    order_id=args.order_id,
                    config=config,
                    approval_manager=ApprovalManager(config.pending_orders_dir),
                )
            except InvalidApprovalIdError:
                if args.json:
                    return emit_cli_error(
                        "atlas submit-approved-order --dry-run",
                        code="invalid_order_id",
                        message="Invalid pending order id.",
                    )
                print("Invalid pending order id.")
                return 2
            except InvalidPendingOrderError:
                if args.json:
                    return emit_cli_error(
                        "atlas submit-approved-order --dry-run",
                        code="invalid_pending_order",
                        message="Pending order file is invalid or corrupted.",
                    )
                print("Pending order file is invalid or corrupted.")
                return 2
            except FileNotFoundError:
                if args.json:
                    return emit_cli_error(
                        "atlas submit-approved-order --dry-run",
                        code="pending_order_not_found",
                        message="Pending order not found.",
                    )
                print("Pending order not found.")
                return 2
            except Exception:
                if args.json:
                    return emit_cli_error(
                        "atlas submit-approved-order --dry-run",
                        code="dry_run_failed",
                        message="Dry-run failed. Manual review required.",
                    )
                print("Dry-run failed. Manual review required.")
                return 2

            if args.json:
                payload = report.to_dict()
                if report.ok:
                    return emit_cli_success("atlas submit-approved-order --dry-run", payload)
                return emit_cli_error(
                    "atlas submit-approved-order --dry-run",
                    code="dry_run_blocked",
                    message=report.message,
                    details={
                        "gates": report.gates,
                        "blocked_reason": report.blocked_reason,
                    },
                )

            if report.blocked_reason == "invalid order id":
                print("Invalid pending order id.")
                return 2

            print("Submit Dry-Run Report")
            print(f"Order: {report.order_id}")
            print(f"Status: {report.status}")
            for gate, result in report.gates.items():
                print(f"  {gate}: {result}")
            if report.warnings:
                print("Warnings:")
                for w in report.warnings:
                    print(f"  - {w}")
            print(report.message)
            return 0 if report.ok else 2

        # Execution skeleton (no flags)
        from atlas_agent.execution.approval import InvalidApprovalIdError, InvalidPendingOrderError
        from atlas_agent.execution.submit_execution import run_submit_execution

        audit_writer = None
        try:
            from atlas_agent.audit import AuditWriter
            audit_writer = AuditWriter(config.audit_dir / "audit.log")
        except (ImportError, AttributeError):
            pass

        try:
            report = run_submit_execution(
                order_id=args.order_id,
                config=config,
                approval_manager=ApprovalManager(config.pending_orders_dir),
                audit_writer=audit_writer,
            )
        except InvalidApprovalIdError:
            if args.json:
                return emit_cli_error(
                    "atlas submit-approved-order",
                    code="invalid_order_id",
                    message="Invalid pending order id.",
                )
            print("Invalid pending order id.")
            return 2
        except InvalidPendingOrderError:
            if args.json:
                return emit_cli_error(
                    "atlas submit-approved-order",
                    code="invalid_pending_order",
                    message="Pending order file is invalid or corrupted.",
                )
            print("Pending order file is invalid or corrupted.")
            return 2
        except FileNotFoundError:
            if args.json:
                return emit_cli_error(
                    "atlas submit-approved-order",
                    code="pending_order_not_found",
                    message="Pending order not found.",
                )
            print("Pending order not found.")
            return 2
        except Exception:
            if args.json:
                return emit_cli_error(
                    "atlas submit-approved-order",
                    code="submit_failed",
                    message="Submit failed. Manual review required.",
                )
            print("Submit failed. Manual review required.")
            return 2

        if args.json:
            payload = report.to_dict()
            if report.ok:
                return emit_cli_success("atlas submit-approved-order", payload)
            return emit_cli_error(
                "atlas submit-approved-order",
                code="submit_blocked",
                message=report.message,
                details={
                    "gates": report.gates,
                    "blocked_reason": report.blocked_reason,
                },
            )

        print("Submit Execution Report")
        print(f"Order: {report.order_id}")
        print(f"Status: {report.status}")
        if report.blocked_reason:
            print(f"Blocked reason: {report.blocked_reason}")
        for gate, result in report.gates.items():
            print(f"  {gate}: {result}")
        if report.warnings:
            print("Warnings:")
            for w in report.warnings:
                print(f"  - {w}")
        print(report.message)
        return 0 if report.ok else 2

    if args.command == "research":
        from atlas_agent.cli_commands.research import dispatch_research

        _handled = dispatch_research(context)
        if _handled is not None:
            return _handled
    if args.command == "notify":
        from atlas_agent.cli_commands.notify import handle_notify

        _handled = handle_notify(context)
        if _handled is not None:
            return _handled

    if args.command == "notifications":
        from atlas_agent.cli_commands.notifications import handle_notifications

        _handled = handle_notifications(context)
        if _handled is not None:
            return _handled

    if args.command == "git-sync":
        from atlas_agent.cli_commands.git_sync import handle_git_sync

        _handled = handle_git_sync(context)
        if _handled is not None:
            return _handled
    if args.command == "schedule":
        from atlas_agent.cli_commands.schedule import handle_schedule

        _handled = handle_schedule(context)
        if _handled is not None:
            return _handled
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
