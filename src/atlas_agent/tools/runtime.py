# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tools/runtime.py
# PURPOSE: Builds the live ToolRegistry from the builtin specs.
# DEPS:    tools.builtin (the specs), tools.registry (the gate)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.tools.builtin import BUILTIN_TOOLS
from atlas_agent.tools.registry import ToolRegistry


def build_builtin_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in BUILTIN_TOOLS:
        registry.register(tool)
    return registry
