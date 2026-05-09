from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


KillSwitchMode = Literal[
    "normal",
    "soft_pause",
    "cancel_all",
    "flatten_all",
    "locked_down"
]


class KillSwitchStatus(BaseModel):
    mode: KillSwitchMode = "normal"
    reason: str = "System default"
    updated_at: str = ""
    actor: str = "system"


class KillSwitchDecision(BaseModel):
    allowed: bool
    status: Literal["allowed", "blocked", "cancel_required", "flatten_required", "locked_down"]
    reason: Optional[str] = None
    mode: KillSwitchMode
    action_required: Optional[str] = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
