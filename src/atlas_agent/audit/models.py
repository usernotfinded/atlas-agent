from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


AuditEventType = Literal[
    "run_started",
    "context_composed",
    "provider_called",
    "provider_response",
    "tool_call_requested",
    "tool_call_executed",
    "tool_call_blocked",
    "approval_required",
    "validation_error",
    "risk_evaluation_started",
    "risk_evaluation_allowed",
    "risk_evaluation_blocked",
    "risk_evaluation_requires_approval",
    "kill_switch_checked",
    "kill_switch_blocked",
    "kill_switch_mode_changed",
    "heartbeat_recorded",
    "heartbeat_expired",
    "run_completed",
    "run_failed",
]


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    event_type: AuditEventType
    run_id: str
    iteration: Optional[int] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    status: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    redacted: bool = True
    previous_hash: Optional[str] = None
    event_hash: Optional[str] = None


class VerificationResult(BaseModel):
    valid: bool
    events_checked: int
    first_error_index: Optional[int] = None
    errors: list[str] = Field(default_factory=list)
