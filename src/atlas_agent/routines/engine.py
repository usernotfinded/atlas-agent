from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from atlas_agent.config import AtlasConfig
from atlas_agent.events.log import EventLogger
from atlas_agent.execution.order import OrderResult
from atlas_agent.leaderboard.roster import list_roster
from atlas_agent.notifications.clickup import (
    ClickUpNotifier,
    NotificationConfigurationError,
)
from atlas_agent.research.perplexity import (
    PerplexityResearchProvider,
    ResearchConfigurationError,
)
from atlas_agent.research.web_research import OfflineResearchProvider
from atlas_agent.routines.context_loader import load_routine_context
from atlas_agent.routines.git_sync import GitSync, GitSyncError
from atlas_agent.routines.lock import RoutineLockError, routine_lock
from atlas_agent.routines.memory_writer import append_memory, overwrite_memory
from atlas_agent.routines.routine_result import RoutineResult


ROUTINE_NAMES = {
    "pre_market",
    "market_open",
    "midday_scan",
    "market_close",
    "weekly_review",
}

OrderRunner = Callable[..., OrderResult]


def run_routine(
    name: str,
    *,
    mode: str,
    config: AtlasConfig | None = None,
    order_runner: OrderRunner | None = None,
    research_provider=None,
    notifier: ClickUpNotifier | None = None,
    git_sync: GitSync | None = None,
    event_logger: EventLogger | None = None,
    run_id: str | None = None,
    command: str = "atlas routine run",
) -> RoutineResult:
    if name not in ROUTINE_NAMES:
        raise ValueError(f"unknown routine: {name}")
    if mode not in {"paper", "live"}:
        raise ValueError("routine mode must be paper or live")
    config = config or AtlasConfig.from_env()
    config.ensure_dirs()
    with routine_lock(_workspace_dir(config), name) as lock:
        return _run_routine_unlocked(
            name,
            mode=mode,
            config=config,
            order_runner=order_runner,
            research_provider=research_provider,
            notifier=notifier,
            git_sync=git_sync,
            lock_status=lock.recovery_message,
            event_logger=event_logger,
            run_id=run_id,
            command=command,
        )


def _run_routine_unlocked(
    name: str,
    *,
    mode: str,
    config: AtlasConfig,
    order_runner: OrderRunner | None = None,
    research_provider=None,
    notifier: ClickUpNotifier | None = None,
    git_sync: GitSync | None = None,
    lock_status: str | None = None,
    event_logger: EventLogger | None = None,
    run_id: str | None = None,
    command: str = "atlas routine run",
) -> RoutineResult:
    context = load_routine_context(
        memory_dir=config.memory_dir,
        reports_dir=config.reports_dir,
    )
    if event_logger is not None and run_id is not None:
        event_logger.write(
            "memory_loaded",
            run_id=run_id,
            command=command,
            mode=mode,
            payload={"files": sorted(context.memory.keys())},
        )

    research = _run_research(config.default_symbol, research_provider)
    if event_logger is not None and run_id is not None:
        event_logger.write(
            "research_completed",
            run_id=run_id,
            command=command,
            mode=mode,
            payload={"summary": research[:200]},
        )
        top_models = [
            {"rank": model.rank, "model": model.model_name, "score": model.score}
            for model in list_roster()[:3]
        ]
        event_logger.write(
            "model_guidance_loaded",
            run_id=run_id,
            command=command,
            mode=mode,
            payload={"top_models": top_models},
        )

    order_result: OrderResult | None = None
    if name in {"market_open", "midday_scan"} and order_runner is not None:
        try:
            order_result = order_runner(
                mode=mode,
                config=config,
                event_logger=event_logger,
                run_id=run_id,
                command=command,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            order_result = order_runner(mode=mode, config=config)

    report_path = _write_routine_report(
        name=name,
        mode=mode,
        reports_dir=config.reports_dir,
        research_summary=research,
        order_result=order_result,
        memory_files=tuple(context.memory),
    )
    updated = _update_memory(
        name=name,
        mode=mode,
        config=config,
        report_path=report_path,
        research_summary=research,
        order_result=order_result,
    )
    if event_logger is not None and run_id is not None and updated:
        event_logger.write(
            "memory_updated",
            run_id=run_id,
            command=command,
            mode=mode,
            payload={"files": [str(path) for path in updated]},
        )

    notification_status = _notify(notifier, report_path)
    if event_logger is not None and run_id is not None:
        event_logger.write(
            "notification_sent",
            run_id=run_id,
            command=command,
            mode=mode,
            payload={"status": notification_status},
        )
    git_status = _sync_git(git_sync, name)
    if event_logger is not None and run_id is not None:
        event_logger.write(
            "git_sync_completed",
            run_id=run_id,
            command=command,
            mode=mode,
            payload={"status": git_status},
        )
    return RoutineResult(
        name=name,
        mode=mode,
        status="complete",
        report_path=report_path,
        memory_files_updated=updated,
        order_status=order_result.status if order_result else None,
        notification_status=notification_status,
        git_status=git_status,
        lock_status=lock_status,
    )


def _workspace_dir(config: AtlasConfig) -> Path:
    return config.memory_dir.parent


def _run_research(symbol: str, provider) -> str:
    provider = provider or _default_research_provider()
    try:
        return provider.research_market(symbol).summary
    except ResearchConfigurationError:
        return OfflineResearchProvider().research_market(symbol).summary


def _default_research_provider():
    return PerplexityResearchProvider()


def _write_routine_report(
    *,
    name: str,
    mode: str,
    reports_dir: Path,
    research_summary: str,
    order_result: OrderResult | None,
    memory_files: tuple[str, ...],
) -> Path:
    day = datetime.now(UTC).date().isoformat()
    subdir = reports_dir / ("weekly" if name == "weekly_review" else "daily")
    subdir.mkdir(parents=True, exist_ok=True)
    suffix = {
        "pre_market": "pre-market",
        "market_open": "market-open",
        "midday_scan": "midday",
        "market_close": "close",
        "weekly_review": "weekly-review",
    }[name]
    path = subdir / f"{day}-{suffix}.md"
    order_text = "No order action for this routine."
    if order_result is not None:
        order_text = f"{order_result.status}: {order_result.message}"
    content = "\n".join(
        [
            f"# {name.replace('_', ' ').title()} Routine",
            "",
            f"- Mode: {mode}",
            f"- Memory files read: {', '.join(memory_files)}",
            f"- Research: {research_summary}",
            f"- Order result: {order_text}",
            "- Live execution requires approval before broker execution.",
            "- Next action: human review of report and pending orders, if any.",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
    latest = reports_dir / "daily" / "latest.md"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(content, encoding="utf-8")
    return path


def _update_memory(
    *,
    name: str,
    mode: str,
    config: AtlasConfig,
    report_path: Path,
    research_summary: str,
    order_result: OrderResult | None,
) -> tuple[Path, ...]:
    updates: list[Path] = []
    body = (
        f"Routine `{name}` ran in `{mode}` mode.\n\n"
        f"Report: `{report_path}`\n\n"
        f"Research: {research_summary}\n"
    )
    updates.append(append_memory(config.memory_dir, "daily_notes.md", name, body))
    if order_result is not None:
        updates.append(
            append_memory(
                config.memory_dir,
                "trade_journal.md",
                f"{name} order result",
                f"{order_result.status}: {order_result.message}",
            )
        )
        updates.append(
            overwrite_memory(
                config.memory_dir,
                "open_positions.md",
                (
                    "# Open Positions\n\n"
                    "Current position state should be reconciled with broker or "
                    "paper portfolio after each market routine.\n"
                ),
            )
        )
    if name == "market_close":
        updates.append(
            append_memory(
                config.memory_dir,
                "portfolio.md",
                "market close",
                "Daily portfolio recap written. Compare against benchmark before live changes.",
            )
        )
    if name == "weekly_review":
        updates.append(
            append_memory(
                config.memory_dir,
                "weekly_review.md",
                "weekly review",
                "Reviewed weekly routine. Strategy changes require explicit justification.",
            )
        )
    return tuple(updates)


def _notify(notifier: ClickUpNotifier | None, report_path: Path) -> str:
    notifier = notifier or ClickUpNotifier()
    try:
        notifier.send(report_path.read_text(encoding="utf-8")[:2000])
    except NotificationConfigurationError:
        return "not_configured"
    return "sent"


def _sync_git(git_sync: GitSync | None, name: str) -> str:
    git_sync = git_sync or GitSync.from_env()
    try:
        return git_sync.commit(f"routine: {name} {datetime.now(UTC).date().isoformat()}")
    except GitSyncError as exc:
        return f"commit refused: {exc}"
