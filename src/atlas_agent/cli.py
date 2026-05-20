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
from atlas_agent.backtest import BacktestConfig, BacktestEngine
from atlas_agent.brokers.alpaca import AlpacaBroker
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.brokers.binance import BinanceBroker
from atlas_agent.brokers.ccxt_adapter import CCXTBroker
from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.cli_commands import build_core_command_registry
from atlas_agent.cli_context import CLIContext
from atlas_agent.config import AtlasConfig
from atlas_agent.config.errors import AtlasConfigError
from atlas_agent.execution.approval import ApprovalManager
from atlas_agent.execution.audit import AuditLogger
from atlas_agent.execution.order import Order, OrderResult
from atlas_agent.execution.order_router import OrderRouter
from atlas_agent.events import (
    EventLogger,
    diagnose_events,
    generate_run_id,
    latest_event_file,
    read_event_file,
)
from atlas_agent.market_data.csv_provider import CSVMarketDataProvider
from atlas_agent.market_data.sample_data import ensure_sample_data
from atlas_agent.portfolio.journal import TradeJournal
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.reports.daily import generate_daily_report
from atlas_agent.research import (
    get_research_provider,
    ResearchConfigurationError,
)
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
from atlas_agent.demo import seed_demo_workspace
from atlas_agent.safety import (
    KillSwitchController,
    deadman_heartbeat_path,
    write_deadman_heartbeat,
)
from atlas_agent.safety.totp import verify_totp
from atlas_agent.strategies.moving_average import MovingAverageStrategy
from atlas_agent.update import AUTO_CHECK_VALUES, SafeUpdateManager
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


SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(?P<name>[A-Z0-9_.-]*(?:API[_-]?KEY|API[_-]?SECRET|SECRET[_-]?KEY|TOKEN|PASSWORD)[A-Z0-9_.-]*)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<quote>[\"']?)"
    r"(?P<value>[^\s,;`\"']+)"
    r"(?P=quote)",
    re.IGNORECASE,
)
BEARER_TOKEN_RE = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


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
    run_parser.add_argument("--interval", type=int, default=60)
    run_parser.add_argument("--max-cycles", type=int, default=None)

    update = subparsers.add_parser("update")
    update_sub = update.add_subparsers(dest="update_command")
    update_sub.add_parser("check")
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

    brokers = subparsers.add_parser("broker")
    brokers_sub = brokers.add_subparsers(dest="brokers_command")
    brokers_sub.add_parser("list")
    brokers_sync = brokers_sub.add_parser("sync")
    brokers_sync.add_argument("--mode", choices=("paper", "live"), default="paper")
    brokers_sync.add_argument("--json", action="store_true")
    brokers_opt_in = brokers_sub.add_parser("opt-in")
    brokers_opt_in.add_argument("--yes", action="store_true", help=argparse.SUPPRESS)
    brokers_opt_out = brokers_sub.add_parser("opt-out")

    backtest = subparsers.add_parser("backtest")
    backtest_sub = backtest.add_subparsers(dest="backtest_command")
    backtest_run = backtest_sub.add_parser("run")
    backtest_run.add_argument("--strategy", default="buy_and_hold")
    backtest_run.add_argument("--symbol", required=True)
    backtest_run.add_argument("--data", required=True)
    backtest_run.add_argument("--initial-equity", type=float, default=10000.0)
    backtest_run.add_argument("--slippage-bps", type=float, default=0.0)
    backtest_run.add_argument("--commission-bps", type=float, default=0.0)
    backtest_run.add_argument("--json", action="store_true")

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

    research_provider_plan = research_sub.add_parser(
        "provider-plan",
        help="Create a provider call plan artifact from a sandbox request. Local-only.",
        description="Create a provider call plan artifact from an existing sandbox request. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_plan.add_argument("sandbox_request_id", help="Source sandbox request ID.")
    research_provider_plan.add_argument("--provider", required=True, help="Provider ID.")
    research_provider_plan.add_argument("--model", required=True, help="Model ID.")
    research_provider_plan.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_plan_list = research_sub.add_parser(
        "provider-plan-list",
        help="List provider call plan artifacts. Read-only. Does not call providers or network.",
        description="List local provider call plan artifacts. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_plan_list.add_argument("--symbol", help="Filter by symbol.")
    research_provider_plan_list.add_argument("--limit", type=int, default=20, help="Maximum items to show. Default: 20, max: 100.")
    research_provider_plan_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_plan_show = research_sub.add_parser(
        "provider-plan-show",
        help="Show a provider call plan artifact. Read-only. Does not call providers or network.",
        description="Show one local provider call plan artifact by ID. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_plan_show.add_argument("provider_call_plan_id", help="Provider call plan ID.")
    research_provider_plan_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_plan_validate = research_sub.add_parser(
        "provider-plan-validate",
        help="Validate a provider call plan artifact against the local contract. Read-only.",
        description="Validate a provider call plan artifact against the local contract. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_plan_validate.add_argument("provider_call_plan_id", help="Provider call plan ID.")
    research_provider_plan_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_plan_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_provider_plan_replay = research_sub.add_parser(
        "provider-plan-replay",
        help="Replay a provider call plan from its source sandbox request and compare hashes. Read-only by default.",
        description="Rebuild the provider call plan from its source sandbox request and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_plan_replay.add_argument("provider_call_plan_id", help="Provider call plan ID.")
    research_provider_plan_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_plan_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")

    research_provider_execution_dry_run = research_sub.add_parser(
        "provider-execution-dry-run",
        help="Create a provider execution dry-run artifact from a provider call plan. Local-only.",
        description="Create a provider execution dry-run artifact from an existing provider call plan. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_dry_run.add_argument("provider_call_plan_id", help="Source provider call plan ID.")
    research_provider_execution_dry_run.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_list = research_sub.add_parser(
        "provider-execution-list",
        help="List provider execution dry-run artifacts. Read-only. Does not call providers or network.",
        description="List local provider execution dry-run artifacts. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_list.add_argument("--symbol", help="Filter by symbol.")
    research_provider_execution_list.add_argument("--limit", type=int, default=20, help="Maximum items to show. Default: 20, max: 100.")
    research_provider_execution_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_show = research_sub.add_parser(
        "provider-execution-show",
        help="Show a provider execution dry-run artifact. Read-only. Does not call providers or network.",
        description="Show one local provider execution dry-run artifact by ID. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_show.add_argument("provider_execution_dry_run_id", help="Provider execution dry-run ID.")
    research_provider_execution_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_validate = research_sub.add_parser(
        "provider-execution-validate",
        help="Validate a provider execution dry-run artifact against the local contract. Read-only.",
        description="Validate a provider execution dry-run artifact against the local contract. Read-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_validate.add_argument("provider_execution_dry_run_id", help="Provider execution dry-run ID.")
    research_provider_execution_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_provider_execution_replay = research_sub.add_parser(
        "provider-execution-replay",
        help="Replay a provider execution dry-run from its source call plan and compare hashes. Read-only by default.",
        description="Rebuild the provider execution dry-run from its source provider call plan and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_replay.add_argument("provider_execution_dry_run_id", help="Provider execution dry-run ID.")
    research_provider_execution_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")

    research_provider_execution_state = research_sub.add_parser(
        "provider-execution-state",
        help="Create a provider execution state transition artifact. Local-only. No provider calls.",
        description="Create a local provider execution opt-in state transition artifact from a dry-run. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_state.add_argument("provider_execution_dry_run_id", help="Source provider execution dry-run ID.")
    research_provider_execution_state.add_argument("--to", dest="requested_state", required=True, help="Requested state. Must be one of: disabled, dry_run_only, manual_unlock_required, provider_call_allowed_but_not_implemented.")
    research_provider_execution_state.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_state_list = research_sub.add_parser(
        "provider-execution-state-list",
        help="List provider execution state artifacts. Read-only.",
        description="List local provider execution state artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_state_list.add_argument("--symbol", help="Filter by symbol.")
    research_provider_execution_state_list.add_argument("--limit", type=int, default=20, help="Max items to return. Default 20, max 100.")
    research_provider_execution_state_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_state_show = research_sub.add_parser(
        "provider-execution-state-show",
        help="Show one provider execution state artifact. Read-only.",
        description="Show a single provider execution state artifact with validation. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_state_show.add_argument("provider_execution_state_id", help="Provider execution state ID.")
    research_provider_execution_state_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_state_validate = research_sub.add_parser(
        "provider-execution-state-validate",
        help="Validate a provider execution state artifact. Read-only.",
        description="Validate a provider execution state artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_state_validate.add_argument("provider_execution_state_id", help="Provider execution state ID.")
    research_provider_execution_state_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_state_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_provider_execution_state_replay = research_sub.add_parser(
        "provider-execution-state-replay",
        help="Replay a provider execution state from its source dry-run and compare hashes. Read-only by default.",
        description="Rebuild the provider execution state from its source dry-run and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_state_replay.add_argument("provider_execution_state_id", help="Provider execution state ID.")
    research_provider_execution_state_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_state_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")

    research_provider_execution_audit = research_sub.add_parser(
        "provider-execution-audit",
        help="Create a provider execution audit packet from a state artifact. Local-only. No provider calls.",
        description="Create a local provider execution audit packet artifact from a provider execution state. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_audit.add_argument("provider_execution_state_id", help="Source provider execution state ID.")
    research_provider_execution_audit.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_audit_list = research_sub.add_parser(
        "provider-execution-audit-list",
        help="List provider execution audit packet artifacts. Read-only.",
        description="List local provider execution audit packet artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_audit_list.add_argument("--symbol", help="Filter by symbol.")
    research_provider_execution_audit_list.add_argument("--limit", type=int, default=20, help="Max items to return. Default 20, max 100.")
    research_provider_execution_audit_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_audit_show = research_sub.add_parser(
        "provider-execution-audit-show",
        help="Show one provider execution audit packet artifact. Read-only.",
        description="Show a single provider execution audit packet artifact with validation. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_audit_show.add_argument("provider_execution_audit_packet_id", help="Provider execution audit packet ID.")
    research_provider_execution_audit_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_audit_validate = research_sub.add_parser(
        "provider-execution-audit-validate",
        help="Validate a provider execution audit packet artifact. Read-only.",
        description="Validate a provider execution audit packet artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_audit_validate.add_argument("provider_execution_audit_packet_id", help="Provider execution audit packet ID.")
    research_provider_execution_audit_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_audit_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_provider_execution_audit_replay = research_sub.add_parser(
        "provider-execution-audit-replay",
        help="Replay a provider execution audit packet from its source state and compare hashes. Read-only by default.",
        description="Rebuild the provider execution audit packet from its source state and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_audit_replay.add_argument("provider_execution_audit_packet_id", help="Provider execution audit packet ID.")
    research_provider_execution_audit_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_audit_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")

    research_provider_execution_readiness = research_sub.add_parser(
        "provider-execution-readiness",
        help="Create a provider execution readiness report from an audit packet. Local-only. No provider calls.",
        description="Create a local provider execution readiness report artifact from a provider execution audit packet. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_readiness.add_argument("provider_execution_audit_packet_id", help="Source provider execution audit packet ID.")
    research_provider_execution_readiness.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_readiness_list = research_sub.add_parser(
        "provider-execution-readiness-list",
        help="List provider execution readiness report artifacts. Read-only.",
        description="List local provider execution readiness report artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_readiness_list.add_argument("--symbol", help="Filter by symbol.")
    research_provider_execution_readiness_list.add_argument("--limit", type=int, default=20, help="Max items to return. Default 20, max 100.")
    research_provider_execution_readiness_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_readiness_show = research_sub.add_parser(
        "provider-execution-readiness-show",
        help="Show one provider execution readiness report artifact. Read-only.",
        description="Show a single provider execution readiness report artifact with validation. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_readiness_show.add_argument("provider_execution_readiness_report_id", help="Provider execution readiness report ID.")
    research_provider_execution_readiness_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_execution_readiness_validate = research_sub.add_parser(
        "provider-execution-readiness-validate",
        help="Validate a provider execution readiness report artifact. Read-only.",
        description="Validate a provider execution readiness report artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_readiness_validate.add_argument("provider_execution_readiness_report_id", help="Provider execution readiness report ID.")
    research_provider_execution_readiness_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_readiness_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_provider_execution_readiness_replay = research_sub.add_parser(
        "provider-execution-readiness-replay",
        help="Replay a provider execution readiness report from its source audit packet and compare hashes. Read-only by default.",
        description="Rebuild the provider execution readiness report from its source audit packet and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_execution_readiness_replay.add_argument("provider_execution_readiness_report_id", help="Provider execution readiness report ID.")
    research_provider_execution_readiness_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_execution_readiness_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")

    research_provider_execution_chain_doctor = research_sub.add_parser(
        "provider-execution-chain-doctor",
        help="Diagnose the full provider-preflight chain for a run. Read-only.",
        description="Read-only diagnostic command for the full provider-preflight chain under one research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_execution_chain_doctor.add_argument("run_id", help="Research run ID.")
    research_provider_execution_chain_doctor.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_preflight_freeze = research_sub.add_parser(
        "provider-preflight-freeze",
        help="Create a provider preflight freeze audit artifact from a readiness report. Local-only.",
        description="Create a local provider preflight freeze audit artifact from a provider execution readiness report. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_preflight_freeze.add_argument("provider_execution_readiness_report_id", help="Source provider execution readiness report ID.")
    research_provider_preflight_freeze.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_preflight_freeze_list = research_sub.add_parser(
        "provider-preflight-freeze-list",
        help="List provider preflight freeze audit artifacts. Read-only.",
        description="List local provider preflight freeze audit artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_preflight_freeze_list.add_argument("--symbol", help="Filter by symbol.")
    research_provider_preflight_freeze_list.add_argument("--limit", type=int, default=20, help="Max items to return. Default 20, max 100.")
    research_provider_preflight_freeze_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_preflight_freeze_show = research_sub.add_parser(
        "provider-preflight-freeze-show",
        help="Show one provider preflight freeze audit artifact. Read-only.",
        description="Show a single provider preflight freeze audit artifact with validation. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_preflight_freeze_show.add_argument("provider_preflight_freeze_id", help="Provider preflight freeze ID.")
    research_provider_preflight_freeze_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_preflight_freeze_validate = research_sub.add_parser(
        "provider-preflight-freeze-validate",
        help="Validate a provider preflight freeze audit artifact. Read-only.",
        description="Validate a provider preflight freeze audit artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_preflight_freeze_validate.add_argument("provider_preflight_freeze_id", help="Provider preflight freeze ID.")
    research_provider_preflight_freeze_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_preflight_freeze_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_provider_preflight_freeze_replay = research_sub.add_parser(
        "provider-preflight-freeze-replay",
        help="Replay a provider preflight freeze audit artifact from its source readiness report and compare hashes. Read-only by default.",
        description="Rebuild the provider preflight freeze audit artifact from its source readiness report and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_preflight_freeze_replay.add_argument("provider_preflight_freeze_id", help="Provider preflight freeze ID.")
    research_provider_preflight_freeze_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_preflight_freeze_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")

    research_provider_preflight_freeze_summary = research_sub.add_parser(
        "provider-preflight-freeze-summary",
        help="Summarize the provider preflight freeze state for a research run. Read-only.",
        description="Read-only summary of the provider preflight freeze state for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_preflight_freeze_summary.add_argument("run_id", help="Research run ID.")
    research_provider_preflight_freeze_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_opt_in_policy = research_sub.add_parser(
        "provider-opt-in-policy",
        help="Create a provider opt-in policy artifact from a preflight freeze. Local-only.",
        description="Create a local provider opt-in policy artifact from a provider preflight freeze. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_opt_in_policy.add_argument("provider_preflight_freeze_id", help="Source provider preflight freeze ID.")
    research_provider_opt_in_policy.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_opt_in_policy_list = research_sub.add_parser(
        "provider-opt-in-policy-list",
        help="List provider opt-in policy artifacts. Read-only.",
        description="List local provider opt-in policy artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_opt_in_policy_list.add_argument("--symbol", help="Filter by symbol.")
    research_provider_opt_in_policy_list.add_argument("--limit", type=int, default=20, help="Max items to return. Default 20, max 100.")
    research_provider_opt_in_policy_list.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_opt_in_policy_show = research_sub.add_parser(
        "provider-opt-in-policy-show",
        help="Show one provider opt-in policy artifact. Read-only.",
        description="Show a single provider opt-in policy artifact with validation. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_opt_in_policy_show.add_argument("provider_opt_in_policy_id", help="Provider opt-in policy ID.")
    research_provider_opt_in_policy_show.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

    research_provider_opt_in_policy_validate = research_sub.add_parser(
        "provider-opt-in-policy-validate",
        help="Validate a provider opt-in policy artifact. Read-only.",
        description="Validate a provider opt-in policy artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
    )
    research_provider_opt_in_policy_validate.add_argument("provider_opt_in_policy_id", help="Provider opt-in policy ID.")
    research_provider_opt_in_policy_validate.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_opt_in_policy_validate.add_argument("--strict", action="store_true", help="Exit non-zero if validation fails.")

    research_provider_opt_in_policy_replay = research_sub.add_parser(
        "provider-opt-in-policy-replay",
        help="Replay a provider opt-in policy artifact from its source freeze and compare hashes. Read-only by default.",
        description="Rebuild the provider opt-in policy artifact from its source preflight freeze and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
    )
    research_provider_opt_in_policy_replay.add_argument("provider_opt_in_policy_id", help="Provider opt-in policy ID.")
    research_provider_opt_in_policy_replay.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    research_provider_opt_in_policy_replay.add_argument("--strict", action="store_true", help="Exit non-zero if replay does not match.")

    research_provider_opt_in_policy_summary = research_sub.add_parser(
        "provider-opt-in-policy-summary",
        help="Summarize the provider opt-in policy state for a research run. Read-only.",
        description="Read-only summary of the provider opt-in policy state for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
    )
    research_provider_opt_in_policy_summary.add_argument("run_id", help="Research run ID.")
    research_provider_opt_in_policy_summary.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")

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
    dashboard.add_argument("--open", action="store_true", help="Open dashboard in browser")

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


def _redact_sensitive_text(text: str) -> str:
    redacted = SECRET_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group('name')}{match.group('sep')}"
            f"{match.group('quote')}[REDACTED]{match.group('quote')}"
        ),
        text,
    )
    return BEARER_TOKEN_RE.sub(r"\1[REDACTED]", redacted)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _kill_switch_controller(config: AtlasConfig) -> KillSwitchController:
    audit_logger = AuditLogger(config.audit_dir)

    def _audit_hook(event_type: str, actor: str, payload: dict[str, Any]) -> None:
        record = dict(payload)
        record["actor"] = actor
        audit_logger.write(event_type, record)

    return KillSwitchController(
        state_path=config.memory_dir / "kill_switch_state.json",
        enabled_flag_path=config.memory_dir / "kill_switch.enabled",
        audit_hook=_audit_hook,
    )


def _effective_config_with_runtime_kill_switch(config: AtlasConfig) -> AtlasConfig:
    enabled = config.kill_switch_enabled or _kill_switch_controller(config).is_enabled()
    if enabled == config.kill_switch_enabled:
        return config
    # Map back to nested structure for model_copy if needed, 
    # but since we added legacy fields to AtlasConfig, we can just update it.
    return config.model_copy(update={"safety": config.safety.model_copy(update={"kill_switch_enabled": enabled})})


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


def _handle_deploy(kind: str) -> int:
    from atlas_agent.deploy import ensure_deploy_files

    files = ensure_deploy_files(kind)
    for generated in files:
        action = "created" if generated.created else "existing"
        print(f"{action}: {_display_path(generated.path)}")
    return 0


def _emit_json_success(command: str, data: dict[str, Any]) -> int:
    emit_json(success_envelope(command, data))
    return 0


def _emit_json_error(
    command: str,
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> int:
    emit_json(error_envelope(command, code=code, message=message, details=details))
    return 2


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


def _events_to_payload(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(events),
        "events": events,
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
    if args.command in {"init", "workspace", "models", "validate", "deploy", "configure", "setup", "discipline"}:
        return False
    if args.command == "providers" and args.providers_command == "list":
        return False
    if args.command == "broker" and args.brokers_command == "list":
        return False
    if args.command == "telegram" and args.telegram_command == "test":
        return False
    return True


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


def _workspace_doctor_payload(resolution: WorkspaceResolution) -> dict[str, Any]:
    default_workspace = get_default_workspace()
    payload: dict[str, Any] = {
        "ok": False,
        "current_directory": str(Path.cwd()),
        "resolved_workspace": str(resolution.path) if resolution.path else None,
        "resolution_source": resolution.source,
        "default_workspace": str(default_workspace) if default_workspace else None,
        "environment_workspace": os.getenv("ATLAS_WORKSPACE"),
        "warning": resolution.warning,
        "missing_paths": [],
        "guidance": [],
    }
    if resolution.path is None:
        payload["guidance"] = [
            "Create a workspace: atlas init my-trader --template routine-trader --set-default",
            "or set one: atlas workspace set <path>",
        ]
        return payload

    expected = (
        "memory",
        "routines",
        "skills",
        "reports",
        "pending_orders",
        "audit",
        "events",
        "configs",
    )
    missing = [
        name for name in expected if not (resolution.path / name).exists()
    ]
    payload["missing_paths"] = missing
    payload["ok"] = not missing
    return payload


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        raise

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
                    return _emit_json_error(
                        "atlas config check",
                        code="config_load_failed",
                        message="Configuration check failed.",
                    )
                return _emit_config_error(None)
            except Exception:
                if getattr(args, "json", False):
                    return _emit_json_error(
                        "atlas config check",
                        code="config_check_failed",
                        message="Configuration check failed.",
                    )
                print("Configuration check failed.", file=sys.stderr)
                return 1
            if getattr(args, "json", False):
                return _emit_json_success("atlas config check", payload)
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

    if args.command == "workspace":
        resolution = resolve_workspace(getattr(args, "workspace", None))
        if args.workspace_command == "show":
            default_ws = get_default_workspace()
            resolved = resolution.path
            print(f"Current directory: {Path.cwd()}")
            print(f"Resolved workspace: {resolved or 'not resolved'}")
            print(f"Resolution source: {resolution.source or 'none'}")
            print(f"Default workspace: {default_ws or 'not set'}")
            if resolution.warning:
                print(f"Warning: {resolution.warning}")
            return 0
        if args.workspace_command == "set":
            path = Path(args.path).resolve()
            if not is_workspace(path):
                print(f"Error: {path} does not look like a valid Atlas workspace.")
                return 2
            set_default_workspace(path)
            print(f"Default workspace set to: {path}")
            return 0
        if args.workspace_command == "clear":
            clear_default_workspace()
            print("Default workspace cleared.")
            return 0
        if args.workspace_command == "doctor":
            payload = _workspace_doctor_payload(resolution)
            if getattr(args, "json", False):
                return _emit_json_success("atlas workspace doctor", payload)
            print("Workspace Doctor")
            print(f"Current directory: {payload['current_directory']}")
            print(f"Resolved workspace: {payload['resolved_workspace'] or 'not resolved'}")
            print(f"Resolution source: {payload['resolution_source'] or 'none'}")
            print(f"Default workspace: {payload['default_workspace'] or 'not set'}")
            if payload["warning"]:
                print(f"Warning: {payload['warning']}")
            if payload["resolved_workspace"] and not payload["missing_paths"]:
                print("Workspace structure looks valid.")
                return 0
            if payload["missing_paths"]:
                print("Missing paths:")
                for missing in payload["missing_paths"]:
                    print(f"- {missing}")
            for guidance in payload["guidance"]:
                print(guidance)
            return 2
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

    # Configless local research commands: resolve workspace only, never load secrets
    _CONFIGLESS_RESEARCH_COMMANDS = {
        "run",
        "list",
        "show",
        "plan",
        "verify",
        "evaluate",
        "summary",
        "check-artifacts",
        "timeline",
        "providers",
        "prompt",
        "simulate-provider",
        "review-response",
        "dossier",
        "sandbox",
        "sandbox-list",
        "sandbox-show",
        "sandbox-validate",
        "sandbox-replay",
        "import-provider-response",
        "provider-targets",
        "provider-plan",
        "provider-plan-list",
        "provider-plan-show",
        "provider-plan-validate",
        "provider-plan-replay",
        "provider-execution-dry-run",
        "provider-execution-list",
        "provider-execution-show",
        "provider-execution-validate",
        "provider-execution-replay",
        "provider-execution-state",
        "provider-execution-state-list",
        "provider-execution-state-show",
        "provider-execution-state-validate",
        "provider-execution-state-replay",
        "provider-execution-audit",
        "provider-execution-audit-list",
        "provider-execution-audit-show",
        "provider-execution-audit-validate",
        "provider-execution-audit-replay",
        "provider-execution-readiness",
        "provider-execution-readiness-list",
        "provider-execution-readiness-show",
        "provider-execution-readiness-validate",
        "provider-execution-readiness-replay",
        "provider-execution-chain-doctor",
        "provider-preflight-freeze",
        "provider-preflight-freeze-list",
        "provider-preflight-freeze-show",
        "provider-preflight-freeze-validate",
        "provider-preflight-freeze-replay",
        "provider-preflight-freeze-summary",
        "provider-opt-in-policy",
        "provider-opt-in-policy-list",
        "provider-opt-in-policy-show",
        "provider-opt-in-policy-validate",
        "provider-opt-in-policy-replay",
        "provider-opt-in-policy-summary",
    }
    if args.command == "research" and getattr(args, "research_command", None) in _CONFIGLESS_RESEARCH_COMMANDS:
        resolution = resolve_workspace(getattr(args, "workspace", None))
        if resolution.path is not None:
            os.chdir(resolution.path)
        if resolution.path is None:
            if getattr(args, "json", False):
                return _emit_json_error(
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
                return _emit_json_error(
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
            if args.command == "validate" and getattr(args, "json", False):
                return _emit_json_error(
                    "atlas validate",
                    code="config_load_failed",
                    message=load_error,
                )
            print(load_error, file=sys.stderr)
            return 1
        if config is None:
            if args.command == "validate" and getattr(args, "json", False):
                return _emit_json_error(
                    "atlas validate",
                    code="config_load_failed",
                    message="Configuration error: unable to load AtlasConfig.",
                )
            print("Configuration error: unable to load AtlasConfig.", file=sys.stderr)
            return 1

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

    if args.command == "update":
        manager = SafeUpdateManager(
            config=config,
            workspace_root=Path.cwd(),
            repo_root=Path.cwd(),
        )
        if args.update_command == "check":
            report = manager.check()
            print("Atlas Update Check")
            print(f"Current version: {report.current_version}")
            print(f"Latest version: {report.latest_version or 'n/a'}")
            print(f"Source: {report.source or 'n/a'}")
            print(f"Update available: {'yes' if report.update_available else 'no'}")
            print(f"Checked at: {report.checked_at}")
            if report.notes:
                print(f"Notes: {report.notes}")
            for warning in report.warnings:
                print(f"Warning: {warning}")
            return 0
        if args.update_command == "status":
            report = manager.status()
            print("Atlas Update Status")
            print(f"Current version: {report.current_version}")
            print(f"Last checked at: {report.last_checked_at or 'n/a'}")
            print(f"Latest version: {report.latest_version or 'n/a'}")
            print(f"Latest source: {report.latest_source or 'n/a'}")
            print(f"Auto-apply enabled: {'yes' if report.auto_apply_enabled else 'no'}")
            print(f"Auto-check schedule: {report.auto_check_schedule}")
            print(f"Safe to apply now: {'yes' if report.safe_to_apply else 'no'}")
            if report.blockers:
                print("Blockers:")
                for blocker in report.blockers:
                    print(f"- {blocker}")
            if report.warnings:
                print("Warnings:")
                for warning in report.warnings:
                    print(f"- {warning}")
            return 0
        if args.update_command == "apply":
            if args.force:
                print("WARNING: --force bypasses safety blockers. Use only with full human review.")
            report = manager.apply(force=args.force, auto=False)
            print(report.message)
            if report.blockers:
                print("Blockers:")
                for blocker in report.blockers:
                    print(f"- {blocker}")
            if report.warnings:
                print("Warnings:")
                for warning in report.warnings:
                    print(f"- {warning}")
            return 0 if report.applied else 2
        if args.update_command == "rollback":
            if not args.yes:
                print("Rollback refused: pass --yes to confirm.")
                return 2
            report = manager.rollback(confirm=args.yes)
            print(report.message)
            if report.warnings:
                print("Warnings:")
                for warning in report.warnings:
                    print(f"- {warning}")
            return 0 if report.rolled_back else 2
        if args.update_command == "config":
            auto_check = args.auto_check
            auto_apply = None
            if args.auto_apply is not None:
                auto_apply = args.auto_apply == "on"
            if auto_check is None and auto_apply is None:
                status = manager.status()
                print("Update configuration")
                print(f"auto-check: {status.auto_check_schedule}")
                print(f"auto-apply: {'on' if status.auto_apply_enabled else 'off'}")
                return 0
            state = manager.configure(auto_check=auto_check, auto_apply=auto_apply)
            print("Update configuration saved")
            print(f"auto-check: {state.auto_check_schedule}")
            print(f"auto-apply: {'on' if state.auto_apply_enabled else 'off'}")
            return 0
        print("Use one of: atlas update check|status|apply|rollback|config")
        return 0

    if args.command == "risk":
        from atlas_agent.risk.limits import RiskLimits
        
        if args.risk_command == "status":
            limits = RiskLimits(
                max_position_notional=config.max_position_size,
                max_single_trade_notional=config.max_order_notional,
                allowed_symbols=config.symbol_allowlist,
                blocked_symbols=config.symbol_blocklist or set(),
                live_trading_enabled=config.enable_live_trading
            )
            manager = RiskManager(limits=limits, kill_switch_enabled=config.kill_switch_enabled)
            print("Risk Management Status:")
            print(f"  Live Trading: {'ENABLED' if limits.live_trading_enabled else 'DISABLED'}")
            print(f"  Kill Switch: {'ACTIVE' if manager.kill_switch_enabled else 'Inactive'}")
            print(f"  Max Position Notional: ${limits.max_position_notional}")
            print(f"  Max Order Notional: ${limits.max_single_trade_notional}")
            print(f"  Allowed Symbols: {limits.allowed_symbols if limits.allowed_symbols else 'All'}")
            print(f"  Blocked Symbols: {list(limits.blocked_symbols) if limits.blocked_symbols else 'None'}")
            return 0

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
                return _emit_json_error(
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
    if args.command == "providers" and args.providers_command == "list":
        print("openai_compatible, anthropic, openrouter")
        return 0
    if args.command == "broker" and args.brokers_command == "list":
        print("paper, alpaca, binance, ccxt, ibkr_stub")
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
        if args.backtest_command == "run" or args.backtest_command is None:
            # If no sub-command, use defaults from config
            symbol = getattr(args, "symbol", config.backtest.default_symbol)
            data_path = str(getattr(args, "data", config.backtest.data_path))
            initial_equity = getattr(args, "initial_equity", config.backtest.initial_cash)
            strategy_mode = getattr(args, "strategy", "buy_and_hold")
            slippage_bps = getattr(args, "slippage_bps", 0.0)
            commission_bps = getattr(args, "commission_bps", 0.0)
            use_json = getattr(args, "json", False)

            bt_config = BacktestConfig(
                symbol=symbol,
                data_path=data_path,
                initial_equity=initial_equity,
                strategy_mode=strategy_mode,
                slippage_bps=slippage_bps,
                commission_bps=commission_bps
            )
            
            ensure_sample_data(Path(data_path))

            # Use AuditWriter if available
            audit_writer = None
            try:
                from atlas_agent.audit import AuditWriter
                audit_writer = AuditWriter(config.audit_dir / "audit.log")
            except (ImportError, AttributeError):
                pass

            engine = BacktestEngine(bt_config, audit_writer=audit_writer)
            result = engine.run()

            if use_json:
                print(result.model_dump_json(indent=2))
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
            
            # Write JSON report to disk
            report_path = Path(".atlas/backtests") / result.run_id / "result.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(result.model_dump_json(indent=2))
            print(f"Report saved to: {report_path}")
            
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
        from atlas_agent.dashboard.render import render_dashboard_html
        
        snapshot = collect_dashboard_snapshot(config, Path.cwd())
        
        if args.json:
            print(snapshot.model_dump_json(indent=2))
            return 0
            
        dashboard_path = config.workspace_root / ".atlas" / "dashboard" / "index.html"
        render_dashboard_html(snapshot, dashboard_path)
        print(f"Dashboard generated: {dashboard_path}")
        
        if args.open:
            import webbrowser
            webbrowser.open(f"file://{dashboard_path.resolve()}")
        return 0

    if args.command == "agent":
        from atlas_agent.agent.planner import get_agent_plan, get_agent_plan_payload
        from atlas_agent.agent.runner import run_agent
        from atlas_agent.agent.status import get_agent_status, get_agent_status_payload
        from atlas_agent.learning import run_learning_cycle, generate_reflection
        
        if args.agent_command == "status":
            if getattr(args, "json", False):
                return _emit_json_success(
                    "atlas agent status",
                    get_agent_status_payload(config),
                )
            print(get_agent_status(config))
            return 0
        elif args.agent_command == "plan":
            if getattr(args, "json", False):
                return _emit_json_success(
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
                return _emit_json_success("atlas skills list", skills)
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
                print(f"- {_display_path(path)}")
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

    if args.command == "user":
        from atlas_agent.learning.user_model import (
            format_user_model_summary,
            remember_user_note,
        )

        if args.user_command == "show":
            print(_redact_sensitive_text(format_user_model_summary(config.memory_dir)))
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

    if args.command == "deploy":
        if args.deploy_command in {"docker", "systemd", "vps", "serverless"}:
            return _handle_deploy(args.deploy_command)

    if args.command == "events":
        if args.events_command == "list":
            latest = latest_event_file(config.events_dir)
            events = read_event_file(latest) if latest else []
            if len(events) > max(args.limit, 1):
                events = events[-max(args.limit, 1) :]
            if getattr(args, "json", False):
                return _emit_json_success("atlas events list", _events_to_payload(events))
            if not events:
                print(f"No event logs found under {config.events_dir}.")
                return 0
            for event in events:
                print(
                    f"{event.get('timestamp')} {event.get('event_type')} "
                    f"run={event.get('run_id')} mode={event.get('mode')}"
                )
            return 0
        if args.events_command == "tail":
            latest = latest_event_file(config.events_dir)
            events = read_event_file(latest) if latest else []
            if len(events) > max(args.limit, 1):
                events = events[-max(args.limit, 1) :]
            if not events:
                print(f"No event logs found under {config.events_dir}.")
                return 0
            for event in events:
                print(
                    f"{event.get('timestamp')} {event.get('event_type')} "
                    f"run={event.get('run_id')} mode={event.get('mode')}"
                )
            return 0
        if args.events_command == "doctor":
            report = diagnose_events(config.events_dir)
            print(f"Event Doctor: files={report.files_scanned} events={report.events_scanned}")
            for item in report.errors:
                print(
                    f"[ERROR] {item.code}: {item.message} "
                    f"({item.path or 'n/a'}{':' + str(item.line) if item.line else ''})"
                )
            for item in report.warnings:
                print(
                    f"[WARN] {item.code}: {item.message} "
                    f"({item.path or 'n/a'}{':' + str(item.line) if item.line else ''})"
                )
            return 0 if report.ok else 2

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

    if args.command == "demo" and args.demo_command == "seed":
        result = seed_demo_workspace(
            workspace_dir=config.memory_dir.parent,
            memory_dir=config.memory_dir,
            reports_dir=config.reports_dir,
            skills_dir=config.memory_dir.parent / "skills",
            events_dir=config.events_dir,
            force=args.force,
        )
        if result.warning:
            print(f"demo seed warning: {result.warning}", file=sys.stderr)
            if not result.written_paths:
                return 2
        if not result.written_paths:
            print("Demo seed complete: no new files were created.")
            return 0
        print("Demo seed wrote:")
        for path in result.written_paths:
            print(f"- {_display_path(path)}")
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
    if args.command == "report" and args.report_command == "daily":
        print(generate_daily_report())
        return 0
    if args.command == "portfolio" and args.portfolio_command == "show":
        payload = _portfolio_payload(config)
        if getattr(args, "json", False):
            return _emit_json_success("atlas portfolio show", payload)
        print("Portfolio state is local. No live broker query is made by this command.")
        print(f"Workspace: {payload['workspace']}")
        print(f"Trading mode: {payload['trading_mode']}")
        print(f"Live enabled: {payload['live_enabled']}")
        print(f"Broker: {payload['broker']}")
        print(f"Pending orders: {payload['pending_orders']}")
        return 0
    if args.command == "risk" and args.risk_command == "check":
        effective = _effective_config_with_runtime_kill_switch(config)
        print(f"kill_switch={effective.kill_switch_enabled}")
        print(f"max_position_size={config.max_position_size}")
        print(f"max_trades_per_day={config.max_trades_per_day}")
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
                return _emit_json_error(
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
                    return _emit_json_error(
                        "atlas submit-approved-order --reconcile",
                        code="invalid_order_id",
                        message="Invalid pending order id.",
                    )
                print("Invalid pending order id.")
                return 2
            except InvalidPendingOrderError:
                if args.json:
                    return _emit_json_error(
                        "atlas submit-approved-order --reconcile",
                        code="invalid_pending_order",
                        message="Pending order file is invalid or corrupted.",
                    )
                print("Pending order file is invalid or corrupted.")
                return 2
            except FileNotFoundError:
                if args.json:
                    return _emit_json_error(
                        "atlas submit-approved-order --reconcile",
                        code="pending_order_not_found",
                        message="Pending order not found.",
                    )
                print("Pending order not found.")
                return 2
            except Exception:
                if args.json:
                    return _emit_json_error(
                        "atlas submit-approved-order --reconcile",
                        code="reconcile_failed",
                        message="Reconciliation failed. Manual review required.",
                    )
                print("Reconciliation failed. Manual review required.")
                return 2

            if args.json:
                payload = report.to_dict()
                if report.ok:
                    return _emit_json_success("atlas submit-approved-order --reconcile", payload)
                return _emit_json_error(
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
                    return _emit_json_error(
                        "atlas submit-approved-order --dry-run",
                        code="invalid_order_id",
                        message="Invalid pending order id.",
                    )
                print("Invalid pending order id.")
                return 2
            except InvalidPendingOrderError:
                if args.json:
                    return _emit_json_error(
                        "atlas submit-approved-order --dry-run",
                        code="invalid_pending_order",
                        message="Pending order file is invalid or corrupted.",
                    )
                print("Pending order file is invalid or corrupted.")
                return 2
            except FileNotFoundError:
                if args.json:
                    return _emit_json_error(
                        "atlas submit-approved-order --dry-run",
                        code="pending_order_not_found",
                        message="Pending order not found.",
                    )
                print("Pending order not found.")
                return 2
            except Exception:
                if args.json:
                    return _emit_json_error(
                        "atlas submit-approved-order --dry-run",
                        code="dry_run_failed",
                        message="Dry-run failed. Manual review required.",
                    )
                print("Dry-run failed. Manual review required.")
                return 2

            if args.json:
                payload = report.to_dict()
                if report.ok:
                    return _emit_json_success("atlas submit-approved-order --dry-run", payload)
                return _emit_json_error(
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
                return _emit_json_error(
                    "atlas submit-approved-order",
                    code="invalid_order_id",
                    message="Invalid pending order id.",
                )
            print("Invalid pending order id.")
            return 2
        except InvalidPendingOrderError:
            if args.json:
                return _emit_json_error(
                    "atlas submit-approved-order",
                    code="invalid_pending_order",
                    message="Pending order file is invalid or corrupted.",
                )
            print("Pending order file is invalid or corrupted.")
            return 2
        except FileNotFoundError:
            if args.json:
                return _emit_json_error(
                    "atlas submit-approved-order",
                    code="pending_order_not_found",
                    message="Pending order not found.",
                )
            print("Pending order not found.")
            return 2
        except Exception:
            if args.json:
                return _emit_json_error(
                    "atlas submit-approved-order",
                    code="submit_failed",
                    message="Submit failed. Manual review required.",
                )
            print("Submit failed. Manual review required.")
            return 2

        if args.json:
            payload = report.to_dict()
            if report.ok:
                return _emit_json_success("atlas submit-approved-order", payload)
            return _emit_json_error(
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

    def _safe_research_session_error(exc: Exception) -> tuple[str, str]:
        """Map a research session exception to a safe static status and message."""
        code = str(exc)
        mapping: dict[str, tuple[str, str]] = {
            "artifact_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "artifact_path_not_allowed": ("research_error", "Research command failed."),
            "artifact_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "ambiguous_run_id": ("invalid_research_id", "Invalid research identifier."),
            "ambiguous_plan_id": ("invalid_research_id", "Invalid research identifier."),
            "ambiguous_prompt_packet_id": ("invalid_research_id", "Invalid research identifier."),
            "plan_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "prompt_packet_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "prompt_packet_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "provider_response_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "provider_response_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "ambiguous_provider_response_id": ("invalid_research_id", "Invalid research identifier."),
            "evaluation_data_invalid": ("evaluation_data_invalid", "Evaluation data is invalid."),
            "limit_must_be_positive": ("research_error", "Research command failed."),
            "run_id must not be empty": ("invalid_research_id", "Invalid research identifier."),
            "run_id contains unsafe characters": ("invalid_research_id", "Invalid research identifier."),
            "run_id exceeds maximum length": ("invalid_research_id", "Invalid research identifier."),
            "invalid_max_context_chars": ("invalid_max_context_chars", "Invalid max-context-chars value."),
            "max_context_chars_exceeds_limit": ("invalid_max_context_chars", "Invalid max-context-chars value."),
            "invalid_research_identifier": ("invalid_research_id", "Invalid research identifier."),
            "invalid_research_symbol": ("invalid_research_symbol", "Invalid research symbol."),
            "invalid_source_run_id": ("invalid_source_run_id", "Invalid sandbox lineage."),
            "invalid_prompt_packet_id": ("invalid_prompt_packet_id", "Invalid sandbox lineage."),
            "invalid_sandbox_lineage": ("invalid_sandbox_lineage", "Invalid sandbox lineage."),
            "sandbox_request_not_found": ("sandbox_request_not_found", "Sandbox request not found."),
            "sandbox_request_malformed": ("sandbox_request_malformed", "Sandbox request is malformed."),
            "unsupported_sandbox_schema": ("unsupported_sandbox_schema", "Unsupported sandbox schema."),
            "ambiguous_sandbox_request_id": ("invalid_sandbox_request_id", "Invalid sandbox request ID."),
            "sandbox_replay_mismatch": ("sandbox_replay_mismatch", "Sandbox replay mismatch."),
            "provider_response_file_not_found": ("provider_response_file_not_found", "Provider response file not found."),
            "provider_response_malformed": ("provider_response_malformed", "Provider response is malformed."),
            "provider_response_unsafe": ("provider_response_unsafe", "Provider response is unsafe."),
            "provider_response_import_failed": ("provider_response_import_failed", "Provider response import failed."),
            "invalid_provider_id": ("invalid_provider_id", "Invalid provider ID."),
            "invalid_model_id": ("invalid_model_id", "Invalid model ID."),
            "provider_call_plan_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "provider_call_plan_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "ambiguous_provider_call_plan_id": ("invalid_research_id", "Invalid research identifier."),
            "unsupported_provider_call_plan_schema": ("unsupported_research_artifact_schema", "Unsupported research artifact schema."),
            "invalid_provider_call_plan_lineage": ("invalid_provider_call_plan_lineage", "Invalid provider call-plan artifact."),
            "invalid_provider_call_plan_provider": ("invalid_provider_call_plan_provider", "Invalid provider call-plan artifact."),
            "invalid_provider_call_plan_model": ("invalid_provider_call_plan_model", "Invalid provider call-plan artifact."),
            "provider_call_plan_hash_mismatch": ("provider_call_plan_hash_mismatch", "Invalid provider call-plan artifact."),
            "provider_call_plan_source_missing": ("provider_call_plan_source_missing", "Invalid provider call-plan artifact."),
            "provider_call_plan_source_hash_mismatch": ("provider_call_plan_source_hash_mismatch", "Invalid provider call-plan artifact."),
            "provider_execution_dry_run_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "provider_execution_dry_run_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "ambiguous_provider_execution_dry_run_id": ("invalid_research_id", "Invalid research identifier."),
            "unsupported_provider_execution_dry_run_schema": ("unsupported_research_artifact_schema", "Unsupported research artifact schema."),
            "invalid_provider_execution_dry_run_lineage": ("invalid_provider_execution_dry_run_lineage", "Invalid provider execution dry-run artifact."),
            "invalid_provider_execution_dry_run_provider": ("invalid_provider_execution_dry_run_provider", "Invalid provider execution dry-run artifact."),
            "invalid_provider_execution_dry_run_model": ("invalid_provider_execution_dry_run_model", "Invalid provider execution dry-run artifact."),
            "provider_execution_dry_run_hash_mismatch": ("provider_execution_dry_run_hash_mismatch", "Invalid provider execution dry-run artifact."),
            "provider_execution_dry_run_source_missing": ("provider_execution_dry_run_source_missing", "Invalid provider execution dry-run artifact."),
            "provider_execution_dry_run_source_hash_mismatch": ("provider_execution_dry_run_source_hash_mismatch", "Invalid provider execution dry-run artifact."),
            "provider_execution_dry_run_impossible_boolean": ("provider_execution_dry_run_impossible_boolean", "Invalid provider execution dry-run artifact."),
            "invalid_provider_execution_state_name": ("invalid_provider_execution_state_name", "Invalid provider execution state."),
            "provider_execution_state_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "provider_execution_state_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "ambiguous_provider_execution_state_id": ("invalid_research_id", "Invalid research identifier."),
            "unsupported_provider_execution_state_schema": ("unsupported_research_artifact_schema", "Unsupported research artifact schema."),
            "invalid_provider_execution_state_lineage": ("invalid_provider_execution_state_lineage", "Invalid provider execution state artifact."),
            "invalid_provider_execution_state_provider": ("invalid_provider_execution_state_provider", "Invalid provider execution state artifact."),
            "invalid_provider_execution_state_model": ("invalid_provider_execution_state_model", "Invalid provider execution state artifact."),
            "provider_execution_state_hash_mismatch": ("provider_execution_state_hash_mismatch", "Invalid provider execution state artifact."),
            "provider_execution_state_source_dry_run_missing": ("provider_execution_state_source_dry_run_missing", "Invalid provider execution state artifact."),
            "provider_execution_state_source_dry_run_hash_mismatch": ("provider_execution_state_source_dry_run_hash_mismatch", "Invalid provider execution state artifact."),
            "provider_execution_state_impossible_boolean": ("provider_execution_state_impossible_boolean", "Invalid provider execution state artifact."),
            "invalid_provider_execution_audit_packet_status": ("invalid_provider_execution_audit_packet_status", "Invalid provider execution audit packet."),
            "invalid_provider_execution_audit_packet_lineage": ("invalid_provider_execution_audit_packet_lineage", "Invalid provider execution audit packet artifact."),
            "invalid_provider_execution_audit_packet_provider": ("invalid_provider_execution_audit_packet_provider", "Invalid provider execution audit packet artifact."),
            "invalid_provider_execution_audit_packet_model": ("invalid_provider_execution_audit_packet_model", "Invalid provider execution audit packet artifact."),
            "provider_execution_audit_packet_hash_mismatch": ("provider_execution_audit_packet_hash_mismatch", "Invalid provider execution audit packet artifact."),
            "provider_execution_audit_packet_source_state_missing": ("provider_execution_audit_packet_source_state_missing", "Invalid provider execution audit packet artifact."),
            "provider_execution_audit_packet_source_state_hash_mismatch": ("provider_execution_audit_packet_source_state_hash_mismatch", "Invalid provider execution audit packet artifact."),
            "provider_execution_audit_packet_impossible_boolean": ("provider_execution_audit_packet_impossible_boolean", "Invalid provider execution audit packet artifact."),
            "provider_execution_audit_packet_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "provider_execution_audit_packet_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "ambiguous_provider_execution_audit_packet_id": ("invalid_research_id", "Invalid research identifier."),
            "unsupported_provider_execution_audit_packet_schema": ("unsupported_research_artifact_schema", "Unsupported research artifact schema."),
            "invalid_provider_execution_readiness_report_status": ("invalid_provider_execution_readiness_report_status", "Invalid provider execution readiness report."),
            "invalid_provider_execution_readiness_report_lineage": ("invalid_provider_execution_readiness_report_lineage", "Invalid provider execution readiness report artifact."),
            "invalid_provider_execution_readiness_report_provider": ("invalid_provider_execution_readiness_report_provider", "Invalid provider execution readiness report artifact."),
            "invalid_provider_execution_readiness_report_model": ("invalid_provider_execution_readiness_report_model", "Invalid provider execution readiness report artifact."),
            "provider_execution_readiness_report_hash_mismatch": ("provider_execution_readiness_report_hash_mismatch", "Invalid provider execution readiness report artifact."),
            "provider_execution_readiness_report_source_audit_packet_missing": ("provider_execution_readiness_report_source_audit_packet_missing", "Invalid provider execution readiness report artifact."),
            "provider_execution_readiness_report_source_audit_packet_hash_mismatch": ("provider_execution_readiness_report_source_audit_packet_hash_mismatch", "Invalid provider execution readiness report artifact."),
            "provider_execution_readiness_report_impossible_boolean": ("provider_execution_readiness_report_impossible_boolean", "Invalid provider execution readiness report artifact."),
            "provider_execution_readiness_report_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "provider_execution_readiness_report_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "ambiguous_provider_execution_readiness_report_id": ("invalid_research_id", "Invalid research identifier."),
            "unsupported_provider_execution_readiness_report_schema": ("unsupported_research_artifact_schema", "Unsupported research artifact schema."),
            "invalid_provider_preflight_freeze_id": ("invalid_research_id", "Invalid research identifier."),
            "invalid_provider_preflight_freeze_lineage": ("invalid_research_id", "Invalid research identifier."),
            "invalid_provider_preflight_freeze_status": ("invalid_provider_preflight_freeze_status", "Invalid provider preflight freeze artifact."),
            "invalid_provider_preflight_freeze_model": ("invalid_provider_preflight_freeze_model", "Invalid provider preflight freeze artifact."),
            "invalid_provider_preflight_freeze_provider": ("invalid_provider_preflight_freeze_provider", "Invalid provider preflight freeze artifact."),
            "provider_preflight_freeze_hash_mismatch": ("provider_preflight_freeze_hash_mismatch", "Invalid provider preflight freeze artifact."),
            "provider_preflight_freeze_source_readiness_missing": ("provider_preflight_freeze_source_readiness_missing", "Invalid provider preflight freeze artifact."),
            "provider_preflight_freeze_source_readiness_hash_mismatch": ("provider_preflight_freeze_source_readiness_hash_mismatch", "Invalid provider preflight freeze artifact."),
            "provider_preflight_freeze_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "unsupported_provider_preflight_freeze_schema": ("unsupported_research_artifact_schema", "Unsupported research artifact schema."),
            "provider_preflight_freeze_impossible_boolean": ("provider_preflight_freeze_impossible_boolean", "Invalid provider preflight freeze artifact."),
            "provider_preflight_freeze_impossible_attestation": ("provider_preflight_freeze_impossible_boolean", "Invalid provider preflight freeze artifact."),
            "provider_preflight_freeze_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "ambiguous_provider_preflight_freeze_id": ("invalid_research_id", "Invalid research identifier."),
            "invalid_provider_opt_in_policy_id": ("invalid_research_id", "Invalid research identifier."),
            "invalid_provider_opt_in_policy_lineage": ("invalid_research_id", "Invalid research identifier."),
            "invalid_provider_opt_in_policy_status": ("invalid_provider_opt_in_policy_status", "Invalid provider opt-in policy artifact."),
            "invalid_provider_opt_in_policy_model": ("invalid_provider_opt_in_policy_model", "Invalid provider opt-in policy artifact."),
            "invalid_provider_opt_in_policy_provider": ("invalid_provider_opt_in_policy_provider", "Invalid provider opt-in policy artifact."),
            "provider_opt_in_policy_hash_mismatch": ("provider_opt_in_policy_hash_mismatch", "Invalid provider opt-in policy artifact."),
            "provider_opt_in_policy_source_freeze_missing": ("provider_opt_in_policy_source_freeze_missing", "Invalid provider opt-in policy artifact."),
            "provider_opt_in_policy_source_freeze_hash_mismatch": ("provider_opt_in_policy_source_freeze_hash_mismatch", "Invalid provider opt-in policy artifact."),
            "provider_opt_in_policy_malformed": ("research_artifact_malformed", "Research artifact is malformed."),
            "unsupported_provider_opt_in_policy_schema": ("unsupported_research_artifact_schema", "Unsupported research artifact schema."),
            "provider_opt_in_policy_impossible_boolean": ("provider_opt_in_policy_impossible_boolean", "Invalid provider opt-in policy artifact."),
            "provider_opt_in_policy_forbidden_claim": ("provider_opt_in_policy_forbidden_claim", "Invalid provider opt-in policy artifact."),
            "provider_opt_in_policy_not_found": ("research_artifact_not_found", "Research artifact not found."),
            "ambiguous_provider_opt_in_policy_id": ("invalid_research_id", "Invalid research identifier."),
            "artifact_path_not_allowed": ("research_error", "Research command failed."),
        }
        return mapping.get(code, ("research_error", "Research command failed."))

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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            print(json.dumps(result, indent=2, sort_keys=True))
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
            status, message = _safe_research_session_error(exc)
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
