"""Provider request/response pairing contract — local, configless pairing artifact.

This module creates, loads, lists, shows, validates, replays, summarizes, and doctors
provider request/response pairing contract artifacts. It does NOT call any real provider,
does NOT perform network requests, does NOT read API keys, does NOT read os.environ,
does NOT load .env.atlas, does NOT import provider SDKs, does NOT receive real provider
responses, and does NOT touch brokers.

A pairing contract defines how a future outbound provider request preview and a future
provider response artifact must be paired, correlated, hashed, replayed, validated, and
kept inside an explicit untrusted response boundary.
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

PROVIDER_REQUEST_RESPONSE_PAIRING_CONTRACT_VERSION = "research_provider_request_response_pairing_v1"

_PROVIDER_REQUEST_RESPONSE_PAIRING_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_PAIRING_STATUSES = {
    "pairing_contract_recorded",
    "manual_review_required",
    "pairing_contract_invalid",
}

_VALID_PAIRING_SCOPES = {
    "future_provider_request_response_pairing_only",
}

_VALID_PAIRING_STATES = {
    "request_preview_only",
    "future_response_required",
    "pairing_not_completed",
    "blocked_until_real_response_artifact_exists",
}

_BOOLEAN_SAFETY_FLAGS = [
    "request_response_pair_completed",
    "future_response_artifact_present",
    "future_response_hash_present",
    "provider_trace_id_present",
    "external_correlation_id_present",
    "raw_request_body_stored",
    "raw_response_body_stored",
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
    "provider_response_received",
    "provider_response_trusted",
    "provider_response_imported",
    "provider_response_reviewed",
    "provider_response_can_create_orders",
    "provider_response_can_approve_orders",
    "provider_response_can_call_broker",
    "future_provider_execution_possible",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
]


@dataclass(frozen=True)
class ProviderRequestResponsePairingValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_pairing_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        value = str(value)
    return sanitize_contract_text(value, max_chars)


def validate_provider_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_request_response_pairing_provider")
    if value not in _get_disabled_provider_ids():
        raise ResearchSessionError("invalid_provider_request_response_pairing_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_request_response_pairing_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_request_response_pairing_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_request_response_pairing_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_request_response_pairing_model")
    return value


def validate_pairing_status(value: str) -> str:
    if not value or value not in _VALID_PAIRING_STATUSES:
        raise ResearchSessionError("invalid_provider_request_response_pairing_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_request_response_pairing_status")
    return value


def validate_pairing_scope(value: str) -> str:
    if not value or value not in _VALID_PAIRING_SCOPES:
        raise ResearchSessionError("invalid_provider_request_response_pairing_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_request_response_pairing_status")
    return value


def validate_pairing_state(value: str) -> str:
    if not value or value not in _VALID_PAIRING_STATES:
        raise ResearchSessionError("invalid_provider_request_response_pairing_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_request_response_pairing_status")
    return value


def provider_request_response_pairing_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_REQUEST_RESPONSE_PAIRING_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS:
        if data.get(flag) is not False:
            return "provider_request_response_pairing_impossible_boolean"
    return None


def _build_request_side(source_preview: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_payload_preview_id": source_preview.get("provider_outbound_payload_preview_id", ""),
        "source_payload_preview_hash": source_preview.get("artifact_hash", ""),
        "payload_body_stored": False,
        "raw_prompt_stored": False,
        "raw_provider_request_stored": False,
        "outbound_request_sent": False,
        "request_hash_available": True,
        "request_hash_source": "provider_outbound_payload_preview",
        "request_body_available": False,
    }


def _build_response_side() -> dict[str, Any]:
    return {
        "future_response_artifact_required": True,
        "future_response_artifact_present": False,
        "future_response_hash_required": True,
        "future_response_hash_present": False,
        "provider_response_received": False,
        "provider_response_trusted": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "raw_response_body_stored": False,
        "response_body_available": False,
    }


def _build_correlation_policy() -> dict[str, Any]:
    return {
        "local_pairing_id_required": True,
        "external_provider_trace_id_required_for_future_call": True,
        "external_provider_trace_id_present": False,
        "provider_request_id_present": False,
        "correlation_without_network_only": True,
        "correlation_does_not_imply_trust": True,
    }


def _build_provider_trace_policy() -> dict[str, Any]:
    return {
        "provider_trace_id_storage_allowed_after_redaction": False,
        "provider_trace_id_present": False,
        "provider_trace_id_required_for_future_real_call": True,
        "provider_trace_id_must_not_be_logged_raw": True,
        "provider_trace_id_must_not_be_in_artifact_before_real_call": True,
    }


def _build_request_hash_policy() -> dict[str, Any]:
    return {
        "request_hash_required": True,
        "request_hash_algorithm": "sha256",
        "request_hash_source": "payload_preview",
        "request_hash_is_not_proof_of_network_send": True,
        "request_hash_does_not_authorize_provider_call": True,
    }


def _build_response_hash_policy() -> dict[str, Any]:
    return {
        "response_hash_required_for_future_response": True,
        "response_hash_present": False,
        "response_hash_algorithm": "sha256",
        "response_hash_without_raw_body_storage_required": True,
        "response_hash_does_not_imply_trust": True,
    }


def _build_pairing_validation_policy() -> dict[str, Any]:
    return {
        "source_payload_preview_hash_must_match": True,
        "source_response_intake_policy_hash_must_match": True,
        "future_response_hash_must_match_declared_pair": True,
        "mismatched_response_behavior": "manual_review_required",
        "missing_response_behavior": "pairing_incomplete",
        "unexpected_response_behavior": "fail_closed",
        "unsafe_response_behavior": "manual_review_required",
    }


def _build_pairing_replay_policy() -> dict[str, Any]:
    return {
        "replay_required": True,
        "source_artifact_hashes_required": True,
        "replay_mismatch_behavior": "manual_review_required",
        "strict_replay_mismatch_exits_nonzero": True,
        "replay_never_calls_provider": True,
    }


def _build_mismatch_policy() -> dict[str, Any]:
    return {
        "request_hash_mismatch_behavior": "fail_closed",
        "response_hash_mismatch_behavior": "manual_review_required",
        "source_lineage_mismatch_behavior": "fail_closed",
        "provider_id_mismatch_behavior": "fail_closed",
        "model_id_mismatch_behavior": "manual_review_required",
        "symbol_mismatch_behavior": "fail_closed",
    }


def _build_trust_boundary_policy() -> dict[str, Any]:
    return {
        "provider_response_trusted_by_default": False,
        "pairing_does_not_make_response_trusted": True,
        "manual_review_required_before_trust_upgrade": True,
        "trust_upgrade_not_implemented": True,
        "provider_response_cannot_create_orders": True,
        "provider_response_cannot_approve_orders": True,
        "provider_response_cannot_call_broker": True,
    }


def _build_manual_review_policy() -> dict[str, Any]:
    return {
        "manual_review_required_before_any_future_response_use": True,
        "manual_review_required_before_any_future_trading_interpretation": True,
        "manual_review_required_before_any_future_broker_bridge": True,
        "review_artifact_required": True,
        "review_event_required": True,
        "review_can_still_not_create_orders": True,
    }


def _build_future_response_requirements() -> dict[str, Any]:
    return {
        "future_response_artifact_required": True,
        "future_response_hash_required": True,
        "future_response_redaction_required": True,
        "future_response_schema_validation_required": True,
        "future_response_manual_review_required": True,
        "future_response_cannot_authorize_trading": True,
    }


def _build_denylist_metadata() -> dict[str, Any]:
    return {
        "denylist_profile": "atlas_provider_request_response_pairing_v1",
        "forbidden_fragment_count": len(FORBIDDEN_FRAGMENTS),
        "forbidden_fragments_raw_stored": False,
    }


def build_provider_request_response_pairing_dict(
    source_intake_policy: dict[str, Any],
    source_preview: dict[str, Any],
    pairing_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(pairing_id, "provider_request_response_pairing_id")

    src_intake_id = source_intake_policy.get("provider_response_intake_policy_id", "")
    validate_contract_lineage_id(src_intake_id, "source_provider_response_intake_policy_id")

    src_preview_id = source_preview.get("provider_outbound_payload_preview_id", "")
    validate_contract_lineage_id(src_preview_id, "source_provider_outbound_payload_preview_id")

    lineage_fields = [
        ("source_provider_credential_boundary_id", "source_provider_credential_boundary_id"),
        ("source_provider_opt_in_policy_id", "source_provider_opt_in_policy_id"),
        ("source_provider_preflight_freeze_id", "source_provider_preflight_freeze_id"),
        ("source_provider_execution_readiness_report_id", "source_provider_execution_readiness_report_id"),
        ("source_provider_execution_audit_packet_id", "source_provider_execution_audit_packet_id"),
        ("source_provider_execution_state_id", "source_provider_execution_state_id"),
        ("source_provider_execution_dry_run_id", "source_provider_execution_dry_run_id"),
        ("source_provider_call_plan_id", "source_provider_call_plan_id"),
        ("source_sandbox_request_id", "source_sandbox_request_id"),
        ("source_prompt_packet_id", "source_prompt_packet_id"),
        ("source_run_id", "source_run_id"),
    ]
    for src_key, field_name in lineage_fields:
        value = source_preview.get(src_key, "")
        validate_contract_lineage_id(value, field_name)

    symbol = validate_contract_symbol(source_preview.get("symbol", ""))
    safe_provider_id = validate_provider_id(source_preview.get("provider_id", ""))
    safe_model_id = validate_model_id(source_preview.get("model_id", ""))

    created_at = datetime.now(UTC)
    artifact_path_rel = f".atlas/research/{symbol}/provider_request_response_pairings/{pairing_id}.json"

    request_side = _build_request_side(source_preview)
    response_side = _build_response_side()
    correlation_policy = _build_correlation_policy()
    provider_trace_policy = _build_provider_trace_policy()
    request_hash_policy = _build_request_hash_policy()
    response_hash_policy = _build_response_hash_policy()
    pairing_validation_policy = _build_pairing_validation_policy()
    pairing_replay_policy = _build_pairing_replay_policy()
    mismatch_policy = _build_mismatch_policy()
    trust_boundary_policy = _build_trust_boundary_policy()
    manual_review_policy = _build_manual_review_policy()
    future_response_requirements = _build_future_response_requirements()
    denylist_metadata = _build_denylist_metadata()

    blocking_reasons = [
        "provider_execution_not_implemented",
        "provider_response_reception_not_implemented",
        "provider_response_trust_boundary_not_established",
        "trading_separation_required",
        "manual_review_required_before_any_interpretation",
        "request_response_pairing_not_completed",
        "future_response_artifact_required",
    ]

    warnings = [
        "This is a local request/response pairing contract. No provider request was sent.",
        "No provider response was received.",
        "No provider response is trusted by default.",
        "Provider response cannot create orders, approvals, or pending orders.",
        "Real provider request/response pairing requires explicit future opt-in.",
    ]

    metadata = {
        "source_intake_policy_schema_version": source_intake_policy.get("schema_version", ""),
        "source_intake_policy_contract_version": source_intake_policy.get("contract_version", ""),
        "source_preview_schema_version": source_preview.get("schema_version", ""),
        "source_preview_contract_version": source_preview.get("contract_version", ""),
    }

    source_response_intake_policy_hash = source_intake_policy.get("artifact_hash", "")
    source_payload_preview_hash = source_preview.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_request_response_pairing",
        "contract_version": PROVIDER_REQUEST_RESPONSE_PAIRING_CONTRACT_VERSION,
        "provider_request_response_pairing_id": pairing_id,
        "source_provider_response_intake_policy_id": src_intake_id,
        "source_provider_outbound_payload_preview_id": src_preview_id,
        "source_provider_credential_boundary_id": source_preview.get("source_provider_credential_boundary_id", ""),
        "source_provider_opt_in_policy_id": source_preview.get("source_provider_opt_in_policy_id", ""),
        "source_provider_preflight_freeze_id": source_preview.get("source_provider_preflight_freeze_id", ""),
        "source_provider_execution_readiness_report_id": source_preview.get("source_provider_execution_readiness_report_id", ""),
        "source_provider_execution_audit_packet_id": source_preview.get("source_provider_execution_audit_packet_id", ""),
        "source_provider_execution_state_id": source_preview.get("source_provider_execution_state_id", ""),
        "source_provider_execution_dry_run_id": source_preview.get("source_provider_execution_dry_run_id", ""),
        "source_provider_call_plan_id": source_preview.get("source_provider_call_plan_id", ""),
        "source_sandbox_request_id": source_preview.get("source_sandbox_request_id", ""),
        "source_prompt_packet_id": source_preview.get("source_prompt_packet_id", ""),
        "source_run_id": source_preview.get("source_run_id", ""),
        "symbol": symbol,
        "mode": "paper",
        "provider_id": safe_provider_id,
        "model_id": safe_model_id,
        "pairing_status": "pairing_contract_recorded",
        "pairing_scope": "future_provider_request_response_pairing_only",
        "pairing_state": "request_preview_only",
        "request_side": request_side,
        "response_side": response_side,
        "correlation_policy": correlation_policy,
        "provider_trace_policy": provider_trace_policy,
        "request_hash_policy": request_hash_policy,
        "response_hash_policy": response_hash_policy,
        "pairing_validation_policy": pairing_validation_policy,
        "pairing_replay_policy": pairing_replay_policy,
        "mismatch_policy": mismatch_policy,
        "trust_boundary_policy": trust_boundary_policy,
        "manual_review_policy": manual_review_policy,
        "future_response_requirements": future_response_requirements,
        "blocking_reasons": blocking_reasons,
        "source_response_intake_policy_hash": source_response_intake_policy_hash,
        "source_payload_preview_hash": source_payload_preview_hash,
        "request_response_pair_completed": False,
        "future_response_artifact_present": False,
        "future_response_hash_present": False,
        "provider_trace_id_present": False,
        "external_correlation_id_present": False,
        "raw_request_body_stored": False,
        "raw_response_body_stored": False,
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
        "provider_response_received": False,
        "provider_response_trusted": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "provider_response_can_create_orders": False,
        "provider_response_can_approve_orders": False,
        "provider_response_can_call_broker": False,
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

    artifact["artifact_hash"] = provider_request_response_pairing_sha256(artifact)
    return artifact


def create_provider_request_response_pairing(
    workspace_path: Path,
    intake_policy_id: str,
) -> dict[str, Any]:
    safe_intake_id = validate_run_id(intake_policy_id)

    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, safe_intake_id)
    if intake_path is None:
        raise ResearchSessionError("provider_request_response_pairing_source_response_intake_missing")

    source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)

    source_preview_id = source_intake_policy.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if preview_path is None:
        raise ResearchSessionError("provider_request_response_pairing_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    pairing_id = generate_run_id()
    artifact = build_provider_request_response_pairing_dict(
        source_intake_policy,
        source_preview,
        pairing_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    pairing_dir = workspace_path / RESEARCH_DIR / symbol / "provider_request_response_pairings"
    pairing_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_request_response_pairing_created",
        "provider_request_response_pairing_id": pairing_id,
        "source_provider_response_intake_policy_id": safe_intake_id,
        "source_provider_outbound_payload_preview_id": source_preview_id,
        "pairing_status": artifact["pairing_status"],
        "pairing_state": artifact["pairing_state"],
        "request_response_pair_completed": False,
        "future_response_artifact_present": False,
        "future_response_hash_present": False,
        "provider_response_received": False,
        "provider_response_trusted": False,
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
        return f"invalid_provider_request_response_pairing_{field_name}"
    return None


def safe_validate_provider_request_response_pairing_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_request_response_pairing_schema"

    if data.get("artifact_type") != "provider_request_response_pairing":
        return None, "provider_request_response_pairing_malformed"

    if data.get("contract_version") != PROVIDER_REQUEST_RESPONSE_PAIRING_CONTRACT_VERSION:
        return None, "provider_request_response_pairing_malformed"

    try:
        validate_pairing_status(data.get("pairing_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_request_response_pairing_status"

    try:
        validate_pairing_scope(data.get("pairing_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_request_response_pairing_status"

    try:
        validate_pairing_state(data.get("pairing_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_request_response_pairing_status"

    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    if data.get("mode") != "paper":
        return None, "provider_request_response_pairing_malformed"

    for field in (
        "provider_request_response_pairing_id",
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
    ):
        value = data.get(field, "")
        try:
            validate_contract_lineage_id(value, field)
        except ResearchSessionError:
            return None, "invalid_provider_request_response_pairing_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_request_response_pairing_lineage"

    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_request_response_pairing_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_request_response_pairing_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_request_response_pairing_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_request_response_pairing_hash_mismatch"

    if workspace_path is not None and not for_replay:
        source_intake_id = data.get("source_provider_response_intake_policy_id", "")
        if source_intake_id:
            try:
                from atlas_agent.research.provider_response_intake_policy import (
                    find_provider_response_intake_policy_by_id,
                    load_provider_response_intake_policy,
                )

                intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
                if intake_path is None:
                    return None, "provider_request_response_pairing_source_response_intake_missing"
                intake_data = load_provider_response_intake_policy(intake_path, workspace_path)
                stored_intake_hash = data.get("source_response_intake_policy_hash", "")
                actual_intake_hash = intake_data.get("artifact_hash", "")
                if stored_intake_hash != actual_intake_hash:
                    return None, "provider_request_response_pairing_source_response_intake_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_request_response_pairing_source_response_intake_missing"

        source_preview_id = data.get("source_provider_outbound_payload_preview_id", "")
        if source_preview_id:
            try:
                from atlas_agent.research.provider_outbound_payload_preview import (
                    find_provider_outbound_payload_preview_by_id,
                    load_provider_outbound_payload_preview,
                )

                preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
                if preview_path is None:
                    return None, "provider_request_response_pairing_source_payload_preview_missing"
                preview_data = load_provider_outbound_payload_preview(preview_path, workspace_path)
                stored_preview_hash = data.get("source_payload_preview_hash", "")
                actual_preview_hash = preview_data.get("artifact_hash", "")
                if stored_preview_hash != actual_preview_hash:
                    return None, "provider_request_response_pairing_source_payload_preview_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_request_response_pairing_source_payload_preview_missing"

    # Check policy fields for forbidden fragments
    policy_fields = [
        json.dumps(data.get("request_side", {})),
        json.dumps(data.get("response_side", {})),
        json.dumps(data.get("correlation_policy", {})),
        json.dumps(data.get("provider_trace_policy", {})),
        json.dumps(data.get("request_hash_policy", {})),
        json.dumps(data.get("response_hash_policy", {})),
        json.dumps(data.get("pairing_validation_policy", {})),
        json.dumps(data.get("pairing_replay_policy", {})),
        json.dumps(data.get("mismatch_policy", {})),
        json.dumps(data.get("trust_boundary_policy", {})),
        json.dumps(data.get("manual_review_policy", {})),
        json.dumps(data.get("future_response_requirements", {})),
        json.dumps(data.get("blocking_reasons", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in policy_fields):
        return None, "provider_request_response_pairing_malformed"

    # Check status/scope/state for forbidden fragments
    policy_summaries = [
        data.get("pairing_status", ""),
        data.get("pairing_scope", ""),
        data.get("pairing_state", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_request_response_pairing_forbidden_pairing_claim"

    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_request_response_pairing_malformed"

    cleaned = {k: v for k, v in data.items()}
    return cleaned, None


def validate_provider_request_response_pairing_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderRequestResponsePairingValidationResult:
    data = load_provider_request_response_pairing(path, workspace_path)
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
            at == "provider_request_response_pairing",
            "artifact_type must be provider_request_response_pairing." if at != "provider_request_response_pairing" else "artifact_type is correct.",
        )
    )

    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_REQUEST_RESPONSE_PAIRING_CONTRACT_VERSION,
            "contract_version must match current contract." if cv != PROVIDER_REQUEST_RESPONSE_PAIRING_CONTRACT_VERSION else "contract_version matches.",
        )
    )

    status = data.get("pairing_status", "")
    status_ok = status in _VALID_PAIRING_STATUSES
    checks.append(
        _check_name(
            "pairing_status_valid",
            status_ok,
            "pairing_status is invalid." if not status_ok else "pairing_status is valid.",
        )
    )

    flags_ok = _check_boolean_safety_flags(data) is None
    checks.append(
        _check_name(
            "boolean_safety_flags_false",
            flags_ok,
            "A boolean safety flag is not False." if not flags_ok else "All boolean safety flags are False.",
        )
    )

    computed = provider_request_response_pairing_sha256(data)
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

    return ProviderRequestResponsePairingValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation="Proceed with pairing contract." if valid else "Reject artifact and investigate tampering.",
        warnings=warnings,
    )


def load_provider_request_response_pairing(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        raise ResearchSessionError("provider_request_response_pairing_malformed") from e

    cleaned, err = safe_validate_provider_request_response_pairing_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    if not cleaned:
        raise ResearchSessionError("provider_request_response_pairing_malformed")
    return cleaned


def load_and_validate_provider_request_response_pairing(path: Path, workspace_path: Path) -> dict[str, Any]:
    data = load_provider_request_response_pairing(path, workspace_path)
    res = validate_provider_request_response_pairing_artifact(path, workspace_path)
    if not res.valid:
        raise ResearchSessionError("invalid_provider_request_response_pairing_artifact")
    return data


def find_provider_request_response_pairing_by_id(workspace_path: Path, pairing_id: str) -> Path | None:
    safe_id = validate_run_id(pairing_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    for p in search_dir.rglob("provider_request_response_pairings/*.json"):
        if p.stem == safe_id:
            return p
    return None


def replay_provider_request_response_pairing(
    workspace_path: Path,
    pairing_id: str,
) -> dict[str, Any]:
    safe_id = validate_run_id(pairing_id)
    artifact_path = find_provider_request_response_pairing_by_id(workspace_path, safe_id)
    if not artifact_path:
        raise ResearchSessionError("provider_request_response_pairing_not_found")

    old_artifact = load_provider_request_response_pairing(artifact_path, workspace_path=None)

    source_intake_id = old_artifact.get("source_provider_response_intake_policy_id", "")
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
        load_provider_response_intake_policy,
    )

    intake_path = find_provider_response_intake_policy_by_id(workspace_path, source_intake_id)
    if not intake_path:
        raise ResearchSessionError("provider_request_response_pairing_source_response_intake_missing")

    source_intake_policy = load_provider_response_intake_policy(intake_path, workspace_path)

    source_preview_id = old_artifact.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if not preview_path:
        raise ResearchSessionError("provider_request_response_pairing_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    new_artifact = build_provider_request_response_pairing_dict(
        source_intake_policy,
        source_preview,
        safe_id,
        workspace_path,
    )

    new_artifact["created_at"] = old_artifact.get("created_at", new_artifact["created_at"])
    new_artifact["artifact_hash"] = provider_request_response_pairing_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_request_response_pairing_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_request_response_pairing_replayed",
        "provider_response_trusted": False,
        "provider_response_received": False,
    }


def iter_provider_request_response_pairing_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider request/response pairing artifact metadata dicts, newest first.

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
        pairing_dir = sym_dir / "provider_request_response_pairings"
        if not pairing_dir.exists():
            continue
        for path in pairing_dir.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                invalid_items.append({
                    "provider_request_response_pairing_id": "<invalid>",
                    "source_provider_response_intake_policy_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "pairing_status": "invalid",
                    "pairing_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_request_response_pairing_artifact",
                    "created_at": "",
                })
                continue
            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_request_response_pairing_id": "<invalid>",
                    "source_provider_response_intake_policy_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "pairing_status": "invalid",
                    "pairing_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_request_response_pairing_artifact",
                    "created_at": "",
                })
                continue
            cleaned, error = safe_validate_provider_request_response_pairing_data(raw, workspace_path=workspace_path)
            if error or cleaned is None:
                invalid_items.append({
                    "provider_request_response_pairing_id": "<invalid>",
                    "source_provider_response_intake_policy_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "pairing_status": "invalid",
                    "pairing_state": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_request_response_pairing_artifact",
                    "created_at": "",
                })
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append({
                "provider_request_response_pairing_id": cleaned.get("provider_request_response_pairing_id", path.stem),
                "source_provider_response_intake_policy_id": cleaned.get("source_provider_response_intake_policy_id", ""),
                "source_provider_outbound_payload_preview_id": cleaned.get("source_provider_outbound_payload_preview_id", ""),
                "source_provider_credential_boundary_id": cleaned.get("source_provider_credential_boundary_id", ""),
                "source_provider_opt_in_policy_id": cleaned.get("source_provider_opt_in_policy_id", ""),
                "source_provider_preflight_freeze_id": cleaned.get("source_provider_preflight_freeze_id", ""),
                "source_provider_execution_readiness_report_id": cleaned.get("source_provider_execution_readiness_report_id", ""),
                "source_provider_execution_audit_packet_id": cleaned.get("source_provider_execution_audit_packet_id", ""),
                "source_provider_execution_state_id": cleaned.get("source_provider_execution_state_id", ""),
                "source_provider_execution_dry_run_id": cleaned.get("source_provider_execution_dry_run_id", ""),
                "source_provider_call_plan_id": cleaned.get("source_provider_call_plan_id", ""),
                "source_sandbox_request_id": cleaned.get("source_sandbox_request_id", ""),
                "source_prompt_packet_id": cleaned.get("source_prompt_packet_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "pairing_status": cleaned.get("pairing_status", ""),
                "pairing_state": cleaned.get("pairing_state", ""),
                "request_response_pair_completed": cleaned.get("request_response_pair_completed", False),
                "future_response_artifact_present": cleaned.get("future_response_artifact_present", False),
                "future_response_hash_present": cleaned.get("future_response_hash_present", False),
                "provider_trace_id_present": cleaned.get("provider_trace_id_present", False),
                "external_correlation_id_present": cleaned.get("external_correlation_id_present", False),
                "raw_request_body_stored": cleaned.get("raw_request_body_stored", False),
                "raw_response_body_stored": cleaned.get("raw_response_body_stored", False),
                "provider_response_received": cleaned.get("provider_response_received", False),
                "provider_response_trusted": cleaned.get("provider_response_trusted", False),
                "provider_response_imported": cleaned.get("provider_response_imported", False),
                "provider_response_reviewed": cleaned.get("provider_response_reviewed", False),
                "provider_response_can_create_orders": cleaned.get("provider_response_can_create_orders", False),
                "provider_response_can_approve_orders": cleaned.get("provider_response_can_approve_orders", False),
                "provider_response_can_call_broker": cleaned.get("provider_response_can_call_broker", False),
                "provider_call_allowed": cleaned.get("provider_call_allowed", False),
                "actual_provider_call_made": cleaned.get("actual_provider_call_made", False),
                "outbound_request_sent": cleaned.get("outbound_request_sent", False),
                "trading_signal_generated": cleaned.get("trading_signal_generated", False),
                "approval_created": cleaned.get("approval_created", False),
                "pending_order_created": cleaned.get("pending_order_created", False),
                "broker_touched": cleaned.get("broker_touched", False),
                "artifact_path": rel_path,
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "created_at": cleaned.get("created_at", ""),
            })

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items + invalid_items


def _find_latest_provider_request_response_pairing_for_run(workspace_path: Path, run_id: str) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    latest_path: Path | None = None
    latest_time = ""
    for p in search_dir.rglob("provider_request_response_pairings/*.json"):
        try:
            data = load_provider_request_response_pairing(p, workspace_path=None)
            if data.get("source_run_id") == safe_run_id:
                t = data.get("created_at", "")
                if not latest_time or t > latest_time:
                    latest_time = t
                    latest_path = p
        except Exception:
            pass
    return latest_path


def summarize_provider_request_response_pairing_state(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_request_response_pairing_for_run(workspace_path, safe_run_id)

    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_request_response_pairing",
            "provider_request_response_pairing_id": None,
            "pairing_status": "not_recorded",
            "pairing_state": "not_recorded",
            "request_response_pair_completed": False,
            "future_response_artifact_present": False,
            "provider_response_trusted": False,
            "artifact_path": None,
        }

    try:
        data = load_and_validate_provider_request_response_pairing(artifact_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": True,
            "status": "invalid_provider_request_response_pairing",
            "provider_request_response_pairing_id": None,
            "pairing_status": "invalid",
            "pairing_state": "invalid",
            "request_response_pair_completed": False,
            "future_response_artifact_present": False,
            "provider_response_trusted": False,
            "artifact_path": None,
        }

    return {
        "ok": True,
        "status": "research_provider_request_response_pairing_summary",
        "provider_request_response_pairing_id": data.get("provider_request_response_pairing_id"),
        "pairing_status": data.get("pairing_status"),
        "pairing_state": data.get("pairing_state"),
        "request_response_pair_completed": False,
        "future_response_artifact_present": False,
        "provider_response_trusted": False,
        "artifact_path": data.get("artifact_path"),
    }


def doctor_provider_request_response_pairing(
    workspace_path: Path,
    run_id: str,
) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)

    missing_artifacts: list[str] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    # Check for payload preview
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
    )

    # Check for response intake policy
    from atlas_agent.research.provider_response_intake_policy import (
        find_provider_response_intake_policy_by_id,
    )

    pairing_path = _find_latest_provider_request_response_pairing_for_run(workspace_path, safe_run_id)
    if not pairing_path:
        missing_artifacts.append("provider_request_response_pairing")
        blocking_reasons.append("provider_request_response_pairing_not_created")
        warnings.append("No pairing contract exists for this run.")
        return {
            "ok": True,
            "status": "research_provider_request_response_pairing_doctor",
            "run_id": safe_run_id,
            "pairing_health": "pairing_missing",
            "request_response_pair_completed": False,
            "future_response_artifact_present": False,
            "provider_response_trusted": False,
            "missing_artifacts": missing_artifacts,
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
        }

    try:
        data = load_provider_request_response_pairing(pairing_path, workspace_path)
    except ResearchSessionError as e:
        warnings.append(f"Pairing artifact is invalid: {e}")
        return {
            "ok": True,
            "status": "research_provider_request_response_pairing_doctor",
            "run_id": safe_run_id,
            "pairing_health": "pairing_invalid",
            "request_response_pair_completed": False,
            "future_response_artifact_present": False,
            "provider_response_trusted": False,
            "missing_artifacts": missing_artifacts,
            "blocking_reasons": ["pairing_artifact_invalid"],
            "warnings": warnings,
        }

    # Check source artifacts
    intake_id = data.get("source_provider_response_intake_policy_id", "")
    preview_id = data.get("source_provider_outbound_payload_preview_id", "")

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

    if data.get("pairing_state") == "request_preview_only":
        pairing_health = "request_preview_only"
    elif data.get("pairing_state") == "future_response_required":
        pairing_health = "incomplete_expected"
    else:
        pairing_health = "pairing_not_completed"

    blocking_reasons.extend([
        "provider_execution_not_implemented",
        "provider_response_reception_not_implemented",
        "future_response_artifact_required",
        "request_response_pairing_not_completed",
    ])

    return {
        "ok": True,
        "status": "research_provider_request_response_pairing_doctor",
        "run_id": safe_run_id,
        "pairing_health": pairing_health,
        "request_response_pair_completed": False,
        "future_response_artifact_present": False,
        "provider_response_trusted": False,
        "missing_artifacts": missing_artifacts,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }
