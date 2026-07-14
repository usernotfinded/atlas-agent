# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/result.py
# PURPOSE: What an agent run reports back. The status vocabulary below is the
#          important part: it distinguishes "finished" from "was stopped" from
#          "hit a ceiling", and those must never be collapsed into a single bool.
# DEPS:    tools.spec (tool call/result types)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from atlas_agent.tools.spec import ToolCall, ToolResult, ToolError


# --- CONFIGURATIONS & CONSTANTS ---

# Only "complete" means the agent finished on its own terms. Everything else is a
# different flavour of "it did not":
#   blocked          → a safety gate stopped it (kill switch, risk);
#   error            → something broke;
#   max_iterations   → it would not stop reasoning;
#   max_tool_calls   → it would not stop acting;
#   approval_required→ it is waiting on a human.
# A caller that treats any of these as success is exactly the bug this enum prevents.
AgentStatus = Literal[
    "complete",
    "blocked",
    "error",
    "max_iterations",
    "max_tool_calls",
    "approval_required"
]


@dataclass(frozen=True)
class IterationResult:
    index: int
    message: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult | ToolError] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class AgentResult:
    status: AgentStatus
    mode: str = "paper"
    final_message: str | None = None
    iterations: list[IterationResult] = field(default_factory=list)
    total_tool_calls: int = 0
    errors: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    lock_status: str | None = None
    report_path: str | None = None
    order_status: str | None = None
    notification_status: str | None = "none"
    git_status: str | None = "none"
