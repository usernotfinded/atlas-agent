# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    audit/models.py
# PURPOSE: The vocabulary of the audit trail — every event the agent is allowed to
#          record, and the shape of the records and manifests themselves.
# DEPS:    pydantic (models)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Optional, List
from uuid import uuid4

from pydantic import BaseModel, Field


# --- CONFIGURATIONS & CONSTANTS ---

# A closed Literal, not a free-form string: an event type that is not listed here
# cannot be written at all. That is deliberate — it means the set of things the
# agent can do is enumerable and reviewable from one place, and no code path can
# quietly invent a new kind of event that nobody is auditing for.
#
# Grouped by subsystem: run lifecycle, provider, tools, risk, kill switch, broker
# sync, safety actions, backtest, autonomous paper, live submit.
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


# ==============================================================================
# EVENT RECORD
# ==============================================================================

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

    # Defaults to True because the writer redacts unconditionally before hashing.
    # An event with redacted=False should not exist; if one ever appears in a log,
    # it is a bug worth investigating, not a supported mode.
    redacted: bool = True

    # --- Chain fields (populated by the writer, never by callers) ---
    # Optional only because the event must be constructed before its own hash can be
    # computed over it. They are always set by the time a record reaches disk.
    previous_hash: Optional[str] = None
    event_hash: Optional[str] = None


# ==============================================================================
# VERIFICATION RESULTS
# ==============================================================================

class VerificationResult(BaseModel):
    valid: bool
    events_checked: int
    # Where the log stops being trustworthy. Everything before this index still is,
    # which is what lets a partially corrupted trail remain partially usable.
    first_error_index: Optional[int] = None
    errors: List[str] = Field(default_factory=list)
    rolling_root: Optional[str] = None


# ==============================================================================
# RUN MANIFEST
# ==============================================================================

class AuditManifest(BaseModel):
    run_id: str
    started_at: str
    completed_at: Optional[str] = None

    # Anything other than "completed" means the run did not seal itself cleanly.
    status: Literal["running", "completed", "failed", "interrupted"] = "running"

    audit_log_path: str

    # --- Sealed evidence (final once the run completes) ---
    # These are the values compute_root_hash() binds. The count and the two endpoint
    # hashes catch truncation; the rolling root catches interior tampering.
    event_count: int = 0
    first_event_hash: Optional[str] = None
    final_event_hash: Optional[str] = None
    root_hash: Optional[str] = None
    final_status: Optional[str] = None

    # Bumped when the sealed field set changes. Manifests written before
    # event_hash_rolling_root existed still carry version 2 and must keep verifying
    # against their original hash — see the None-guard in compute_root_hash().
    schema_version: int = 2
    event_hash_rolling_root: Optional[str] = None

    # Deliberately NOT bound by the root hash: diagnostics are free-form and may be
    # appended after sealing, so binding them would break the seal.
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ManifestVerificationResult(BaseModel):
    valid: bool
    manifest_status: str
    events_checked: int
    log_integrity: VerificationResult
    errors: List[str] = Field(default_factory=list)
