"""CLI handler for `atlas scheduler`."""
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_scheduler(context: CLIContext) -> int | None:
    args = context.args
    config = context.config
    from atlas_agent.scheduler.runner import run_scheduler_once
    from atlas_agent.cli import (
        _check_discipline_or_exit,
        run_once,
    )

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
    return None

