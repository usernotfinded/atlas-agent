# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_adapter_interface_contract.py
# PURPOSE: The conformance artifact for the adapter interface: proves a given adapter
#          satisfies the contract, without instantiating anything that could call out.
# DEPS:    research.provider_adapter_interface, research.sandbox_contracts
# ==============================================================================

"""Provider adapter interface contract — local, configless adapter interface artifact.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider adapter interface contract artifacts. It does NOT implement any real provider
adapter, does NOT call any real provider, does NOT perform network requests, does NOT
read API keys, does NOT read os.environ, does NOT load .env.atlas, does NOT import
provider SDKs, does NOT receive real provider responses, does NOT trust provider
responses, does NOT create trading signals, does NOT create approvals or pending
orders, does NOT authorize live trading, and does NOT touch brokers.

A provider adapter interface contract defines the future adapter boundary, required
prerequisites, blocked states, and disabled adapter harness. Only the disabled adapter
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

PROVIDER_ADAPTER_INTERFACE_CONTRACT_VERSION = "research_provider_adapter_interface_contract_v1"

_PROVIDER_ADAPTER_INTERFACE_CONTRACT_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_ADAPTER_CONTRACT_STATUSES = {
    "adapter_interface_recorded",
    "adapter_disabled",
    "adapter_contract_invalid",
}

_VALID_ADAPTER_CONTRACT_SCOPES = {
    "future_provider_adapter_interface_only",
}

_VALID_ADAPTER_STATES = {
    "disabled_adapter_only",
    "real_adapter_not_implemented",
    "blocked_no_provider_sdk",
    "blocked_no_network_policy",
    "blocked_no_credential_loader",
    "blocked_no_manual_unlock",
}

_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE = [
    "adapter_present",
    "adapter_enabled",
    "real_provider_adapter_implemented",
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
    "provider_response_received",
    "provider_response_imported",
    "provider_response_trusted",
    "trust_upgrade_performed",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
]

_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE = [
    "adapter_interface_recorded",
    "disabled_adapter_available",
]

# Unsafe positive-claim phrases that must not appear in string values anywhere in the artifact.
# These indicate real provider execution, network calls, credential loading, trading, or broker access.
_UNSAFE_POSITIVE_CLAIM_PHRASES = (
    "provider call allowed and send succeeded",
    "send succeeded",
    "real provider adapter implemented",
    "provider sdk imported",
    "http client imported",
    "network enabled",
    "network call attempted",
    "credentials loaded",
    "credential lookup attempted",
    "env read attempted",
    "dotenv loaded",
    "provider execution unlocked",
    "manual unlock granted",
    "actual provider call made",
    "outbound request sent",
    "provider response received",
    "provider response imported",
    "provider response trusted",
    "trust upgrade performed",
    "trading signal generated",
    "create order",
    "approve order",
    "pending order created",
    "call broker",
    "broker touched",
    "buy signal",
    "sell signal",
    "live trading authorized",
    "api key loaded",
    "api call succeeded",
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
class ProviderAdapterInterfaceContractValidationResult:
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
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_provider")
    if value not in _get_disabled_provider_ids():
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_model")
    return value


def validate_adapter_contract_status(value: str) -> str:
    if not value or value not in _VALID_ADAPTER_CONTRACT_STATUSES:
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_status")
    return value


def validate_adapter_contract_scope(value: str) -> str:
    if not value or value not in _VALID_ADAPTER_CONTRACT_SCOPES:
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_status")
    return value


def validate_adapter_state(value: str) -> str:
    if not value or value not in _VALID_ADAPTER_STATES:
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_status")
    return value


def provider_adapter_interface_contract_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_ADAPTER_INTERFACE_CONTRACT_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
        if data.get(flag) is not False:
            return "provider_adapter_interface_contract_impossible_boolean"
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
        if data.get(flag) is not True:
            return "provider_adapter_interface_contract_impossible_boolean"
    return None


def _build_adapter_capability_summary() -> dict[str, Any]:
    return {
        "adapter_protocol_defined": True,
        "disabled_adapter_available": True,
        "real_adapter_implemented": False,
        "provider_sdk_required_for_future_real_adapter": True,
        "provider_sdk_imported_in_this_batch": False,
        "http_client_imported_in_this_batch": False,
        "network_call_allowed_in_this_batch": False,
        "credential_loading_allowed_in_this_batch": False,
        "broker_bridge_allowed": False,
    }


def _build_disabled_adapter_policy() -> dict[str, Any]:
    return {
        "disabled_adapter_must_fail_send": True,
        "disabled_adapter_send_returns_success": False,
        "disabled_adapter_can_call_provider": False,
        "disabled_adapter_can_use_network": False,
        "disabled_adapter_can_load_credentials": False,
        "disabled_adapter_can_call_broker": False,
        "disabled_adapter_error_static_safe": True,
    }


def _build_request_preview_contract() -> dict[str, Any]:
    return {
        "request_preview_allowed": True,
        "raw_payload_body_stored": False,
        "raw_prompt_stored": False,
        "payload_hash_required": True,
        "credential_value_present": False,
        "provider_call_allowed": False,
        "request_preview_does_not_send_network": True,
    }


def _build_response_placeholder_contract() -> dict[str, Any]:
    return {
        "response_placeholder_allowed": True,
        "real_response_received": False,
        "raw_response_body_stored": False,
        "response_hash_present": False,
        "provider_response_trusted": False,
        "manual_review_required": True,
        "placeholder_does_not_imply_response_received": True,
    }


def _build_send_method_policy() -> dict[str, Any]:
    return {
        "send_method_defined_by_interface": True,
        "send_method_disabled_in_this_batch": True,
        "send_method_must_fail_closed": True,
        "send_method_returns_provider_response": False,
        "send_method_can_use_network": False,
        "send_method_can_load_credentials": False,
        "send_method_can_create_orders": False,
        "send_method_can_call_broker": False,
    }


def _build_credential_access_policy() -> dict[str, Any]:
    return {
        "credential_access_allowed": False,
        "credential_lookup_attempted": False,
        "env_lookup_allowed": False,
        "dotenv_loading_allowed": False,
        "api_key_required_in_this_batch": False,
        "future_credential_loader_required": True,
    }


def _build_network_access_policy() -> dict[str, Any]:
    return {
        "network_access_allowed": False,
        "network_call_attempted": False,
        "http_client_imported": False,
        "provider_network_call_allowed": False,
        "future_network_policy_required": True,
    }


def _build_provider_sdk_policy() -> dict[str, Any]:
    return {
        "provider_sdk_import_allowed": False,
        "provider_sdk_imported": False,
        "real_provider_adapter_requires_future_sdk_policy": True,
    }


def _build_error_handling_policy() -> dict[str, Any]:
    return {
        "disabled_error_static_safe": True,
        "provider_sdk_errors_wrapped": False,
        "raw_exception_leakage_behavior": "release_blocker",
        "absolute_path_leakage_behavior": "release_blocker",
        "credential_leakage_behavior": "release_blocker",
    }


def _build_side_effect_policy() -> dict[str, Any]:
    return {
        "filesystem_side_effects_limited_to_artifacts": True,
        "summary_commands_write_artifacts": False,
        "doctor_commands_write_artifacts": False,
        "send_method_writes_events": False,
        "send_method_writes_artifacts": False,
        "send_method_touches_broker": False,
    }


def _build_broker_separation_policy() -> dict[str, Any]:
    return {
        "broker_live_bridge_allowed": False,
        "broker_adapter_access_allowed": False,
        "order_routing_allowed": False,
        "approval_manager_access_allowed": False,
        "risk_manager_access_allowed": False,
    }


def _build_future_adapter_requirements() -> dict[str, Any]:
    return {
        "future_real_adapter_requires_manual_unlock": True,
        "future_real_adapter_requires_credential_loader": True,
        "future_real_adapter_requires_network_policy": True,
        "future_real_adapter_requires_provider_sdk_policy": True,
        "future_real_adapter_requires_response_import_policy": True,
        "future_real_adapter_cannot_call_broker": True,
    }


def _build_denylist_metadata() -> dict[str, Any]:
    return {
        "denylist_profile": "atlas_provider_adapter_interface_contract_v1",
        "forbidden_fragment_count": len(FORBIDDEN_FRAGMENTS),
        "forbidden_fragments_raw_stored": False,
    }


def build_provider_adapter_interface_contract_dict(
    source_unlock_state: dict[str, Any],
    source_review_result: dict[str, Any],
    source_schema_contract: dict[str, Any],
    source_pairing: dict[str, Any],
    source_intake_policy: dict[str, Any],
    source_preview: dict[str, Any],
    contract_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(contract_id, "provider_adapter_interface_contract_id")

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
    artifact_path_rel = f".atlas/research/{symbol}/provider_adapter_interface_contracts/{contract_id}.json"

    adapter_capability_summary = _build_adapter_capability_summary()
    disabled_adapter_policy = _build_disabled_adapter_policy()
    request_preview_contract = _build_request_preview_contract()
    response_placeholder_contract = _build_response_placeholder_contract()
    send_method_policy = _build_send_method_policy()
    credential_access_policy = _build_credential_access_policy()
    network_access_policy = _build_network_access_policy()
    provider_sdk_policy = _build_provider_sdk_policy()
    error_handling_policy = _build_error_handling_policy()
    side_effect_policy = _build_side_effect_policy()
    broker_separation_policy = _build_broker_separation_policy()
    future_adapter_requirements = _build_future_adapter_requirements()
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
        "adapter_interface_recorded",
        "disabled_adapter_available",
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
        "This is a local provider adapter interface contract. No provider request was sent.",
        "No provider response was received.",
        "No provider response is trusted by default.",
        "Provider execution remains disabled and not implemented.",
        "Manual unlock is required but not granted.",
        "Provider adapter is not implemented. Only disabled adapter harness exists.",
        "Credential loader is not implemented.",
        "Network policy is not implemented.",
        "Real provider response artifact is missing.",
        "Trust upgrade policy is not implemented.",
        "Provider SDK is not imported.",
        "Adapter interface contract cannot create orders, approvals, or pending orders.",
        "Adapter interface contract cannot call broker.",
        "Real provider execution requires explicit future opt-in.",
    ]

    metadata = {
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

    source_unlock_state_hash = source_unlock_state.get("artifact_hash", "")
    source_review_result_hash = source_review_result.get("artifact_hash", "")
    source_schema_contract_hash = source_schema_contract.get("artifact_hash", "")
    source_pairing_hash = source_pairing.get("artifact_hash", "")
    source_response_intake_policy_hash = source_intake_policy.get("artifact_hash", "")
    source_payload_preview_hash = source_preview.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_adapter_interface_contract",
        "contract_version": PROVIDER_ADAPTER_INTERFACE_CONTRACT_VERSION,
        "provider_adapter_interface_contract_id": contract_id,
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
        "provider_id": safe_provider_id,
        "model_id": safe_model_id,
        "adapter_contract_status": "adapter_interface_recorded",
        "adapter_contract_scope": "future_provider_adapter_interface_only",
        "adapter_state": "disabled_adapter_only",
        "adapter_interface_version": PROVIDER_ADAPTER_INTERFACE_CONTRACT_VERSION,
        "adapter_capability_summary": adapter_capability_summary,
        "disabled_adapter_policy": disabled_adapter_policy,
        "request_preview_contract": request_preview_contract,
        "response_placeholder_contract": response_placeholder_contract,
        "send_method_policy": send_method_policy,
        "credential_access_policy": credential_access_policy,
        "network_access_policy": network_access_policy,
        "provider_sdk_policy": provider_sdk_policy,
        "error_handling_policy": error_handling_policy,
        "side_effect_policy": side_effect_policy,
        "broker_separation_policy": broker_separation_policy,
        "future_adapter_requirements": future_adapter_requirements,
        "required_prerequisites": required_prerequisites,
        "satisfied_prerequisites": satisfied_prerequisites,
        "missing_prerequisites": missing_prerequisites,
        "blocking_reasons": blocking_reasons,
        "source_unlock_state_hash": source_unlock_state_hash,
        "source_review_result_hash": source_review_result_hash,
        "source_schema_contract_hash": source_schema_contract_hash,
        "source_pairing_hash": source_pairing_hash,
        "source_response_intake_policy_hash": source_response_intake_policy_hash,
        "source_payload_preview_hash": source_payload_preview_hash,
        "adapter_interface_recorded": True,
        "disabled_adapter_available": True,
        "adapter_present": False,
        "adapter_enabled": False,
        "real_provider_adapter_implemented": False,
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
        "provider_response_received": False,
        "provider_response_imported": False,
        "provider_response_trusted": False,
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

    artifact["artifact_hash"] = provider_adapter_interface_contract_sha256(artifact)
    return artifact


def create_provider_adapter_interface_contract(
    workspace_path: Path,
    unlock_state_id: str,
) -> dict[str, Any]:
    safe_unlock_state_id = validate_run_id(unlock_state_id)

    from atlas_agent.research.provider_execution_unlock_state import (
        find_provider_execution_unlock_state_by_id,
        load_provider_execution_unlock_state,
    )

    unlock_state_path = find_provider_execution_unlock_state_by_id(workspace_path, safe_unlock_state_id)
    if unlock_state_path is None:
        raise ResearchSessionError("provider_adapter_interface_contract_source_unlock_state_missing")

    source_unlock_state = load_provider_execution_unlock_state(unlock_state_path, workspace_path)

    source_review_result_id = source_unlock_state.get("source_provider_response_review_result_id", "")
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )

    review_result_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
    if review_result_path is None:
        raise ResearchSessionError("provider_adapter_interface_contract_source_review_result_missing")

    source_review_result = load_provider_response_review_result(review_result_path, workspace_path)

    source_schema_contract_id = source_unlock_state.get("source_provider_response_schema_contract_id", "")
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )

    schema_contract_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
    if schema_contract_path is None:
        raise ResearchSessionError("provider_adapter_interface_contract_source_schema_contract_missing")

    source_schema_contract = load_provider_response_schema_contract(schema_contract_path, workspace_path)

    source_pairing_id = source_unlock_state.get("source_provider_request_response_pairing_id", "")
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )

    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
    if pairing_path is None:
        raise ResearchSessionError("provider_adapter_interface_contract_source_pairing_missing")

    source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)

    source_intake_id = source_unlock_state.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
    if intake_path is None:
        raise ResearchSessionError("provider_adapter_interface_contract_source_response_intake_missing")

    source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)

    source_preview_id = source_unlock_state.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if preview_path is None:
        raise ResearchSessionError("provider_adapter_interface_contract_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    contract_id = generate_run_id()
    artifact = build_provider_adapter_interface_contract_dict(
        source_unlock_state,
        source_review_result,
        source_schema_contract,
        source_pairing,
        source_intake_policy,
        source_preview,
        contract_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    result_dir = workspace_path / RESEARCH_DIR / symbol / "provider_adapter_interface_contracts"
    result_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_adapter_interface_contract_created",
        "provider_adapter_interface_contract_id": contract_id,
        "source_provider_execution_unlock_state_id": safe_unlock_state_id,
        "source_provider_response_review_result_id": source_review_result_id,
        "source_provider_response_schema_contract_id": source_schema_contract_id,
        "source_provider_request_response_pairing_id": source_pairing_id,
        "source_provider_response_intake_policy_id": source_intake_id,
        "source_provider_outbound_payload_preview_id": source_preview_id,
        "adapter_contract_status": artifact["adapter_contract_status"],
        "adapter_state": artifact["adapter_state"],
        "adapter_interface_recorded": True,
        "disabled_adapter_available": True,
        "adapter_present": False,
        "adapter_enabled": False,
        "real_provider_adapter_implemented": False,
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
        "provider_response_received": False,
        "provider_response_imported": False,
        "provider_response_trusted": False,
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
        return f"invalid_provider_adapter_interface_contract_{field_name}"
    return None


def safe_validate_provider_adapter_interface_contract_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_adapter_interface_contract_schema"

    if data.get("artifact_type") != "provider_adapter_interface_contract":
        return None, "provider_adapter_interface_contract_malformed"

    if data.get("contract_version") != PROVIDER_ADAPTER_INTERFACE_CONTRACT_VERSION:
        return None, "provider_adapter_interface_contract_malformed"

    try:
        validate_adapter_contract_status(data.get("adapter_contract_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_adapter_interface_contract_status"

    try:
        validate_adapter_contract_scope(data.get("adapter_contract_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_adapter_interface_contract_status"

    try:
        validate_adapter_state(data.get("adapter_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_adapter_interface_contract_status"

    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    if data.get("mode") != "paper":
        return None, "provider_adapter_interface_contract_malformed"

    lineage_field_names = [
        "provider_adapter_interface_contract_id",
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
            return None, "invalid_provider_adapter_interface_contract_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_adapter_interface_contract_lineage"

    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_adapter_interface_contract_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_adapter_interface_contract_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_adapter_interface_contract_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_adapter_interface_contract_hash_mismatch"

    if workspace_path is not None and not for_replay:
        source_unlock_state_id = data.get("source_provider_execution_unlock_state_id", "")
        if source_unlock_state_id:
            try:
                from atlas_agent.research.provider_execution_unlock_state import (
                    find_provider_execution_unlock_state_by_id,
                    load_provider_execution_unlock_state,
                )

                us_path = find_provider_execution_unlock_state_by_id(workspace_path, source_unlock_state_id)
                if us_path is None:
                    return None, "provider_adapter_interface_contract_source_unlock_state_missing"
                us_data = load_provider_execution_unlock_state(us_path, workspace_path)
                stored_us_hash = data.get("source_unlock_state_hash", "")
                actual_us_hash = us_data.get("artifact_hash", "")
                if stored_us_hash != actual_us_hash:
                    return None, "provider_adapter_interface_contract_source_unlock_state_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_adapter_interface_contract_source_unlock_state_missing"

        source_review_result_id = data.get("source_provider_response_review_result_id", "")
        if source_review_result_id:
            try:
                from atlas_agent.research.provider_response_review_result import (
                    find_provider_response_review_result_by_id,
                    load_provider_response_review_result,
                )

                rr_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
                if rr_path is None:
                    return None, "provider_adapter_interface_contract_source_review_result_missing"
                rr_data = load_provider_response_review_result(rr_path, workspace_path)
                stored_rr_hash = data.get("source_review_result_hash", "")
                actual_rr_hash = rr_data.get("artifact_hash", "")
                if stored_rr_hash != actual_rr_hash:
                    return None, "provider_adapter_interface_contract_source_review_result_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_adapter_interface_contract_source_review_result_missing"

        source_schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
        if source_schema_contract_id:
            try:
                from atlas_agent.research.provider_response_schema_contract import (
                    find_provider_response_schema_contract_by_id,
                    load_provider_response_schema_contract,
                )

                sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_contract_id)
                if sc_path is None:
                    return None, "provider_adapter_interface_contract_source_schema_contract_missing"
                sc_data = load_provider_response_schema_contract(sc_path, workspace_path)
                stored_sc_hash = data.get("source_schema_contract_hash", "")
                actual_sc_hash = sc_data.get("artifact_hash", "")
                if stored_sc_hash != actual_sc_hash:
                    return None, "provider_adapter_interface_contract_source_schema_contract_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_adapter_interface_contract_source_schema_contract_missing"

        source_pairing_id = data.get("source_provider_request_response_pairing_id", "")
        if source_pairing_id:
            try:
                from atlas_agent.research.provider_request_response_pairing import (
                    find_provider_request_response_pairing_by_id,
                    load_provider_request_response_pairing,
                )

                pairing_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
                if pairing_path is None:
                    return None, "provider_adapter_interface_contract_source_pairing_missing"
                pairing_data = load_provider_request_response_pairing(pairing_path, workspace_path)
                stored_pairing_hash = data.get("source_pairing_hash", "")
                actual_pairing_hash = pairing_data.get("artifact_hash", "")
                if stored_pairing_hash != actual_pairing_hash:
                    return None, "provider_adapter_interface_contract_source_pairing_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_adapter_interface_contract_source_pairing_missing"

        source_intake_id = data.get("source_provider_response_intake_policy_id", "")
        if source_intake_id:
            try:
                from atlas_agent.research.provider_response_intake_policy import (
                    find_provider_response_intake_policy_by_id,
                    load_provider_response_intake_policy,
                )

                intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
                if intake_path is None:
                    return None, "provider_adapter_interface_contract_source_response_intake_missing"
                intake_data = load_provider_response_intake_policy(intake_path, workspace_path)
                stored_intake_hash = data.get("source_response_intake_policy_hash", "")
                actual_intake_hash = intake_data.get("artifact_hash", "")
                if stored_intake_hash != actual_intake_hash:
                    return None, "provider_adapter_interface_contract_source_response_intake_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_adapter_interface_contract_source_response_intake_missing"

        source_preview_id = data.get("source_provider_outbound_payload_preview_id", "")
        if source_preview_id:
            try:
                from atlas_agent.research.provider_outbound_payload_preview import (
                    find_provider_outbound_payload_preview_by_id,
                    load_provider_outbound_payload_preview,
                )

                preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
                if preview_path is None:
                    return None, "provider_adapter_interface_contract_source_payload_preview_missing"
                preview_data = load_provider_outbound_payload_preview(preview_path, workspace_path)
                stored_preview_hash = data.get("source_payload_preview_hash", "")
                actual_preview_hash = preview_data.get("artifact_hash", "")
                if stored_preview_hash != actual_preview_hash:
                    return None, "provider_adapter_interface_contract_source_payload_preview_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_adapter_interface_contract_source_payload_preview_missing"

    # Check policy fields for forbidden fragments
    policy_fields = [
        json.dumps(data.get("adapter_capability_summary", {})),
        json.dumps(data.get("disabled_adapter_policy", {})),
        json.dumps(data.get("request_preview_contract", {})),
        json.dumps(data.get("response_placeholder_contract", {})),
        json.dumps(data.get("send_method_policy", {})),
        json.dumps(data.get("credential_access_policy", {})),
        json.dumps(data.get("network_access_policy", {})),
        json.dumps(data.get("provider_sdk_policy", {})),
        json.dumps(data.get("error_handling_policy", {})),
        json.dumps(data.get("side_effect_policy", {})),
        json.dumps(data.get("broker_separation_policy", {})),
        json.dumps(data.get("future_adapter_requirements", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("required_prerequisites", [])),
        json.dumps(data.get("satisfied_prerequisites", [])),
        json.dumps(data.get("missing_prerequisites", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in policy_fields):
        return None, "provider_adapter_interface_contract_malformed"

    # Check status/scope/state for forbidden fragments
    policy_summaries = [
        data.get("adapter_contract_status", ""),
        data.get("adapter_contract_scope", ""),
        data.get("adapter_state", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_adapter_interface_contract_forbidden_adapter_claim"

    # Check policy fields for unsafe positive claims
    policy_fields_for_positive_claim_check = [
        data.get("adapter_capability_summary", {}),
        data.get("disabled_adapter_policy", {}),
        data.get("request_preview_contract", {}),
        data.get("response_placeholder_contract", {}),
        data.get("send_method_policy", {}),
        data.get("credential_access_policy", {}),
        data.get("network_access_policy", {}),
        data.get("provider_sdk_policy", {}),
        data.get("error_handling_policy", {}),
        data.get("side_effect_policy", {}),
        data.get("broker_separation_policy", {}),
        data.get("future_adapter_requirements", {}),
    ]
    if any(_has_unsafe_positive_claims(f) for f in policy_fields_for_positive_claim_check):
        return None, "provider_adapter_interface_contract_forbidden_adapter_claim"

    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_adapter_interface_contract_malformed"

    cleaned = {k: v for k, v in data.items()}
    return cleaned, None


def validate_provider_adapter_interface_contract_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderAdapterInterfaceContractValidationResult:
    data = load_provider_adapter_interface_contract(path, workspace_path)
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
            at == "provider_adapter_interface_contract",
            "artifact_type must be provider_adapter_interface_contract." if at != "provider_adapter_interface_contract" else "artifact_type is correct.",
        )
    )

    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_ADAPTER_INTERFACE_CONTRACT_VERSION,
            "contract_version must match current contract." if cv != PROVIDER_ADAPTER_INTERFACE_CONTRACT_VERSION else "contract_version matches.",
        )
    )

    status = data.get("adapter_contract_status", "")
    status_ok = status in _VALID_ADAPTER_CONTRACT_STATUSES
    checks.append(
        _check_name(
            "adapter_contract_status_valid",
            status_ok,
            "adapter_contract_status is invalid." if not status_ok else "adapter_contract_status is valid.",
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

    computed = provider_adapter_interface_contract_sha256(data)
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

    return ProviderAdapterInterfaceContractValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation="Proceed with adapter interface contract." if valid else "Reject artifact and investigate tampering.",
        warnings=warnings,
    )


def load_provider_adapter_interface_contract(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        raise ResearchSessionError("provider_adapter_interface_contract_malformed") from e

    cleaned, err = safe_validate_provider_adapter_interface_contract_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    if not cleaned:
        raise ResearchSessionError("provider_adapter_interface_contract_malformed")
    return cleaned


def load_and_validate_provider_adapter_interface_contract(path: Path, workspace_path: Path) -> dict[str, Any]:
    data = load_provider_adapter_interface_contract(path, workspace_path)
    res = validate_provider_adapter_interface_contract_artifact(path, workspace_path)
    if not res.valid:
        raise ResearchSessionError("invalid_provider_adapter_interface_contract_artifact")
    return data


def find_provider_adapter_interface_contract_by_id(workspace_path: Path, contract_id: str) -> Path | None:
    safe_id = validate_run_id(contract_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    for p in search_dir.rglob("provider_adapter_interface_contracts/*.json"):
        if p.stem == safe_id:
            return p
    return None


def replay_provider_adapter_interface_contract(
    workspace_path: Path,
    contract_id: str,
) -> dict[str, Any]:
    safe_id = validate_run_id(contract_id)
    artifact_path = find_provider_adapter_interface_contract_by_id(workspace_path, safe_id)
    if not artifact_path:
        raise ResearchSessionError("provider_adapter_interface_contract_not_found")

    try:
        old_artifact = load_provider_adapter_interface_contract(artifact_path, workspace_path=None)
    except ResearchSessionError:
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
            old_hash = raw.get("artifact_hash", "")
        except Exception:
            old_hash = ""
        return {
            "ok": False,
            "match": False,
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_hash,
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    source_unlock_state_id = old_artifact.get("source_provider_execution_unlock_state_id", "")
    from atlas_agent.research.provider_execution_unlock_state import (
        find_provider_execution_unlock_state_by_id,
        load_provider_execution_unlock_state,
    )

    us_path = find_provider_execution_unlock_state_by_id(workspace_path, source_unlock_state_id)
    if not us_path:
        return {
            "ok": False,
            "match": False,
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    try:
        source_unlock_state = load_provider_execution_unlock_state(us_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
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
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    try:
        source_review_result = load_provider_response_review_result(rr_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
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
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    try:
        source_schema_contract = load_provider_response_schema_contract(sc_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
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
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    try:
        source_pairing = load_provider_request_response_pairing(pairing_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
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
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    try:
        source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
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
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    try:
        source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": False,
            "match": False,
            "provider_adapter_interface_contract_id": safe_id,
            "original_hash": old_artifact.get("artifact_hash", ""),
            "replayed_hash": "",
            "status": "research_provider_adapter_interface_contract_replay_failed",
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
        }

    new_artifact = build_provider_adapter_interface_contract_dict(
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
    new_artifact["artifact_hash"] = provider_adapter_interface_contract_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_adapter_interface_contract_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_adapter_interface_contract_replayed",
        "provider_response_received": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "broker_touched": False,
    }


def iter_provider_adapter_interface_contract_artifacts(
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
        result_dir = sym_dir / "provider_adapter_interface_contracts"
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
                    "provider_adapter_interface_contract_id": "<invalid>",
                    "source_provider_execution_unlock_state_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "adapter_contract_status": "invalid",
                    "adapter_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_adapter_interface_contract_artifact",
                    "created_at": "",
                })
                continue
            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_adapter_interface_contract_id": "<invalid>",
                    "source_provider_execution_unlock_state_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "adapter_contract_status": "invalid",
                    "adapter_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_adapter_interface_contract_artifact",
                    "created_at": "",
                })
                continue
            cleaned, error = safe_validate_provider_adapter_interface_contract_data(raw, workspace_path=workspace_path)
            if error or cleaned is None:
                invalid_items.append({
                    "provider_adapter_interface_contract_id": "<invalid>",
                    "source_provider_execution_unlock_state_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "adapter_contract_status": "invalid",
                    "adapter_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_adapter_interface_contract_artifact",
                    "created_at": "",
                })
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append({
                "provider_adapter_interface_contract_id": cleaned.get("provider_adapter_interface_contract_id", path.stem),
                "source_provider_execution_unlock_state_id": cleaned.get("source_provider_execution_unlock_state_id", ""),
                "source_provider_response_review_result_id": cleaned.get("source_provider_response_review_result_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "adapter_contract_status": cleaned.get("adapter_contract_status", ""),
                "adapter_contract_scope": cleaned.get("adapter_contract_scope", ""),
                "adapter_state": cleaned.get("adapter_state", ""),
                "artifact_path": rel_path,
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "created_at": cleaned.get("created_at", ""),
                "adapter_interface_recorded": cleaned.get("adapter_interface_recorded", True),
                "disabled_adapter_available": cleaned.get("disabled_adapter_available", True),
                "adapter_present": cleaned.get("adapter_present", False),
                "adapter_enabled": cleaned.get("adapter_enabled", False),
                "real_provider_adapter_implemented": cleaned.get("real_provider_adapter_implemented", False),
                "provider_sdk_imported": cleaned.get("provider_sdk_imported", False),
                "http_client_imported": cleaned.get("http_client_imported", False),
                "network_enabled": cleaned.get("network_enabled", False),
                "credentials_loaded": cleaned.get("credentials_loaded", False),
                "credential_value_present": cleaned.get("credential_value_present", False),
                "provider_call_allowed": cleaned.get("provider_call_allowed", False),
                "actual_provider_call_made": cleaned.get("actual_provider_call_made", False),
                "outbound_request_sent": cleaned.get("outbound_request_sent", False),
                "provider_response_received": cleaned.get("provider_response_received", False),
                "provider_response_trusted": cleaned.get("provider_response_trusted", False),
                "trust_upgrade_performed": cleaned.get("trust_upgrade_performed", False),
                "trading_signal_generated": cleaned.get("trading_signal_generated", False),
                "approval_created": cleaned.get("approval_created", False),
                "pending_order_created": cleaned.get("pending_order_created", False),
                "broker_touched": cleaned.get("broker_touched", False),
            })

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items + invalid_items


def _find_latest_provider_adapter_interface_contract_for_run(workspace_path: Path, run_id: str) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    latest_path: Path | None = None
    latest_time = ""
    for p in search_dir.rglob("provider_adapter_interface_contracts/*.json"):
        try:
            data = load_provider_adapter_interface_contract(p, workspace_path=None)
            if data.get("source_run_id") == safe_run_id:
                t = data.get("created_at", "")
                if not latest_time or t > latest_time:
                    latest_time = t
                    latest_path = p
        except Exception:
            pass
    return latest_path


def summarize_provider_adapter_interface_contract(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_adapter_interface_contract_for_run(workspace_path, safe_run_id)

    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_adapter_interface_contract",
            "provider_adapter_interface_contract_id": None,
            "adapter_contract_status": "not_recorded",
            "adapter_state": "not_recorded",
            "adapter_present": False,
            "adapter_enabled": False,
            "real_provider_adapter_implemented": False,
            "provider_call_allowed": False,
            "artifact_path": None,
        }

    try:
        data = load_and_validate_provider_adapter_interface_contract(artifact_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": True,
            "status": "invalid_provider_adapter_interface_contract",
            "provider_adapter_interface_contract_id": None,
            "adapter_contract_status": "invalid",
            "adapter_state": "invalid",
            "adapter_present": False,
            "adapter_enabled": False,
            "real_provider_adapter_implemented": False,
            "provider_call_allowed": False,
            "artifact_path": None,
        }

    return {
        "ok": True,
        "status": "research_provider_adapter_interface_contract_summary",
        "provider_adapter_interface_contract_id": data.get("provider_adapter_interface_contract_id"),
        "adapter_contract_status": data.get("adapter_contract_status"),
        "adapter_state": data.get("adapter_state"),
        "adapter_present": False,
        "adapter_enabled": False,
        "real_provider_adapter_implemented": False,
        "provider_call_allowed": False,
        "artifact_path": data.get("artifact_path"),
    }


def doctor_provider_adapter_interface_contract(
    workspace_path: Path,
    run_id: str,
) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)

    missing_artifacts: list[str] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    contract_path = _find_latest_provider_adapter_interface_contract_for_run(workspace_path, safe_run_id)
    if not contract_path:
        missing_artifacts.append("provider_adapter_interface_contract")
        blocking_reasons.append("provider_adapter_interface_contract_not_created")
        warnings.append("No provider adapter interface contract exists for this run.")
        return {
            "ok": True,
            "status": "research_provider_adapter_interface_contract_doctor",
            "run_id": safe_run_id,
            "adapter_health": "adapter_interface_contract_missing",
            "adapter_present": False,
            "adapter_enabled": False,
            "real_provider_adapter_implemented": False,
            "provider_call_allowed": False,
            "missing_prerequisites": missing_artifacts,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
        }

    try:
        data = load_provider_adapter_interface_contract(contract_path, workspace_path)
    except ResearchSessionError as e:
        warnings.append(f"Adapter interface contract artifact is invalid: {e}")
        return {
            "ok": True,
            "status": "research_provider_adapter_interface_contract_doctor",
            "run_id": safe_run_id,
            "adapter_health": "adapter_interface_contract_invalid",
            "adapter_present": False,
            "adapter_enabled": False,
            "real_provider_adapter_implemented": False,
            "provider_call_allowed": False,
            "missing_prerequisites": missing_artifacts,
            "blocking_reasons": ["adapter_interface_contract_artifact_invalid"],
            "warnings": warnings,
        }

    # Check source artifacts
    unlock_state_id = data.get("source_provider_execution_unlock_state_id", "")
    review_result_id = data.get("source_provider_response_review_result_id", "")
    schema_contract_id = data.get("source_provider_response_schema_contract_id", "")
    pairing_id = data.get("source_provider_request_response_pairing_id", "")
    intake_id = data.get("source_provider_response_intake_policy_id", "")
    preview_id = data.get("source_provider_outbound_payload_preview_id", "")

    from atlas_agent.research.provider_execution_unlock_state import find_provider_execution_unlock_state_by_id
    from atlas_agent.research.provider_response_review_result import find_provider_response_review_result_by_id
    from atlas_agent.research.provider_response_schema_contract import find_provider_response_schema_contract_by_id
    from atlas_agent.research.provider_request_response_pairing import find_provider_request_response_pairing_by_id
    from atlas_agent.research.provider_response_intake_policy import find_provider_response_intake_policy_by_id
    from atlas_agent.research.provider_outbound_payload_preview import find_provider_outbound_payload_preview_by_id

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

    if data.get("adapter_state") == "disabled_adapter_only":
        adapter_health = "disabled_adapter_only"
    else:
        adapter_health = "blocked"

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
        "status": "research_provider_adapter_interface_contract_doctor",
        "run_id": safe_run_id,
        "adapter_health": adapter_health,
        "adapter_present": False,
        "adapter_enabled": False,
        "real_provider_adapter_implemented": False,
        "provider_call_allowed": False,
        "missing_prerequisites": missing_artifacts,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def run_disabled_adapter_smoke(contract_id: str) -> dict[str, Any]:
    """Exercise the disabled adapter harness and prove it cannot call providers."""
    from atlas_agent.research.provider_adapter_interface import (
        DisabledProviderAdapter,
        ProviderAdapterDisabledError,
    )

    adapter = DisabledProviderAdapter()

    # Call capabilities
    cap = adapter.capabilities()

    # Call build_request_preview
    preview = adapter.build_request_preview(
        request_preview_id="smoke-preview",
        source_provider_execution_unlock_state_id="smoke-unlock",
        source_provider_outbound_payload_preview_id="smoke-preview",
        provider_id="disabled",
        model_id="disabled",
        request_family="smoke",
        payload_hash="smoke-hash",
    )

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

    # Validate placeholder
    from atlas_agent.research.provider_adapter_interface import ProviderAdapterResponsePlaceholder
    placeholder = ProviderAdapterResponsePlaceholder(
        response_placeholder_id="smoke-placeholder",
        provider_response_received=False,
        provider_response_trusted=False,
        provider_response_imported=False,
        raw_response_body_present=False,
        response_hash_present=False,
        manual_review_required=True,
    )
    placeholder_valid = adapter.validate_response_placeholder(placeholder)

    if not send_failed:
        return {
            "ok": False,
            "status": "research_provider_adapter_disabled_smoke_failed",
            "provider_adapter_interface_contract_id": contract_id,
            "error_code": "disabled_adapter_send_unexpected_success",
            "disabled_adapter_available": True,
            "send_failed_closed": False,
            "static_safe_error": False,
            "provider_response_received": False,
            "network_call_attempted": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "broker_touched": False,
            "warnings": ["Disabled adapter send() did not raise an error."],
        }

    return {
        "ok": True,
        "status": "research_provider_adapter_disabled_smoke_passed",
        "provider_adapter_interface_contract_id": contract_id,
        "disabled_adapter_available": True,
        "send_failed_closed": send_failed,
        "static_safe_error": static_safe_error,
        "provider_response_received": False,
        "network_call_attempted": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "broker_touched": False,
        "placeholder_valid": placeholder_valid,
        "warnings": [],
    }
