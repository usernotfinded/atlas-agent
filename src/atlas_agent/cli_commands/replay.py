"""CLI handler for `atlas replay`."""
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_replay(context: CLIContext) -> int | None:
    args = context.args
    config = context.config
    from atlas_agent.replay import replay_from_path
    from atlas_agent.replay import replay_last_run
    from atlas_agent.cli import _print_replay

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
    return None

