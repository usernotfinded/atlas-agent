from __future__ import annotations

import argparse
from pathlib import Path

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
from atlas_agent.strategies.moving_average import MovingAverageStrategy
from atlas_agent.workspace import (
    DEFAULT_TEMPLATE,
    WorkspaceInitError,
    init_workspace,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas")
    subparsers = parser.add_subparsers(dest="command")
    init = subparsers.add_parser("init")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--template", default=DEFAULT_TEMPLATE)
    init.add_argument("--force", action="store_true")
    subparsers.add_parser("validate")

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
    agent_sub.add_parser("status")
    agent_sub.add_parser("plan")

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
    portfolio_sub.add_parser("show")

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

    models = subparsers.add_parser("models")
    models_sub = models.add_subparsers(dest="models_command")
    models_update_readme = models_sub.add_parser("update-readme")
    models_sub.add_parser("list")
    return parser


def run_once(
    mode: str,
    config: AtlasConfig | None = None,
) -> OrderResult:
    config = config or AtlasConfig.from_env()
    config.ensure_dirs()
    ensure_sample_data(config.data_path)
    bars = CSVMarketDataProvider(config.data_path).load_bars(config.default_symbol)
    decision = MovingAverageStrategy().decide(bars)
    latest = bars[-1]
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        raise
    config = AtlasConfig.from_env()

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
        result = run_once(mode=args.mode, config=config)
        print(f"{args.mode} result: {result.status} - {result.message}")
        if result.reasons:
            print("Reasons:", "; ".join(result.reasons))
        return 0 if result.status in {"filled", "held", "pending_approval"} else 2
        
    if args.command == "agent":
        from atlas_agent.agent.status import get_agent_status
        from atlas_agent.agent.planner import get_agent_plan
        from atlas_agent.agent.runner import run_agent
        
        if args.agent_command == "status":
            print(get_agent_status(config))
            return 0
        elif args.agent_command == "plan":
            print(get_agent_plan(config))
            return 0
        elif args.agent_command == "run":
            result = run_agent(mode=args.mode, config=config)
            if result.lock_status:
                print(result.lock_status)
            print(f"agent run {args.mode}: {result.status}")
            print(f"Report: {result.report_path}")
            if result.order_status:
                print(f"Order status: {result.order_status}")
            print(f"Notification: {result.notification_status}")
            print(f"Git: {result.git_status}")
            return 0

    if args.command == "routine" and args.routine_command == "run":
        from atlas_agent.routines.engine import RoutineLockError, run_routine
        try:
            result = run_routine(
                args.name,
                mode=args.mode,
                config=config,
                order_runner=lambda **kwargs: run_once(
                    **kwargs,
                ),
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
        print("Portfolio state is local. No live broker query is made by this command.")
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
        print("Vals AI Finance Agent Benchmark (Reference Only)")
        print("| Rank | Model | Score |")
        print("|---|---|---|")
        for model in list_roster()[:7]:
            score_str = f"{model.score:.2f}%" if model.score is not None else "N/A"
            print(f"| {model.rank} | {model.model_name} | {score_str} |")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
