# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_mock_response_review_sandbox.py
# PURPOSE: Mock pipeline, step 2: reviews a candidate response in a contained sandbox,
#          so a bad response is caught here rather than downstream.
# DEPS:    research.provider_mock_response_simulation, research.sandbox_contracts
# ==============================================================================

"""Provider mock response review sandbox — local, configless mock response review artifact.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider mock response review sandbox artifacts. It does NOT implement any real provider
response review, does NOT review raw provider responses, does NOT read external files,
does NOT accept stdin input, does NOT call any real provider, does NOT perform network
requests, does NOT read API keys, does NOT read os.environ, does NOT load .env.atlas,
does NOT import provider SDKs, does NOT receive real provider responses, does NOT trust
provider responses, does NOT create trading signals, does NOT create approvals or pending
orders, does NOT authorize live trading, and does NOT touch brokers.

A provider mock response review sandbox is derived ONLY from an existing
provider_mock_response_import_candidate artifact. It represents a local sandboxed review
layer for mock import candidates, not a real provider response review.
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

PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION = "research_provider_mock_response_review_sandbox_v1"

_PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_MOCK_REVIEW_SANDBOX_STATUSES = {
    "mock_review_sandbox_recorded",
    "mock_review_sandbox_invalid",
}

_VALID_MOCK_REVIEW_SANDBOX_SCOPES = {
    "offline_mock_response_review_sandbox_only",
}

_VALID_MOCK_REVIEW_SANDBOX_STATES = {
    "mock_review_sandbox_recorded_untrusted",
    "mock_review_checks_completed_untrusted",
    "manual_followup_required",
    "mock_only_review_not_authorizing",
}

_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE = [
    "real_provider_response_reviewed",
    "real_provider_response_imported",
    "real_provider_response_received",
    "provider_response_received",
    "provider_response_imported",
    "provider_response_reviewed",
    "provider_response_trusted",
    "mock_response_trusted",
    "review_result_present",
    "manual_review_gate_open",
    "manual_review_completed",
    "review_decision_allows_use",
    "review_decision_allows_trust_upgrade",
    "review_decision_allows_trading_interpretation",
    "review_decision_allows_order_creation",
    "review_decision_allows_order_approval",
    "review_decision_allows_broker_call",
    "future_response_schema_validated",
    "raw_response_body_stored",
    "raw_request_body_stored",
    "raw_prompt_body_stored",
    "raw_review_notes_stored",
    "provider_sdk_imported",
    "http_client_imported",
    "network_enabled",
    "network_call_attempted",
    "credentials_loaded",
    "credential_value_present",
    "credential_lookup_attempted",
    "env_read_attempted",
    "dotenv_loaded",
    "provider_execution_unlocked",
    "manual_unlock_granted",
    "provider_call_allowed",
    "actual_provider_call_made",
    "outbound_request_sent",
    "trust_upgrade_performed",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
]

_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE = [
    "mock_review_sandbox_recorded",
    "mock_review_source_verified",
    "mock_review_checks_completed",
    "mock_review_passed",
    "mock_review_requires_manual_followup",
    "mock_only",
    "sandbox_review_only",
]

# Unsafe positive-claim phrases that must not appear in string values anywhere in the artifact.
_UNSAFE_POSITIVE_CLAIM_PHRASES = (
    "real provider response reviewed",
    "real provider response imported",
    "real provider response received",
    "provider response trusted",
    "mock response trusted",
    "sandbox review trusted",
    "manual review completed",
    "review decision allows use",
    "review decision allows trust upgrade",
    "review decision allows trading",
    "create order",
    "approve order",
    "call broker",
    "buy",
    "sell",
    "trading signal",
    "approval created",
    "pending order created",
    "broker touched",
    "trust upgrade performed",
    "manual unlock granted",
    "provider call allowed",
    "network enabled",
    "network call attempted",
    "credentials loaded",
    "api key loaded",
    "api call succeeded",
    "live trading authorized",
    "real provider adapter used",
    "real provider request sent",
)


@dataclass(frozen=True)
class ProviderMockResponseReviewSandboxValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _has_unsafe_positive_claims(value: Any) -> bool:
    """Recursively scan value for unsafe positive-claim phrases in string values."""
    if isinstance(value, str):
        lower = value.lower()
        return any(phrase in lower for phrase in _UNSAFE_POSITIVE_CLAIM_PHRASES)
    if isinstance(value, dict):
        return any(_has_unsafe_positive_claims(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_unsafe_positive_claims(item) for item in value)
    return False


def validate_provider_id(value: str) -> str:
    if not value or value != "mock":
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_model")
    return value


def validate_mock_review_sandbox_status(value: str) -> str:
    if not value or value not in _VALID_MOCK_REVIEW_SANDBOX_STATUSES:
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_status")
    return value


def validate_mock_review_sandbox_scope(value: str) -> str:
    if not value or value not in _VALID_MOCK_REVIEW_SANDBOX_SCOPES:
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_status")
    return value


def validate_mock_review_sandbox_state(value: str) -> str:
    if not value or value not in _VALID_MOCK_REVIEW_SANDBOX_STATES:
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_status")
    return value


def provider_mock_response_review_sandbox_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
        if data.get(flag) is not False:
            return "provider_mock_response_review_sandbox_impossible_boolean"
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
        if data.get(flag) is not True:
            return "provider_mock_response_review_sandbox_impossible_boolean"
    return None


def _build_mock_review_source_summary() -> dict[str, Any]:
    return {
        "source_artifact_type": "provider_mock_response_import_candidate",
        "source_provider_id": "mock",
        "source_is_mock": True,
        "source_is_real_provider_response": False,
        "source_import_candidate_trusted": False,
        "source_provider_response_trusted": False,
        "source_can_create_orders": False,
        "source_can_call_broker": False,
    }


def _build_mock_review_check_summary() -> dict[str, Any]:
    return {
        "mock_review_checks_completed": True,
        "mock_review_passed": True,
        "mock_review_requires_manual_followup": True,
        "real_provider_response_reviewed": False,
        "manual_review_completed": False,
        "trust_upgrade_performed": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
    }


def _build_mock_review_boundary_policy() -> dict[str, Any]:
    return {
        "mock_review_sandbox_allowed": True,
        "real_provider_review_allowed": False,
        "raw_response_review_allowed": False,
        "external_response_file_review_allowed": False,
        "stdin_response_review_allowed": False,
        "network_response_review_allowed": False,
        "sandbox_review_does_not_imply_trust": True,
        "sandbox_review_does_not_imply_manual_review_completed": True,
        "sandbox_review_does_not_authorize_trading": True,
    }


def _build_mock_review_storage_policy() -> dict[str, Any]:
    return {
        "raw_response_body_stored": False,
        "raw_prompt_body_stored": False,
        "raw_request_body_stored": False,
        "raw_review_notes_stored": False,
        "bounded_summary_stored": True,
        "raw_response_in_events_allowed": False,
        "raw_response_in_logs_allowed": False,
        "artifact_storage_allowed": True,
    }


def _build_mock_review_trust_policy() -> dict[str, Any]:
    return {
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "sandbox_review_trusted": False,
        "trust_upgrade_not_implemented": True,
        "sandbox_review_cannot_mark_trusted": True,
        "manual_review_required_before_any_future_use": True,
    }


def _build_mock_review_authorization_policy() -> dict[str, Any]:
    return {
        "review_result_present": False,
        "manual_review_gate_open": False,
        "manual_review_completed": False,
        "review_decision_allows_use": False,
        "review_decision_allows_trust_upgrade": False,
        "review_decision_allows_trading_interpretation": False,
        "review_decision_allows_order_creation": False,
        "review_decision_allows_order_approval": False,
        "review_decision_allows_broker_call": False,
    }


def _build_mock_review_trading_separation_policy() -> dict[str, Any]:
    return {
        "sandbox_review_is_not_trading_signal": True,
        "sandbox_review_cannot_create_pending_order": True,
        "sandbox_review_cannot_approve_order": True,
        "sandbox_review_cannot_submit_order": True,
        "sandbox_review_cannot_modify_risk": True,
        "sandbox_review_cannot_call_broker": True,
    }


def _build_mock_review_broker_separation_policy() -> dict[str, Any]:
    return {
        "broker_live_bridge_allowed": False,
        "broker_adapter_access_allowed": False,
        "order_routing_allowed": False,
        "approval_manager_access_allowed": False,
        "risk_manager_access_allowed": False,
    }


def _build_real_provider_review_boundary_policy() -> dict[str, Any]:
    return {
        "real_provider_response_reviewed": False,
        "real_provider_response_imported": False,
        "real_provider_response_received": False,
        "real_provider_review_allowed": False,
        "real_provider_review_requires_future_command": True,
        "real_provider_review_requires_future_redaction": True,
        "real_provider_review_requires_future_policy": True,
    }


def _build_network_boundary_policy() -> dict[str, Any]:
    return {
        "network_enabled": False,
        "network_call_attempted": False,
        "http_client_imported": False,
        "provider_network_call_allowed": False,
    }


def _build_credential_boundary_policy() -> dict[str, Any]:
    return {
        "credentials_loaded": False,
        "credential_value_present": False,
        "credential_lookup_attempted": False,
        "env_read_attempted": False,
        "dotenv_loaded": False,
    }


def _build_side_effect_policy() -> dict[str, Any]:
    return {
        "filesystem_side_effects_limited_to_artifacts": True,
        "summary_commands_write_artifacts": False,
        "doctor_commands_write_artifacts": False,
        "mock_review_sandbox_writes_only_review_sandbox_artifact": True,
        "mock_review_sandbox_writes_events": True,
        "mock_review_sandbox_touches_broker": False,
    }


def _build_denylist_metadata() -> dict[str, Any]:
    return {
        "denylist_profile": "atlas_provider_mock_response_review_sandbox_v1",
        "forbidden_fragment_count": len(FORBIDDEN_FRAGMENTS),
        "forbidden_fragments_raw_stored": False,
    }


def build_provider_mock_response_review_sandbox_dict(
    source_mock_import_candidate: dict[str, Any],
    source_mock_response_simulation: dict[str, Any],
    source_adapter_interface_contract: dict[str, Any],
    source_unlock_state: dict[str, Any],
    source_review_result: dict[str, Any],
    source_schema_contract: dict[str, Any],
    source_pairing: dict[str, Any],
    source_intake_policy: dict[str, Any],
    source_preview: dict[str, Any],
    sandbox_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(sandbox_id, "provider_mock_response_review_sandbox_id")

    src_import_candidate_id = source_mock_import_candidate.get("provider_mock_response_import_candidate_id", "")
    validate_contract_lineage_id(src_import_candidate_id, "source_provider_mock_response_import_candidate_id")

    src_mock_simulation_id = source_mock_response_simulation.get("provider_mock_response_simulation_id", "")
    validate_contract_lineage_id(src_mock_simulation_id, "source_provider_mock_response_simulation_id")

    src_adapter_contract_id = source_adapter_interface_contract.get("provider_adapter_interface_contract_id", "")
    validate_contract_lineage_id(src_adapter_contract_id, "source_provider_adapter_interface_contract_id")

    src_unlock_state_id = source_unlock_state.get("provider_execution_unlock_state_id", "")
    validate_contract_lineage_id(src_unlock_state_id, "source_provider_execution_unlock_state_id")

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

    # Propagate upstream lineage from payload preview through unlock state
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
    safe_model_id = validate_model_id(source_preview.get("model_id", ""))

    created_at = datetime.now(UTC)
    artifact_path_rel = f".atlas/research/{symbol}/provider_mock_response_review_sandboxes/{sandbox_id}.json"

    mock_review_source_summary = _build_mock_review_source_summary()
    mock_review_check_summary = _build_mock_review_check_summary()
    mock_review_boundary_policy = _build_mock_review_boundary_policy()
    mock_review_storage_policy = _build_mock_review_storage_policy()
    mock_review_trust_policy = _build_mock_review_trust_policy()
    mock_review_authorization_policy = _build_mock_review_authorization_policy()
    mock_review_trading_separation_policy = _build_mock_review_trading_separation_policy()
    mock_review_broker_separation_policy = _build_mock_review_broker_separation_policy()
    real_provider_review_boundary_policy = _build_real_provider_review_boundary_policy()
    network_boundary_policy = _build_network_boundary_policy()
    credential_boundary_policy = _build_credential_boundary_policy()
    side_effect_policy = _build_side_effect_policy()
    denylist_metadata = _build_denylist_metadata()

    required_prerequisites = [
        "provider_opt_in_policy_recorded",
        "credential_boundary_recorded",
        "payload_preview_recorded",
        "response_intake_policy_recorded",
        "request_response_pairing_recorded",
        "response_schema_contract_recorded",
        "response_review_result_contract_recorded",
        "provider_execution_unlock_state_recorded",
        "provider_adapter_interface_contract_recorded",
        "provider_mock_response_simulation_recorded",
        "provider_mock_response_import_candidate_recorded",
        "manual_unlock_policy_required",
        "credential_loader_policy_required_in_future",
        "provider_adapter_required_in_future",
        "network_policy_required_in_future",
        "real_response_artifact_required_in_future",
        "trust_upgrade_policy_required_in_future",
        "mock_review_sandbox_recorded",
    ]

    satisfied_prerequisites = [
        "provider_opt_in_policy_recorded",
        "credential_boundary_recorded",
        "payload_preview_recorded",
        "response_intake_policy_recorded",
        "request_response_pairing_recorded",
        "response_schema_contract_recorded",
        "response_review_result_contract_recorded",
        "provider_execution_unlock_state_recorded",
        "provider_adapter_interface_contract_recorded",
        "provider_mock_response_simulation_recorded",
        "provider_mock_response_import_candidate_recorded",
        "mock_review_sandbox_recorded",
        "mock_review_source_verified",
        "mock_review_checks_completed",
        "mock_review_passed",
        "mock_only",
        "sandbox_review_only",
    ]

    missing_prerequisites = [
        "manual_unlock_not_granted",
        "credential_loader_not_implemented",
        "real_provider_adapter_not_implemented",
        "network_policy_not_implemented",
        "real_provider_response_artifact_missing",
        "trust_upgrade_policy_not_implemented",
        "provider_sdk_policy_not_implemented",
        "real_provider_response_review_not_enabled",
        "real_provider_response_import_not_enabled",
    ]

    blocking_reasons = [
        "provider_execution_disabled",
        "manual_unlock_required",
        "real_provider_adapter_missing",
        "provider_sdk_not_imported",
        "credentials_not_loaded",
        "network_disabled",
        "real_response_missing",
        "trust_upgrade_missing",
        "broker_bridge_disabled",
        "real_provider_response_review_not_enabled",
        "real_provider_response_import_not_enabled",
    ]

    warnings = [
        "This is a local provider mock response review sandbox. No real provider response was reviewed.",
        "No provider request was sent.",
        "No provider response was received.",
        "No provider response is trusted by default.",
        "Provider execution remains disabled and not implemented.",
        "Manual unlock is required but not granted.",
        "Provider adapter is not implemented. Only mock adapter harness exists.",
        "Credential loader is not implemented.",
        "Network policy is not implemented.",
        "Real provider response artifact is missing.",
        "Trust upgrade policy is not implemented.",
        "Provider SDK is not imported.",
        "Mock review sandbox cannot generate order-simulation signals, approvals, or pending orders.",
        "Mock review sandbox cannot interact with broker.",
        "Real provider response review is not enabled.",
        "Real provider response import is not enabled.",
    ]

    metadata = {
        "source_mock_import_candidate_schema_version": source_mock_import_candidate.get("schema_version", ""),
        "source_mock_import_candidate_contract_version": source_mock_import_candidate.get("contract_version", ""),
        "source_mock_response_simulation_schema_version": source_mock_response_simulation.get("schema_version", ""),
        "source_mock_response_simulation_contract_version": source_mock_response_simulation.get("contract_version", ""),
        "source_adapter_interface_contract_schema_version": source_adapter_interface_contract.get("schema_version", ""),
        "source_adapter_interface_contract_contract_version": source_adapter_interface_contract.get("contract_version", ""),
        "source_unlock_state_schema_version": source_unlock_state.get("schema_version", ""),
        "source_unlock_state_contract_version": source_unlock_state.get("contract_version", ""),
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

    source_mock_import_candidate_hash = source_mock_import_candidate.get("artifact_hash", "")
    source_mock_response_simulation_hash = source_mock_response_simulation.get("artifact_hash", "")
    source_adapter_interface_contract_hash = source_adapter_interface_contract.get("artifact_hash", "")
    source_unlock_state_hash = source_unlock_state.get("artifact_hash", "")
    source_review_result_hash = source_review_result.get("artifact_hash", "")
    source_schema_contract_hash = source_schema_contract.get("artifact_hash", "")
    source_pairing_hash = source_pairing.get("artifact_hash", "")
    source_response_intake_policy_hash = source_intake_policy.get("artifact_hash", "")
    source_payload_preview_hash = source_preview.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_mock_response_review_sandbox",
        "contract_version": PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION,
        "provider_mock_response_review_sandbox_id": sandbox_id,
        "source_provider_mock_response_import_candidate_id": src_import_candidate_id,
        "source_provider_mock_response_simulation_id": src_mock_simulation_id,
        "source_provider_adapter_interface_contract_id": src_adapter_contract_id,
        "source_provider_execution_unlock_state_id": src_unlock_state_id,
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
        "provider_id": "mock",
        "model_id": safe_model_id,
        "mock_review_sandbox_status": "mock_review_sandbox_recorded",
        "mock_review_sandbox_scope": "offline_mock_response_review_sandbox_only",
        "mock_review_sandbox_state": "mock_review_sandbox_recorded_untrusted",
        "mock_review_source_summary": mock_review_source_summary,
        "mock_review_check_summary": mock_review_check_summary,
        "mock_review_boundary_policy": mock_review_boundary_policy,
        "mock_review_storage_policy": mock_review_storage_policy,
        "mock_review_trust_policy": mock_review_trust_policy,
        "mock_review_authorization_policy": mock_review_authorization_policy,
        "mock_review_trading_separation_policy": mock_review_trading_separation_policy,
        "mock_review_broker_separation_policy": mock_review_broker_separation_policy,
        "real_provider_review_boundary_policy": real_provider_review_boundary_policy,
        "network_boundary_policy": network_boundary_policy,
        "credential_boundary_policy": credential_boundary_policy,
        "side_effect_policy": side_effect_policy,
        "required_prerequisites": required_prerequisites,
        "satisfied_prerequisites": satisfied_prerequisites,
        "missing_prerequisites": missing_prerequisites,
        "blocking_reasons": blocking_reasons,
        "source_mock_import_candidate_hash": source_mock_import_candidate_hash,
        "source_mock_response_simulation_hash": source_mock_response_simulation_hash,
        "source_adapter_interface_contract_hash": source_adapter_interface_contract_hash,
        "source_unlock_state_hash": source_unlock_state_hash,
        "source_review_result_hash": source_review_result_hash,
        "source_schema_contract_hash": source_schema_contract_hash,
        "source_pairing_hash": source_pairing_hash,
        "source_response_intake_policy_hash": source_response_intake_policy_hash,
        "source_payload_preview_hash": source_payload_preview_hash,
        "mock_review_sandbox_recorded": True,
        "mock_review_source_verified": True,
        "mock_review_checks_completed": True,
        "mock_review_passed": True,
        "mock_review_requires_manual_followup": True,
        "mock_only": True,
        "sandbox_review_only": True,
        "real_provider_response_reviewed": False,
        "real_provider_response_imported": False,
        "real_provider_response_received": False,
        "provider_response_received": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "review_result_present": False,
        "manual_review_gate_open": False,
        "manual_review_completed": False,
        "review_decision_allows_use": False,
        "review_decision_allows_trust_upgrade": False,
        "review_decision_allows_trading_interpretation": False,
        "review_decision_allows_order_creation": False,
        "review_decision_allows_order_approval": False,
        "review_decision_allows_broker_call": False,
        "future_response_schema_validated": False,
        "raw_response_body_stored": False,
        "raw_request_body_stored": False,
        "raw_prompt_body_stored": False,
        "raw_review_notes_stored": False,
        "provider_sdk_imported": False,
        "http_client_imported": False,
        "network_enabled": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
        "credential_value_present": False,
        "credential_lookup_attempted": False,
        "env_read_attempted": False,
        "dotenv_loaded": False,
        "provider_execution_unlocked": False,
        "manual_unlock_granted": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "outbound_request_sent": False,
        "trust_upgrade_performed": False,
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

    artifact["artifact_hash"] = provider_mock_response_review_sandbox_sha256(artifact)
    return artifact


def create_provider_mock_response_review_sandbox(
    workspace_path: Path,
    import_candidate_id: str,
) -> dict[str, Any]:
    safe_import_candidate_id = validate_run_id(import_candidate_id)

    from atlas_agent.research.provider_mock_response_import_candidate import (
        find_provider_mock_response_import_candidate_by_id,
        load_provider_mock_response_import_candidate,
    )

    import_candidate_path = find_provider_mock_response_import_candidate_by_id(workspace_path, safe_import_candidate_id)
    if import_candidate_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_import_candidate_missing")

    source_mock_import_candidate = load_provider_mock_response_import_candidate(import_candidate_path, workspace_path)

    # Enforce provider_id="mock" on source mock import candidate
    if source_mock_import_candidate.get("provider_id") != "mock":
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_import_candidate_provider_not_mock")

    src_mock_simulation_id = source_mock_import_candidate.get("source_provider_mock_response_simulation_id", "")
    from atlas_agent.research.provider_mock_response_simulation import (
        find_provider_mock_response_simulation_by_id,
        load_provider_mock_response_simulation,
    )

    simulation_path = find_provider_mock_response_simulation_by_id(workspace_path, src_mock_simulation_id)
    if simulation_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_mock_response_missing")

    source_mock_response_simulation = load_provider_mock_response_simulation(simulation_path, workspace_path)

    src_adapter_contract_id = source_mock_import_candidate.get("source_provider_adapter_interface_contract_id", "")
    from atlas_agent.research.provider_adapter_interface_contract import (
        find_provider_adapter_interface_contract_by_id,
        load_provider_adapter_interface_contract,
    )

    adapter_path = find_provider_adapter_interface_contract_by_id(workspace_path, src_adapter_contract_id)
    if adapter_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_adapter_interface_missing")

    source_adapter_interface_contract = load_provider_adapter_interface_contract(adapter_path, workspace_path)

    src_unlock_state_id = source_mock_import_candidate.get("source_provider_execution_unlock_state_id", "")
    from atlas_agent.research.provider_execution_unlock_state import (
        find_provider_execution_unlock_state_by_id,
        load_provider_execution_unlock_state,
    )

    unlock_state_path = find_provider_execution_unlock_state_by_id(workspace_path, src_unlock_state_id)
    if unlock_state_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_unlock_state_missing")

    source_unlock_state = load_provider_execution_unlock_state(unlock_state_path, workspace_path)

    src_review_result_id = source_mock_import_candidate.get("source_provider_response_review_result_id", "")
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )

    review_result_path = find_provider_response_review_result_by_id(workspace_path, src_review_result_id)
    if review_result_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_review_result_missing")

    source_review_result = load_provider_response_review_result(review_result_path, workspace_path)

    src_schema_contract_id = source_mock_import_candidate.get("source_provider_response_schema_contract_id", "")
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )

    schema_contract_path = find_provider_response_schema_contract_by_id(workspace_path, src_schema_contract_id)
    if schema_contract_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_schema_contract_missing")

    source_schema_contract = load_provider_response_schema_contract(schema_contract_path, workspace_path)

    src_pairing_id = source_mock_import_candidate.get("source_provider_request_response_pairing_id", "")
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )

    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, src_pairing_id)
    if pairing_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_pairing_missing")

    source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)

    src_intake_id = source_mock_import_candidate.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, src_intake_id)
    if intake_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_response_intake_missing")

    source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)

    src_preview_id = source_mock_import_candidate.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, src_preview_id)
    if preview_path is None:
        raise ResearchSessionError("provider_mock_response_review_sandbox_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    sandbox_id = generate_run_id()
    artifact = build_provider_mock_response_review_sandbox_dict(
        source_mock_import_candidate,
        source_mock_response_simulation,
        source_adapter_interface_contract,
        source_unlock_state,
        source_review_result,
        source_schema_contract,
        source_pairing,
        source_intake_policy,
        source_preview,
        sandbox_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    result_dir = workspace_path / RESEARCH_DIR / symbol / "provider_mock_response_review_sandboxes"
    result_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_mock_response_review_sandbox_created",
        "provider_mock_response_review_sandbox_id": sandbox_id,
        "source_provider_mock_response_import_candidate_id": safe_import_candidate_id,
        "source_provider_mock_response_simulation_id": src_mock_simulation_id,
        "source_provider_adapter_interface_contract_id": src_adapter_contract_id,
        "source_provider_execution_unlock_state_id": src_unlock_state_id,
        "source_provider_response_review_result_id": src_review_result_id,
        "source_provider_response_schema_contract_id": src_schema_contract_id,
        "source_provider_request_response_pairing_id": src_pairing_id,
        "source_provider_response_intake_policy_id": src_intake_id,
        "source_provider_outbound_payload_preview_id": src_preview_id,
        "provider_id": "mock",
        "mock_review_sandbox_recorded": True,
        "mock_review_source_verified": True,
        "mock_review_checks_completed": True,
        "mock_review_passed": True,
        "mock_review_requires_manual_followup": True,
        "mock_only": True,
        "sandbox_review_only": True,
        "real_provider_response_reviewed": False,
        "real_provider_response_imported": False,
        "real_provider_response_received": False,
        "provider_response_received": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "review_result_present": False,
        "manual_review_gate_open": False,
        "manual_review_completed": False,
        "review_decision_allows_use": False,
        "review_decision_allows_trust_upgrade": False,
        "review_decision_allows_trading_interpretation": False,
        "review_decision_allows_order_creation": False,
        "review_decision_allows_order_approval": False,
        "review_decision_allows_broker_call": False,
        "raw_response_body_stored": False,
        "raw_request_body_stored": False,
        "raw_prompt_body_stored": False,
        "raw_review_notes_stored": False,
        "provider_sdk_imported": False,
        "http_client_imported": False,
        "network_enabled": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
        "credential_lookup_attempted": False,
        "env_read_attempted": False,
        "dotenv_loaded": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "outbound_request_sent": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "artifact_path": artifact_path_rel,
        "warnings": [],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_mock_response_review_sandbox_{field_name}"
    return None


def safe_validate_provider_mock_response_review_sandbox_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_mock_response_review_sandbox_schema"

    if data.get("artifact_type") != "provider_mock_response_review_sandbox":
        return None, "provider_mock_response_review_sandbox_malformed"

    if data.get("contract_version") != PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION:
        return None, "provider_mock_response_review_sandbox_malformed"

    try:
        validate_mock_review_sandbox_status(data.get("mock_review_sandbox_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_review_sandbox_status"

    try:
        validate_mock_review_sandbox_scope(data.get("mock_review_sandbox_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_review_sandbox_status"

    try:
        validate_mock_review_sandbox_state(data.get("mock_review_sandbox_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_review_sandbox_status"

    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    if data.get("mode") != "paper":
        return None, "provider_mock_response_review_sandbox_malformed"

    lineage_field_names = [
        "provider_mock_response_review_sandbox_id",
        "source_provider_mock_response_import_candidate_id",
        "source_provider_mock_response_simulation_id",
        "source_provider_adapter_interface_contract_id",
        "source_provider_execution_unlock_state_id",
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
            return None, "invalid_provider_mock_response_review_sandbox_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_review_sandbox_lineage"

    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_review_sandbox_provider"
    if provider_id != "mock":
        return None, "invalid_provider_mock_response_review_sandbox_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_review_sandbox_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_mock_response_review_sandbox_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_mock_response_review_sandbox_hash_mismatch"

    # Semantic positive-claim validation across ALL policy fields
    policy_fields_for_positive_claim_check = [
        data.get("mock_review_source_summary", {}),
        data.get("mock_review_check_summary", {}),
        data.get("mock_review_boundary_policy", {}),
        data.get("mock_review_storage_policy", {}),
        data.get("mock_review_trust_policy", {}),
        data.get("mock_review_authorization_policy", {}),
        data.get("mock_review_trading_separation_policy", {}),
        data.get("mock_review_broker_separation_policy", {}),
        data.get("real_provider_review_boundary_policy", {}),
        data.get("network_boundary_policy", {}),
        data.get("credential_boundary_policy", {}),
        data.get("side_effect_policy", {}),
        data.get("blocking_reasons", []),
        data.get("required_prerequisites", []),
        data.get("satisfied_prerequisites", []),
        data.get("missing_prerequisites", []),
        data.get("warnings", []),
    ]
    if any(_has_unsafe_positive_claims(f) for f in policy_fields_for_positive_claim_check):
        return None, "provider_mock_response_review_sandbox_forbidden_review_claim"

    # Check status/scope/state for forbidden fragments
    policy_summaries = [
        data.get("mock_review_sandbox_status", ""),
        data.get("mock_review_sandbox_scope", ""),
        data.get("mock_review_sandbox_state", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_mock_response_review_sandbox_forbidden_review_claim"

    # Check policy fields for forbidden fragments
    policy_fields = [
        json.dumps(data.get("mock_review_source_summary", {})),
        json.dumps(data.get("mock_review_check_summary", {})),
        json.dumps(data.get("mock_review_boundary_policy", {})),
        json.dumps(data.get("mock_review_storage_policy", {})),
        json.dumps(data.get("mock_review_trust_policy", {})),
        json.dumps(data.get("mock_review_authorization_policy", {})),
        json.dumps(data.get("mock_review_trading_separation_policy", {})),
        json.dumps(data.get("mock_review_broker_separation_policy", {})),
        json.dumps(data.get("real_provider_review_boundary_policy", {})),
        json.dumps(data.get("network_boundary_policy", {})),
        json.dumps(data.get("credential_boundary_policy", {})),
        json.dumps(data.get("side_effect_policy", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("required_prerequisites", [])),
        json.dumps(data.get("satisfied_prerequisites", [])),
        json.dumps(data.get("missing_prerequisites", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in policy_fields):
        return None, "provider_mock_response_review_sandbox_malformed"

    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_mock_response_review_sandbox_malformed"

    if workspace_path is not None and not for_replay:
        source_import_candidate_id = data.get("source_provider_mock_response_import_candidate_id", "")
        if source_import_candidate_id:
            try:
                from atlas_agent.research.provider_mock_response_import_candidate import (
                    find_provider_mock_response_import_candidate_by_id,
                    load_provider_mock_response_import_candidate,
                )

                ic_path = find_provider_mock_response_import_candidate_by_id(workspace_path, source_import_candidate_id)
                if ic_path is None:
                    return None, "provider_mock_response_review_sandbox_source_import_candidate_missing"
                ic_data = load_provider_mock_response_import_candidate(ic_path, workspace_path)
                stored_ic_hash = data.get("source_mock_import_candidate_hash", "")
                actual_ic_hash = ic_data.get("artifact_hash", "")
                if stored_ic_hash != actual_ic_hash:
                    return None, "provider_mock_response_review_sandbox_source_import_candidate_hash_mismatch"
                # Also enforce source provider_id == "mock"
                if ic_data.get("provider_id") != "mock":
                    return None, "provider_mock_response_review_sandbox_source_import_candidate_provider_not_mock"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_import_candidate_missing"

        source_mock_simulation_id = data.get("source_provider_mock_response_simulation_id", "")
        if source_mock_simulation_id:
            try:
                from atlas_agent.research.provider_mock_response_simulation import (
                    find_provider_mock_response_simulation_by_id,
                    load_provider_mock_response_simulation,
                )

                ms_path = find_provider_mock_response_simulation_by_id(workspace_path, source_mock_simulation_id)
                if ms_path is None:
                    return None, "provider_mock_response_review_sandbox_source_mock_response_missing"
                ms_data = load_provider_mock_response_simulation(ms_path, workspace_path)
                stored_ms_hash = data.get("source_mock_response_simulation_hash", "")
                actual_ms_hash = ms_data.get("artifact_hash", "")
                if stored_ms_hash != actual_ms_hash:
                    return None, "provider_mock_response_review_sandbox_source_mock_response_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_mock_response_missing"

        source_adapter_contract_id = data.get("source_provider_adapter_interface_contract_id", "")
        if source_adapter_contract_id:
            try:
                from atlas_agent.research.provider_adapter_interface_contract import (
                    find_provider_adapter_interface_contract_by_id,
                    load_provider_adapter_interface_contract,
                )

                ac_path = find_provider_adapter_interface_contract_by_id(workspace_path, source_adapter_contract_id)
                if ac_path is None:
                    return None, "provider_mock_response_review_sandbox_source_adapter_interface_missing"
                ac_data = load_provider_adapter_interface_contract(ac_path, workspace_path)
                stored_ac_hash = data.get("source_adapter_interface_contract_hash", "")
                actual_ac_hash = ac_data.get("artifact_hash", "")
                if stored_ac_hash != actual_ac_hash:
                    return None, "provider_mock_response_review_sandbox_source_adapter_interface_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_adapter_interface_missing"

        source_unlock_state_id = data.get("source_provider_execution_unlock_state_id", "")
        if source_unlock_state_id:
            try:
                from atlas_agent.research.provider_execution_unlock_state import (
                    find_provider_execution_unlock_state_by_id,
                    load_provider_execution_unlock_state,
                )

                us_path = find_provider_execution_unlock_state_by_id(workspace_path, source_unlock_state_id)
                if us_path is None:
                    return None, "provider_mock_response_review_sandbox_source_unlock_state_missing"
                us_data = load_provider_execution_unlock_state(us_path, workspace_path)
                stored_us_hash = data.get("source_unlock_state_hash", "")
                actual_us_hash = us_data.get("artifact_hash", "")
                if stored_us_hash != actual_us_hash:
                    return None, "provider_mock_response_review_sandbox_source_unlock_state_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_unlock_state_missing"

        source_review_result_id = data.get("source_provider_response_review_result_id", "")
        if source_review_result_id:
            try:
                from atlas_agent.research.provider_response_review_result import (
                    find_provider_response_review_result_by_id,
                    load_provider_response_review_result,
                )

                rr_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
                if rr_path is None:
                    return None, "provider_mock_response_review_sandbox_source_review_result_missing"
                rr_data = load_provider_response_review_result(rr_path, workspace_path)
                stored_rr_hash = data.get("source_review_result_hash", "")
                actual_rr_hash = rr_data.get("artifact_hash", "")
                if stored_rr_hash != actual_rr_hash:
                    return None, "provider_mock_response_review_sandbox_source_review_result_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_review_result_missing"

        source_schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
        if source_schema_contract_id:
            try:
                from atlas_agent.research.provider_response_schema_contract import (
                    find_provider_response_schema_contract_by_id,
                    load_provider_response_schema_contract,
                )

                sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
                if sc_path is None:
                    return None, "provider_mock_response_review_sandbox_source_schema_contract_missing"
                sc_data = load_provider_response_schema_contract(sc_path, workspace_path)
                stored_sc_hash = data.get("source_schema_contract_hash", "")
                actual_sc_hash = sc_data.get("artifact_hash", "")
                if stored_sc_hash != actual_sc_hash:
                    return None, "provider_mock_response_review_sandbox_source_schema_contract_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_schema_contract_missing"

        source_pairing_id = data.get("source_provider_request_response_pairing_id", "")
        if source_pairing_id:
            try:
                from atlas_agent.research.provider_request_response_pairing import (
                    find_provider_request_response_pairing_by_id,
                    load_provider_request_response_pairing,
                )

                pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
                if pairing_path is None:
                    return None, "provider_mock_response_review_sandbox_source_pairing_missing"
                pairing_data = load_provider_request_response_pairing(pairing_path, workspace_path)
                stored_pairing_hash = data.get("source_pairing_hash", "")
                actual_pairing_hash = pairing_data.get("artifact_hash", "")
                if stored_pairing_hash != actual_pairing_hash:
                    return None, "provider_mock_response_review_sandbox_source_pairing_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_pairing_missing"

        source_intake_id = data.get("source_provider_response_intake_policy_id", "")
        if source_intake_id:
            try:
                from atlas_agent.research.provider_response_intake_policy import (
                    find_provider_response_intake_policy_by_id,
                    load_provider_response_intake_policy,
                )

                intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
                if intake_path is None:
                    return None, "provider_mock_response_review_sandbox_source_response_intake_missing"
                intake_data = load_provider_response_intake_policy(intake_path, workspace_path)
                stored_intake_hash = data.get("source_response_intake_policy_hash", "")
                actual_intake_hash = intake_data.get("artifact_hash", "")
                if stored_intake_hash != actual_intake_hash:
                    return None, "provider_mock_response_review_sandbox_source_response_intake_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_response_intake_missing"

        source_preview_id = data.get("source_provider_outbound_payload_preview_id", "")
        if source_preview_id:
            try:
                from atlas_agent.research.provider_outbound_payload_preview import (
                    find_provider_outbound_payload_preview_by_id,
                    load_provider_outbound_payload_preview,
                )

                preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
                if preview_path is None:
                    return None, "provider_mock_response_review_sandbox_source_payload_preview_missing"
                preview_data = load_provider_outbound_payload_preview(preview_path, workspace_path)
                stored_preview_hash = data.get("source_payload_preview_hash", "")
                actual_preview_hash = preview_data.get("artifact_hash", "")
                if stored_preview_hash != actual_preview_hash:
                    return None, "provider_mock_response_review_sandbox_source_payload_preview_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_review_sandbox_source_payload_preview_missing"

    cleaned = {k: v for k, v in data.items()}
    return cleaned, None


def validate_provider_mock_response_review_sandbox_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderMockResponseReviewSandboxValidationResult:
    data = load_provider_mock_response_review_sandbox(path, workspace_path)
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
            at == "provider_mock_response_review_sandbox",
            "artifact_type must be provider_mock_response_review_sandbox." if at != "provider_mock_response_review_sandbox" else "artifact_type is correct.",
        )
    )

    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION,
            "contract_version must match current contract." if cv != PROVIDER_MOCK_RESPONSE_REVIEW_SANDBOX_VERSION else "contract_version matches.",
        )
    )

    status = data.get("mock_review_sandbox_status", "")
    status_ok = status in _VALID_MOCK_REVIEW_SANDBOX_STATUSES
    checks.append(
        _check_name(
            "mock_review_sandbox_status_valid",
            status_ok,
            "mock_review_sandbox_status is invalid." if not status_ok else "mock_review_sandbox_status is valid.",
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

    computed = provider_mock_response_review_sandbox_sha256(data)
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

    return ProviderMockResponseReviewSandboxValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation="Proceed with mock review sandbox review." if valid else "Reject artifact and investigate tampering.",
        warnings=warnings,
    )


def load_provider_mock_response_review_sandbox(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        raise ResearchSessionError("provider_mock_response_review_sandbox_malformed") from e

    cleaned, err = safe_validate_provider_mock_response_review_sandbox_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    if not cleaned:
        raise ResearchSessionError("provider_mock_response_review_sandbox_malformed")
    return cleaned


def load_and_validate_provider_mock_response_review_sandbox(path: Path, workspace_path: Path) -> dict[str, Any]:
    data = load_provider_mock_response_review_sandbox(path, workspace_path)
    res = validate_provider_mock_response_review_sandbox_artifact(path, workspace_path)
    if not res.valid:
        raise ResearchSessionError("invalid_provider_mock_response_review_sandbox_artifact")
    return data


def find_provider_mock_response_review_sandbox_by_id(workspace_path: Path, sandbox_id: str) -> Path | None:
    safe_id = validate_run_id(sandbox_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    for p in search_dir.rglob("provider_mock_response_review_sandboxes/*.json"):
        if p.stem == safe_id:
            return p
    return None


def replay_provider_mock_response_review_sandbox(
    workspace_path: Path,
    sandbox_id: str,
) -> dict[str, Any]:
    safe_id = validate_run_id(sandbox_id)
    artifact_path = find_provider_mock_response_review_sandbox_by_id(workspace_path, safe_id)
    if not artifact_path:
        raise ResearchSessionError("provider_mock_response_review_sandbox_not_found")

    try:
        old_artifact = load_provider_mock_response_review_sandbox(artifact_path, workspace_path=None)
    except ResearchSessionError:
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            old_hash = raw.get("artifact_hash", "")
        except Exception:
            old_hash = ""
        return {
            "ok": False,
            "match": False,
            "provider_mock_response_review_sandbox_id": safe_id,
            "original_hash": old_hash,
            "replayed_hash": "",
            "status": "research_provider_mock_response_review_sandbox_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    source_import_candidate_id = old_artifact.get("source_provider_mock_response_import_candidate_id", "")
    from atlas_agent.research.provider_mock_response_import_candidate import (
        find_provider_mock_response_import_candidate_by_id,
        load_provider_mock_response_import_candidate,
    )

    ic_path = find_provider_mock_response_import_candidate_by_id(workspace_path, source_import_candidate_id)
    if not ic_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_mock_import_candidate = load_provider_mock_response_import_candidate(ic_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    source_mock_simulation_id = old_artifact.get("source_provider_mock_response_simulation_id", "")
    from atlas_agent.research.provider_mock_response_simulation import (
        find_provider_mock_response_simulation_by_id,
        load_provider_mock_response_simulation,
    )

    ms_path = find_provider_mock_response_simulation_by_id(workspace_path, source_mock_simulation_id)
    if not ms_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_mock_response_simulation = load_provider_mock_response_simulation(ms_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    source_adapter_contract_id = old_artifact.get("source_provider_adapter_interface_contract_id", "")
    from atlas_agent.research.provider_adapter_interface_contract import (
        find_provider_adapter_interface_contract_by_id,
        load_provider_adapter_interface_contract,
    )

    ac_path = find_provider_adapter_interface_contract_by_id(workspace_path, source_adapter_contract_id)
    if not ac_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_adapter_interface_contract = load_provider_adapter_interface_contract(ac_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    source_unlock_state_id = old_artifact.get("source_provider_execution_unlock_state_id", "")
    from atlas_agent.research.provider_execution_unlock_state import (
        find_provider_execution_unlock_state_by_id,
        load_provider_execution_unlock_state,
    )

    us_path = find_provider_execution_unlock_state_by_id(workspace_path, source_unlock_state_id)
    if not us_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_unlock_state = load_provider_execution_unlock_state(us_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    source_review_result_id = old_artifact.get("source_provider_response_review_result_id", "")
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )

    rr_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
    if not rr_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_review_result = load_provider_response_review_result(rr_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    source_schema_contract_id = old_artifact.get("source_provider_response_schema_contract_id", "")
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )

    sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
    if not sc_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_schema_contract = load_provider_response_schema_contract(sc_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    source_pairing_id = old_artifact.get("source_provider_request_response_pairing_id", "")
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )

    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
    if not pairing_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    source_intake_id = old_artifact.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
    if not intake_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    source_preview_id = old_artifact.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if not preview_path:
        return _replay_failure_envelope(safe_id, old_artifact)

    try:
        source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)
    except ResearchSessionError:
        return _replay_failure_envelope(safe_id, old_artifact)

    new_artifact = build_provider_mock_response_review_sandbox_dict(
        source_mock_import_candidate,
        source_mock_response_simulation,
        source_adapter_interface_contract,
        source_unlock_state,
        source_review_result,
        source_schema_contract,
        source_pairing,
        source_intake_policy,
        source_preview,
        safe_id,
        workspace_path,
    )

    new_artifact["created_at"] = old_artifact.get("created_at", new_artifact["created_at"])
    new_artifact["artifact_hash"] = provider_mock_response_review_sandbox_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_mock_response_review_sandbox_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_mock_response_review_sandbox_replayed",
        "provider_response_received": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "broker_touched": False,
    }


def _replay_failure_envelope(safe_id: str, old_artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "match": False,
        "provider_mock_response_review_sandbox_id": safe_id,
        "original_hash": old_artifact.get("artifact_hash", ""),
        "replayed_hash": "",
        "status": "research_provider_mock_response_review_sandbox_replay_failed",
        "provider_response_received": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "broker_touched": False,
    }


def iter_provider_mock_response_review_sandbox_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    items: list[dict[str, Any]] = []
    invalid_items: list[dict[str, Any]] = []

    symbol_dirs = [research_dir / symbol] if symbol else research_dir.iterdir()

    for sym_dir in symbol_dirs:
        if not sym_dir.is_dir():
            continue
        result_dir = sym_dir / "provider_mock_response_review_sandboxes"
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
                    "provider_mock_response_review_sandbox_id": "<invalid>",
                    "source_provider_mock_response_import_candidate_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "mock_review_sandbox_status": "invalid",
                    "mock_review_sandbox_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_mock_response_review_sandbox_artifact",
                    "created_at": "",
                })
                continue
            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_mock_response_review_sandbox_id": "<invalid>",
                    "source_provider_mock_response_import_candidate_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "mock_review_sandbox_status": "invalid",
                    "mock_review_sandbox_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_mock_response_review_sandbox_artifact",
                    "created_at": "",
                })
                continue
            cleaned, error = safe_validate_provider_mock_response_review_sandbox_data(raw, workspace_path=workspace_path)
            if error or cleaned is None:
                invalid_items.append({
                    "provider_mock_response_review_sandbox_id": "<invalid>",
                    "source_provider_mock_response_import_candidate_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "mock_review_sandbox_status": "invalid",
                    "mock_review_sandbox_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_mock_response_review_sandbox_artifact",
                    "created_at": "",
                })
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append({
                "provider_mock_response_review_sandbox_id": cleaned.get("provider_mock_response_review_sandbox_id", path.stem),
                "source_provider_mock_response_import_candidate_id": cleaned.get("source_provider_mock_response_import_candidate_id", ""),
                "source_provider_mock_response_simulation_id": cleaned.get("source_provider_mock_response_simulation_id", ""),
                "source_provider_adapter_interface_contract_id": cleaned.get("source_provider_adapter_interface_contract_id", ""),
                "source_provider_execution_unlock_state_id": cleaned.get("source_provider_execution_unlock_state_id", ""),
                "source_provider_response_review_result_id": cleaned.get("source_provider_response_review_result_id", ""),
                "source_provider_response_schema_contract_id": cleaned.get("source_provider_response_schema_contract_id", ""),
                "source_provider_request_response_pairing_id": cleaned.get("source_provider_request_response_pairing_id", ""),
                "source_provider_response_intake_policy_id": cleaned.get("source_provider_response_intake_policy_id", ""),
                "source_provider_outbound_payload_preview_id": cleaned.get("source_provider_outbound_payload_preview_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "mock_review_sandbox_status": cleaned.get("mock_review_sandbox_status", ""),
                "mock_review_sandbox_scope": cleaned.get("mock_review_sandbox_scope", ""),
                "mock_review_sandbox_state": cleaned.get("mock_review_sandbox_state", ""),
                "artifact_path": rel_path,
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "created_at": cleaned.get("created_at", ""),
                "mock_review_sandbox_recorded": cleaned.get("mock_review_sandbox_recorded", True),
                "mock_review_source_verified": cleaned.get("mock_review_source_verified", True),
                "mock_review_checks_completed": cleaned.get("mock_review_checks_completed", True),
                "mock_review_passed": cleaned.get("mock_review_passed", True),
                "mock_only": cleaned.get("mock_only", True),
                "sandbox_review_only": cleaned.get("sandbox_review_only", True),
                "real_provider_response_reviewed": cleaned.get("real_provider_response_reviewed", False),
                "provider_response_trusted": cleaned.get("provider_response_trusted", False),
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


def _find_latest_provider_mock_response_review_sandbox_for_run(workspace_path: Path, run_id: str) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    latest_path: Path | None = None
    latest_time = ""
    for p in search_dir.rglob("provider_mock_response_review_sandboxes/*.json"):
        try:
            data = load_provider_mock_response_review_sandbox(p, workspace_path=None)
            if data.get("source_run_id") == safe_run_id:
                t = data.get("created_at", "")
                if not latest_time or t > latest_time:
                    latest_time = t
                    latest_path = p
        except Exception:
            pass
    return latest_path


def summarize_provider_mock_response_review_sandbox(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_mock_response_review_sandbox_for_run(workspace_path, safe_run_id)

    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_mock_response_review_sandbox",
            "provider_mock_response_review_sandbox_id": None,
            "mock_review_sandbox_status": "not_recorded",
            "mock_review_sandbox_state": "not_recorded",
            "mock_review_sandbox_recorded": False,
            "mock_only": True,
            "sandbox_review_only": True,
            "real_provider_response_reviewed": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
            "artifact_path": None,
        }

    try:
        data = load_and_validate_provider_mock_response_review_sandbox(artifact_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": True,
            "status": "invalid_provider_mock_response_review_sandbox",
            "provider_mock_response_review_sandbox_id": None,
            "mock_review_sandbox_status": "invalid",
            "mock_review_sandbox_state": "invalid",
            "mock_review_sandbox_recorded": False,
            "mock_only": True,
            "sandbox_review_only": True,
            "real_provider_response_reviewed": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
            "artifact_path": None,
        }

    return {
        "ok": True,
        "status": "research_provider_mock_response_review_sandbox_summary",
        "provider_mock_response_review_sandbox_id": data.get("provider_mock_response_review_sandbox_id"),
        "mock_review_sandbox_status": data.get("mock_review_sandbox_status"),
        "mock_review_sandbox_state": data.get("mock_review_sandbox_state"),
        "mock_review_sandbox_recorded": True,
        "mock_review_passed": True,
        "mock_only": True,
        "sandbox_review_only": True,
        "real_provider_response_reviewed": False,
        "provider_response_trusted": False,
        "provider_call_allowed": False,
        "broker_touched": False,
        "artifact_path": data.get("artifact_path"),
    }


def doctor_provider_mock_response_review_sandbox(
    workspace_path: Path,
    run_id: str,
) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)

    missing_artifacts: list[str] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    sandbox_path = _find_latest_provider_mock_response_review_sandbox_for_run(workspace_path, safe_run_id)
    if not sandbox_path:
        missing_artifacts.append("provider_mock_response_review_sandbox")
        blocking_reasons.append("provider_mock_response_review_sandbox_not_created")
        warnings.append("No provider mock response review sandbox exists for this run.")
        return {
            "ok": True,
            "status": "research_provider_mock_response_review_sandbox_doctor",
            "run_id": safe_run_id,
            "mock_review_health": "mock_review_sandbox_missing",
            "mock_review_sandbox_recorded": False,
            "mock_only": True,
            "sandbox_review_only": True,
            "real_provider_response_reviewed": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "missing_prerequisites": missing_artifacts,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
        }

    try:
        data = load_provider_mock_response_review_sandbox(sandbox_path, workspace_path)
    except ResearchSessionError as e:
        warnings.append(f"Mock review sandbox artifact is invalid: {e}")
        return {
            "ok": True,
            "status": "research_provider_mock_response_review_sandbox_doctor",
            "run_id": safe_run_id,
            "mock_review_health": "mock_review_sandbox_invalid",
            "mock_review_sandbox_recorded": False,
            "mock_only": True,
            "sandbox_review_only": True,
            "real_provider_response_reviewed": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "missing_prerequisites": missing_artifacts,
            "blocking_reasons": ["mock_review_sandbox_artifact_invalid"],
            "warnings": warnings,
        }

    # Check source artifacts
    import_candidate_id = data.get("source_provider_mock_response_import_candidate_id", "")
    mock_simulation_id = data.get("source_provider_mock_response_simulation_id", "")
    unlock_state_id = data.get("source_provider_execution_unlock_state_id", "")
    review_result_id = data.get("source_provider_response_review_result_id", "")
    schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
    pairing_id = data.get("source_provider_request_response_pairing_id", "")
    intake_id = data.get("source_provider_response_intake_policy_id", "")
    preview_id = data.get("source_provider_outbound_payload_preview_id", "")
    adapter_contract_id = data.get("source_provider_adapter_interface_contract_id", "")

    from atlas_agent.research.provider_mock_response_import_candidate import find_provider_mock_response_import_candidate_by_id
    from atlas_agent.research.provider_mock_response_simulation import find_provider_mock_response_simulation_by_id
    from atlas_agent.research.provider_execution_unlock_state import find_provider_execution_unlock_state_by_id
    from atlas_agent.research.provider_response_review_result import find_provider_response_review_result_by_id
    from atlas_agent.research.provider_response_schema_contract import find_provider_response_schema_contract_by_id
    from atlas_agent.research.provider_request_response_pairing import find_provider_request_response_pairing_by_id
    from atlas_agent.research.provider_response_intake_policy import find_provider_response_intake_policy_by_id
    from atlas_agent.research.provider_outbound_payload_preview import find_provider_outbound_payload_preview_by_id
    from atlas_agent.research.provider_adapter_interface_contract import find_provider_adapter_interface_contract_by_id

    if adapter_contract_id:
        ac_path = find_provider_adapter_interface_contract_by_id(workspace_path, adapter_contract_id)
        if not ac_path:
            missing_artifacts.append("source_provider_adapter_interface_contract")
    else:
        missing_artifacts.append("source_provider_adapter_interface_contract")

    if unlock_state_id:
        us_path = find_provider_execution_unlock_state_by_id(workspace_path, unlock_state_id)
        if not us_path:
            missing_artifacts.append("source_provider_execution_unlock_state")
    else:
        missing_artifacts.append("source_provider_execution_unlock_state")

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

    if mock_simulation_id:
        ms_path = find_provider_mock_response_simulation_by_id(workspace_path, mock_simulation_id)
        if not ms_path:
            missing_artifacts.append("source_provider_mock_response_simulation")
    else:
        missing_artifacts.append("source_provider_mock_response_simulation")

    if import_candidate_id:
        ic_path = find_provider_mock_response_import_candidate_by_id(workspace_path, import_candidate_id)
        if not ic_path:
            missing_artifacts.append("source_provider_mock_response_import_candidate")
    else:
        missing_artifacts.append("source_provider_mock_response_import_candidate")

    # Future prerequisites are expected to be missing
    missing_artifacts.extend([
        "real_provider_adapter_not_implemented",
        "provider_sdk_policy_not_implemented",
        "credential_loader_not_implemented",
        "network_policy_not_implemented",
        "real_provider_response_artifact_missing",
        "trust_upgrade_policy_not_implemented",
        "real_provider_response_review_not_enabled",
        "real_provider_response_import_not_enabled",
    ])
    warnings.append("Future prerequisites are missing. This is expected in this batch.")

    if data.get("mock_review_sandbox_state") == "mock_review_sandbox_recorded_untrusted":
        mock_review_health = "mock_review_sandbox_recorded_untrusted"
    else:
        mock_review_health = "blocked"

    blocking_reasons.extend([
        "provider_execution_disabled",
        "manual_unlock_required",
        "real_provider_adapter_missing",
        "provider_sdk_not_imported",
        "credentials_not_loaded",
        "network_disabled",
        "real_response_missing",
        "trust_upgrade_missing",
        "broker_bridge_disabled",
        "real_provider_response_review_not_enabled",
        "real_provider_response_import_not_enabled",
    ])

    return {
        "ok": True,
        "status": "research_provider_mock_response_review_sandbox_doctor",
        "run_id": safe_run_id,
        "mock_review_health": mock_review_health,
        "mock_review_sandbox_recorded": True,
        "mock_only": True,
        "sandbox_review_only": True,
        "real_provider_response_reviewed": False,
        "provider_response_trusted": False,
        "provider_call_allowed": False,
        "missing_prerequisites": missing_artifacts,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }
