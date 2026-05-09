from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from atlas_agent.tools.spec import ToolCall, ToolResult, ToolError


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
