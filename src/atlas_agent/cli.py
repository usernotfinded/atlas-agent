from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

from atlas_agent import __version__
from atlas_agent.backtest.runner import run_backtest
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
from atlas_agent.leaderboard.roster import (
    list_roster,
    update_readme_roster,
)
from atlas_agent.market_data.csv_provider import CSVMarketDataProvider
from atlas_agent.market_data.sample_data import ensure_sample_data
from atlas_agent.portfolio.journal import TradeJournal
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.reports.daily import generate_daily_report
from atlas_agent.research.perplexity import (
    PerplexityResearchProvider,
    ResearchConfigurationError,
)
from atlas_agent.risk.kill_switch import KillSwitch
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
from atlas_agent.strategies.moving_average import MovingAverageStrategy
from atlas_agent.workspace import (
    DEFAULT_TEMPLATE,
    WorkspaceInitError,
    init_workspace,
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

Atlas Agent is a self-improving AI trading agent.
It runs autonomous trading cycles during market hours and
self-improvement cycles during off-hours.
"""
    epilog = """
Core Commands:
  atlas init          - Initialize a new workspace
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
    subparsers = parser.add_subparsers(dest="command")
    init = subparsers.add_parser("init")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--template", default=DEFAULT_TEMPLATE)
    init.add_argument("--force", action="store_true")
    subparsers.add_parser("validate")

    subparsers.add_parser("status")
    subparsers.add_parser("plan")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--mode", choices=("auto", "paper", "live"), default="auto")
    run_parser.add_argument("--continuous", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--interval", type=int, default=60)
    run_parser.add_argument("--max-cycles", type=int, default=None)

    providers = subparsers.add_parser("providers")
    providers_sub = providers.add_subparsers(dest="providers_command")
    providers_sub.add_parser("list")

    brokers = subparsers.add_parser("brokers")
    brokers_sub = brokers.add_subparsers(dest="brokers_command")
    brokers_sub.add_parser("list")

    backtest = subparsers.add_parser("backtest")
    backtest.add_argument("--strategy", default="moving_average")
    backtest.add_argument("--symbol", default=None)

    run_once_parser = subparsers.add_parser("run-once")
    run_once_parser.add_argument("--mode", choices=("paper", "live"), default="paper")

    agent = subparsers.add_parser("agent")
    agent_sub = agent.add_subparsers(dest="agent_command")
    agent_run = agent_sub.add_parser("run")
    agent_run.add_argument("--mode", choices=("auto", "paper", "live"), default="auto")
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

    telegram = subparsers.add_parser("telegram")
    telegram_sub = telegram.add_subparsers(dest="telegram_command")
    telegram_sub.add_parser("run")
    telegram_sub.add_parser("test")

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

    kill_switch = subparsers.add_parser("kill-switch")
    kill_sub = kill_switch.add_subparsers(dest="kill_command")
    kill_sub.add_parser("enable")
    kill_sub.add_parser("disable")

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

    models = subparsers.add_parser("models")
    models_sub = models.add_subparsers(dest="models_command")
    models_sub.add_parser("update-readme")
    models_list = models_sub.add_parser("list")
    models_list.add_argument("--json", action="store_true")
    return parser


def run_once(
    mode: str,
    config: AtlasConfig | None = None,
    event_logger: EventLogger | None = None,
    run_id: str | None = None,
    command: str = "atlas run-once",
) -> OrderResult:
    config = config or AtlasConfig.from_env()
    config.ensure_dirs()
    ensure_sample_data(config.data_path)
    bars = CSVMarketDataProvider(config.data_path).load_bars(config.default_symbol)
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


def _is_workspace(config: AtlasConfig) -> bool:
    # If memory_dir is absolute, we assume it's a test or explicit config
    if config.memory_dir.is_absolute():
        return True
    # A workspace is identified by the presence of core directories
    # Check for memory and either configs or routines to be sure
    return (config.memory_dir.exists() and 
            ((config.memory_dir.parent / "configs").exists() or 
             (config.memory_dir.parent / "routines").exists()))


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


def _print_welcome() -> None:
    print(r"""
      ___ _____ _      _   ___      _   ___ ___ _  _ _____ 
     / _ \_   _| |    /_\ / __|    /_\ / __| __| \| |_   _|
    / ___ \| | | |__ / _ \\__ \   / _ \ (_ | _|| .` | | |  
   /_/   \_|_| |____/_/ \_\___/  /_/ \_\___|___|_|\_| |_|  

Atlas Agent is a self-improving AI trading agent.
""")
    update = _check_for_updates()
    if update:
        print(f"NOTICE: A newer version of Atlas Agent is available: {update} (current: {__version__})")
        print("Run 'git pull' to update your local installation.")
        print("")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        raise

    try:
        config = AtlasConfig.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 1

    # Commands that do not require a workspace
    if args.command in {"init", "validate", "models"} or "--help" in sys.argv or "-h" in sys.argv:
        pass
    elif not _is_workspace(config):
        print("Atlas Agent needs a workspace before it can run.")
        print("")
        print("Create one:")
        print("  atlas init my-trader --template routine-trader")
        print("  cd my-trader")
        print("  atlas")
        return 2

    if args.command is None:
        from atlas_agent.agent.runner import run_agent
        _print_welcome()
        print("Starting autonomous cycle...")
        result = run_agent(mode="auto", config=config, continuous=False)
        return 0 if result and result.status in {"filled", "held", "pending_approval", "simulated", "complete"} else 2

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
        result = run_agent(
            mode=args.mode,
            config=config,
            continuous=args.continuous,
            interval=args.interval,
            max_cycles=args.max_cycles
        )
        return 0 if result and result.status in {"filled", "held", "pending_approval", "simulated", "complete"} else 2

    if args.command == "init":
        try:
            result = init_workspace(
                args.path,
                template=args.template,
                force=args.force,
            )
        except WorkspaceInitError as exc:
            print(f"init refused: {exc}")
            return 2
        action = "overwritten" if result.overwritten else "created"
        print(
            f"Atlas Agent workspace {action}: "
            f"{result.path} (template: {result.template})"
        )
        return 0
    if args.command == "validate":
        config.ensure_dirs()
        (config.reports_dir / "daily").mkdir(parents=True, exist_ok=True)
        (config.reports_dir / "weekly").mkdir(parents=True, exist_ok=True)
        ensure_sample_data(config.data_path)
        print("Configuration valid. Default mode:", config.trading_mode)
        print("Live trading enabled:", config.enable_live_trading)
        return 0
    if args.command == "providers" and args.providers_command == "list":
        print("null, openai_compatible, anthropic, openrouter, local_command")
        return 0
    if args.command == "brokers" and args.brokers_command == "list":
        print("paper, alpaca, binance, ccxt, ibkr_stub")
        return 0
    if args.command == "backtest":
        symbol = args.symbol or config.default_symbol
        result = run_backtest(symbol=symbol, strategy_name=args.strategy, config=config)
        print(f"Backtest complete: {symbol}")
        print(f"Total return: {result.metrics.total_return:.2%}")
        if result.report_paths:
            print("JSON report:", result.report_paths[0])
            print("Markdown report:", result.report_paths[1])
            print("CSV trade log:", result.report_paths[2])
        return 0
    if args.command == "run-once":
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
            result = run_agent(
                mode=args.mode,
                config=config,
                continuous=args.continuous,
                interval=args.interval,
                max_cycles=args.max_cycles
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

    if args.command == "telegram":
        from atlas_agent.telegram_control import (
            TELEGRAM_COMMANDS,
            get_telegram_diagnostics,
        )

        if args.telegram_command == "test":
            print(get_telegram_diagnostics().format())
            return 0
        if args.telegram_command == "run":
            print("Telegram control plane adapter is optional and stdlib-only in this package.")
            print("Configure TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS, then wire polling/webhook in your deployment wrapper.")
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
        print(f"kill_switch={config.kill_switch_enabled}")
        print(f"max_position_size={config.max_position_size}")
        print(f"max_trades_per_day={config.max_trades_per_day}")
        return 0
    if args.command == "kill-switch":
        switch = KillSwitch(config.memory_dir / "kill_switch.enabled")
        if args.kill_command == "enable":
            switch.enable()
            print("Kill switch enabled")
            return 0
        if args.kill_command == "disable":
            switch.disable()
            print("Kill switch disabled")
            return 0
    if args.command == "approve-order":
        path = ApprovalManager(config.pending_orders_dir).approve(args.order_id)
        print(f"Approved pending order: {path}")
        return 0
    if args.command == "research" and args.research_command == "market":
        try:
            report = PerplexityResearchProvider().research_market(args.symbol)
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
    if args.command == "models" and args.models_command == "update-readme":
        try:
            update_readme_roster()
            print("README model benchmark reference updated")
        except Exception as exc:
            print(f"update-readme failed: {exc}")
            return 2
        return 0
        
    if args.command == "models" and args.models_command == "list":
        models = [
            {
                "rank": model.rank,
                "model": model.model_name,
                "provider": model.provider,
                "score": model.score,
                "benchmark_name": model.benchmark_name,
                "benchmark_url": model.benchmark_url,
                "benchmark_updated": model.benchmark_updated,
            }
            for model in list_roster()[:7]
        ]
        if getattr(args, "json", False):
            return _emit_json_success(
                "atlas models list",
                {
                    "benchmark": "Vals AI Finance Agent",
                    "reference_only": True,
                    "models": models,
                },
            )
        print("Vals AI Finance Agent Benchmark (Reference Only)")
        print("| Rank | Model | Score |")
        print("|---|---|---|")
        for model in models:
            score = model["score"]
            score_str = f"{score:.2f}%" if isinstance(score, float) else "N/A"
            print(f"| {model['rank']} | {model['model']} | {score_str} |")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
