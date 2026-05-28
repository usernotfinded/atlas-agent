from __future__ import annotations

import sys

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_io import display_path
from atlas_agent.demo import seed_demo_workspace


def handle_demo(context: CLIContext) -> int:
    args = context.args
    config = context.config

    if args.demo_command == "seed":
        result = seed_demo_workspace(
            workspace_dir=config.memory_dir.parent,
            memory_dir=config.memory_dir,
            reports_dir=config.reports_dir,
            skills_dir=config.memory_dir.parent / "skills",
            events_dir=config.events_dir,
            force=args.force,
        )
        if result.warning:
            print(f"demo seed warning: {result.warning}", file=sys.stderr)
            if not result.written_paths:
                return 2
        if not result.written_paths:
            print("Demo seed complete: no new files were created.")
            return 0
        print("Demo seed wrote:")
        for path in result.written_paths:
            print(f"- {display_path(path)}")
        return 0

    return 0
