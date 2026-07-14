# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/status.py
# PURPOSE: CLI handler for `atlas status` — version, mode, workspace. Read-only.
# DEPS:    atlas_agent (__version__), cli_context
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent import __version__
from atlas_agent.cli_context import CLIContext


def handle_status(context: CLIContext) -> int:
    from atlas_agent.agent.status import get_agent_status

    print(get_agent_status(context.config))
    update = context.update_checker() if context.update_checker else None
    if update:
        print(f"\n[UPDATE] A newer version of Atlas Agent is available: {update} (current: {__version__})")
        print("Run 'git pull' to update.")
    return 0
