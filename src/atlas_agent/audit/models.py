from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Optional, List
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
    "tool_call_live_analysis_only",
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
    "broker_sync_started",
    "broker_sync_completed",
    "broker_sync_partial",
    "broker_sync_failed",
    "safety_action_plan_created",
    "safety_action_plan_blocked",
    "safety_action_requires_approval",
    "safety_action_no_op",
    "safety_plan_execution_requested",
    "safety_plan_execution_requires_approval",
    "safety_action_execution_started",
    "safety_action_execution_completed",
    "safety_action_execution_failed",
    "safety_plan_execution_completed",
    "safety_plan_execution_blocked",
    "backtest_started",
    "backtest_order_proposed",
    "backtest_order_blocked",
    "backtest_order_filled",
    "backtest_completed",
    "backtest_failed",
    "autonomous_paper_started",
    "autonomous_paper_decision",
    "autonomous_paper_fill",
    "autonomous_paper_manifest_sealed",
    "autonomous_paper_completed",
    "autonomous_paper_cycle_failed",
    "live_submit_opt_in_enabled",
    "live_submit_opt_in_disabled",
    "live_submit_opt_in_config_changed",
    "live_submit_blocked",
    "live_submit_attempted",
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
    errors: List[str] = Field(default_factory=list)
    rolling_root: Optional[str] = None


class AuditManifest(BaseModel):
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: Literal["running", "completed", "failed", "interrupted"] = "running"
    audit_log_path: str
    event_count: int = 0
    first_event_hash: Optional[str] = None
    final_event_hash: Optional[str] = None
    root_hash: Optional[str] = None
    final_status: Optional[str] = None
    schema_version: int = 2
    event_hash_rolling_root: Optional[str] = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ManifestVerificationResult(BaseModel):
    valid: bool
    manifest_status: str
    events_checked: int
    log_integrity: VerificationResult
    errors: List[str] = Field(default_factory=list)
