# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/git_sync.py
# PURPOSE: CLI handler for `atlas git-sync` — commits and pushes memory/ and
#          reports/. The only command that can publish workspace content to a remote.
# DEPS:    routines.git_sync (the allowlist and the secret scan live there)
# ==============================================================================

"""CLI handler for `atlas git-sync`."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_git_sync(context: CLIContext) -> int | None:
    args = context.args
    from atlas_agent.routines.git_sync import GitSync
    from atlas_agent.routines.git_sync import GitSyncError

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
    return None

