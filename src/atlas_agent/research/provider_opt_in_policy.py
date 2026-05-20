"""Provider opt-in policy — local, configless policy artifact.

This module creates, validates, replays, and summarizes provider opt-in policy
artifacts. It does NOT call any real provider, does NOT perform network requests,
does NOT read API keys, does NOT import provider SDKs, and does NOT touch brokers.

A provider opt-in policy records the explicit safety gates and policies that must
be in place before any future provider execution can be considered. It answers:
- Is there a documented policy for credential handling?
- Is there a documented policy for outbound payloads?
- Is there a documented policy for provider responses?
- Is trading separation enforced?
- Are all boolean safety flags False?
- Which future controls are required before provider execution?
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
    validate_run_id,
)

PROVIDER_OPT_IN_POLICY_CONTRACT_VERSION = "research_provider_opt_in_policy_v1"

_PROVIDER_OPT_IN_POLICY_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_POLICY_STATUSES = {
    "policy_recorded",
    "manual_review_required",
    "policy_invalid",
}

_VALID_POLICY_SCOPES = {
    "future_provider_execution_opt_in",
}

_VALID_OPT_IN_STATES = {
    "not_requested",
    "manual_unlock_required",
    "blocked_until_credentials_policy_exists",
    "blocked_until_payload_policy_exists",
    "blocked_until_response_policy_exists",
    "blocked_until_provider_adapter_exists",
}

_BOOLEAN_SAFETY_FLAGS = [
    "provider_enabled",
    "network_enabled",
    "credentials_loaded",
    "provider_call_allowed",
    "actual_provider_call_made",
    "future_provider_execution_possible",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
]


@dataclass(frozen=True)
class ProviderOptInPolicyValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets

    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_policy_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
    """Redact forbidden fragments and bound length."""
    if not isinstance(value, str):
        value = str(value)
    return sanitize_contract_text(value, max_chars)


def validate_provider_id(value: str) -> str:
    """Validate provider_id against known disabled targets. Fail closed."""
    if not value:
        raise ResearchSessionError("invalid_provider_id")
    if value not in _get_disabled_provider_ids():
        raise ResearchSessionError("invalid_provider_id")
    return value


def validate_model_id(value: str) -> str:
    """Validate model_id. Bounds length, rejects unsafe chars/fragments. Fail closed."""
    if not value:
        raise ResearchSessionError("invalid_model_id")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_model_id")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_model_id")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_model_id")
    return value


def validate_policy_status(value: str) -> str:
    """Validate policy_status. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_POLICY_STATUSES:
        raise ResearchSessionError("invalid_provider_opt_in_policy_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_opt_in_policy_status")
    return value


def validate_policy_scope(value: str) -> str:
    """Validate policy_scope. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_POLICY_SCOPES:
        raise ResearchSessionError("invalid_provider_opt_in_policy_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_opt_in_policy_status")
    return value


def validate_opt_in_state(value: str) -> str:
    """Validate opt_in_state. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_OPT_IN_STATES:
        raise ResearchSessionError("invalid_provider_opt_in_policy_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_opt_in_policy_status")
    return value


def provider_opt_in_policy_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_OPT_IN_POLICY_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    """Return error code if any boolean safety flag is not False."""
    for flag in _BOOLEAN_SAFETY_FLAGS:
        if data.get(flag) is not False:
            return "provider_opt_in_policy_impossible_boolean"
    return None


def _build_required_future_controls() -> list[str]:
    """Return list of strings describing future controls required for provider execution."""
    return [
        "Manual review of opt-in policy by human operator.",
        "Explicit credential policy creation and validation.",
        "Explicit outbound payload policy creation and validation.",
        "Explicit provider response policy creation and validation.",
        "Provider adapter integration and testing.",
        "Risk manager approval for provider execution scope.",
        "Network enablement and firewall rules review.",
        "Broker adapter configuration review.",
    ]


def _build_forbidden_actions() -> list[str]:
    """Return list of forbidden action strings."""
    return [
        "No provider API calls allowed.",
        "No network requests allowed.",
        "No credential loading allowed.",
        "No .env.atlas loading allowed.",
        "No provider SDK import allowed.",
        "No trading signal generation allowed.",
        "No approval creation allowed.",
        "No pending order creation allowed.",
        "No broker touch allowed.",
        "No live trading authorization allowed.",
    ]


def _build_credential_policy() -> dict[str, Any]:
    """Return dict with all required credential policy fields."""
    return {
        "credentials_loaded": False,
        "credential_loading_allowed": False,
        "env_atlas_loading_allowed": False,
        "api_key_read": False,
        "explicit_credential_policy_required": True,
        "credential_storage_policy": "no_plaintext_storage",
        "credential_rotation_policy": "manual_rotation_required",
    }


def _build_outbound_payload_policy() -> dict[str, Any]:
    """Return dict with all required outbound payload policy fields."""
    return {
        "outbound_payload_allowed": False,
        "network_request_allowed": False,
        "payload_review_required": True,
        "payload_content_policy": "no_secrets_no_paths",
        "payload_size_limit_chars": 10000,
        "payload_logging_policy": "log_metadata_only",
    }


def _build_provider_response_policy() -> dict[str, Any]:
    """Return dict with all required provider response policy fields."""
    return {
        "provider_response_allowed": False,
        "response_review_required": True,
        "response_trust_level": "untrusted",
        "response_authenticity": "unverified",
        "response_logging_policy": "log_metadata_only",
    }


def _build_trading_separation_policy() -> dict[str, Any]:
    """Return dict with all required trading separation fields."""
    return {
        "trading_signal_generation_allowed": False,
        "approval_creation_allowed": False,
        "pending_order_creation_allowed": False,
        "broker_execution_allowed": False,
        "trading_separation_required": True,
        "analysis_execution_boundary": "strict",
    }


def _build_audit_policy() -> dict[str, Any]:
    """Return dict with all required audit policy fields."""
    return {
        "audit_logging_required": True,
        "audit_hash_chain_required": True,
        "manifest_system_required": True,
        "audit_retention_policy": "indefinite",
        "audit_immutability_expected": True,
    }


def _build_failure_policy() -> dict[str, Any]:
    """Return dict with all required failure policy fields."""
    return {
        "failure_mode": "block_and_log",
        "fallback_action": "manual_review",
        "auto_retry_allowed": False,
        "failure_notification_required": True,
    }


def _build_rollback_policy() -> dict[str, Any]:
    """Return dict with all required rollback policy fields."""
    return {
        "rollback_possible": False,
        "rollback_policy_defined": True,
        "rollback_requires_manual_approval": True,
        "rollback_scope": "none_until_provider_execution_enabled",
    }


def _build_denylist_manifest() -> dict[str, Any]:
    """Build denylist manifest for the policy artifact.

    Never stores raw forbidden fragment strings in the artifact.
    Only safe metadata: profile name, count, and safety expectation flags.
    """
    return {
        "denylist_profile": "atlas_standard_forbidden_fragments_v1",
        "forbidden_fragment_count": len(FORBIDDEN_FRAGMENTS),
        "forbidden_fragments_raw_stored": False,
        "output_safety_expected": True,
        "artifact_safety_expected": True,
        "raw_exception_output_allowed": False,
        "absolute_path_output_allowed": False,
        "unsafe_value_echo_allowed": False,
    }


def build_provider_opt_in_policy_dict(
    source_freeze: dict[str, Any],
    policy_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    """Build a provider opt-in policy artifact dict in memory.

    No network. No API keys. No provider SDKs. No broker calls.
    """
    validate_contract_lineage_id(policy_id, "provider_opt_in_policy_id")

    source_provider_preflight_freeze_id = source_freeze.get("provider_preflight_freeze_id", "")
    validate_contract_lineage_id(source_provider_preflight_freeze_id, "source_provider_preflight_freeze_id")
    source_provider_execution_readiness_report_id = source_freeze.get("source_provider_execution_readiness_report_id", "")
    validate_contract_lineage_id(source_provider_execution_readiness_report_id, "source_provider_execution_readiness_report_id")
    source_provider_execution_audit_packet_id = source_freeze.get("source_provider_execution_audit_packet_id", "")
    validate_contract_lineage_id(source_provider_execution_audit_packet_id, "source_provider_execution_audit_packet_id")
    source_provider_execution_state_id = source_freeze.get("source_provider_execution_state_id", "")
    validate_contract_lineage_id(source_provider_execution_state_id, "source_provider_execution_state_id")
    source_provider_execution_dry_run_id = source_freeze.get("source_provider_execution_dry_run_id", "")
    validate_contract_lineage_id(source_provider_execution_dry_run_id, "source_provider_execution_dry_run_id")
    source_provider_call_plan_id = source_freeze.get("source_provider_call_plan_id", "")
    validate_contract_lineage_id(source_provider_call_plan_id, "source_provider_call_plan_id")
    source_sandbox_request_id = source_freeze.get("source_sandbox_request_id", "")
    validate_contract_lineage_id(source_sandbox_request_id, "source_sandbox_request_id")
    source_prompt_packet_id = source_freeze.get("source_prompt_packet_id", "")
    validate_contract_lineage_id(source_prompt_packet_id, "source_prompt_packet_id")
    source_run_id = source_freeze.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    symbol = validate_contract_symbol(source_freeze.get("symbol", ""))
    safe_provider_id = validate_provider_id(source_freeze.get("provider_id", ""))
    safe_model_id = validate_model_id(source_freeze.get("model_id", ""))

    created_at = datetime.now(UTC)

    artifact_path_rel = f".atlas/research/{symbol}/provider_opt_in_policies/{policy_id}.json"

    credential_policy = _build_credential_policy()
    outbound_payload_policy = _build_outbound_payload_policy()
    provider_response_policy = _build_provider_response_policy()
    trading_separation_policy = _build_trading_separation_policy()
    audit_policy = _build_audit_policy()
    failure_policy = _build_failure_policy()
    rollback_policy = _build_rollback_policy()
    denylist_manifest = _build_denylist_manifest()
    required_future_controls = _build_required_future_controls()
    forbidden_actions = _build_forbidden_actions()

    policy_status = "policy_recorded"
    policy_scope = "future_provider_execution_opt_in"
    opt_in_state = "manual_unlock_required"

    blocking_reasons = [
        "Provider execution is blocked and not implemented.",
        "Manual unlock is required before any provider execution.",
        "All safety policies must be reviewed and approved.",
        "Future provider execution requires explicit opt-in.",
    ]

    warnings = [
        "This is a local opt-in policy. No provider was called.",
        "Provider execution remains blocked and not implemented.",
        "All boolean safety flags are False by design.",
        "Real provider execution requires explicit future opt-in.",
        "Manual review of this policy is required.",
    ]

    metadata = {
        "source_freeze_schema_version": source_freeze.get("schema_version", ""),
        "source_freeze_contract_version": source_freeze.get("contract_version", ""),
    }

    source_freeze_hash = source_freeze.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_opt_in_policy",
        "contract_version": PROVIDER_OPT_IN_POLICY_CONTRACT_VERSION,
        "provider_opt_in_policy_id": policy_id,
        "source_provider_preflight_freeze_id": source_provider_preflight_freeze_id,
        "source_provider_execution_readiness_report_id": source_provider_execution_readiness_report_id,
        "source_provider_execution_audit_packet_id": source_provider_execution_audit_packet_id,
        "source_provider_execution_state_id": source_provider_execution_state_id,
        "source_provider_execution_dry_run_id": source_provider_execution_dry_run_id,
        "source_provider_call_plan_id": source_provider_call_plan_id,
        "source_sandbox_request_id": source_sandbox_request_id,
        "source_prompt_packet_id": source_prompt_packet_id,
        "source_run_id": source_run_id,
        "symbol": symbol,
        "mode": "paper",
        "provider_id": safe_provider_id,
        "model_id": safe_model_id,
        "policy_status": policy_status,
        "policy_scope": policy_scope,
        "opt_in_state": opt_in_state,
        "manual_unlock_required": True,
        "credential_policy": credential_policy,
        "outbound_payload_policy": outbound_payload_policy,
        "provider_response_policy": provider_response_policy,
        "trading_separation_policy": trading_separation_policy,
        "audit_policy": audit_policy,
        "failure_policy": failure_policy,
        "rollback_policy": rollback_policy,
        "required_future_controls": required_future_controls,
        "forbidden_actions": forbidden_actions,
        "blocking_reasons": blocking_reasons,
        "source_freeze_hash": source_freeze_hash,
        "provider_enabled": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "future_provider_execution_possible": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "denylist_manifest": denylist_manifest,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": metadata,
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_opt_in_policy_sha256(artifact)
    return artifact


def create_provider_opt_in_policy(
    workspace_path: Path,
    freeze_id: str,
) -> dict[str, Any]:
    """Create and persist a provider opt-in policy artifact.

    Loads the source freeze, builds the policy, and writes the artifact.
    """
    safe_freeze_id = validate_run_id(freeze_id)

    from atlas_agent.research.provider_preflight_freeze import (
        find_provider_preflight_freeze_by_id,
        load_and_validate_provider_preflight_freeze,
    )

    freeze_path = find_provider_preflight_freeze_by_id(workspace_path, safe_freeze_id)
    if freeze_path is None:
        raise ResearchSessionError("provider_preflight_freeze_not_found")

    source_freeze = load_and_validate_provider_preflight_freeze(freeze_path, workspace_path)

    policy_id = generate_run_id()
    artifact = build_provider_opt_in_policy_dict(
        source_freeze,
        policy_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    policy_dir = workspace_path / RESEARCH_DIR / symbol / "provider_opt_in_policies"
    policy_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_opt_in_policy_created",
        "provider_opt_in_policy_id": policy_id,
        "source_provider_preflight_freeze_id": safe_freeze_id,
        "policy_status": artifact["policy_status"],
        "policy_scope": artifact["policy_scope"],
        "opt_in_state": artifact["opt_in_state"],
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    """Return static error code if value contains forbidden fragments or unsafe chars."""
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_opt_in_policy_{field_name}"
    return None


def safe_validate_provider_opt_in_policy_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """Strictly validate a loaded policy artifact for read paths.

    Returns (cleaned_data, None) if valid, or (None, error_code) if invalid.
    Never includes raw tampered values in error codes.

    When ``for_replay`` is True, the source freeze hash match is skipped so
    that replay can detect drift and report ``match=false``.
    """
    # 1. schema_version
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_opt_in_policy_schema"

    # 2. artifact_type
    if data.get("artifact_type") != "provider_opt_in_policy":
        return None, "provider_opt_in_policy_malformed"

    # 3. contract_version
    if data.get("contract_version") != PROVIDER_OPT_IN_POLICY_CONTRACT_VERSION:
        return None, "provider_opt_in_policy_malformed"

    # 4. policy_status
    try:
        validate_policy_status(data.get("policy_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_opt_in_policy_status"

    # 5. policy_scope
    try:
        validate_policy_scope(data.get("policy_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_opt_in_policy_status"

    # 6. opt_in_state
    try:
        validate_opt_in_state(data.get("opt_in_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_opt_in_policy_status"

    # 7. boolean safety flags (all must be False)
    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    # 8. mode
    if data.get("mode") != "paper":
        return None, "provider_opt_in_policy_malformed"

    # 9. lineage IDs — reject if unsafe
    for field in (
        "provider_opt_in_policy_id",
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
            return None, "invalid_provider_opt_in_policy_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    # 10. symbol
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_opt_in_policy_lineage"

    # 11. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_opt_in_policy_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    # 12. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_opt_in_policy_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    # 13. hash consistency
    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_opt_in_policy_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_opt_in_policy_hash_mismatch"

    # 14. source freeze exists and hash matches (if workspace provided)
    if workspace_path is not None and not for_replay:
        source_freeze_id = data.get("source_provider_preflight_freeze_id", "")
        if source_freeze_id:
            try:
                from atlas_agent.research.provider_preflight_freeze import (
                    find_provider_preflight_freeze_by_id,
                    load_provider_preflight_freeze,
                )

                freeze_path = find_provider_preflight_freeze_by_id(workspace_path, source_freeze_id)
                if freeze_path is None:
                    return None, "provider_opt_in_policy_source_freeze_missing"
                freeze_data = load_provider_preflight_freeze(freeze_path, workspace_path)
                stored_freeze_hash = data.get("source_freeze_hash", "")
                actual_freeze_hash = freeze_data.get("artifact_hash", "")
                if stored_freeze_hash != actual_freeze_hash:
                    return None, "provider_opt_in_policy_source_freeze_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_opt_in_policy_source_freeze_missing"

    # 15. no forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("credential_policy", {})),
        json.dumps(data.get("outbound_payload_policy", {})),
        json.dumps(data.get("provider_response_policy", {})),
        json.dumps(data.get("trading_separation_policy", {})),
        json.dumps(data.get("audit_policy", {})),
        json.dumps(data.get("failure_policy", {})),
        json.dumps(data.get("rollback_policy", {})),
        json.dumps(data.get("required_future_controls", [])),
        json.dumps(data.get("forbidden_actions", [])),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("denylist_manifest", {})),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_opt_in_policy_malformed"

    # 16. policy summaries safe (no forbidden positive claims)
    policy_summaries = [
        data.get("policy_status", ""),
        data.get("policy_scope", ""),
        data.get("opt_in_state", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_opt_in_policy_forbidden_claim"

    # 17. path containment
    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_opt_in_policy_malformed"

    # Return a cleaned copy with only safe fields
    cleaned = {
        "schema_version": data.get("schema_version", ""),
        "artifact_type": data.get("artifact_type", ""),
        "contract_version": data.get("contract_version", ""),
        "provider_opt_in_policy_id": data.get("provider_opt_in_policy_id", ""),
        "source_provider_preflight_freeze_id": data.get("source_provider_preflight_freeze_id", ""),
        "source_provider_execution_readiness_report_id": data.get("source_provider_execution_readiness_report_id", ""),
        "source_provider_execution_audit_packet_id": data.get("source_provider_execution_audit_packet_id", ""),
        "source_provider_execution_state_id": data.get("source_provider_execution_state_id", ""),
        "source_provider_execution_dry_run_id": data.get("source_provider_execution_dry_run_id", ""),
        "source_provider_call_plan_id": data.get("source_provider_call_plan_id", ""),
        "source_sandbox_request_id": data.get("source_sandbox_request_id", ""),
        "source_prompt_packet_id": data.get("source_prompt_packet_id", ""),
        "source_run_id": data.get("source_run_id", ""),
        "symbol": data.get("symbol", ""),
        "mode": data.get("mode", ""),
        "provider_id": data.get("provider_id", ""),
        "model_id": data.get("model_id", ""),
        "policy_status": data.get("policy_status", ""),
        "policy_scope": data.get("policy_scope", ""),
        "opt_in_state": data.get("opt_in_state", ""),
        "manual_unlock_required": data.get("manual_unlock_required", True),
        "credential_policy": data.get("credential_policy", {}),
        "outbound_payload_policy": data.get("outbound_payload_policy", {}),
        "provider_response_policy": data.get("provider_response_policy", {}),
        "trading_separation_policy": data.get("trading_separation_policy", {}),
        "audit_policy": data.get("audit_policy", {}),
        "failure_policy": data.get("failure_policy", {}),
        "rollback_policy": data.get("rollback_policy", {}),
        "required_future_controls": data.get("required_future_controls", []),
        "forbidden_actions": data.get("forbidden_actions", []),
        "blocking_reasons": data.get("blocking_reasons", []),
        "source_freeze_hash": data.get("source_freeze_hash", ""),
        "provider_enabled": data.get("provider_enabled", False),
        "network_enabled": data.get("network_enabled", False),
        "credentials_loaded": data.get("credentials_loaded", False),
        "provider_call_allowed": data.get("provider_call_allowed", False),
        "actual_provider_call_made": data.get("actual_provider_call_made", False),
        "future_provider_execution_possible": data.get("future_provider_execution_possible", False),
        "trading_signal_generated": data.get("trading_signal_generated", False),
        "approval_created": data.get("approval_created", False),
        "pending_order_created": data.get("pending_order_created", False),
        "broker_touched": data.get("broker_touched", False),
        "denylist_manifest": data.get("denylist_manifest", {}),
        "artifact_path": data.get("artifact_path", ""),
        "warnings": data.get("warnings", []),
        "metadata": data.get("metadata", {}),
        "artifact_hash": data.get("artifact_hash", ""),
        "created_at": data.get("created_at", ""),
    }
    return cleaned, None


def validate_provider_opt_in_policy_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderOptInPolicyValidationResult:
    """Validate a provider opt-in policy artifact against the local contract.

    Loads the artifact from disk, then performs detailed check-by-check validation.
    """
    data = load_provider_opt_in_policy(path, workspace_path)
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    # 1. schema_version
    sv = data.get("schema_version")
    checks.append(
        _check_name(
            "schema_version_supported",
            sv == RESEARCH_ARTIFACT_SCHEMA_VERSION,
            "Schema version must match supported version."
            if sv != RESEARCH_ARTIFACT_SCHEMA_VERSION
            else "Schema version is supported.",
        )
    )

    # 2. artifact_type
    at = data.get("artifact_type")
    checks.append(
        _check_name(
            "artifact_type_correct",
            at == "provider_opt_in_policy",
            "artifact_type must be provider_opt_in_policy."
            if at != "provider_opt_in_policy"
            else "artifact_type is correct.",
        )
    )

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_OPT_IN_POLICY_CONTRACT_VERSION,
            "contract_version must match current contract."
            if cv != PROVIDER_OPT_IN_POLICY_CONTRACT_VERSION
            else "contract_version matches.",
        )
    )

    # 4. policy_status
    policy_status = data.get("policy_status", "")
    status_ok = policy_status in _VALID_POLICY_STATUSES
    checks.append(
        _check_name(
            "policy_status_valid",
            status_ok,
            "policy_status is invalid." if not status_ok else "policy_status is valid.",
        )
    )

    # 5. policy_scope
    policy_scope = data.get("policy_scope", "")
    scope_ok = policy_scope in _VALID_POLICY_SCOPES
    checks.append(
        _check_name(
            "policy_scope_valid",
            scope_ok,
            "policy_scope is invalid." if not scope_ok else "policy_scope is valid.",
        )
    )

    # 6. opt_in_state
    opt_in_state = data.get("opt_in_state", "")
    state_ok = opt_in_state in _VALID_OPT_IN_STATES
    checks.append(
        _check_name(
            "opt_in_state_valid",
            state_ok,
            "opt_in_state is invalid." if not state_ok else "opt_in_state is valid.",
        )
    )

    # 7. boolean safety flags
    flags_ok = _check_boolean_safety_flags(data) is None
    checks.append(
        _check_name(
            "boolean_safety_flags_false",
            flags_ok,
            "A boolean safety flag is not False." if not flags_ok else "All boolean safety flags are False.",
        )
    )

    # 8. mode
    mode = data.get("mode", "")
    mode_ok = mode == "paper"
    checks.append(
        _check_name(
            "mode_paper",
            mode_ok,
            "mode must be paper." if not mode_ok else "mode is paper.",
        )
    )

    # 9. lineage IDs
    lineage_fields = (
        "provider_opt_in_policy_id",
        "source_provider_preflight_freeze_id",
        "source_provider_execution_readiness_report_id",
        "source_provider_execution_audit_packet_id",
        "source_provider_execution_state_id",
        "source_provider_execution_dry_run_id",
        "source_provider_call_plan_id",
        "source_sandbox_request_id",
        "source_prompt_packet_id",
        "source_run_id",
    )
    lineage_ok = True
    for field in lineage_fields:
        value = data.get(field, "")
        try:
            validate_contract_lineage_id(value, field)
        except ResearchSessionError:
            lineage_ok = False
            break
    checks.append(
        _check_name(
            "lineage_ids_valid",
            lineage_ok,
            "A lineage ID is invalid." if not lineage_ok else "All lineage IDs are valid.",
        )
    )

    # 10. symbol
    symbol = data.get("symbol", "")
    try:
        validate_contract_symbol(symbol)
        symbol_ok = True
    except ResearchSessionError:
        symbol_ok = False
    checks.append(
        _check_name(
            "symbol_valid",
            symbol_ok,
            "symbol is invalid." if not symbol_ok else "symbol is valid.",
        )
    )

    # 11. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
        provider_ok = True
    except ResearchSessionError:
        provider_ok = False
    checks.append(
        _check_name(
            "provider_id_valid",
            provider_ok,
            "provider_id is invalid." if not provider_ok else "provider_id is valid.",
        )
    )

    # 12. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
        model_ok = True
    except ResearchSessionError:
        model_ok = False
    checks.append(
        _check_name(
            "model_id_valid",
            model_ok,
            "model_id is invalid." if not model_ok else "model_id is valid.",
        )
    )

    # 13. hash consistency
    stored_hash = data.get("artifact_hash", "")
    hash_ok = False
    if stored_hash:
        computed = provider_opt_in_policy_sha256(data)
        hash_ok = stored_hash == computed
    checks.append(
        _check_name(
            "artifact_hash_consistent",
            hash_ok,
            "artifact_hash does not match computed hash." if not hash_ok else "artifact_hash is consistent.",
        )
    )

    # 14. source freeze hash match (if workspace)
    if workspace_path is not None:
        source_freeze_id = data.get("source_provider_preflight_freeze_id", "")
        source_hash_ok = False
        if source_freeze_id:
            try:
                from atlas_agent.research.provider_preflight_freeze import (
                    find_provider_preflight_freeze_by_id,
                    load_provider_preflight_freeze,
                )

                freeze_path = find_provider_preflight_freeze_by_id(workspace_path, source_freeze_id)
                if freeze_path is not None:
                    freeze_data = load_provider_preflight_freeze(freeze_path, workspace_path)
                    stored_freeze_hash = data.get("source_freeze_hash", "")
                    actual_freeze_hash = freeze_data.get("artifact_hash", "")
                    source_hash_ok = stored_freeze_hash == actual_freeze_hash
            except Exception:
                pass
        checks.append(
            _check_name(
                "source_freeze_hash_match",
                source_hash_ok,
                "Source freeze hash does not match." if not source_hash_ok else "Source freeze hash matches.",
            )
        )

    # 15. forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("credential_policy", {})),
        json.dumps(data.get("outbound_payload_policy", {})),
        json.dumps(data.get("provider_response_policy", {})),
        json.dumps(data.get("trading_separation_policy", {})),
        json.dumps(data.get("audit_policy", {})),
        json.dumps(data.get("failure_policy", {})),
        json.dumps(data.get("rollback_policy", {})),
        json.dumps(data.get("required_future_controls", [])),
        json.dumps(data.get("forbidden_actions", [])),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("denylist_manifest", {})),
    ]
    text_ok = not any(_has_forbidden_fragments(str(f)) for f in text_fields)
    checks.append(
        _check_name(
            "text_fields_forbidden_fragment_free",
            text_ok,
            "A text field contains a forbidden fragment." if not text_ok else "Text fields are clean.",
        )
    )

    # 16. denylist manifest shape (must not store raw fragments)
    denylist = data.get("denylist_manifest", {})
    denylist_ok = (
        isinstance(denylist, dict)
        and denylist.get("denylist_profile") == "atlas_standard_forbidden_fragments_v1"
        and isinstance(denylist.get("forbidden_fragment_count"), int)
        and denylist.get("forbidden_fragment_count") >= 1
        and denylist.get("forbidden_fragments_raw_stored") is False
        and denylist.get("output_safety_expected") is True
        and denylist.get("artifact_safety_expected") is True
        and denylist.get("raw_exception_output_allowed") is False
        and denylist.get("absolute_path_output_allowed") is False
        and denylist.get("unsafe_value_echo_allowed") is False
    )
    checks.append(
        _check_name(
            "denylist_manifest_safe",
            denylist_ok,
            "denylist_manifest is not safe: raw fragments may be stored." if not denylist_ok else "denylist_manifest is safe and does not store raw fragments.",
        )
    )

    # 17. policy summaries safe (no forbidden positive claims)
    policy_summaries = [
        data.get("policy_status", ""),
        data.get("policy_scope", ""),
        data.get("opt_in_state", ""),
    ]
    summaries_ok = not any(_has_forbidden_fragments(str(s)) for s in policy_summaries)
    checks.append(
        _check_name(
            "policy_summaries_safe",
            summaries_ok,
            "A policy summary contains a forbidden fragment." if not summaries_ok else "Policy summaries are safe.",
        )
    )

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    valid = failed == 0

    recommendation = (
        "provider_opt_in_policy_valid"
        if valid
        else "manual_review_required"
    )

    if not valid:
        warnings.append("Provider opt-in policy validation failed. Manual review required.")

    return ProviderOptInPolicyValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def replay_provider_opt_in_policy(
    freeze_id: str,
    workspace_path: Path,
    strict: bool = False,
) -> dict[str, Any]:
    """Replay a provider opt-in policy from its source freeze and compare hashes.

    Read-only by default. Does not call providers, read API keys, or authorize trading.
    """
    safe_id = validate_run_id(freeze_id)

    policy_path = find_provider_opt_in_policy_by_id(workspace_path, safe_id)
    if policy_path is None:
        raise ResearchSessionError("provider_opt_in_policy_not_found")

    loaded_data = load_provider_opt_in_policy(policy_path, workspace_path)
    cleaned, error = safe_validate_provider_opt_in_policy_data(
        loaded_data, workspace_path, for_replay=True
    )
    if error:
        raise ResearchSessionError(error)

    source_freeze_id = loaded_data.get("source_provider_preflight_freeze_id", "")
    from atlas_agent.research.provider_preflight_freeze import (
        find_provider_preflight_freeze_by_id,
        load_provider_preflight_freeze,
    )

    freeze_path = find_provider_preflight_freeze_by_id(workspace_path, source_freeze_id)
    if freeze_path is None:
        raise ResearchSessionError("provider_preflight_freeze_not_found")
    source_freeze = load_provider_preflight_freeze(freeze_path, workspace_path)

    rebuilt = build_provider_opt_in_policy_dict(
        source_freeze,
        safe_id,
        workspace_path,
    )

    expected_hash = loaded_data.get("artifact_hash", "")
    actual_hash = provider_opt_in_policy_sha256(rebuilt)

    checks = [
        _check_name(
            "artifact_hash_match",
            expected_hash == actual_hash,
            "Artifact hash matches." if expected_hash == actual_hash else "Artifact hash mismatch detected.",
        ),
        _check_name(
            "provider_id_consistent",
            loaded_data.get("provider_id") == rebuilt.get("provider_id"),
            "provider_id is consistent."
            if loaded_data.get("provider_id") == rebuilt.get("provider_id")
            else "provider_id is inconsistent.",
        ),
        _check_name(
            "model_id_consistent",
            loaded_data.get("model_id") == rebuilt.get("model_id"),
            "model_id is consistent."
            if loaded_data.get("model_id") == rebuilt.get("model_id")
            else "model_id is inconsistent.",
        ),
        _check_name(
            "symbol_consistent",
            loaded_data.get("symbol") == rebuilt.get("symbol"),
            "symbol is consistent."
            if loaded_data.get("symbol") == rebuilt.get("symbol")
            else "symbol is inconsistent.",
        ),
    ]

    warnings: list[str] = []
    if expected_hash != actual_hash:
        warnings.append("Provider opt-in policy hash mismatch. Source freeze or linked chain may have changed.")

    return {
        "match": expected_hash == actual_hash,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "checks": checks,
        "warnings": warnings,
    }


def find_provider_opt_in_policy_by_id(
    workspace_path: Path,
    policy_id: str,
) -> Path | None:
    """Find a provider opt-in policy artifact by its ID.

    Returns the path if found, None if not found, raises if ambiguous.
    """
    safe_id = validate_run_id(policy_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        policy_dir = sym_dir / "provider_opt_in_policies"
        if not policy_dir.exists():
            continue
        for path in policy_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("provider_opt_in_policy_id") == safe_id:
                matches.append(path)

    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_opt_in_policy_id")
    return matches[0] if matches else None


def load_provider_opt_in_policy(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load a provider opt-in policy artifact from disk.

    Performs basic safety checks but does not fully validate.
    """
    if not path.exists():
        raise ResearchSessionError("provider_opt_in_policy_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_opt_in_policy_malformed")

    data["artifact_path"] = path.relative_to(workspace_path).as_posix()

    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError(
            f"Unsupported schema version: {sv} (expected {RESEARCH_ARTIFACT_SCHEMA_VERSION})"
        )

    return data


def load_and_validate_provider_opt_in_policy(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load and strictly validate a provider opt-in policy artifact."""
    data = load_provider_opt_in_policy(path, workspace_path)
    cleaned, error = safe_validate_provider_opt_in_policy_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_provider_opt_in_policy_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider opt-in policy artifact metadata dicts, newest first.

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
        policy_dir = sym_dir / "provider_opt_in_policies"
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
                    "provider_opt_in_policy_id": "<invalid>",
                    "source_provider_preflight_freeze_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": sym_dir.name,
                    "policy_status": "policy_invalid",
                    "policy_scope": "future_provider_execution_opt_in",
                    "opt_in_state": "not_requested",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "warnings_count": 0,
                    "_invalid": True,
                    "created_at": "",
                })
                continue

            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_opt_in_policy_id": "<invalid>",
                    "source_provider_preflight_freeze_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "policy_status": "policy_invalid",
                    "policy_scope": "future_provider_execution_opt_in",
                    "opt_in_state": "not_requested",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "unsupported_provider_opt_in_policy_schema",
                    "created_at": "",
                })
                continue

            cleaned, error = safe_validate_provider_opt_in_policy_data(raw, workspace_path)
            if error:
                invalid_items.append({
                    "provider_opt_in_policy_id": "<invalid>",
                    "source_provider_preflight_freeze_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "policy_status": "policy_invalid",
                    "policy_scope": "future_provider_execution_opt_in",
                    "opt_in_state": "not_requested",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": error,
                    "created_at": "",
                })
                continue

            items.append({
                "provider_opt_in_policy_id": cleaned.get("provider_opt_in_policy_id", ""),
                "source_provider_preflight_freeze_id": cleaned.get("source_provider_preflight_freeze_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", ""),
                "policy_status": cleaned.get("policy_status", ""),
                "policy_scope": cleaned.get("policy_scope", ""),
                "opt_in_state": cleaned.get("opt_in_state", ""),
                "created_at": cleaned.get("created_at", ""),
                "artifact_path": cleaned.get("artifact_path", ""),
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "warnings_count": len(cleaned.get("warnings", [])),
            })

    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    invalid_items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items + invalid_items


def summarize_provider_opt_in_policy_for_run(
    run_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    """Read-only summary of the latest opt-in policy for a research run.

    Does NOT create artifacts. Returns a safe envelope if no policy is found.
    """
    safe_run_id = validate_run_id(run_id)

    all_policies = iter_provider_opt_in_policy_artifacts(workspace_path)
    run_policies = [p for p in all_policies if p.get("source_run_id") == safe_run_id and not p.get("_invalid")]

    if not run_policies:
        return {
            "ok": False,
            "status": "provider_opt_in_policy_missing",
            "run_id": safe_run_id,
            "symbol": "",
            "policy_status": "policy_invalid",
            "policy_scope": "future_provider_execution_opt_in",
            "opt_in_state": "not_requested",
            "provider_execution_allowed": False,
            "provider_call_made": False,
            "blocking_reasons": ["No opt-in policy found for this run."],
            "warnings": ["No provider opt-in policy artifact exists for the given run_id."],
        }

    latest = run_policies[0]

    return {
        "ok": True,
        "status": "research_provider_opt_in_policy_summary",
        "run_id": safe_run_id,
        "symbol": latest.get("symbol", ""),
        "policy_status": latest.get("policy_status", "policy_invalid"),
        "policy_scope": latest.get("policy_scope", "future_provider_execution_opt_in"),
        "opt_in_state": latest.get("opt_in_state", "not_requested"),
        "provider_execution_allowed": False,
        "provider_call_made": False,
        "blocking_reasons": ["Provider execution is blocked and not implemented."],
        "warnings": [],
    }
