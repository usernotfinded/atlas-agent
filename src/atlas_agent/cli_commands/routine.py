# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/routine.py
# PURPOSE: CLI handler for `atlas routine` — runs a named routine once.
# DEPS:    routines.engine (which takes the single-instance lock)
# ==============================================================================

"""CLI handler for `atlas routine`."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_routine(context: CLIContext) -> int | None:
    args = context.args
    config = context.config
    from atlas_agent.events import EventLogger
    from atlas_agent.events import generate_run_id
    from atlas_agent.routines.engine import run_routine
    from atlas_agent.routines.lock import RoutineLockError
    from atlas_agent.routines.lock import routine_status
    from atlas_agent.routines.lock import unlock_routine
    from atlas_agent.cli import (
        _check_discipline_or_exit,
        _resolve_symbol,
        run_once,
    )

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
    return None

