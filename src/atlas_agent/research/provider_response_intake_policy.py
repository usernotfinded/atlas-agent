# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_response_intake_policy.py
# PURPOSE: Response side: the policy that decides whether a response may be TAKEN IN at
#          all — before anything downstream is allowed to read it.
# DEPS:    research.provider_response_schema_contract, research.sandbox_contracts
# ==============================================================================

"""Provider response intake policy — local, configless response intake policy artifact.

This module creates, loads, lists, shows, validates, replays, and summarizes provider
response intake policy artifacts. It does NOT call any real provider, does NOT perform
network requests, does NOT read API keys, does NOT read os.environ, does NOT load .env.atlas,
does NOT import provider SDKs, does NOT receive real provider responses, and does NOT touch brokers.

A provider response intake policy defines how future provider responses must be received,
treated as untrusted, redacted, hashed, reviewed, and prevented from directly affecting
trading/broker/live execution.
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

PROVIDER_RESPONSE_INTAKE_POLICY_CONTRACT_VERSION = "research_provider_response_intake_policy_v1"

_PROVIDER_RESPONSE_INTAKE_POLICY_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_INTAKE_STATUSES = {
    "response_intake_policy_recorded",
    "manual_review_required",
    "response_intake_policy_invalid",
}

_VALID_INTAKE_SCOPES = {
    "future_provider_response_intake_only",
}

_BOOLEAN_SAFETY_FLAGS = [
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
class ProviderResponseIntakePolicyValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_intake_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        value = str(value)
    return sanitize_contract_text(value, max_chars)


def validate_provider_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_response_intake_policy_provider")
    if value not in _get_disabled_provider_ids():
        raise ResearchSessionError("invalid_provider_response_intake_policy_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_response_intake_policy_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_response_intake_policy_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_intake_policy_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_response_intake_policy_model")
    return value


def validate_response_intake_policy_status(value: str) -> str:
    if not value or value not in _VALID_INTAKE_STATUSES:
        raise ResearchSessionError("invalid_provider_response_intake_policy_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_intake_policy_status")
    return value


def validate_response_intake_policy_scope(value: str) -> str:
    if not value or value not in _VALID_INTAKE_SCOPES:
        raise ResearchSessionError("invalid_provider_response_intake_policy_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_intake_policy_status")
    return value


def validate_response_trust_boundary(value: str) -> str:
    if not value or value != "provider_response_untrusted_by_default":
        raise ResearchSessionError("invalid_provider_response_intake_policy_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_response_intake_policy_status")
    return value


def provider_response_intake_policy_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_RESPONSE_INTAKE_POLICY_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS:
        if data.get(flag) is not False:
            return "provider_response_intake_policy_impossible_boolean"
    return None


def _build_response_storage_policy() -> dict[str, Any]:
    return {
        "raw_provider_response_stored": False,
        "response_body_stored": False,
        "response_body_hash_required": True,
        "response_body_preview_allowed": False,
        "bounded_summary_allowed": True,
        "artifact_storage_allowed_after_redaction": True,
        "raw_response_in_events_allowed": False,
        "raw_response_in_logs_allowed": False,
    }


def _build_response_redaction_policy() -> dict[str, Any]:
    return {
        "redaction_required_before_output": True,
        "redaction_required_before_artifact_write": True,
        "redaction_required_before_event_write": True,
        "secrets_redacted": True,
        "absolute_paths_redacted": True,
        "broker_content_redacted": True,
        "raw_exception_text_redacted": True,
        "raw_secret_echo_allowed": False,
        "redaction_profile": "atlas_provider_response_intake_v1",
        "raw_denylist_fragments_stored": False,
    }


def _build_response_validation_policy() -> dict[str, Any]:
    return {
        "response_schema_validation_required": True,
        "response_hash_required": True,
        "source_request_hash_required": True,
        "source_payload_preview_hash_required": True,
        "unsafe_content_detection_required": True,
        "trading_action_detection_required": True,
        "broker_action_detection_required": True,
        "manual_review_required_on_invalid_response": True,
    }


def _build_response_review_policy() -> dict[str, Any]:
    return {
        "manual_review_required": True,
        "auto_accept_response_allowed": False,
        "auto_execute_response_allowed": False,
        "auto_create_order_allowed": False,
        "auto_approve_order_allowed": False,
        "auto_call_broker_allowed": False,
    }


def _build_unsafe_response_policy() -> dict[str, Any]:
    return {
        "unsafe_response_behavior": "manual_review_required",
        "malformed_response_behavior": "fail_closed",
        "forbidden_fragment_behavior": "fail_closed",
        "trading_instruction_behavior": "manual_review_required",
        "broker_instruction_behavior": "fail_closed",
        "raw_exception_leakage_behavior": "release_blocker",
    }


def _build_trading_separation_policy() -> dict[str, Any]:
    return {
        "provider_response_is_trade_signal": False,
        "provider_response_can_create_pending_order": False,
        "provider_response_can_approve_order": False,
        "provider_response_can_submit_order": False,
        "provider_response_can_modify_risk": False,
        "broker_live_bridge_allowed": False,
    }


def _build_response_hash_policy() -> dict[str, Any]:
    return {
        "response_hash_required": True,
        "hash_algorithm": "sha256",
        "canonical_json_required": True,
        "raw_body_hash_allowed_without_storing_body": True,
        "hash_excludes_volatile_fields": True,
    }


def _build_manual_review_policy() -> dict[str, Any]:
    return {
        "human_review_required_before_any_trading_interpretation": True,
        "human_review_required_before_any_future_broker_bridge": True,
        "review_artifact_required": True,
        "review_event_required": True,
        "review_can_still_not_create_orders": True,
    }


def _build_denylist_metadata() -> dict[str, Any]:
    return {
        "denylist_profile": "atlas_provider_response_intake_v1",
        "forbidden_fragment_count": len(FORBIDDEN_FRAGMENTS),
        "forbidden_fragments_raw_stored": False,
    }


def build_provider_response_intake_policy_dict(
    source_preview: dict[str, Any],
    policy_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(policy_id, "provider_response_intake_policy_id")

    # Validate all lineage fields from source preview
    # The source preview stores its own ID as provider_outbound_payload_preview_id
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
    artifact_path_rel = f".atlas/research/{symbol}/provider_response_intake_policies/{policy_id}.json"

    response_storage_policy = _build_response_storage_policy()
    response_redaction_policy = _build_response_redaction_policy()
    response_validation_policy = _build_response_validation_policy()
    response_review_policy = _build_response_review_policy()
    unsafe_response_policy = _build_unsafe_response_policy()
    trading_separation_policy = _build_trading_separation_policy()
    response_hash_policy = _build_response_hash_policy()
    manual_review_policy = _build_manual_review_policy()
    denylist_metadata = _build_denylist_metadata()

    blocking_reasons = [
        "provider_execution_not_implemented",
        "provider_response_reception_not_implemented",
        "provider_response_trust_boundary_not_established",
        "trading_separation_required",
        "manual_review_required_before_any_interpretation",
    ]

    future_unlock_requirements = [
        "explicit_provider_execution_opt_in",
        "human_review_of_response_intake_policy",
        "separate_broker_bridge_approval",
        "risk_manager_validation",
    ]

    warnings = [
        "This is a local response intake policy. No provider response was received.",
        "No network request was sent.",
        "No provider response is trusted by default.",
        "Provider response cannot create orders, approvals, or pending orders.",
        "Real provider response handling requires explicit future opt-in.",
    ]

    metadata = {
        "source_preview_schema_version": source_preview.get("schema_version", ""),
        "source_preview_contract_version": source_preview.get("contract_version", ""),
    }

    source_payload_preview_hash = source_preview.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_response_intake_policy",
        "contract_version": PROVIDER_RESPONSE_INTAKE_POLICY_CONTRACT_VERSION,
        "provider_response_intake_policy_id": policy_id,
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
        "response_intake_policy_status": "response_intake_policy_recorded",
        "response_intake_policy_scope": "future_provider_response_intake_only",
        "response_trust_boundary": "provider_response_untrusted_by_default",
        "response_storage_policy": response_storage_policy,
        "response_redaction_policy": response_redaction_policy,
        "response_validation_policy": response_validation_policy,
        "response_review_policy": response_review_policy,
        "unsafe_response_policy": unsafe_response_policy,
        "trading_separation_policy": trading_separation_policy,
        "response_hash_policy": response_hash_policy,
        "manual_review_policy": manual_review_policy,
        "future_unlock_requirements": future_unlock_requirements,
        "blocking_reasons": blocking_reasons,
        "source_payload_preview_hash": source_payload_preview_hash,
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

    artifact["artifact_hash"] = provider_response_intake_policy_sha256(artifact)
    return artifact


def create_provider_response_intake_policy(
    workspace_path: Path,
    preview_id: str,
) -> dict[str, Any]:
    safe_preview_id = validate_run_id(preview_id)

    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_and_validate_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, safe_preview_id)
    if preview_path is None:
        raise ResearchSessionError("provider_response_intake_policy_source_payload_preview_missing")

    source_preview = load_and_validate_provider_outbound_payload_preview(preview_path, workspace_path)

    policy_id = generate_run_id()
    artifact = build_provider_response_intake_policy_dict(
        source_preview,
        policy_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    policy_dir = workspace_path / RESEARCH_DIR / symbol / "provider_response_intake_policies"
    policy_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_response_intake_policy_created",
        "provider_response_intake_policy_id": policy_id,
        "source_provider_outbound_payload_preview_id": safe_preview_id,
        "response_intake_policy_status": artifact["response_intake_policy_status"],
        "response_trust_boundary": artifact["response_trust_boundary"],
        "provider_response_trusted": False,
        "provider_response_received": False,
        "provider_response_imported": False,
        "provider_response_reviewed": False,
        "provider_response_can_create_orders": False,
        "provider_response_can_approve_orders": False,
        "provider_response_can_call_broker": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_response_intake_policy_{field_name}"
    return None


def safe_validate_provider_response_intake_policy_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_response_intake_policy_schema"

    if data.get("artifact_type") != "provider_response_intake_policy":
        return None, "provider_response_intake_policy_malformed"

    if data.get("contract_version") != PROVIDER_RESPONSE_INTAKE_POLICY_CONTRACT_VERSION:
        return None, "provider_response_intake_policy_malformed"

    try:
        validate_response_intake_policy_status(data.get("response_intake_policy_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_intake_policy_status"

    try:
        validate_response_intake_policy_scope(data.get("response_intake_policy_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_intake_policy_status"

    try:
        validate_response_trust_boundary(data.get("response_trust_boundary", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_intake_policy_status"

    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    if data.get("mode") != "paper":
        return None, "provider_response_intake_policy_malformed"

    for field in (
        "provider_response_intake_policy_id",
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
            return None, "invalid_provider_response_intake_policy_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_response_intake_policy_lineage"

    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_response_intake_policy_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_response_intake_policy_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_response_intake_policy_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_response_intake_policy_hash_mismatch"

    if workspace_path is not None and not for_replay:
        source_preview_id = data.get("source_provider_outbound_payload_preview_id", "")
        if source_preview_id:
            try:
                from atlas_agent.research.provider_outbound_payload_preview import (
                    find_provider_outbound_payload_preview_by_id,
                    load_provider_outbound_payload_preview,
                )

                preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
                if preview_path is None:
                    return None, "provider_response_intake_policy_source_payload_preview_missing"
                preview_data = load_provider_outbound_payload_preview(preview_path, workspace_path)
                stored_preview_hash = data.get("source_payload_preview_hash", "")
                actual_preview_hash = preview_data.get("artifact_hash", "")
                if stored_preview_hash != actual_preview_hash:
                    return None, "provider_response_intake_policy_source_payload_preview_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_response_intake_policy_source_payload_preview_missing"

    # Check policy fields for forbidden fragments
    policy_fields = [
        json.dumps(data.get("response_storage_policy", {})),
        json.dumps(data.get("response_redaction_policy", {})),
        json.dumps(data.get("response_validation_policy", {})),
        json.dumps(data.get("response_review_policy", {})),
        json.dumps(data.get("unsafe_response_policy", {})),
        json.dumps(data.get("trading_separation_policy", {})),
        json.dumps(data.get("response_hash_policy", {})),
        json.dumps(data.get("manual_review_policy", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("future_unlock_requirements", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in policy_fields):
        return None, "provider_response_intake_policy_malformed"

    # Check status/scope/trust_boundary for forbidden fragments
    policy_summaries = [
        data.get("response_intake_policy_status", ""),
        data.get("response_intake_policy_scope", ""),
        data.get("response_trust_boundary", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_response_intake_policy_forbidden_response_claim"

    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_response_intake_policy_malformed"

    cleaned = {k: v for k, v in data.items()}
    return cleaned, None


def validate_provider_response_intake_policy_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderResponseIntakePolicyValidationResult:
    data = load_provider_response_intake_policy(path, workspace_path)
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
            at == "provider_response_intake_policy",
            "artifact_type must be provider_response_intake_policy." if at != "provider_response_intake_policy" else "artifact_type is correct.",
        )
    )

    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_RESPONSE_INTAKE_POLICY_CONTRACT_VERSION,
            "contract_version must match current contract." if cv != PROVIDER_RESPONSE_INTAKE_POLICY_CONTRACT_VERSION else "contract_version matches.",
        )
    )

    status = data.get("response_intake_policy_status", "")
    status_ok = status in _VALID_INTAKE_STATUSES
    checks.append(
        _check_name(
            "response_intake_policy_status_valid",
            status_ok,
            "response_intake_policy_status is invalid." if not status_ok else "response_intake_policy_status is valid.",
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

    computed = provider_response_intake_policy_sha256(data)
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

    return ProviderResponseIntakePolicyValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation="Proceed with response intake policy." if valid else "Reject artifact and investigate tampering.",
        warnings=warnings,
    )


def load_provider_response_intake_policy(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        raise ResearchSessionError("provider_response_intake_policy_malformed") from e

    cleaned, err = safe_validate_provider_response_intake_policy_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    if not cleaned:
        raise ResearchSessionError("provider_response_intake_policy_malformed")
    return cleaned


def load_and_validate_provider_response_intake_policy(path: Path, workspace_path: Path) -> dict[str, Any]:
    data = load_provider_response_intake_policy(path, workspace_path)
    res = validate_provider_response_intake_policy_artifact(path, workspace_path)
    if not res.valid:
        raise ResearchSessionError("invalid_provider_response_intake_policy_artifact")
    return data


def find_provider_response_intake_policy_by_id(workspace_path: Path, policy_id: str) -> Path | None:
    safe_id = validate_run_id(policy_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    for p in search_dir.rglob("provider_response_intake_policies/*.json"):
        if p.stem == safe_id:
            return p
    return None


def replay_provider_response_intake_policy(
    workspace_path: Path,
    policy_id: str,
) -> dict[str, Any]:
    safe_id = validate_run_id(policy_id)
    artifact_path = find_provider_response_intake_policy_by_id(workspace_path, safe_id)
    if not artifact_path:
        raise ResearchSessionError("provider_response_intake_policy_not_found")

    old_artifact = load_provider_response_intake_policy(artifact_path, workspace_path=None)

    source_preview_id = old_artifact.get("source_provider_outbound_payload_preview_id", "")
    from atlas_agent.research.provider_outbound_payload_preview import (
        find_provider_outbound_payload_preview_by_id,
        load_provider_outbound_payload_preview,
    )

    preview_path = find_provider_outbound_payload_preview_by_id(workspace_path, source_preview_id)
    if not preview_path:
        raise ResearchSessionError("provider_response_intake_policy_source_payload_preview_missing")

    source_preview = load_provider_outbound_payload_preview(preview_path, workspace_path)

    new_artifact = build_provider_response_intake_policy_dict(
        source_preview,
        safe_id,
        workspace_path,
    )

    new_artifact["created_at"] = old_artifact.get("created_at", new_artifact["created_at"])
    new_artifact["artifact_hash"] = provider_response_intake_policy_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_response_intake_policy_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_response_intake_policy_replay",
        "provider_response_trusted": False,
        "provider_response_received": False,
    }


def iter_provider_response_intake_policy_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider response intake policy artifact metadata dicts, newest first.

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
        policy_dir = sym_dir / "provider_response_intake_policies"
        if not policy_dir.exists():
            continue
        for path in policy_dir.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                invalid_items.append({
                    "provider_response_intake_policy_id": "<invalid>",
                    "source_provider_outbound_payload_preview_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "response_intake_policy_status": "invalid",
                    "response_intake_policy_scope": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_response_intake_policy_artifact",
                    "created_at": "",
                })
                continue
            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_response_intake_policy_id": "<invalid>",
                    "source_provider_outbound_payload_preview_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "response_intake_policy_status": "invalid",
                    "response_intake_policy_scope": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_response_intake_policy_artifact",
                    "created_at": "",
                })
                continue
            cleaned, error = safe_validate_provider_response_intake_policy_data(raw, workspace_path=workspace_path)
            if error or cleaned is None:
                invalid_items.append({
                    "provider_response_intake_policy_id": "<invalid>",
                    "source_provider_outbound_payload_preview_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "response_intake_policy_status": "invalid",
                    "response_intake_policy_scope": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_response_intake_policy_artifact",
                    "created_at": "",
                })
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append({
                "provider_response_intake_policy_id": cleaned.get("provider_response_intake_policy_id", path.stem),
                "source_provider_outbound_payload_preview_id": cleaned.get("source_provider_outbound_payload_preview_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "response_intake_policy_status": cleaned.get("response_intake_policy_status", ""),
                "response_intake_policy_scope": cleaned.get("response_intake_policy_scope", ""),
                "artifact_path": rel_path,
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "created_at": cleaned.get("created_at", ""),
            })

    items.sort(key=lambda i: i["created_at"], reverse=True)
    return items + invalid_items


def _find_latest_provider_response_intake_policy_for_run(workspace_path: Path, run_id: str) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    latest_path: Path | None = None
    latest_time = ""
    for p in search_dir.rglob("provider_response_intake_policies/*.json"):
        try:
            data = load_provider_response_intake_policy(p, workspace_path=None)
            if data.get("source_run_id") == safe_run_id:
                t = data.get("created_at", "")
                if not latest_time or t > latest_time:
                    latest_time = t
                    latest_path = p
        except Exception:
            pass
    return latest_path


def summarize_provider_response_intake_policy_state(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_response_intake_policy_for_run(workspace_path, safe_run_id)

    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_response_intake_policy",
            "provider_response_intake_policy_id": None,
            "response_intake_policy_status": "not_recorded",
            "provider_response_trusted": False,
            "provider_response_received": False,
            "provider_response_can_create_orders": False,
            "artifact_path": None,
        }

    try:
        data = load_and_validate_provider_response_intake_policy(artifact_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": True,
            "status": "invalid_provider_response_intake_policy",
            "provider_response_intake_policy_id": None,
            "response_intake_policy_status": "invalid",
            "provider_response_trusted": False,
            "provider_response_received": False,
            "provider_response_can_create_orders": False,
            "artifact_path": None,
        }

    return {
        "ok": True,
        "status": "research_provider_response_intake_policy_summary",
        "provider_response_intake_policy_id": data.get("provider_response_intake_policy_id"),
        "response_intake_policy_status": data.get("response_intake_policy_status"),
        "provider_response_trusted": False,
        "provider_response_received": False,
        "provider_response_can_create_orders": False,
        "artifact_path": data.get("artifact_path"),
    }
