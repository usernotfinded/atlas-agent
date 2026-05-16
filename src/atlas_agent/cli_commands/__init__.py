from __future__ import annotations

from atlas_agent.cli_commands.audit import handle_audit
from atlas_agent.cli_commands.memory import handle_memory
from atlas_agent.cli_commands.status import handle_status
from atlas_agent.cli_registry import CommandRegistry


def build_core_command_registry() -> CommandRegistry:
    registry = CommandRegistry()
    registry.register("audit", handle_audit)
    registry.register("memory", handle_memory)
    registry.register("status", handle_status)
    return registry
