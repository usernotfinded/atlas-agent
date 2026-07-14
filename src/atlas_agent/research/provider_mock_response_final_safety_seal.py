# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_mock_response_final_safety_seal.py
# PURPOSE: Mock pipeline, TERMINAL node: the final safety seal. Nothing downstream may
#          consume a mock response that does not carry this seal.
# DEPS:    research.provider_mock_response_import_candidate, research.sandbox_contracts
# ==============================================================================

"""Provider mock response final safety seal — terminal node in the mock response pipeline.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider mock response final safety seal artifacts. It does NOT implement any real trust
decision, does NOT upgrade trust, does NOT grant manual approval, does NOT review raw provider
responses, does NOT read external files, does NOT accept stdin input, does NOT call any real
provider, does NOT perform network requests, does NOT read API keys, does NOT read os.environ,
does NOT load .env.atlas, does NOT import provider SDKs, does NOT receive real provider responses,
does NOT trust provider responses, does NOT trust mock responses, does NOT create trading signals,
does NOT create approvals or pending orders, does NOT authorize live trading, and does NOT touch
brokers.

A provider mock response final safety seal is derived ONLY from an existing
provider_mock_response_trust_decision_blocker artifact. It represents a terminal red-light
artifact that explicitly records the completion of the mock pipeline with the final safety
seal applied, while maintaining all trust-blocking and non-authorizing guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.events.log import generate_run_id
from atlas_agent.research.artifact_engine import (
    ArtifactSpec,
    artifact_sha256,
    build_artifact_path,
    list_artifact_json_paths,
    load_json_object,
    save_json_object,
)
from atlas_agent.research.sandbox_contracts import (
    FORBIDDEN_FRAGMENTS,
    MAX_CONTRACT_TEXT_CHARS,
    _has_forbidden_fragments,
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
from atlas_agent.research.provider_mock_response_trust_decision_blocker import (
    find_provider_mock_response_trust_decision_blocker_by_id,
    load_provider_mock_response_trust_decision_blocker,
    provider_mock_response_trust_decision_blocker_sha256,
)

PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_VERSION = "research_provider_mock_response_final_safety_seal_v1"

_PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_SPEC = ArtifactSpec(
    artifact_type="provider_mock_response_final_safety_seal",
    artifact_directory="provider_mock_response_final_safety_seals",
    hash_excluded_fields=frozenset(_PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_HASH_EXCLUDED_FIELDS),
)

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_FINAL_SAFETY_SEAL_STATUSES = {
    "final_safety_seal_recorded",
    "final_safety_seal_invalid",
}

_VALID_FINAL_SAFETY_SEAL_SCOPES = {
    "offline_mock_response_final_safety_seal_only",
}

_VALID_FINAL_SAFETY_SEAL_STATES = {
    "mock_pipeline_sealed",
    "trust_blocked_and_sealed",
    "sandbox_only_seal_valid",
    "non_authorizing_seal_active",
}

_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE = [
    "trust_decision_present",
    "trust_decision_granted",
    "trust_decision_denied",
    "trust_upgrade_available",
    "trust_upgrade_performed",
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
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
    "seal_authorizing",
    "seal_allows_execution",
    "seal_allows_trading",
    "live_trading_path_enabled",
    "broker_order_path_enabled",
]

_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE = [
    "final_safety_seal_created",
    "mock_pipeline_complete",
    "sandbox_only",
    "mock_only",
    "trust_decision_blocker_recorded",
    "trust_source_verified",
    "trust_blocker_active",
    "trust_decision_required",
    "trust_decision_explicitly_blocked",
    "seal_valid",
    "seal_non_authorizing",
]

_UNSAFE_POSITIVE_CLAIM_PHRASES = (
    "trust decision granted",
    "trust decision present",
    "trust upgrade performed",
    "trust upgrade available",
    "provider response trusted",
    "mock response trusted",
    "sandbox review trusted",
    "manual review completed",
    "review decision allows trading",
    "review decision allows order creation",
    "create order",
    "approve order",
    "call broker",
    "buy",
    "sell",
    "trading signal",
    "approval created",
    "pending order created",
    "broker touched",
    "real provider response trusted",
    "real provider response reviewed",
    "manual unlock granted",
    "provider call allowed",
    "network enabled",
    "credentials loaded",
    "api key loaded",
    "api call succeeded",
    "live trading authorized",
    "real provider adapter used",
    "real provider request sent",
    "seal authorizes",
    "seal approves",
    "seal permits execution",
    "final seal grants trust",
    "seal unlocks trading",
)


@dataclass(frozen=True)
class ProviderMockResponseFinalSafetySealValidationResult:
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
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_model")
    return value


def validate_final_safety_seal_status(value: str) -> str:
    if not value or value not in _VALID_FINAL_SAFETY_SEAL_STATUSES:
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_status")
    return value


def validate_final_safety_seal_scope(value: str) -> str:
    if not value or value not in _VALID_FINAL_SAFETY_SEAL_SCOPES:
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_status")
    return value


def validate_final_safety_seal_state(value: str) -> str:
    if not value or value not in _VALID_FINAL_SAFETY_SEAL_STATES:
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_final_safety_seal_status")
    return value


def provider_mock_response_final_safety_seal_sha256(data: dict[str, Any]) -> str:
    return artifact_sha256(data, _PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_SPEC)


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
        if data.get(flag) is not False:
            return "provider_mock_response_final_safety_seal_impossible_boolean"
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
        if data.get(flag) is not True:
            return "provider_mock_response_final_safety_seal_impossible_boolean"
    return None


def _build_seal_source_summary() -> dict[str, Any]:
    return {
        "source_artifact_type": "provider_mock_response_trust_decision_blocker",
        "source_provider_id": "mock",
        "source_is_mock": True,
        "source_is_real_provider_response": False,
        "source_trust_decision_blocker_recorded": True,
        "source_trust_decision_blocked": True,
        "source_trust_decision_granted": False,
        "source_provider_response_trusted": False,
        "source_can_create_orders": False,
        "source_can_call_broker": False,
    }


def _build_seal_summary() -> dict[str, Any]:
    return {
        "final_safety_seal_created": True,
        "mock_pipeline_complete": True,
        "seal_valid": True,
        "seal_non_authorizing": True,
        "trust_decision_blocker_recorded": True,
        "trust_blocker_active": True,
        "trust_decision_required": True,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_explicitly_blocked": True,
        "trust_upgrade_performed": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "manual_review_completed": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
    }


def _build_seal_decision_policy() -> dict[str, Any]:
    return {
        "mock_pipeline_sealed": True,
        "trust_blocked_and_sealed": True,
        "sandbox_only_seal_valid": True,
        "non_authorizing_seal_active": True,
        "seal_authorizing": False,
        "seal_allows_execution": False,
        "seal_allows_trading": False,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_explicitly_blocked": True,
    }


def _build_seal_upgrade_policy() -> dict[str, Any]:
    return {
        "trust_upgrade_available": False,
        "trust_upgrade_performed": False,
        "trust_upgrade_not_implemented": True,
        "seal_cannot_upgrade_trust": True,
        "mock_review_sandbox_cannot_upgrade_trust": True,
        "trust_upgrade_requires_future_design": True,
    }


def _build_manual_review_policy() -> dict[str, Any]:
    return {
        "manual_review_required": True,
        "manual_review_gate_open": False,
        "manual_review_completed": False,
        "review_result_present": False,
        "sandbox_review_does_not_complete_manual_review": True,
        "manual_review_required_before_future_trust_decision": True,
        "manual_review_cannot_be_inferred_from_mock": True,
    }


def _build_mock_response_trust_policy() -> dict[str, Any]:
    return {
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "sandbox_review_trusted": False,
        "mock_response_cannot_be_trusted_in_this_batch": True,
        "mock_response_cannot_be_trading_signal": True,
        "mock_response_cannot_create_orders": True,
        "mock_response_cannot_approve_orders": True,
        "mock_response_cannot_call_broker": True,
    }


def _build_real_provider_trust_boundary_policy() -> dict[str, Any]:
    return {
        "real_provider_response_received": False,
        "real_provider_response_imported": False,
        "real_provider_response_reviewed": False,
        "real_provider_response_trusted": False,
        "real_provider_trust_decision_allowed": False,
        "real_provider_trust_requires_future_policy": True,
    }


def _build_trading_authorization_policy() -> dict[str, Any]:
    return {
        "seal_is_not_trading_signal": True,
        "seal_cannot_create_pending_order": True,
        "seal_cannot_approve_order": True,
        "seal_cannot_submit_order": True,
        "seal_cannot_modify_risk": True,
        "seal_cannot_call_broker": True,
    }


def _build_broker_separation_policy() -> dict[str, Any]:
    return {
        "broker_live_bridge_allowed": False,
        "broker_adapter_access_allowed": False,
        "order_routing_allowed": False,
        "approval_manager_access_allowed": False,
        "risk_manager_access_allowed": False,
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
        "final_safety_seal_writes_only_seal_artifact": True,
        "final_safety_seal_writes_events": True,
        "final_safety_seal_touches_broker": False,
    }


def build_provider_mock_response_final_safety_seal_dict(
    source_trust_decision_blocker: dict[str, Any],
    seal_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(seal_id, "invalid_provider_mock_response_final_safety_seal_id")

    safe_symbol = validate_contract_symbol(source_trust_decision_blocker.get("symbol", "UNKNOWN"))
    safe_model_id = validate_model_id(source_trust_decision_blocker.get("model_id", "unknown"))
    safe_source_provider_id = validate_provider_id(source_trust_decision_blocker.get("source_provider_id", "mock"))

    now = datetime.now(UTC).isoformat()

    artifact_path = build_artifact_path(
        workspace_path,
        RESEARCH_DIR,
        safe_symbol,
        _PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_SPEC,
        seal_id,
    )

    final_safety_seal_status = "final_safety_seal_recorded"
    final_safety_seal_scope = "offline_mock_response_final_safety_seal_only"
    final_safety_seal_state = "mock_pipeline_sealed"

    artifact = {
        "artifact_type": "provider_mock_response_final_safety_seal",
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "contract_version": PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_VERSION,
        "provider_mock_response_final_safety_seal_id": seal_id,
        "seal_type": "mock_response_final_safety_seal",
        "source_trust_decision_blocker_id": source_trust_decision_blocker.get("provider_mock_response_trust_decision_blocker_id", ""),
        "source_trust_decision_blocker_hash": source_trust_decision_blocker.get("artifact_hash", ""),
        "source_run_id": source_trust_decision_blocker.get("source_run_id", ""),
        "symbol": safe_symbol,
        "mode": "paper",
        "provider_id": "mock",
        "model_id": safe_model_id,
        "source_provider_id": safe_source_provider_id,
        "final_safety_seal_status": final_safety_seal_status,
        "final_safety_seal_scope": final_safety_seal_scope,
        "final_safety_seal_state": final_safety_seal_state,
        "seal_source_summary": _build_seal_source_summary(),
        "seal_summary": _build_seal_summary(),
        "seal_decision_policy": _build_seal_decision_policy(),
        "seal_upgrade_policy": _build_seal_upgrade_policy(),
        "manual_review_policy": _build_manual_review_policy(),
        "mock_response_trust_policy": _build_mock_response_trust_policy(),
        "real_provider_trust_boundary_policy": _build_real_provider_trust_boundary_policy(),
        "trading_authorization_policy": _build_trading_authorization_policy(),
        "broker_separation_policy": _build_broker_separation_policy(),
        "network_boundary_policy": _build_network_boundary_policy(),
        "credential_boundary_policy": _build_credential_boundary_policy(),
        "side_effect_policy": _build_side_effect_policy(),
        "final_safety_seal_created": True,
        "mock_pipeline_complete": True,
        "sandbox_only": True,
        "mock_only": True,
        "trust_decision_blocker_recorded": True,
        "trust_source_verified": True,
        "trust_blocker_active": True,
        "trust_decision_required": True,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_denied": False,
        "trust_decision_explicitly_blocked": True,
        "trust_upgrade_available": False,
        "trust_upgrade_performed": False,
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
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
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
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "seal_authorizing": False,
        "seal_allows_execution": False,
        "seal_allows_trading": False,
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
        "seal_valid": True,
        "seal_non_authorizing": True,
        "artifact_hash": "",
        "created_at": now,
        "artifact_path": str(artifact_path.relative_to(workspace_path)),
        "warnings": [],
        "metadata": {
            "denylist_profile": "research_provider_mock_response_final_safety_seal",
            "forbidden_fragment_count": 0,
            "forbidden_fragments_raw_stored": False,
        },
    }
    artifact["artifact_hash"] = provider_mock_response_final_safety_seal_sha256(artifact)
    return artifact


def create_provider_mock_response_final_safety_seal(workspace_path: Path, blocker_id: str) -> dict[str, Any]:
    """Create a provider mock response final safety seal from a trust decision blocker artifact."""
    safe_blocker_id = validate_run_id(blocker_id)

    blocker_path = find_provider_mock_response_trust_decision_blocker_by_id(workspace_path, safe_blocker_id)
    if blocker_path is None:
        raise ResearchSessionError("provider_mock_response_final_safety_seal_source_trust_decision_blocker_missing")
    blocker = load_provider_mock_response_trust_decision_blocker(blocker_path, workspace_path)
    if blocker.get("provider_id") != "mock":
        raise ResearchSessionError("provider_mock_response_final_safety_seal_source_trust_decision_blocker_provider_not_mock")

    seal_id = generate_run_id()
    artifact = build_provider_mock_response_final_safety_seal_dict(
        source_trust_decision_blocker=blocker,
        seal_id=seal_id,
        workspace_path=workspace_path,
    )

    artifact_path = workspace_path / artifact["artifact_path"]
    save_json_object(artifact_path, artifact)

    return {
        "ok": True,
        "status": "research_provider_mock_response_final_safety_seal_created",
        "provider_mock_response_final_safety_seal_id": seal_id,
        "source_trust_decision_blocker_id": safe_blocker_id,
        "provider_id": "mock",
        "final_safety_seal_created": True,
        "mock_pipeline_complete": True,
        "seal_valid": True,
        "seal_non_authorizing": True,
        "trust_decision_blocker_recorded": True,
        "trust_source_verified": True,
        "trust_blocker_active": True,
        "trust_decision_required": True,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_denied": False,
        "trust_decision_explicitly_blocked": True,
        "trust_upgrade_available": False,
        "trust_upgrade_performed": False,
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
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
        "artifact_path": artifact["artifact_path"],
        "warnings": [],
    }


def load_provider_mock_response_final_safety_seal(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    data = load_json_object(path)
    cleaned, err = safe_validate_provider_mock_response_final_safety_seal_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    return cleaned


def safe_validate_provider_mock_response_final_safety_seal_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(data, dict):
        return None, "provider_mock_response_final_safety_seal_malformed"

    artifact_type = data.get("artifact_type", "")
    schema_version = data.get("schema_version", "")
    contract_version = data.get("contract_version", "")

    if artifact_type != "provider_mock_response_final_safety_seal":
        return None, "provider_mock_response_final_safety_seal_malformed"
    if schema_version != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_mock_response_final_safety_seal_schema"
    if contract_version != PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_VERSION:
        return None, "unsupported_provider_mock_response_final_safety_seal_schema"

    try:
        validate_contract_lineage_id(data.get("provider_mock_response_final_safety_seal_id", ""), "invalid_provider_mock_response_final_safety_seal_id")
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_final_safety_seal_id"

    lineage_fields = [
        "source_trust_decision_blocker_id",
        "source_run_id",
    ]
    for field in lineage_fields:
        try:
            validate_contract_lineage_id(data.get(field, ""), "invalid_provider_mock_response_final_safety_seal_lineage")
        except ResearchSessionError:
            return None, "invalid_provider_mock_response_final_safety_seal_lineage"

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_final_safety_seal_lineage"

    try:
        validate_provider_id(data.get("provider_id", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_final_safety_seal_provider"

    try:
        validate_model_id(data.get("model_id", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_final_safety_seal_model"

    try:
        validate_final_safety_seal_status(data.get("final_safety_seal_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_final_safety_seal_status"

    try:
        validate_final_safety_seal_scope(data.get("final_safety_seal_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_final_safety_seal_status"

    try:
        validate_final_safety_seal_state(data.get("final_safety_seal_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_final_safety_seal_status"

    impossible = _check_boolean_safety_flags(data)
    if impossible:
        return None, impossible

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_mock_response_final_safety_seal_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_mock_response_final_safety_seal_hash_mismatch"

    policy_fields_for_positive_claim_check = [
        data.get("seal_source_summary", {}),
        data.get("seal_summary", {}),
        data.get("seal_decision_policy", {}),
        data.get("seal_upgrade_policy", {}),
        data.get("manual_review_policy", {}),
        data.get("mock_response_trust_policy", {}),
        data.get("real_provider_trust_boundary_policy", {}),
        data.get("trading_authorization_policy", {}),
        data.get("broker_separation_policy", {}),
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
        return None, "provider_mock_response_final_safety_seal_forbidden_trust_claim"

    if workspace_path is not None and not for_replay:
        source_blocker_id = data.get("source_trust_decision_blocker_id", "")
        if source_blocker_id:
            blocker_path = find_provider_mock_response_trust_decision_blocker_by_id(workspace_path, source_blocker_id)
            if blocker_path is None:
                return None, "provider_mock_response_final_safety_seal_source_trust_decision_blocker_missing"
            blocker_data = load_provider_mock_response_trust_decision_blocker(blocker_path, workspace_path)
            stored_blocker_hash = data.get("source_trust_decision_blocker_hash", "")
            actual_blocker_hash = blocker_data.get("artifact_hash", "")
            if stored_blocker_hash and actual_blocker_hash and stored_blocker_hash != actual_blocker_hash:
                return None, "provider_mock_response_final_safety_seal_source_trust_decision_blocker_hash_mismatch"
            if blocker_data.get("provider_id") != "mock":
                return None, "provider_mock_response_final_safety_seal_source_trust_decision_blocker_provider_not_mock"

    artifact_path = data.get("artifact_path", "")
    if artifact_path and workspace_path is not None:
        abs_path = (workspace_path / artifact_path).resolve()
        if not _is_inside_workspace(abs_path, workspace_path):
            return None, "provider_mock_response_final_safety_seal_malformed"

    return dict(data), None


def validate_provider_mock_response_final_safety_seal_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderMockResponseFinalSafetySealValidationResult:
    data = load_provider_mock_response_final_safety_seal(path, workspace_path)
    checks: list[dict[str, Any]] = []

    sv = data.get("schema_version", "")
    checks.append(_check_name("schema_version_supported", sv == RESEARCH_ARTIFACT_SCHEMA_VERSION, f"schema_version={sv}"))

    at = data.get("artifact_type", "")
    checks.append(_check_name("artifact_type_correct", at == "provider_mock_response_final_safety_seal", f"artifact_type={at}"))

    cv = data.get("contract_version", "")
    checks.append(_check_name("contract_version_supported", cv == PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_VERSION, f"contract_version={cv}"))

    stored_hash = data.get("artifact_hash", "")
    computed_hash = provider_mock_response_final_safety_seal_sha256(data)
    checks.append(_check_name("artifact_hash_match", stored_hash == computed_hash, "hash mismatch"))

    pid = data.get("provider_id", "")
    checks.append(_check_name("provider_id_mock", pid == "mock", f"provider_id={pid}"))

    impossible = _check_boolean_safety_flags(data)
    checks.append(_check_name("boolean_safety_flags", impossible is None, impossible or "ok"))

    checks.append(_check_name(
        "no_forbidden_positive_claims",
        not any(_has_unsafe_positive_claims(data.get(f, {})) for f in [
            "seal_source_summary", "seal_summary", "seal_decision_policy", "seal_upgrade_policy",
            "manual_review_policy", "mock_response_trust_policy", "real_provider_trust_boundary_policy",
            "trading_authorization_policy", "broker_separation_policy", "network_boundary_policy",
            "credential_boundary_policy", "side_effect_policy",
        ]),
        "forbidden positive claim detected",
    ))

    checks.append(_check_name("artifact_path_inside_workspace", True, "ok"))

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    valid = failed == 0

    if strict and not valid:
        recommendation = "Validation failed in strict mode. Do not proceed."
    elif not valid:
        recommendation = "Validation failed. Review warnings and re-create the artifact."
    else:
        recommendation = "Artifact valid. Mock pipeline sealed. Seal is non-authorizing."

    return ProviderMockResponseFinalSafetySealValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=data.get("warnings", []),
    )


def replay_provider_mock_response_final_safety_seal(workspace_path: Path, seal_id: str) -> dict[str, Any]:
    safe_id = validate_run_id(seal_id)
    artifact_path = find_provider_mock_response_final_safety_seal_by_id(workspace_path, safe_id)
    if artifact_path is None:
        raise ResearchSessionError("provider_mock_response_final_safety_seal_not_found")

    old_artifact = load_provider_mock_response_final_safety_seal(artifact_path, workspace_path=None)

    source_blocker = load_provider_mock_response_trust_decision_blocker(
        find_provider_mock_response_trust_decision_blocker_by_id(workspace_path, old_artifact["source_trust_decision_blocker_id"]),
        workspace_path,
    )

    new_artifact = build_provider_mock_response_final_safety_seal_dict(
        source_trust_decision_blocker=source_blocker,
        seal_id=safe_id,
        workspace_path=workspace_path,
    )
    new_artifact["created_at"] = old_artifact.get("created_at", datetime.now(UTC).isoformat())
    new_artifact["artifact_hash"] = provider_mock_response_final_safety_seal_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_mock_response_final_safety_seal_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_mock_response_final_safety_seal_replayed",
        "final_safety_seal_created": True,
        "mock_pipeline_complete": True,
        "seal_valid": True,
        "seal_non_authorizing": True,
        "trust_decision_blocker_recorded": True,
        "trust_blocker_active": True,
        "trust_decision_required": True,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_explicitly_blocked": True,
        "trust_upgrade_performed": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "provider_call_allowed": False,
        "broker_touched": False,
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
    }


def _find_latest_provider_mock_response_final_safety_seal_for_run(
    workspace_path: Path, run_id: str
) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    items = iter_provider_mock_response_final_safety_seal_artifacts(workspace_path)
    candidates = [
        item for item in items
        if item.get("source_run_id") == safe_run_id and not item.get("_invalid")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    latest_id = candidates[0].get("provider_mock_response_final_safety_seal_id", "")
    return find_provider_mock_response_final_safety_seal_by_id(workspace_path, latest_id)


def summarize_provider_mock_response_final_safety_seal(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_mock_response_final_safety_seal_for_run(workspace_path, safe_run_id)
    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_mock_response_final_safety_seal",
            "run_id": safe_run_id,
            "final_safety_seal_created": False,
            "mock_pipeline_complete": False,
            "seal_valid": False,
            "seal_non_authorizing": False,
            "trust_decision_blocker_recorded": False,
            "trust_blocker_active": False,
            "trust_decision_required": False,
            "trust_decision_present": False,
            "trust_decision_granted": False,
            "trust_decision_explicitly_blocked": False,
            "trust_upgrade_performed": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
        }
    data = load_provider_mock_response_final_safety_seal(artifact_path, workspace_path)
    return {
        "ok": True,
        "status": "research_provider_mock_response_final_safety_seal_summary",
        "run_id": safe_run_id,
        "provider_mock_response_final_safety_seal_id": data.get("provider_mock_response_final_safety_seal_id", ""),
        "final_safety_seal_status": data.get("final_safety_seal_status", ""),
        "final_safety_seal_state": data.get("final_safety_seal_state", ""),
        "final_safety_seal_created": True,
        "mock_pipeline_complete": True,
        "seal_valid": True,
        "seal_non_authorizing": True,
        "trust_decision_blocker_recorded": True,
        "trust_blocker_active": True,
        "trust_decision_required": True,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_explicitly_blocked": True,
        "trust_upgrade_performed": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "provider_call_allowed": False,
        "broker_touched": False,
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
    }


def doctor_provider_mock_response_final_safety_seal(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    seal_path = _find_latest_provider_mock_response_final_safety_seal_for_run(workspace_path, safe_run_id)
    if not seal_path:
        return {
            "ok": True,
            "status": "research_provider_mock_response_final_safety_seal_doctor",
            "run_id": safe_run_id,
            "seal_health": "seal_missing",
            "final_safety_seal_created": False,
            "mock_pipeline_complete": False,
            "seal_valid": False,
            "seal_non_authorizing": False,
            "trust_decision_blocker_recorded": False,
            "trust_blocker_active": False,
            "trust_decision_required": False,
            "trust_decision_present": False,
            "trust_decision_granted": False,
            "trust_decision_explicitly_blocked": False,
            "trust_upgrade_performed": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
            "live_trading_path_enabled": False,
            "broker_order_path_enabled": False,
            "missing_prerequisites": [
                "real_trust_decision_not_implemented",
                "manual_review_not_completed",
                "trust_upgrade_not_implemented",
                "real_provider_response_not_available",
            ],
            "blocking_reasons": ["final_safety_seal_missing"],
            "warnings": [],
        }

    data = load_provider_mock_response_final_safety_seal(seal_path, workspace_path)
    seal_id = data.get("provider_mock_response_final_safety_seal_id", "")

    missing_prerequisites = [
        "real_trust_decision_not_implemented",
        "manual_review_not_completed",
        "trust_upgrade_not_implemented",
        "real_provider_response_not_available",
    ]
    blocking_reasons = [
        "trust_decision_explicitly_blocked",
        "trust_upgrade_not_implemented",
        "manual_review_required_before_future_trust",
        "mock_response_not_trusted",
        "provider_response_not_trusted",
        "provider_execution_disabled",
    ]

    warnings: list[str] = []
    if not find_provider_mock_response_trust_decision_blocker_by_id(workspace_path, data.get("source_trust_decision_blocker_id", "")):
        warnings.append("source_trust_decision_blocker_missing")

    return {
        "ok": True,
        "status": "research_provider_mock_response_final_safety_seal_doctor",
        "run_id": safe_run_id,
        "provider_mock_response_final_safety_seal_id": seal_id,
        "seal_health": "seal_valid",
        "final_safety_seal_created": True,
        "mock_pipeline_complete": True,
        "seal_valid": True,
        "seal_non_authorizing": True,
        "trust_decision_blocker_recorded": True,
        "trust_blocker_active": True,
        "trust_decision_required": True,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_explicitly_blocked": True,
        "trust_upgrade_performed": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "provider_call_allowed": False,
        "broker_touched": False,
        "live_trading_path_enabled": False,
        "broker_order_path_enabled": False,
        "missing_prerequisites": missing_prerequisites,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def iter_provider_mock_response_final_safety_seal_artifacts(
    workspace_path: Path, symbol: str | None = None
) -> list[dict[str, Any]]:
    paths = list_artifact_json_paths(
        workspace_path,
        RESEARCH_DIR,
        _PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_SPEC,
        symbol=symbol,
    )

    items: list[dict[str, Any]] = []
    invalid_items: list[dict[str, Any]] = []
    for path in paths:
        if path.is_symlink():
            resolved = path.resolve()
            if not _is_inside_workspace(resolved, workspace_path):
                continue
        try:
            raw = load_json_object(path)
        except Exception:
            invalid_items.append({
                "provider_mock_response_final_safety_seal_id": path.stem,
                "symbol": path.parents[1].name if len(path.parents) > 1 else "",
                "provider_id": "unknown",
                "model_id": "unknown",
                "final_safety_seal_status": "invalid",
                "final_safety_seal_state": "invalid",
                "_invalid": True,
                "error_code": "provider_mock_response_final_safety_seal_malformed",
            })
            continue
        cleaned, error = safe_validate_provider_mock_response_final_safety_seal_data(raw, workspace_path=workspace_path)
        if error or cleaned is None:
            invalid_items.append({
                "provider_mock_response_final_safety_seal_id": raw.get("provider_mock_response_final_safety_seal_id", path.stem),
                "symbol": raw.get("symbol", ""),
                "provider_id": raw.get("provider_id", "unknown"),
                "model_id": raw.get("model_id", "unknown"),
                "final_safety_seal_status": raw.get("final_safety_seal_status", "invalid"),
                "final_safety_seal_state": raw.get("final_safety_seal_state", "invalid"),
                "_invalid": True,
                "error_code": error or "provider_mock_response_final_safety_seal_malformed",
            })
            continue
        items.append({
            "provider_mock_response_final_safety_seal_id": cleaned.get("provider_mock_response_final_safety_seal_id", ""),
            "symbol": cleaned.get("symbol", ""),
            "provider_id": cleaned.get("provider_id", ""),
            "model_id": cleaned.get("model_id", ""),
            "final_safety_seal_status": cleaned.get("final_safety_seal_status", ""),
            "final_safety_seal_state": cleaned.get("final_safety_seal_state", ""),
            "source_trust_decision_blocker_id": cleaned.get("source_trust_decision_blocker_id", ""),
            "source_run_id": cleaned.get("source_run_id", ""),
            "created_at": cleaned.get("created_at", ""),
            "artifact_path": cleaned.get("artifact_path", ""),
        })

    items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    return items + invalid_items


def find_provider_mock_response_final_safety_seal_by_id(workspace_path: Path, seal_id: str) -> Path | None:
    safe_id = validate_run_id(seal_id)
    search_dir = workspace_path / RESEARCH_DIR
    for p in search_dir.rglob("provider_mock_response_final_safety_seals/*.json"):
        if p.stem == safe_id:
            return p
    return None
