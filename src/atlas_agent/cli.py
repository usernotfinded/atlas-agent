from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    render_empty_json_report,
    render_empty_markdown_report,
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
from atlas_agent.brokers.alpaca import AlpacaBroker
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.brokers.binance import BinanceBroker
from atlas_agent.brokers.ccxt_adapter import CCXTBroker
from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.cli_commands import build_core_command_registry
from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_io import display_path, emit_cli_error, emit_cli_success, redact_cli_text
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
from atlas_agent.reports.daily import generate_daily_report
from atlas_agent.reports.generator import generate_report
from atlas_agent.reports.renderers import render_json_string, render_markdown
from atlas_agent.reports.weekly import generate_weekly_report
from atlas_agent.research import (
    get_research_provider,
    ResearchConfigurationError,
)
from atlas_agent.research.command_specs import (
    CONFIGLESS_RESEARCH_COMMANDS,
    RESEARCH_COMMAND_ALIAS_MAP,
    add_research_subparsers,
)
from atlas_agent.research.errors import safe_research_session_error
from atlas_agent.risk.manager import RiskManager
from atlas_agent.routines.engine import ROUTINE_NAMES, run_routine
from atlas_agent.routines.git_sync import GitSync, GitSyncError
from atlas_agent.routines.lock import (
    RoutineLockError,
    routine_status,
    unlock_routine,
)
from atlas_agent.scheduler.github_actions import write_github_actions_workflow
from atlas_agent.scheduler.runner import VALID_ROUTINES, run_scheduler_once
from atlas_agent.notifications.clickup import (
    ClickUpNotifier,
    NotificationConfigurationError,
)
from atlas_agent.output import emit_json, error_envelope, success_envelope
from atlas_agent.replay import replay_from_path, replay_last_run
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
    clear_default_workspace,
    get_default_workspace,
    is_workspace,
    resolve_workspace,
    set_default_workspace,
)


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


def _broker_for_mode(
    mode: str,
    config: AtlasConfig,
    portfolio: PortfolioState,
    audit: AuditLogger,
):
    from atlas_agent.brokers.resolver import BrokerResolver

    resolver = BrokerResolver(config)
    resolution = resolver.resolve_execution_broker(mode)

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
    from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot

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


def _requires_kill_switch_totp(
    *,
    state_mode: str,
    explicit_2fa: bool,
) -> bool:
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


def _check_discipline_or_exit(config: AtlasConfig) -> None:
    """Exit with an error if the user discipline profile is missing or invalid."""
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


def _print_first_run_onboarding(
    *,
    config: AtlasConfig | None,
    config_error: str | None,
    resolution: WorkspaceResolution,
) -> None:
    from atlas_agent.brokers.resolver import BrokerResolver

    _print_welcome()
    workspace_configured = resolution.path is not None
    provider_configured = _provider_configured(resolution.path)

    if config_error:
        trading_mode = "not configured"
        live_enabled = "no"
        broker_mode = "not configured"
    elif config is not None:
        trading_mode = config.trading_mode
        live_enabled = "yes" if config.enable_live_trading else "no"
        broker_mode = config.live_broker if config.live_broker not in {"", "none"} else "paper"
    else:
        trading_mode = "not configured"
        live_enabled = "no"
        broker_mode = "not configured"

    live_status = BrokerResolver(config).resolve_status("live")
    live_creds = live_status.credentials_configured

    print("Current setup status:")
    print(f"- workspace configured: {'yes' if workspace_configured else 'no'}")
    print(f"- provider configured: {'yes' if provider_configured else 'no'}")
    print(f"- broker mode: {broker_mode}")
    print(f"- live broker credentials: {'configured' if live_creds else 'not configured'}")
    print(f"- live trading enabled: {live_enabled}")
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


def main(argv: list[str] | None = None) -> int:
    import json

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        raise

    # Normalize research command aliases so handlers receive canonical names.
    _research_cmd = getattr(args, "research_command", None)
    if _research_cmd in RESEARCH_COMMAND_ALIAS_MAP:
        args.research_command = RESEARCH_COMMAND_ALIAS_MAP[_research_cmd]

    if args.command == "config":
        from atlas_agent.config import (
            get_config, get_raw_config, get_raw_value, set_raw_value, unset_raw_value,
            get_secret, get_secret_status, set_secret, unset_secret, is_secret_key,
            migrate_legacy_config, redact_value
        )
        from atlas_agent.config.secrets import InvalidSecretValueError, canonical_env_var
        from atlas_agent.config.paths import get_config_toml_path, get_env_atlas_path
        import json

        if args.config_command == "paths":
            print(f"Config TOML: {get_config_toml_path()}")
            print(f"Secrets ENV: {get_env_atlas_path()}")
            return 0

        if args.config_command == "show":
            if getattr(args, "effective", False):
                try:
                    config = get_config()
                except AtlasConfigError as exc:
                    return _emit_config_error(exc)
                payload = config.model_dump(mode="json")
                def redact_secrets_in_dict(d):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            redact_secrets_in_dict(v)
                        elif isinstance(k, str) and is_secret_key(k):
                            d[k] = "[REDACTED]"
                redact_secrets_in_dict(payload)
                print(json.dumps(payload, indent=2))
            else:
                try:
                    raw = get_raw_config()
                except AtlasConfigError as exc:
                    return _emit_config_error(exc)
                import tomlkit
                def redact_recursive(d):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            redact_recursive(v)
                        elif isinstance(k, str) and is_secret_key(k):
                            d[k] = "[REDACTED]"
                redacted_raw = tomlkit.parse(tomlkit.dumps(raw))
                redact_recursive(redacted_raw)
                print(tomlkit.dumps(redacted_raw))
            return 0

        if args.config_command == "get":
            if is_secret_key(args.key):
                env_var = canonical_env_var(args.key)
                print(get_secret_status(env_var))
                return 0

            if getattr(args, "effective", False):
                try:
                    config = get_config()
                except AtlasConfigError as exc:
                    return _emit_config_error(exc)
                val = config.model_dump(mode="json")
                try:
                    for p in args.key.split("."):
                        val = val[p]
                    print(val)
                except (KeyError, TypeError):
                    print(f"Key not found: {args.key}")
                    return 1
            else:
                val = get_raw_value(args.key)
                if val is None:
                    print(f"Key not found: {args.key}")
                    return 1
                print(val)
            return 0

        if args.config_command == "set":
            if args.key == "model.default":
                args.key = "model.model"
            if is_secret_key(args.key):
                env_var = canonical_env_var(args.key)
                try:
                    set_secret(env_var, args.value)
                except InvalidSecretValueError as exc:
                    print(str(exc))
                    return 2
                print(f"Updated secret {env_var} in .env.atlas")
            else:
                set_raw_value(args.key, args.value)
                print(f"Updated {args.key} in config.toml")
            return 0

        if args.config_command == "unset":
            if is_secret_key(args.key):
                env_var = canonical_env_var(args.key)
                unset_secret(env_var)
                print(f"Unset secret {env_var}")
            else:
                unset_raw_value(args.key)
                print(f"Unset {args.key}")
            return 0

        if args.config_command == "migrate":
            if migrate_legacy_config():
                print("Successfully migrated legacy config.")
            else:
                print("No legacy config found or migration failed.")
            return 0

        if args.config_command == "doctor":
            from atlas_agent.providers.catalog import get_provider_profile, normalize_provider_id
            from atlas_agent.providers.runtime import resolve_runtime_provider
            try:
                config = get_config()
            except AtlasConfigError as exc:
                return _emit_config_error(exc)
            canonical = normalize_provider_id(config.model.provider or "")
            profile = get_provider_profile(canonical)
            runtime = resolve_runtime_provider(config)
            print("Config Doctor")
            print(f"provider: {config.model.provider}")
            print(f"model: {config.model.model}")

            if profile is None:
                print(f"API key: unknown provider '{canonical}'")
            elif not profile.key_required:
                print("API key: not required for this provider")
            else:
                key_source = runtime["api_key_source"]
                env_var_used = runtime["api_key_env_var_used"]
                if key_source in ("process_env", "env_atlas"):
                    print(f"API key: configured/redacted ({env_var_used})")
                else:
                    expected_vars = ", ".join(profile.env_precedence)
                    print(f"API key: missing (expected: {expected_vars})")

                # Warn about ignored keys from other providers
                other_keys_found = []
                for other_p in (get_provider_profile(p) for p in ["openrouter", "anthropic", "openai", "deepseek"]):
                    if other_p and other_p.id != canonical:
                        for var in other_p.env_precedence:
                            if os.getenv(var):
                                other_keys_found.append(var)
                if other_keys_found:
                    print(f"Note: other provider keys detected but ignored: {', '.join(other_keys_found)}")

                # Gemini-specific warning
                if canonical == "google" and runtime.get("warnings"):
                    for w in runtime["warnings"]:
                        print(f"Warning: {w}")

            print(f"live trading {'enabled' if config.enable_live_trading else 'disabled unless explicitly enabled'}")
            print(f"raw prompt logging: {'enabled (redacted)' if config.audit.log_raw_prompts else 'disabled'}")
            print(f"provider text logging: {'enabled (redacted)' if config.audit.log_provider_text else 'disabled'}")
            return 0

        if args.config_command == "edit":
            path = get_config_toml_path()
            editor = os.getenv("EDITOR", "vim")
            subprocess.run(shlex.split(editor) + [str(path)], check=False)
            return 0

        if args.config_command == "check":
            try:
                config = get_config()
                payload = config.model_dump(mode="json")
                def redact_secrets_in_dict(d):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            redact_secrets_in_dict(v)
                        elif isinstance(k, str) and is_secret_key(k):
                            d[k] = "[REDACTED]"
                redact_secrets_in_dict(payload)
            except AtlasConfigError:
                if getattr(args, "json", False):
                    return emit_cli_error(
                        "atlas config check",
                        code="config_load_failed",
                        message="Configuration check failed.",
                    )
                return _emit_config_error(None)
            except Exception:
                if getattr(args, "json", False):
                    return emit_cli_error(
                        "atlas config check",
                        code="config_check_failed",
                        message="Configuration check failed.",
                    )
                print("Configuration check failed.", file=sys.stderr)
                return 1
            if getattr(args, "json", False):
                return emit_cli_success("atlas config check", payload)
            print("Config is valid.")
            return 0

    if args.command == "model":
        from atlas_agent.config import get_config, set_raw_value
        from atlas_agent.providers.catalog import (
            infer_google_api_mode,
            list_provider_profiles,
            get_provider_profile,
            normalize_provider_id,
            is_known_model_for_provider,
            provider_allows_custom_model,
            validate_model_for_provider,
        )
        from atlas_agent.providers.runtime import resolve_runtime_provider
        from atlas_agent.config.secrets import InvalidSecretValueError, set_secret
        try:
            config = get_config()
        except AtlasConfigError as exc:
            return _emit_config_error(exc)

        if args.model_command == "providers":
            for profile in list_provider_profiles():
                if not profile.include_in_model_providers_default:
                    continue
                runtime = resolve_runtime_provider(config, profile.id)
                key_status = runtime["api_key_source"]
                if runtime.get("auth_method") == "oauth_adc":
                    key_label = "oauth/adc" if runtime.get("credential_source") != "missing" else "oauth missing"
                elif key_status == "missing" and profile.auth_header_type != "none" and profile.key_required:
                    key_label = "missing"
                elif key_status in ("process_env", "env_atlas"):
                    key_label = "configured"
                else:
                    key_label = "not required"
                print(f"{profile.id:15s}  {profile.label:25s}  key: {key_label:12s}  default: {profile.default_model}")

            if getattr(args, "include_legacy", False):
                print(f"{'local_command':15s}  {'Local command (legacy)':25s}  key: {'not required':12s}  default: {'local_command'}")

            if getattr(args, "include_internal", False):
                print(f"{'null':15s}  {'Null provider / dry-run':25s}  key: {'not required':12s}  default: {'null'}")
            return 0
        if args.model_command == "list":
            provider_filter = getattr(args, "provider", None)
            if provider_filter:
                profile = get_provider_profile(provider_filter)
                if not profile:
                    print(f"Unknown provider: {provider_filter}")
                    return 2
                profiles = [profile]
            else:
                profiles = list_provider_profiles()
            for profile in profiles:
                print(f"{profile.label} ({profile.id})")
                for m in profile.models:
                    rec = "  *" if m.recommended else ""
                    print(f"  {m.id:40s}{rec}")
                if profile.allow_custom_model:
                    print("  Custom model IDs allowed.")
            return 0

        if args.model_command == "current":
            runtime = resolve_runtime_provider(config)
            print(f"provider: {runtime.get('provider_label', runtime['provider'])}")
            print(f"provider_id: {runtime['provider']}")
            print(f"model:    {runtime['model']}")
            print(f"mode:     {runtime.get('mode_label', runtime['api_mode'])}")
            print(f"api_mode: {runtime['api_mode']}")
            print(f"base_url: {runtime['base_url'] or '(default)'}")
            key_source = runtime["api_key_source"]
            env_var = runtime["api_key_env_var_used"]
            if runtime.get("auth_method") == "oauth_adc":
                if runtime.get("credential_source") != "missing":
                    print(f"auth:     OAuth/ADC configured ({runtime['credential_source']})")
                else:
                    print("auth:     OAuth/ADC missing")
            else:
                if key_source == "process_env":
                    print(f"auth:     API key configured ({env_var} from process env)")
                elif key_source == "env_atlas":
                    print(f"auth:     API key configured ({env_var} from .env.atlas)")
                elif key_source == "none":
                    print("auth:     not required")
                else:
                    print("auth:     API key missing")
            for err in runtime.get("errors", []):
                print(f"error:    {err}")
            if runtime.get("warnings"):
                for w in runtime["warnings"]:
                    print(f"warning:  {w}")
            return 0

        if args.model_command == "set":
            # Two-arg form: atlas model set <provider> <model>
            if args.model is not None:
                raw_provider_input = args.model_id.strip()
                provider_id = normalize_provider_id(raw_provider_input)
                model_id = args.model.strip()
            else:
                raw = args.model_id.strip()
                raw_provider_input = ""
                # Support "openrouter:openai/gpt-5.5" or single-argument syntax
                if ":" in raw and "/" in raw:
                    provider_part, model_part = raw.split(":", 1)
                    raw_provider_input = provider_part
                    provider_id = normalize_provider_id(provider_part)
                    model_id = model_part
                elif "/" in raw:
                    provider_part, model_part = raw.split("/", 1)
                    raw_provider_input = provider_part
                    provider_id = normalize_provider_id(provider_part)
                    model_id = raw  # Keep full ID for openrouter-style models
                    # For non-openrouter providers, use just the model_part
                    profile = get_provider_profile(provider_id)
                    if profile and profile.id != "openrouter":
                        model_id = model_part
                else:
                    # No provider prefix; use current provider
                    raw_provider_input = config.model.provider or "openai"
                    provider_id = normalize_provider_id(config.model.provider or "openai")
                    model_id = raw

            profile = get_provider_profile(provider_id)
            if not profile:
                print(f"Warning: unknown provider '{provider_id}'.")
            else:
                provider_id = profile.id  # canonical
                valid_pair, validation_error = validate_model_for_provider(provider_id, model_id)
                if not valid_pair:
                    print(f"Error: {validation_error}")
                    return 2
                if (
                    not provider_allows_custom_model(provider_id)
                    and not is_known_model_for_provider(provider_id, model_id)
                ):
                    print(f"Warning: '{model_id}' is not in the curated catalog for {provider_id}.")
                    print("Proceeding because this may be a newer model ID.")

            set_raw_value("model.provider", provider_id)
            set_raw_value("model.model", model_id)
            if provider_id == "google":
                inferred_google_mode = infer_google_api_mode(raw_provider_input)
                if inferred_google_mode:
                    set_raw_value("model.google.api_mode", inferred_google_mode)
            print(f"Model set to {provider_id}/{model_id}")
            return 0

        if args.model_command == "configure":
            profiles = list_provider_profiles()
            print("Select a provider:")
            for i, profile in enumerate(profiles, 1):
                print(f"  {i}. {profile.label} ({profile.id})")
            try:
                choice = input("Enter number (or provider id): ").strip()
            except (EOFError, OSError):
                print("Non-interactive mode. Use `atlas model set <provider>/<model>` instead.")
                return 2
            # Allow entering provider id directly
            profile = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(profiles):
                    profile = profiles[idx]
            if not profile:
                profile = get_provider_profile(choice)
            if not profile:
                print(f"Unknown provider: {choice}")
                return 2

            # Prompt for API key if needed and missing
            if profile.key_required:
                runtime = resolve_runtime_provider(config, profile.id)
                if runtime["api_key_source"] in ("missing", ""):
                    print(f"{profile.label} requires an API key.")
                    env_var = profile.canonical_env_var if profile.canonical_env_var else f"{profile.id.upper()}_API_KEY"
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", getpass.GetPassWarning)
                            key = getpass.getpass(f"Enter {env_var}: ").strip()
                    except getpass.GetPassWarning:
                        print("Secure hidden input is unavailable in this environment. Use `atlas config set_atlas_secret <key> <value>`.")
                        return 2
                    except (EOFError, OSError):
                        print("Non-interactive mode. Use `atlas config set_atlas_secret <key> <value>`.")
                        return 2
                    if key:
                        try:
                            set_secret(env_var, key)
                        except InvalidSecretValueError as exc:
                            print(str(exc))
                            return 2
                        print(f"Saved {env_var} to .env.atlas")

            # Select model
            print(f"Select a model for {profile.label}:")
            for i, m in enumerate(profile.models, 1):
                rec = "  *" if m.recommended else ""
                print(f"  {i}. {m.id:40s}{rec}")
            try:
                mchoice = input("Enter number (or model id, or press Enter for default): ").strip()
            except (EOFError, OSError):
                print("Non-interactive mode. Use `atlas model set <provider>/<model>`.")
                return 2
            model_id = profile.default_model
            if mchoice:
                if mchoice.isdigit():
                    idx = int(mchoice) - 1
                    if 0 <= idx < len(profile.models):
                        model_id = profile.models[idx].id
                else:
                    model_id = mchoice

            set_raw_value("model.provider", profile.id)
            set_raw_value("model.model", model_id)
            print(f"Configured {profile.id}/{model_id}")
            return 0

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

    dispatched = build_core_command_registry().dispatch(
        CLIContext(
            args=args,
            config=config,
            resolution=resolution,
            update_checker=_check_for_updates,
        )
    )
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
    if args.command == "providers" and args.providers_command == "list":
        print("openai_compatible, anthropic, openrouter")
        return 0

    if args.command == "providers" and args.providers_command == "capability-inventory":
        import json
        from atlas_agent.providers.provider_readiness import generate_capability_inventory
        try:
            inventory = generate_capability_inventory()
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                if not getattr(args, "json", False):
                    print(f"Generated capability inventory at {display_path(args.output)}")
            if getattr(args, "json", False):
                return emit_cli_success("atlas providers capability-inventory", {"inventory": inventory})
            elif not args.output:
                print(json.dumps(inventory, indent=2, sort_keys=True))
            return 0
        except Exception as e:
            if getattr(args, "json", False):
                return emit_cli_error("atlas providers capability-inventory", "capability_inventory_error", str(e))
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if args.command == "providers" and args.providers_command == "readiness-check":
        import json
        from atlas_agent.providers.provider_readiness import evaluate_provider_readiness
        from atlas_agent.providers.provider_preflight import PreflightValidationError
        try:
            report = evaluate_provider_readiness(
                provider_id=args.provider,
                model_id=args.model,
                purpose=args.purpose,
                max_context_chars=args.max_context_chars,
            )
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                if not getattr(args, "json", False):
                    print(f"Generated readiness report at {display_path(args.output)}")
            if getattr(args, "json", False):
                return emit_cli_success("atlas providers readiness-check", {"report": report})
            elif not args.output:
                print(json.dumps(report, indent=2, sort_keys=True))
            return 0
        except PreflightValidationError as exc:
            if getattr(args, "json", False):
                return emit_cli_error("atlas providers readiness-check", "preflight_validation_error", str(exc))
            print(f"Validation error: {exc}", file=sys.stderr)
            return 2
        except Exception as e:
            if getattr(args, "json", False):
                return emit_cli_error("atlas providers readiness-check", "readiness_check_error", str(e))
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if args.command == "providers" and args.providers_command == "evidence-index":
        if args.evidence_command == "build":
            from atlas_agent.providers.provider_evidence_index import build_provider_evidence_index
            try:
                index = build_provider_evidence_index(root=args.root, output=args.output)
                # Check for findings (invalid or unsafe artifacts)
                if index.get("findings"):
                    if getattr(args, "json", False):
                        return emit_cli_success("atlas providers evidence-index build", {"index": index, "status": "findings"})
                    print(f"Provider evidence index built but contains invalid artifacts.")
                    if args.output:
                        print(f"Index written to {display_path(args.output)}")
                    return 1
                else:
                    if getattr(args, "json", False):
                        return emit_cli_success("atlas providers evidence-index build", {"index": index, "status": "success"})
                    if args.output:
                        print(f"Provider evidence index written to {display_path(args.output)}")
                    return 0
            except Exception as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index build", "evidence_index_error", str(e))
                print(f"Provider evidence index build failed: {e}", file=sys.stderr)
                return 2
        elif args.evidence_command == "inspect":
            from atlas_agent.providers.provider_evidence_index import inspect_provider_evidence_index, EvidenceIndexError
            try:
                data = inspect_provider_evidence_index(args.index_path)
                if getattr(args, "json", False):
                    return emit_cli_success("atlas providers evidence-index inspect", {"index": data, "status": "valid"})
                print("Provider evidence index is valid.")
                return 0
            except EvidenceIndexError as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index inspect", "inspection_error", str(e))
                print(f"Provider evidence index inspection failed: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index inspect", "inspection_error", str(e))
                print(f"Provider evidence index inspection failed: {e}", file=sys.stderr)
                return 1
        elif args.evidence_command == "report":
            from atlas_agent.providers.provider_evidence_index import generate_provider_evidence_report, EvidenceIndexError
            try:
                result = generate_provider_evidence_report(args.index_path, output=args.output)
                is_valid = result.get("is_valid", False)
                if not is_valid:
                    if getattr(args, "json", False):
                        return emit_cli_success("atlas providers evidence-index report", {"report_generated": True, "status": "unsafe_or_invalid_index", "findings": result.get("error_message")})
                    print(f"Provider evidence report generated to {display_path(args.output)}, but index was invalid or unsafe.")
                    return 1
                if getattr(args, "json", False):
                    return emit_cli_success("atlas providers evidence-index report", {"report_generated": True, "status": "valid"})
                print(f"Provider evidence report written to {display_path(args.output)}")
                return 0
            except EvidenceIndexError as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index report", "report_generation_error", str(e))
                print(f"Provider evidence report generation failed: {e}", file=sys.stderr)
                return 2
            except Exception as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index report", "report_generation_error", str(e))
                print(f"Provider evidence report generation failed: {e}", file=sys.stderr)
                return 2
        elif args.evidence_command == "export-summary":
            from atlas_agent.providers.provider_evidence_index import export_provider_evidence_summary, EvidenceIndexError
            try:
                summary = export_provider_evidence_summary(args.index_path, output=args.output)
                is_valid = summary.get("valid", False)
                if not is_valid:
                    if getattr(args, "json", False):
                        return emit_cli_success("atlas providers evidence-index export-summary", {"summary_exported": True, "status": "unsafe_or_invalid_index"})
                    print(f"Provider evidence summary exported to {display_path(args.output)}, but index was invalid or unsafe.")
                    return 1
                if getattr(args, "json", False):
                    return emit_cli_success("atlas providers evidence-index export-summary", {"summary_exported": True, "status": "valid"})
                print(f"Provider evidence summary exported to {display_path(args.output)}")
                return 0
            except EvidenceIndexError as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index export-summary", "summary_export_error", str(e))
                print(f"Provider evidence summary export failed: {e}", file=sys.stderr)
                return 2
            except Exception as e:
                if getattr(args, "json", False):
                    return emit_cli_error("atlas providers evidence-index export-summary", "summary_export_error", str(e))
                print(f"Provider evidence summary export failed: {e}", file=sys.stderr)
                return 2

    if args.command == "providers" and args.providers_command == "validate-preflight":
        import json
        from atlas_agent.providers.provider_preflight import (
            validate_call_plan_artifact,
            PreflightValidationError,
        )
        artifact_path = Path(args.artifact_path)
        if not artifact_path.exists():
            print(f"File not found: {artifact_path}", file=sys.stderr)
            return 2
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas providers validate-preflight",
                    code="json_parse_error",
                    message=f"Invalid JSON: {exc}"
                )
            print(f"Invalid JSON: {exc}", file=sys.stderr)
            return 2

        try:
            validate_call_plan_artifact(artifact)
        except PreflightValidationError as exc:
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas providers validate-preflight",
                    code="preflight_validation_error",
                    message=str(exc)
                )
            print(f"Validation failed: {exc}", file=sys.stderr)
            return 1

        if getattr(args, "json", False):
            return emit_cli_success("atlas providers validate-preflight", {"valid": True})
        print("Artifact is valid and safe.")
        return 0

    if args.command == "providers" and args.providers_command == "preflight":
        import json
        from atlas_agent.providers.provider_preflight import (
            generate_call_plan_artifact,
            PreflightValidationError,
        )
        try:
            artifact = generate_call_plan_artifact(
                provider_id=args.provider,
                model_id=args.model,
                purpose=args.purpose,
                max_context_chars=args.max_context_chars,
            )
        except PreflightValidationError as exc:
            if getattr(args, "json", False):
                return emit_cli_error(
                    "atlas providers preflight",
                    code="preflight_validation_error",
                    message=str(exc)
                )
            print(f"Validation error: {exc}", file=sys.stderr)
            return 2

        if args.output:
            out_path = args.output
        else:
            now_for_path = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out_path = Path("artifacts/provider_preflight") / f"{now_for_path}-call-plan.json"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

        if getattr(args, "json", False):
            return emit_cli_success("atlas providers preflight", {"artifact_path": str(out_path)})

        print(f"Generated dry-run call-plan artifact at {display_path(out_path)}")
        return 0
    if args.command == "broker" and args.brokers_command == "list":
        print("paper, alpaca, binance, ccxt, ibkr_stub")
        return 0
    if args.command == "broker" and args.brokers_command == "status":
        from atlas_agent.brokers.resolver import BrokerResolver
        from atlas_agent.brokers.status import list_broker_support_inventory

        resolver = BrokerResolver(config)
        inventory = [
            {
                "support": entry.to_dict(),
                "runtime": resolver.resolve_status(
                    "paper" if entry.broker_id == "paper" else "live"
                ).to_dict()
                if entry.broker_id != "paper" or config is not None
                else resolver.resolve_status("paper").to_dict(),
            }
            for entry in list_broker_support_inventory()
        ]
        if getattr(args, "json", False):
            print(json.dumps({"inventory": inventory}, indent=2))
            return 0

        print("Broker Support Inventory")
        print("-" * 60)
        for item in inventory:
            support = item["support"]
            runtime = item["runtime"]
            print(f"{support['display_name']} ({support['broker_id']})")
            print(f"  Status             : {support['status']}")
            print(f"  Paper supported    : {support['paper_supported']}")
            print(f"  Read-only supported: {support['read_only_supported']}")
            print(f"  Live submit support: {support['live_submit_supported']}")
            print(f"  Requires opt-in    : {support['requires_explicit_opt_in']}")
            print(f"  Default enabled    : {support['default_enabled']}")
            print(f"  Runtime code       : {runtime['code']}")
            print(f"  Notes              : {support['notes']}")
            print()
        return 0
    if args.command == "broker" and args.brokers_command == "sync":
        from atlas_agent.brokers.resolver import BrokerResolver
        from atlas_agent.brokers.sync import BrokerSyncService
        from atlas_agent.brokers.models import BrokerSyncResult

        mode = getattr(args, "mode", "paper")
        resolver = BrokerResolver(config)
        resolution = resolver.resolve_sync_provider(mode)

        if resolution.sync_provider is None:
            result = BrokerSyncResult(
                status="failed",
                errors=[resolution.status.message],
                diagnostics={"broker_status": resolution.status.to_dict()},
            )
        else:
            sync_service = BrokerSyncService(broker=resolution.sync_provider)
            result = sync_service.sync()

        if getattr(args, "json", False):
            print(result.model_dump_json(indent=2))
            return 0

        print(f"Broker Sync Result: {result.status.upper()}")
        print(f"  Synced At: {result.synced_at}")
        if result.account:
            print(f"  Account ID: {result.account.account_id}")
            print(f"  Live: {result.account.is_live}")
            print(f"  Cash: ${result.account.cash:,.2f}")
            print(f"  Equity: ${result.account.equity:,.2f}")
        print(f"  Positions: {len(result.positions)}")
        print(f"  Open Orders: {len(result.open_orders)}")
        if result.errors:
            print("  Errors:")
            for err in result.errors:
                print(f"    - {err}")
        return 0 if result.status == "success" else 2
    if args.command == "broker" and args.brokers_command == "opt-in":
        return _cmd_broker_opt_in(args, config)
    if args.command == "broker" and args.brokers_command == "opt-out":
        return _cmd_broker_opt_out(args, config)
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
        from atlas_agent.dashboard.collectors import collect_dashboard_snapshot
        from atlas_agent.dashboard.render import render_dashboard_html, render_dashboard_markdown

        snapshot = collect_dashboard_snapshot(config, Path.cwd())

        if args.json:
            print(snapshot.model_dump_json(indent=2))
            return 0

        fmt = getattr(args, "format", "html")
        if fmt == "markdown":
            md = render_dashboard_markdown(snapshot)
            print(md)
            return 0

        dashboard_path = config.workspace_root / ".atlas" / "dashboard" / "index.html"
        render_dashboard_html(snapshot, dashboard_path)
        print(f"Dashboard generated: {dashboard_path}")

        if args.open:
            import webbrowser
            webbrowser.open(f"file://{dashboard_path.resolve()}")
        return 0

    if args.command == "reflection":
        from atlas_agent.reflection.generator import generate_reflection
        from atlas_agent.reflection.storage import save_artifact, load_artifact, list_artifacts
        from atlas_agent.reflection.approval import approve, reject, archive, submit_for_review
        from atlas_agent.reflection.renderers import render_markdown as _render_reflection_markdown

        if args.reflection_command == "create":
            input_path = getattr(args, "input", None)
            kind = getattr(args, "kind", None)
            output = getattr(args, "output", "stdout")
            use_json = getattr(args, "json", False)
            artifact = generate_reflection(
                input_path,
                kind=kind,
                workspace=".",
                dry_run=True,
            )
            save_artifact(artifact, workspace=".")
            if use_json:
                content = artifact.model_dump_json(indent=2)
            else:
                content = _render_reflection_markdown(artifact)
            if output == "stdout":
                print(content)
            else:
                out_path = Path(output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                print(f"Reflection written to: {out_path}")
            return 0

        if args.reflection_command == "list":
            status_filter = getattr(args, "status", None)
            use_json = getattr(args, "json", False)
            from atlas_agent.reflection.models import ReflectionStatus
            status = ReflectionStatus(status_filter) if status_filter else None
            artifacts = list_artifacts(workspace=".", status=status)
            if use_json:
                print(json.dumps(artifacts, indent=2, sort_keys=True, default=str))
            else:
                if not artifacts:
                    print("No reflection artifacts found.")
                    return 0
                print(f"{'ID':<36} {'Status':<16} {'Kind':<12} {'Generated'}")
                print("-" * 80)
                for a in artifacts:
                    print(f"{a['reflection_id']:<36} {a['status']:<16} {a['kind']:<12} {a['generated_at']}")
            return 0

        if args.reflection_command == "show":
            reflection_id = getattr(args, "reflection_id", None)
            use_json = getattr(args, "json", False)
            artifact = load_artifact(reflection_id, workspace=".")
            if use_json:
                print(artifact.model_dump_json(indent=2))
            else:
                print(_render_reflection_markdown(artifact))
            return 0

        if args.reflection_command == "submit":
            reflection_id = getattr(args, "reflection_id", None)
            artifact = load_artifact(reflection_id, workspace=".")
            submit_for_review(artifact, workspace=".")
            print(f"Reflection {reflection_id} submitted for review.")
            return 0

        if args.reflection_command == "approve":
            reflection_id = getattr(args, "reflection_id", None)
            reason = getattr(args, "reason", "")
            artifact = load_artifact(reflection_id, workspace=".")
            approve(artifact, reason=reason or None, workspace=".")
            print(f"Reflection {reflection_id} approved.")
            return 0

        if args.reflection_command == "reject":
            reflection_id = getattr(args, "reflection_id", None)
            reason = getattr(args, "reason", "")
            if not reason:
                print("Error: --reason is required for rejection.", file=sys.stderr)
                return 1
            artifact = load_artifact(reflection_id, workspace=".")
            reject(artifact, reason=reason, workspace=".")
            print(f"Reflection {reflection_id} rejected.")
            return 0

        if args.reflection_command == "archive":
            reflection_id = getattr(args, "reflection_id", None)
            reason = getattr(args, "reason", "")
            artifact = load_artifact(reflection_id, workspace=".")
            archive(artifact, reason=reason or None, workspace=".")
            print(f"Reflection {reflection_id} archived.")
            return 0

        print("Error: Use 'atlas reflection --help' for usage.")
        return 1

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
        from atlas_agent.skills import (
            archive_skill,
            approve_skill,
            diff_skill,
            improve_proposed_skills,
            list_skills,
            show_skill,
        )
        from atlas_agent.learning.skill_miner import mine_skills_from_journal, save_proposed_skill
        skills_dir = config.memory_dir.parent / "skills"

        if args.skills_command == "list":
            skills = list_skills(skills_dir)
            if getattr(args, "json", False):
                return emit_cli_success("atlas skills list", skills)
            for cat, files in skills.items():
                print(f"{cat.upper()}:")
                for f in files:
                    print(f"  - {f}")
            return 0
        elif args.skills_command == "propose" or args.skills_command == "create-from-journal":
            event_logger = EventLogger(config.events_dir)
            run_id = generate_run_id()
            proposed = mine_skills_from_journal(config.memory_dir)
            for s in proposed:
                path = save_proposed_skill(skills_dir, s)
                event_logger.write(
                    "skill_proposed",
                    run_id=run_id,
                    command=f"atlas skills {args.skills_command}",
                    mode="paper",
                    payload={"skill": path.name},
                )
                print(f"Proposed skill created: {path.name}")
            if not proposed:
                print("No new skills identified from journal.")
            return 0
        elif args.skills_command == "approve":
            try:
                path = approve_skill(skills_dir, args.skill_name)
                print(f"Skill approved and activated: {path}")
            except FileNotFoundError as exc:
                print(f"Error: {exc}")
                return 2
            return 0
        elif args.skills_command == "archive":
            try:
                path = archive_skill(skills_dir, args.skill_name)
                print(f"Skill archived: {path}")
            except FileNotFoundError as exc:
                print(f"Error: {exc}")
                return 2
            return 0
        elif args.skills_command == "improve":
            improved = improve_proposed_skills(skills_dir)
            if not improved:
                print("No proposed skills found to improve.")
                return 0
            event_logger = EventLogger(config.events_dir)
            run_id = generate_run_id()
            print("Improved proposed skill drafts; active skills unchanged:")
            for path in improved:
                event_logger.write(
                    "skill_improved",
                    run_id=run_id,
                    command="atlas skills improve",
                    mode="paper",
                    payload={"skill": path.name},
                )
                print(f"- {display_path(path)}")
            return 0
        elif args.skills_command == "show":
            try:
                skill = show_skill(skills_dir, args.skill_name)
            except FileNotFoundError as exc:
                print(f"Error: {exc}")
                return 2
            print(f"Skill: {args.skill_name}")
            print(f"Path: {skill['path']}")
            print(f"Status: {skill['status']}")
            metadata = skill["metadata"]
            if isinstance(metadata, dict):
                print("Metadata:")
                for key, value in metadata.items():
                    print(f"- {key}: {value}")
            return 0
        elif args.skills_command == "diff":
            try:
                lines = diff_skill(skills_dir, args.skill_name)
            except FileNotFoundError as exc:
                print(f"Error: {exc}")
                return 2
            if not lines:
                print("No differences between active and proposed skill versions.")
                return 0
            print("\n".join(lines))
            return 0

        # Skill candidate handlers
        if args.skills_command == "create-candidate":
            from atlas_agent.skills.generator import generate_candidate_from_input
            from atlas_agent.skills.storage import save_candidate
            from atlas_agent.skills.renderers import render_markdown as _render_skill_markdown

            input_path = getattr(args, "input", None)
            kind = getattr(args, "kind", None)
            use_json = getattr(args, "json", False)
            candidate = generate_candidate_from_input(
                input_path,
                kind=kind,
                workspace=str(config.workspace_root),
                dry_run=True,
            )
            save_candidate(candidate, workspace=str(config.workspace_root))
            if use_json:
                print(candidate.model_dump_json(indent=2))
            else:
                print(f"Skill candidate {candidate.candidate_id} created.")
            return 0

        if args.skills_command == "list-candidates":
            from atlas_agent.skills.models import SkillCandidateStatus
            from atlas_agent.skills.storage import list_candidates

            status_filter = getattr(args, "status", None)
            use_json = getattr(args, "json", False)
            status = SkillCandidateStatus(status_filter) if status_filter else None
            items = list_candidates(workspace=str(config.workspace_root), status=status)
            if use_json:
                print(json.dumps(items, indent=2, sort_keys=True, default=str))
            else:
                if not items:
                    print("No skill candidates found.")
                    return 0
                print(f"{'ID':<36} {'Status':<16} {'Kind':<12} {'Title'}")
                print("-" * 80)
                for item in items:
                    print(f"{item['candidate_id']:<36} {item['status']:<16} {item['kind']:<12} {item['title']}")
            return 0

        if args.skills_command == "show-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.renderers import render_markdown as _render_skill_markdown

            candidate_id = getattr(args, "candidate_id", None)
            use_json = getattr(args, "json", False)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            if use_json:
                print(candidate.model_dump_json(indent=2))
            else:
                print(_render_skill_markdown(candidate))
            return 0

        if args.skills_command == "submit-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import submit_for_review

            candidate_id = getattr(args, "candidate_id", None)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            submit_for_review(candidate, workspace=str(config.workspace_root))
            print(f"Skill candidate {candidate_id} submitted for review.")
            return 0

        if args.skills_command == "approve-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import approve

            candidate_id = getattr(args, "candidate_id", None)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            approve(candidate, reason=getattr(args, "reason", None), workspace=str(config.workspace_root))
            print(f"Skill candidate {candidate_id} approved.")
            return 0

        if args.skills_command == "reject-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import reject

            candidate_id = getattr(args, "candidate_id", None)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            reject(candidate, reason=getattr(args, "reason", None), workspace=str(config.workspace_root))
            print(f"Skill candidate {candidate_id} rejected.")
            return 0

        if args.skills_command == "archive-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import archive

            candidate_id = getattr(args, "candidate_id", None)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            archive(candidate, reason=getattr(args, "reason", None), workspace=str(config.workspace_root))
            print(f"Skill candidate {candidate_id} archived.")
            return 0

        if args.skills_command == "promote-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import promote_to_library

            candidate_id = getattr(args, "candidate_id", None)
            try:
                candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
                entry = promote_to_library(candidate, workspace=str(config.workspace_root))
                print(f"Skill candidate {candidate_id} promoted to library as skill {entry.skill_id}.")
            except (FileNotFoundError, ValueError) as exc:
                print(f"Error: {exc}")
                return 2
            return 0

        if args.skills_command == "list-library":
            from atlas_agent.skills.library import list_skills as _list_library_skills

            use_json = getattr(args, "json", False)
            items = _list_library_skills(workspace=str(config.workspace_root))
            if use_json:
                print(json.dumps(items, indent=2, sort_keys=True, default=str))
            else:
                if not items:
                    print("No skills in library.")
                    return 0
                print(f"{'ID':<36} {'Kind':<12} {'Title'}")
                print("-" * 60)
                for item in items:
                    print(f"{item['skill_id']:<36} {item['kind']:<12} {item['title']}")
            return 0

        if args.skills_command == "show-library":
            from atlas_agent.skills.library import load_skill
            from atlas_agent.skills.renderers import render_skill_markdown

            skill_id = getattr(args, "skill_id", None)
            use_json = getattr(args, "json", False)
            entry = load_skill(skill_id, workspace=str(config.workspace_root))
            if use_json:
                print(entry.model_dump_json(indent=2))
            else:
                print(render_skill_markdown(entry))
            return 0

    if args.command == "user":
        from atlas_agent.learning.user_model import (
            format_user_model_summary,
            remember_user_note,
        )

        if args.user_command == "show":
            print(redact_cli_text(format_user_model_summary(config.memory_dir)))
            return 0
        if args.user_command == "remember":
            path = remember_user_note(config.memory_dir, args.text)
            print(f"User memory updated: {path}")
            return 0
        if args.user_command == "forget":
            print("User forget is not automated yet. Edit memory/user_profile.md, memory/preferences.md, or memory/trading_style.md intentionally.")
            return 0
        if args.user_command == "update-from-reflection":
            print("User model update from reflection is handled during reviewed learning cycles.")
            return 0

    if args.command == "learning":
        from atlas_agent.learning.generator import (
            generate_suggestion_from_input,
            generate_suggestion_from_reflection,
            generate_suggestion_from_skill,
        )
        from atlas_agent.learning.storage import (
            save_suggestion,
            load_suggestion,
            list_suggestions,
        )
        from atlas_agent.learning.approval import (
            submit_for_review,
            accept,
            reject,
            archive,
        )
        from atlas_agent.learning.renderers import render_markdown as _render_learning_markdown, render_json_string as _render_learning_json

        workspace = str(config.workspace_root)

        if args.learning_command == "suggest":
            suggestion = generate_suggestion_from_input(
                args.input,
                kind=getattr(args, "kind", None),
                workspace=workspace,
                dry_run=getattr(args, "dry_run", True),
            )
            save_suggestion(suggestion, workspace=workspace)
            if getattr(args, "json", False):
                print(_render_learning_json(suggestion))
            else:
                print(f"Learning suggestion created: {suggestion.suggestion_id}")
            return 0

        if args.learning_command == "suggest-from-reflection":
            print("Use 'atlas learning suggest --input <reflection-path> --kind reflection' instead.")
            return 0

        if args.learning_command == "suggest-from-skill":
            print("Use 'atlas learning suggest --input <skill-path> --kind skill' instead.")
            return 0

        if args.learning_command == "list-suggestions":
            from atlas_agent.learning.models import SuggestionStatus
            status_filter = None
            status_arg = getattr(args, "status", None)
            if status_arg:
                status_filter = SuggestionStatus(status_arg)
            items = list_suggestions(workspace=workspace, status=status_filter)
            if getattr(args, "json", False):
                print(json.dumps(items, indent=2, sort_keys=True, default=str))
            else:
                if not items:
                    print("No learning suggestions found.")
                    return 0
                print(f"{'ID':<36} {'Status':<16} {'Kind':<12} {'Created'}")
                for item in items:
                    print(f"{item['suggestion_id']:<36} {item['status']:<16} {item['kind']:<12} {item['created_at']}")
            return 0

        if args.learning_command == "show-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            suggestion = load_suggestion(suggestion_id, workspace=workspace)
            if getattr(args, "json", False):
                print(_render_learning_json(suggestion))
            else:
                print(_render_learning_markdown(suggestion))
            return 0

        if args.learning_command == "submit-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            try:
                suggestion = load_suggestion(suggestion_id, workspace=workspace)
                submit_for_review(suggestion, workspace=workspace)
                print(f"Suggestion {suggestion_id} submitted for review.")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        if args.learning_command == "accept-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            reason = getattr(args, "reason", "")
            try:
                suggestion = load_suggestion(suggestion_id, workspace=workspace)
                accept(suggestion, reason=reason or None, workspace=workspace)
                print(f"Suggestion {suggestion_id} accepted.")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        if args.learning_command == "reject-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            reason = getattr(args, "reason", "")
            if not reason:
                print("Error: --reason is required for rejection.", file=sys.stderr)
                return 1
            try:
                suggestion = load_suggestion(suggestion_id, workspace=workspace)
                reject(suggestion, reason=reason, workspace=workspace)
                print(f"Suggestion {suggestion_id} rejected.")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        if args.learning_command == "archive-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            reason = getattr(args, "reason", "")
            try:
                suggestion = load_suggestion(suggestion_id, workspace=workspace)
                archive(suggestion, reason=reason or None, workspace=workspace)
                print(f"Suggestion {suggestion_id} archived.")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        print("Error: Use 'atlas learning --help' for usage.")
        return 1

    if args.command == "discipline":
        from atlas_agent.ai.discipline import (
            _DISCIPLINE_SECTIONS,
            _REQUIRED_SAFETY_SENTENCE,
            default_discipline_text,
            discipline_path,
            discipline_status,
            load_user_discipline,
            sanitize_discipline_text,
            validate_discipline_text,
            write_user_discipline,
        )

        if args.discipline_command == "show":
            user_text = load_user_discipline(".")
            if user_text:
                print(user_text)
            else:
                print("# No user discipline profile configured.")
                print("# Atlas will not run agentic workflows until one is set.")
                print()
                print("# Default template (non-operational, for reference only):")
                print(default_discipline_text())
            return 0
        if args.discipline_command == "validate":
            user_text = load_user_discipline(".")
            if not user_text:
                print("No user discipline file found.")
                return 0
            ok, errors = validate_discipline_text(user_text)
            if ok:
                print("Discipline profile is valid.")
                return 0
            print("Discipline profile has errors:")
            for err in errors:
                print(f"  - {err}")
            return 2
        if args.discipline_command == "set":
            raw_text = " ".join(args.text)

            content = sanitize_discipline_text(raw_text)
            # If the user provided a full profile with sections, use it as-is
            has_sections = sum(1 for s in _DISCIPLINE_SECTIONS if f"## {s}" in content)
            if has_sections < len(_DISCIPLINE_SECTIONS):
                # Wrap freeform text into a minimal valid profile
                content = (
                    "# Atlas User Discipline Profile\n\n"
                    "## Decision temperament\n\n"
                    f"{content}\n\n"
                    "## Reasoning style\n\n"
                    "Step-by-step and transparent. Explain assumptions and label uncertainties.\n\n"
                    "## Communication style\n\n"
                    "Concise, structured, and respectful.\n\n"
                    "## Risk posture\n\n"
                    "Conservative. Every proposed order must acknowledge risk limits.\n\n"
                    "## Uncertainty handling\n\n"
                    "Explicitly state confidence levels and missing information.\n\n"
                    "## No-trade bias\n\n"
                    "Default to no action unless the case is compelling.\n\n"
                    "## Forbidden overrides\n\n"
                    f"{_REQUIRED_SAFETY_SENTENCE}\n"
                )
            # Ensure required safety sentence is present
            if _REQUIRED_SAFETY_SENTENCE not in content:
                content = content + "\n\n## Forbidden overrides\n\n" + _REQUIRED_SAFETY_SENTENCE + "\n"
            ok, errors = validate_discipline_text(content)
            if not ok:
                print("Discipline profile has errors:")
                for err in errors:
                    print(f"  - {err}")
                return 2
            write_user_discipline(".", content)
            print(f"Discipline profile saved to {discipline_path('.')}")
            return 0
        if args.discipline_command == "generate":
            from atlas_agent.ai.discipline import build_discipline_generation_prompt

            # Print the generation prompt so the user can pipe it to their LLM
            print(build_discipline_generation_prompt("I want a cautious, evidence-based trading analyst."))
            return 0
        if args.discipline_command == "reset":
            path = discipline_path(".")
            if path.exists():
                path.unlink()
                print("User discipline profile removed.")
            else:
                print("No user discipline profile to reset.")
            return 0
        if args.discipline_command == "setup":
            path = discipline_path(".")
            if path.exists():
                print(f"Discipline profile already exists at {path}")
                print("Use `atlas discipline reset` first if you want to replace it.")
                return 1
            if args.manual:
                template = default_discipline_text()
                if not args.yes:
                    print("The following template will be written to .atlas/discipline.md:")
                    print("---")
                    print(template)
                    print("---")
                    try:
                        confirm = input("Confirm? [yes/no]: ").strip().lower()
                    except EOFError:
                        confirm = "no"
                    if confirm != "yes":
                        print("Setup cancelled.")
                        return 130
                write_user_discipline(".", template)
                print(f"Discipline profile created at {path}")
                return 0
            else:
                print("Run `atlas discipline setup --manual` to create from the default template.")
                print("Or use `atlas discipline set <text>` to provide your own.")
                print("Or use `atlas discipline generate` to produce a prompt for your LLM.")
                return 0
        if args.discipline_command == "doctor":
            status = discipline_status(".")
            print(f"Path: {status['path']}")
            print(f"Configured: {status['configured']}")
            print(f"Valid: {status['valid']}")
            if status["errors"]:
                print("Errors:")
                for err in status["errors"]:
                    print(f"  - {err}")
            return 0

    if args.command == "telegram":
        from atlas_agent.telegram_control import (
            TELEGRAM_COMMANDS,
            get_telegram_diagnostics,
            verify_resume_totp_from_env,
        )

        if args.telegram_command == "test":
            print(get_telegram_diagnostics().format())
            return 0
        if args.telegram_command == "kill":
            controller = _kill_switch_controller(config)
            runtime_config = _effective_config_with_runtime_kill_switch(config)
            broker = _broker_for_mode(
                runtime_config.trading_mode,
                runtime_config,
                PortfolioState(cash=runtime_config.starting_cash),
                AuditLogger(runtime_config.audit_dir),
            )
            transition = controller.enable(
                mode=args.mode,
                reason=args.reason,
                actor="telegram",
                broker=broker,
            )
            print(
                f"Telegram /kill applied: changed={transition.changed} "
                f"mode={transition.state.mode}"
            )
            return 0
        if args.telegram_command == "resume":
            controller = _kill_switch_controller(config)
            state = controller.status()
            if not verify_resume_totp_from_env(args.totp or ""):
                print("Telegram /resume refused: invalid or missing TOTP")
                return 2
            transition = controller.disable(reason=args.reason, actor="telegram")
            print(
                f"Telegram /resume applied: changed={transition.changed} "
                f"prev_mode={state.mode}"
            )
            return 0
        if args.telegram_command == "heartbeat":
            path = _heartbeat_path_for_config(config)
            write_deadman_heartbeat(path, source=args.source, actor=args.actor)
            print(f"Telegram heartbeat recorded: {path}")
            return 0
        if args.telegram_command == "run":
            print("Telegram control plane adapter is optional and stdlib-only in this package.")
            print(
                "Configure TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS, "
                "then wire polling/webhook in your deployment wrapper."
            )
            print("Commands: " + ", ".join(TELEGRAM_COMMANDS))
            return 0

    if args.command == "replay":
        summary = None
        if args.last:
            summary = replay_last_run(config.events_dir)
        elif args.target:
            summary = replay_from_path(args.target, config.events_dir)
        else:
            summary = replay_last_run(config.events_dir)
        if summary is None:
            print("No replay data available yet. Run `atlas agent run --once` first.")
            return 0
        _print_replay(summary)
        return 0

    if args.command == "routine" and args.routine_command == "run":
        _check_discipline_or_exit(config)
        resolved_symbol = _resolve_symbol(config, getattr(args, "symbol", None))
        event_logger = EventLogger(config.events_dir)
        run_id = generate_run_id()
        try:
            result = run_routine(
                args.name,
                mode=args.mode,
                config=config,
                order_runner=lambda **kwargs: run_once(
                    **kwargs,
                ),
                event_logger=event_logger,
                run_id=run_id,
                command=f"atlas routine run {args.name}",
                symbol=resolved_symbol,
            )
        except RoutineLockError as exc:
            print(f"routine refused: {exc}")
            return 2
        if result.lock_status:
            print(result.lock_status)
        print(f"routine {result.name} {result.mode}: {result.status}")
        print(f"Report: {result.report_path}")
        if result.order_status:
            print(f"Order status: {result.order_status}")
        print(f"Notification: {result.notification_status}")
        print(f"Git: {result.git_status}")
        return 0
    if args.command == "routine" and args.routine_command == "unlock":
        try:
            print(unlock_routine(config.memory_dir.parent))
        except RoutineLockError as exc:
            print(f"unlock refused: {exc}")
            return 2
        return 0
    if args.command == "routine" and args.routine_command == "status":
        try:
            print(routine_status(config.memory_dir.parent))
        except RoutineLockError as exc:
            print(f"routine lock error: {exc}")
            return 2
        return 0
    if args.command == "scheduler" and args.scheduler_command == "run":
        _check_discipline_or_exit(config)
        result = run_scheduler_once(
            routine=args.routine,
            mode=args.mode,
            config=config,
            run_once_func=run_once,
        )
        print(
            f"scheduler {result.routine} {result.mode}: "
            f"{result.order_result.status}"
        )
        return 0 if result.order_result.status in {"filled", "held", "pending_approval"} else 2
    if args.command == "report":
        if args.report_command == "daily":
            print(generate_daily_report())
            return 0
        if args.report_command == "generate":
            run_id = getattr(args, "run_id", None)
            report_type = getattr(args, "type", "daily")
            fmt = getattr(args, "format", "text")
            output = getattr(args, "output", "stdout")

            # Legacy backtest-specific report path
            if run_id:
                result_path = Path(".atlas/backtests") / run_id / "result.json"
                if not result_path.exists():
                    print(f"Error: No backtest result found for run_id '{run_id}'", file=sys.stderr)
                    return 1
                import json as _json
                data = _json.loads(result_path.read_text(encoding="utf-8"))
                from atlas_agent.backtest.models import BacktestResult as _BR
                loaded_result = _BR.model_validate(data)

                if fmt == "json":
                    content = json.dumps(render_json_report(loaded_result), indent=2, sort_keys=True, default=str)
                elif fmt == "markdown":
                    content = render_markdown_report(loaded_result)
                else:
                    content = render_markdown_report(loaded_result)

                if output == "stdout":
                    print(content)
                else:
                    out_path = Path(output)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(content, encoding="utf-8")
                    print(f"Report written to: {out_path}")
                return 0

            # New local report generator path
            report_data = generate_report(
                report_type,  # type: ignore[arg-type]
                workspace=".",
                output_format="json" if fmt == "json" else "markdown",
            )
            if fmt == "json":
                content = render_json_string(report_data)
            else:
                content = render_markdown(report_data)

            if output == "stdout":
                print(content)
            else:
                out_path = Path(output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                print(f"Report written to: {out_path}")
            return 0
        print("Error: Use 'atlas report --help' for usage.")
        return 1
    if args.command == "portfolio" and args.portfolio_command == "show":
        payload = _portfolio_payload(config)
        if getattr(args, "json", False):
            return emit_cli_success("atlas portfolio show", payload)
        print("Portfolio state is local. No live broker query is made by this command.")
        print(f"Workspace: {payload['workspace']}")
        print(f"Trading mode: {payload['trading_mode']}")
        print(f"Live enabled: {payload['live_enabled']}")
        print(f"Broker: {payload['broker']}")
        print(f"Pending orders: {payload['pending_orders']}")
        return 0
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
            from atlas_agent.execution.submit_reconcile import ReconcileReport, run_reconcile

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

    def _research_error_json(status: str, message: str) -> None:
        import json
        print(json.dumps({"ok": False, "status": status, "message": message}, indent=2, sort_keys=True))

    def _research_error_text(prefix: str, message: str) -> None:
        print(f"{prefix} skipped safely: {message}")


    if args.command == "research" and args.research_command == "market":
        if args.json:
            _research_error_json("legacy_command_disabled", "research market is legacy and disabled in the frozen local research pipeline.")
        else:
            _research_error_text("research market", "legacy and disabled in the frozen local research pipeline")
        return 1
    if args.command == "research" and args.research_command == "run":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedResearchProviderError,
                run_research_session,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research run skipped safely: no workspace found")
                return 1
            event_logger = EventLogger(ws / "events")
            artifact = run_research_session(
                symbol=args.symbol,
                workspace_path=ws,
                memory_dir=ws / "memory",
                event_logger=event_logger,
                provider_name=args.provider,
                use_memory=not args.no_memory,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research run skipped safely: invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."}, indent=2, sort_keys=True))
            else:
                print("research run skipped safely: unsupported research provider")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research run", message.lower().rstrip("."))
            return 1
        except ResearchConfigurationError:
            if args.json:
                _research_error_json("configuration_error", "Configuration error.")
            else:
                _research_error_text("research run", "configuration error")
            return 0
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research run", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "created",
                "symbol": artifact.symbol,
                "mode": artifact.mode,
                "provider": artifact.provider,
                "run_id": artifact.run_id,
                "artifact_path": artifact.artifact_path,
                "warnings": artifact.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Research artifact created")
            print(f"  Symbol: {artifact.symbol}")
            print(f"  Mode: {artifact.mode}")
            print(f"  Provider: {artifact.provider}")
            print(f"  Artifact: {artifact.artifact_path}")
            if artifact.warnings:
                print(f"  Warnings: {len(artifact.warnings)}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "list":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                iter_research_artifacts,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_research_artifacts(ws, symbol=symbol_filter)[:limit]

            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "research_listed",
                    "items": items,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                if not items:
                    print("No research artifacts found.")
                else:
                    print(f"{'Created At':<24} {'Symbol':<8} {'Run ID':<34} {'Provider':<14} {'Warnings':<9} {'Artifact'}")
                    for item in items:
                        created = item.get("created_at", "")[:19]
                        print(f"{created:<24} {item['symbol']:<8} {item['run_id']:<34} {item['provider']:<14} {item['warnings_count']:<9} {item['artifact_path']}")
            return 0
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research list", "research command failed")
            return 1
    if args.command == "research" and args.research_command == "show":
        try:
            from atlas_agent.research.session import (
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                find_research_artifact_by_run_id,
                load_research_artifact,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research show skipped safely: no workspace found")
                return 1

            safe_run_id = validate_run_id(args.run_id)
            artifact_path = find_research_artifact_by_run_id(ws, safe_run_id)
            if artifact_path is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "artifact_not_found"}, indent=2, sort_keys=True))
                else:
                    print("research show skipped safely: artifact not found")
                return 1

            artifact = load_research_artifact(artifact_path, ws)
            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "research_loaded",
                    "artifact": artifact,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                print("Research Artifact")
                print(f"  Run ID: {artifact.get('run_id', '')}")
                print(f"  Symbol: {artifact.get('symbol', '')}")
                print(f"  Created: {artifact.get('created_at', '')}")
                print(f"  Provider: {artifact.get('provider', '')}")
                print(f"  Summary: {artifact.get('summary', '')}")
                print(f"  Thesis: {artifact.get('thesis', '')}")
                risks = artifact.get("risks", [])
                if risks:
                    print("  Risks:")
                    for r in risks:
                        print(f"    - {r}")
                inv = artifact.get("invalidation_conditions", [])
                if inv:
                    print("  Invalidation Conditions:")
                    for i in inv:
                        print(f"    - {i}")
                print(f"  Paper-only Plan: {artifact.get('paper_only_plan', '')}")
                artifact_warnings = artifact.get("warnings", [])
                if artifact_warnings:
                    print(f"  Warnings: {len(artifact_warnings)}")
                else:
                    print("  Warnings: 0")
                print(f"  Artifact: {artifact.get('artifact_path', '')}")
            return 0
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research show", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research show", "research command failed")
            return 1
    if args.command == "research" and args.research_command == "plan":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                UnsupportedResearchProviderError,
                create_paper_plan,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research plan skipped safely: no workspace found")
                return 1
            event_logger = EventLogger(ws / "events")
            plan = create_paper_plan(
                workspace_path=ws,
                run_id=args.run_id,
                event_logger=event_logger,
                provider_name=args.provider,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research plan skipped safely: invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."}, indent=2, sort_keys=True))
            else:
                print("research plan skipped safely: unsupported research provider")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research plan", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research plan", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research plan", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "paper_plan_created",
                "symbol": plan.symbol,
                "source_run_id": plan.source_run_id,
                "plan_id": plan.plan_id,
                "artifact_path": plan.artifact_path,
                "warnings": plan.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Paper plan created")
            print(f"  Symbol: {plan.symbol}")
            print(f"  Mode: {plan.mode}")
            print(f"  Source Run ID: {plan.source_run_id}")
            print(f"  Plan ID: {plan.plan_id}")
            print(f"  Artifact: {plan.artifact_path}")
            if plan.warnings:
                print(f"  Warnings: {len(plan.warnings)}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "summary":
        try:
            from atlas_agent.research.session import (
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                summarize_research_workspace,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research summary skipped safely: no workspace found")
                return 1

            summary = summarize_research_workspace(ws)
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research summary", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research summary", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_summary",
                "research_count": summary["research_count"],
                "plan_count": summary["plan_count"],
                "symbols": summary["symbols"],
                "warnings": summary["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            if summary["research_count"] == 0 and summary["plan_count"] == 0:
                print("No research artifacts found.")
            else:
                print("Research summary")
                print(f"Research artifacts: {summary['research_count']}")
                print(f"Paper plans: {summary['plan_count']}")
                sym_names = [s["symbol"] for s in summary["symbols"]]
                if sym_names:
                    print(f"Symbols: {', '.join(sym_names)}")
                for sym in summary["symbols"]:
                    print()
                    print(f"{sym['symbol']}")
                    if sym["latest_research_run_id"]:
                        print(f"  Latest research: {sym['latest_research_run_id']}")
                    if sym["latest_plan_id"]:
                        print(f"  Latest plan: {sym['latest_plan_id']}")
            if summary["warnings"]:
                print()
                for w in summary["warnings"]:
                    print(f"Warning: {w}")
        return 0
    if args.command == "research" and args.research_command == "verify":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                UnsupportedResearchProviderError,
                verify_paper_plan,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research verify skipped safely: no workspace found")
                return 1
            event_logger = EventLogger(ws / "events")
            verification = verify_paper_plan(
                workspace_path=ws,
                plan_id=args.plan_id,
                event_logger=event_logger,
                provider_name=args.provider,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research verify skipped safely: invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."}, indent=2, sort_keys=True))
            else:
                print("research verify skipped safely: unsupported research provider")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research verify", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research verify", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research verify", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_verification_created",
                "symbol": verification.symbol,
                "source_plan_id": verification.source_plan_id,
                "verification_id": verification.verification_id,
                "recommendation": verification.recommendation,
                "passed_checks": verification.passed_checks,
                "failed_checks": verification.failed_checks,
                "artifact_path": verification.artifact_path,
                "warnings": verification.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Paper plan verification created")
            print(f"  Symbol: {verification.symbol}")
            print(f"  Mode: {verification.mode}")
            print(f"  Source Plan ID: {verification.source_plan_id}")
            print(f"  Verification ID: {verification.verification_id}")
            print(f"  Recommendation: {verification.recommendation}")
            print(f"  Passed checks: {verification.passed_checks}")
            print(f"  Failed checks: {verification.failed_checks}")
            print(f"  Artifact: {verification.artifact_path}")
            if verification.warnings:
                print(f"  Warnings: {len(verification.warnings)}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "evaluate":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                UnsupportedResearchProviderError,
                evaluate_paper_plan,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research evaluate skipped safely: no workspace found")
                return 1
            event_logger = EventLogger(ws / "events")
            evaluation = evaluate_paper_plan(
                workspace_path=ws,
                plan_id=args.plan_id,
                data_path=args.data,
                event_logger=event_logger,
                provider_name=args.provider,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research evaluate skipped safely: invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."}, indent=2, sort_keys=True))
            else:
                print("research evaluate skipped safely: unsupported research provider")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research evaluate", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research evaluate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research evaluate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_evaluation_created",
                "symbol": evaluation.symbol,
                "source_plan_id": evaluation.source_plan_id,
                "evaluation_id": evaluation.evaluation_id,
                "recommendation": evaluation.recommendation,
                "artifact_path": evaluation.artifact_path,
                "passed_checks": sum(1 for c in evaluation.checks if c["status"] == "pass"),
                "failed_checks": sum(1 for c in evaluation.checks if c["status"] == "fail"),
                "metrics": evaluation.metrics,
                "warnings": evaluation.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Paper plan evaluation created")
            print(f"  Symbol: {evaluation.symbol}")
            print(f"  Mode: {evaluation.mode}")
            print(f"  Source Plan ID: {evaluation.source_plan_id}")
            print(f"  Evaluation ID: {evaluation.evaluation_id}")
            print(f"  Recommendation: {evaluation.recommendation}")
            print(f"  Rows: {evaluation.metrics.get('row_count', 0)}")
            print(f"  Artifact: {evaluation.artifact_path}")
            if evaluation.warnings:
                print(f"  Warnings: {len(evaluation.warnings)}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "check-artifacts":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                check_research_artifacts,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research check-artifacts skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            result = check_research_artifacts(ws, symbol_filter=symbol_filter)
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research check-artifacts skipped safely: invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research check-artifacts", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research check-artifacts", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research check-artifacts", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Research artifact health check")
            print(f"  Research artifacts: {result['counts']['research']}")
            print(f"  Paper plans: {result['counts']['plans']}")
            print(f"  Verifications: {result['counts']['verifications']}")
            print(f"  Evaluations: {result['counts']['evaluations']}")
            print(f"  Provider call plans: {result['counts']['provider_call_plans']}")
            print(f"  Provider execution dry-runs: {result['counts']['provider_execution_dry_runs']}")
            print(f"  Provider execution readiness reports: {result['counts']['provider_execution_readiness_reports']}")
            print(f"  Provider outbound payload previews: {result['counts']['provider_outbound_payload_previews']}")
            total_issues = len(result["issues"])
            total_warnings = len(result["warnings"])
            print(f"  Issues: {total_issues}")
            print(f"  Warnings: {total_warnings}")
            if result["issues"]:
                print("\nIssues:")
                for issue in result["issues"]:
                    print(f"  - {issue['code']}: {issue['path']}")
            if result["warnings"]:
                print("\nWarnings:")
                for warning in result["warnings"]:
                    print(f"  - {warning['code']}: {warning['path']}")
            if not result["issues"] and not result["warnings"]:
                print("\nNo artifact health issues found.")
        if args.strict and result["issues"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "timeline":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                build_research_timeline,
                sanitize_symbol,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research timeline skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            run_id_filter = None
            if args.run_id:
                run_id_filter = validate_run_id(args.run_id)

            limit = args.limit
            if limit < 1:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "invalid_limit"}, indent=2, sort_keys=True))
                else:
                    print("research timeline skipped safely: limit must be positive")
                return 1
            if limit > 100:
                limit = 100

            result = build_research_timeline(
                ws,
                symbol_filter=symbol_filter,
                run_id_filter=run_id_filter,
                limit=limit,
            )
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research timeline skipped safely: invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research timeline", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research timeline", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research timeline", "research command failed")
            return 1
        if args.json:
            import json
            try:
                print(json.dumps(result, indent=2, sort_keys=True))
            except (ValueError, TypeError):
                print(json.dumps({
                    "ok": False,
                    "status": "research_timeline_failed",
                    "error_code": "research_timeline_serialization_failed",
                    "message": "Research timeline could not be generated safely.",
                }, indent=2, sort_keys=True))
                return 1
        else:
            entries = result.get("entries", [])
            if not entries:
                print("No research timeline entries found.")
            else:
                print("Research timeline")
                for entry in entries:
                    symbol = entry.get("symbol", "")
                    run_id = entry.get("run_id", "")
                    print(f"\n{symbol} — {run_id}")
                    print(f"  Research: {entry.get('research_path', '')}")
                    for plan in entry.get("plans", []):
                        plan_id = plan.get("plan_id", "")
                        print(f"  Plan: {plan_id}")
                        for v in plan.get("verifications", []):
                            vid = v.get("verification_id", "")
                            rec = v.get("recommendation", "")
                            print(f"    Verification: {vid} — {rec}")
                        for e in plan.get("evaluations", []):
                            eid = e.get("evaluation_id", "")
                            rec = e.get("recommendation", "")
                            print(f"    Evaluation: {eid} — {rec}")
                    for prompt in entry.get("prompts", []):
                        prompt_id = prompt.get("prompt_packet_id", "")
                        print(f"  Prompt: {prompt_id}")
                        for pr in prompt.get("provider_responses", []):
                            pr_id = pr.get("provider_response_id", "")
                            provider = pr.get("provider", "")
                            rec = pr.get("recommendation", "")
                            print(f"    Provider response: {pr_id} ({provider}) — {rec}")
                            for rr in pr.get("response_reviews", []):
                                rr_id = rr.get("response_review_id", "")
                                rr_rec = rr.get("recommendation", "")
                                print(f"      Response review: {rr_id} — {rr_rec}")
                        for sr in prompt.get("sandbox_requests", []):
                            sr_id = sr.get("sandbox_request_id", "")
                            print(f"    Sandbox request: {sr_id}")
                            for pcp in sr.get("provider_call_plans", []):
                                pcp_id = pcp.get("provider_call_plan_id", "")
                                print(f"      Provider call plan: {pcp_id}")
                                for ped in pcp.get("provider_execution_dry_runs", []):
                                    ped_id = ped.get("provider_execution_dry_run_id", "")
                                    print(f"        Provider execution dry-run: {ped_id}")
                                    for pes in ped.get("provider_execution_states", []):
                                        pes_id = pes.get("provider_execution_state_id", "")
                                        pes_state = pes.get("state", "")
                                        print(f"          Provider execution state: {pes_id} ({pes_state})")
                                        for peap in pes.get("provider_execution_audit_packets", []):
                                            peap_id = peap.get("provider_execution_audit_packet_id", "")
                                            print(f"            Provider execution audit packet: {peap_id}")
                                            for perr in peap.get("provider_execution_readiness_reports", []):
                                                perr_id = perr.get("provider_execution_readiness_report_id", "")
                                                perr_status = perr.get("readiness_status", "")
                                                perr_score = perr.get("readiness_score", 0)
                                                print(f"              Provider execution readiness report: {perr_id} ({perr_status}, score: {perr_score})")
            timeline_warnings = result.get("warnings", [])
            if timeline_warnings:
                print("\nWarnings:")
                for w in timeline_warnings:
                    print(f"  - {w.get('code', '')}: {w.get('path', '')}")
        return 0
    if args.command == "research" and args.research_command == "providers":
        from atlas_agent.research.providers import list_research_providers

        providers = list_research_providers()
        if args.json:
            import json

            payload = {
                "ok": True,
                "status": "research_providers_listed",
                "providers": [
                    {
                        "name": p.name,
                        "status": p.status,
                        "enabled": p.enabled,
                        "default": p.default,
                        "local": p.local,
                        "network": p.network,
                        "requires_api_key": p.requires_api_key,
                    }
                    for p in providers
                ],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("Research providers\n")
            for p in providers:
                print(p.name)
                print(f"  Status: {p.status}")
                print(f"  Default: {'yes' if p.default else 'no'}")
                print(f"  Local: {'yes' if p.local else 'no'}")
                print(f"  Network: {'yes' if p.network else 'no'}")
                print(f"  Requires API key: {'yes' if p.requires_api_key else 'no'}")
                print()
            print("External LLM research providers are not enabled.")
        return 0
    if args.command == "research" and args.research_command == "prompt":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                generate_prompt_packet,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research prompt skipped safely: no workspace found")
                return 1

            safe_run_id = validate_run_id(args.run_id)

            max_chars = args.max_context_chars
            if not isinstance(max_chars, int) or max_chars <= 0 or max_chars > 20000:
                if args.json:
                    _research_error_json("invalid_max_context_chars", "Invalid max-context-chars value.")
                else:
                    _research_error_text("research prompt", "invalid max-context-chars value")
                return 1

            event_logger = EventLogger(ws / "events")

            packet = generate_prompt_packet(
                ws,
                safe_run_id,
                max_context_chars=max_chars,
                event_logger=event_logger,
            )

            if args.json:
                import json

                out = {
                    "ok": True,
                    "status": "research_prompt_packet_created",
                    "symbol": packet["symbol"],
                    "source_run_id": packet["source_run_id"],
                    "prompt_packet_id": packet["prompt_packet_id"],
                    "artifact_path": packet["artifact_path"],
                    "warnings": packet.get("warnings", []),
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                print("Research prompt packet created")
                print(f"Symbol: {packet['symbol']}")
                print(f"Mode: {packet['mode']}")
                print(f"Source Run ID: {packet['source_run_id']}")
                print(f"Prompt Packet ID: {packet['prompt_packet_id']}")
                print(f"Artifact: {packet['artifact_path']}")
            return 0
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research prompt", "invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research prompt", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research prompt", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research prompt", "research command failed")
            return 1
    if args.command == "research" and args.research_command == "simulate-provider":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                UnsupportedResearchProviderError,
                simulate_provider_response,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research simulate-provider skipped safely: no workspace found")
                return 1

            safe_prompt_id = validate_run_id(args.prompt_packet_id)

            event_logger = EventLogger(ws / "events")

            result = simulate_provider_response(
                workspace_path=ws,
                prompt_packet_id=safe_prompt_id,
                provider=args.provider,
                event_logger=event_logger,
            )
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research simulate-provider", "invalid research symbol")
            return 1
        except UnsupportedResearchProviderError:
            if args.json:
                import json

                print(
                    json.dumps(
                        {"ok": False, "status": "unsupported_research_provider", "message": "Unsupported research provider."},
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print("research simulate-provider skipped safely: unsupported research provider")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research simulate-provider", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research simulate-provider", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research simulate-provider", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "research_provider_response_created",
                "symbol": result["symbol"],
                "source_prompt_packet_id": result["source_prompt_packet_id"],
                "provider_response_id": result["provider_response_id"],
                "provider": result["provider"],
                "recommendation": result["recommendation"],
                "artifact_path": result["artifact_path"],
                "warnings": result.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Simulated provider response created")
            print(f"  Symbol: {result['symbol']}")
            print(f"  Mode: {result['mode']}")
            print(f"  Provider: {result['provider']}")
            print(f"  Source Prompt Packet ID: {result['source_prompt_packet_id']}")
            print(f"  Provider Response ID: {result['provider_response_id']}")
            print(f"  Recommendation: {result['recommendation']}")
            print(f"  Artifact: {result['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "review-response":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                review_provider_response,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research review-response skipped safely: no workspace found")
                return 1

            safe_response_id = validate_run_id(args.provider_response_id)

            event_logger = EventLogger(ws / "events")

            result = review_provider_response(
                workspace_path=ws,
                provider_response_id=safe_response_id,
                event_logger=event_logger,
            )
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research review-response", "invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research review-response", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research review-response", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research review-response", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "research_response_review_created",
                "symbol": result["symbol"],
                "source_provider_response_id": result["source_provider_response_id"],
                "response_review_id": result["response_review_id"],
                "provider": result["provider"],
                "recommendation": result["recommendation"],
                "artifact_path": result["artifact_path"],
                "warnings": result.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider response review created")
            print(f"  Symbol: {result['symbol']}")
            print(f"  Mode: {result['mode']}")
            print(f"  Provider: {result['provider']}")
            print(f"  Source Provider Response ID: {result['source_provider_response_id']}")
            print(f"  Response Review ID: {result['response_review_id']}")
            print(f"  Recommendation: {result['recommendation']}")
            print(f"  Artifact: {result['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "dossier":
        try:
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                build_dossier,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research dossier skipped safely: no workspace found")
                return 1

            safe_run_id = validate_run_id(args.run_id)

            events_dir = ws / "events"
            event_logger = EventLogger(events_dir)

            result = build_dossier(
                workspace_path=ws,
                run_id=safe_run_id,
                event_logger=event_logger,
            )
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research dossier", "invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research dossier", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research dossier", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research dossier", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "research_dossier_created",
                "symbol": result["symbol"],
                "source_run_id": result["source_run_id"],
                "dossier_id": result["dossier_id"],
                "provider": result["provider"],
                "recommendation": result["recommendation"],
                "artifact_path": result["artifact_path"],
                "warnings": result.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Research dossier created")
            print(f"  Symbol: {result['symbol']}")
            print(f"  Mode: {result['mode']}")
            print(f"  Source Run ID: {result['source_run_id']}")
            print(f"  Dossier ID: {result['dossier_id']}")
            print(f"  Recommendation: {result['recommendation']}")
            print(f"  Artifact: {result['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "sandbox":
        try:
            from atlas_agent.research.llm_sandbox import build_llm_sandbox_request_from_prompt_packet
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                UnsupportedArtifactSchemaError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json

                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research sandbox skipped safely: no workspace found")
                return 1

            safe_prompt_packet_id = validate_run_id(args.prompt_packet_id)

            result = build_llm_sandbox_request_from_prompt_packet(
                workspace_path=ws,
                prompt_packet_id=safe_prompt_packet_id,
            )
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                _research_error_text("research sandbox", "invalid research symbol")
            return 1
        except UnsupportedArtifactSchemaError:
            if args.json:
                _research_error_json("unsupported_research_artifact_schema", "Unsupported research artifact schema.")
            else:
                _research_error_text("research sandbox", "unsupported research artifact schema")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research sandbox", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research sandbox", "research command failed")
            return 1
        if args.json:
            import json

            out = {
                "ok": True,
                "status": "research_sandbox_request_created",
                "symbol": result["symbol"],
                "prompt_packet_id": result["prompt_packet_id"],
                "source_run_id": result["source_run_id"],
                "sandbox_request_id": result["sandbox_request_id"],
                "provider": result["provider"],
                "recommendation": "sandbox_request_ready",
                "artifact_path": result["artifact_path"],
                "warnings": result.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Research sandbox request created")
            print(f"  Symbol: {result['symbol']}")
            print(f"  Prompt Packet ID: {result['prompt_packet_id']}")
            print(f"  Source Run ID: {result['source_run_id']}")
            print(f"  Sandbox Request ID: {result['sandbox_request_id']}")
            print(f"  Provider: {result['provider']}")
            print(f"  Recommendation: sandbox_request_ready")
            print(f"  Artifact: {result['artifact_path']}")
            if result.get("warnings"):
                print(f"  Warnings: {len(result['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "sandbox-list":
        try:
            from atlas_agent.research.session import _iter_sandbox_request_artifacts
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research sandbox-list skipped safely: no workspace found")
                return 1

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = _iter_sandbox_request_artifacts(ws, symbol=args.symbol)
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research sandbox-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research sandbox-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_sandbox_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Sandbox requests: {len(items)}")
            for item in items:
                print(f"  {item['sandbox_request_id']}  {item['symbol']}  {item['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "sandbox-show":
        try:
            from atlas_agent.research.session import (
                ResearchSessionError,
                find_sandbox_request_by_id,
                load_sandbox_request,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research sandbox-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_request_id)
            path = find_sandbox_request_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("sandbox_request_not_found")
            artifact = load_sandbox_request(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research sandbox-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research sandbox-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_sandbox_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Sandbox request: {artifact['sandbox_request_id']}")
            print(f"  Symbol: {artifact['symbol']}")
            print(f"  Prompt Packet ID: {artifact['prompt_packet_id']}")
            print(f"  Source Run ID: {artifact['source_run_id']}")
            print(f"  Provider: {artifact['provider']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "sandbox-validate":
        try:
            from atlas_agent.research.sandbox_contracts import validate_sandbox_request_artifact
            from atlas_agent.research.session import (
                ResearchSessionError,
                find_sandbox_request_by_id,
                load_sandbox_request,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research sandbox-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_request_id)
            path = find_sandbox_request_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("sandbox_request_not_found")
            artifact = load_sandbox_request(path, ws)
            result = validate_sandbox_request_artifact(artifact)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research sandbox-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research sandbox-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_sandbox_validated",
                "sandbox_request_id": artifact["sandbox_request_id"],
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Sandbox request {artifact['sandbox_request_id']}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "sandbox-replay":
        try:
            from atlas_agent.research.llm_sandbox import _build_sandbox_request_dict
            from atlas_agent.research.session import (
                ResearchSessionError,
                find_prompt_packet_by_id,
                find_sandbox_request_by_id,
                load_prompt_packet,
                load_sandbox_request,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research sandbox-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_request_id)
            sandbox_path = find_sandbox_request_by_id(ws, safe_id)
            if sandbox_path is None:
                raise ResearchSessionError("sandbox_request_not_found")
            sandbox = load_sandbox_request(sandbox_path, ws)

            prompt_packet_id = sandbox.get("prompt_packet_id", "")
            if not prompt_packet_id:
                raise ResearchSessionError("invalid_sandbox_lineage")

            packet_path = find_prompt_packet_by_id(ws, prompt_packet_id)
            if packet_path is None:
                raise ResearchSessionError("prompt_packet_not_found")
            prompt_packet = load_prompt_packet(packet_path, ws)

            rebuilt = _build_sandbox_request_dict(prompt_packet, prompt_packet_id, safe_id)
            actual_hash = sandbox.get("content_hash", "")
            expected_hash = rebuilt.get("content_hash", "")
            match = actual_hash == expected_hash

            checks = [
                {"name": "sandbox_request_loaded", "passed": True, "message": "Sandbox request loaded."},
                {"name": "prompt_packet_loaded", "passed": True, "message": "Prompt packet loaded."},
                {"name": "hash_matches", "passed": match, "message": "Hash matches." if match else "Hash mismatch detected."},
            ]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research sandbox-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research sandbox-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_sandbox_replayed",
                "sandbox_request_id": safe_id,
                "source_prompt_packet_id": prompt_packet_id,
                "match": match,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
                "checks": checks,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if match else "mismatch"
            print(f"Sandbox replay {safe_id}: {status_str}")
        if args.strict and not match:
            return 2
        return 0
    if args.command == "research" and args.research_command == "import-provider-response":
        try:
            from atlas_agent.research.sandbox_contracts import (
                artifact_sha256,
                canonical_json_dumps,
                sanitize_contract_text,
                validate_contract_lineage_id,
                validate_contract_symbol,
                validate_external_provider_response_payload,
            )
            from atlas_agent.research.session import (
                RESEARCH_ARTIFACT_SCHEMA_VERSION,
                RESEARCH_DIR,
                ResearchSessionError,
                find_sandbox_request_by_id,
                load_sandbox_request,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research import-provider-response skipped safely: no workspace found")
                return 1

            safe_sandbox_id = validate_run_id(args.sandbox_request_id)
            sandbox_path = find_sandbox_request_by_id(ws, safe_sandbox_id)
            if sandbox_path is None:
                raise ResearchSessionError("sandbox_request_not_found")
            sandbox = load_sandbox_request(sandbox_path, ws)

            file_path = args.file
            if not file_path.exists() or not file_path.is_file():
                raise ResearchSessionError("provider_response_file_not_found")
            if file_path.is_symlink():
                try:
                    resolved = file_path.resolve()
                    ws_resolved = ws.resolve()
                    resolved.relative_to(ws_resolved)
                except ValueError:
                    raise ResearchSessionError("artifact_path_not_allowed")

            try:
                import json
                raw_data: dict[str, Any] = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                raise ResearchSessionError("provider_response_malformed")

            summary = sanitize_contract_text(raw_data.get("summary", ""), 4000)
            sections = raw_data.get("sections", [])
            if not isinstance(sections, list):
                sections = []
            safe_sections = []
            for sec in sections:
                if isinstance(sec, dict):
                    safe_sections.append({
                        "title": sanitize_contract_text(str(sec.get("title", "")), 200),
                        "content": sanitize_contract_text(str(sec.get("content", "")), 4000),
                    })

            safety_checks = raw_data.get("safety_checks", [])
            if not isinstance(safety_checks, list):
                safety_checks = []
            safe_checks = []
            for chk in safety_checks:
                if isinstance(chk, dict):
                    safe_checks.append({
                        "name": sanitize_contract_text(str(chk.get("name", "")), 200),
                        "status": str(chk.get("status", "warn")),
                        "notes": sanitize_contract_text(str(chk.get("notes", "")), 1000),
                    })

            limitations = raw_data.get("limitations", [])
            if not isinstance(limitations, list):
                limitations = []
            safe_limitations = [sanitize_contract_text(str(l), 500) for l in limitations]

            symbol = validate_contract_symbol(sandbox.get("symbol", ""))
            prompt_packet_id = validate_contract_lineage_id(sandbox.get("prompt_packet_id", ""), "prompt_packet_id")
            source_run_id = validate_contract_lineage_id(sandbox.get("source_run_id", ""), "source_run_id")

            provider_response_id = generate_run_id()
            created_at = datetime.now(UTC)

            artifact_path_rel = f".atlas/research/{symbol}/provider_responses/{provider_response_id}.json"
            artifact_path = ws / artifact_path_rel

            response_payload: dict[str, Any] = {
                "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
                "artifact_type": "provider_response",
                "provider_response_id": provider_response_id,
                "source_sandbox_request_id": safe_sandbox_id,
                "source_prompt_packet_id": prompt_packet_id,
                "source_run_id": source_run_id,
                "created_at": created_at.isoformat(),
                "symbol": symbol,
                "mode": "paper",
                "provider": "external-local-import",
                "provider_status": "imported_untrusted",
                "response_summary": summary,
                "response_sections": safe_sections,
                "safety_checks": safe_checks,
                "limitations": safe_limitations,
                "artifact_path": artifact_path_rel,
            }

            validation = validate_external_provider_response_payload(response_payload)
            if not validation.valid:
                resp_warnings = validation.warnings + ["Imported provider response failed contract validation."]
            else:
                resp_warnings = validation.warnings

            response_payload["recommendation"] = validation.recommendation
            response_payload["redaction_summary"] = {"redacted_fragments_count": 0, "truncated": False}
            response_payload["warnings"] = resp_warnings
            response_payload["content_hash"] = artifact_sha256(response_payload)

            responses_dir = ws / RESEARCH_DIR / symbol / "provider_responses"
            responses_dir.mkdir(parents=True, exist_ok=True)

            artifact_path.write_text(json.dumps(response_payload, indent=2, sort_keys=True), encoding="utf-8")
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research import-provider-response", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research import-provider-response", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_imported",
                "provider_response_id": provider_response_id,
                "source_sandbox_request_id": safe_sandbox_id,
                "artifact_path": artifact_path_rel,
                "recommendation": validation.recommendation,
                "warnings": resp_warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response imported: {provider_response_id}")
            print(f"  Source Sandbox: {safe_sandbox_id}")
            print(f"  Artifact: {artifact_path_rel}")
            print(f"  Recommendation: {validation.recommendation}")
        return 0
    if args.command == "research" and args.research_command == "provider-targets":
        try:
            from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
            from atlas_agent.research.session import ResearchSessionError

            targets = list_disabled_provider_call_targets()
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-targets", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-targets", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_targets_listed",
                "targets": targets,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider call targets")
            for t in targets:
                print(f"  {t['provider_id']}")
                print(f"    Status: {t['status']}")
                print(f"    Enabled: {'yes' if t['enabled'] else 'no'}")
                print(f"    Network: {'yes' if t['network'] else 'no'}")
                print(f"    Description: {t['description']}")
        return 0
    if args.command == "research" and args.research_command == "provider-plan":
        try:
            from atlas_agent.research.provider_call_plan import (
                create_provider_call_plan,
                validate_model_id,
                validate_provider_id,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-plan skipped safely: no workspace found")
                return 1

            safe_sandbox_request_id = validate_run_id(args.sandbox_request_id)
            provider_id = validate_provider_id(args.provider)
            model_id = validate_model_id(args.model)

            artifact = create_provider_call_plan(ws, safe_sandbox_request_id, provider_id, model_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plan_created",
                "provider_call_plan_id": artifact["provider_call_plan_id"],
                "source_sandbox_request_id": artifact["source_sandbox_request_id"],
                "provider_id": artifact["provider_id"],
                "model_id": artifact["model_id"],
                "artifact_path": artifact["artifact_path"],
                "warnings": artifact.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider call plan created: {artifact['provider_call_plan_id']}")
            print(f"  Source Sandbox: {artifact['source_sandbox_request_id']}")
            print(f"  Provider: {artifact['provider_id']}")
            print(f"  Model: {artifact['model_id']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "provider-plan-list":
        try:
            from atlas_agent.research.provider_call_plan import iter_provider_call_plan_artifacts
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-plan-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_call_plan_artifacts(ws, symbol=symbol_filter)
            items = items[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research provider-plan-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plans_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider call plans: {len(items)}")
            for item in items:
                print(f"  {item['provider_call_plan_id']}  {item['symbol']}  {item['provider_id']}  {item['model_id']}  {item['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "provider-plan-show":
        try:
            from atlas_agent.research.provider_call_plan import (
                find_provider_call_plan_by_id,
                load_and_validate_provider_call_plan,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-plan-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_call_plan_id)
            path = find_provider_call_plan_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("provider_call_plan_not_found")
            artifact = load_and_validate_provider_call_plan(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plan_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider call plan: {artifact['provider_call_plan_id']}")
            print(f"  Symbol: {artifact['symbol']}")
            print(f"  Provider: {artifact['provider_id']}")
            print(f"  Model: {artifact['model_id']}")
            print(f"  Source Sandbox: {artifact['source_sandbox_request_id']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "provider-plan-validate":
        try:
            from atlas_agent.research.provider_call_plan import (
                find_provider_call_plan_by_id,
                load_provider_call_plan,
                validate_provider_call_plan_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-plan-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_call_plan_id)
            path = find_provider_call_plan_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("provider_call_plan_not_found")
            plan_data = load_provider_call_plan(path, ws)
            result = validate_provider_call_plan_artifact(plan_data, workspace_path=ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plan_validated",
                "provider_call_plan_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider call plan {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-plan-replay":
        try:
            from atlas_agent.research.provider_call_plan import replay_provider_call_plan
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-plan-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_call_plan_id)
            replay_result = replay_provider_call_plan(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-plan-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-plan-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_call_plan_replayed",
                "provider_call_plan_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider call plan replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-dry-run":
        try:
            from atlas_agent.research.provider_execution_dry_run import (
                create_provider_execution_dry_run,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-dry-run skipped safely: no workspace found")
                return 1

            safe_plan_id = validate_run_id(args.provider_call_plan_id)
            artifact = create_provider_execution_dry_run(ws, safe_plan_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-dry-run", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-dry-run", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_run_created",
                "provider_execution_dry_run_id": artifact["provider_execution_dry_run_id"],
                "source_provider_call_plan_id": artifact["source_provider_call_plan_id"],
                "provider_id": artifact["provider_id"],
                "model_id": artifact["model_id"],
                "artifact_path": artifact["artifact_path"],
                "warnings": artifact.get("warnings", []),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution dry-run created: {artifact['provider_execution_dry_run_id']}")
            print(f"  Source Plan: {artifact['source_provider_call_plan_id']}")
            print(f"  Provider: {artifact['provider_id']}")
            print(f"  Model: {artifact['model_id']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-list":
        try:
            from atlas_agent.research.provider_execution_dry_run import (
                iter_provider_execution_dry_run_artifacts,
            )
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_execution_dry_run_artifacts(ws, symbol=symbol_filter)
            items = items[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research provider-execution-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_runs_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution dry-runs: {len(items)}")
            for item in items:
                print(f"  {item['provider_execution_dry_run_id']}  {item['symbol']}  {item['provider_id']}  {item['model_id']}  {item['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-show":
        try:
            from atlas_agent.research.provider_execution_dry_run import (
                find_provider_execution_dry_run_by_id,
                load_and_validate_provider_execution_dry_run,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_dry_run_id)
            path = find_provider_execution_dry_run_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("provider_execution_dry_run_not_found")
            artifact = load_and_validate_provider_execution_dry_run(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_run_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution dry-run: {artifact['provider_execution_dry_run_id']}")
            print(f"  Symbol: {artifact['symbol']}")
            print(f"  Provider: {artifact['provider_id']}")
            print(f"  Model: {artifact['model_id']}")
            print(f"  Source Plan: {artifact['source_provider_call_plan_id']}")
            print(f"  Artifact: {artifact['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-validate":
        try:
            from atlas_agent.research.provider_execution_dry_run import (
                find_provider_execution_dry_run_by_id,
                load_provider_execution_dry_run,
                validate_provider_execution_dry_run_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_dry_run_id)
            path = find_provider_execution_dry_run_by_id(ws, safe_id)
            if path is None:
                raise ResearchSessionError("provider_execution_dry_run_not_found")
            dry_run_data = load_provider_execution_dry_run(path, ws)
            result = validate_provider_execution_dry_run_artifact(dry_run_data, workspace_path=ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_run_validated",
                "provider_execution_dry_run_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider execution dry-run {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-replay":
        try:
            from atlas_agent.research.provider_execution_dry_run import replay_provider_execution_dry_run
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_dry_run_id)
            replay_result = replay_provider_execution_dry_run(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_dry_run_replayed",
                "provider_execution_dry_run_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider execution dry-run replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-state":
        try:
            from atlas_agent.research.provider_execution_state import create_provider_execution_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-state skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_dry_run_id)
            result = create_provider_execution_state(ws, safe_id, args.requested_state)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-state", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if result.get("ok"):
                print(f"Provider execution state {result.get('provider_execution_state_id')}: {result.get('state')}")
            else:
                print(f"Provider execution state transition blocked: {', '.join(result.get('blocking_reasons', []))}")
        return 0 if result.get("ok") else 1
    if args.command == "research" and args.research_command == "provider-execution-state-list":
        try:
            from atlas_agent.research.provider_execution_state import iter_provider_execution_state_artifacts
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-state-list skipped safely: no workspace found")
                return 1

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100
            items = iter_provider_execution_state_artifacts(ws, symbol=args.symbol)
            items = items[:limit]
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_states_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution states: {len(items)} found")
            for item in items:
                sid = item.get("provider_execution_state_id", "<invalid>")
                st = item.get("state", "<invalid>")
                print(f"  {sid}: {st}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-state-show":
        try:
            from atlas_agent.research.provider_execution_state import (
                find_provider_execution_state_by_id,
                load_and_validate_provider_execution_state,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-state-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_state_id)
            state_path = find_provider_execution_state_by_id(ws, safe_id)
            if state_path is None:
                raise ResearchSessionError("provider_execution_state_not_found")
            artifact = load_and_validate_provider_execution_state(state_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-state-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_state_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution state {safe_id}: {artifact.get('state')}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-state-validate":
        try:
            from atlas_agent.research.provider_execution_state import (
                find_provider_execution_state_by_id,
                validate_provider_execution_state_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-state-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_state_id)
            state_path = find_provider_execution_state_by_id(ws, safe_id)
            if state_path is None:
                raise ResearchSessionError("provider_execution_state_not_found")
            import json
            data = json.loads(state_path.read_text(encoding="utf-8"))
            result = validate_provider_execution_state_artifact(data, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-state-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_state_validated",
                "provider_execution_state_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider execution state {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-state-replay":
        try:
            from atlas_agent.research.provider_execution_state import replay_provider_execution_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-state-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_state_id)
            replay_result = replay_provider_execution_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-state-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-state-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_state_replayed",
                "provider_execution_state_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider execution state replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-audit":
        try:
            from atlas_agent.research.provider_execution_audit_packet import create_provider_execution_audit_packet
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-audit skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_state_id)
            result = create_provider_execution_audit_packet(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-audit", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution audit packet {result.get('provider_execution_audit_packet_id')}: {result.get('audit_status')}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-audit-list":
        try:
            from atlas_agent.research.provider_execution_audit_packet import iter_provider_execution_audit_packet_artifacts
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-audit-list skipped safely: no workspace found")
                return 1

            items = iter_provider_execution_audit_packet_artifacts(ws, symbol=args.symbol)
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({
                "ok": True,
                "status": "research_provider_execution_audit_packets_listed",
                "items": list(items)[:args.limit],
            }, indent=2, sort_keys=True))
        else:
            print("Provider execution audit packets:")
            for item in list(items)[:args.limit]:
                sid = item.get("provider_execution_audit_packet_id", "<invalid>")
                st = item.get("audit_status", "<invalid>")
                print(f"  {sid}: {st}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-audit-show":
        try:
            from atlas_agent.research.provider_execution_audit_packet import (
                find_provider_execution_audit_packet_by_id,
                load_and_validate_provider_execution_audit_packet,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-audit-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_audit_packet_id)
            audit_path = find_provider_execution_audit_packet_by_id(ws, safe_id)
            if audit_path is None:
                raise ResearchSessionError("provider_execution_audit_packet_not_found")
            artifact = load_and_validate_provider_execution_audit_packet(audit_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-audit-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit-show", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({
                "ok": True,
                "status": "research_provider_execution_audit_packet_loaded",
                "artifact": artifact,
            }, indent=2, sort_keys=True))
        else:
            print(f"Provider execution audit packet {safe_id}:")
            print(f"  audit_status: {artifact.get('audit_status')}")
            print(f"  execution_status: {artifact.get('execution_status')}")
            print(f"  latest_state: {artifact.get('latest_state')}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-audit-validate":
        try:
            from atlas_agent.research.provider_execution_audit_packet import (
                find_provider_execution_audit_packet_by_id,
                validate_provider_execution_audit_packet_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-audit-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_audit_packet_id)
            audit_path = find_provider_execution_audit_packet_by_id(ws, safe_id)
            if audit_path is None:
                raise ResearchSessionError("provider_execution_audit_packet_not_found")
            import json
            data = json.loads(audit_path.read_text(encoding="utf-8"))
            result = validate_provider_execution_audit_packet_artifact(data, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-audit-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_audit_packet_validated",
                "provider_execution_audit_packet_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider execution audit packet {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-audit-replay":
        try:
            from atlas_agent.research.provider_execution_audit_packet import replay_provider_execution_audit_packet
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-audit-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_audit_packet_id)
            replay_result = replay_provider_execution_audit_packet(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-audit-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-audit-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_audit_packet_replayed",
                "provider_execution_audit_packet_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider execution audit packet replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-readiness":
        try:
            from atlas_agent.research.provider_execution_readiness_report import create_provider_execution_readiness_report
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-readiness skipped safely: no workspace found")
                return 1

            result = create_provider_execution_readiness_report(ws, args.provider_execution_audit_packet_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution readiness report {result.get('provider_execution_readiness_report_id')}: {result.get('readiness_status')} (score: {result.get('readiness_score')})")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-readiness-list":
        try:
            from atlas_agent.research.provider_execution_readiness_report import iter_provider_execution_readiness_report_artifacts
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-readiness-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_execution_readiness_report_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                import json
                print(json.dumps({"ok": False, "status": "invalid_research_symbol", "message": "Invalid research symbol."}, indent=2, sort_keys=True))
            else:
                print("research provider-execution-readiness-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_readiness_reports_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            if not items:
                print("No provider execution readiness reports found.")
            else:
                print(f"{'Created At':<24} {'Symbol':<8} {'Report ID':<34} {'Status':<24} {'Score':<6} {'Artifact'}")
                for item in items:
                    created = item.get("created_at", "")[:19]
                    print(f"{created:<24} {item['symbol']:<8} {item['provider_execution_readiness_report_id']:<34} {item['readiness_status']:<24} {item['readiness_score']:<6} {item['artifact_path']}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-readiness-show":
        try:
            from atlas_agent.research.provider_execution_readiness_report import (
                find_provider_execution_readiness_report_by_id,
                load_and_validate_provider_execution_readiness_report,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-readiness-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_readiness_report_id)
            report_path = find_provider_execution_readiness_report_by_id(ws, safe_id)
            if report_path is None:
                raise ResearchSessionError("provider_execution_readiness_report_not_found")
            artifact = load_and_validate_provider_execution_readiness_report(report_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_readiness_report_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider execution readiness report")
            print(f"  Report ID: {artifact.get('provider_execution_readiness_report_id', '')}")
            print(f"  Symbol: {artifact.get('symbol', '')}")
            print(f"  Readiness status: {artifact.get('readiness_status', '')}")
            print(f"  Readiness score: {artifact.get('readiness_score', 0)}")
            print(f"  Chain health: {artifact.get('chain_health', '')}")
            print(f"  Execution status: {artifact.get('execution_status', '')}")
            print(f"  Artifact: {artifact.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-readiness-validate":
        try:
            from atlas_agent.research.provider_execution_readiness_report import (
                find_provider_execution_readiness_report_by_id,
                validate_provider_execution_readiness_report_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-readiness-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_readiness_report_id)
            report_path = find_provider_execution_readiness_report_by_id(ws, safe_id)
            if report_path is None:
                raise ResearchSessionError("provider_execution_readiness_report_not_found")
            import json as _json
            data = _json.loads(report_path.read_text(encoding="utf-8"))
            result = validate_provider_execution_readiness_report_artifact(data, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_readiness_report_validated",
                "provider_execution_readiness_report_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if result.valid else "invalid"
            print(f"Provider execution readiness report validation {safe_id}: {status_str}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-readiness-replay":
        try:
            from atlas_agent.research.provider_execution_readiness_report import replay_provider_execution_readiness_report
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-readiness-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_execution_readiness_report_id)
            replay_result = replay_provider_execution_readiness_report(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-readiness-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-readiness-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_readiness_report_replayed",
                "provider_execution_readiness_report_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider execution readiness report replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-chain-doctor":
        try:
            from atlas_agent.research.provider_execution_readiness_report import provider_execution_chain_doctor
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-chain-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = provider_execution_chain_doctor(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-chain-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-chain-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Chain doctor: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
                print(f"  Warnings: {result.get('warnings', [])}")
            else:
                print(f"Chain doctor for run {safe_id}:")
                print(f"  Symbol: {result.get('symbol', '')}")
                print(f"  Chain health: {result.get('chain_health', '')}")
                print(f"  Readiness status: {result.get('readiness_status', '')}")
                if result.get("missing_artifacts"):
                    print(f"  Missing: {', '.join(result['missing_artifacts'])}")
                if result.get("invalid_artifacts"):
                    print(f"  Invalid: {', '.join(result['invalid_artifacts'])}")
                if result.get("blocking_reasons"):
                    print(f"  Blocking: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-preflight-freeze":
        try:
            from atlas_agent.research.provider_preflight_freeze import create_provider_preflight_freeze
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-preflight-freeze skipped safely: no workspace found")
                return 1

            result = create_provider_preflight_freeze(ws, args.provider_execution_readiness_report_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider preflight freeze {result.get('provider_preflight_freeze_id')}: {result.get('freeze_status')} ({result.get('freeze_recommendation')})")
        return 0
    if args.command == "research" and args.research_command == "provider-preflight-freeze-list":
        try:
            from atlas_agent.research.provider_preflight_freeze import iter_provider_preflight_freeze_artifacts
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-preflight-freeze-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_preflight_freeze_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-preflight-freeze-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_preflight_freezes_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            if not items:
                print("No provider preflight freeze artifacts found.")
            else:
                print(f"{'Created At':<24} {'Symbol':<8} {'Freeze ID':<34} {'Status':<24} {'Artifact'}")
                for item in items:
                    print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_preflight_freeze_id', ''):<34} {item.get('freeze_status', ''):<24} {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-preflight-freeze-show":
        try:
            from atlas_agent.research.provider_preflight_freeze import (
                find_provider_preflight_freeze_by_id,
                load_and_validate_provider_preflight_freeze,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-preflight-freeze-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_preflight_freeze_id)
            freeze_path = find_provider_preflight_freeze_by_id(ws, safe_id)
            if freeze_path is None:
                raise ResearchSessionError("provider_preflight_freeze_not_found")
            artifact = load_and_validate_provider_preflight_freeze(freeze_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_preflight_freeze_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider preflight freeze")
            print(f"  Freeze ID: {artifact.get('provider_preflight_freeze_id', '')}")
            print(f"  Symbol: {artifact.get('symbol', '')}")
            print(f"  Freeze status: {artifact.get('freeze_status', '')}")
            print(f"  Freeze recommendation: {artifact.get('freeze_recommendation', '')}")
            print(f"  Readiness score: {artifact.get('readiness_score', 0)}")
            print(f"  Chain health: {artifact.get('chain_health', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-preflight-freeze-validate":
        try:
            from atlas_agent.research.provider_preflight_freeze import (
                find_provider_preflight_freeze_by_id,
                validate_provider_preflight_freeze_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-preflight-freeze-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_preflight_freeze_id)
            freeze_path = find_provider_preflight_freeze_by_id(ws, safe_id)
            if freeze_path is None:
                raise ResearchSessionError("provider_preflight_freeze_not_found")
            validation = validate_provider_preflight_freeze_artifact(freeze_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_preflight_freeze_validated",
                "provider_preflight_freeze_id": safe_id,
                "valid": validation.valid,
                "passed_checks": validation.passed_checks,
                "failed_checks": validation.failed_checks,
                "checks": validation.checks,
                "warnings": validation.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "valid" if validation.valid else "invalid"
            print(f"Provider preflight freeze validation {safe_id}: {status_str}")
            print(f"  Passed: {validation.passed_checks}")
            print(f"  Failed: {validation.failed_checks}")
        if args.strict and not validation.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-preflight-freeze-replay":
        try:
            from atlas_agent.research.provider_preflight_freeze import replay_provider_preflight_freeze
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-preflight-freeze-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_preflight_freeze_id)
            replay_result = replay_provider_preflight_freeze(safe_id, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_preflight_freeze_replayed",
                "provider_preflight_freeze_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            status_str = "matches" if replay_result["match"] else "mismatch"
            print(f"Provider preflight freeze replay {safe_id}: {status_str}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-preflight-freeze-summary":
        try:
            from atlas_agent.research.provider_preflight_freeze import summarize_provider_preflight_freeze_for_run
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-preflight-freeze-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_preflight_freeze_for_run(safe_id, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-preflight-freeze-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-preflight-freeze-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Preflight freeze summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
                print(f"  Warnings: {result.get('warnings', [])}")
            else:
                print(f"Preflight freeze summary for run {safe_id}:")
                print(f"  Symbol: {result.get('symbol', '')}")
                print(f"  Freeze status: {result.get('freeze_status', '')}")
                print(f"  Freeze recommendation: {result.get('freeze_recommendation', '')}")
                print(f"  Provider execution allowed: {result.get('provider_execution_allowed', False)}")
                if result.get("blocking_reasons"):
                    print(f"  Blocking: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-opt-in-policy":
        try:
            from atlas_agent.research.provider_opt_in_policy import create_provider_opt_in_policy
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-opt-in-policy skipped safely: no workspace found")
                return 1

            result = create_provider_opt_in_policy(ws, args.provider_preflight_freeze_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider opt-in policy {result.get('provider_opt_in_policy_id')}: {result.get('policy_status')} ({result.get('opt_in_state')})")
        return 0
    if args.command == "research" and args.research_command == "provider-opt-in-policy-list":
        try:
            from atlas_agent.research.provider_opt_in_policy import iter_provider_opt_in_policy_artifacts
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-opt-in-policy-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = max(1, min(args.limit, 100))
            items = iter_provider_opt_in_policy_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-opt-in-policy-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_opt_in_policies_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"{'Created At':<24} {'Symbol':<8} {'Policy ID':<34} {'Status':<24} {'Artifact'}")
            for item in items:
                print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_opt_in_policy_id', ''):<34} {item.get('policy_status', ''):<24} {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-opt-in-policy-show":
        try:
            from atlas_agent.research.provider_opt_in_policy import (
                find_provider_opt_in_policy_by_id,
                load_provider_opt_in_policy,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-opt-in-policy-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_opt_in_policy_id)
            policy_path = find_provider_opt_in_policy_by_id(ws, safe_id)
            if policy_path is None:
                raise ResearchSessionError("provider_opt_in_policy_not_found")
            artifact = load_provider_opt_in_policy(policy_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_opt_in_policy_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider opt-in policy {artifact.get('provider_opt_in_policy_id')}:")
            print(f"  Symbol: {artifact.get('symbol', '')}")
            print(f"  Policy status: {artifact.get('policy_status', '')}")
            print(f"  Opt-in state: {artifact.get('opt_in_state', '')}")
            print(f"  Provider execution allowed: {artifact.get('provider_call_allowed', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-opt-in-policy-validate":
        try:
            from atlas_agent.research.provider_opt_in_policy import (
                find_provider_opt_in_policy_by_id,
                validate_provider_opt_in_policy_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-opt-in-policy-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_opt_in_policy_id)
            policy_path = find_provider_opt_in_policy_by_id(ws, safe_id)
            if policy_path is None:
                raise ResearchSessionError("provider_opt_in_policy_not_found")
            validation = validate_provider_opt_in_policy_artifact(policy_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_opt_in_policy_validated",
                "provider_opt_in_policy_id": safe_id,
                "valid": validation.valid,
                "passed_checks": validation.passed_checks,
                "failed_checks": validation.failed_checks,
                "checks": validation.checks,
                "warnings": validation.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider opt-in policy {safe_id}: {'valid' if validation.valid else 'invalid'}")
            print(f"  Passed: {validation.passed_checks}")
            print(f"  Failed: {validation.failed_checks}")
        if args.strict and not validation.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-opt-in-policy-replay":
        try:
            from atlas_agent.research.provider_opt_in_policy import replay_provider_opt_in_policy
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-opt-in-policy-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_opt_in_policy_id)
            replay_result = replay_provider_opt_in_policy(safe_id, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_opt_in_policy_replayed",
                "provider_opt_in_policy_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider opt-in policy {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Expected hash: {replay_result['expected_hash']}")
            print(f"  Actual hash: {replay_result['actual_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-opt-in-policy-summary":
        try:
            from atlas_agent.research.provider_opt_in_policy import summarize_provider_opt_in_policy_for_run
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-opt-in-policy-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_opt_in_policy_for_run(safe_id, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-opt-in-policy-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-opt-in-policy-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Opt-in policy summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
                print(f"  Warnings: {result.get('warnings', [])}")
            else:
                print(f"Opt-in policy summary for run {safe_id}:")
                print(f"  Symbol: {result.get('symbol', '')}")
                print(f"  Policy status: {result.get('policy_status', '')}")
                print(f"  Opt-in state: {result.get('opt_in_state', '')}")
                print(f"  Provider execution allowed: {result.get('provider_execution_allowed', False)}")
                if result.get("blocking_reasons"):
                    print(f"  Blocking: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-credential-boundary":
        try:
            from atlas_agent.research.provider_credential_boundary import create_provider_credential_boundary
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-credential-boundary skipped safely: no workspace found")
                return 1

            result = create_provider_credential_boundary(ws, args.provider_opt_in_policy_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider credential boundary {result.get('provider_credential_boundary_id')}: {result.get('credential_boundary_status')} ({result.get('credential_loading_state')})")
        return 0
    if args.command == "research" and args.research_command == "provider-credential-boundary-list":
        try:
            from atlas_agent.research.provider_credential_boundary import iter_provider_credential_boundary_artifacts
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-credential-boundary-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = max(1, min(args.limit, 100))
            items = iter_provider_credential_boundary_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-credential-boundary-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_credential_boundaries_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"{'Created At':<24} {'Symbol':<8} {'Boundary ID':<34} {'Status':<24} {'Artifact'}")
            for item in items:
                print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_credential_boundary_id', ''):<34} {item.get('credential_boundary_status', ''):<24} {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-credential-boundary-show":
        try:
            from atlas_agent.research.provider_credential_boundary import (
                find_provider_credential_boundary_by_id,
                load_provider_credential_boundary,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-credential-boundary-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_credential_boundary_id)
            boundary_path = find_provider_credential_boundary_by_id(ws, safe_id)
            if boundary_path is None:
                raise ResearchSessionError("provider_credential_boundary_not_found")
            artifact = load_provider_credential_boundary(boundary_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_credential_boundary_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider credential boundary {artifact.get('provider_credential_boundary_id')}:")
            print(f"  Symbol: {artifact.get('symbol', '')}")
            print(f"  Credential boundary status: {artifact.get('credential_boundary_status', '')}")
            print(f"  Credential loading state: {artifact.get('credential_loading_state', '')}")
            print(f"  Provider execution allowed: {artifact.get('provider_call_allowed', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-credential-boundary-validate":
        try:
            from atlas_agent.research.provider_credential_boundary import (
                find_provider_credential_boundary_by_id,
                validate_provider_credential_boundary_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-credential-boundary-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_credential_boundary_id)
            boundary_path = find_provider_credential_boundary_by_id(ws, safe_id)
            if boundary_path is None:
                raise ResearchSessionError("provider_credential_boundary_not_found")
            validation = validate_provider_credential_boundary_artifact(boundary_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_credential_boundary_validated",
                "provider_credential_boundary_id": safe_id,
                "valid": validation.valid,
                "passed_checks": validation.passed_checks,
                "failed_checks": validation.failed_checks,
                "checks": validation.checks,
                "warnings": validation.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider credential boundary {safe_id}: {'valid' if validation.valid else 'invalid'}")
            print(f"  Passed: {validation.passed_checks}")
            print(f"  Failed: {validation.failed_checks}")
        if args.strict and not validation.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-credential-boundary-replay":
        try:
            from atlas_agent.research.provider_credential_boundary import replay_provider_credential_boundary
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-credential-boundary-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_credential_boundary_id)
            replay_result = replay_provider_credential_boundary(safe_id, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_credential_boundary_replayed",
                "provider_credential_boundary_id": safe_id,
                "match": replay_result["match"],
                "expected_hash": replay_result["expected_hash"],
                "actual_hash": replay_result["actual_hash"],
                "checks": replay_result["checks"],
                "warnings": replay_result["warnings"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider credential boundary {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Expected hash: {replay_result['expected_hash']}")
            print(f"  Actual hash: {replay_result['actual_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-credential-boundary-summary":
        try:
            from atlas_agent.research.provider_credential_boundary import summarize_provider_credential_boundary_for_run
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-credential-boundary-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_credential_boundary_for_run(safe_id, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-credential-boundary-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-credential-boundary-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Credential boundary summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
                print(f"  Warnings: {result.get('warnings', [])}")
            else:
                print(f"Credential boundary summary for run {safe_id}:")
                print(f"  Symbol: {result.get('symbol', '')}")
                print(f"  Credential boundary status: {result.get('credential_boundary_status', '')}")
                print(f"  Credential loading state: {result.get('credential_loading_state', '')}")
                print(f"  Credentials loaded: {result.get('credentials_loaded', False)}")
                print(f"  Env read attempted: {result.get('env_read_attempted', False)}")
                print(f"  Dotenv loaded: {result.get('dotenv_loaded', False)}")
                print(f"  Provider execution allowed: {result.get('provider_execution_allowed', False)}")
                if result.get("blocking_reasons"):
                    print(f"  Blocking: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-payload-preview":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import create_provider_outbound_payload_preview
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-payload-preview skipped safely: no workspace found")
                return 1

            result = create_provider_outbound_payload_preview(ws, args.provider_credential_boundary_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider outbound payload preview {result.get('provider_outbound_payload_preview_id')}: {result.get('payload_preview_status')}")
            print(f"  Payload body stored: {result.get('payload_body_stored', False)}")
            print(f"  Outbound request sent: {result.get('outbound_request_sent', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-payload-preview-list":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import iter_provider_outbound_payload_preview_artifacts
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-payload-preview-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = max(1, min(args.limit, 100))
            items = iter_provider_outbound_payload_preview_artifacts(ws, symbol=symbol_filter)[:limit]
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-payload-preview-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-list", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_outbound_payload_previews_listed",
                "items": items,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"{'Created At':<24} {'Symbol':<8} {'Preview ID':<34} {'Status':<24} {'Artifact'}")
            for item in items:
                print(f"{item.get('created_at', ''):<24} {item.get('symbol', ''):<8} {item.get('provider_outbound_payload_preview_id', ''):<34} {item.get('payload_preview_status', ''):<24} {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-payload-preview-show":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import (
                find_provider_outbound_payload_preview_by_id,
                load_provider_outbound_payload_preview,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-payload-preview-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_outbound_payload_preview_id)
            preview_path = find_provider_outbound_payload_preview_by_id(ws, safe_id)
            if preview_path is None:
                raise ResearchSessionError("provider_outbound_payload_preview_not_found")
            artifact = load_provider_outbound_payload_preview(preview_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_outbound_payload_preview_loaded",
                "artifact": artifact,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider outbound payload preview {safe_id}:")
            print(f"  Status: {artifact.get('payload_preview_status', '')}")
            print(f"  Scope: {artifact.get('payload_preview_scope', '')}")
            print(f"  Provider: {artifact.get('provider_id', '')}")
            print(f"  Model: {artifact.get('model_id', '')}")
            print(f"  Payload body stored: {artifact.get('payload_body_stored', False)}")
            print(f"  Outbound request sent: {artifact.get('outbound_request_sent', False)}")
            print(f"  Artifact: {artifact.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-payload-preview-validate":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import (
                find_provider_outbound_payload_preview_by_id,
                validate_provider_outbound_payload_preview_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-payload-preview-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_outbound_payload_preview_id)
            preview_path = find_provider_outbound_payload_preview_by_id(ws, safe_id)
            if preview_path is None:
                raise ResearchSessionError("provider_outbound_payload_preview_not_found")
            validation = validate_provider_outbound_payload_preview_artifact(preview_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_outbound_payload_preview_validated",
                "provider_outbound_payload_preview_id": safe_id,
                "valid": validation.valid,
                "passed_checks": validation.passed_checks,
                "failed_checks": validation.failed_checks,
                "checks": validation.checks,
                "warnings": validation.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider outbound payload preview {safe_id}: {'valid' if validation.valid else 'invalid'}")
            print(f"  Passed: {validation.passed_checks}")
            print(f"  Failed: {validation.failed_checks}")
        if args.strict and not validation.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-payload-preview-replay":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import replay_provider_outbound_payload_preview
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-payload-preview-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_outbound_payload_preview_id)
            replay_result = replay_provider_outbound_payload_preview(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_outbound_payload_preview_replayed",
                "provider_outbound_payload_preview_id": safe_id,
                "match": replay_result["match"],
                "original_hash": replay_result["original_hash"],
                "replayed_hash": replay_result["replayed_hash"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider outbound payload preview {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Original hash: {replay_result['original_hash']}")
            print(f"  Replayed hash: {replay_result['replayed_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-payload-preview-summary":
        try:
            from atlas_agent.research.provider_outbound_payload_preview import summarize_provider_outbound_payload_preview_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-payload-preview-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_outbound_payload_preview_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-payload-preview-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-payload-preview-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Payload preview summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
                print(f"  Warnings: {result.get('warnings', [])}")
            else:
                print(f"Payload preview summary for run {safe_id}:")
                print(f"  Preview ID: {result.get('provider_outbound_payload_preview_id') or 'none'}")
                print(f"  Status: {result.get('payload_preview_status', '')}")
                print(f"  Payload body stored: {result.get('payload_body_stored', False)}")
                print(f"  Outbound request sent: {result.get('outbound_request_sent', False)}")
                print(f"  Credentials loaded: {result.get('credentials_loaded', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-intake-policy":
        try:
            from atlas_agent.research.provider_response_intake_policy import create_provider_response_intake_policy
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-intake-policy skipped safely: no workspace found")
                return 1

            result = create_provider_response_intake_policy(ws, args.provider_outbound_payload_preview_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-intake-policy", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-intake-policy", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider response intake policy {result.get('provider_response_intake_policy_id')}: {result.get('response_intake_policy_status')}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Source preview ID: {result.get('source_provider_outbound_payload_preview_id')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-intake-policy-list":
        try:
            from atlas_agent.research.provider_response_intake_policy import iter_provider_response_intake_policy_artifacts
            from atlas_agent.research.session import (
                InvalidResearchSymbolError,
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-intake-policy-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)
            items = iter_provider_response_intake_policy_artifacts(ws, symbol=symbol_filter)
        except InvalidResearchSymbolError:
            if args.json:
                _research_error_json("invalid_research_symbol", "Invalid research symbol.")
            else:
                print("research provider-response-intake-policy-list skipped safely: invalid research symbol")
            return 1
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-intake-policy-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-intake-policy-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_response_intake_policy_list", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider response intake policies")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('artifact_path', '')} — {item.get('error_code', 'unknown')}")
                else:
                    print(f"  {item.get('provider_response_intake_policy_id', '')}: {item.get('response_intake_policy_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-intake-policy-show":
        try:
            from atlas_agent.research.provider_response_intake_policy import (
                find_provider_response_intake_policy_by_id,
                load_provider_response_intake_policy,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-intake-policy-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_response_intake_policy_id)
            path = find_provider_response_intake_policy_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-response-intake-policy-show skipped safely: artifact not found")
                return 1
            data = load_provider_response_intake_policy(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-intake-policy-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-intake-policy-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_intake_policy_shown",
                "provider_response_intake_policy_id": data.get("provider_response_intake_policy_id", ""),
                "response_intake_policy_status": data.get("response_intake_policy_status", ""),
                "response_intake_policy_scope": data.get("response_intake_policy_scope", ""),
                "provider_id": data.get("provider_id", ""),
                "model_id": data.get("model_id", ""),
                "artifact_path": data.get("artifact_path", ""),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response intake policy {data.get('provider_response_intake_policy_id', '')}")
            print(f"  Status: {data.get('response_intake_policy_status', '')}")
            print(f"  Scope: {data.get('response_intake_policy_scope', '')}")
            print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-intake-policy-validate":
        try:
            from atlas_agent.research.provider_response_intake_policy import (
                find_provider_response_intake_policy_by_id,
                validate_provider_response_intake_policy_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-intake-policy-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_response_intake_policy_id)
            path = find_provider_response_intake_policy_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-response-intake-policy-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_response_intake_policy_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-intake-policy-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-intake-policy-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": result.valid,
                "status": "research_provider_response_intake_policy_validated" if result.valid else "research_provider_response_intake_policy_invalid",
                "provider_response_intake_policy_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response intake policy {safe_id}: {'valid' if result.valid else 'invalid'}")
            print(f"  Passed: {result.passed_checks}, Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-response-intake-policy-replay":
        try:
            from atlas_agent.research.provider_response_intake_policy import replay_provider_response_intake_policy
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-intake-policy-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.provider_response_intake_policy_id)
            replay_result = replay_provider_response_intake_policy(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-intake-policy-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-intake-policy-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_intake_policy_replayed",
                "provider_response_intake_policy_id": safe_id,
                "match": replay_result["match"],
                "original_hash": replay_result["original_hash"],
                "replayed_hash": replay_result["replayed_hash"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response intake policy {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Original hash: {replay_result['original_hash']}")
            print(f"  Replayed hash: {replay_result['replayed_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-response-intake-policy-summary":
        try:
            from atlas_agent.research.provider_response_intake_policy import summarize_provider_response_intake_policy_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-intake-policy-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_response_intake_policy_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-intake-policy-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-intake-policy-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Response intake policy summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
            else:
                print(f"Response intake policy summary for run {safe_id}:")
                print(f"  Policy ID: {result.get('provider_response_intake_policy_id') or 'none'}")
                print(f"  Status: {result.get('response_intake_policy_status', '')}")
                print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
                print(f"  Provider response received: {result.get('provider_response_received', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-request-response-pairing":
        try:
            from atlas_agent.research.provider_request_response_pairing import create_provider_request_response_pairing
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.intake_policy_id)
            result = create_provider_request_response_pairing(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairing created: {result.get('provider_request_response_pairing_id', '')}")
            print(f"  Source intake policy: {result.get('source_provider_response_intake_policy_id', '')}")
            print(f"  Status: {result.get('pairing_status', '')}")
            print(f"  State: {result.get('pairing_state', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-request-response-pairing-list":
        try:
            from atlas_agent.research.provider_request_response_pairing import iter_provider_request_response_pairing_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-list skipped safely: no workspace found")
                return 1

            safe_symbol = args.symbol.strip().upper() if args.symbol else None
            if safe_symbol:
                safe_symbol = sanitize_symbol(safe_symbol)
            limit = max(1, min(args.limit, 100))
            items = iter_provider_request_response_pairing_artifacts(ws, symbol=safe_symbol)
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_request_response_pairing_list", "items": items}, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairings ({len(items)}):")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_request_response_pairing_id', '')}: {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_request_response_pairing_id', '')}: {item.get('pairing_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-request-response-pairing-show":
        try:
            from atlas_agent.research.provider_request_response_pairing import (
                find_provider_request_response_pairing_by_id,
                load_provider_request_response_pairing,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.pairing_id)
            path = find_provider_request_response_pairing_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-request-response-pairing-show skipped safely: artifact not found")
                return 1
            data = load_provider_request_response_pairing(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_request_response_pairing_shown",
                "provider_request_response_pairing_id": safe_id,
                "pairing_status": data.get("pairing_status"),
                "pairing_state": data.get("pairing_state"),
                "request_response_pair_completed": data.get("request_response_pair_completed"),
                "future_response_artifact_present": data.get("future_response_artifact_present"),
                "provider_response_trusted": data.get("provider_response_trusted"),
                "artifact_path": data.get("artifact_path"),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairing {safe_id}:")
            print(f"  Status: {data.get('pairing_status', '')}")
            print(f"  State: {data.get('pairing_state', '')}")
            print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-request-response-pairing-validate":
        try:
            from atlas_agent.research.provider_request_response_pairing import (
                find_provider_request_response_pairing_by_id,
                validate_provider_request_response_pairing_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.pairing_id)
            path = find_provider_request_response_pairing_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-request-response-pairing-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_request_response_pairing_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_request_response_pairing_validated",
                "provider_request_response_pairing_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairing {safe_id}: {'valid' if result.valid else 'invalid'}")
            print(f"  Passed: {result.passed_checks}, Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-request-response-pairing-replay":
        try:
            from atlas_agent.research.provider_request_response_pairing import replay_provider_request_response_pairing
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.pairing_id)
            replay_result = replay_provider_request_response_pairing(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_request_response_pairing_replayed",
                "provider_request_response_pairing_id": safe_id,
                "match": replay_result["match"],
                "original_hash": replay_result["original_hash"],
                "replayed_hash": replay_result["replayed_hash"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider request/response pairing {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Original hash: {replay_result['original_hash']}")
            print(f"  Replayed hash: {replay_result['replayed_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-request-response-pairing-summary":
        try:
            from atlas_agent.research.provider_request_response_pairing import summarize_provider_request_response_pairing_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_request_response_pairing_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Request/response pairing summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
            else:
                print(f"Request/response pairing summary for run {safe_id}:")
                print(f"  Pairing ID: {result.get('provider_request_response_pairing_id') or 'none'}")
                print(f"  Status: {result.get('pairing_status', '')}")
                print(f"  State: {result.get('pairing_state', '')}")
                print(f"  Pair completed: {result.get('request_response_pair_completed', False)}")
                print(f"  Future response present: {result.get('future_response_artifact_present', False)}")
                print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-request-response-pairing-doctor":
        try:
            from atlas_agent.research.provider_request_response_pairing import doctor_provider_request_response_pairing
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-request-response-pairing-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_request_response_pairing(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-request-response-pairing-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-request-response-pairing-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Request/response pairing doctor for run {safe_id}:")
            print(f"  Health: {result.get('pairing_health', '')}")
            print(f"  Pair completed: {result.get('request_response_pair_completed', False)}")
            print(f"  Future response present: {result.get('future_response_artifact_present', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            if result.get("missing_artifacts"):
                print(f"  Missing artifacts: {', '.join(result['missing_artifacts'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-schema-contract":
        try:
            from atlas_agent.research.provider_response_schema_contract import create_provider_response_schema_contract
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-schema-contract skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.pairing_id)
            result = create_provider_response_schema_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-schema-contract", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-schema-contract", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider response schema contract created: {result.get('provider_response_schema_contract_id', '')}")
            print(f"  Source pairing: {result.get('source_provider_request_response_pairing_id', '')}")
            print(f"  Status: {result.get('response_schema_status', '')}")
            print(f"  State: {result.get('response_schema_state', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-schema-contract-list":
        try:
            from atlas_agent.research.provider_response_schema_contract import iter_provider_response_schema_contract_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-schema-contract-list skipped safely: no workspace found")
                return 1

            safe_symbol = args.symbol.strip().upper() if args.symbol else None
            if safe_symbol:
                safe_symbol = sanitize_symbol(safe_symbol)
            limit = max(1, min(args.limit, 100))
            items = iter_provider_response_schema_contract_artifacts(ws, symbol=safe_symbol)
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-schema-contract-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-schema-contract-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_response_schema_contract_list", "items": items}, indent=2, sort_keys=True))
        else:
            print(f"Provider response schema contracts ({len(items)}):")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_response_schema_contract_id', '')}: {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_response_schema_contract_id', '')}: {item.get('response_schema_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-schema-contract-show":
        try:
            from atlas_agent.research.provider_response_schema_contract import (
                find_provider_response_schema_contract_by_id,
                load_provider_response_schema_contract,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-schema-contract-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            path = find_provider_response_schema_contract_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-response-schema-contract-show skipped safely: artifact not found")
                return 1
            data = load_provider_response_schema_contract(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-schema-contract-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-schema-contract-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_schema_contract_shown",
                "provider_response_schema_contract_id": safe_id,
                "response_schema_status": data.get("response_schema_status"),
                "response_schema_state": data.get("response_schema_state"),
                "manual_review_gate_open": data.get("manual_review_gate_open"),
                "future_response_artifact_present": data.get("future_response_artifact_present"),
                "provider_response_trusted": data.get("provider_response_trusted"),
                "artifact_path": data.get("artifact_path"),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response schema contract {safe_id}:")
            print(f"  Status: {data.get('response_schema_status', '')}")
            print(f"  State: {data.get('response_schema_state', '')}")
            print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-schema-contract-validate":
        try:
            from atlas_agent.research.provider_response_schema_contract import (
                find_provider_response_schema_contract_by_id,
                validate_provider_response_schema_contract_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-schema-contract-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            path = find_provider_response_schema_contract_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-response-schema-contract-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_response_schema_contract_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-schema-contract-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-schema-contract-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_schema_contract_validated",
                "provider_response_schema_contract_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response schema contract {safe_id}: {'valid' if result.valid else 'invalid'}")
            print(f"  Passed: {result.passed_checks}, Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-response-schema-contract-replay":
        try:
            from atlas_agent.research.provider_response_schema_contract import replay_provider_response_schema_contract
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-schema-contract-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            replay_result = replay_provider_response_schema_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-schema-contract-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-schema-contract-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_schema_contract_replayed",
                "provider_response_schema_contract_id": safe_id,
                "match": replay_result["match"],
                "original_hash": replay_result["original_hash"],
                "replayed_hash": replay_result["replayed_hash"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response schema contract {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Original hash: {replay_result['original_hash']}")
            print(f"  Replayed hash: {replay_result['replayed_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-response-schema-contract-summary":
        try:
            from atlas_agent.research.provider_response_schema_contract import summarize_provider_response_schema_contract_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-schema-contract-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_response_schema_contract_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-schema-contract-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-schema-contract-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Response schema contract summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
            else:
                print(f"Response schema contract summary for run {safe_id}:")
                print(f"  Contract ID: {result.get('provider_response_schema_contract_id') or 'none'}")
                print(f"  Status: {result.get('response_schema_status', '')}")
                print(f"  State: {result.get('response_schema_state', '')}")
                print(f"  Manual review gate open: {result.get('manual_review_gate_open', False)}")
                print(f"  Future response present: {result.get('future_response_artifact_present', False)}")
                print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-schema-contract-doctor":
        try:
            from atlas_agent.research.provider_response_schema_contract import doctor_provider_response_schema_contract
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-schema-contract-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_response_schema_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-schema-contract-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-schema-contract-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Response schema contract doctor for run {safe_id}:")
            print(f"  Health: {result.get('schema_health', '')}")
            print(f"  Manual review gate open: {result.get('manual_review_gate_open', False)}")
            print(f"  Future response present: {result.get('future_response_artifact_present', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            if result.get("missing_artifacts"):
                print(f"  Missing artifacts: {', '.join(result['missing_artifacts'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-review-result":
        try:
            from atlas_agent.research.provider_response_review_result import create_provider_response_review_result
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-review-result skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.schema_contract_id)
            result = create_provider_response_review_result(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-review-result", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-review-result", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider response review result created: {result.get('provider_response_review_result_id', '')}")
            print(f"  Source schema contract: {result.get('source_provider_response_schema_contract_id', '')}")
            print(f"  Status: {result.get('review_result_status', '')}")
            print(f"  State: {result.get('review_result_state', '')}")
            print(f"  Decision: {result.get('review_decision', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-review-result-list":
        try:
            from atlas_agent.research.provider_response_review_result import iter_provider_response_review_result_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-review-result-list skipped safely: no workspace found")
                return 1

            safe_symbol = args.symbol.strip().upper() if args.symbol else None
            if safe_symbol:
                safe_symbol = sanitize_symbol(safe_symbol)
            limit = max(1, min(args.limit, 100))
            items = iter_provider_response_review_result_artifacts(ws, symbol=safe_symbol)
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-review-result-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-review-result-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_response_review_result_list", "items": items}, indent=2, sort_keys=True))
        else:
            print(f"Provider response review results ({len(items)}):")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_response_review_result_id', '')}: {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_response_review_result_id', '')}: {item.get('review_result_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-review-result-show":
        try:
            from atlas_agent.research.provider_response_review_result import (
                find_provider_response_review_result_by_id,
                load_provider_response_review_result,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-review-result-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.review_result_id)
            path = find_provider_response_review_result_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-response-review-result-show skipped safely: artifact not found")
                return 1
            data = load_provider_response_review_result(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-review-result-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-review-result-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_review_result_shown",
                "provider_response_review_result_id": safe_id,
                "review_result_status": data.get("review_result_status"),
                "review_result_state": data.get("review_result_state"),
                "review_decision": data.get("review_decision"),
                "manual_review_gate_open": data.get("manual_review_gate_open"),
                "review_result_present": data.get("review_result_present"),
                "provider_response_trusted": data.get("provider_response_trusted"),
                "artifact_path": data.get("artifact_path"),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response review result {safe_id}:")
            print(f"  Status: {data.get('review_result_status', '')}")
            print(f"  State: {data.get('review_result_state', '')}")
            print(f"  Decision: {data.get('review_decision', '')}")
            print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-review-result-validate":
        try:
            from atlas_agent.research.provider_response_review_result import (
                find_provider_response_review_result_by_id,
                validate_provider_response_review_result_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-review-result-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.review_result_id)
            path = find_provider_response_review_result_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-response-review-result-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_response_review_result_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-review-result-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-review-result-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_review_result_validated",
                "provider_response_review_result_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response review result {safe_id}: {'valid' if result.valid else 'invalid'}")
            print(f"  Passed: {result.passed_checks}, Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-response-review-result-replay":
        try:
            from atlas_agent.research.provider_response_review_result import replay_provider_response_review_result
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-review-result-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.review_result_id)
            replay_result = replay_provider_response_review_result(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-review-result-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-review-result-replay", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_response_review_result_replayed",
                "provider_response_review_result_id": safe_id,
                "match": replay_result["match"],
                "original_hash": replay_result["original_hash"],
                "replayed_hash": replay_result["replayed_hash"],
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider response review result {safe_id}: {'match' if replay_result['match'] else 'mismatch'}")
            print(f"  Original hash: {replay_result['original_hash']}")
            print(f"  Replayed hash: {replay_result['replayed_hash']}")
        if args.strict and not replay_result["match"]:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-response-review-result-summary":
        try:
            from atlas_agent.research.provider_response_review_result import summarize_provider_response_review_result_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-review-result-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_response_review_result_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-review-result-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-review-result-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if not result.get("ok"):
                print(f"Response review result summary: {result.get('status', 'error')}")
                print(f"  Run ID: {safe_id}")
            else:
                print(f"Response review result summary for run {safe_id}:")
                print(f"  Review result ID: {result.get('provider_response_review_result_id') or 'none'}")
                print(f"  Status: {result.get('review_result_status', '')}")
                print(f"  State: {result.get('review_result_state', '')}")
                print(f"  Decision: {result.get('review_decision', '')}")
                print(f"  Review result present: {result.get('review_result_present', False)}")
                print(f"  Manual review gate open: {result.get('manual_review_gate_open', False)}")
                print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-response-review-result-doctor":
        try:
            from atlas_agent.research.provider_response_review_result import doctor_provider_response_review_result
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-response-review-result-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_response_review_result(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-response-review-result-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-response-review-result-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Response review result doctor for run {safe_id}:")
            print(f"  Health: {result.get('review_health', '')}")
            print(f"  Review result present: {result.get('review_result_present', False)}")
            print(f"  Manual review gate open: {result.get('manual_review_gate_open', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            if result.get("missing_artifacts"):
                print(f"  Missing artifacts: {', '.join(result['missing_artifacts'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-unlock-state":
        try:
            from atlas_agent.research.provider_execution_unlock_state import create_provider_execution_unlock_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-unlock-state skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.review_result_id)
            result = create_provider_execution_unlock_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider execution unlock state created:")
            print(f"  ID: {result.get('provider_execution_unlock_state_id', '')}")
            print(f"  Source review result: {result.get('source_provider_response_review_result_id', '')}")
            print(f"  Status: {result.get('unlock_state_status', '')}")
            print(f"  State: {result.get('unlock_state', '')}")
            print(f"  Current state: {result.get('current_state', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-unlock-state-list":
        try:
            from atlas_agent.research.provider_execution_unlock_state import iter_provider_execution_unlock_state_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-unlock-state-list skipped safely: no workspace found")
                return 1

            safe_symbol = args.symbol.strip().upper() if args.symbol else None
            if safe_symbol:
                safe_symbol = sanitize_symbol(safe_symbol)
            items = iter_provider_execution_unlock_state_artifacts(ws, symbol=safe_symbol)
            if args.limit:
                items = items[:args.limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_execution_unlock_state_list", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider execution unlock states:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_execution_unlock_state_id', '')}: {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_execution_unlock_state_id', '')}: {item.get('unlock_state_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-unlock-state-show":
        try:
            from atlas_agent.research.provider_execution_unlock_state import (
                find_provider_execution_unlock_state_by_id,
                load_provider_execution_unlock_state,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-unlock-state-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.unlock_state_id)
            path = find_provider_execution_unlock_state_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-execution-unlock-state-show skipped safely: artifact not found")
                return 1
            data = load_provider_execution_unlock_state(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_execution_unlock_state_shown",
                "provider_execution_unlock_state_id": data.get("provider_execution_unlock_state_id"),
                "unlock_state_status": data.get("unlock_state_status"),
                "unlock_state": data.get("unlock_state"),
                "current_state": data.get("current_state"),
                "manual_unlock_required": data.get("manual_unlock_required"),
                "manual_unlock_granted": data.get("manual_unlock_granted"),
                "provider_execution_unlocked": data.get("provider_execution_unlocked"),
                "provider_call_allowed": data.get("provider_call_allowed"),
                "artifact_path": data.get("artifact_path"),
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider execution unlock state:")
            print(f"  ID: {data.get('provider_execution_unlock_state_id', '')}")
            print(f"  Status: {data.get('unlock_state_status', '')}")
            print(f"  State: {data.get('unlock_state', '')}")
            print(f"  Current state: {data.get('current_state', '')}")
            print(f"  Provider: {data.get('provider_id', '')} / {data.get('model_id', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-unlock-state-validate":
        try:
            from atlas_agent.research.provider_execution_unlock_state import (
                find_provider_execution_unlock_state_by_id,
                validate_provider_execution_unlock_state_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-unlock-state-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.unlock_state_id)
            path = find_provider_execution_unlock_state_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-execution-unlock-state-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_execution_unlock_state_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-validate", message.lower().rstrip("."))
            return 2 if args.strict else 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": result.valid,
                "status": "research_provider_execution_unlock_state_validated",
                "provider_execution_unlock_state_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider execution unlock state validation: {result.valid}")
            for check in result.checks:
                status = "PASS" if check["passed"] else "FAIL"
                print(f"  [{status}] {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-unlock-state-replay":
        try:
            from atlas_agent.research.provider_execution_unlock_state import replay_provider_execution_unlock_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-unlock-state-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.unlock_state_id)
            result = replay_provider_execution_unlock_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution unlock state replay: {result.get('match', False)}")
            print(f"  ID: {result.get('provider_execution_unlock_state_id', '')}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-execution-unlock-state-summary":
        try:
            from atlas_agent.research.provider_execution_unlock_state import summarize_provider_execution_unlock_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-unlock-state-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_execution_unlock_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution unlock state summary for run {safe_id}:")
            print(f"  ID: {result.get('provider_execution_unlock_state_id', '')}")
            print(f"  Status: {result.get('unlock_state_status', '')}")
            print(f"  State: {result.get('unlock_state', '')}")
            print(f"  Current state: {result.get('current_state', '')}")
            print(f"  Provider execution unlocked: {result.get('provider_execution_unlocked', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Manual unlock granted: {result.get('manual_unlock_granted', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-execution-unlock-state-doctor":
        try:
            from atlas_agent.research.provider_execution_unlock_state import doctor_provider_execution_unlock_state
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-execution-unlock-state-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_execution_unlock_state(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-execution-unlock-state-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-execution-unlock-state-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider execution unlock state doctor for run {safe_id}:")
            print(f"  Health: {result.get('unlock_health', '')}")
            print(f"  Provider execution unlocked: {result.get('provider_execution_unlocked', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Manual unlock granted: {result.get('manual_unlock_granted', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-adapter-interface-contract":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import create_provider_adapter_interface_contract
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-adapter-interface-contract skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.unlock_state_id)
            result = create_provider_adapter_interface_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider adapter interface contract created:")
            print(f"  ID: {result.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Source unlock state: {result.get('source_provider_execution_unlock_state_id', '')}")
            print(f"  Status: {result.get('adapter_contract_status', '')}")
            print(f"  State: {result.get('adapter_state', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-list":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import iter_provider_adapter_interface_contract_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-adapter-interface-contract-list skipped safely: no workspace found")
                return 1

            safe_symbol = args.symbol.strip().upper() if args.symbol else None
            if safe_symbol:
                safe_symbol = sanitize_symbol(safe_symbol)
            items = iter_provider_adapter_interface_contract_artifacts(ws, symbol=safe_symbol)
            if args.limit:
                items = items[:args.limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-list", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({"ok": True, "status": "research_provider_adapter_interface_contract_list", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider adapter interface contracts:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_adapter_interface_contract_id', '')}: {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_adapter_interface_contract_id', '')}: {item.get('adapter_contract_status', '')} ({item.get('symbol', '')}) — {item.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-show":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import (
                find_provider_adapter_interface_contract_by_id,
                load_provider_adapter_interface_contract,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-adapter-interface-contract-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            path = find_provider_adapter_interface_contract_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-adapter-interface-contract-show skipped safely: artifact not found")
                return 1
            data = load_provider_adapter_interface_contract(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-show", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_adapter_interface_contract_shown",
                "artifact": data,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print("Provider adapter interface contract:")
            print(f"  ID: {data.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Status: {data.get('adapter_contract_status', '')}")
            print(f"  State: {data.get('adapter_state', '')}")
            print(f"  Adapter present: {data.get('adapter_present', False)}")
            print(f"  Adapter enabled: {data.get('adapter_enabled', False)}")
            print(f"  Real adapter implemented: {data.get('real_provider_adapter_implemented', False)}")
            print(f"  Provider call allowed: {data.get('provider_call_allowed', False)}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-validate":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import (
                find_provider_adapter_interface_contract_by_id,
                validate_provider_adapter_interface_contract_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-adapter-interface-contract-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            path = find_provider_adapter_interface_contract_by_id(ws, safe_id)
            if path is None:
                if args.json:
                    _research_error_json("research_artifact_not_found", "Research artifact not found.")
                else:
                    print("research provider-adapter-interface-contract-validate skipped safely: artifact not found")
                return 1
            result = validate_provider_adapter_interface_contract_artifact(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-validate", message.lower().rstrip("."))
            return 2 if args.strict else 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-validate", "research command failed")
            return 1
        if args.json:
            import json
            out = {
                "ok": True,
                "status": "research_provider_adapter_interface_contract_validated",
                "provider_adapter_interface_contract_id": safe_id,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "warnings": result.warnings,
            }
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"Provider adapter interface contract validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            for check in result.checks:
                print(f"    {'✓' if check['passed'] else '✗'} {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-replay":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import replay_provider_adapter_interface_contract
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-adapter-interface-contract-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            result = replay_provider_adapter_interface_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider adapter interface contract replay: {result.get('match', False)}")
            print(f"  ID: {result.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-summary":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import summarize_provider_adapter_interface_contract
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-adapter-interface-contract-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_adapter_interface_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider adapter interface contract summary for run {safe_id}:")
            print(f"  ID: {result.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Status: {result.get('adapter_contract_status', '')}")
            print(f"  State: {result.get('adapter_state', '')}")
            print(f"  Adapter present: {result.get('adapter_present', False)}")
            print(f"  Adapter enabled: {result.get('adapter_enabled', False)}")
            print(f"  Real adapter implemented: {result.get('real_provider_adapter_implemented', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-adapter-interface-contract-doctor":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import doctor_provider_adapter_interface_contract
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            from atlas_agent.workspace import resolve_workspace_path
            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-adapter-interface-contract-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_adapter_interface_contract(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-interface-contract-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-interface-contract-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider adapter interface contract doctor for run {safe_id}:")
            print(f"  Health: {result.get('adapter_health', '')}")
            print(f"  Adapter present: {result.get('adapter_present', False)}")
            print(f"  Adapter enabled: {result.get('adapter_enabled', False)}")
            print(f"  Real adapter implemented: {result.get('real_provider_adapter_implemented', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
        return 0
    if args.command == "research" and args.research_command == "provider-adapter-disabled-smoke":
        try:
            from atlas_agent.research.provider_adapter_interface_contract import run_disabled_adapter_smoke
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )

            safe_id = validate_run_id(args.contract_id)
            result = run_disabled_adapter_smoke(safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-adapter-disabled-smoke", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-adapter-disabled-smoke", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Disabled adapter smoke test: {'PASS' if result.get('ok') else 'FAIL'}")
            print(f"  Contract ID: {result.get('provider_adapter_interface_contract_id', '')}")
            print(f"  Send failed closed: {result.get('send_failed_closed', False)}")
            print(f"  Static safe error: {result.get('static_safe_error', False)}")
            print(f"  Provider response received: {result.get('provider_response_received', False)}")
            print(f"  Network call attempted: {result.get('network_call_attempted', False)}")
            print(f"  Credentials loaded: {result.get('credentials_loaded', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0 if result.get("ok") else 1
    if args.command == "research" and args.research_command == "provider-mock-response-simulate":
        try:
            from atlas_agent.research.provider_mock_response_simulation import create_provider_mock_response_simulation
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-simulate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.contract_id)
            result = create_provider_mock_response_simulation(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-simulate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-simulate", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response simulation created")
            print(f"  ID: {result.get('provider_mock_response_simulation_id', '')}")
            print(f"  Status: {result.get('mock_simulation_status', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            if result.get("warnings"):
                print(f"  Warnings: {len(result['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-list":
        try:
            from atlas_agent.research.provider_mock_response_simulation import iter_provider_mock_response_simulation_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_mock_response_simulation_artifacts(ws, symbol=symbol_filter)[:limit]

            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "provider_mock_response_simulations_listed",
                    "items": items,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                if not items:
                    print("No provider mock response simulation artifacts found.")
                else:
                    print(f"{'Created At':<24} {'Symbol':<8} {'Run ID':<34} {'Provider':<14} {'Status':<24} {'Artifact'}")
                    for item in items:
                        created = item.get("created_at", "")[:19]
                        print(f"{created:<24} {item['symbol']:<8} {item['source_run_id']:<34} {item['provider_id']:<14} {item['mock_simulation_status']:<24} {item['artifact_path']}")
            return 0
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-list", "research command failed")
            return 1
    if args.command == "research" and args.research_command == "provider-mock-response-show":
        try:
            from atlas_agent.research.provider_mock_response_simulation import (
                find_provider_mock_response_simulation_by_id,
                load_provider_mock_response_simulation,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.simulation_id)
            path = find_provider_mock_response_simulation_by_id(ws, safe_id)
            if not path:
                if args.json:
                    _research_error_json("not_found", "Provider mock response simulation not found.")
                else:
                    _research_error_text("research provider-mock-response-show", "not found")
                return 1

            data = load_provider_mock_response_simulation(path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-show", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation: {data.get('provider_mock_response_simulation_id', '')}")
            print(f"  Status: {data.get('mock_simulation_status', '')}")
            print(f"  State: {data.get('mock_simulation_state', '')}")
            print(f"  Provider: {data.get('provider_id', '')}")
            print(f"  Model: {data.get('model_id', '')}")
            print(f"  Mock adapter used: {data.get('mock_adapter_used', False)}")
            print(f"  Mock response simulated: {data.get('mock_response_simulated', False)}")
            print(f"  Mock only: {data.get('mock_only', False)}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
            if data.get("warnings"):
                print(f"  Warnings: {len(data['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-validate":
        try:
            from atlas_agent.research.provider_mock_response_simulation import (
                find_provider_mock_response_simulation_by_id,
                validate_provider_mock_response_simulation_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.simulation_id)
            path = find_provider_mock_response_simulation_by_id(ws, safe_id)
            if not path:
                if args.json:
                    _research_error_json("not_found", "Provider mock response simulation not found.")
                else:
                    _research_error_text("research provider-mock-response-validate", "not found")
                return 1

            result = validate_provider_mock_response_simulation_artifact(path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-validate", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps({
                "ok": result.valid,
                "status": "research_provider_mock_response_simulation_validated" if result.valid else "research_provider_mock_response_simulation_validation_failed",
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
                "warnings": result.warnings,
            }, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed checks: {result.passed_checks}")
            print(f"  Failed checks: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
            if result.warnings:
                for w in result.warnings:
                    print(f"  Warning: {w}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-replay":
        try:
            from atlas_agent.research.provider_mock_response_simulation import replay_provider_mock_response_simulation
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.simulation_id)
            result = replay_provider_mock_response_simulation(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation replay: {result.get('match', False)}")
            print(f"  ID: {result.get('provider_mock_response_simulation_id', '')}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-summary":
        try:
            from atlas_agent.research.provider_mock_response_simulation import summarize_provider_mock_response_simulation
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_simulation(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation summary for run {safe_id}:")
            print(f"  ID: {result.get('provider_mock_response_simulation_id', '')}")
            print(f"  Status: {result.get('mock_simulation_status', '')}")
            print(f"  State: {result.get('mock_simulation_state', '')}")
            print(f"  Mock response simulated: {result.get('mock_response_simulated', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Real provider request sent: {result.get('real_provider_request_sent', False)}")
            print(f"  Real provider response received: {result.get('real_provider_response_received', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-doctor":
        try:
            from atlas_agent.research.provider_mock_response_simulation import doctor_provider_mock_response_simulation
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_simulation(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response simulation doctor for run {safe_id}:")
            print(f"  Health: {result.get('mock_response_health', '')}")
            print(f"  Mock response simulated: {result.get('mock_response_simulated', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Real provider request sent: {result.get('real_provider_request_sent', False)}")
            print(f"  Real provider response received: {result.get('real_provider_response_received', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import create_provider_mock_response_import_candidate
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-import-candidate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.simulation_id)
            result = create_provider_mock_response_import_candidate(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response import candidate created")
            print(f"  ID: {result.get('provider_mock_response_import_candidate_id', '')}")
            print(f"  Source mock simulation: {result.get('source_provider_mock_response_simulation_id', '')}")
            print(f"  Status: {result.get('status', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            if result.get("warnings"):
                print(f"  Warnings: {len(result['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-list":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import iter_provider_mock_response_import_candidate_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-import-candidate-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_mock_response_import_candidate_artifacts(ws, symbol=symbol_filter)[:limit]

            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "provider_mock_response_import_candidates_listed",
                    "items": items,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                if not items:
                    print("No provider mock response import candidate artifacts found.")
                else:
                    print(f"{'Created At':<24} {'Symbol':<8} {'Run ID':<34} {'Provider':<14} {'Status':<24} {'Artifact'}")
                    for item in items:
                        created = item.get("created_at", "")[:19]
                        print(f"{created:<24} {item['symbol']:<8} {item['source_run_id']:<34} {item['provider_id']:<14} {item['mock_import_candidate_status']:<24} {item['artifact_path']}")
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-list", "research command failed")
            return 1
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-show":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import (
                find_provider_mock_response_import_candidate_by_id,
                load_and_validate_provider_mock_response_import_candidate,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-import-candidate-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.candidate_id)
            artifact_path = find_provider_mock_response_import_candidate_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    _research_error_json("candidate_not_found", "Provider mock response import candidate not found.")
                else:
                    _research_error_text("research provider-mock-response-import-candidate-show", "candidate not found")
                return 1

            data = load_and_validate_provider_mock_response_import_candidate(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-show", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate: {safe_id}")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider: {data.get('provider_id', '')}")
            print(f"  Model: {data.get('model_id', '')}")
            print(f"  Status: {data.get('mock_import_candidate_status', '')}")
            print(f"  State: {data.get('mock_import_candidate_state', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-validate":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import (
                find_provider_mock_response_import_candidate_by_id,
                validate_provider_mock_response_import_candidate_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-import-candidate-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.candidate_id)
            artifact_path = find_provider_mock_response_import_candidate_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    _research_error_json("candidate_not_found", "Provider mock response import candidate not found.")
                else:
                    _research_error_text("research provider-mock-response-import-candidate-validate", "candidate not found")
                return 1

            result = validate_provider_mock_response_import_candidate_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-validate", "research command failed")
            return 1
        if args.json:
            import json
            payload = {
                "ok": result.valid,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
                "warnings": result.warnings,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate validation: {safe_id}")
            print(f"  Valid: {result.valid}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            for c in result.checks:
                status = "PASS" if c["passed"] else "FAIL"
                print(f"  [{status}] {c['name']}: {c['message']}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-replay":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import replay_provider_mock_response_import_candidate
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-import-candidate-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.candidate_id)
            result = replay_provider_mock_response_import_candidate(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate replay: {safe_id}")
            print(f"  Match: {result.get('match', False)}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-summary":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import summarize_provider_mock_response_import_candidate
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-import-candidate-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_import_candidate(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate summary for run {safe_id}:")
            print(f"  Candidate ID: {result.get('provider_mock_response_import_candidate_id', 'None')}")
            print(f"  Status: {result.get('mock_import_candidate_status', '')}")
            print(f"  State: {result.get('mock_import_candidate_state', '')}")
            print(f"  Mock import candidate recorded: {result.get('mock_response_import_candidate_recorded', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Real provider response imported: {result.get('real_provider_response_imported', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-import-candidate-doctor":
        try:
            from atlas_agent.research.provider_mock_response_import_candidate import doctor_provider_mock_response_import_candidate
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-import-candidate-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_import_candidate(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-import-candidate-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-import-candidate-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response import candidate doctor for run {safe_id}:")
            print(f"  Health: {result.get('mock_import_health', '')}")
            print(f"  Mock import candidate recorded: {result.get('mock_response_import_candidate_recorded', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Real provider response imported: {result.get('real_provider_response_imported', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import create_provider_mock_response_review_sandbox
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-review-sandbox skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.import_candidate_id)
            result = create_provider_mock_response_review_sandbox(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response review sandbox created")
            print(f"  ID: {result.get('provider_mock_response_review_sandbox_id', '')}")
            print(f"  Source import candidate: {result.get('source_provider_mock_response_import_candidate_id', '')}")
            print(f"  Status: {result.get('status', '')}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            if result.get("warnings"):
                print(f"  Warnings: {len(result['warnings'])}")
            else:
                print("  Warnings: 0")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-list":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import iter_provider_mock_response_review_sandbox_artifacts
            from atlas_agent.research.session import (
                ResearchSessionError,
                sanitize_symbol,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-review-sandbox-list skipped safely: no workspace found")
                return 1

            symbol_filter = None
            if args.symbol:
                symbol_filter = sanitize_symbol(args.symbol)

            limit = args.limit
            if limit < 1:
                limit = 1
            if limit > 100:
                limit = 100

            items = iter_provider_mock_response_review_sandbox_artifacts(ws, symbol=symbol_filter)[:limit]

            if args.json:
                import json
                out = {
                    "ok": True,
                    "status": "provider_mock_response_review_sandboxes_listed",
                    "items": items,
                }
                print(json.dumps(out, indent=2, sort_keys=True))
            else:
                if not items:
                    print("No provider mock response review sandbox artifacts found.")
                else:
                    print(f"{'Created At':<24} {'Symbol':<8} {'Run ID':<34} {'Provider':<14} {'Status':<24} {'Artifact'}")
                    for item in items:
                        created = item.get("created_at", "")[:19]
                        print(f"{created:<24} {item['symbol']:<8} {item['source_run_id']:<34} {item['provider_id']:<14} {item['mock_review_sandbox_status']:<24} {item['artifact_path']}")
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-list", "research command failed")
            return 1
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-show":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import (
                find_provider_mock_response_review_sandbox_by_id,
                load_and_validate_provider_mock_response_review_sandbox,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-review-sandbox-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_id)
            artifact_path = find_provider_mock_response_review_sandbox_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    _research_error_json("sandbox_not_found", "Provider mock response review sandbox not found.")
                else:
                    _research_error_text("research provider-mock-response-review-sandbox-show", "sandbox not found")
                return 1

            data = load_and_validate_provider_mock_response_review_sandbox(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-show", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox: {safe_id}")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider: {data.get('provider_id', '')}")
            print(f"  Model: {data.get('model_id', '')}")
            print(f"  Status: {data.get('mock_review_sandbox_status', '')}")
            print(f"  State: {data.get('mock_review_sandbox_state', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-validate":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import (
                find_provider_mock_response_review_sandbox_by_id,
                validate_provider_mock_response_review_sandbox_artifact,
            )
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-review-sandbox-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_id)
            artifact_path = find_provider_mock_response_review_sandbox_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    _research_error_json("sandbox_not_found", "Provider mock response review sandbox not found.")
                else:
                    _research_error_text("research provider-mock-response-review-sandbox-validate", "sandbox not found")
                return 1

            result = validate_provider_mock_response_review_sandbox_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-validate", "research command failed")
            return 1
        if args.json:
            import json
            payload = {
                "ok": result.valid,
                "valid": result.valid,
                "passed_checks": result.passed_checks,
                "failed_checks": result.failed_checks,
                "checks": result.checks,
                "recommendation": result.recommendation,
                "warnings": result.warnings,
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox validation: {safe_id}")
            print(f"  Valid: {result.valid}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            for c in result.checks:
                status = "PASS" if c["passed"] else "FAIL"
                print(f"  [{status}] {c['name']}: {c['message']}")
            print(f"  Recommendation: {result.recommendation}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-replay":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import replay_provider_mock_response_review_sandbox
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-review-sandbox-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.sandbox_id)
            result = replay_provider_mock_response_review_sandbox(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-replay", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox replay: {safe_id}")
            print(f"  Match: {result.get('match', False)}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-summary":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import summarize_provider_mock_response_review_sandbox
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-review-sandbox-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_review_sandbox(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-summary", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox summary for run {safe_id}:")
            print(f"  Sandbox ID: {result.get('provider_mock_response_review_sandbox_id', 'None')}")
            print(f"  Status: {result.get('mock_review_sandbox_status', '')}")
            print(f"  State: {result.get('mock_review_sandbox_state', '')}")
            print(f"  Mock review sandbox recorded: {result.get('mock_review_sandbox_recorded', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Sandbox review only: {result.get('sandbox_review_only', False)}")
            print(f"  Real provider response reviewed: {result.get('real_provider_response_reviewed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-review-sandbox-doctor":
        try:
            from atlas_agent.research.provider_mock_response_review_sandbox import doctor_provider_mock_response_review_sandbox
            from atlas_agent.research.session import (
                ResearchSessionError,
                validate_run_id,
            )
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    import json
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-review-sandbox-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_review_sandbox(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-review-sandbox-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-review-sandbox-doctor", "research command failed")
            return 1
        if args.json:
            import json
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response review sandbox doctor for run {safe_id}:")
            print(f"  Health: {result.get('mock_review_health', '')}")
            print(f"  Mock review sandbox recorded: {result.get('mock_review_sandbox_recorded', False)}")
            print(f"  Mock only: {result.get('mock_only', False)}")
            print(f"  Sandbox review only: {result.get('sandbox_review_only', False)}")
            print(f"  Real provider response reviewed: {result.get('real_provider_response_reviewed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import create_provider_mock_response_trust_decision_blocker
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.review_sandbox_id)
            result = create_provider_mock_response_trust_decision_blocker(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response trust decision blocker created")
            print(f"  ID: {result.get('provider_mock_response_trust_decision_blocker_id', '')}")
            print(f"  Source review sandbox: {result.get('source_provider_mock_response_review_sandbox_id', '')}")
            print(f"  Provider ID: {result.get('provider_id', '')}")
            print(f"  Trust blocker active: {result.get('trust_blocker_active', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust decision explicitly blocked: {result.get('trust_decision_explicitly_blocked', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            print(f"  Warnings: {len(result.get('warnings', []))}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-list":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import iter_provider_mock_response_trust_decision_blocker_artifacts
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-list skipped safely: no workspace found")
                return 1

            items = iter_provider_mock_response_trust_decision_blocker_artifacts(ws, symbol=args.symbol)
            limit = max(1, min(args.limit, 100))
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-list", "research command failed")
            return 1
        if args.json:
            print(json.dumps({"ok": True, "status": "provider_mock_response_trust_decision_blockers_listed", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider mock response trust decision blockers:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_mock_response_trust_decision_blocker_id', '')} — {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_mock_response_trust_decision_blocker_id', '')} {item.get('symbol', '')} {item.get('trust_decision_blocker_status', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-show":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import (
                find_provider_mock_response_trust_decision_blocker_by_id,
                load_provider_mock_response_trust_decision_blocker,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.blocker_id)
            artifact_path = find_provider_mock_response_trust_decision_blocker_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "blocker_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider mock response trust decision blocker not found.")
                return 1
            data = load_provider_mock_response_trust_decision_blocker(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-show", "research command failed")
            return 1
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response trust decision blocker {safe_id}:")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider ID: {data.get('provider_id', '')}")
            print(f"  Status: {data.get('trust_decision_blocker_status', '')}")
            print(f"  State: {data.get('trust_decision_blocker_state', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-validate":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import (
                find_provider_mock_response_trust_decision_blocker_by_id,
                validate_provider_mock_response_trust_decision_blocker_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.blocker_id)
            artifact_path = find_provider_mock_response_trust_decision_blocker_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "blocker_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider mock response trust decision blocker not found.")
                return 1
            result = validate_provider_mock_response_trust_decision_blocker_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-validate", "research command failed")
            return 1
        payload = {
            "ok": True,
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "recommendation": result.recommendation,
            "warnings": result.warnings,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
            for check in result.checks:
                status_str = "PASS" if check["passed"] else "FAIL"
                print(f"  [{status_str}] {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-replay":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import replay_provider_mock_response_trust_decision_blocker
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.blocker_id)
            result = replay_provider_mock_response_trust_decision_blocker(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-replay", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Replay: {'MATCH' if result.get('match') else 'MISMATCH'}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-summary":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import summarize_provider_mock_response_trust_decision_blocker
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_trust_decision_blocker(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-summary", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response trust decision blocker summary for run {safe_id}:")
            print(f"  Blocker ID: {result.get('provider_mock_response_trust_decision_blocker_id', 'None')}")
            print(f"  Status: {result.get('trust_decision_blocker_status', '')}")
            print(f"  State: {result.get('trust_decision_blocker_state', '')}")
            print(f"  Trust blocker active: {result.get('trust_blocker_active', False)}")
            print(f"  Trust decision present: {result.get('trust_decision_present', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust decision explicitly blocked: {result.get('trust_decision_explicitly_blocked', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-trust-decision-blocker-doctor":
        try:
            import json
            from atlas_agent.research.provider_mock_response_trust_decision_blocker import doctor_provider_mock_response_trust_decision_blocker
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-trust-decision-blocker-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_trust_decision_blocker(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-trust-decision-blocker-doctor", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response trust decision blocker doctor for run {safe_id}:")
            print(f"  Health: {result.get('trust_health', '')}")
            print(f"  Trust blocker active: {result.get('trust_blocker_active', False)}")
            print(f"  Trust decision present: {result.get('trust_decision_present', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust decision explicitly blocked: {result.get('trust_decision_explicitly_blocked', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import create_provider_mock_response_final_safety_seal
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.blocker_id)
            result = create_provider_mock_response_final_safety_seal(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider mock response final safety seal created")
            print(f"  ID: {result.get('provider_mock_response_final_safety_seal_id', '')}")
            print(f"  Source trust decision blocker: {result.get('source_provider_mock_response_trust_decision_blocker_id', '')}")
            print(f"  Provider ID: {result.get('provider_id', '')}")
            print(f"  Final safety seal created: {result.get('final_safety_seal_created', False)}")
            print(f"  Mock pipeline complete: {result.get('mock_pipeline_complete', False)}")
            print(f"  Seal valid: {result.get('seal_valid', False)}")
            print(f"  Seal non-authorizing: {result.get('seal_non_authorizing', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            print(f"  Warnings: {len(result.get('warnings', []))}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-list":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import iter_provider_mock_response_final_safety_seal_artifacts
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-list skipped safely: no workspace found")
                return 1

            items = iter_provider_mock_response_final_safety_seal_artifacts(ws, symbol=args.symbol)
            limit = max(1, min(args.limit, 100))
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-list", "research command failed")
            return 1
        if args.json:
            print(json.dumps({"ok": True, "status": "provider_mock_response_final_safety_seals_listed", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider mock response final safety seals:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_mock_response_final_safety_seal_id', '')} — {item.get('error_code', '')}")
                else:
                    print(f"  {item.get('provider_mock_response_final_safety_seal_id', '')} {item.get('symbol', '')} {item.get('final_safety_seal_status', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-show":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import (
                find_provider_mock_response_final_safety_seal_by_id,
                load_provider_mock_response_final_safety_seal,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.seal_id)
            artifact_path = find_provider_mock_response_final_safety_seal_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "seal_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider mock response final safety seal not found.")
                return 1
            data = load_provider_mock_response_final_safety_seal(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-show", "research command failed")
            return 1
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response final safety seal {safe_id}:")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider ID: {data.get('provider_id', '')}")
            print(f"  Status: {data.get('final_safety_seal_status', '')}")
            print(f"  State: {data.get('final_safety_seal_state', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-validate":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import (
                find_provider_mock_response_final_safety_seal_by_id,
                validate_provider_mock_response_final_safety_seal_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.seal_id)
            artifact_path = find_provider_mock_response_final_safety_seal_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "seal_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider mock response final safety seal not found.")
                return 1
            result = validate_provider_mock_response_final_safety_seal_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-validate", "research command failed")
            return 1
        payload = {
            "ok": True,
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "recommendation": result.recommendation,
            "warnings": result.warnings,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
            for check in result.checks:
                status_str = "PASS" if check["passed"] else "FAIL"
                print(f"  [{status_str}] {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-replay":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import replay_provider_mock_response_final_safety_seal
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.seal_id)
            result = replay_provider_mock_response_final_safety_seal(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-replay", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Replay: {'MATCH' if result.get('match') else 'MISMATCH'}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-summary":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import summarize_provider_mock_response_final_safety_seal
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_mock_response_final_safety_seal(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-summary", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response final safety seal summary for run {safe_id}:")
            print(f"  Seal ID: {result.get('provider_mock_response_final_safety_seal_id', 'None')}")
            print(f"  Status: {result.get('final_safety_seal_status', '')}")
            print(f"  State: {result.get('final_safety_seal_state', '')}")
            print(f"  Final safety seal created: {result.get('final_safety_seal_created', False)}")
            print(f"  Mock pipeline complete: {result.get('mock_pipeline_complete', False)}")
            print(f"  Seal valid: {result.get('seal_valid', False)}")
            print(f"  Seal non-authorizing: {result.get('seal_non_authorizing', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-mock-response-final-safety-seal-doctor":
        try:
            import json
            from atlas_agent.research.provider_mock_response_final_safety_seal import doctor_provider_mock_response_final_safety_seal
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-mock-response-final-safety-seal-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_mock_response_final_safety_seal(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-mock-response-final-safety-seal-doctor", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider mock response final safety seal doctor for run {safe_id}:")
            print(f"  Health: {result.get('seal_health', '')}")
            print(f"  Final safety seal created: {result.get('final_safety_seal_created', False)}")
            print(f"  Mock pipeline complete: {result.get('mock_pipeline_complete', False)}")
            print(f"  Seal valid: {result.get('seal_valid', False)}")
            print(f"  Seal non-authorizing: {result.get('seal_non_authorizing', False)}")
            print(f"  Trust decision granted: {result.get('trust_decision_granted', False)}")
            print(f"  Trust decision present: {result.get('trust_decision_present', False)}")
            print(f"  Trust upgrade performed: {result.get('trust_upgrade_performed', False)}")
            print(f"  Provider response trusted: {result.get('provider_response_trusted', False)}")
            print(f"  Mock response trusted: {result.get('mock_response_trusted', False)}")
            print(f"  Provider call allowed: {result.get('provider_call_allowed', False)}")
            print(f"  Broker touched: {result.get('broker_touched', False)}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import create_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.seal_id)
            result = create_provider_safety_dossier(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider safety dossier created")
            print(f"  ID: {result.get('provider_safety_dossier_id', '')}")
            print(f"  Symbol: {result.get('symbol', '')}")
            print(f"  Provider ID: {result.get('provider_id', '')}")
            print(f"  Safety Verdict: {result.get('safety_verdict', '')}")
            print(f"  Sandbox Only: {result.get('sandbox_only', False)}")
            print(f"  Chain Complete: {result.get('chain_complete', False)}")
            print(f"  Artifact: {result.get('artifact_path', '')}")
            print(f"  Warnings: {len(result.get('warnings', []))}")
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier-list":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import iter_provider_safety_dossier_artifacts
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-list skipped safely: no workspace found")
                return 1

            items = iter_provider_safety_dossier_artifacts(ws, symbol=args.symbol, status_filter=args.status)
            limit = max(1, min(args.limit, 100))
            items = items[:limit]
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-list", "research command failed")
            return 1
        if args.json:
            print(json.dumps({"ok": True, "status": "provider_safety_dossiers_listed", "items": items}, indent=2, sort_keys=True))
        else:
            print("Provider safety dossiers:")
            for item in items:
                if item.get("_invalid"):
                    print(f"  [INVALID] {item.get('provider_safety_dossier_id', '')} — {item.get('safe_status', '')}")
                else:
                    print(f"  {item.get('provider_safety_dossier_id', '')} {item.get('safe_status', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier-latest":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import latest_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-latest skipped safely: no workspace found")
                return 1

            result = latest_provider_safety_dossier(ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-latest", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-latest", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            if result.get("found"):
                print("Latest provider safety dossier:")
                print(f"  ID: {result.get('artifact_id', '')}")
                print(f"  Hash: {result.get('artifact_hash', '')}")
                print(f"  Created: {result.get('created_at', '')}")
                print(f"  Provider: {result.get('provider_id', '')}")
                print(f"  Sandbox Only: {result.get('sandbox_only', False)}")
                print(f"  Chain Health: {result.get('chain_health', '')}")
                print(f"  Safety Verdict: {result.get('safety_verdict', '')}")
                print(f"  Export Available: {result.get('export_available', False)}")
                print(f"  Safe Status: {result.get('safe_status', '')}")
            else:
                print(f"No provider safety dossier found: {result.get('reason', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier-show":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import (
                find_provider_safety_dossier_by_id,
                load_provider_safety_dossier,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.dossier_id)
            artifact_path = find_provider_safety_dossier_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "dossier_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider safety dossier not found.")
                return 1
            data = load_provider_safety_dossier(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-show", "research command failed")
            return 1
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print(f"Provider safety dossier {safe_id}:")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Provider ID: {data.get('provider_id', '')}")
            print(f"  Safety Verdict: {data.get('safety_verdict', '')}")
            print(f"  Artifact: {data.get('artifact_path', '')}")
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier-validate":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import (
                find_provider_safety_dossier_by_id,
                validate_provider_safety_dossier_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.dossier_id)
            artifact_path = find_provider_safety_dossier_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "dossier_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Provider safety dossier not found.")
                return 1
            result = validate_provider_safety_dossier_artifact(artifact_path, ws, strict=args.strict)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-validate", "research command failed")
            return 1
        payload = {
            "ok": True,
            "valid": result.valid,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "checks": result.checks,
            "recommendation": result.recommendation,
            "warnings": result.warnings,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
            for check in result.checks:
                status_str = "PASS" if check["passed"] else "FAIL"
                print(f"  [{status_str}] {check['name']}: {check['message']}")
        if args.strict and not result.valid:
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier-replay":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import replay_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-replay skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.dossier_id)
            result = replay_provider_safety_dossier(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-replay", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-replay", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Replay: {'MATCH' if result.get('match') else 'MISMATCH'}")
            print(f"  Original hash: {result.get('original_hash', '')}")
            print(f"  Replayed hash: {result.get('replayed_hash', '')}")
        if args.strict and not result.get("match"):
            return 2
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier-summary":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import summarize_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = summarize_provider_safety_dossier(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-summary", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider safety dossier summary for run {safe_id}:")
            print(f"  Dossier ID: {result.get('provider_safety_dossier_id', 'None')}")
            print(f"  Verdict: {result.get('safety_verdict', '')}")
            print(f"  Chain Complete: {result.get('chain_complete', False)}")
            print(f"  Sandbox Only: {result.get('sandbox_only', False)}")
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier-doctor":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import doctor_provider_safety_dossier
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.run_id)
            result = doctor_provider_safety_dossier(ws, safe_id)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-doctor", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"Provider safety dossier doctor for run {safe_id}:")
            print(f"  Health: {result.get('dossier_health', '')}")
            if result.get("missing_prerequisites"):
                print(f"  Missing prerequisites: {', '.join(result['missing_prerequisites'])}")
            if result.get("blocking_reasons"):
                print(f"  Blocking reasons: {', '.join(result['blocking_reasons'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    if args.command == "research" and args.research_command == "provider-safety-dossier-export":
        try:
            import json
            from atlas_agent.research.provider_safety_dossier import export_provider_safety_dossier_markdown
            from atlas_agent.research.session import ResearchSessionError, _is_inside_workspace, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-export skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.dossier_id)
            output_path = Path(args.output).resolve()
            if not _is_inside_workspace(output_path, ws):
                if args.json:
                    print(json.dumps({"ok": False, "status": "export_path_outside_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research provider-safety-dossier-export refused: output path must be inside workspace")
                return 1

            result = export_provider_safety_dossier_markdown(ws, safe_id, output_path)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research provider-safety-dossier-export", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research provider-safety-dossier-export", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Provider safety dossier exported")
            print(f"  Dossier ID: {result.get('provider_safety_dossier_id', '')}")
            print(f"  Output: {result.get('output_path_relative', '')}")
            print(f"  Format: {result.get('format', '')}")
        return 0
    if args.command == "research" and args.research_command == "release-candidate-readiness":
        try:
            import json
            from atlas_agent.research.release_candidate_readiness import create_release_candidate_readiness
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-readiness skipped safely: no workspace found")
                return 1

            from atlas_agent import __version__
            result = create_release_candidate_readiness(ws, args.symbol, __version__)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-readiness", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-readiness", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Release candidate readiness report created")
            print(f"  ID: {result.get('release_candidate_readiness_report_id', '')}")
            print(f"  Symbol: {result.get('symbol', '')}")
            print(f"  Version: {result.get('version', '')}")
            print(f"  Readiness Status: {result.get('readiness_status', '')}")
            print(f"  Readiness Score: {result.get('readiness_score', 0)}")
            blockers = result.get("blockers", [])
            if blockers:
                print(f"  Blockers: {', '.join(blockers)}")
        return 0
    if args.command == "research" and args.research_command == "release-candidate-readiness-list":
        try:
            import json
            from atlas_agent.research.release_candidate_readiness import iter_release_candidate_readiness_artifacts
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-readiness-list skipped safely: no workspace found")
                return 1

            result = iter_release_candidate_readiness_artifacts(ws, symbol=args.symbol)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-readiness-list", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-readiness-list", "research command failed")
            return 1
        if args.json:
            print(json.dumps({"ok": True, "status": "research_release_candidate_readiness_list", "items": result}, indent=2, sort_keys=True))
        else:
            print(f"Release candidate readiness reports: {len(result)}")
            for item in result:
                print(f"  {item.get('release_candidate_readiness_report_id', '')} | {item.get('symbol', '')} | {item.get('readiness_status', '')} | {item.get('readiness_score', 0)}")
        return 0
    if args.command == "research" and args.research_command == "release-candidate-readiness-show":
        try:
            import json
            from atlas_agent.research.release_candidate_readiness import (
                find_release_candidate_readiness_by_id,
                load_release_candidate_readiness,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-readiness-show skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.report_id)
            artifact_path = find_release_candidate_readiness_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "report_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Release candidate readiness report not found.")
                return 1
            data = load_release_candidate_readiness(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-readiness-show", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-readiness-show", "research command failed")
            return 1
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            print("Release candidate readiness report")
            print(f"  ID: {data.get('release_candidate_readiness_report_id', '')}")
            print(f"  Symbol: {data.get('symbol', '')}")
            print(f"  Version: {data.get('version', '')}")
            print(f"  Status: {data.get('readiness_status', '')}")
            print(f"  Score: {data.get('readiness_score', 0)}")
            print(f"  Sandbox Only: {data.get('sandbox_only', True)}")
            print(f"  Paper First: {data.get('paper_first', True)}")
            print(f"  Offline Safe: {data.get('offline_safe', True)}")
        return 0
    if args.command == "research" and args.research_command == "release-candidate-readiness-validate":
        try:
            import json
            from atlas_agent.research.release_candidate_readiness import (
                find_release_candidate_readiness_by_id,
                validate_release_candidate_readiness_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-readiness-validate skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.report_id)
            artifact_path = find_release_candidate_readiness_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "report_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Release candidate readiness report not found.")
                return 1
            result = validate_release_candidate_readiness_artifact(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-readiness-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-readiness-validate", "research command failed")
            return 1
        output = {
            "ok": result.valid,
            "status": "research_release_candidate_readiness_validated" if result.valid else "research_release_candidate_readiness_validation_failed",
            "valid": result.valid,
            "structurally_valid": result.structurally_valid,
            "readiness_valid": result.readiness_valid,
            "readiness_status": result.readiness_status,
            "blockers": result.blockers,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "recommendation": result.recommendation,
            "warnings": result.warnings,
        }
        if args.json:
            print(json.dumps(output, indent=2, sort_keys=True))
        else:
            print(f"Release candidate readiness validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Passed: {result.passed_checks}")
            print(f"  Failed: {result.failed_checks}")
            print(f"  Recommendation: {result.recommendation}")
            if result.warnings:
                for w in result.warnings:
                    print(f"  Warning: {w}")
        if args.strict and not result.valid:
            return 1
        return 0
    if args.command == "research" and args.research_command == "release-candidate-readiness-summary":
        try:
            import json
            from atlas_agent.research.release_candidate_readiness import (
                find_release_candidate_readiness_by_id,
                summarize_release_candidate_readiness,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-readiness-summary skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.report_id)
            artifact_path = find_release_candidate_readiness_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "report_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Release candidate readiness report not found.")
                return 1
            result = summarize_release_candidate_readiness(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-readiness-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-readiness-summary", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Release candidate readiness summary")
            print(f"  ID: {result.get('release_candidate_readiness_report_id', '')}")
            print(f"  Status: {result.get('readiness_status', '')}")
            print(f"  Score: {result.get('readiness_score', 0)}")
            print(f"  Checks: {result.get('total_checks', 0)} total, {result.get('passed_checks', 0)} passed, {result.get('failed_checks', 0)} failed")
            blockers = result.get("blockers", [])
            if blockers:
                print(f"  Blockers: {', '.join(blockers)}")
        return 0
    if args.command == "research" and args.research_command == "release-candidate-readiness-doctor":
        try:
            import json
            from atlas_agent.research.release_candidate_readiness import (
                find_release_candidate_readiness_by_id,
                doctor_release_candidate_readiness,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-readiness-doctor skipped safely: no workspace found")
                return 1

            safe_id = validate_run_id(args.report_id)
            artifact_path = find_release_candidate_readiness_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "report_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Release candidate readiness report not found.")
                return 1
            result = doctor_release_candidate_readiness(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-readiness-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-readiness-doctor", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Release candidate readiness doctor")
            print(f"  Valid: {result.get('valid', False)}")
            print(f"  Structurally Valid: {result.get('structurally_valid', False)}")
            print(f"  Readiness Valid: {result.get('readiness_valid', False)}")
            print(f"  Readiness Status: {result.get('readiness_status', '')}")
            print(f"  Passed: {result.get('passed_checks', 0)}")
            print(f"  Failed: {result.get('failed_checks', 0)}")
            print(f"  Recommendation: {result.get('recommendation', '')}")
            if result.get("mismatched_fields"):
                print(f"  Mismatched Fields: {', '.join(result['mismatched_fields'])}")
            if result.get("blockers"):
                print(f"  Blockers: {', '.join(result['blockers'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    if args.command == "research" and args.research_command == "release-candidate-cutover-dry-run":
        try:
            import json
            from atlas_agent.research.release_candidate_cutover import create_release_candidate_cutover_dry_run
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-cutover-dry-run skipped safely: no workspace found")
                return 1

            result = create_release_candidate_cutover_dry_run(ws, args.target_version)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-cutover-dry-run", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-cutover-dry-run", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Release candidate cutover dry run")
            print(f"  Status: {result.get('cutover_status', '')}")
            print(f"  Target: {result.get('target_version', '')}")
            print(f"  Score: {result.get('cutover_score', 0)}")
            if result.get("blockers"):
                print(f"  Blockers: {', '.join(result['blockers'])}")
            print("  Dry run only: no tag, push, or publish executed.")
        return 0 if result.get("ok") else 1
    if args.command == "research" and args.research_command == "release-candidate-cutover-dry-run-list":
        try:
            import json
            from atlas_agent.research.release_candidate_cutover import iter_release_candidate_cutover_artifacts
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-cutover-dry-run-list skipped safely: no workspace found")
                return 1
            result = iter_release_candidate_cutover_artifacts(ws)
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-cutover-dry-run-list", "research command failed")
            return 1
        if args.json:
            print(json.dumps({"ok": True, "status": "research_release_candidate_cutover_dry_run_list", "items": result}, indent=2, sort_keys=True))
        else:
            print(f"Release candidate cutover dry runs: {len(result)}")
            for item in result:
                print(f"  {item.get('release_candidate_cutover_dry_run_id', '')} | {item.get('target_version', '')} | {item.get('cutover_status', '')} | {item.get('cutover_score', 0)}")
        return 0
    if args.command == "research" and args.research_command == "release-candidate-cutover-dry-run-validate":
        try:
            import json
            from atlas_agent.research.release_candidate_cutover import (
                find_release_candidate_cutover_by_id,
                validate_release_candidate_cutover_artifact,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-cutover-dry-run-validate skipped safely: no workspace found")
                return 1
            safe_id = validate_run_id(args.report_id)
            artifact_path = find_release_candidate_cutover_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "report_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Release candidate cutover dry-run report not found.")
                return 1
            result = validate_release_candidate_cutover_artifact(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-cutover-dry-run-validate", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-cutover-dry-run-validate", "research command failed")
            return 1
        output = {
            "ok": result.valid,
            "status": "research_release_candidate_cutover_dry_run_validated" if result.valid else "research_release_candidate_cutover_dry_run_validation_failed",
            "valid": result.valid,
            "structurally_valid": result.structurally_valid,
            "cutover_valid": result.cutover_valid,
            "cutover_status": result.cutover_status,
            "blockers": result.blockers,
            "passed_checks": result.passed_checks,
            "failed_checks": result.failed_checks,
            "recommendation": result.recommendation,
            "warnings": result.warnings,
            "mismatched_fields": result.mismatched_fields,
        }
        if args.json:
            print(json.dumps(output, indent=2, sort_keys=True))
        else:
            print(f"Release candidate cutover dry-run validation: {'PASS' if result.valid else 'FAIL'}")
            print(f"  Status: {result.cutover_status}")
            if result.blockers:
                print(f"  Blockers: {', '.join(result.blockers)}")
        if args.strict and not result.valid:
            return 1
        return 0
    if args.command == "research" and args.research_command == "release-candidate-cutover-dry-run-summary":
        try:
            import json
            from atlas_agent.research.release_candidate_cutover import (
                find_release_candidate_cutover_by_id,
                summarize_release_candidate_cutover,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-cutover-dry-run-summary skipped safely: no workspace found")
                return 1
            safe_id = validate_run_id(args.report_id)
            artifact_path = find_release_candidate_cutover_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "report_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Release candidate cutover dry-run report not found.")
                return 1
            result = summarize_release_candidate_cutover(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-cutover-dry-run-summary", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-cutover-dry-run-summary", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Release candidate cutover dry-run summary")
            print(f"  Status: {result.get('cutover_status', '')}")
            print(f"  Target: {result.get('target_version', '')}")
            print(f"  Score: {result.get('cutover_score', 0)}")
            if result.get("blockers"):
                print(f"  Blockers: {', '.join(result['blockers'])}")
        return 0
    if args.command == "research" and args.research_command == "release-candidate-cutover-dry-run-doctor":
        try:
            import json
            from atlas_agent.research.release_candidate_cutover import (
                doctor_release_candidate_cutover,
                find_release_candidate_cutover_by_id,
            )
            from atlas_agent.research.session import ResearchSessionError, validate_run_id
            from atlas_agent.workspace import resolve_workspace_path

            ws = resolve_workspace_path()
            if ws is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                else:
                    print("research release-candidate-cutover-dry-run-doctor skipped safely: no workspace found")
                return 1
            safe_id = validate_run_id(args.report_id)
            artifact_path = find_release_candidate_cutover_by_id(ws, safe_id)
            if artifact_path is None:
                if args.json:
                    print(json.dumps({"ok": False, "status": "report_not_found"}, indent=2, sort_keys=True))
                else:
                    print("Release candidate cutover dry-run report not found.")
                return 1
            result = doctor_release_candidate_cutover(artifact_path, ws)
        except ResearchSessionError as exc:
            status, message = safe_research_session_error(exc)
            if args.json:
                _research_error_json(status, message)
            else:
                _research_error_text("research release-candidate-cutover-dry-run-doctor", message.lower().rstrip("."))
            return 1
        except Exception:
            if args.json:
                _research_error_json("research_error", "Research command failed.")
            else:
                _research_error_text("research release-candidate-cutover-dry-run-doctor", "research command failed")
            return 1
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Release candidate cutover dry-run doctor")
            print(f"  Valid: {result.get('valid', False)}")
            print(f"  Status: {result.get('cutover_status', '')}")
            if result.get("blockers"):
                print(f"  Blockers: {', '.join(result['blockers'])}")
            if result.get("warnings"):
                for w in result["warnings"]:
                    print(f"  Warning: {w}")
        return 0
    if args.command == "notify" and args.notify_command == "clickup":
        if not args.file.exists():
            print(f"notification skipped safely: file not found: {args.file}")
            return 0
        try:
            ClickUpNotifier().send(args.file.read_text(encoding="utf-8")[:2000])
        except NotificationConfigurationError as exc:
            print(f"notification skipped safely: {exc}")
            return 0
        print("ClickUp notification sent")
        return 0

    if args.command == "notifications":
        from atlas_agent.notifications import (
            NotificationConfig,
            NotificationPayload,
            NotificationSeverity,
            NotificationTransport,
            send_notification,
            save_result,
        )

        transport_str = getattr(args, "transport", "dry_run")
        severity_str = getattr(args, "severity", "info")
        message = getattr(args, "message", "")
        title = getattr(args, "title", "")
        source = getattr(args, "source", "cli")
        dry_run = getattr(args, "dry_run", True)

        # Always default to dry_run unless explicitly slack and not --dry-run
        effective_transport = transport_str
        if dry_run and transport_str == "slack":
            effective_transport = "dry_run"

        config = NotificationConfig(
            enabled=True,
            transport=effective_transport,  # type: ignore[arg-type]
        )

        payload = NotificationPayload(
            severity=NotificationSeverity(severity_str),
            title=title,
            message=message,
            source=source,
            source_command=f"notifications {getattr(args, 'notifications_command', '')}",
            mode=config.trading_mode if hasattr(config, "trading_mode") else "unknown",
        )

        result = send_notification(payload, config)
        save_result(result, Path.cwd())

        print(f"Notification result: {result.status}")
        print(f"  Transport: {result.transport.value}")
        print(f"  Message: {result.message}")
        if result.redacted_preview:
            print(f"  Preview:\n{result.redacted_preview}")
        if result.error_code:
            print(f"  Error: {result.error_code} — {result.error_detail}")
        return 0 if result.status in ("delivered", "dry_run", "disabled") else 1

    if args.command == "git-sync":
        sync = GitSync.from_env()
        try:
            if args.git_command == "commit":
                print(sync.commit(args.message))
                return 0
            if args.git_command == "push":
                print(sync.push())
                return 0
        except GitSyncError as exc:
            print(f"git sync refused: {exc}")
            return 2
    if args.command == "schedule" and args.schedule_command == "github-actions":
        try:
            path = write_github_actions_workflow(template=args.template)
        except ValueError as exc:
            print(f"schedule refused: {exc}")
            return 2
        print(f"GitHub Actions workflow generated: {path}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
