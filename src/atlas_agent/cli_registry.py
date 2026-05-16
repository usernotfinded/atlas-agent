from __future__ import annotations

from collections.abc import Callable

from atlas_agent.cli_context import CLIContext


CommandHandler = Callable[[CLIContext], int]


class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, command: str, handler: CommandHandler) -> None:
        self._handlers[command] = handler

    def dispatch(self, context: CLIContext) -> int | None:
        command = getattr(context.args, "command", None)
        if command not in self._handlers:
            return None
        return self._handlers[command](context)
