# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_mock_response_trust_decision_blocker.py
# PURPOSE: Mock pipeline, step 3: the BLOCKER. Records every reason a candidate response
#          must not be trusted. A non-empty blocker set halts the pipeline.
# DEPS:    research.provider_mock_response_review_sandbox, research.sandbox_contracts
# ==============================================================================

"""Provider mock response trust decision blocker — local, configless mock response trust blocker artifact.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider mock response trust decision blocker artifacts. It does NOT implement any real trust
decision, does NOT upgrade trust, does NOT grant manual approval, does NOT review raw provider
responses, does NOT read external files, does NOT accept stdin input, does NOT call any real
provider, does NOT perform network requests, does NOT read API keys, does NOT read os.environ,
does NOT load .env.atlas, does NOT import provider SDKs, does NOT receive real provider responses,
does NOT trust provider responses, does NOT trust mock responses, does NOT create trading signals,
does NOT create approvals or pending orders, does NOT authorize live trading, and does NOT touch
brokers.

A provider mock response trust decision blocker is derived ONLY from an existing
provider_mock_response_review_sandbox artifact. It represents a local red-light artifact that
explicitly records the absence of any valid trust decision, trust upgrade, or trading authorization.
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

PROVIDER_MOCK_RESPONSE_TRUST_DECISION_BLOCKER_VERSION = "research_provider_mock_response_trust_decision_blocker_v1"

_PROVIDER_MOCK_RESPONSE_TRUST_DECISION_BLOCKER_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_TRUST_DECISION_BLOCKER_STATUSES = {
    "trust_decision_blocker_recorded",
    "trust_decision_blocker_invalid",
}

_VALID_TRUST_DECISION_BLOCKER_SCOPES = {
    "offline_mock_response_trust_decision_blocker_only",
}

_VALID_TRUST_DECISION_BLOCKER_STATES = {
    "trust_decision_blocked_untrusted",
    "mock_review_sandbox_not_sufficient_for_trust",
    "manual_review_required_before_future_trust",
    "trust_upgrade_not_implemented",
    "mock_only_trust_blocked",
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
]

_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE = [
    "trust_decision_blocker_recorded",
    "trust_source_verified",
    "trust_blocker_active",
    "trust_decision_required",
    "trust_decision_explicitly_blocked",
    "mock_only",
    "sandbox_only",
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
)


@dataclass(frozen=True)
class ProviderMockResponseTrustDecisionBlockerValidationResult:
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
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_model")
    return value


def validate_trust_decision_blocker_status(value: str) -> str:
    if not value or value not in _VALID_TRUST_DECISION_BLOCKER_STATUSES:
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_status")
    return value


def validate_trust_decision_blocker_scope(value: str) -> str:
    if not value or value not in _VALID_TRUST_DECISION_BLOCKER_SCOPES:
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_status")
    return value


def validate_trust_decision_blocker_state(value: str) -> str:
    if not value or value not in _VALID_TRUST_DECISION_BLOCKER_STATES:
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_mock_response_trust_decision_blocker_status")
    return value


def provider_mock_response_trust_decision_blocker_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_MOCK_RESPONSE_TRUST_DECISION_BLOCKER_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE:
        if data.get(flag) is not False:
            return "provider_mock_response_trust_decision_blocker_impossible_boolean"
    for flag in _BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE:
        if data.get(flag) is not True:
            return "provider_mock_response_trust_decision_blocker_impossible_boolean"
    return None


def _build_trust_source_summary() -> dict[str, Any]:
    return {
        "source_artifact_type": "provider_mock_response_review_sandbox",
        "source_provider_id": "mock",
        "source_is_mock": True,
        "source_is_real_provider_response": False,
        "source_review_sandbox_recorded": True,
        "source_review_sandbox_trusted": False,
        "source_manual_review_completed": False,
        "source_provider_response_trusted": False,
        "source_can_create_orders": False,
        "source_can_call_broker": False,
    }


def _build_trust_blocker_summary() -> dict[str, Any]:
    return {
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
    }


def _build_trust_decision_policy() -> dict[str, Any]:
    return {
        "trust_decision_required_before_any_future_use": True,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_denied": False,
        "trust_decision_explicitly_blocked": True,
        "mock_review_sandbox_does_not_create_trust_decision": True,
        "trust_decision_requires_future_command": True,
        "trust_decision_requires_future_policy": True,
        "trust_decision_cannot_be_inferred_from_mock": True,
    }


def _build_trust_upgrade_policy() -> dict[str, Any]:
    return {
        "trust_upgrade_available": False,
        "trust_upgrade_performed": False,
        "trust_upgrade_not_implemented": True,
        "mock_review_sandbox_cannot_upgrade_trust": True,
        "mock_import_candidate_cannot_upgrade_trust": True,
        "mock_response_simulation_cannot_upgrade_trust": True,
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
        "trust_blocker_is_not_trading_signal": True,
        "trust_blocker_cannot_create_pending_order": True,
        "trust_blocker_cannot_approve_order": True,
        "trust_blocker_cannot_submit_order": True,
        "trust_blocker_cannot_modify_risk": True,
        "trust_blocker_cannot_call_broker": True,
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
        "trust_decision_blocker_writes_only_blocker_artifact": True,
        "trust_decision_blocker_writes_events": True,
        "trust_decision_blocker_touches_broker": False,
    }


def build_provider_mock_response_trust_decision_blocker_dict(
    source_review_sandbox: dict[str, Any],
    source_mock_import_candidate: dict[str, Any],
    source_mock_response_simulation: dict[str, Any],
    source_adapter_interface_contract: dict[str, Any],
    source_unlock_state: dict[str, Any],
    source_review_result: dict[str, Any],
    source_schema_contract: dict[str, Any],
    source_pairing: dict[str, Any],
    source_intake_policy: dict[str, Any],
    source_preview: dict[str, Any],
    source_opt_in_policy: dict[str, Any],
    source_preflight_freeze: dict[str, Any],
    source_readiness_report: dict[str, Any],
    source_audit_packet: dict[str, Any],
    source_execution_state: dict[str, Any],
    source_dry_run: dict[str, Any],
    source_call_plan: dict[str, Any],
    blocker_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(blocker_id, "invalid_provider_mock_response_trust_decision_blocker_id")

    safe_symbol = validate_contract_symbol(source_review_sandbox.get("symbol", "UNKNOWN"))
    safe_model_id = validate_model_id(source_review_sandbox.get("model_id", "unknown"))
    safe_source_provider_id = validate_provider_id(source_review_sandbox.get("source_provider_id", "mock"))

    now = datetime.now(UTC).isoformat()

    symbol_safe = safe_symbol.replace("/", "_")
    artifact_path = (
        workspace_path
        / RESEARCH_DIR
        / symbol_safe
        / "provider_mock_response_trust_decision_blockers"
        / f"{blocker_id}.json"
    )

    trust_decision_blocker_status = "trust_decision_blocker_recorded"
    trust_decision_blocker_scope = "offline_mock_response_trust_decision_blocker_only"
    trust_decision_blocker_state = "trust_decision_blocked_untrusted"

    artifact = {
        "artifact_type": "provider_mock_response_trust_decision_blocker",
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "contract_version": PROVIDER_MOCK_RESPONSE_TRUST_DECISION_BLOCKER_VERSION,
        "provider_mock_response_trust_decision_blocker_id": blocker_id,
        "source_provider_mock_response_review_sandbox_id": source_review_sandbox.get("provider_mock_response_review_sandbox_id", ""),
        "source_provider_mock_response_import_candidate_id": source_mock_import_candidate.get("provider_mock_response_import_candidate_id", ""),
        "source_provider_mock_response_simulation_id": source_mock_response_simulation.get("provider_mock_response_simulation_id", ""),
        "source_provider_adapter_interface_contract_id": source_adapter_interface_contract.get("provider_adapter_interface_contract_id", ""),
        "source_provider_execution_unlock_state_id": source_unlock_state.get("provider_execution_unlock_state_id", ""),
        "source_provider_response_review_result_id": source_review_result.get("provider_response_review_result_id", ""),
        "source_provider_response_schema_contract_id": source_schema_contract.get("provider_response_schema_contract_id", ""),
        "source_provider_request_response_pairing_id": source_pairing.get("provider_request_response_pairing_id", ""),
        "source_provider_response_intake_policy_id": source_intake_policy.get("provider_response_intake_policy_id", ""),
        "source_provider_outbound_payload_preview_id": source_preview.get("provider_outbound_payload_preview_id", ""),
        "source_provider_credential_boundary_id": source_preview.get("source_provider_credential_boundary_id", ""),
        "source_provider_opt_in_policy_id": source_opt_in_policy.get("provider_opt_in_policy_id", ""),
        "source_provider_preflight_freeze_id": source_preflight_freeze.get("provider_preflight_freeze_id", ""),
        "source_provider_execution_readiness_report_id": source_readiness_report.get("provider_execution_readiness_report_id", ""),
        "source_provider_execution_audit_packet_id": source_audit_packet.get("provider_execution_audit_packet_id", ""),
        "source_provider_execution_state_id": source_execution_state.get("provider_execution_state_id", ""),
        "source_provider_execution_dry_run_id": source_dry_run.get("provider_execution_dry_run_id", ""),
        "source_provider_call_plan_id": source_call_plan.get("provider_call_plan_id", ""),
        "source_sandbox_request_id": source_call_plan.get("source_sandbox_request_id", ""),
        "source_prompt_packet_id": source_call_plan.get("source_prompt_packet_id", ""),
        "source_run_id": source_call_plan.get("source_run_id", ""),
        "symbol": safe_symbol,
        "mode": "paper",
        "provider_id": "mock",
        "model_id": safe_model_id,
        "source_provider_id": safe_source_provider_id,
        "trust_decision_blocker_status": trust_decision_blocker_status,
        "trust_decision_blocker_scope": trust_decision_blocker_scope,
        "trust_decision_blocker_state": trust_decision_blocker_state,
        "trust_source_summary": _build_trust_source_summary(),
        "trust_blocker_summary": _build_trust_blocker_summary(),
        "trust_decision_policy": _build_trust_decision_policy(),
        "trust_upgrade_policy": _build_trust_upgrade_policy(),
        "manual_review_policy": _build_manual_review_policy(),
        "mock_response_trust_policy": _build_mock_response_trust_policy(),
        "real_provider_trust_boundary_policy": _build_real_provider_trust_boundary_policy(),
        "trading_authorization_policy": _build_trading_authorization_policy(),
        "broker_separation_policy": _build_broker_separation_policy(),
        "network_boundary_policy": _build_network_boundary_policy(),
        "credential_boundary_policy": _build_credential_boundary_policy(),
        "side_effect_policy": _build_side_effect_policy(),
        "source_mock_review_sandbox_hash": source_review_sandbox.get("artifact_hash", ""),
        "source_mock_import_candidate_hash": source_mock_import_candidate.get("artifact_hash", ""),
        "source_mock_response_simulation_hash": source_mock_response_simulation.get("artifact_hash", ""),
        "source_adapter_interface_contract_hash": source_adapter_interface_contract.get("artifact_hash", ""),
        "source_unlock_state_hash": source_unlock_state.get("artifact_hash", ""),
        "source_review_result_hash": source_review_result.get("artifact_hash", ""),
        "source_schema_contract_hash": source_schema_contract.get("artifact_hash", ""),
        "source_pairing_hash": source_pairing.get("artifact_hash", ""),
        "source_response_intake_policy_hash": source_intake_policy.get("artifact_hash", ""),
        "source_payload_preview_hash": source_preview.get("artifact_hash", ""),
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
        "mock_only": True,
        "sandbox_only": True,
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
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "artifact_hash": "",
        "created_at": now,
        "artifact_path": str(artifact_path.relative_to(workspace_path)),
        "warnings": [],
        "metadata": {
            "denylist_profile": "research_provider_mock_response_trust_decision_blocker",
            "forbidden_fragment_count": 0,
            "forbidden_fragments_raw_stored": False,
        },
    }
    artifact["artifact_hash"] = provider_mock_response_trust_decision_blocker_sha256(artifact)
    return artifact


def create_provider_mock_response_trust_decision_blocker(workspace_path: Path, review_sandbox_id: str) -> dict[str, Any]:
    """Create a provider mock response trust decision blocker from a review sandbox artifact."""
    safe_review_sandbox_id = validate_run_id(review_sandbox_id)

    from atlas_agent.research.provider_mock_response_review_sandbox import (
        find_provider_mock_response_review_sandbox_by_id,
        load_provider_mock_response_review_sandbox,
    )
    from atlas_agent.research.provider_mock_response_import_candidate import (
        find_provider_mock_response_import_candidate_by_id,
        load_provider_mock_response_import_candidate,
    )
    from atlas_agent.research.provider_mock_response_simulation import (
        find_provider_mock_response_simulation_by_id,
        load_provider_mock_response_simulation,
    )
    from atlas_agent.research.provider_adapter_interface_contract import (
        find_provider_adapter_interface_contract_by_id,
        load_provider_adapter_interface_contract,
    )
    from atlas_agent.research.provider_execution_unlock_state import (
        find_provider_execution_unlock_state_by_id,
        load_provider_execution_unlock_state,
    )
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )
    from atlas_agent.research.provider_opt_in_policy import (
        find_provider_opt_in_policy_by_id,
        load_provider_opt_in_policy,
    )
    from atlas_agent.research.provider_preflight_freeze import (
        find_provider_preflight_freeze_by_id,
        load_provider_preflight_freeze,
    )
    from atlas_agent.research.provider_execution_readiness_report import (
        find_provider_execution_readiness_report_by_id,
        load_provider_execution_readiness_report,
    )
    from atlas_agent.research.provider_execution_audit_packet import (
        find_provider_execution_audit_packet_by_id,
        load_provider_execution_audit_packet,
    )
    from atlas_agent.research.provider_execution_state import (
        find_provider_execution_state_by_id,
        load_provider_execution_state,
    )
    from atlas_agent.research.provider_execution_dry_run import (
        find_provider_execution_dry_run_by_id,
        load_provider_execution_dry_run,
    )
    from atlas_agent.research.provider_call_plan import (
        find_provider_call_plan_by_id,
        load_provider_call_plan,
    )
    # sandbox_request, prompt_packet, and run lineage are propagated from review_sandbox data

    review_sandbox_path = find_provider_mock_response_review_sandbox_by_id(workspace_path, safe_review_sandbox_id)
    if review_sandbox_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_review_sandbox_missing")
    review_sandbox = load_provider_mock_response_review_sandbox(review_sandbox_path, workspace_path)
    if review_sandbox.get("provider_id") != "mock":
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_review_sandbox_provider_not_mock")

    import_candidate_id = review_sandbox.get("source_provider_mock_response_import_candidate_id", "")
    import_candidate_path = find_provider_mock_response_import_candidate_by_id(workspace_path, import_candidate_id)
    if import_candidate_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_import_candidate_missing")
    import_candidate = load_provider_mock_response_import_candidate(import_candidate_path, workspace_path)

    simulation_id = import_candidate.get("source_provider_mock_response_simulation_id", "")
    simulation_path = find_provider_mock_response_simulation_by_id(workspace_path, simulation_id)
    if simulation_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_mock_response_missing")
    simulation = load_provider_mock_response_simulation(simulation_path, workspace_path)

    adapter_id = simulation.get("source_provider_adapter_interface_contract_id", "")
    adapter_path = find_provider_adapter_interface_contract_by_id(workspace_path, adapter_id)
    if adapter_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_adapter_interface_missing")
    adapter = load_provider_adapter_interface_contract(adapter_path, workspace_path)

    unlock_id = adapter.get("source_provider_execution_unlock_state_id", "")
    unlock_path = find_provider_execution_unlock_state_by_id(workspace_path, unlock_id)
    if unlock_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_unlock_state_missing")
    unlock = load_provider_execution_unlock_state(unlock_path, workspace_path)

    review_result_id = unlock.get("source_provider_response_review_result_id", "")
    review_result_path = find_provider_response_review_result_by_id(workspace_path, review_result_id)
    if review_result_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_review_result_missing")
    review_result = load_provider_response_review_result(review_result_path, workspace_path)

    schema_id = review_result.get("source_provider_response_schema_contract_id", "")
    schema_path = find_provider_response_schema_contract_by_id(workspace_path, schema_id)
    if schema_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_schema_contract_missing")
    schema = load_provider_response_schema_contract(schema_path, workspace_path)

    pairing_id = schema.get("source_provider_request_response_pairing_id", "")
    pairing_path = find_provider_request_response_pairing_by_id(workspace_path, pairing_id)
    if pairing_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_pairing_missing")
    pairing = load_provider_request_response_pairing(pairing_path, workspace_path)

    intake_id = pairing.get("source_provider_response_intake_policy_id", "")
    intake_path = find_provider_response_intake_policy_by_id(workspace_path, intake_id)
    if intake_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_response_intake_missing")
    intake = load_provider_response_intake_policy(intake_path, workspace_path)

    preview_id = intake.get("source_provider_outbound_payload_preview_id", "")
    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, preview_id)
    if preview_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_payload_preview_missing")
    preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    opt_in_id = preview.get("source_provider_opt_in_policy_id", "")
    opt_in_path = find_provider_opt_in_policy_by_id(workspace_path, opt_in_id)
    if opt_in_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_opt_in_policy_missing")
    opt_in = load_provider_opt_in_policy(opt_in_path, workspace_path)

    freeze_id = opt_in.get("source_provider_preflight_freeze_id", "")
    freeze_path = find_provider_preflight_freeze_by_id(workspace_path, freeze_id)
    if freeze_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_preflight_freeze_missing")
    freeze = load_provider_preflight_freeze(freeze_path, workspace_path)

    readiness_id = freeze.get("source_provider_execution_readiness_report_id", "")
    readiness_path = find_provider_execution_readiness_report_by_id(workspace_path, readiness_id)
    if readiness_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_readiness_report_missing")
    readiness = load_provider_execution_readiness_report(readiness_path, workspace_path)

    audit_id = readiness.get("source_provider_execution_audit_packet_id", "")
    audit_path = find_provider_execution_audit_packet_by_id(workspace_path, audit_id)
    if audit_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_audit_packet_missing")
    audit = load_provider_execution_audit_packet(audit_path, workspace_path)

    state_id = audit.get("source_provider_execution_state_id", "")
    state_path = find_provider_execution_state_by_id(workspace_path, state_id)
    if state_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_execution_state_missing")
    state = load_provider_execution_state(state_path, workspace_path)

    dry_run_id = state.get("source_provider_execution_dry_run_id", "")
    dry_run_path = find_provider_execution_dry_run_by_id(workspace_path, dry_run_id)
    if dry_run_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_dry_run_missing")
    dry_run = load_provider_execution_dry_run(dry_run_path, workspace_path)

    call_plan_id = dry_run.get("source_provider_call_plan_id", "")
    call_plan_path = find_provider_call_plan_by_id(workspace_path, call_plan_id)
    if call_plan_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_source_call_plan_missing")
    call_plan = load_provider_call_plan(call_plan_path, workspace_path)

    blocker_id = generate_run_id()
    artifact = build_provider_mock_response_trust_decision_blocker_dict(
        source_review_sandbox=review_sandbox,
        source_mock_import_candidate=import_candidate,
        source_mock_response_simulation=simulation,
        source_adapter_interface_contract=adapter,
        source_unlock_state=unlock,
        source_review_result=review_result,
        source_schema_contract=schema,
        source_pairing=pairing,
        source_intake_policy=intake,
        source_preview=preview,
        source_opt_in_policy=opt_in,
        source_preflight_freeze=freeze,
        source_readiness_report=readiness,
        source_audit_packet=audit,
        source_execution_state=state,
        source_dry_run=dry_run,
        source_call_plan=call_plan,
        blocker_id=blocker_id,
        workspace_path=workspace_path,
    )

    artifact_path = workspace_path / artifact["artifact_path"]
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "ok": True,
        "status": "research_provider_mock_response_trust_decision_blocker_created",
        "provider_mock_response_trust_decision_blocker_id": blocker_id,
        "source_provider_mock_response_review_sandbox_id": review_sandbox.get("provider_mock_response_review_sandbox_id", ""),
        "source_provider_mock_response_import_candidate_id": import_candidate_id,
        "source_provider_mock_response_simulation_id": simulation_id,
        "source_provider_adapter_interface_contract_id": adapter_id,
        "source_provider_execution_unlock_state_id": unlock_id,
        "source_provider_response_review_result_id": review_result_id,
        "source_provider_response_schema_contract_id": schema_id,
        "source_provider_request_response_pairing_id": pairing_id,
        "source_provider_response_intake_policy_id": intake_id,
        "source_provider_outbound_payload_preview_id": preview_id,
        "provider_id": "mock",
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
        "mock_only": True,
        "sandbox_only": True,
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
        "artifact_path": artifact["artifact_path"],
        "warnings": [],
    }


def load_provider_mock_response_trust_decision_blocker(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    cleaned, err = safe_validate_provider_mock_response_trust_decision_blocker_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    return cleaned


def safe_validate_provider_mock_response_trust_decision_blocker_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(data, dict):
        return None, "provider_mock_response_trust_decision_blocker_malformed"

    artifact_type = data.get("artifact_type", "")
    schema_version = data.get("schema_version", "")
    contract_version = data.get("contract_version", "")

    if artifact_type != "provider_mock_response_trust_decision_blocker":
        return None, "provider_mock_response_trust_decision_blocker_malformed"
    if schema_version != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_mock_response_trust_decision_blocker_schema"
    if contract_version != PROVIDER_MOCK_RESPONSE_TRUST_DECISION_BLOCKER_VERSION:
        return None, "unsupported_provider_mock_response_trust_decision_blocker_schema"

    try:
        validate_contract_lineage_id(data.get("provider_mock_response_trust_decision_blocker_id", ""), "invalid_provider_mock_response_trust_decision_blocker_id")
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_trust_decision_blocker_id"

    lineage_fields = [
        "source_provider_mock_response_review_sandbox_id",
        "source_provider_mock_response_import_candidate_id",
        "source_provider_mock_response_simulation_id",
        "source_provider_adapter_interface_contract_id",
        "source_provider_execution_unlock_state_id",
        "source_provider_response_review_result_id",
        "source_provider_response_schema_contract_id",
        "source_provider_request_response_pairing_id",
        "source_provider_response_intake_policy_id",
        "source_provider_outbound_payload_preview_id",
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
    for field in lineage_fields:
        try:
            validate_contract_lineage_id(data.get(field, ""), "invalid_provider_mock_response_trust_decision_blocker_lineage")
        except ResearchSessionError:
            return None, "invalid_provider_mock_response_trust_decision_blocker_lineage"

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_trust_decision_blocker_lineage"

    try:
        validate_provider_id(data.get("provider_id", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_trust_decision_blocker_provider"

    try:
        validate_model_id(data.get("model_id", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_trust_decision_blocker_model"

    try:
        validate_trust_decision_blocker_status(data.get("trust_decision_blocker_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_trust_decision_blocker_status"

    try:
        validate_trust_decision_blocker_scope(data.get("trust_decision_blocker_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_trust_decision_blocker_status"

    try:
        validate_trust_decision_blocker_state(data.get("trust_decision_blocker_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_mock_response_trust_decision_blocker_status"

    impossible = _check_boolean_safety_flags(data)
    if impossible:
        return None, impossible

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_mock_response_trust_decision_blocker_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_mock_response_trust_decision_blocker_hash_mismatch"

    policy_fields_for_positive_claim_check = [
        data.get("trust_source_summary", {}),
        data.get("trust_blocker_summary", {}),
        data.get("trust_decision_policy", {}),
        data.get("trust_upgrade_policy", {}),
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
        return None, "provider_mock_response_trust_decision_blocker_forbidden_trust_claim"

    if workspace_path is not None and not for_replay:
        from atlas_agent.research.provider_mock_response_review_sandbox import (
            find_provider_mock_response_review_sandbox_by_id,
            load_provider_mock_response_review_sandbox,
            provider_mock_response_review_sandbox_sha256,
        )
        from atlas_agent.research.provider_mock_response_import_candidate import (
            find_provider_mock_response_import_candidate_by_id,
            load_provider_mock_response_import_candidate,
            provider_mock_response_import_candidate_sha256,
        )
        from atlas_agent.research.provider_mock_response_simulation import (
            find_provider_mock_response_simulation_by_id,
            load_provider_mock_response_simulation,
            provider_mock_response_simulation_sha256,
        )
        from atlas_agent.research.provider_adapter_interface_contract import (
            find_provider_adapter_interface_contract_by_id,
            load_provider_adapter_interface_contract,
            provider_adapter_interface_contract_sha256,
        )
        from atlas_agent.research.provider_execution_unlock_state import (
            find_provider_execution_unlock_state_by_id,
            load_provider_execution_unlock_state,
            provider_execution_unlock_state_sha256,
        )
        from atlas_agent.research.provider_response_review_result import (
            find_provider_response_review_result_by_id,
            load_provider_response_review_result,
            provider_response_review_result_sha256,
        )
        from atlas_agent.research.provider_response_schema_contract import (
            find_provider_response_schema_contract_by_id,
            load_provider_response_schema_contract,
            provider_response_schema_contract_sha256,
        )
        from atlas_agent.research.provider_request_response_pairing import (
            find_provider_request_response_pairing_by_id,
            load_provider_request_response_pairing,
            provider_request_response_pairing_sha256,
        )
        from atlas_agent.research.provider_response_intake_policy import (
            find_provider_response_intake_policy_by_id,
            load_provider_response_intake_policy,
            provider_response_intake_policy_sha256,
        )
        from atlas_agent.research.provider_outbound_payload_preview import (
            find_provider_outbound_payload_preview_by_id,
            load_provider_outbound_payload_preview,
            provider_outbound_payload_preview_sha256,
        )

        source_review_sandbox_id = data.get("source_provider_mock_response_review_sandbox_id", "")
        if source_review_sandbox_id:
            rs_path = find_provider_mock_response_review_sandbox_by_id(workspace_path, source_review_sandbox_id)
            if rs_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_review_sandbox_missing"
            rs_data = load_provider_mock_response_review_sandbox(rs_path, workspace_path)
            stored_rs_hash = data.get("source_mock_review_sandbox_hash", "")
            actual_rs_hash = rs_data.get("artifact_hash", "")
            if stored_rs_hash and actual_rs_hash and stored_rs_hash != actual_rs_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_review_sandbox_hash_mismatch"
            if rs_data.get("provider_id") != "mock":
                return None, "provider_mock_response_trust_decision_blocker_source_review_sandbox_provider_not_mock"

        source_import_candidate_id = data.get("source_provider_mock_response_import_candidate_id", "")
        if source_import_candidate_id:
            ic_path = find_provider_mock_response_import_candidate_by_id(workspace_path, source_import_candidate_id)
            if ic_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_import_candidate_missing"
            ic_data = load_provider_mock_response_import_candidate(ic_path, workspace_path)
            stored_ic_hash = data.get("source_mock_import_candidate_hash", "")
            actual_ic_hash = ic_data.get("artifact_hash", "")
            if stored_ic_hash and actual_ic_hash and stored_ic_hash != actual_ic_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_import_candidate_hash_mismatch"

        source_simulation_id = data.get("source_provider_mock_response_simulation_id", "")
        if source_simulation_id:
            sim_path = find_provider_mock_response_simulation_by_id(workspace_path, source_simulation_id)
            if sim_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_mock_response_missing"
            sim_data = load_provider_mock_response_simulation(sim_path, workspace_path)
            stored_sim_hash = data.get("source_mock_response_simulation_hash", "")
            actual_sim_hash = sim_data.get("artifact_hash", "")
            if stored_sim_hash and actual_sim_hash and stored_sim_hash != actual_sim_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_mock_response_hash_mismatch"

        source_adapter_id = data.get("source_provider_adapter_interface_contract_id", "")
        if source_adapter_id:
            ad_path = find_provider_adapter_interface_contract_by_id(workspace_path, source_adapter_id)
            if ad_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_adapter_interface_missing"
            ad_data = load_provider_adapter_interface_contract(ad_path, workspace_path)
            stored_ad_hash = data.get("source_adapter_interface_contract_hash", "")
            actual_ad_hash = ad_data.get("artifact_hash", "")
            if stored_ad_hash and actual_ad_hash and stored_ad_hash != actual_ad_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_adapter_interface_hash_mismatch"

        source_unlock_id = data.get("source_provider_execution_unlock_state_id", "")
        if source_unlock_id:
            un_path = find_provider_execution_unlock_state_by_id(workspace_path, source_unlock_id)
            if un_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_unlock_state_missing"
            un_data = load_provider_execution_unlock_state(un_path, workspace_path)
            stored_un_hash = data.get("source_unlock_state_hash", "")
            actual_un_hash = un_data.get("artifact_hash", "")
            if stored_un_hash and actual_un_hash and stored_un_hash != actual_un_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_unlock_state_hash_mismatch"

        source_review_result_id = data.get("source_provider_response_review_result_id", "")
        if source_review_result_id:
            rr_path = find_provider_response_review_result_by_id(workspace_path, source_review_result_id)
            if rr_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_review_result_missing"
            rr_data = load_provider_response_review_result(rr_path, workspace_path)
            stored_rr_hash = data.get("source_review_result_hash", "")
            actual_rr_hash = rr_data.get("artifact_hash", "")
            if stored_rr_hash and actual_rr_hash and stored_rr_hash != actual_rr_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_review_result_hash_mismatch"

        source_schema_id = data.get("source_provider_response_schema_contract_id", "")
        if source_schema_id:
            sc_path = find_provider_response_schema_contract_by_id(workspace_path, source_schema_id)
            if sc_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_schema_contract_missing"
            sc_data = load_provider_response_schema_contract(sc_path, workspace_path)
            stored_sc_hash = data.get("source_schema_contract_hash", "")
            actual_sc_hash = sc_data.get("artifact_hash", "")
            if stored_sc_hash and actual_sc_hash and stored_sc_hash != actual_sc_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_schema_contract_hash_mismatch"

        source_pairing_id = data.get("source_provider_request_response_pairing_id", "")
        if source_pairing_id:
            pr_path = find_provider_request_response_pairing_by_id(workspace_path, source_pairing_id)
            if pr_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_pairing_missing"
            pr_data = load_provider_request_response_pairing(pr_path, workspace_path)
            stored_pr_hash = data.get("source_pairing_hash", "")
            actual_pr_hash = pr_data.get("artifact_hash", "")
            if stored_pr_hash and actual_pr_hash and stored_pr_hash != actual_pr_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_pairing_hash_mismatch"

        source_intake_id = data.get("source_provider_response_intake_policy_id", "")
        if source_intake_id:
            ri_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
            if ri_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_response_intake_missing"
            ri_data = load_provider_response_intake_policy(ri_path, workspace_path)
            stored_ri_hash = data.get("source_response_intake_policy_hash", "")
            actual_ri_hash = ri_data.get("artifact_hash", "")
            if stored_ri_hash and actual_ri_hash and stored_ri_hash != actual_ri_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_response_intake_hash_mismatch"

        source_preview_id = data.get("source_provider_outbound_payload_preview_id", "")
        if source_preview_id:
            pp_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
            if pp_path is None:
                return None, "provider_mock_response_trust_decision_blocker_source_payload_preview_missing"
            pp_data = load_provider_outbound_payload_preview(pp_path, workspace_path)
            stored_pp_hash = data.get("source_payload_preview_hash", "")
            actual_pp_hash = pp_data.get("artifact_hash", "")
            if stored_pp_hash and actual_pp_hash and stored_pp_hash != actual_pp_hash:
                return None, "provider_mock_response_trust_decision_blocker_source_payload_preview_hash_mismatch"

    artifact_path = data.get("artifact_path", "")
    if artifact_path and workspace_path is not None:
        abs_path = (workspace_path / artifact_path).resolve()
        if not _is_inside_workspace(abs_path, workspace_path):
            return None, "provider_mock_response_trust_decision_blocker_malformed"

    return dict(data), None


def validate_provider_mock_response_trust_decision_blocker_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderMockResponseTrustDecisionBlockerValidationResult:
    data = load_provider_mock_response_trust_decision_blocker(path, workspace_path)
    checks: list[dict[str, Any]] = []

    sv = data.get("schema_version", "")
    checks.append(_check_name("schema_version_supported", sv == RESEARCH_ARTIFACT_SCHEMA_VERSION, f"schema_version={sv}"))

    at = data.get("artifact_type", "")
    checks.append(_check_name("artifact_type_correct", at == "provider_mock_response_trust_decision_blocker", f"artifact_type={at}"))

    cv = data.get("contract_version", "")
    checks.append(_check_name("contract_version_supported", cv == PROVIDER_MOCK_RESPONSE_TRUST_DECISION_BLOCKER_VERSION, f"contract_version={cv}"))

    stored_hash = data.get("artifact_hash", "")
    computed_hash = provider_mock_response_trust_decision_blocker_sha256(data)
    checks.append(_check_name("artifact_hash_match", stored_hash == computed_hash, "hash mismatch"))

    pid = data.get("provider_id", "")
    checks.append(_check_name("provider_id_mock", pid == "mock", f"provider_id={pid}"))

    impossible = _check_boolean_safety_flags(data)
    checks.append(_check_name("boolean_safety_flags", impossible is None, impossible or "ok"))

    checks.append(_check_name(
        "no_forbidden_positive_claims",
        not any(_has_unsafe_positive_claims(data.get(f, {})) for f in [
            "trust_source_summary", "trust_blocker_summary", "trust_decision_policy", "trust_upgrade_policy",
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
        recommendation = "Artifact valid. Trust remains blocked. No trust decision exists."

    return ProviderMockResponseTrustDecisionBlockerValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=data.get("warnings", []),
    )


def replay_provider_mock_response_trust_decision_blocker(workspace_path: Path, blocker_id: str) -> dict[str, Any]:
    safe_id = validate_run_id(blocker_id)
    artifact_path = find_provider_mock_response_trust_decision_blocker_by_id(workspace_path, safe_id)
    if artifact_path is None:
        raise ResearchSessionError("provider_mock_response_trust_decision_blocker_not_found")

    old_artifact = load_provider_mock_response_trust_decision_blocker(artifact_path, workspace_path=None)

    from atlas_agent.research.provider_mock_response_review_sandbox import (
        find_provider_mock_response_review_sandbox_by_id,
        load_provider_mock_response_review_sandbox,
    )
    from atlas_agent.research.provider_mock_response_import_candidate import (
        find_provider_mock_response_import_candidate_by_id,
        load_provider_mock_response_import_candidate,
    )
    from atlas_agent.research.provider_mock_response_simulation import (
        find_provider_mock_response_simulation_by_id,
        load_provider_mock_response_simulation,
    )
    from atlas_agent.research.provider_adapter_interface_contract import (
        find_provider_adapter_interface_contract_by_id,
        load_provider_adapter_interface_contract,
    )
    from atlas_agent.research.provider_execution_unlock_state import (
        find_provider_execution_unlock_state_by_id,
        load_provider_execution_unlock_state,
    )
    from atlas_agent.research.provider_response_review_result import (
        find_provider_response_review_result_by_id,
        load_provider_response_review_result,
    )
    from atlas_agent.research.provider_response_schema_contract import (
        find_provider_response_schema_contract_by_id,
        load_provider_response_schema_contract,
    )
    from atlas_agent.research.provider_request_response_pairing import (
        find_provider_request_response_pairing_by_id,
        load_provider_request_response_pairing,
    )
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )
    from atlas_agent.research.provider_opt_in_policy import (
        find_provider_opt_in_policy_by_id,
        load_provider_opt_in_policy,
    )
    from atlas_agent.research.provider_preflight_freeze import (
        find_provider_preflight_freeze_by_id,
        load_provider_preflight_freeze,
    )
    from atlas_agent.research.provider_execution_readiness_report import (
        find_provider_execution_readiness_report_by_id,
        load_provider_execution_readiness_report,
    )
    from atlas_agent.research.provider_execution_audit_packet import (
        find_provider_execution_audit_packet_by_id,
        load_provider_execution_audit_packet,
    )
    from atlas_agent.research.provider_execution_state import (
        find_provider_execution_state_by_id,
        load_provider_execution_state,
    )
    from atlas_agent.research.provider_execution_dry_run import (
        find_provider_execution_dry_run_by_id,
        load_provider_execution_dry_run,
    )
    from atlas_agent.research.provider_call_plan import (
        find_provider_call_plan_by_id,
        load_provider_call_plan,
    )
    # sandbox_request, prompt_packet, and run lineage propagated from stored artifact data

    review_sandbox = load_provider_mock_response_review_sandbox(
        find_provider_mock_response_review_sandbox_by_id(workspace_path, old_artifact["source_provider_mock_response_review_sandbox_id"]),
        workspace_path,
    )
    import_candidate = load_provider_mock_response_import_candidate(
        find_provider_mock_response_import_candidate_by_id(workspace_path, old_artifact["source_provider_mock_response_import_candidate_id"]),
        workspace_path,
    )
    simulation = load_provider_mock_response_simulation(
        find_provider_mock_response_simulation_by_id(workspace_path, old_artifact["source_provider_mock_response_simulation_id"]),
        workspace_path,
    )
    adapter = load_provider_adapter_interface_contract(
        find_provider_adapter_interface_contract_by_id(workspace_path, old_artifact["source_provider_adapter_interface_contract_id"]),
        workspace_path,
    )
    unlock = load_provider_execution_unlock_state(
        find_provider_execution_unlock_state_by_id(workspace_path, old_artifact["source_provider_execution_unlock_state_id"]),
        workspace_path,
    )
    review_result = load_provider_response_review_result(
        find_provider_response_review_result_by_id(workspace_path, old_artifact["source_provider_response_review_result_id"]),
        workspace_path,
    )
    schema = load_provider_response_schema_contract(
        find_provider_response_schema_contract_by_id(workspace_path, old_artifact["source_provider_response_schema_contract_id"]),
        workspace_path,
    )
    pairing = load_provider_request_response_pairing(
        find_provider_request_response_pairing_by_id(workspace_path, old_artifact["source_provider_request_response_pairing_id"]),
        workspace_path,
    )
    intake = load_provider_response_intake_policy(
        find_provider_response_intake_policy_by_id(workspace_path, old_artifact["source_provider_response_intake_policy_id"]),
        workspace_path,
    )
    preview = load_provider_outbound_payload_preview(
        find_provider_outbound_payload_preview_by_id(workspace_path, old_artifact["source_provider_outbound_payload_preview_id"]),
        workspace_path,
    )
    opt_in = load_provider_opt_in_policy(
        find_provider_opt_in_policy_by_id(workspace_path, old_artifact["source_provider_opt_in_policy_id"]),
        workspace_path,
    )
    freeze = load_provider_preflight_freeze(
        find_provider_preflight_freeze_by_id(workspace_path, old_artifact["source_provider_preflight_freeze_id"]),
        workspace_path,
    )
    readiness = load_provider_execution_readiness_report(
        find_provider_execution_readiness_report_by_id(workspace_path, old_artifact["source_provider_execution_readiness_report_id"]),
        workspace_path,
    )
    audit = load_provider_execution_audit_packet(
        find_provider_execution_audit_packet_by_id(workspace_path, old_artifact["source_provider_execution_audit_packet_id"]),
        workspace_path,
    )
    state = load_provider_execution_state(
        find_provider_execution_state_by_id(workspace_path, old_artifact["source_provider_execution_state_id"]),
        workspace_path,
    )
    dry_run = load_provider_execution_dry_run(
        find_provider_execution_dry_run_by_id(workspace_path, old_artifact["source_provider_execution_dry_run_id"]),
        workspace_path,
    )
    call_plan = load_provider_call_plan(
        find_provider_call_plan_by_id(workspace_path, old_artifact["source_provider_call_plan_id"]),
        workspace_path,
    )

    new_artifact = build_provider_mock_response_trust_decision_blocker_dict(
        source_review_sandbox=review_sandbox,
        source_mock_import_candidate=import_candidate,
        source_mock_response_simulation=simulation,
        source_adapter_interface_contract=adapter,
        source_unlock_state=unlock,
        source_review_result=review_result,
        source_schema_contract=schema,
        source_pairing=pairing,
        source_intake_policy=intake,
        source_preview=preview,
        source_opt_in_policy=opt_in,
        source_preflight_freeze=freeze,
        source_readiness_report=readiness,
        source_audit_packet=audit,
        source_execution_state=state,
        source_dry_run=dry_run,
        source_call_plan=call_plan,
        blocker_id=safe_id,
        workspace_path=workspace_path,
    )
    new_artifact["created_at"] = old_artifact.get("created_at", datetime.now(UTC).isoformat())
    new_artifact["artifact_hash"] = provider_mock_response_trust_decision_blocker_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_mock_response_trust_decision_blocker_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_mock_response_trust_decision_blocker_replayed",
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
    }


def _find_latest_provider_mock_response_trust_decision_blocker_for_run(
    workspace_path: Path, run_id: str
) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    items = iter_provider_mock_response_trust_decision_blocker_artifacts(workspace_path)
    candidates = [
        item for item in items
        if item.get("source_run_id") == safe_run_id and not item.get("_invalid")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    latest_id = candidates[0].get("provider_mock_response_trust_decision_blocker_id", "")
    return find_provider_mock_response_trust_decision_blocker_by_id(workspace_path, latest_id)


def summarize_provider_mock_response_trust_decision_blocker(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_mock_response_trust_decision_blocker_for_run(workspace_path, safe_run_id)
    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_mock_response_trust_decision_blocker",
            "run_id": safe_run_id,
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
        }
    data = load_provider_mock_response_trust_decision_blocker(artifact_path, workspace_path)
    return {
        "ok": True,
        "status": "research_provider_mock_response_trust_decision_blocker_summary",
        "run_id": safe_run_id,
        "provider_mock_response_trust_decision_blocker_id": data.get("provider_mock_response_trust_decision_blocker_id", ""),
        "trust_decision_blocker_status": data.get("trust_decision_blocker_status", ""),
        "trust_decision_blocker_state": data.get("trust_decision_blocker_state", ""),
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
    }


def doctor_provider_mock_response_trust_decision_blocker(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    blocker_path = _find_latest_provider_mock_response_trust_decision_blocker_for_run(workspace_path, safe_run_id)
    if not blocker_path:
        return {
            "ok": True,
            "status": "research_provider_mock_response_trust_decision_blocker_doctor",
            "run_id": safe_run_id,
            "trust_health": "trust_decision_blocker_missing",
            "trust_blocker_active": False,
            "trust_decision_required": False,
            "trust_decision_present": False,
            "trust_decision_granted": False,
            "trust_decision_explicitly_blocked": False,
            "trust_upgrade_performed": False,
            "provider_response_trusted": False,
            "mock_response_trusted": False,
            "provider_call_allowed": False,
            "missing_prerequisites": [
                "real_trust_decision_not_implemented",
                "manual_review_not_completed",
                "trust_upgrade_not_implemented",
                "real_provider_response_not_available",
            ],
            "blocking_reasons": ["trust_decision_blocker_missing"],
            "warnings": [],
        }

    data = load_provider_mock_response_trust_decision_blocker(blocker_path, workspace_path)
    blocker_id = data.get("provider_mock_response_trust_decision_blocker_id", "")

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

    from atlas_agent.research.provider_mock_response_review_sandbox import find_provider_mock_response_review_sandbox_by_id
    from atlas_agent.research.provider_mock_response_import_candidate import find_provider_mock_response_import_candidate_by_id
    from atlas_agent.research.provider_mock_response_simulation import find_provider_mock_response_simulation_by_id

    warnings: list[str] = []
    if not find_provider_mock_response_review_sandbox_by_id(workspace_path, data.get("source_provider_mock_response_review_sandbox_id", "")):
        warnings.append("source_review_sandbox_missing")
    if not find_provider_mock_response_import_candidate_by_id(workspace_path, data.get("source_provider_mock_response_import_candidate_id", "")):
        warnings.append("source_import_candidate_missing")
    if not find_provider_mock_response_simulation_by_id(workspace_path, data.get("source_provider_mock_response_simulation_id", "")):
        warnings.append("source_mock_response_simulation_missing")

    return {
        "ok": True,
        "status": "research_provider_mock_response_trust_decision_blocker_doctor",
        "run_id": safe_run_id,
        "provider_mock_response_trust_decision_blocker_id": blocker_id,
        "trust_health": "trust_decision_blocked_untrusted",
        "trust_blocker_active": True,
        "trust_decision_required": True,
        "trust_decision_present": False,
        "trust_decision_granted": False,
        "trust_decision_explicitly_blocked": True,
        "trust_upgrade_performed": False,
        "provider_response_trusted": False,
        "mock_response_trusted": False,
        "provider_call_allowed": False,
        "missing_prerequisites": missing_prerequisites,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def iter_provider_mock_response_trust_decision_blocker_artifacts(
    workspace_path: Path, symbol: str | None = None
) -> list[dict[str, Any]]:
    search_dir = workspace_path / RESEARCH_DIR
    if symbol:
        result_dir = search_dir / symbol / "provider_mock_response_trust_decision_blockers"
        if not result_dir.exists():
            return []
        paths = list(result_dir.glob("*.json"))
    else:
        paths = list(search_dir.rglob("provider_mock_response_trust_decision_blockers/*.json"))

    items: list[dict[str, Any]] = []
    invalid_items: list[dict[str, Any]] = []
    for path in paths:
        if path.is_symlink():
            resolved = path.resolve()
            if not _is_inside_workspace(resolved, workspace_path):
                continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            invalid_items.append({
                "provider_mock_response_trust_decision_blocker_id": path.stem,
                "symbol": path.parents[1].name if len(path.parents) > 1 else "",
                "provider_id": "unknown",
                "model_id": "unknown",
                "trust_decision_blocker_status": "invalid",
                "trust_decision_blocker_state": "invalid",
                "_invalid": True,
                "error_code": "provider_mock_response_trust_decision_blocker_malformed",
            })
            continue
        cleaned, error = safe_validate_provider_mock_response_trust_decision_blocker_data(raw, workspace_path=workspace_path)
        if error or cleaned is None:
            invalid_items.append({
                "provider_mock_response_trust_decision_blocker_id": raw.get("provider_mock_response_trust_decision_blocker_id", path.stem),
                "symbol": raw.get("symbol", ""),
                "provider_id": raw.get("provider_id", "unknown"),
                "model_id": raw.get("model_id", "unknown"),
                "trust_decision_blocker_status": raw.get("trust_decision_blocker_status", "invalid"),
                "trust_decision_blocker_state": raw.get("trust_decision_blocker_state", "invalid"),
                "_invalid": True,
                "error_code": error or "provider_mock_response_trust_decision_blocker_malformed",
            })
            continue
        items.append({
            "provider_mock_response_trust_decision_blocker_id": cleaned.get("provider_mock_response_trust_decision_blocker_id", ""),
            "symbol": cleaned.get("symbol", ""),
            "provider_id": cleaned.get("provider_id", ""),
            "model_id": cleaned.get("model_id", ""),
            "trust_decision_blocker_status": cleaned.get("trust_decision_blocker_status", ""),
            "trust_decision_blocker_state": cleaned.get("trust_decision_blocker_state", ""),
            "source_provider_mock_response_review_sandbox_id": cleaned.get("source_provider_mock_response_review_sandbox_id", ""),
            "source_run_id": cleaned.get("source_run_id", ""),
            "created_at": cleaned.get("created_at", ""),
            "artifact_path": cleaned.get("artifact_path", ""),
        })

    items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    return items + invalid_items


def find_provider_mock_response_trust_decision_blocker_by_id(workspace_path: Path, blocker_id: str) -> Path | None:
    safe_id = validate_run_id(blocker_id)
    search_dir = workspace_path / RESEARCH_DIR
    for p in search_dir.rglob("provider_mock_response_trust_decision_blockers/*.json"):
        if p.stem == safe_id:
            return p
    return None
