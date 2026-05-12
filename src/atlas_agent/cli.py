from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

YELLOW = "\033[93m"
RESET = "\033[0m"

from atlas_agent import __version__
from atlas_agent.backtest import BacktestConfig, BacktestEngine
from atlas_agent.brokers.alpaca import AlpacaBroker
from atlas_agent.brokers.binance import BinanceBroker
from atlas_agent.brokers.ccxt_adapter import CCXTBroker
from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.config import AtlasConfig
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
    read_recent_events,
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
from atlas_agent.memory_doctor import run_memory_doctor
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
MAX_CLI_SNIPPET_CHARS = 220


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
    brokers_sync.add_argument("--json", action="store_true")

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

    research = subparsers.add_parser("research")
    research_sub = research.add_subparsers(dest="research_command")
    research_market = research_sub.add_parser("market")
    research_market.add_argument("--symbol", required=True)

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
    portfolio = PortfolioState(cash=config.starting_cash)
    broker = _broker_for_mode(mode, config, portfolio, audit)
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
    if mode == "paper":
        return PaperBroker(
            portfolio,
            audit=audit,
            journal=TradeJournal(config.memory_dir / "trade_journal.md"),
        )
    if config.live_broker == "alpaca":
        return AlpacaBroker(config)
    if config.live_broker == "binance":
        return BinanceBroker(config)
    return CCXTBroker(config)


def _memory_search_matches(config: AtlasConfig, query: str) -> tuple[list[dict[str, str]], str | None]:
    memory_dir = config.memory_dir
    if not memory_dir.exists():
        return [], f"No memory directory found at {memory_dir}."

    files = _memory_markdown_files(memory_dir)
    if not files:
        return [], f"No Markdown memory files found under {memory_dir} or {memory_dir / 'conversations'}."

    query_lower = query.lower()
    matches: list[dict[str, str]] = []
    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace")
        index = content.lower().find(query_lower)
        if index < 0:
            continue
        snippet = _snippet(content, index, len(query))
        matches.append({"path": _display_path(path), "snippet": snippet})
    return matches, None


def _handle_memory_search(config: AtlasConfig, query: str) -> int:
    matches, warning = _memory_search_matches(config, query)
    if warning:
        print(warning)
        return 0
    if not matches:
        print(f"No memory matches found for: {query}")
        return 0
    for match in matches:
        print(f"{match['path']}: {match['snippet']}")
    return 0


def _memory_markdown_files(memory_dir: Path) -> list[Path]:
    files = [path for path in sorted(memory_dir.glob("*.md")) if path.is_file()]
    conversations_dir = memory_dir / "conversations"
    if conversations_dir.exists():
        files.extend(
            path
            for path in sorted(conversations_dir.rglob("*.md"))
            if path.is_file()
        )
    return files


def _snippet(content: str, index: int, query_length: int) -> str:
    start = max(0, index - 80)
    end = min(len(content), index + max(query_length, 1) + 140)
    snippet = " ".join(content[start:end].split())
    if start > 0:
        snippet = "... " + snippet
    if end < len(content):
        snippet += " ..."
    snippet = _redact_sensitive_text(snippet)
    if len(snippet) > MAX_CLI_SNIPPET_CHARS:
        snippet = snippet[: MAX_CLI_SNIPPET_CHARS - 4].rstrip() + " ..."
    return snippet


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


def _memory_doctor_payload(config: AtlasConfig) -> dict[str, Any]:
    skills_dir = config.memory_dir.parent / "skills"
    result = run_memory_doctor(
        memory_dir=config.memory_dir,
        pending_orders_dir=config.pending_orders_dir,
        reports_dir=config.reports_dir,
        skills_dir=skills_dir,
        stale_hours=24,
    )
    return {
        "ok": result.ok,
        "checked_at": result.checked_at,
        "errors": [asdict(item) for item in result.errors],
        "warnings": [asdict(item) for item in result.warnings],
        "finding_count": len(result.findings),
    }


def _print_memory_doctor_text(payload: dict[str, Any]) -> None:
    print("Memory Doctor")
    print(f"Checked at: {payload['checked_at']}")
    if not payload["errors"] and not payload["warnings"]:
        print("No issues found.")
        return
    for error in payload["errors"]:
        print(f"[ERROR] {error['code']}: {error['message']} ({error.get('path') or 'n/a'})")
    for warning in payload["warnings"]:
        print(f"[WARN] {warning['code']}: {warning['message']} ({warning.get('path') or 'n/a'})")


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


def _live_broker_credentials_configured(config: AtlasConfig | None) -> bool:
    if config is None:
        return False
    if config.live_broker == "alpaca":
        return bool(os.getenv("ALPACA_API_KEY")) and bool(os.getenv("ALPACA_SECRET_KEY"))
    if config.live_broker == "binance":
        return bool(os.getenv("BINANCE_API_KEY")) and bool(os.getenv("BINANCE_SECRET_KEY"))
    if config.live_broker == "ccxt":
        return bool(os.getenv("CCXT_API_KEY")) or bool(os.getenv("EXCHANGE_API_KEY"))
    return False


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

    live_creds = _live_broker_credentials_configured(config)

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
        from atlas_agent.config.secrets import canonical_env_var
        from atlas_agent.config.paths import get_config_toml_path, get_env_atlas_path
        import json
        
        if args.config_command == "paths":
            print(f"Config TOML: {get_config_toml_path()}")
            print(f"Secrets ENV: {get_env_atlas_path()}")
            return 0

        if args.config_command == "show":
            if getattr(args, "effective", False):
                config = get_config()
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
                raw = get_raw_config()
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
                config = get_config()
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
                set_secret(env_var, args.value)
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
            config = get_config()
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
            os.system(f"{editor} {path}")
            return 0

        if args.config_command == "check":
            config = get_config()
            payload = config.model_dump(mode="json")
            def redact_secrets_in_dict(d):
                for k, v in d.items():
                    if isinstance(v, dict):
                        redact_secrets_in_dict(v)
                    elif isinstance(k, str) and is_secret_key(k):
                        d[k] = "[REDACTED]"
            redact_secrets_in_dict(payload)
            if getattr(args, "json", False):
                from atlas_agent.output import emit_json
                return emit_json(payload)
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
        from atlas_agent.config.secrets import set_secret
        config = get_config()

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
                        key = input(f"Enter {env_var} (input hidden): ").strip()
                    except (EOFError, OSError):
                        print("Non-interactive mode. Use `atlas config set_atlas_secret <key> <value>`.")
                        return 2
                    if key:
                        set_secret(env_var, key)
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
        print(load_error, file=sys.stderr)
        return 1
    if config is None:
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

    if args.command == "audit":
        from atlas_agent.audit import verify_audit_log, verify_run_manifest

        if args.audit_command == "verify":
            if args.all:
                manifest_dir = config.audit_dir / "manifests"
                if not manifest_dir.exists():
                    print("No manifests found.")
                    return 0
                manifests = list(manifest_dir.glob("*.json"))
                if not manifests:
                    print("No manifests found.")
                    return 0
                
                print(f"Verifying {len(manifests)} manifests...")
                all_valid = True
                for manifest_path in sorted(manifests):
                    result = verify_run_manifest(manifest_path)
                    status_icon = "✅" if result.valid else "❌"
                    print(f"{status_icon} {manifest_path.name}: {result.manifest_status}")
                    if not result.valid:
                        all_valid = False
                        for error in result.errors:
                            print(f"  - {error}")
                return 0 if all_valid else 2

            if args.manifest:
                result = verify_run_manifest(args.manifest)
                if result.valid:
                    print(
                        f"Audit manifest verification successful. Checked {result.events_checked} events."
                    )
                    print(f"Status: {result.manifest_status.upper()}")
                    return 0
                else:
                    print(
                        f"Audit manifest verification FAILED. Checked {result.events_checked} events."
                    )
                    print(f"Status: {result.manifest_status.upper()}")
                    for error in result.errors:
                        print(f"- {error}")
                    return 2

            path = args.path or (config.audit_dir / "events.jsonl")
            result = verify_audit_log(path)
            if result.valid:
                print(
                    f"Audit log verification successful. Checked {result.events_checked} events."
                )
                return 0
            else:
                print(
                    f"Audit log verification FAILED. Checked {result.events_checked} events."
                )
                for error in result.errors:
                    print(f"- {error}")
                return 2

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

    if args.command == "status":
        from atlas_agent.agent.status import get_agent_status
        print(get_agent_status(config))
        update = _check_for_updates()
        if update:
            print(f"\n[UPDATE] A newer version of Atlas Agent is available: {update} (current: {__version__})")
            print("Run 'git pull' to update.")
        return 0
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

        report = run_diagnostics(config)
        
        if getattr(args, "json", False):
            import json
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print_readiness_report(report)
            
        return 0
    if args.command == "providers" and args.providers_command == "list":
        print("openai_compatible, anthropic, openrouter")
        return 0
    if args.command == "broker" and args.brokers_command == "list":
        print("paper, alpaca, binance, ccxt, ibkr_stub")
        return 0
    if args.command == "broker" and args.brokers_command == "sync":
        from atlas_agent.brokers.sync import BrokerSyncService
        from atlas_agent.brokers.paper import PaperBroker, PaperBrokerAdapter
        
        # For CLI sync, use paper broker as default if nothing else is configured
        paper_broker = PaperBroker(state=PortfolioState(cash=config.starting_cash))
        broker_provider = PaperBrokerAdapter(broker=paper_broker)
        
        sync_service = BrokerSyncService(broker=broker_provider)
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

    if args.command == "memory":
        from atlas_agent.learning import ingest_conversation
        from atlas_agent.learning.nudges import generate_memory_nudge

        if args.memory_command == "ingest":
            if not args.file.exists():
                print(f"memory ingest skipped: file not found: {args.file}")
                return 0
            path = ingest_conversation(config.memory_dir, args.file)
            print(f"Conversation memory ingested: {path}")
            return 0
        if args.memory_command == "search":
            if getattr(args, "json", False):
                matches, warning = _memory_search_matches(config, args.query)
                return _emit_json_success(
                    "atlas memory search",
                    {
                        "query": args.query,
                        "matches": matches,
                        "warning": warning,
                    },
                )
            return _handle_memory_search(config, args.query)
        if args.memory_command == "doctor":
            payload = _memory_doctor_payload(config)
            if getattr(args, "json", False):
                return _emit_json_success("atlas memory doctor", payload)
            _print_memory_doctor_text(payload)
            return 0
        if args.memory_command == "summarize":
            print("Memory summary is generated through agent learn/reflect cycles.")
            return 0
        if args.memory_command == "nudge":
            nudge = generate_memory_nudge(config.memory_dir)
            print(nudge or "No memory nudge available yet.")
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
        path = ApprovalManager(config.pending_orders_dir).approve(args.order_id)
        print(f"Approved pending order: {path}")
        return 0
    if args.command == "research" and args.research_command == "market":
        try:
            report = get_research_provider().research_market(args.symbol)
        except ResearchConfigurationError as exc:
            print(f"research skipped safely: {exc}")
            return 0
        print(report.summary)
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
