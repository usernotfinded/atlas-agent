"""Provider execution unlock state contract — local, configless unlock state artifact.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider execution unlock state artifacts. It does NOT call any real provider,
does NOT perform network requests, does NOT read API keys, does NOT read os.environ,
does NOT load .env.atlas, does NOT import provider SDKs, does NOT receive real provider
responses, does NOT trust provider responses, does NOT open the manual review gate,
does NOT grant manual unlock, does NOT enable provider calls, and does NOT touch brokers.

A provider execution unlock state contract defines the future provider execution unlock
state machine, required prerequisites, blocked states, failure modes, and manual-unlock
requirements. Provider execution remains disabled and unimplemented.
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

PROVIDER_EXECUTION_UNLOCK_STATE_VERSION = "research_provider_execution_unlock_state_v1"

_PROVIDER_EXECUTION_UNLOCK_STATE_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_UNLOCK_STATUSES = {
    "unlock_state_recorded",
    "manual_unlock_required",
    "unlock_state_invalid",
}

_VALID_UNLOCK_SCOPES = {
    "future_provider_execution_unlock_only",
}

_VALID_UNLOCK_STATES = {
    "disabled",
    "prerequisites_recorded",
    "manual_unlock_required",
    "blocked_no_provider_adapter",
    "blocked_no_credential_loader",
    "blocked_no_real_response_artifact",
    "blocked_no_trust_upgrade_policy",
    "blocked_no_network_policy",
    "blocked_no_manual_approval_policy",
}

_VALID_CURRENT_STATES = {
    "disabled",
    "manual_unlock_required",
}

_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE = [
    "manual_unlock_requested",
    "manual_unlock_granted",
    "manual_unlock_revoked",
    "provider_execution_unlocked",
    "provider_enabled",
    "network_enabled",
    "credentials_loaded",
    "credential_value_present",
    "credential_lookup_attempted",
    "env_read_attempted",
    "dotenv_loaded",
    "provider_adapter_present",
    "provider_adapter_enabled",
    "provider_call_allowed",
    "actual_provider_call_made",
    "outbound_request_sent",
    "future_provider_execution_possible",
    "future_response_artifact_present",
    "provider_response_received",
    "provider_response_trusted",
    "provider_response_imported",
    "provider_response_reviewed",
    "review_result_present",
    "manual_review_gate_open",
    "trust_upgrade_performed",
    "provider_response_can_create_orders",
    "provider_response_can_approve_orders",
    "provider_response_can_call_broker",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
]

_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE = [
    "unlock_state_recorded",
    "manual_unlock_required",
]


@dataclass(frozen=True)
class ProviderExecutionUnlockStateValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_unlock_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        value = str(value)
    return sanitize_contract_text(value, max_chars)


def validate_provider_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_execution_unlock_state_provider")
    if value not in _get_disabled_provider_ids():
        raise ResearchSessionError("invalid_provider_execution_unlock_state_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_execution_unlock_state_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_execution_unlock_state_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_unlock_state_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_execution_unlock_state_model")
    return value


def validate_unlock_state_status(value: str) -> str:
    if not value or value not in _VALID_UNLOCK_STATUSES:
        raise ResearchSessionError("invalid_provider_execution_unlock_state_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_unlock_state_status")
    return value


def validate_unlock_state_scope(value: str) -> str:
    if not value or value not in _VALID_UNLOCK_SCOPES:
        raise ResearchSessionError("invalid_provider_execution_unlock_state_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_unlock_state_status")
    return value


def validate_unlock_state(value: str) -> str:
    if not value or value not in _VALID_UNLOCK_STATES:
        raise ResearchSessionError("invalid_provider_execution_unlock_state_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_unlock_state_status")
    return value


def validate_current_state(value: str) -> str:
    if not value or value not in _VALID_CURRENT_STATES:
        raise ResearchSessionError("invalid_provider_execution_unlock_state_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_unlock_state_status")
    return value


def provider_execution_unlock_state_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_EXECUTION_UNLOCK_STATE_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
        if data.get(flag) is not False:
            return "provider_execution_unlock_state_impossible_boolean"
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
        if data.get(flag) is not True:
            return "provider_execution_unlock_state_impossible_boolean"
    return None


def _build_unlock_transition_policy() -> dict[str, Any]:
    return {
        "automatic_unlock_allowed": False,
        "artifact_self_unlock_allowed": False,
        "review_result_self_unlock_allowed": False,
        "manual_unlock_required": True,
        "manual_unlock_grants_provider_call_in_this_batch": False,
        "unlock_requires_separate_future_policy": True,
        "unlock_transition_writes_events_in_this_batch": False,
        "unlock_transition_can_create_orders": False,
        "unlock_transition_can_call_broker": False,
    }


def _build_manual_unlock_policy() -> dict[str, Any]:
    return {
        "manual_unlock_required": True,
        "manual_unlock_requested": False,
        "manual_unlock_granted": False,
        "manual_unlock_revoked": False,
        "manual_unlock_actor_recorded": False,
        "manual_unlock_reason_recorded": False,
        "manual_unlock_can_enable_provider_call_in_this_batch": False,
        "manual_unlock_requires_future_command": True,
        "manual_unlock_requires_future_audit_event": True,
        "manual_unlock_requires_future_revocation_path": True,
    }


def _build_credential_unlock_policy() -> dict[str, Any]:
    return {
        "credential_loader_required_in_future": True,
        "credential_loader_implemented": False,
        "credential_lookup_allowed_in_this_batch": False,
        "credentials_loaded": False,
        "credential_value_present": False,
        "dotenv_loading_allowed": False,
        "env_lookup_allowed": False,
    }


def _build_provider_adapter_unlock_policy() -> dict[str, Any]:
    return {
        "provider_adapter_required_in_future": True,
        "provider_adapter_present": False,
        "provider_adapter_enabled": False,
        "provider_sdk_import_allowed": False,
        "provider_network_call_allowed": False,
        "provider_adapter_can_call_broker": False,
    }


def _build_network_unlock_policy() -> dict[str, Any]:
    return {
        "network_required_for_future_real_call": True,
        "network_enabled": False,
        "network_call_allowed_in_this_batch": False,
        "outbound_request_sent": False,
        "request_send_requires_future_gate": True,
    }


def _build_request_send_unlock_policy() -> dict[str, Any]:
    return {
        "payload_preview_required": True,
        "payload_preview_present": True,
        "raw_request_body_stored": False,
        "outbound_request_sent": False,
        "request_send_allowed_in_this_batch": False,
        "request_send_requires_future_unlock": True,
    }


def _build_response_import_unlock_policy() -> dict[str, Any]:
    return {
        "future_response_artifact_required": True,
        "future_response_artifact_present": False,
        "provider_response_received": False,
        "provider_response_imported": False,
        "provider_response_trusted": False,
        "response_import_allowed_in_this_batch": False,
    }


def _build_trust_upgrade_policy() -> dict[str, Any]:
    return {
        "trust_upgrade_required_before_any_future_use": True,
        "trust_upgrade_implemented": False,
        "trust_upgrade_performed": False,
        "provider_response_trusted": False,
        "manual_review_does_not_imply_trust": True,
        "unlock_state_does_not_imply_trust": True,
    }


def _build_trading_separation_policy() -> dict[str, Any]:
    return {
        "unlock_state_is_not_trading_signal": True,
        "unlock_state_cannot_create_pending_order": True,
        "unlock_state_cannot_approve_order": True,
        "unlock_state_cannot_submit_order": True,
        "unlock_state_cannot_modify_risk": True,
        "unlock_state_cannot_call_broker": True,
    }


def _build_broker_separation_policy() -> dict[str, Any]:
    return {
        "broker_live_bridge_allowed": False,
        "broker_adapter_access_allowed": False,
        "order_routing_allowed": False,
        "approval_manager_access_allowed": False,
        "risk_manager_access_allowed": False,
    }


def _build_rollback_policy() -> dict[str, Any]:
    return {
        "unlock_revocation_required_in_future": True,
        "unlock_revoked_in_this_batch": False,
        "rollback_to_disabled_required": True,
        "rollback_event_required_in_future": True,
        "rollback_can_call_broker": False,
    }


def _build_denylist_metadata() -> dict[str, Any]:
    return {
        "denylist_profile": "atlas_provider_execution_unlock_state_v1",
        "forbidden_fragment_count": len(FORBIDDEN_FRAGMENTS),
        "forbidden_fragments_raw_stored": False,
    }


def build_provider_execution_unlock_state_dict(
    source_review_result: dict[str, Any],
    source_schema_contract: dict[str, Any],
    source_pairing: dict[str, Any],
    source_intake_policy: dict[str, Any],
    source_preview: dict[str, Any],
    unlock_state_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(unlock_state_id, "provider_execution_unlock_state_id")

    src_review_result_id = source_review_result.get("provider_response_review_result_id", "")
    validate_contract_lineage_id(src_review_result_id, "source_provider_response_review_result_id")

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
    artifact_path_rel = f".atlas/research/{symbol}/provider_execution_unlock_states/{unlock_state_id}.json"

    unlock_transition_policy = _build_unlock_transition_policy()
    manual_unlock_policy = _build_manual_unlock_policy()
    credential_unlock_policy = _build_credential_unlock_policy()
    provider_adapter_unlock_policy = _build_provider_adapter_unlock_policy()
    network_unlock_policy = _build_network_unlock_policy()
    request_send_unlock_policy = _build_request_send_unlock_policy()
    response_import_unlock_policy = _build_response_import_unlock_policy()
    trust_upgrade_policy = _build_trust_upgrade_policy()
    trading_separation_policy = _build_trading_separation_policy()
    broker_separation_policy = _build_broker_separation_policy()
    rollback_policy = _build_rollback_policy()
    denylist_metadata = _build_denylist_metadata()

    required_prerequisites = [
        "provider_opt_in_policy_recorded",
        "credential_boundary_recorded",
        "payload_preview_recorded",
        "response_intake_policy_recorded",
        "request_response_pairing_recorded",
        "response_schema_contract_recorded",
        "response_review_result_contract_recorded",
        "manual_unlock_policy_required",
        "credential_loader_policy_required_in_future",
        "provider_adapter_required_in_future",
        "network_policy_required_in_future",
        "real_response_artifact_required_in_future",
        "trust_upgrade_policy_required_in_future",
    ]

    satisfied_prerequisites = [
        "provider_opt_in_policy_recorded",
        "credential_boundary_recorded",
        "payload_preview_recorded",
        "response_intake_policy_recorded",
        "request_response_pairing_recorded",
        "response_schema_contract_recorded",
        "response_review_result_contract_recorded",
    ]

    missing_prerequisites = [
        "manual_unlock_not_granted",
        "credential_loader_not_implemented",
        "provider_adapter_not_implemented",
        "network_policy_not_implemented",
        "real_provider_response_artifact_missing",
        "trust_upgrade_policy_not_implemented",
    ]

    blocking_reasons = [
        "provider_execution_disabled",
        "manual_unlock_required",
        "provider_adapter_missing",
        "credentials_not_loaded",
        "network_disabled",
        "real_response_missing",
        "trust_upgrade_missing",
        "broker_bridge_disabled",
    ]

    warnings = [
        "This is a local provider execution unlock state contract. No provider request was sent.",
        "No provider response was received.",
        "No provider response is trusted by default.",
        "Provider execution remains disabled and not implemented.",
        "Manual unlock is required but not granted.",
        "Provider adapter is not implemented.",
        "Credential loader is not implemented.",
        "Network policy is not implemented.",
        "Real provider response artifact is missing.",
        "Trust upgrade policy is not implemented.",
        "Unlock state cannot create orders, approvals, or pending orders.",
        "Unlock state cannot call broker.",
        "Real provider execution requires explicit future opt-in.",
    ]

    metadata = {
        "source_review_result_schema_version": source_review_result.get("schema_version", ""),
        "source_review_result_contract_version": source_review_result.get("contract_version", ""),
        "source_schema_contract_schema_version": source_schema_contract.get("schema_version", ""),
        "source_schema_contract_contract_version": source_schema_contract.get("contract_version", ""),
        "source_pairing_schema_version": source_pairing.get("schema_version", ""),
        "source_pairing_contract_version": source_pairing.get("contract_version", ""),
        "source_intake_policy_schema_version": source_intake_policy.get("schema_version", ""),
        "source_intake_policy_contract_version": source_intake_policy.get("contract_version", ""),
        "source_preview_schema_version": source_preview.get("schema_version", ""),
        "source_preview_contract_version": source_preview.get("contract_version", ""),
    }

    source_review_result_hash = source_review_result.get("artifact_hash", "")
    source_schema_contract_hash = source_schema_contract.get("artifact_hash", "")
    source_pairing_hash = source_pairing.get("artifact_hash", "")
    source_response_intake_policy_hash = source_intake_policy.get("artifact_hash", "")
    source_payload_preview_hash = source_preview.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_execution_unlock_state",
        "contract_version": PROVIDER_EXECUTION_UNLOCK_STATE_VERSION,
        "provider_execution_unlock_state_id": unlock_state_id,
        "source_provider_response_review_result_id": src_review_result_id,
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
        "unlock_state_status": "unlock_state_recorded",
        "unlock_state_scope": "future_provider_execution_unlock_only",
        "unlock_state": "manual_unlock_required",
        "state_machine_version": PROVIDER_EXECUTION_UNLOCK_STATE_VERSION,
        "current_state": "disabled",
        "allowed_future_states": [
            "prerequisites_recorded",
            "manual_unlock_required",
            "blocked_no_provider_adapter",
            "blocked_no_credential_loader",
            "blocked_no_real_response_artifact",
            "blocked_no_trust_upgrade_policy",
            "blocked_no_network_policy",
            "blocked_no_manual_approval_policy",
        ],
        "blocked_future_states": [
            "enabled",
            "unlocked",
            "provider_call_allowed",
            "ready_to_call_provider",
            "production_ready",
            "live_ready",
        ],
        "required_prerequisites": required_prerequisites,
        "satisfied_prerequisites": satisfied_prerequisites,
        "missing_prerequisites": missing_prerequisites,
        "blocking_reasons": blocking_reasons,
        "unlock_transition_policy": unlock_transition_policy,
        "manual_unlock_policy": manual_unlock_policy,
        "credential_unlock_policy": credential_unlock_policy,
        "provider_adapter_unlock_policy": provider_adapter_unlock_policy,
        "network_unlock_policy": network_unlock_policy,
        "request_send_unlock_policy": request_send_unlock_policy,
        "response_import_unlock_policy": response_import_unlock_policy,
        "trust_upgrade_policy": trust_upgrade_policy,
        "trading_separation_policy": trading_separation_policy,
        "broker_separation_policy": broker_separation_policy,
        "rollback_policy": rollback_policy,
        "source_review_result_hash": source_review_result_hash,
        "source_schema_contract_hash": source_schema_contract_hash,
        "source_pairing_hash": source_pairing_hash,
        "source_response_intake_policy_hash": source_response_intake_policy_hash,
        "source_payload_preview_hash": source_payload_preview_hash,
        "unlock_state_recorded": True,
        "manual_unlock_required": True,
        "manual_unlock_requested": False,
        "manual_unlock_granted": False,
        "manual_unlock_revoked": False,
        "provider_execution_unlocked": False,
        "provider_enabled": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "credential_value_present": False,
        "credential_lookup_attempted": False,
        "env_read_attempted": False,
        "dotenv_loaded": False,
        "provider_adapter_present": False,
        "provider_adapter_enabled": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "outbound_request_sent": False,
        "future_provider_execution_possible": False,
        "future_response_artifact_present": False,
        "provider_response_received": False,
        "provider_response_trusted": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "review_result_present": False,
        "manual_review_gate_open": False,
        "trust_upgrade_performed": False,
        "provider_response_can_create_orders": False,
        "provider_response_can_approve_orders": False,
        "provider_response_can_call_broker": False,
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

    artifact["artifact_hash"] = provider_execution_unlock_state_sha256(artifact)
    return artifact


def create_provider_execution_unlock_state(
    workspace_path: Path,
    review_result_id: str,
) -> dict[str, Any]:
    safe_review_result_id = validate_run_id(review_result_id)

    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )

    review_result_path = find_provider_response_review_result_by_id(workspace_path, safe_review_result_id)
    if review_result_path is None:
        raise ResearchSessionError("provider_execution_unlock_state_source_review_result_missing")

    source_review_result = load_provider_response_review_result(review_result_path, workspace_path)

    source_schema_contract_id = source_review_result.get("source_provider_response_schema_contract_id", "")
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )

    schema_contract_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
    if schema_contract_path is None:
        raise ResearchSessionError("provider_execution_unlock_state_source_schema_contract_missing")

    source_schema_contract = load_provider_response_schema_contract(schema_contract_path, workspace_path)

    source_pairing_id = source_review_result.get("source_provider_request_response_pairing_id", "")
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )

    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
    if pairing_path is None:
        raise ResearchSessionError("provider_execution_unlock_state_source_pairing_missing")

    source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)

    source_intake_id = source_review_result.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
    if intake_path is None:
        raise ResearchSessionError("provider_execution_unlock_state_source_response_intake_missing")

    source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)

    source_preview_id = source_review_result.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if preview_path is None:
        raise ResearchSessionError("provider_execution_unlock_state_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    unlock_state_id = generate_run_id()
    artifact = build_provider_execution_unlock_state_dict(
        source_review_result,
        source_schema_contract,
        source_pairing,
        source_intake_policy,
        source_preview,
        unlock_state_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    result_dir = workspace_path / RESEARCH_DIR / symbol / "provider_execution_unlock_states"
    result_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_execution_unlock_state_created",
        "provider_execution_unlock_state_id": unlock_state_id,
        "source_provider_response_review_result_id": safe_review_result_id,
        "source_provider_response_schema_contract_id": source_schema_contract_id,
        "source_provider_request_response_pairing_id": source_pairing_id,
        "source_provider_response_intake_policy_id": source_intake_id,
        "source_provider_outbound_payload_preview_id": source_preview_id,
        "unlock_state_status": artifact["unlock_state_status"],
        "unlock_state": artifact["unlock_state"],
        "current_state": artifact["current_state"],
        "manual_unlock_required": True,
        "manual_unlock_requested": False,
        "manual_unlock_granted": False,
        "provider_execution_unlocked": False,
        "provider_adapter_present": False,
        "provider_adapter_enabled": False,
        "provider_enabled": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "outbound_request_sent": False,
        "future_provider_execution_possible": False,
        "provider_response_received": False,
        "provider_response_trusted": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "review_result_present": False,
        "manual_review_gate_open": False,
        "trust_upgrade_performed": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_execution_unlock_state_{field_name}"
    return None


def safe_validate_provider_execution_unlock_state_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_execution_unlock_state_schema"

    if data.get("artifact_type") != "provider_execution_unlock_state":
        return None, "provider_execution_unlock_state_malformed"

    if data.get("contract_version") != PROVIDER_EXECUTION_UNLOCK_STATE_VERSION:
        return None, "provider_execution_unlock_state_malformed"

    try:
        validate_unlock_state_status(data.get("unlock_state_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_unlock_state_status"

    try:
        validate_unlock_state_scope(data.get("unlock_state_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_unlock_state_status"

    try:
        validate_unlock_state(data.get("unlock_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_unlock_state_status"

    try:
        validate_current_state(data.get("current_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_unlock_state_status"

    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    if data.get("mode") != "paper":
        return None, "provider_execution_unlock_state_malformed"

    lineage_field_names = [
        "provider_execution_unlock_state_id",
        "source_provider_response_review_result_id",
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
            return None, "invalid_provider_execution_unlock_state_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_unlock_state_lineage"

    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_unlock_state_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_unlock_state_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_execution_unlock_state_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_execution_unlock_state_hash_mismatch"

    if workspace_path is not None and not for_replay:
        source_review_result_id = data.get("source_provider_response_review_result_id", "")
        if source_review_result_id:
            try:
                from atlas_agent.research.provider_response_review_result import (
                    find_provider_response_review_result_by_id,
                    load_provider_response_review_result,
                )

                rr_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
                if rr_path is None:
                    return None, "provider_execution_unlock_state_source_review_result_missing"
                rr_data = load_provider_response_review_result(rr_path, workspace_path)
                stored_rr_hash = data.get("source_review_result_hash", "")
                actual_rr_hash = rr_data.get("artifact_hash", "")
                if stored_rr_hash != actual_rr_hash:
                    return None, "provider_execution_unlock_state_source_review_result_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_unlock_state_source_review_result_missing"

        source_schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
        if source_schema_contract_id:
            try:
                from atlas_agent.research.provider_response_schema_contract import (
                    find_provider_response_schema_contract_by_id,
                    load_provider_response_schema_contract,
                )

                sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
                if sc_path is None:
                    return None, "provider_execution_unlock_state_source_schema_contract_missing"
                sc_data = load_provider_response_schema_contract(sc_path, workspace_path)
                stored_sc_hash = data.get("source_schema_contract_hash", "")
                actual_sc_hash = sc_data.get("artifact_hash", "")
                if stored_sc_hash != actual_sc_hash:
                    return None, "provider_execution_unlock_state_source_schema_contract_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_unlock_state_source_schema_contract_missing"

        source_pairing_id = data.get("source_provider_request_response_pairing_id", "")
        if source_pairing_id:
            try:
                from atlas_agent.research.provider_request_response_pairing import (
                    find_provider_request_response_pairing_by_id,
                    load_provider_request_response_pairing,
                )

                pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
                if pairing_path is None:
                    return None, "provider_execution_unlock_state_source_pairing_missing"
                pairing_data = load_provider_request_response_pairing(pairing_path, workspace_path)
                stored_pairing_hash = data.get("source_pairing_hash", "")
                actual_pairing_hash = pairing_data.get("artifact_hash", "")
                if stored_pairing_hash != actual_pairing_hash:
                    return None, "provider_execution_unlock_state_source_pairing_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_unlock_state_source_pairing_missing"

        source_intake_id = data.get("source_provider_response_intake_policy_id", "")
        if source_intake_id:
            try:
                from atlas_agent.research.provider_response_intake_policy import (
                    find_provider_response_intake_policy_by_id,
                    load_provider_response_intake_policy,
                )

                intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
                if intake_path is None:
                    return None, "provider_execution_unlock_state_source_response_intake_missing"
                intake_data = load_provider_response_intake_policy(intake_path, workspace_path)
                stored_intake_hash = data.get("source_response_intake_policy_hash", "")
                actual_intake_hash = intake_data.get("artifact_hash", "")
                if stored_intake_hash != actual_intake_hash:
                    return None, "provider_execution_unlock_state_source_response_intake_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_unlock_state_source_response_intake_missing"

        source_preview_id = data.get("source_provider_outbound_payload_preview_id", "")
        if source_preview_id:
            try:
                from atlas_agent.research.provider_outbound_payload_preview import (
                    find_provider_outbound_payload_preview_by_id,
                    load_provider_outbound_payload_preview,
                )

                preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
                if preview_path is None:
                    return None, "provider_execution_unlock_state_source_payload_preview_missing"
                preview_data = load_provider_outbound_payload_preview(preview_path, workspace_path)
                stored_preview_hash = data.get("source_payload_preview_hash", "")
                actual_preview_hash = preview_data.get("artifact_hash", "")
                if stored_preview_hash != actual_preview_hash:
                    return None, "provider_execution_unlock_state_source_payload_preview_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_unlock_state_source_payload_preview_missing"

    # Check policy fields for forbidden fragments
    policy_fields = [
        json.dumps(data.get("unlock_transition_policy", {})),
        json.dumps(data.get("manual_unlock_policy", {})),
        json.dumps(data.get("credential_unlock_policy", {})),
        json.dumps(data.get("provider_adapter_unlock_policy", {})),
        json.dumps(data.get("network_unlock_policy", {})),
        json.dumps(data.get("request_send_unlock_policy", {})),
        json.dumps(data.get("response_import_unlock_policy", {})),
        json.dumps(data.get("trust_upgrade_policy", {})),
        json.dumps(data.get("trading_separation_policy", {})),
        json.dumps(data.get("broker_separation_policy", {})),
        json.dumps(data.get("rollback_policy", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("required_prerequisites", [])),
        json.dumps(data.get("satisfied_prerequisites", [])),
        json.dumps(data.get("missing_prerequisites", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in policy_fields):
        return None, "provider_execution_unlock_state_malformed"

    # Check status/scope/state/current_state for forbidden fragments
    policy_summaries = [
        data.get("unlock_state_status", ""),
        data.get("unlock_state_scope", ""),
        data.get("unlock_state", ""),
        data.get("current_state", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_execution_unlock_state_forbidden_unlock_claim"

    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_execution_unlock_state_malformed"

    cleaned = {k: v for k, v in data.items()}
    return cleaned, None


def validate_provider_execution_unlock_state_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderExecutionUnlockStateValidationResult:
    data = load_provider_execution_unlock_state(path, workspace_path)
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
            at == "provider_execution_unlock_state",
            "artifact_type must be provider_execution_unlock_state." if at != "provider_execution_unlock_state" else "artifact_type is correct.",
        )
    )

    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_EXECUTION_UNLOCK_STATE_VERSION,
            "contract_version must match current contract." if cv != PROVIDER_EXECUTION_UNLOCK_STATE_VERSION else "contract_version matches.",
        )
    )

    status = data.get("unlock_state_status", "")
    status_ok = status in _VALID_UNLOCK_STATUSES
    checks.append(
        _check_name(
            "unlock_state_status_valid",
            status_ok,
            "unlock_state_status is invalid." if not status_ok else "unlock_state_status is valid.",
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

    computed = provider_execution_unlock_state_sha256(data)
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

    return ProviderExecutionUnlockStateValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation="Proceed with unlock state contract." if valid else "Reject artifact and investigate tampering.",
        warnings=warnings,
    )


def load_provider_execution_unlock_state(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        raise ResearchSessionError("provider_execution_unlock_state_malformed") from e

    cleaned, err = safe_validate_provider_execution_unlock_state_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    if not cleaned:
        raise ResearchSessionError("provider_execution_unlock_state_malformed")
    return cleaned


def load_and_validate_provider_execution_unlock_state(path: Path, workspace_path: Path) -> dict[str, Any]:
    data = load_provider_execution_unlock_state(path, workspace_path)
    res = validate_provider_execution_unlock_state_artifact(path, workspace_path)
    if not res.valid:
        raise ResearchSessionError("invalid_provider_execution_unlock_state_artifact")
    return data


def find_provider_execution_unlock_state_by_id(workspace_path: Path, unlock_state_id: str) -> Path | None:
    safe_id = validate_run_id(unlock_state_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    for p in search_dir.rglob("provider_execution_unlock_states/*.json"):
        if p.stem == safe_id:
            return p
    return None


def replay_provider_execution_unlock_state(
    workspace_path: Path,
    unlock_state_id: str,
) -> dict[str, Any]:
    safe_id = validate_run_id(unlock_state_id)
    artifact_path = find_provider_execution_unlock_state_by_id(workspace_path, safe_id)
    if not artifact_path:
        raise ResearchSessionError("provider_execution_unlock_state_not_found")

    try:
        old_artifact = load_provider_execution_unlock_state(artifact_path, workspace_path=None)
    except ResearchSessionError:
        # Hash mismatch or other validation failure — read raw for basic info
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            old_hash = raw.get("artifact_hash", "")
        except Exception:
            old_hash = ""
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_hash,
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    source_review_result_id = old_artifact.get("source_provider_response_review_result_id", "")
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )

    rr_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
    if not rr_path:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    try:
        source_review_result = load_provider_response_review_result(rr_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    source_schema_contract_id = old_artifact.get("source_provider_response_schema_contract_id", "")
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )

    sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
    if not sc_path:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    try:
        source_schema_contract = load_provider_response_schema_contract(sc_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    source_pairing_id = old_artifact.get("source_provider_request_response_pairing_id", "")
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )

    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
    if not pairing_path:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    try:
        source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    source_intake_id = old_artifact.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
    if not intake_path:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    try:
        source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    source_preview_id = old_artifact.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if not preview_path:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    try:
        source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_execution_unlock_state_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_execution_unlock_state_replay_failed",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
        }

    new_artifact = build_provider_execution_unlock_state_dict(
        source_review_result,
        source_schema_contract,
        source_pairing,
        source_intake_policy,
        source_preview,
        safe_id,
        workspace_path,
    )

    new_artifact["created_at"] = old_artifact.get("created_at", new_artifact["created_at"])
    new_artifact["artifact_hash"] = provider_execution_unlock_state_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_execution_unlock_state_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_execution_unlock_state_replayed",
        "provider_execution_unlocked": False,
        "provider_call_allowed": False,
        "manual_unlock_granted": False,
    }


def iter_provider_execution_unlock_state_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider execution unlock state artifact metadata dicts, newest first.

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
        result_dir = sym_dir / "provider_execution_unlock_states"
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
                    "provider_execution_unlock_state_id": "<invalid>",
                    "source_provider_response_review_result_id": "<invalid>",
                    "source_provider_response_schema_contract_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "unlock_state_status": "invalid",
                    "unlock_state": "invalid",
                    "current_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_execution_unlock_state_artifact",
                    "created_at": "",
                })
                continue
            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_execution_unlock_state_id": "<invalid>",
                    "source_provider_response_review_result_id": "<invalid>",
                    "source_provider_response_schema_contract_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "unlock_state_status": "invalid",
                    "unlock_state": "invalid",
                    "current_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_execution_unlock_state_artifact",
                    "created_at": "",
                })
                continue
            cleaned, error = safe_validate_provider_execution_unlock_state_data(raw, workspace_path=workspace_path)
            if error or cleaned is None:
                invalid_items.append({
                    "provider_execution_unlock_state_id": "<invalid>",
                    "source_provider_response_review_result_id": "<invalid>",
                    "source_provider_response_schema_contract_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "unlock_state_status": "invalid",
                    "unlock_state": "invalid",
                    "current_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_execution_unlock_state_artifact",
                    "created_at": "",
                })
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append({
                "provider_execution_unlock_state_id": cleaned.get("provider_execution_unlock_state_id", path.stem),
                "source_provider_response_review_result_id": cleaned.get("source_provider_response_review_result_id", ""),
                "source_provider_response_schema_contract_id": cleaned.get("source_provider_response_schema_contract_id", ""),
                "source_provider_request_response_pairing_id": cleaned.get("source_provider_request_response_pairing_id", ""),
                "source_provider_response_intake_policy_id": cleaned.get("source_provider_response_intake_policy_id", ""),
                "source_provider_outbound_payload_preview_id": cleaned.get("source_provider_outbound_payload_preview_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "unlock_state_status": cleaned.get("unlock_state_status", ""),
                "unlock_state_scope": cleaned.get("unlock_state_scope", ""),
                "unlock_state": cleaned.get("unlock_state", ""),
                "current_state": cleaned.get("current_state", ""),
                "artifact_path": rel_path,
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "created_at": cleaned.get("created_at", ""),
                "unlock_state_recorded": cleaned.get("unlock_state_recorded", True),
                "manual_unlock_required": cleaned.get("manual_unlock_required", True),
                "manual_unlock_requested": cleaned.get("manual_unlock_requested", False),
                "manual_unlock_granted": cleaned.get("manual_unlock_granted", False),
                "provider_execution_unlocked": cleaned.get("provider_execution_unlocked", False),
                "provider_adapter_present": cleaned.get("provider_adapter_present", False),
                "provider_adapter_enabled": cleaned.get("provider_adapter_enabled", False),
                "provider_enabled": cleaned.get("provider_enabled", False),
                "network_enabled": cleaned.get("network_enabled", False),
                "credentials_loaded": cleaned.get("credentials_loaded", False),
                "credential_value_present": cleaned.get("credential_value_present", False),
                "provider_call_allowed": cleaned.get("provider_call_allowed", False),
                "actual_provider_call_made": cleaned.get("actual_provider_call_made", False),
                "outbound_request_sent": cleaned.get("outbound_request_sent", False),
                "provider_response_received": cleaned.get("provider_response_received", False),
                "provider_response_trusted": cleaned.get("provider_response_trusted", False),
                "provider_response_imported": cleaned.get("provider_response_imported", False),
                "provider_response_reviewed": cleaned.get("provider_response_reviewed", False),
                "review_result_present": cleaned.get("review_result_present", False),
                "manual_review_gate_open": cleaned.get("manual_review_gate_open", False),
                "trust_upgrade_performed": cleaned.get("trust_upgrade_performed", False),
                "trading_signal_generated": cleaned.get("trading_signal_generated", False),
                "approval_created": cleaned.get("approval_created", False),
                "pending_order_created": cleaned.get("pending_order_created", False),
                "broker_touched": cleaned.get("broker_touched", False),
            })

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items + invalid_items


def _find_latest_provider_execution_unlock_state_for_run(workspace_path: Path, run_id: str) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    latest_path: Path | None = None
    latest_time = ""
    for p in search_dir.rglob("provider_execution_unlock_states/*.json"):
        try:
            data = load_provider_execution_unlock_state(p, workspace_path=None)
            if data.get("source_run_id") == safe_run_id:
                t = data.get("created_at", "")
                if not latest_time or t > latest_time:
                    latest_time = t
                    latest_path = p
        except Exception:
            pass
    return latest_path


def summarize_provider_execution_unlock_state(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_execution_unlock_state_for_run(workspace_path, safe_run_id)

    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_execution_unlock_state",
            "provider_execution_unlock_state_id": None,
            "unlock_state_status": "not_recorded",
            "unlock_state": "not_recorded",
            "current_state": "not_recorded",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
            "artifact_path": None,
        }

    try:
        data = load_and_validate_provider_execution_unlock_state(artifact_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": True,
            "status": "invalid_provider_execution_unlock_state",
            "provider_execution_unlock_state_id": None,
            "unlock_state_status": "invalid",
            "unlock_state": "invalid",
            "current_state": "invalid",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
            "artifact_path": None,
        }

    return {
        "ok": True,
        "status": "research_provider_execution_unlock_state_summary",
        "provider_execution_unlock_state_id": data.get("provider_execution_unlock_state_id"),
        "unlock_state_status": data.get("unlock_state_status"),
        "unlock_state": data.get("unlock_state"),
        "current_state": data.get("current_state"),
        "provider_execution_unlocked": False,
        "provider_call_allowed": False,
        "manual_unlock_granted": False,
        "artifact_path": data.get("artifact_path"),
    }


def doctor_provider_execution_unlock_state(
    workspace_path: Path,
    run_id: str,
) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)

    missing_artifacts: list[str] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    unlock_path = _find_latest_provider_execution_unlock_state_for_run(workspace_path, safe_run_id)
    if not unlock_path:
        missing_artifacts.append("provider_execution_unlock_state")
        blocking_reasons.append("provider_execution_unlock_state_not_created")
        warnings.append("No provider execution unlock state exists for this run.")
        return {
            "ok": True,
            "status": "research_provider_execution_unlock_state_doctor",
            "run_id": safe_run_id,
            "unlock_health": "unlock_state_missing",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
            "missing_prerequisites": missing_artifacts,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
        }

    try:
        data = load_provider_execution_unlock_state(unlock_path, workspace_path)
    except ResearchSessionError as e:
        warnings.append(f"Unlock state artifact is invalid: {e}")
        return {
            "ok": True,
            "status": "research_provider_execution_unlock_state_doctor",
            "run_id": safe_run_id,
            "unlock_health": "unlock_state_invalid",
            "provider_execution_unlocked": False,
            "provider_call_allowed": False,
            "manual_unlock_granted": False,
            "missing_prerequisites": missing_artifacts,
            "blocking_reasons": ["unlock_state_artifact_invalid"],
            "warnings": warnings,
        }

    # Check source artifacts
    review_result_id = data.get("source_provider_response_review_result_id", "")
    schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
    pairing_id = data.get("source_provider_request_response_pairing_id", "")
    intake_id = data.get("source_provider_response_intake_policy_id", "")
    preview_id = data.get("source_provider_outbound_payload_preview_id", "")

    from atlas_agent.research.provider_response_review_result import find_provider_response_review_result_by_id
    from atlas_agent.research.provider_response_schema_contract import find_provider_response_schema_contract_by_id
    from atlas_agent.research.provider_request_response_pairing import find_provider_request_response_pairing_by_id
    from atlas_agent.research.provider_response_intake_policy import find_provider_response_intake_policy_by_id
    from atlas_agent.research.provider_outbound_payload_preview import find_provider_outbound_payload_preview_by_id

    if review_result_id:
        rr_path = find_provider_response_review_result_by_id(workspace_path, review_result_id)
        if not rr_path:
            missing_artifacts.append("source_provider_response_review_result")
    else:
        missing_artifacts.append("source_provider_response_review_result")

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

    # Future prerequisites are expected to be missing
    missing_artifacts.extend([
        "manual_unlock_not_granted",
        "provider_adapter_not_implemented",
        "credential_loader_not_implemented",
        "network_policy_not_implemented",
        "real_provider_response_artifact_missing",
        "trust_upgrade_policy_not_implemented",
    ])
    warnings.append("Future prerequisites are missing. This is expected in this batch.")

    if data.get("unlock_state") == "manual_unlock_required":
        unlock_health = "manual_unlock_required"
    elif data.get("unlock_state") == "prerequisites_recorded":
        unlock_health = "incomplete_expected"
    else:
        unlock_health = "blocked"

    blocking_reasons.extend([
        "provider_execution_disabled",
        "manual_unlock_required",
        "provider_adapter_missing",
        "credentials_not_loaded",
        "network_disabled",
        "real_response_missing",
        "trust_upgrade_missing",
        "broker_bridge_disabled",
    ])

    return {
        "ok": True,
        "status": "research_provider_execution_unlock_state_doctor",
        "run_id": safe_run_id,
        "unlock_health": unlock_health,
        "provider_execution_unlocked": False,
        "provider_call_allowed": False,
        "manual_unlock_granted": False,
        "missing_prerequisites": missing_artifacts,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }
