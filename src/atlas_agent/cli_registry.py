# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_registry.py
# PURPOSE: Name-to-handler lookup for CLI commands. Keeps dispatch a dict lookup
#          instead of a growing if/elif chain in cli.py.
# DEPS:    atlas_agent.cli_context (CLIContext)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from collections.abc import Callable

from atlas_agent.cli_context import CLIContext


# --- CONFIGURATIONS & CONSTANTS ---

CommandHandler = Callable[[CLIContext], int]


# ==============================================================================
# COMMAND REGISTRY
# ==============================================================================

class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, command: str, handler: CommandHandler) -> None:
        self._handlers[command] = handler

    def dispatch(self, context: CLIContext) -> int | None:
        command = getattr(context.args, "command", None)
        # `None` means "not mine" — an unknown command is not an error here. The
        # caller falls through to the legacy dispatch path, which is what makes it
        # possible to migrate commands into the registry one at a time. An exit code
        # would foreclose that.
        if command not in self._handlers:
            return None
        return self._handlers[command](context)
