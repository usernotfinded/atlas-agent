# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_mock_response_simulation.py
# PURPOSE: Mock pipeline, step 1: synthesises a candidate response so the entire intake
#          path can be exercised with no provider and no network behind it.
# DEPS:    research.provider_response_schema_contract, research.sandbox_contracts
# ==============================================================================

"""Provider mock response simulation — local, configless mock response artifact.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider mock response simulation artifacts. It does NOT implement any real provider
adapter, does NOT call any real provider, does NOT perform network requests, does NOT
read API keys, does NOT read os.environ, does NOT load .env.atlas, does NOT import
provider SDKs, does NOT receive real provider responses, does NOT trust provider
responses, does NOT create trading signals, does NOT create approvals or pending
orders, does NOT authorize live trading, and does NOT touch brokers.

A provider mock response simulation defines the offline mock adapter boundary, required
prerequisites, blocked states, and mock response harness. Only the mock adapter
exists; no real provider adapter is implemented.
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

PROVIDER_MOCK_RESPONSE_SIMULATION_VERSION = "research_provider_mock_response_simulation_v1"

_PROVIDER_MOCK_RESPONSE_SIMULATION_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_MOCK_SIMULATION_STATUSES = {
    "mock_response_simulation_recorded",
    "mock_response_simulation_invalid",
}

_VALID_MOCK_SIMULATION_SCOPES = {
    "offline_mock_provider_response_only",
}

_VALID_MOCK_SIMULATION_STATES = {
    "simulated_response_recorded_no_provider_call",
    "mock_only_untrusted",
    "manual_review_required",
}

_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE = [
    "real_provider_adapter_used",
    "real_provider_request_sent",
    "real_provider_response_received",
    "provider_response_received",
    "provider_response_imported",
    "provider_response_trusted",
    "provider_response_reviewed",
    "mock_response_trusted",
    "raw_request_body_stored",
    "raw_response_body_stored",
    "raw_prompt_body_stored",
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
    "mock_adapter_used",
    "mock_response_simulated",
    "mock_only",
    "manual_review_required",
]

# Unsafe positive-claim phrases that must not appear in string values anywhere in the artifact.
_UNSAFE_POSITIVE_CLAIM_PHRASES = (
    "real provider adapter used",
    "real provider adapter implemented",
    "real provider request sent",
    "provider response received",
    "provider response trusted",
    "mock response trusted",
    "network enabled",
    "network call attempted",
    "credentials loaded",
    "provider call allowed",
    "actual provider call made",
    "outbound request sent",
    "trading signal generated",
    "create order",
    "approve order",
    "call broker",
    "buy signal",
    "sell signal",
    "broker touched",
    "trust upgrade performed",
    "manual unlock granted",
    "api key loaded",
    "api call succeeded",
    "live trading authorized",
)


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


@dataclass(frozen=True)
class ProviderMockResponseSimulationValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_adapter_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        value = str(value)
    return sanitize_contract_text(value, max_chars)


def validate_provider_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_mock_response_simulation_provider")
    if value == "mock":
        return value
    if value not in _get_disabled_provider_ids():
        raise ResearchSessionError("invalid_provider_mock_response_simulation_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_mock_response_simulation_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_mock_response_simulation_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_simulation_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_mock_response_simulation_model")
    return value


def validate_mock_simulation_status(value: str) -> str:
    if not value or value not in _VALID_MOCK_SIMULATION_STATUSES:
        raise ResearchSessionError("invalid_provider_mock_response_simulation_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_simulation_status")
    return value


def validate_mock_simulation_scope(value: str) -> str:
    if not value or value not in _VALID_MOCK_SIMULATION_SCOPES:
        raise ResearchSessionError("invalid_provider_mock_response_simulation_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_simulation_status")
    return value


def validate_mock_simulation_state(value: str) -> str:
    if not value or value not in _VALID_MOCK_SIMULATION_STATES:
        raise ResearchSessionError("invalid_provider_mock_response_simulation_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_simulation_status")
    return value


def provider_mock_response_simulation_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_MOCK_RESPONSE_SIMULATION_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
        if data.get(flag) is not False:
            return "provider_mock_response_simulation_impossible_boolean"
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
        if data.get(flag) is not True:
            return "provider_mock_response_simulation_impossible_boolean"
    return None


def _build_mock_adapter_capability_summary() -> dict[str, Any]:
    return {
        "mock_adapter_available": True,
        "mock_only": True,
        "real_provider_adapter_used": False,
        "real_provider_adapter_implemented": False,
        "provider_sdk_imported": False,
        "http_client_imported": False,
        "network_call_allowed": False,
        "credential_loading_allowed": False,
        "broker_bridge_allowed": False,
    }


def _build_mock_request_preview_summary() -> dict[str, Any]:
    return {
        "request_preview_used": True,
        "payload_hash_used": True,
        "raw_payload_body_stored": False,
        "raw_prompt_stored": False,
        "real_provider_request_sent": False,
        "provider_call_allowed": False,
    }


def _build_mock_response_summary() -> dict[str, Any]:
    return {
        "simulation_family": "offline_mock_provider_response",
        "simulated_response_summary": "offline_mock_response_placeholder_no_provider_call",
        "raw_response_body_stored": False,
        "provider_response_received": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
    }


def _build_mock_response_hash_policy() -> dict[str, Any]:
    return {
        "mock_response_hash_required": True,
        "hash_algorithm": "sha256",
        "hash_without_raw_body_storage": True,
        "hash_does_not_imply_real_response": True,
        "hash_does_not_imply_trust": True,
    }


def _build_mock_response_storage_policy() -> dict[str, Any]:
    return {
        "raw_response_body_stored": False,
        "raw_prompt_body_stored": False,
        "bounded_summary_stored": True,
        "raw_response_in_events_allowed": False,
        "raw_response_in_logs_allowed": False,
    }


def _build_mock_response_trust_policy() -> dict[str, Any]:
    return {
        "mock_response_trusted": False,
        "provider_response_trusted": False,
        "mock_response_cannot_be_trading_signal": True,
        "mock_response_cannot_create_orders": True,
        "mock_response_cannot_approve_orders": True,
        "mock_response_cannot_call_broker": True,
        "trust_upgrade_not_implemented": True,
    }


def _build_mock_response_review_policy() -> dict[str, Any]:
    return {
        "manual_review_required": True,
        "manual_review_gate_open": False,
        "review_result_present": False,
        "review_does_not_authorize_trading": True,
    }


def _build_real_provider_boundary_policy() -> dict[str, Any]:
    return {
        "real_provider_adapter_used": False,
        "real_provider_request_sent": False,
        "real_provider_response_received": False,
        "real_provider_execution_allowed": False,
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


def _build_broker_separation_policy() -> dict[str, Any]:
    return {
        "broker_live_bridge_allowed": False,
        "broker_adapter_access_allowed": False,
        "order_routing_allowed": False,
        "approval_manager_access_allowed": False,
        "risk_manager_access_allowed": False,
    }


def _build_side_effect_policy() -> dict[str, Any]:
    return {
        "filesystem_side_effects_limited_to_artifacts": True,
        "summary_commands_write_artifacts": False,
        "doctor_commands_write_artifacts": False,
        "mock_simulation_writes_only_simulation_artifact": True,
        "mock_simulation_writes_events": True,
        "mock_simulation_touches_broker": False,
    }


def _build_denylist_metadata() -> dict[str, Any]:
    return {
        "denylist_profile": "atlas_provider_mock_response_simulation_v1",
        "forbidden_fragment_count": len(FORBIDDEN_FRAGMENTS),
        "forbidden_fragments_raw_stored": False,
    }


def build_provider_mock_response_simulation_dict(
    source_adapter_interface_contract: dict[str, Any],
    source_unlock_state: dict[str, Any],
    source_review_result: dict[str, Any],
    source_schema_contract: dict[str, Any],
    source_pairing: dict[str, Any],
    source_intake_policy: dict[str, Any],
    source_preview: dict[str, Any],
    simulation_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(simulation_id, "provider_mock_response_simulation_id")

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
    safe_provider_id = validate_provider_id(source_preview.get("provider_id", ""))
    safe_model_id = validate_model_id(source_preview.get("model_id", ""))

    created_at = datetime.now(UTC)
    artifact_path_rel = f".atlas/research/{symbol}/provider_mock_response_simulations/{simulation_id}.json"

    mock_adapter_capability_summary = _build_mock_adapter_capability_summary()
    mock_request_preview_summary = _build_mock_request_preview_summary()
    mock_response_summary = _build_mock_response_summary()
    mock_response_hash_policy = _build_mock_response_hash_policy()
    mock_response_storage_policy = _build_mock_response_storage_policy()
    mock_response_trust_policy = _build_mock_response_trust_policy()
    mock_response_review_policy = _build_mock_response_review_policy()
    real_provider_boundary_policy = _build_real_provider_boundary_policy()
    network_boundary_policy = _build_network_boundary_policy()
    credential_boundary_policy = _build_credential_boundary_policy()
    broker_separation_policy = _build_broker_separation_policy()
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
        "provider_execution_unlock_state_recorded",
        "provider_adapter_interface_contract_recorded",
        "mock_response_simulation_recorded",
        "mock_adapter_used",
        "mock_response_simulated",
    ]

    missing_prerequisites = [
        "manual_unlock_not_granted",
        "credential_loader_not_implemented",
        "real_provider_adapter_not_implemented",
        "network_policy_not_implemented",
        "real_provider_response_artifact_missing",
        "trust_upgrade_policy_not_implemented",
        "provider_sdk_policy_not_implemented",
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
    ]

    warnings = [
        "This is a local provider mock response simulation. No provider request was sent.",
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
        "Mock response simulation cannot create orders, approvals, or pending orders.",
        "Mock response simulation cannot call broker.",
        "Real provider execution requires explicit future opt-in.",
    ]

    metadata = {
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

    source_adapter_interface_contract_hash = source_adapter_interface_contract.get("artifact_hash", "")
    source_unlock_state_hash = source_unlock_state.get("artifact_hash", "")
    source_review_result_hash = source_review_result.get("artifact_hash", "")
    source_schema_contract_hash = source_schema_contract.get("artifact_hash", "")
    source_pairing_hash = source_pairing.get("artifact_hash", "")
    source_response_intake_policy_hash = source_intake_policy.get("artifact_hash", "")
    source_payload_preview_hash = source_preview.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_mock_response_simulation",
        "contract_version": PROVIDER_MOCK_RESPONSE_SIMULATION_VERSION,
        "provider_mock_response_simulation_id": simulation_id,
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
        "mock_simulation_status": "mock_response_simulation_recorded",
        "mock_simulation_scope": "offline_mock_provider_response_only",
        "mock_simulation_state": "simulated_response_recorded_no_provider_call",
        "mock_adapter_capability_summary": mock_adapter_capability_summary,
        "mock_request_preview_summary": mock_request_preview_summary,
        "mock_response_summary": mock_response_summary,
        "mock_response_hash_policy": mock_response_hash_policy,
        "mock_response_storage_policy": mock_response_storage_policy,
        "mock_response_trust_policy": mock_response_trust_policy,
        "mock_response_review_policy": mock_response_review_policy,
        "real_provider_boundary_policy": real_provider_boundary_policy,
        "network_boundary_policy": network_boundary_policy,
        "credential_boundary_policy": credential_boundary_policy,
        "broker_separation_policy": broker_separation_policy,
        "side_effect_policy": side_effect_policy,
        "required_prerequisites": required_prerequisites,
        "satisfied_prerequisites": satisfied_prerequisites,
        "missing_prerequisites": missing_prerequisites,
        "blocking_reasons": blocking_reasons,
        "source_adapter_interface_contract_hash": source_adapter_interface_contract_hash,
        "source_unlock_state_hash": source_unlock_state_hash,
        "source_review_result_hash": source_review_result_hash,
        "source_schema_contract_hash": source_schema_contract_hash,
        "source_pairing_hash": source_pairing_hash,
        "source_response_intake_policy_hash": source_response_intake_policy_hash,
        "source_payload_preview_hash": source_payload_preview_hash,
        "provider_id": "mock",
        "mock_adapter_used": True,
        "mock_response_simulated": True,
        "mock_only": True,
        "real_provider_adapter_used": False,
        "real_provider_request_sent": False,
        "real_provider_response_received": False,
        "provider_response_received": False,
        "provider_response_imported": False,
        "provider_response_trusted": False,
        "provider_response_reviewed": False,
        "mock_response_trusted": False,
        "manual_review_required": True,
        "raw_request_body_stored": False,
        "raw_response_body_stored": False,
        "raw_prompt_body_stored": False,
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

    artifact["artifact_hash"] = provider_mock_response_simulation_sha256(artifact)
    return artifact


def create_provider_mock_response_simulation(
    workspace_path: Path,
    adapter_interface_contract_id: str,
) -> dict[str, Any]:
    safe_contract_id = validate_run_id(adapter_interface_contract_id)

    from atlas_agent.research.provider_adapter_interface_contract import (
        find_provider_adapter_interface_contract_by_id,
        load_provider_adapter_interface_contract,
    )

    adapter_path = find_provider_adapter_interface_contract_by_id(workspace_path, safe_contract_id)
    if adapter_path is None:
        raise ResearchSessionError("provider_mock_response_simulation_source_adapter_interface_missing")

    source_adapter_interface_contract = load_provider_adapter_interface_contract(adapter_path, workspace_path)

    source_unlock_state_id = source_adapter_interface_contract.get("source_provider_execution_unlock_state_id", "")
    from atlas_agent.research.provider_execution_unlock_state import (
        find_provider_execution_unlock_state_by_id,
        load_provider_execution_unlock_state,
    )

    unlock_state_path = find_provider_execution_unlock_state_by_id(workspace_path, source_unlock_state_id)
    if unlock_state_path is None:
        raise ResearchSessionError("provider_mock_response_simulation_source_unlock_state_missing")

    source_unlock_state = load_provider_execution_unlock_state(unlock_state_path, workspace_path)

    source_review_result_id = source_adapter_interface_contract.get("source_provider_response_review_result_id", "")
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )

    review_result_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
    if review_result_path is None:
        raise ResearchSessionError("provider_mock_response_simulation_source_review_result_missing")

    source_review_result = load_provider_response_review_result(review_result_path, workspace_path)

    source_schema_contract_id = source_adapter_interface_contract.get("source_provider_response_schema_contract_id", "")
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )

    schema_contract_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
    if schema_contract_path is None:
        raise ResearchSessionError("provider_mock_response_simulation_source_schema_contract_missing")

    source_schema_contract = load_provider_response_schema_contract(schema_contract_path, workspace_path)

    source_pairing_id = source_adapter_interface_contract.get("source_provider_request_response_pairing_id", "")
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )

    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
    if pairing_path is None:
        raise ResearchSessionError("provider_mock_response_simulation_source_pairing_missing")

    source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)

    source_intake_id = source_adapter_interface_contract.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
    if intake_path is None:
        raise ResearchSessionError("provider_mock_response_simulation_source_response_intake_missing")

    source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)

    source_preview_id = source_adapter_interface_contract.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if preview_path is None:
        raise ResearchSessionError("provider_mock_response_simulation_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    simulation_id = generate_run_id()
    artifact = build_provider_mock_response_simulation_dict(
        source_adapter_interface_contract,
        source_unlock_state,
        source_review_result,
        source_schema_contract,
        source_pairing,
        source_intake_policy,
        source_preview,
        simulation_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    result_dir = workspace_path / RESEARCH_DIR / symbol / "provider_mock_response_simulations"
    result_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_mock_response_simulated",
        "provider_mock_response_simulation_id": simulation_id,
        "source_provider_adapter_interface_contract_id": safe_contract_id,
        "source_provider_execution_unlock_state_id": source_unlock_state_id,
        "source_provider_response_review_result_id": source_review_result_id,
        "source_provider_response_schema_contract_id": source_schema_contract_id,
        "source_provider_request_response_pairing_id": source_pairing_id,
        "source_provider_response_intake_policy_id": source_intake_id,
        "source_provider_outbound_payload_preview_id": source_preview_id,
        "provider_id": "mock",
        "mock_adapter_used": True,
        "mock_response_simulated": True,
        "mock_only": True,
        "real_provider_adapter_used": False,
        "real_provider_request_sent": False,
        "real_provider_response_received": False,
        "provider_response_received": False,
        "provider_response_imported": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "manual_review_required": True,
        "raw_request_body_stored": False,
        "raw_response_body_stored": False,
        "raw_prompt_body_stored": False,
        "provider_sdk_imported": False,
        "http_client_imported": False,
        "network_enabled": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
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
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_mock_response_simulation_{field_name}"
    return None


def safe_validate_provider_mock_response_simulation_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_mock_response_simulation_schema"

    if data.get("artifact_type") != "provider_mock_response_simulation":
        return None, "provider_mock_response_simulation_malformed"

    if data.get("contract_version") != PROVIDER_MOCK_RESPONSE_SIMULATION_VERSION:
        return None, "provider_mock_response_simulation_malformed"

    try:
        validate_mock_simulation_status(data.get("mock_simulation_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_simulation_status"

    try:
        validate_mock_simulation_scope(data.get("mock_simulation_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_simulation_status"

    try:
        validate_mock_simulation_state(data.get("mock_simulation_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_simulation_status"

    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    if data.get("mode") != "paper":
        return None, "provider_mock_response_simulation_malformed"

    lineage_field_names = [
        "provider_mock_response_simulation_id",
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
            return None, "invalid_provider_mock_response_simulation_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_simulation_lineage"

    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_simulation_provider"
    if provider_id != "mock":
        return None, "invalid_provider_mock_response_simulation_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_simulation_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_mock_response_simulation_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_mock_response_simulation_hash_mismatch"

    if workspace_path is not None and not for_replay:
        source_adapter_contract_id = data.get("source_provider_adapter_interface_contract_id", "")
        if source_adapter_contract_id:
            try:
                from atlas_agent.research.provider_adapter_interface_contract import (
                    find_provider_adapter_interface_contract_by_id,
                    load_provider_adapter_interface_contract,
                )

                ac_path = find_provider_adapter_interface_contract_by_id(workspace_path, source_adapter_contract_id)
                if ac_path is None:
                    return None, "provider_mock_response_simulation_source_adapter_interface_missing"
                ac_data = load_provider_adapter_interface_contract(ac_path, workspace_path)
                stored_ac_hash = data.get("source_adapter_interface_contract_hash", "")
                actual_ac_hash = ac_data.get("artifact_hash", "")
                if stored_ac_hash != actual_ac_hash:
                    return None, "provider_mock_response_simulation_source_adapter_interface_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_simulation_source_adapter_interface_missing"

        source_unlock_state_id = data.get("source_provider_execution_unlock_state_id", "")
        if source_unlock_state_id:
            try:
                from atlas_agent.research.provider_execution_unlock_state import (
                    find_provider_execution_unlock_state_by_id,
                    load_provider_execution_unlock_state,
                )

                us_path = find_provider_execution_unlock_state_by_id(workspace_path, source_unlock_state_id)
                if us_path is None:
                    return None, "provider_mock_response_simulation_source_unlock_state_missing"
                us_data = load_provider_execution_unlock_state(us_path, workspace_path)
                stored_us_hash = data.get("source_unlock_state_hash", "")
                actual_us_hash = us_data.get("artifact_hash", "")
                if stored_us_hash != actual_us_hash:
                    return None, "provider_mock_response_simulation_source_unlock_state_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_simulation_source_unlock_state_missing"

        source_review_result_id = data.get("source_provider_response_review_result_id", "")
        if source_review_result_id:
            try:
                from atlas_agent.research.provider_response_review_result import (
                    find_provider_response_review_result_by_id,
                    load_provider_response_review_result,
                )

                rr_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
                if rr_path is None:
                    return None, "provider_mock_response_simulation_source_review_result_missing"
                rr_data = load_provider_response_review_result(rr_path, workspace_path)
                stored_rr_hash = data.get("source_review_result_hash", "")
                actual_rr_hash = rr_data.get("artifact_hash", "")
                if stored_rr_hash != actual_rr_hash:
                    return None, "provider_mock_response_simulation_source_review_result_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_simulation_source_review_result_missing"

        source_schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
        if source_schema_contract_id:
            try:
                from atlas_agent.research.provider_response_schema_contract import (
                    find_provider_response_schema_contract_by_id,
                    load_provider_response_schema_contract,
                )

                sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
                if sc_path is None:
                    return None, "provider_mock_response_simulation_source_schema_contract_missing"
                sc_data = load_provider_response_schema_contract(sc_path, workspace_path)
                stored_sc_hash = data.get("source_schema_contract_hash", "")
                actual_sc_hash = sc_data.get("artifact_hash", "")
                if stored_sc_hash != actual_sc_hash:
                    return None, "provider_mock_response_simulation_source_schema_contract_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_simulation_source_schema_contract_missing"

        source_pairing_id = data.get("source_provider_request_response_pairing_id", "")
        if source_pairing_id:
            try:
                from atlas_agent.research.provider_request_response_pairing import (
                    find_provider_request_response_pairing_by_id,
                    load_provider_request_response_pairing,
                )

                pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
                if pairing_path is None:
                    return None, "provider_mock_response_simulation_source_pairing_missing"
                pairing_data = load_provider_request_response_pairing(pairing_path, workspace_path)
                stored_pairing_hash = data.get("source_pairing_hash", "")
                actual_pairing_hash = pairing_data.get("artifact_hash", "")
                if stored_pairing_hash != actual_pairing_hash:
                    return None, "provider_mock_response_simulation_source_pairing_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_simulation_source_pairing_missing"

        source_intake_id = data.get("source_provider_response_intake_policy_id", "")
        if source_intake_id:
            try:
                from atlas_agent.research.provider_response_intake_policy import (
                    find_provider_response_intake_policy_by_id,
                    load_provider_response_intake_policy,
                )

                intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
                if intake_path is None:
                    return None, "provider_mock_response_simulation_source_response_intake_missing"
                intake_data = load_provider_response_intake_policy(intake_path, workspace_path)
                stored_intake_hash = data.get("source_response_intake_policy_hash", "")
                actual_intake_hash = intake_data.get("artifact_hash", "")
                if stored_intake_hash != actual_intake_hash:
                    return None, "provider_mock_response_simulation_source_response_intake_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_simulation_source_response_intake_missing"

        source_preview_id = data.get("source_provider_outbound_payload_preview_id", "")
        if source_preview_id:
            try:
                from atlas_agent.research.provider_outbound_payload_preview import (
                    find_provider_outbound_payload_preview_by_id,
                    load_provider_outbound_payload_preview,
                )

                preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
                if preview_path is None:
                    return None, "provider_mock_response_simulation_source_payload_preview_missing"
                preview_data = load_provider_outbound_payload_preview(preview_path, workspace_path)
                stored_preview_hash = data.get("source_payload_preview_hash", "")
                actual_preview_hash = preview_data.get("artifact_hash", "")
                if stored_preview_hash != actual_preview_hash:
                    return None, "provider_mock_response_simulation_source_payload_preview_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_mock_response_simulation_source_payload_preview_missing"

    # Check policy fields for forbidden fragments
    policy_fields = [
        json.dumps(data.get("mock_adapter_capability_summary", {})),
        json.dumps(data.get("mock_request_preview_summary", {})),
        json.dumps(data.get("mock_response_summary", {})),
        json.dumps(data.get("mock_response_hash_policy", {})),
        json.dumps(data.get("mock_response_storage_policy", {})),
        json.dumps(data.get("mock_response_trust_policy", {})),
        json.dumps(data.get("mock_response_review_policy", {})),
        json.dumps(data.get("real_provider_boundary_policy", {})),
        json.dumps(data.get("network_boundary_policy", {})),
        json.dumps(data.get("credential_boundary_policy", {})),
        json.dumps(data.get("broker_separation_policy", {})),
        json.dumps(data.get("side_effect_policy", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("required_prerequisites", [])),
        json.dumps(data.get("satisfied_prerequisites", [])),
        json.dumps(data.get("missing_prerequisites", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in policy_fields):
        return None, "provider_mock_response_simulation_malformed"

    # Check status/scope/state for forbidden fragments
    policy_summaries = [
        data.get("mock_simulation_status", ""),
        data.get("mock_simulation_scope", ""),
        data.get("mock_simulation_state", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_mock_response_simulation_forbidden_mock_claim"

    # Check policy fields for unsafe positive claims
    policy_fields_for_positive_claim_check = [
        data.get("mock_adapter_capability_summary", {}),
        data.get("mock_request_preview_summary", {}),
        data.get("mock_response_summary", {}),
        data.get("response_text", ""),
        data.get("mock_response_hash_policy", {}),
        data.get("mock_response_storage_policy", {}),
        data.get("mock_response_trust_policy", {}),
        data.get("mock_response_review_policy", {}),
        data.get("real_provider_boundary_policy", {}),
        data.get("network_boundary_policy", {}),
        data.get("credential_boundary_policy", {}),
        data.get("broker_separation_policy", {}),
        data.get("side_effect_policy", {}),
    ]
    if any(_has_unsafe_positive_claims(f) for f in policy_fields_for_positive_claim_check):
        return None, "provider_mock_response_simulation_forbidden_mock_claim"

    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_mock_response_simulation_malformed"

    cleaned = {k: v for k, v in data.items()}
    return cleaned, None


def validate_provider_mock_response_simulation_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderMockResponseSimulationValidationResult:
    data = load_provider_mock_response_simulation(path, workspace_path)
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
            at == "provider_mock_response_simulation",
            "artifact_type must be provider_mock_response_simulation." if at != "provider_mock_response_simulation" else "artifact_type is correct.",
        )
    )

    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_MOCK_RESPONSE_SIMULATION_VERSION,
            "contract_version must match current contract." if cv != PROVIDER_MOCK_RESPONSE_SIMULATION_VERSION else "contract_version matches.",
        )
    )

    status = data.get("mock_simulation_status", "")
    status_ok = status in _VALID_MOCK_SIMULATION_STATUSES
    checks.append(
        _check_name(
            "mock_simulation_status_valid",
            status_ok,
            "mock_simulation_status is invalid." if not status_ok else "mock_simulation_status is valid.",
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

    computed = provider_mock_response_simulation_sha256(data)
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

    return ProviderMockResponseSimulationValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation="Proceed with mock response simulation." if valid else "Reject artifact and investigate tampering.",
        warnings=warnings,
    )


def load_provider_mock_response_simulation(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        raise ResearchSessionError("provider_mock_response_simulation_malformed") from e

    cleaned, err = safe_validate_provider_mock_response_simulation_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    if not cleaned:
        raise ResearchSessionError("provider_mock_response_simulation_malformed")
    return cleaned


def load_and_validate_provider_mock_response_simulation(path: Path, workspace_path: Path) -> dict[str, Any]:
    data = load_provider_mock_response_simulation(path, workspace_path)
    res = validate_provider_mock_response_simulation_artifact(path, workspace_path)
    if not res.valid:
        raise ResearchSessionError("invalid_provider_mock_response_simulation_artifact")
    return data


def find_provider_mock_response_simulation_by_id(workspace_path: Path, simulation_id: str) -> Path | None:
    safe_id = validate_run_id(simulation_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    for p in search_dir.rglob("provider_mock_response_simulations/*.json"):
        if p.stem == safe_id:
            return p
    return None


def replay_provider_mock_response_simulation(
    workspace_path: Path,
    simulation_id: str,
) -> dict[str, Any]:
    safe_id = validate_run_id(simulation_id)
    artifact_path = find_provider_mock_response_simulation_by_id(workspace_path, safe_id)
    if not artifact_path:
        raise ResearchSessionError("provider_mock_response_simulation_not_found")

    try:
        old_artifact = load_provider_mock_response_simulation(artifact_path, workspace_path=None)
    except ResearchSessionError:
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            old_hash = raw.get("artifact_hash", "")
        except Exception:
            old_hash = ""
        return {
            "ok": False,
            "match": False,
            "provider_mock_response_simulation_id": safe_id,
            "original_hash": old_hash,
            "replayed_hash": "",
            "status": "research_provider_mock_response_simulation_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

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

    new_artifact = build_provider_mock_response_simulation_dict(
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
    new_artifact["artifact_hash"] = provider_mock_response_simulation_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_mock_response_simulation_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_mock_response_simulation_replayed",
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
        "provider_mock_response_simulation_id": safe_id,
        "original_hash": old_artifact.get("artifact_hash", ""),
        "replayed_hash": "",
        "status": "research_provider_mock_response_simulation_replay_failed",
        "provider_response_received": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "broker_touched": False,
    }


def iter_provider_mock_response_simulation_artifacts(
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
        result_dir = sym_dir / "provider_mock_response_simulations"
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
                    "provider_mock_response_simulation_id": "<invalid>",
                    "source_provider_adapter_interface_contract_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "mock_simulation_status": "invalid",
                    "mock_simulation_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_mock_response_simulation_artifact",
                    "created_at": "",
                })
                continue
            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_mock_response_simulation_id": "<invalid>",
                    "source_provider_adapter_interface_contract_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "mock_simulation_status": "invalid",
                    "mock_simulation_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_mock_response_simulation_artifact",
                    "created_at": "",
                })
                continue
            cleaned, error = safe_validate_provider_mock_response_simulation_data(raw, workspace_path=workspace_path)
            if error or cleaned is None:
                invalid_items.append({
                    "provider_mock_response_simulation_id": "<invalid>",
                    "source_provider_adapter_interface_contract_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "mock_simulation_status": "invalid",
                    "mock_simulation_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_mock_response_simulation_artifact",
                    "created_at": "",
                })
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append({
                "provider_mock_response_simulation_id": cleaned.get("provider_mock_response_simulation_id", path.stem),
                "source_provider_adapter_interface_contract_id": cleaned.get("source_provider_adapter_interface_contract_id", ""),
                "source_provider_execution_unlock_state_id": cleaned.get("source_provider_execution_unlock_state_id", ""),
                "source_provider_response_review_result_id": cleaned.get("source_provider_response_review_result_id", ""),
                "source_provider_response_schema_contract_id": cleaned.get("source_provider_response_schema_contract_id", ""),
                "source_provider_request_response_pairing_id": cleaned.get("source_provider_request_response_pairing_id", ""),
                "source_provider_response_intake_policy_id": cleaned.get("source_provider_response_intake_policy_id", ""),
                "source_provider_outbound_payload_preview_id": cleaned.get("source_provider_outbound_payload_preview_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "mock_simulation_status": cleaned.get("mock_simulation_status", ""),
                "mock_simulation_scope": cleaned.get("mock_simulation_scope", ""),
                "mock_simulation_state": cleaned.get("mock_simulation_state", ""),
                "artifact_path": rel_path,
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "created_at": cleaned.get("created_at", ""),
                "mock_adapter_used": cleaned.get("mock_adapter_used", True),
                "mock_response_simulated": cleaned.get("mock_response_simulated", True),
                "mock_only": cleaned.get("mock_only", True),
                "real_provider_adapter_used": cleaned.get("real_provider_adapter_used", False),
                "real_provider_request_sent": cleaned.get("real_provider_request_sent", False),
                "real_provider_response_received": cleaned.get("real_provider_response_received", False),
                "provider_response_received": cleaned.get("provider_response_received", False),
                "provider_response_trusted": cleaned.get("provider_response_trusted", False),
                "mock_response_trusted": cleaned.get("mock_response_trusted", False),
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


def _find_latest_provider_mock_response_simulation_for_run(workspace_path: Path, run_id: str) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    latest_path: Path | None = None
    latest_time = ""
    for p in search_dir.rglob("provider_mock_response_simulations/*.json"):
        try:
            data = load_provider_mock_response_simulation(p, workspace_path=None)
            if data.get("source_run_id") == safe_run_id:
                t = data.get("created_at", "")
                if not latest_time or t > latest_time:
                    latest_time = t
                    latest_path = p
        except Exception:
            pass
    return latest_path


def summarize_provider_mock_response_simulation(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_mock_response_simulation_for_run(workspace_path, safe_run_id)

    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_mock_response_simulation",
            "provider_mock_response_simulation_id": None,
            "mock_simulation_status": "not_recorded",
            "mock_simulation_state": "not_recorded",
            "mock_response_simulated": False,
            "mock_only": True,
            "real_provider_request_sent": False,
            "real_provider_response_received": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
            "artifact_path": None,
        }

    try:
        data = load_and_validate_provider_mock_response_simulation(artifact_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": True,
            "status": "invalid_provider_mock_response_simulation",
            "provider_mock_response_simulation_id": None,
            "mock_simulation_status": "invalid",
            "mock_simulation_state": "invalid",
            "mock_response_simulated": False,
            "mock_only": True,
            "real_provider_request_sent": False,
            "real_provider_response_received": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "broker_touched": False,
            "artifact_path": None,
        }

    return {
        "ok": True,
        "status": "research_provider_mock_response_simulation_summary",
        "provider_mock_response_simulation_id": data.get("provider_mock_response_simulation_id"),
        "mock_simulation_status": data.get("mock_simulation_status"),
        "mock_simulation_state": data.get("mock_simulation_state"),
        "mock_response_simulated": True,
        "mock_only": True,
        "real_provider_request_sent": False,
        "real_provider_response_received": False,
        "provider_response_trusted": False,
        "provider_call_allowed": False,
        "broker_touched": False,
        "artifact_path": data.get("artifact_path"),
    }


def doctor_provider_mock_response_simulation(
    workspace_path: Path,
    run_id: str,
) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)

    missing_artifacts: list[str] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    simulation_path = _find_latest_provider_mock_response_simulation_for_run(workspace_path, safe_run_id)
    if not simulation_path:
        missing_artifacts.append("provider_mock_response_simulation")
        blocking_reasons.append("provider_mock_response_simulation_not_created")
        warnings.append("No provider mock response simulation exists for this run.")
        return {
            "ok": True,
            "status": "research_provider_mock_response_doctor",
            "run_id": safe_run_id,
            "mock_response_health": "mock_response_simulation_missing",
            "mock_response_simulated": False,
            "mock_only": True,
            "real_provider_request_sent": False,
            "real_provider_response_received": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "missing_prerequisites": missing_artifacts,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
        }

    try:
        data = load_provider_mock_response_simulation(simulation_path, workspace_path)
    except ResearchSessionError as e:
        warnings.append(f"Mock response simulation artifact is invalid: {e}")
        return {
            "ok": True,
            "status": "research_provider_mock_response_doctor",
            "run_id": safe_run_id,
            "mock_response_health": "mock_response_simulation_invalid",
            "mock_response_simulated": False,
            "mock_only": True,
            "real_provider_request_sent": False,
            "real_provider_response_received": False,
            "provider_response_trusted": False,
            "provider_call_allowed": False,
            "missing_prerequisites": missing_artifacts,
            "blocking_reasons": ["mock_response_simulation_artifact_invalid"],
            "warnings": warnings,
        }

    # Check source artifacts
    unlock_state_id = data.get("source_provider_execution_unlock_state_id", "")
    review_result_id = data.get("source_provider_response_review_result_id", "")
    schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
    pairing_id = data.get("source_provider_request_response_pairing_id", "")
    intake_id = data.get("source_provider_response_intake_policy_id", "")
    preview_id = data.get("source_provider_outbound_payload_preview_id", "")
    adapter_contract_id = data.get("source_provider_adapter_interface_contract_id", "")

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

    # Future prerequisites are expected to be missing
    missing_artifacts.extend([
        "real_provider_adapter_not_implemented",
        "provider_sdk_policy_not_implemented",
        "credential_loader_not_implemented",
        "network_policy_not_implemented",
        "real_provider_response_artifact_missing",
        "trust_upgrade_policy_not_implemented",
    ])
    warnings.append("Future prerequisites are missing. This is expected in this batch.")

    if data.get("mock_simulation_state") == "simulated_response_recorded_no_provider_call":
        mock_response_health = "mock_response_simulated_untrusted"
    else:
        mock_response_health = "blocked"

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
    ])

    return {
        "ok": True,
        "status": "research_provider_mock_response_doctor",
        "run_id": safe_run_id,
        "mock_response_health": mock_response_health,
        "mock_response_simulated": True,
        "mock_only": True,
        "real_provider_request_sent": False,
        "real_provider_response_received": False,
        "provider_response_trusted": False,
        "provider_call_allowed": False,
        "missing_prerequisites": missing_artifacts,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def run_mock_adapter_smoke(adapter_interface_contract_id: str) -> dict[str, Any]:
    """Exercise the mock adapter harness and prove it produces safe mock responses."""
    from atlas_agent.research.provider_adapter_interface import (
        MockProviderAdapter,
        ProviderAdapterDisabledError,
    )

    adapter = MockProviderAdapter()

    # Call capabilities
    cap = adapter.capabilities()

    # Call build_request_preview
    preview = adapter.build_request_preview(
        mock_request_preview_id="smoke-preview",
        source_provider_adapter_interface_contract_id=adapter_interface_contract_id,
        source_provider_execution_unlock_state_id="smoke-unlock",
        source_provider_outbound_payload_preview_id="smoke-preview",
        provider_id="mock",
        model_id="mock",
        request_family="smoke",
        payload_hash="smoke-hash",
    )

    # Call simulate_response
    simulation = adapter.simulate_response(preview, mock_response_simulation_id="smoke-simulation")

    # Call send, expecting failure
    send_failed = False
    static_safe_error = False
    try:
        adapter.send(preview)
    except ProviderAdapterDisabledError:
        send_failed = True
        static_safe_error = True
    except Exception:
        send_failed = True
        static_safe_error = False

    if not send_failed:
        return {
            "ok": False,
            "status": "research_provider_mock_adapter_smoke_failed",
            "provider_adapter_interface_contract_id": adapter_interface_contract_id,
            "error_code": "mock_adapter_send_unexpected_success",
            "mock_adapter_available": True,
            "send_failed_closed": False,
            "static_safe_error": False,
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
            "warnings": ["Mock adapter send() did not raise an error."],
        }

    return {
        "ok": True,
        "status": "research_provider_mock_adapter_smoke_passed",
        "provider_adapter_interface_contract_id": adapter_interface_contract_id,
        "mock_adapter_available": True,
        "send_failed_closed": send_failed,
        "static_safe_error": static_safe_error,
        "provider_response_received": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "broker_touched": False,
        "mock_response_simulated": True,
        "mock_only": True,
        "warnings": [],
    }
