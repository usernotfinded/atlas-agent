"""CLI handler for `atlas git-sync`."""
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

