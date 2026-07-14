# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/update.py
# PURPOSE: CLI handler for `atlas update` — checks for and applies a self-update.
#          The apply path is gated: it refuses while there are open positions or
#          pending orders.
# DEPS:    update.manager (SafeUpdateManager), update.safety (the gate)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path

from atlas_agent.cli_context import CLIContext
from atlas_agent.update import SafeUpdateManager


def handle_update(context: CLIContext) -> int:
    args = context.args
    config = context.config

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
