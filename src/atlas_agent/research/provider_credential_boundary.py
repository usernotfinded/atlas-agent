"""Provider credential boundary — local, configless credential boundary artifact.

This module creates, validates, replays, and summarizes provider credential boundary
artifacts. It does NOT call any real provider, does NOT perform network requests,
does NOT read API keys, does NOT read os.environ, does NOT load .env.atlas,
does NOT import provider SDKs, and does NOT touch brokers.

A provider credential boundary records the explicit requirements for future credential
handling before any provider execution can be considered. It answers:
- Are credentials documented as not loaded?
- Is secret storage policy defined?
- Is secret input/output/logging/redaction/rotation/revocation policy defined?
- Are all boolean safety flags False?
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

PROVIDER_CREDENTIAL_BOUNDARY_CONTRACT_VERSION = "research_provider_credential_boundary_v1"

_PROVIDER_CREDENTIAL_BOUNDARY_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_BOUNDARY_STATUSES = {
    "credential_boundary_recorded",
    "manual_review_required",
    "credential_boundary_invalid",
}

_VALID_BOUNDARY_SCOPES = {
    "future_provider_credentials_only",
}

_VALID_CREDENTIAL_LOADING_STATES = {
    "not_implemented",
    "not_loaded",
    "blocked_until_manual_unlock",
    "blocked_until_credential_policy_implemented",
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
    "future_provider_execution_possible",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
]


@dataclass(frozen=True)
class ProviderCredentialBoundaryValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets

    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_boundary_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
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


def validate_boundary_status(value: str) -> str:
    """Validate credential_boundary_status. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_BOUNDARY_STATUSES:
        raise ResearchSessionError("invalid_provider_credential_boundary_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_credential_boundary_status")
    return value


def validate_boundary_scope(value: str) -> str:
    """Validate credential_boundary_scope. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_BOUNDARY_SCOPES:
        raise ResearchSessionError("invalid_provider_credential_boundary_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_credential_boundary_status")
    return value


def validate_credential_loading_state(value: str) -> str:
    """Validate credential_loading_state. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_CREDENTIAL_LOADING_STATES:
        raise ResearchSessionError("invalid_provider_credential_boundary_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_credential_boundary_status")
    return value


def provider_credential_boundary_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_CREDENTIAL_BOUNDARY_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    """Return error code if any boolean safety flag is not False."""
    for flag in _BOOLEAN_SAFETY_FLAGS:
        if data.get(flag) is not False:
            return "provider_credential_boundary_impossible_boolean"
    return None


def _build_secret_storage_policy() -> dict[str, Any]:
    return {
        "store_api_keys_in_artifacts": False,
        "store_api_keys_in_events": False,
        "store_api_keys_in_logs": False,
        "store_api_keys_in_git": False,
        "store_api_keys_in_docs": False,
        "store_api_keys_in_test_fixtures": False,
        "future_secret_store_required": True,
        "current_secret_store_implemented": False,
    }


def _build_secret_input_policy() -> dict[str, Any]:
    return {
        "manual_user_provided_secret_required_for_future_calls": True,
        "preflight_commands_may_read_secrets": False,
        "ci_may_require_provider_secrets": False,
        "dotenv_loading_allowed": False,
        "env_lookup_allowed_in_this_batch": False,
        "future_env_lookup_requires_explicit_gate": True,
    }


def _build_secret_output_policy() -> dict[str, Any]:
    return {
        "print_api_keys_allowed": False,
        "artifact_api_key_output_allowed": False,
        "event_api_key_output_allowed": False,
        "raw_exception_secret_output_allowed": False,
        "absolute_path_output_allowed": False,
    }


def _build_secret_logging_policy() -> dict[str, Any]:
    return {
        "log_authorization_headers_allowed": False,
        "log_bearer_tokens_allowed": False,
        "log_provider_request_headers_allowed": False,
        "log_redacted_secret_metadata_only": True,
    }


def _build_secret_redaction_policy() -> dict[str, Any]:
    return {
        "redaction_required_before_output": True,
        "redaction_required_before_artifact_write": True,
        "redaction_required_before_event_write": True,
        "raw_secret_echo_allowed": False,
    }


def _build_secret_rotation_policy() -> dict[str, Any]:
    return {
        "rotation_required_for_future_credentials": True,
        "rotation_state_tracked": False,
        "current_credentials_present": False,
    }


def _build_secret_revocation_policy() -> dict[str, Any]:
    return {
        "revocation_required": True,
        "credential_revocation_state_tracked": False,
        "policy_downgrade_to_disabled_required": True,
    }


def _build_ci_secret_policy() -> dict[str, Any]:
    return {
        "ci_requires_provider_secrets": False,
        "ci_provider_calls_allowed": False,
        "ci_secret_free_by_default": True,
        "ci_failure_if_secret_required": True,
    }


def _build_denylist_manifest() -> dict[str, Any]:
    """Build denylist manifest for the boundary artifact.

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


def build_provider_credential_boundary_dict(
    source_policy: dict[str, Any],
    boundary_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    """Build a provider credential boundary artifact dict in memory.

    No network. No API keys. No provider SDKs. No broker calls.
    """
    validate_contract_lineage_id(boundary_id, "provider_credential_boundary_id")

    source_provider_opt_in_policy_id = source_policy.get("provider_opt_in_policy_id", "")
    validate_contract_lineage_id(source_provider_opt_in_policy_id, "source_provider_opt_in_policy_id")
    source_provider_preflight_freeze_id = source_policy.get("source_provider_preflight_freeze_id", "")
    validate_contract_lineage_id(source_provider_preflight_freeze_id, "source_provider_preflight_freeze_id")
    source_provider_execution_readiness_report_id = source_policy.get("source_provider_execution_readiness_report_id", "")
    validate_contract_lineage_id(source_provider_execution_readiness_report_id, "source_provider_execution_readiness_report_id")
    source_provider_execution_audit_packet_id = source_policy.get("source_provider_execution_audit_packet_id", "")
    validate_contract_lineage_id(source_provider_execution_audit_packet_id, "source_provider_execution_audit_packet_id")
    source_provider_execution_state_id = source_policy.get("source_provider_execution_state_id", "")
    validate_contract_lineage_id(source_provider_execution_state_id, "source_provider_execution_state_id")
    source_provider_execution_dry_run_id = source_policy.get("source_provider_execution_dry_run_id", "")
    validate_contract_lineage_id(source_provider_execution_dry_run_id, "source_provider_execution_dry_run_id")
    source_provider_call_plan_id = source_policy.get("source_provider_call_plan_id", "")
    validate_contract_lineage_id(source_provider_call_plan_id, "source_provider_call_plan_id")
    source_sandbox_request_id = source_policy.get("source_sandbox_request_id", "")
    validate_contract_lineage_id(source_sandbox_request_id, "source_sandbox_request_id")
    source_prompt_packet_id = source_policy.get("source_prompt_packet_id", "")
    validate_contract_lineage_id(source_prompt_packet_id, "source_prompt_packet_id")
    source_run_id = source_policy.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    symbol = validate_contract_symbol(source_policy.get("symbol", ""))
    safe_provider_id = validate_provider_id(source_policy.get("provider_id", ""))
    safe_model_id = validate_model_id(source_policy.get("model_id", ""))

    created_at = datetime.now(UTC)

    artifact_path_rel = f".atlas/research/{symbol}/provider_credential_boundaries/{boundary_id}.json"

    secret_storage_policy = _build_secret_storage_policy()
    secret_input_policy = _build_secret_input_policy()
    secret_output_policy = _build_secret_output_policy()
    secret_logging_policy = _build_secret_logging_policy()
    secret_redaction_policy = _build_secret_redaction_policy()
    secret_rotation_policy = _build_secret_rotation_policy()
    secret_revocation_policy = _build_secret_revocation_policy()
    ci_secret_policy = _build_ci_secret_policy()
    denylist_manifest = _build_denylist_manifest()

    credential_boundary_status = "credential_boundary_recorded"
    credential_boundary_scope = "future_provider_credentials_only"
    credential_loading_state = "not_implemented"

    future_unlock_requirements = [
        "Manual review of credential boundary by human operator.",
        "Explicit secret storage policy implementation.",
        "Explicit secret input/output/logging/redaction/rotation/revocation policy implementation.",
        "Provider adapter integration and testing.",
        "Risk manager approval for provider execution scope.",
        "Network enablement and firewall rules review.",
        "Broker adapter configuration review.",
    ]

    blocking_reasons = [
        "Provider execution is blocked and not implemented.",
        "Credential loading is blocked and not implemented.",
        "All secret policies must be reviewed and approved.",
        "Future provider execution requires explicit opt-in.",
    ]

    warnings = [
        "This is a local credential boundary. No provider was called.",
        "No credentials were loaded. No API keys were read.",
        "Provider execution remains blocked and not implemented.",
        "All boolean safety flags are False by design.",
        "Real provider execution requires explicit future opt-in.",
    ]

    metadata = {
        "source_policy_schema_version": source_policy.get("schema_version", ""),
        "source_policy_contract_version": source_policy.get("contract_version", ""),
    }

    source_policy_hash = source_policy.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_credential_boundary",
        "contract_version": PROVIDER_CREDENTIAL_BOUNDARY_CONTRACT_VERSION,
        "provider_credential_boundary_id": boundary_id,
        "source_provider_opt_in_policy_id": source_provider_opt_in_policy_id,
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
        "credential_boundary_status": credential_boundary_status,
        "credential_boundary_scope": credential_boundary_scope,
        "credential_loading_state": credential_loading_state,
        "secret_storage_policy": secret_storage_policy,
        "secret_input_policy": secret_input_policy,
        "secret_output_policy": secret_output_policy,
        "secret_logging_policy": secret_logging_policy,
        "secret_redaction_policy": secret_redaction_policy,
        "secret_rotation_policy": secret_rotation_policy,
        "secret_revocation_policy": secret_revocation_policy,
        "ci_secret_policy": ci_secret_policy,
        "future_unlock_requirements": future_unlock_requirements,
        "blocking_reasons": blocking_reasons,
        "source_opt_in_policy_hash": source_policy_hash,
        "provider_enabled": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "credential_value_present": False,
        "credential_lookup_attempted": False,
        "env_read_attempted": False,
        "dotenv_loaded": False,
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

    artifact["artifact_hash"] = provider_credential_boundary_sha256(artifact)
    return artifact


def create_provider_credential_boundary(
    workspace_path: Path,
    policy_id: str,
) -> dict[str, Any]:
    """Create and persist a provider credential boundary artifact.

    Loads the source policy, builds the boundary, and writes the artifact.
    """
    safe_policy_id = validate_run_id(policy_id)

    from atlas_agent.research.provider_opt_in_policy import (
        find_provider_opt_in_policy_by_id,
        load_and_validate_provider_opt_in_policy,
    )

    policy_path = find_provider_opt_in_policy_by_id(workspace_path, safe_policy_id)
    if policy_path is None:
        raise ResearchSessionError("provider_opt_in_policy_not_found")

    source_policy = load_and_validate_provider_opt_in_policy(policy_path, workspace_path)

    boundary_id = generate_run_id()
    artifact = build_provider_credential_boundary_dict(
        source_policy,
        boundary_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    boundary_dir = workspace_path / RESEARCH_DIR / symbol / "provider_credential_boundaries"
    boundary_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_credential_boundary_created",
        "provider_credential_boundary_id": boundary_id,
        "source_provider_opt_in_policy_id": safe_policy_id,
        "credential_boundary_status": artifact["credential_boundary_status"],
        "credential_loading_state": artifact["credential_loading_state"],
        "credentials_loaded": False,
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    """Return static error code if value contains forbidden fragments or unsafe chars."""
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_credential_boundary_{field_name}"
    return None


def safe_validate_provider_credential_boundary_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """Strictly validate a loaded boundary artifact for read paths.

    Returns (cleaned_data, None) if valid, or (None, error_code) if invalid.
    Never includes raw tampered values in error codes.

    When ``for_replay`` is True, the source policy hash match is skipped so
    that replay can detect drift and report ``match=false``.
    """
    # 1. schema_version
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_credential_boundary_schema"

    # 2. artifact_type
    if data.get("artifact_type") != "provider_credential_boundary":
        return None, "provider_credential_boundary_malformed"

    # 3. contract_version
    if data.get("contract_version") != PROVIDER_CREDENTIAL_BOUNDARY_CONTRACT_VERSION:
        return None, "provider_credential_boundary_malformed"

    # 4. credential_boundary_status
    try:
        validate_boundary_status(data.get("credential_boundary_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_credential_boundary_status"

    # 5. credential_boundary_scope
    try:
        validate_boundary_scope(data.get("credential_boundary_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_credential_boundary_status"

    # 6. credential_loading_state
    try:
        validate_credential_loading_state(data.get("credential_loading_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_credential_boundary_status"

    # 7. boolean safety flags (all must be False)
    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    # 8. mode
    if data.get("mode") != "paper":
        return None, "provider_credential_boundary_malformed"

    # 9. lineage IDs — reject if unsafe
    for field in (
        "provider_credential_boundary_id",
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
            return None, "invalid_provider_credential_boundary_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    # 10. symbol
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_credential_boundary_lineage"

    # 11. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_credential_boundary_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    # 12. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_credential_boundary_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    # 13. hash consistency
    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_credential_boundary_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_credential_boundary_hash_mismatch"

    # 14. source policy exists and hash matches (if workspace provided)
    if workspace_path is not None and not for_replay:
        source_policy_id = data.get("source_provider_opt_in_policy_id", "")
        if source_policy_id:
            try:
                from atlas_agent.research.provider_opt_in_policy import (
                    find_provider_opt_in_policy_by_id,
                    load_provider_opt_in_policy,
                )

                policy_path = find_provider_opt_in_policy_by_id(workspace_path, source_policy_id)
                if policy_path is None:
                    return None, "provider_credential_boundary_source_policy_missing"
                policy_data = load_provider_opt_in_policy(policy_path, workspace_path)
                stored_policy_hash = data.get("source_opt_in_policy_hash", "")
                actual_policy_hash = policy_data.get("artifact_hash", "")
                if stored_policy_hash != actual_policy_hash:
                    return None, "provider_credential_boundary_source_policy_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_credential_boundary_source_policy_missing"

    # 15. no forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("secret_storage_policy", {})),
        json.dumps(data.get("secret_input_policy", {})),
        json.dumps(data.get("secret_output_policy", {})),
        json.dumps(data.get("secret_logging_policy", {})),
        json.dumps(data.get("secret_redaction_policy", {})),
        json.dumps(data.get("secret_rotation_policy", {})),
        json.dumps(data.get("secret_revocation_policy", {})),
        json.dumps(data.get("ci_secret_policy", {})),
        json.dumps(data.get("future_unlock_requirements", [])),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("denylist_manifest", {})),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_credential_boundary_malformed"

    # 16. policy summaries safe (no forbidden positive claims)
    policy_summaries = [
        data.get("credential_boundary_status", ""),
        data.get("credential_boundary_scope", ""),
        data.get("credential_loading_state", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_credential_boundary_forbidden_secret_claim"

    # 17. path containment
    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_credential_boundary_malformed"

    # Return a cleaned copy with only safe fields
    cleaned = {
        "schema_version": data.get("schema_version", ""),
        "artifact_type": data.get("artifact_type", ""),
        "contract_version": data.get("contract_version", ""),
        "provider_credential_boundary_id": data.get("provider_credential_boundary_id", ""),
        "source_provider_opt_in_policy_id": data.get("source_provider_opt_in_policy_id", ""),
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
        "credential_boundary_status": data.get("credential_boundary_status", ""),
        "credential_boundary_scope": data.get("credential_boundary_scope", ""),
        "credential_loading_state": data.get("credential_loading_state", ""),
        "secret_storage_policy": data.get("secret_storage_policy", {}),
        "secret_input_policy": data.get("secret_input_policy", {}),
        "secret_output_policy": data.get("secret_output_policy", {}),
        "secret_logging_policy": data.get("secret_logging_policy", {}),
        "secret_redaction_policy": data.get("secret_redaction_policy", {}),
        "secret_rotation_policy": data.get("secret_rotation_policy", {}),
        "secret_revocation_policy": data.get("secret_revocation_policy", {}),
        "ci_secret_policy": data.get("ci_secret_policy", {}),
        "future_unlock_requirements": data.get("future_unlock_requirements", []),
        "blocking_reasons": data.get("blocking_reasons", []),
        "source_opt_in_policy_hash": data.get("source_opt_in_policy_hash", ""),
        "provider_enabled": data.get("provider_enabled", False),
        "network_enabled": data.get("network_enabled", False),
        "credentials_loaded": data.get("credentials_loaded", False),
        "credential_value_present": data.get("credential_value_present", False),
        "credential_lookup_attempted": data.get("credential_lookup_attempted", False),
        "env_read_attempted": data.get("env_read_attempted", False),
        "dotenv_loaded": data.get("dotenv_loaded", False),
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


def validate_provider_credential_boundary_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderCredentialBoundaryValidationResult:
    """Validate a provider credential boundary artifact against the local contract.

    Loads the artifact from disk, then performs detailed check-by-check validation.
    """
    data = load_provider_credential_boundary(path, workspace_path)
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
            at == "provider_credential_boundary",
            "artifact_type must be provider_credential_boundary."
            if at != "provider_credential_boundary"
            else "artifact_type is correct.",
        )
    )

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_CREDENTIAL_BOUNDARY_CONTRACT_VERSION,
            "contract_version must match current contract."
            if cv != PROVIDER_CREDENTIAL_BOUNDARY_CONTRACT_VERSION
            else "contract_version matches.",
        )
    )

    # 4. credential_boundary_status
    credential_boundary_status = data.get("credential_boundary_status", "")
    status_ok = credential_boundary_status in _VALID_BOUNDARY_STATUSES
    checks.append(
        _check_name(
            "credential_boundary_status_valid",
            status_ok,
            "credential_boundary_status is invalid." if not status_ok else "credential_boundary_status is valid.",
        )
    )

    # 5. credential_boundary_scope
    credential_boundary_scope = data.get("credential_boundary_scope", "")
    scope_ok = credential_boundary_scope in _VALID_BOUNDARY_SCOPES
    checks.append(
        _check_name(
            "credential_boundary_scope_valid",
            scope_ok,
            "credential_boundary_scope is invalid." if not scope_ok else "credential_boundary_scope is valid.",
        )
    )

    # 6. credential_loading_state
    credential_loading_state = data.get("credential_loading_state", "")
    state_ok = credential_loading_state in _VALID_CREDENTIAL_LOADING_STATES
    checks.append(
        _check_name(
            "credential_loading_state_valid",
            state_ok,
            "credential_loading_state is invalid." if not state_ok else "credential_loading_state is valid.",
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
        "provider_credential_boundary_id",
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
        computed = provider_credential_boundary_sha256(data)
        hash_ok = stored_hash == computed
    checks.append(
        _check_name(
            "artifact_hash_consistent",
            hash_ok,
            "artifact_hash does not match computed hash." if not hash_ok else "artifact_hash is consistent.",
        )
    )

    # 14. source policy hash match (if workspace)
    if workspace_path is not None:
        source_policy_id = data.get("source_provider_opt_in_policy_id", "")
        source_hash_ok = False
        if source_policy_id:
            try:
                from atlas_agent.research.provider_opt_in_policy import (
                    find_provider_opt_in_policy_by_id,
                    load_provider_opt_in_policy,
                )

                policy_path = find_provider_opt_in_policy_by_id(workspace_path, source_policy_id)
                if policy_path is not None:
                    policy_data = load_provider_opt_in_policy(policy_path, workspace_path)
                    stored_policy_hash = data.get("source_opt_in_policy_hash", "")
                    actual_policy_hash = policy_data.get("artifact_hash", "")
                    source_hash_ok = stored_policy_hash == actual_policy_hash
            except Exception:
                pass
        checks.append(
            _check_name(
                "source_policy_hash_match",
                source_hash_ok,
                "Source policy hash does not match." if not source_hash_ok else "Source policy hash matches.",
            )
        )

    # 15. forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("secret_storage_policy", {})),
        json.dumps(data.get("secret_input_policy", {})),
        json.dumps(data.get("secret_output_policy", {})),
        json.dumps(data.get("secret_logging_policy", {})),
        json.dumps(data.get("secret_redaction_policy", {})),
        json.dumps(data.get("secret_rotation_policy", {})),
        json.dumps(data.get("secret_revocation_policy", {})),
        json.dumps(data.get("ci_secret_policy", {})),
        json.dumps(data.get("future_unlock_requirements", [])),
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
        data.get("credential_boundary_status", ""),
        data.get("credential_boundary_scope", ""),
        data.get("credential_loading_state", ""),
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
        "provider_credential_boundary_valid"
        if valid
        else "manual_review_required"
    )

    if not valid:
        warnings.append("Provider credential boundary validation failed. Manual review required.")

    return ProviderCredentialBoundaryValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def replay_provider_credential_boundary(
    boundary_id: str,
    workspace_path: Path,
    strict: bool = False,
) -> dict[str, Any]:
    """Replay a provider credential boundary from its source policy and compare hashes.

    Read-only by default. Does not call providers, read API keys, or authorize trading.
    """
    safe_id = validate_run_id(boundary_id)

    boundary_path = find_provider_credential_boundary_by_id(workspace_path, safe_id)
    if boundary_path is None:
        raise ResearchSessionError("provider_credential_boundary_not_found")

    loaded_data = load_provider_credential_boundary(boundary_path, workspace_path)
    cleaned, error = safe_validate_provider_credential_boundary_data(
        loaded_data, workspace_path, for_replay=True
    )
    if error:
        raise ResearchSessionError(error)

    source_policy_id = loaded_data.get("source_provider_opt_in_policy_id", "")
    from atlas_agent.research.provider_opt_in_policy import (
        find_provider_opt_in_policy_by_id,
        load_provider_opt_in_policy,
    )

    policy_path = find_provider_opt_in_policy_by_id(workspace_path, source_policy_id)
    if policy_path is None:
        raise ResearchSessionError("provider_opt_in_policy_not_found")
    source_policy = load_provider_opt_in_policy(policy_path, workspace_path)

    rebuilt = build_provider_credential_boundary_dict(
        source_policy,
        safe_id,
        workspace_path,
    )

    expected_hash = loaded_data.get("artifact_hash", "")
    actual_hash = provider_credential_boundary_sha256(rebuilt)

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
        warnings.append("Provider credential boundary hash mismatch. Source policy or linked chain may have changed.")

    return {
        "match": expected_hash == actual_hash,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "checks": checks,
        "warnings": warnings,
    }


def find_provider_credential_boundary_by_id(
    workspace_path: Path,
    boundary_id: str,
) -> Path | None:
    """Find a provider credential boundary artifact by its ID.

    Returns the path if found, None if not found, raises if ambiguous.
    """
    safe_id = validate_run_id(boundary_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        boundary_dir = sym_dir / "provider_credential_boundaries"
        if not boundary_dir.exists():
            continue
        for path in boundary_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("provider_credential_boundary_id") == safe_id:
                matches.append(path)

    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_credential_boundary_id")
    return matches[0] if matches else None


def load_provider_credential_boundary(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load a provider credential boundary artifact from disk.

    Performs basic safety checks but does not fully validate.
    """
    if not path.exists():
        raise ResearchSessionError("provider_credential_boundary_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_credential_boundary_malformed")

    data["artifact_path"] = path.relative_to(workspace_path).as_posix()

    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError(
            f"Unsupported schema version: {sv} (expected {RESEARCH_ARTIFACT_SCHEMA_VERSION})"
        )

    return data


def load_and_validate_provider_credential_boundary(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load and strictly validate a provider credential boundary artifact."""
    data = load_provider_credential_boundary(path, workspace_path)
    cleaned, error = safe_validate_provider_credential_boundary_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_provider_credential_boundary_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider credential boundary artifact metadata dicts, newest first.

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
        boundary_dir = sym_dir / "provider_credential_boundaries"
        if not boundary_dir.exists():
            continue
        for path in boundary_dir.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                invalid_items.append({
                    "provider_credential_boundary_id": "<invalid>",
                    "source_provider_opt_in_policy_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": sym_dir.name,
                    "credential_boundary_status": "credential_boundary_invalid",
                    "credential_boundary_scope": "future_provider_credentials_only",
                    "credential_loading_state": "not_implemented",
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
                    "provider_credential_boundary_id": "<invalid>",
                    "source_provider_opt_in_policy_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "credential_boundary_status": "credential_boundary_invalid",
                    "credential_boundary_scope": "future_provider_credentials_only",
                    "credential_loading_state": "not_implemented",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "unsupported_provider_credential_boundary_schema",
                    "created_at": "",
                })
                continue

            cleaned, error = safe_validate_provider_credential_boundary_data(raw, workspace_path)
            if error:
                invalid_items.append({
                    "provider_credential_boundary_id": "<invalid>",
                    "source_provider_opt_in_policy_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "credential_boundary_status": "credential_boundary_invalid",
                    "credential_boundary_scope": "future_provider_credentials_only",
                    "credential_loading_state": "not_implemented",
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
                "provider_credential_boundary_id": cleaned.get("provider_credential_boundary_id", ""),
                "source_provider_opt_in_policy_id": cleaned.get("source_provider_opt_in_policy_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", ""),
                "credential_boundary_status": cleaned.get("credential_boundary_status", ""),
                "credential_boundary_scope": cleaned.get("credential_boundary_scope", ""),
                "credential_loading_state": cleaned.get("credential_loading_state", ""),
                "created_at": cleaned.get("created_at", ""),
                "artifact_path": cleaned.get("artifact_path", ""),
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "warnings_count": len(cleaned.get("warnings", [])),
            })

    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    invalid_items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items + invalid_items


def summarize_provider_credential_boundary_for_run(
    run_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    """Read-only summary of the latest credential boundary for a research run.

    Does NOT create artifacts. Returns a safe envelope if no boundary is found.
    """
    safe_run_id = validate_run_id(run_id)

    all_boundaries = iter_provider_credential_boundary_artifacts(workspace_path)
    run_boundaries = [b for b in all_boundaries if b.get("source_run_id") == safe_run_id and not b.get("_invalid")]

    if not run_boundaries:
        return {
            "ok": False,
            "status": "provider_credential_boundary_missing",
            "run_id": safe_run_id,
            "symbol": "",
            "credential_boundary_status": "credential_boundary_invalid",
            "credential_loading_state": "not_implemented",
            "credentials_loaded": False,
            "credential_value_present": False,
            "env_read_attempted": False,
            "dotenv_loaded": False,
            "provider_execution_allowed": False,
            "blocking_reasons": ["No credential boundary found for this run."],
            "warnings": ["No provider credential boundary artifact exists for the given run_id."],
        }

    latest = run_boundaries[0]

    return {
        "ok": True,
        "status": "research_provider_credential_boundary_summary",
        "run_id": safe_run_id,
        "symbol": latest.get("symbol", ""),
        "credential_boundary_status": latest.get("credential_boundary_status", "credential_boundary_invalid"),
        "credential_loading_state": latest.get("credential_loading_state", "not_implemented"),
        "credentials_loaded": False,
        "credential_value_present": False,
        "env_read_attempted": False,
        "dotenv_loaded": False,
        "provider_execution_allowed": False,
        "blocking_reasons": ["Provider execution is blocked and not implemented."],
        "warnings": [],
    }
