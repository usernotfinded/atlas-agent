# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/schedule.py
# PURPOSE: CLI handler for `atlas schedule` — prints a crontab line or writes a
#          GitHub Actions workflow. Suggests; never installs.
# DEPS:    scheduler.cron, scheduler.github_actions
# ==============================================================================

"""CLI handler for `atlas schedule`."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_schedule(context: CLIContext) -> int | None:
    args = context.args
    from atlas_agent.scheduler.github_actions import write_github_actions_workflow

    if args.command == "schedule" and args.schedule_command == "github-actions":
        try:
            path = write_github_actions_workflow(template=args.template)
        except ValueError as exc:
            print(f"schedule refused: {exc}")
            return 2
        print(f"GitHub Actions workflow generated: {path}")
        return 0
    return None

