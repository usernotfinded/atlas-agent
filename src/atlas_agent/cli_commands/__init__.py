from __future__ import annotations

from atlas_agent.cli_commands.audit import handle_audit
from atlas_agent.cli_commands.demo import handle_demo
from atlas_agent.cli_commands.deploy import handle_deploy
from atlas_agent.cli_commands.events import handle_events
from atlas_agent.cli_commands.memory import handle_memory
from atlas_agent.cli_commands.risk import handle_risk
from atlas_agent.cli_commands.status import handle_status
from atlas_agent.cli_commands.update import handle_update
from atlas_agent.cli_commands.workspace import handle_workspace
from atlas_agent.cli_registry import CommandRegistry


def build_core_command_registry() -> CommandRegistry:
    registry = CommandRegistry()
    registry.register("audit", handle_audit)
    registry.register("demo", handle_demo)
    registry.register("deploy", handle_deploy)
    registry.register("events", handle_events)
    registry.register("memory", handle_memory)
    registry.register("risk", handle_risk)
    registry.register("status", handle_status)
    registry.register("update", handle_update)
    registry.register("workspace", handle_workspace)
    return registry
