# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/scheduler.py
# PURPOSE: CLI handler for `atlas scheduler` — the unattended entry point invoked by
#          cron or CI. Requires a valid discipline profile and fails closed without one.
# DEPS:    scheduler.runner
# ==============================================================================

"""CLI handler for `atlas scheduler`."""

# --- IMPORTS ---
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

