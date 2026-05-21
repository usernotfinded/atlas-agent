"""Provider response review result contract — local, configless review result artifact.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider response review result artifacts. It does NOT call any real provider,
does NOT perform network requests, does NOT read API keys, does NOT read os.environ,
does NOT load .env.atlas, does NOT import provider SDKs, does NOT receive real provider
responses, does NOT trust provider responses, does NOT open the manual review gate,
and does NOT touch brokers.

A provider response review result contract defines how a future manual review result
for a provider response must be recorded, bounded, redacted, validated, and kept
non-authorizing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.events.log import generate_run_id
from atlas_agent.research.sandbox_contracts import (
    FORBIDDEN_FRAGMENTS,
    MAX_CONTRACT_TEXT_CHARS,
    _has_forbidden_fragments,
    canonical_json_dumps,
    sanitize_contract_text,
    validate_contract_lineage_id,
    validate_contract_symbol,
)
from atlas_agent.research.session import (
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_DIR,
    ResearchSessionError,
    UnsupportedArtifactSchemaError,
    _is_inside_workspace,
    validate_run_id,
)

PROVIDER_RESPONSE_REVIEW_RESULT_VERSION = "research_provider_response_review_result_v1"

_PROVIDER_RESPONSE_REVIEW_RESULT_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_REVIEW_STATUSES = {
    "review_result_contract_recorded",
    "manual_review_required",
    "review_result_contract_invalid",
}

_VALID_REVIEW_SCOPES = {
    "future_provider_response_review_result_only",
}

_VALID_REVIEW_STATES = {
    "review_contract_recorded_no_response_present",
    "future_response_required",
    "manual_review_gate_closed",
    "blocked_until_response_artifact_exists",
    "blocked_until_schema_validation_exists",
}

_VALID_REVIEW_DECISIONS = {
    "no_decision_recorded",
    "future_manual_review_required",
    "blocked_no_response_present",
}

_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE = [
    "review_result_present",
    "manual_review_gate_open",
    "manual_review_completed",
    "reviewer_identity_recorded",
    "review_notes_stored",
    "review_decision_allows_use",
    "review_decision_allows_trust_upgrade",
    "review_decision_allows_trading_interpretation",
    "review_decision_allows_order_creation",
    "review_decision_allows_order_approval",
    "review_decision_allows_broker_call",
    "schema_contract_enabled",
    "future_response_artifact_present",
    "future_response_schema_validated",
    "provider_response_received",
    "provider_response_trusted",
    "provider_response_imported",
    "provider_response_reviewed",
    "provider_response_can_create_orders",
    "provider_response_can_approve_orders",
    "provider_response_can_call_broker",
    "response_schema_allows_trading_signal",
    "response_schema_allows_order_creation",
    "response_schema_allows_order_approval",
    "response_schema_allows_broker_call",
    "raw_response_body_stored",
    "raw_prompt_body_stored",
    "provider_enabled",
    "network_enabled",
    "credentials_loaded",
    "credential_value_present",
    "credential_lookup_attempted",
    "env_read_attempted",
    "dotenv_loaded",
    "provider_call_allowed",
    "actual_provider_call_made",
    "outbound_request_sent",
    "future_provider_execution_possible",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
]

_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE = [
    "review_notes_bounded",
    "review_notes_redacted",
]


@dataclass(frozen=True)
class ProviderResponseReviewResultValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_review_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        value = str(value)
    return sanitize_contract_text(value, max_chars)


def validate_provider_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_response_review_result_provider")
    if value not in _get_disabled_provider_ids():
        raise ResearchSessionError("invalid_provider_response_review_result_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_response_review_result_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_response_review_result_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_review_result_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_response_review_result_model")
    return value


def validate_review_result_status(value: str) -> str:
    if not value or value not in _VALID_REVIEW_STATUSES:
        raise ResearchSessionError("invalid_provider_response_review_result_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_review_result_status")
    return value


def validate_review_result_scope(value: str) -> str:
    if not value or value not in _VALID_REVIEW_SCOPES:
        raise ResearchSessionError("invalid_provider_response_review_result_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_review_result_status")
    return value


def validate_review_result_state(value: str) -> str:
    if not value or value not in _VALID_REVIEW_STATES:
        raise ResearchSessionError("invalid_provider_response_review_result_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_review_result_status")
    return value


def validate_review_decision(value: str) -> str:
    if not value or value not in _VALID_REVIEW_DECISIONS:
        raise ResearchSessionError("invalid_provider_response_review_result_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_review_result_status")
    return value


def provider_response_review_result_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_RESPONSE_REVIEW_RESULT_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
        if data.get(flag) is not False:
            return "provider_response_review_result_impossible_boolean"
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
        if data.get(flag) is not True:
            return "provider_response_review_result_impossible_boolean"
    return None


def _build_reviewer_identity_policy() -> dict[str, Any]:
    return {
        "reviewer_identity_required_in_future": True,
        "reviewer_identity_recorded": False,
        "reviewer_identity_raw_stored": False,
        "reviewer_identity_hash_required_in_future": True,
        "reviewer_identity_can_authorize_trading": False,
        "reviewer_identity_can_open_broker_bridge": False,
    }


def _build_review_notes_policy() -> dict[str, Any]:
    return {
        "review_notes_allowed_in_future": True,
        "review_notes_stored": False,
        "review_notes_must_be_bounded": True,
        "review_notes_must_be_redacted": True,
        "raw_review_notes_allowed": False,
        "review_notes_can_create_order": False,
        "review_notes_can_approve_order": False,
        "review_notes_can_call_broker": False,
    }


def _build_review_bounds_policy() -> dict[str, Any]:
    return {
        "max_review_note_chars": 1000,
        "structured_review_result_required": True,
        "freeform_review_only_allowed": False,
        "review_result_schema_required": True,
        "unsafe_content_detection_required": True,
        "manual_review_does_not_authorize_trading": True,
    }


def _build_review_redaction_policy() -> dict[str, Any]:
    return {
        "redaction_required_before_output": True,
        "redaction_required_before_artifact_write": True,
        "redaction_required_before_event_write": True,
        "raw_secret_echo_allowed": False,
        "raw_response_echo_allowed": False,
        "raw_prompt_echo_allowed": False,
        "redaction_profile": "atlas_provider_response_review_result_v1",
        "raw_denylist_fragments_stored": False,
    }


def _build_review_validation_policy() -> dict[str, Any]:
    return {
        "review_result_schema_validation_required": True,
        "review_result_hash_required": True,
        "source_schema_contract_hash_required": True,
        "source_pairing_hash_required": True,
        "unsafe_review_content_behavior": "fail_closed",
        "missing_future_response_behavior": "manual_review_required",
        "malformed_review_behavior": "fail_closed",
        "raw_exception_leakage_behavior": "release_blocker",
    }


def _build_trust_upgrade_policy() -> dict[str, Any]:
    return {
        "trust_upgrade_allowed": False,
        "trust_upgrade_not_implemented": True,
        "manual_review_does_not_make_response_trusted": True,
        "future_trust_upgrade_requires_separate_policy": True,
        "review_result_can_mark_response_trusted": False,
    }


def _build_trading_separation_policy() -> dict[str, Any]:
    return {
        "review_result_is_not_trading_signal": True,
        "review_result_cannot_create_pending_order": True,
        "review_result_cannot_approve_order": True,
        "review_result_cannot_submit_order": True,
        "review_result_cannot_modify_risk": True,
        "review_result_cannot_call_broker": True,
    }


def _build_broker_separation_policy() -> dict[str, Any]:
    return {
        "broker_live_bridge_allowed": False,
        "broker_adapter_access_allowed": False,
        "order_routing_allowed": False,
        "approval_manager_access_allowed": False,
        "risk_manager_access_allowed": False,
    }


def _build_review_event_policy() -> dict[str, Any]:
    return {
        "review_event_required_in_future": True,
        "review_event_written_in_this_batch": False,
        "review_event_can_authorize_trading": False,
        "review_event_can_call_broker": False,
        "review_event_must_be_static_safe": True,
    }


def _build_future_response_requirements() -> dict[str, Any]:
    return {
        "future_response_artifact_required": True,
        "future_response_schema_validation_required": True,
        "future_response_hash_required": True,
        "future_response_redaction_required": True,
        "future_response_manual_review_required": True,
        "future_review_result_required": True,
        "future_review_result_cannot_authorize_trading": True,
        "future_review_result_cannot_touch_broker": True,
    }


def _build_denylist_metadata() -> dict[str, Any]:
    return {
        "denylist_profile": "atlas_provider_response_review_result_v1",
        "forbidden_fragment_count": len(FORBIDDEN_FRAGMENTS),
        "forbidden_fragments_raw_stored": False,
    }


def build_provider_response_review_result_dict(
    source_schema_contract: dict[str, Any],
    source_pairing: dict[str, Any],
    source_intake_policy: dict[str, Any],
    source_preview: dict[str, Any],
    review_result_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(review_result_id, "provider_response_review_result_id")

    src_schema_contract_id = source_schema_contract.get("provider_response_schema_contract_id", "")
    validate_contract_lineage_id(src_schema_contract_id, "source_provider_response_schema_contract_id")

    src_pairing_id = source_pairing.get("provider_request_response_pairing_id", "")
    validate_contract_lineage_id(src_pairing_id, "source_provider_request_response_pairing_id")

    src_intake_id = source_intake_policy.get("provider_response_intake_policy_id", "")
    validate_contract_lineage_id(src_intake_id, "source_provider_response_intake_policy_id")

    src_preview_id = source_preview.get("provider_outbound_payload_preview_id", "")
    validate_contract_lineage_id(src_preview_id, "source_provider_outbound_payload_preview_id")

    # Propagate upstream lineage from payload preview through schema contract
    lineage_fields = [
        ("source_provider_credential_boundary_id", source_preview.get("source_provider_credential_boundary_id", "")),
        ("source_provider_opt_in_policy_id", source_preview.get("source_provider_opt_in_policy_id", "")),
        ("source_provider_preflight_freeze_id", source_preview.get("source_provider_preflight_freeze_id", "")),
        ("source_provider_execution_readiness_report_id", source_preview.get("source_provider_execution_readiness_report_id", "")),
        ("source_provider_execution_audit_packet_id", source_preview.get("source_provider_execution_audit_packet_id", "")),
        ("source_provider_execution_state_id", source_preview.get("source_provider_execution_state_id", "")),
        ("source_provider_execution_dry_run_id", source_preview.get("source_provider_execution_dry_run_id", "")),
        ("source_provider_call_plan_id", source_preview.get("source_provider_call_plan_id", "")),
        ("source_sandbox_request_id", source_preview.get("source_sandbox_request_id", "")),
        ("source_prompt_packet_id", source_preview.get("source_prompt_packet_id", "")),
        ("source_run_id", source_preview.get("source_run_id", "")),
    ]
    for field_name, value in lineage_fields:
        validate_contract_lineage_id(value, field_name)

    symbol = validate_contract_symbol(source_preview.get("symbol", ""))
    safe_provider_id = validate_provider_id(source_preview.get("provider_id", ""))
    safe_model_id = validate_model_id(source_preview.get("model_id", ""))

    created_at = datetime.now(UTC)
    artifact_path_rel = f".atlas/research/{symbol}/provider_response_review_results/{review_result_id}.json"

    reviewer_identity_policy = _build_reviewer_identity_policy()
    review_notes_policy = _build_review_notes_policy()
    review_bounds_policy = _build_review_bounds_policy()
    review_redaction_policy = _build_review_redaction_policy()
    review_validation_policy = _build_review_validation_policy()
    trust_upgrade_policy = _build_trust_upgrade_policy()
    trading_separation_policy = _build_trading_separation_policy()
    broker_separation_policy = _build_broker_separation_policy()
    review_event_policy = _build_review_event_policy()
    future_response_requirements = _build_future_response_requirements()
    denylist_metadata = _build_denylist_metadata()

    blocking_reasons = [
        "provider_execution_not_implemented",
        "provider_response_reception_not_implemented",
        "provider_response_trust_boundary_not_established",
        "trading_separation_required",
        "manual_review_required_before_any_interpretation",
        "future_response_artifact_required",
        "schema_contract_not_enabled",
        "review_result_not_present",
        "manual_review_gate_closed",
        "trust_upgrade_not_implemented",
    ]

    warnings = [
        "This is a local provider response review result contract. No provider request was sent.",
        "No provider response was received.",
        "No provider response is trusted by default.",
        "Provider response cannot create orders, approvals, or pending orders.",
        "Real provider response handling requires explicit future opt-in.",
        "Manual review gate is closed. No automatic review is allowed.",
        "Review result does not make response trusted.",
        "Review result cannot authorize trading.",
    ]

    metadata = {
        "source_schema_contract_schema_version": source_schema_contract.get("schema_version", ""),
        "source_schema_contract_contract_version": source_schema_contract.get("contract_version", ""),
        "source_pairing_schema_version": source_pairing.get("schema_version", ""),
        "source_pairing_contract_version": source_pairing.get("contract_version", ""),
        "source_intake_policy_schema_version": source_intake_policy.get("schema_version", ""),
        "source_intake_policy_contract_version": source_intake_policy.get("contract_version", ""),
        "source_preview_schema_version": source_preview.get("schema_version", ""),
        "source_preview_contract_version": source_preview.get("contract_version", ""),
    }

    source_schema_contract_hash = source_schema_contract.get("artifact_hash", "")
    source_pairing_hash = source_pairing.get("artifact_hash", "")
    source_response_intake_policy_hash = source_intake_policy.get("artifact_hash", "")
    source_payload_preview_hash = source_preview.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_response_review_result",
        "contract_version": PROVIDER_RESPONSE_REVIEW_RESULT_VERSION,
        "provider_response_review_result_id": review_result_id,
        "source_provider_response_schema_contract_id": src_schema_contract_id,
        "source_provider_request_response_pairing_id": src_pairing_id,
        "source_provider_response_intake_policy_id": src_intake_id,
        "source_provider_outbound_payload_preview_id": src_preview_id,
        "source_provider_credential_boundary_id": lineage_fields[0][1],
        "source_provider_opt_in_policy_id": lineage_fields[1][1],
        "source_provider_preflight_freeze_id": lineage_fields[2][1],
        "source_provider_execution_readiness_report_id": lineage_fields[3][1],
        "source_provider_execution_audit_packet_id": lineage_fields[4][1],
        "source_provider_execution_state_id": lineage_fields[5][1],
        "source_provider_execution_dry_run_id": lineage_fields[6][1],
        "source_provider_call_plan_id": lineage_fields[7][1],
        "source_sandbox_request_id": lineage_fields[8][1],
        "source_prompt_packet_id": lineage_fields[9][1],
        "source_run_id": lineage_fields[10][1],
        "symbol": symbol,
        "mode": "paper",
        "provider_id": safe_provider_id,
        "model_id": safe_model_id,
        "review_result_status": "review_result_contract_recorded",
        "review_result_scope": "future_provider_response_review_result_only",
        "review_result_state": "review_contract_recorded_no_response_present",
        "review_decision": "no_decision_recorded",
        "reviewer_identity_policy": reviewer_identity_policy,
        "review_notes_policy": review_notes_policy,
        "review_bounds_policy": review_bounds_policy,
        "review_redaction_policy": review_redaction_policy,
        "review_validation_policy": review_validation_policy,
        "trust_upgrade_policy": trust_upgrade_policy,
        "trading_separation_policy": trading_separation_policy,
        "broker_separation_policy": broker_separation_policy,
        "review_event_policy": review_event_policy,
        "future_response_requirements": future_response_requirements,
        "blocking_reasons": blocking_reasons,
        "source_schema_contract_hash": source_schema_contract_hash,
        "source_pairing_hash": source_pairing_hash,
        "source_response_intake_policy_hash": source_response_intake_policy_hash,
        "source_payload_preview_hash": source_payload_preview_hash,
        "review_result_present": False,
        "manual_review_gate_open": False,
        "manual_review_completed": False,
        "reviewer_identity_recorded": False,
        "review_notes_stored": False,
        "review_notes_bounded": True,
        "review_notes_redacted": True,
        "review_decision_allows_use": False,
        "review_decision_allows_trust_upgrade": False,
        "review_decision_allows_trading_interpretation": False,
        "review_decision_allows_order_creation": False,
        "review_decision_allows_order_approval": False,
        "review_decision_allows_broker_call": False,
        "schema_contract_enabled": False,
        "future_response_artifact_present": False,
        "future_response_schema_validated": False,
        "provider_response_received": False,
        "provider_response_trusted": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "provider_response_can_create_orders": False,
        "provider_response_can_approve_orders": False,
        "provider_response_can_call_broker": False,
        "response_schema_allows_trading_signal": False,
        "response_schema_allows_order_creation": False,
        "response_schema_allows_order_approval": False,
        "response_schema_allows_broker_call": False,
        "raw_response_body_stored": False,
        "raw_prompt_body_stored": False,
        "provider_enabled": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "credential_value_present": False,
        "credential_lookup_attempted": False,
        "env_read_attempted": False,
        "dotenv_loaded": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "outbound_request_sent": False,
        "future_provider_execution_possible": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": metadata,
        "denylist_metadata": denylist_metadata,
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_response_review_result_sha256(artifact)
    return artifact


def create_provider_response_review_result(
    workspace_path: Path,
    schema_contract_id: str,
) -> dict[str, Any]:
    safe_schema_contract_id = validate_run_id(schema_contract_id)

    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )

    schema_contract_path = find_provider_response_schema_contract_by_id(workspace_path, safe_schema_contract_id)
    if schema_contract_path is None:
        raise ResearchSessionError("provider_response_review_result_source_schema_contract_missing")

    source_schema_contract = load_provider_response_schema_contract(schema_contract_path, workspace_path)

    source_pairing_id = source_schema_contract.get("source_provider_request_response_pairing_id", "")
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )

    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
    if pairing_path is None:
        raise ResearchSessionError("provider_response_review_result_source_pairing_missing")

    source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)

    source_intake_id = source_schema_contract.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
    if intake_path is None:
        raise ResearchSessionError("provider_response_review_result_source_response_intake_missing")

    source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)

    source_preview_id = source_schema_contract.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if preview_path is None:
        raise ResearchSessionError("provider_response_review_result_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    review_result_id = generate_run_id()
    artifact = build_provider_response_review_result_dict(
        source_schema_contract,
        source_pairing,
        source_intake_policy,
        source_preview,
        review_result_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    result_dir = workspace_path / RESEARCH_DIR / symbol / "provider_response_review_results"
    result_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_response_review_result_created",
        "provider_response_review_result_id": review_result_id,
        "source_provider_response_schema_contract_id": safe_schema_contract_id,
        "source_provider_request_response_pairing_id": source_pairing_id,
        "source_provider_response_intake_policy_id": source_intake_id,
        "source_provider_outbound_payload_preview_id": source_preview_id,
        "review_result_status": artifact["review_result_status"],
        "review_result_state": artifact["review_result_state"],
        "review_decision": artifact["review_decision"],
        "review_result_present": False,
        "manual_review_gate_open": False,
        "manual_review_completed": False,
        "reviewer_identity_recorded": False,
        "review_notes_stored": False,
        "review_notes_bounded": True,
        "review_notes_redacted": True,
        "review_decision_allows_use": False,
        "review_decision_allows_trust_upgrade": False,
        "review_decision_allows_trading_interpretation": False,
        "review_decision_allows_order_creation": False,
        "review_decision_allows_order_approval": False,
        "review_decision_allows_broker_call": False,
        "provider_response_received": False,
        "provider_response_trusted": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "provider_response_can_create_orders": False,
        "provider_response_can_approve_orders": False,
        "provider_response_can_call_broker": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "outbound_request_sent": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_response_review_result_{field_name}"
    return None


def safe_validate_provider_response_review_result_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_response_review_result_schema"

    if data.get("artifact_type") != "provider_response_review_result":
        return None, "provider_response_review_result_malformed"

    if data.get("contract_version") != PROVIDER_RESPONSE_REVIEW_RESULT_VERSION:
        return None, "provider_response_review_result_malformed"

    try:
        validate_review_result_status(data.get("review_result_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_review_result_status"

    try:
        validate_review_result_scope(data.get("review_result_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_review_result_status"

    try:
        validate_review_result_state(data.get("review_result_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_review_result_status"

    try:
        validate_review_decision(data.get("review_decision", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_review_result_status"

    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    if data.get("mode") != "paper":
        return None, "provider_response_review_result_malformed"

    lineage_field_names = [
        "provider_response_review_result_id",
        "source_provider_response_schema_contract_id",
        "source_provider_request_response_pairing_id",
        "source_provider_response_intake_policy_id",
        "source_provider_outbound_payload_preview_id",
        "source_provider_credential_boundary_id",
        "source_provider_opt_in_policy_id",
        "source_provider_preflight_freeze_id",
        "source_provider_execution_readiness_report_id",
        "source_provider_execution_audit_packet_id",
        "source_provider_execution_state_id",
        "source_provider_execution_dry_run_id",
        "source_provider_call_plan_id",
        "source_sandbox_request_id",
        "source_prompt_packet_id",
        "source_run_id",
    ]
    for field in lineage_field_names:
        value = data.get(field, "")
        try:
            validate_contract_lineage_id(value, field)
        except ResearchSessionError:
            return None, "invalid_provider_response_review_result_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_review_result_lineage"

    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_response_review_result_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_response_review_result_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_response_review_result_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_response_review_result_hash_mismatch"

    if workspace_path is not None and not for_replay:
        source_schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
        if source_schema_contract_id:
            try:
                from atlas_agent.research.provider_response_schema_contract import (
                    find_provider_response_schema_contract_by_id,
                    load_provider_response_schema_contract,
                )

                sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
                if sc_path is None:
                    return None, "provider_response_review_result_source_schema_contract_missing"
                sc_data = load_provider_response_schema_contract(sc_path, workspace_path)
                stored_sc_hash = data.get("source_schema_contract_hash", "")
                actual_sc_hash = sc_data.get("artifact_hash", "")
                if stored_sc_hash != actual_sc_hash:
                    return None, "provider_response_review_result_source_schema_contract_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_response_review_result_source_schema_contract_missing"

        source_pairing_id = data.get("source_provider_request_response_pairing_id", "")
        if source_pairing_id:
            try:
                from atlas_agent.research.provider_request_response_pairing import (
                    find_provider_request_response_pairing_by_id,
                    load_provider_request_response_pairing,
                )

                pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
                if pairing_path is None:
                    return None, "provider_response_review_result_source_pairing_missing"
                pairing_data = load_provider_request_response_pairing(pairing_path, workspace_path)
                stored_pairing_hash = data.get("source_pairing_hash", "")
                actual_pairing_hash = pairing_data.get("artifact_hash", "")
                if stored_pairing_hash != actual_pairing_hash:
                    return None, "provider_response_review_result_source_pairing_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_response_review_result_source_pairing_missing"

        source_intake_id = data.get("source_provider_response_intake_policy_id", "")
        if source_intake_id:
            try:
                from atlas_agent.research.provider_response_intake_policy import (
                    find_provider_response_intake_policy_by_id,
                    load_provider_response_intake_policy,
                )

                intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
                if intake_path is None:
                    return None, "provider_response_review_result_source_response_intake_missing"
                intake_data = load_provider_response_intake_policy(intake_path, workspace_path)
                stored_intake_hash = data.get("source_response_intake_policy_hash", "")
                actual_intake_hash = intake_data.get("artifact_hash", "")
                if stored_intake_hash != actual_intake_hash:
                    return None, "provider_response_review_result_source_response_intake_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_response_review_result_source_response_intake_missing"

        source_preview_id = data.get("source_provider_outbound_payload_preview_id", "")
        if source_preview_id:
            try:
                from atlas_agent.research.provider_outbound_payload_preview import (
                    find_provider_outbound_payload_preview_by_id,
                    load_provider_outbound_payload_preview,
                )

                preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
                if preview_path is None:
                    return None, "provider_response_review_result_source_payload_preview_missing"
                preview_data = load_provider_outbound_payload_preview(preview_path, workspace_path)
                stored_preview_hash = data.get("source_payload_preview_hash", "")
                actual_preview_hash = preview_data.get("artifact_hash", "")
                if stored_preview_hash != actual_preview_hash:
                    return None, "provider_response_review_result_source_payload_preview_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_response_review_result_source_payload_preview_missing"

    # Check policy fields for forbidden fragments
    policy_fields = [
        json.dumps(data.get("reviewer_identity_policy", {})),
        json.dumps(data.get("review_notes_policy", {})),
        json.dumps(data.get("review_bounds_policy", {})),
        json.dumps(data.get("review_redaction_policy", {})),
        json.dumps(data.get("review_validation_policy", {})),
        json.dumps(data.get("trust_upgrade_policy", {})),
        json.dumps(data.get("trading_separation_policy", {})),
        json.dumps(data.get("broker_separation_policy", {})),
        json.dumps(data.get("review_event_policy", {})),
        json.dumps(data.get("future_response_requirements", {})),
        json.dumps(data.get("blocking_reasons", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in policy_fields):
        return None, "provider_response_review_result_malformed"

    # Check status/scope/state/decision for forbidden fragments
    policy_summaries = [
        data.get("review_result_status", ""),
        data.get("review_result_scope", ""),
        data.get("review_result_state", ""),
        data.get("review_decision", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_response_review_result_forbidden_review_claim"

    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_response_review_result_malformed"

    cleaned = {k: v for k, v in data.items()}
    return cleaned, None


def validate_provider_response_review_result_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderResponseReviewResultValidationResult:
    data = load_provider_response_review_result(path, workspace_path)
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    sv = data.get("schema_version")
    checks.append(
        _check_name(
            "schema_version_supported",
            sv == RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "Schema version must match supported version." if sv != RESEARCH_ARTIFACT_SCHEMA_VERSION else "Schema version is supported.",
        )
    )

    at = data.get("artifact_type")
    checks.append(
        _check_name(
            "artifact_type_correct",
            at == "provider_response_review_result",
            "artifact_type must be provider_response_review_result." if at != "provider_response_review_result" else "artifact_type is correct.",
        )
    )

    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_RESPONSE_REVIEW_RESULT_VERSION,
            "contract_version must match current contract." if cv != PROVIDER_RESPONSE_REVIEW_RESULT_VERSION else "contract_version matches.",
        )
    )

    status = data.get("review_result_status", "")
    status_ok = status in _VALID_REVIEW_STATUSES
    checks.append(
        _check_name(
            "review_result_status_valid",
            status_ok,
            "review_result_status is invalid." if not status_ok else "review_result_status is valid.",
        )
    )

    flags_ok = _check_boolean_safety_flags(data) is None
    checks.append(
        _check_name(
            "boolean_safety_flags_correct",
            flags_ok,
            "A boolean safety flag is incorrect." if not flags_ok else "All boolean safety flags are correct.",
        )
    )

    computed = provider_response_review_result_sha256(data)
    stored = data.get("artifact_hash", "")
    hash_ok = computed == stored
    checks.append(
        _check_name(
            "artifact_hash_match",
            hash_ok,
            "artifact_hash does not match canonical JSON." if not hash_ok else "artifact_hash matches.",
        )
    )

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    valid = failed == 0

    return ProviderResponseReviewResultValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation="Proceed with review result contract." if valid else "Reject artifact and investigate tampering.",
        warnings=warnings,
    )


def load_provider_response_review_result(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        raise ResearchSessionError("provider_response_review_result_malformed") from e

    cleaned, err = safe_validate_provider_response_review_result_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    if not cleaned:
        raise ResearchSessionError("provider_response_review_result_malformed")
    return cleaned


def load_and_validate_provider_response_review_result(path: Path, workspace_path: Path) -> dict[str, Any]:
    data = load_provider_response_review_result(path, workspace_path)
    res = validate_provider_response_review_result_artifact(path, workspace_path)
    if not res.valid:
        raise ResearchSessionError("invalid_provider_response_review_result_artifact")
    return data


def find_provider_response_review_result_by_id(workspace_path: Path, review_result_id: str) -> Path | None:
    safe_id = validate_run_id(review_result_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    for p in search_dir.rglob("provider_response_review_results/*.json"):
        if p.stem == safe_id:
            return p
    return None


def replay_provider_response_review_result(
    workspace_path: Path,
    review_result_id: str,
) -> dict[str, Any]:
    safe_id = validate_run_id(review_result_id)
    artifact_path = find_provider_response_review_result_by_id(workspace_path, safe_id)
    if not artifact_path:
        raise ResearchSessionError("provider_response_review_result_not_found")

    old_artifact = load_provider_response_review_result(artifact_path, workspace_path=None)

    source_schema_contract_id = old_artifact.get("source_provider_response_schema_contract_id", "")
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )

    sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
    if not sc_path:
        raise ResearchSessionError("provider_response_review_result_source_schema_contract_missing")

    source_schema_contract = load_provider_response_schema_contract(sc_path, workspace_path)

    source_pairing_id = old_artifact.get("source_provider_request_response_pairing_id", "")
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )

    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
    if not pairing_path:
        raise ResearchSessionError("provider_response_review_result_source_pairing_missing")

    source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)

    source_intake_id = old_artifact.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
    if not intake_path:
        raise ResearchSessionError("provider_response_review_result_source_response_intake_missing")

    source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)

    source_preview_id = old_artifact.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if not preview_path:
        raise ResearchSessionError("provider_response_review_result_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    new_artifact = build_provider_response_review_result_dict(
        source_schema_contract,
        source_pairing,
        source_intake_policy,
        source_preview,
        safe_id,
        workspace_path,
    )

    new_artifact["created_at"] = old_artifact.get("created_at", new_artifact["created_at"])
    new_artifact["artifact_hash"] = provider_response_review_result_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_response_review_result_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_response_review_result_replayed",
        "provider_response_trusted": False,
        "provider_response_received": False,
        "review_result_present": False,
        "manual_review_gate_open": False,
    }


def iter_provider_response_review_result_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider response review result artifact metadata dicts, newest first.

    Each item is validated before inclusion. Invalid artifacts are returned as
    safe sentinels without raw tampered values.
    """
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    items: list[dict[str, Any]] = []
    invalid_items: list[dict[str, Any]] = []

    symbol_dirs = [research_dir / symbol] if symbol else research_dir.iterdir()

    for sym_dir in symbol_dirs:
        if not sym_dir.is_dir():
            continue
        result_dir = sym_dir / "provider_response_review_results"
        if not result_dir.exists():
            continue
        for path in result_dir.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                invalid_items.append({
                    "provider_response_review_result_id": "<invalid>",
                    "source_provider_response_schema_contract_id": "<invalid>",
                    "source_provider_request_response_pairing_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "review_result_status": "invalid",
                    "review_result_state": "invalid",
                    "review_decision": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_response_review_result_artifact",
                    "created_at": "",
                })
                continue
            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_response_review_result_id": "<invalid>",
                    "source_provider_response_schema_contract_id": "<invalid>",
                    "source_provider_request_response_pairing_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "review_result_status": "invalid",
                    "review_result_state": "invalid",
                    "review_decision": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_response_review_result_artifact",
                    "created_at": "",
                })
                continue
            cleaned, error = safe_validate_provider_response_review_result_data(raw, workspace_path=workspace_path)
            if error or cleaned is None:
                invalid_items.append({
                    "provider_response_review_result_id": "<invalid>",
                    "source_provider_response_schema_contract_id": "<invalid>",
                    "source_provider_request_response_pairing_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "review_result_status": "invalid",
                    "review_result_state": "invalid",
                    "review_decision": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_response_review_result_artifact",
                    "created_at": "",
                })
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append({
                "provider_response_review_result_id": cleaned.get("provider_response_review_result_id", path.stem),
                "source_provider_response_schema_contract_id": cleaned.get("source_provider_response_schema_contract_id", ""),
                "source_provider_request_response_pairing_id": cleaned.get("source_provider_request_response_pairing_id", ""),
                "source_provider_response_intake_policy_id": cleaned.get("source_provider_response_intake_policy_id", ""),
                "source_provider_outbound_payload_preview_id": cleaned.get("source_provider_outbound_payload_preview_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "review_result_status": cleaned.get("review_result_status", ""),
                "review_result_scope": cleaned.get("review_result_scope", ""),
                "review_result_state": cleaned.get("review_result_state", ""),
                "review_decision": cleaned.get("review_decision", ""),
                "artifact_path": rel_path,
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "created_at": cleaned.get("created_at", ""),
                "review_result_present": cleaned.get("review_result_present", False),
                "manual_review_gate_open": cleaned.get("manual_review_gate_open", False),
                "manual_review_completed": cleaned.get("manual_review_completed", False),
                "reviewer_identity_recorded": cleaned.get("reviewer_identity_recorded", False),
                "review_notes_stored": cleaned.get("review_notes_stored", False),
                "review_notes_bounded": cleaned.get("review_notes_bounded", True),
                "review_notes_redacted": cleaned.get("review_notes_redacted", True),
                "review_decision_allows_use": cleaned.get("review_decision_allows_use", False),
                "review_decision_allows_trust_upgrade": cleaned.get("review_decision_allows_trust_upgrade", False),
                "review_decision_allows_order_creation": cleaned.get("review_decision_allows_order_creation", False),
                "review_decision_allows_order_approval": cleaned.get("review_decision_allows_order_approval", False),
                "review_decision_allows_broker_call": cleaned.get("review_decision_allows_broker_call", False),
                "provider_response_received": cleaned.get("provider_response_received", False),
                "provider_response_trusted": cleaned.get("provider_response_trusted", False),
                "provider_response_imported": cleaned.get("provider_response_imported", False),
                "provider_response_reviewed": cleaned.get("provider_response_reviewed", False),
                "provider_response_can_create_orders": cleaned.get("provider_response_can_create_orders", False),
                "provider_response_can_approve_orders": cleaned.get("provider_response_can_approve_orders", False),
                "provider_response_can_call_broker": cleaned.get("provider_response_can_call_broker", False),
                "raw_response_body_stored": cleaned.get("raw_response_body_stored", False),
                "raw_prompt_body_stored": cleaned.get("raw_prompt_body_stored", False),
                "provider_enabled": cleaned.get("provider_enabled", False),
                "network_enabled": cleaned.get("network_enabled", False),
                "credentials_loaded": cleaned.get("credentials_loaded", False),
                "credential_value_present": cleaned.get("credential_value_present", False),
                "provider_call_allowed": cleaned.get("provider_call_allowed", False),
                "actual_provider_call_made": cleaned.get("actual_provider_call_made", False),
                "outbound_request_sent": cleaned.get("outbound_request_sent", False),
                "trading_signal_generated": cleaned.get("trading_signal_generated", False),
                "approval_created": cleaned.get("approval_created", False),
                "pending_order_created": cleaned.get("pending_order_created", False),
                "broker_touched": cleaned.get("broker_touched", False),
            })

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items + invalid_items


def _find_latest_provider_response_review_result_for_run(workspace_path: Path, run_id: str) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    latest_path: Path | None = None
    latest_time = ""
    for p in search_dir.rglob("provider_response_review_results/*.json"):
        try:
            data = load_provider_response_review_result(p, workspace_path=None)
            if data.get("source_run_id") == safe_run_id:
                t = data.get("created_at", "")
                if not latest_time or t > latest_time:
                    latest_time = t
                    latest_path = p
        except Exception:
            pass
    return latest_path


def summarize_provider_response_review_result_state(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_response_review_result_for_run(workspace_path, safe_run_id)

    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_response_review_result",
            "provider_response_review_result_id": None,
            "review_result_status": "not_recorded",
            "review_result_state": "not_recorded",
            "review_decision": "not_recorded",
            "review_result_present": False,
            "manual_review_gate_open": False,
            "provider_response_trusted": False,
            "artifact_path": None,
        }

    try:
        data = load_and_validate_provider_response_review_result(artifact_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": True,
            "status": "invalid_provider_response_review_result",
            "provider_response_review_result_id": None,
            "review_result_status": "invalid",
            "review_result_state": "invalid",
            "review_decision": "invalid",
            "review_result_present": False,
            "manual_review_gate_open": False,
            "provider_response_trusted": False,
            "artifact_path": None,
        }

    return {
        "ok": True,
        "status": "research_provider_response_review_result_summary",
        "provider_response_review_result_id": data.get("provider_response_review_result_id"),
        "review_result_status": data.get("review_result_status"),
        "review_result_state": data.get("review_result_state"),
        "review_decision": data.get("review_decision"),
        "review_result_present": False,
        "manual_review_gate_open": False,
        "provider_response_trusted": False,
        "artifact_path": data.get("artifact_path"),
    }


def doctor_provider_response_review_result(
    workspace_path: Path,
    run_id: str,
) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)

    missing_artifacts: list[str] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    result_path = _find_latest_provider_response_review_result_for_run(workspace_path, safe_run_id)
    if not result_path:
        missing_artifacts.append("provider_response_review_result")
        blocking_reasons.append("provider_response_review_result_not_created")
        warnings.append("No provider response review result exists for this run.")
        return {
            "ok": True,
            "status": "research_provider_response_review_result_doctor",
            "run_id": safe_run_id,
            "review_health": "review_result_missing",
            "review_result_present": False,
            "manual_review_gate_open": False,
            "provider_response_trusted": False,
            "missing_artifacts": missing_artifacts,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
        }

    try:
        data = load_provider_response_review_result(result_path, workspace_path)
    except ResearchSessionError as e:
        warnings.append(f"Review result artifact is invalid: {e}")
        return {
            "ok": True,
            "status": "research_provider_response_review_result_doctor",
            "run_id": safe_run_id,
            "review_health": "review_result_invalid",
            "review_result_present": False,
            "manual_review_gate_open": False,
            "provider_response_trusted": False,
            "missing_artifacts": missing_artifacts,
            "blocking_reasons": ["review_result_artifact_invalid"],
            "warnings": warnings,
        }

    # Check source artifacts
    schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
    pairing_id = data.get("source_provider_request_response_pairing_id", "")
    intake_id = data.get("source_provider_response_intake_policy_id", "")
    preview_id = data.get("source_provider_outbound_payload_preview_id", "")

    from atlas_agent.research.provider_response_schema_contract import find_provider_response_schema_contract_by_id
    from atlas_agent.research.provider_request_response_pairing import find_provider_request_response_pairing_by_id
    from atlas_agent.research.provider_response_intake_policy import find_provider_response_intake_policy_by_id
    from atlas_agent.research.provider_outbound_payload_preview import find_provider_outbound_payload_preview_by_id

    if schema_contract_id:
        sc_path = find_provider_response_schema_contract_by_id(workspace_path, schema_contract_id)
        if not sc_path:
            missing_artifacts.append("source_provider_response_schema_contract")
    else:
        missing_artifacts.append("source_provider_response_schema_contract")

    if pairing_id:
        pairing_path = find_provider_request_response_pairing_by_id(workspace_path, pairing_id)
        if not pairing_path:
            missing_artifacts.append("source_provider_request_response_pairing")
    else:
        missing_artifacts.append("source_provider_request_response_pairing")

    if intake_id:
        intake_path = find_provider_response_intake_policy_by_id(workspace_path, intake_id)
        if not intake_path:
            missing_artifacts.append("source_provider_response_intake_policy")
    else:
        missing_artifacts.append("source_provider_response_intake_policy")

    if preview_id:
        preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, preview_id)
        if not preview_path:
            missing_artifacts.append("source_provider_outbound_payload_preview")
    else:
        missing_artifacts.append("source_provider_outbound_payload_preview")

    # Future response is expected to be missing in this batch
    missing_artifacts.append("future_provider_response_artifact")
    warnings.append("Future provider response artifact is not yet present. This is expected.")

    if data.get("review_result_state") == "review_contract_recorded_no_response_present":
        review_health = "review_contract_recorded_no_response_present"
    elif data.get("review_result_state") == "future_response_required":
        review_health = "incomplete_expected"
    else:
        review_health = "blocked_until_response_artifact_exists"

    blocking_reasons.extend([
        "provider_execution_not_implemented",
        "provider_response_reception_not_implemented",
        "future_response_artifact_required",
        "manual_review_gate_required",
        "schema_contract_not_enabled",
        "review_result_not_present",
        "trust_upgrade_not_implemented",
    ])

    return {
        "ok": True,
        "status": "research_provider_response_review_result_doctor",
        "run_id": safe_run_id,
        "review_health": review_health,
        "review_result_present": False,
        "manual_review_gate_open": False,
        "provider_response_trusted": False,
        "missing_artifacts": missing_artifacts,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }
