"""Provider outbound payload preview — local, configless payload preview artifact.

This module creates, loads, lists, shows, validates, replays, and summarizes provider
outbound payload preview artifacts. It does NOT call any real provider, does NOT perform
network requests, does NOT read API keys, does NOT read os.environ, does NOT load .env.atlas,
does NOT import provider SDKs, and does NOT touch brokers.

A provider outbound payload preview records the safe bounds of what a future provider
request might look like after minimization and redaction, without actually sending it.
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

PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_CONTRACT_VERSION = "research_provider_outbound_payload_preview_v1"

_PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_PREVIEW_STATUSES = {
    "payload_preview_recorded",
    "manual_review_required",
    "payload_preview_invalid",
}

_VALID_PREVIEW_SCOPES = {
    "future_provider_request_preview_only",
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
    "future_provider_execution_possible",
    "trading_signal_generated",
    "approval_created",
    "pending_order_created",
    "broker_touched",
    "payload_body_stored",
    "raw_prompt_stored",
    "raw_provider_request_stored",
    "raw_provider_response_stored",
    "absolute_paths_included",
    "secrets_included",
    "broker_credentials_included",
    "trading_instruction_included",
    "forbidden_fragments_raw_stored",
]


@dataclass(frozen=True)
class ProviderOutboundPayloadPreviewValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_preview_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        value = str(value)
    return sanitize_contract_text(value, max_chars)


def validate_provider_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_provider")
    if value not in _get_disabled_provider_ids():
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_provider")
    return value


def validate_model_id(value: str) -> str:
    if not value:
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_model")
    if len(value) > _MAX_MODEL_ID_CHARS:
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_model")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_model")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-./:")
    if not all(ch in allowed for ch in value):
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_model")
    return value


def validate_payload_preview_status(value: str) -> str:
    if not value or value not in _VALID_PREVIEW_STATUSES:
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_status")
    return value


def validate_payload_preview_scope(value: str) -> str:
    if not value or value not in _VALID_PREVIEW_SCOPES:
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_status")
    return value


def provider_outbound_payload_preview_sha256(data: dict[str, Any]) -> str:
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    for flag in _BOOLEAN_SAFETY_FLAGS:
        if data.get(flag) is not False:
            return "provider_outbound_payload_preview_impossible_boolean"
    return None


def _build_payload_shape() -> dict[str, Any]:
    return {
        "request_family": "chat_like_preview",
        "message_count_estimate": 0,
        "max_output_tokens_policy": "bounded_by_model",
        "temperature_policy": "deterministic",
        "tool_calls_allowed": False,
        "streaming_allowed": False,
        "system_prompt_included": False,
        "user_prompt_included": False,
        "raw_body_included": False,
    }


def _build_payload_minimization_summary() -> dict[str, Any]:
    return {
        "minimization_required": True,
        "raw_prompt_omitted": True,
        "artifact_links_used_instead_of_raw_text": True,
        "hashes_used_instead_of_raw_content": True,
        "only_bounded_summaries_allowed": True,
        "broker_data_omitted": True,
        "absolute_paths_omitted": True,
    }


def _build_payload_redaction_summary() -> dict[str, Any]:
    return {
        "redaction_required": True,
        "redaction_applied": True,
        "secrets_redacted": True,
        "absolute_paths_redacted": True,
        "broker_credentials_redacted": True,
        "raw_exception_text_redacted": True,
        "redaction_profile": "atlas_provider_payload_preview_v1",
        "raw_denylist_fragments_stored": False,
    }


def _build_blocked_fields() -> list[str]:
    return [
        "credentials",
        "authorization_headers",
        "absolute_paths",
        "broker_credentials",
        "raw_prompt_body",
        "raw_provider_request_body",
        "raw_provider_response_body",
        "live_trading_instructions",
        "order_submission_fields",
    ]


def build_provider_outbound_payload_preview_dict(
    source_boundary: dict[str, Any],
    preview_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    validate_contract_lineage_id(preview_id, "provider_outbound_payload_preview_id")

    source_provider_credential_boundary_id = source_boundary.get("provider_credential_boundary_id", "")
    validate_contract_lineage_id(source_provider_credential_boundary_id, "source_provider_credential_boundary_id")
    source_provider_opt_in_policy_id = source_boundary.get("source_provider_opt_in_policy_id", "")
    validate_contract_lineage_id(source_provider_opt_in_policy_id, "source_provider_opt_in_policy_id")
    source_provider_preflight_freeze_id = source_boundary.get("source_provider_preflight_freeze_id", "")
    validate_contract_lineage_id(source_provider_preflight_freeze_id, "source_provider_preflight_freeze_id")
    source_provider_execution_readiness_report_id = source_boundary.get("source_provider_execution_readiness_report_id", "")
    validate_contract_lineage_id(source_provider_execution_readiness_report_id, "source_provider_execution_readiness_report_id")
    source_provider_execution_audit_packet_id = source_boundary.get("source_provider_execution_audit_packet_id", "")
    validate_contract_lineage_id(source_provider_execution_audit_packet_id, "source_provider_execution_audit_packet_id")
    source_provider_execution_state_id = source_boundary.get("source_provider_execution_state_id", "")
    validate_contract_lineage_id(source_provider_execution_state_id, "source_provider_execution_state_id")
    source_provider_execution_dry_run_id = source_boundary.get("source_provider_execution_dry_run_id", "")
    validate_contract_lineage_id(source_provider_execution_dry_run_id, "source_provider_execution_dry_run_id")
    source_provider_call_plan_id = source_boundary.get("source_provider_call_plan_id", "")
    validate_contract_lineage_id(source_provider_call_plan_id, "source_provider_call_plan_id")
    source_sandbox_request_id = source_boundary.get("source_sandbox_request_id", "")
    validate_contract_lineage_id(source_sandbox_request_id, "source_sandbox_request_id")
    source_prompt_packet_id = source_boundary.get("source_prompt_packet_id", "")
    validate_contract_lineage_id(source_prompt_packet_id, "source_prompt_packet_id")
    source_run_id = source_boundary.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    symbol = validate_contract_symbol(source_boundary.get("symbol", ""))
    safe_provider_id = validate_provider_id(source_boundary.get("provider_id", ""))
    safe_model_id = validate_model_id(source_boundary.get("model_id", ""))

    created_at = datetime.now(UTC)

    artifact_path_rel = f".atlas/research/{symbol}/provider_outbound_payload_previews/{preview_id}.json"

    payload_shape = _build_payload_shape()
    payload_minimization_summary = _build_payload_minimization_summary()
    payload_redaction_summary = _build_payload_redaction_summary()
    blocked_fields = _build_blocked_fields()
    omitted_fields = []
    allowed_field_summary = ["model", "messages", "temperature", "max_tokens"]

    # Calculate a stable dummy hash for the preview since it doesn't hold raw data
    payload_hash = hashlib.sha256("empty_payload_preview_by_design".encode("utf-8")).hexdigest()

    warnings = [
        "This is a local payload preview. No provider was called.",
        "No network request was sent.",
        "No payload is actually constructed.",
        "Real provider execution requires explicit future opt-in."
    ]

    metadata = {
        "source_boundary_schema_version": source_boundary.get("schema_version", ""),
        "source_boundary_contract_version": source_boundary.get("contract_version", ""),
    }

    source_boundary_hash = source_boundary.get("artifact_hash", "")

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_outbound_payload_preview",
        "contract_version": PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_CONTRACT_VERSION,
        "provider_outbound_payload_preview_id": preview_id,
        "source_provider_credential_boundary_id": source_provider_credential_boundary_id,
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
        "payload_preview_status": "payload_preview_recorded",
        "payload_preview_scope": "future_provider_request_preview_only",
        "payload_shape": payload_shape,
        "payload_minimization_summary": payload_minimization_summary,
        "payload_redaction_summary": payload_redaction_summary,
        "payload_hash": payload_hash,
        "payload_hash_algorithm": "sha256",
        "payload_body_stored": False,
        "raw_prompt_stored": False,
        "raw_provider_request_stored": False,
        "raw_provider_response_stored": False,
        "absolute_paths_included": False,
        "secrets_included": False,
        "broker_credentials_included": False,
        "trading_instruction_included": False,
        "forbidden_fragments_raw_stored": False,
        "blocked_fields": blocked_fields,
        "omitted_fields": omitted_fields,
        "allowed_field_summary": allowed_field_summary,
        "source_credential_boundary_hash": source_boundary_hash,
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
        "future_provider_execution_possible": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": metadata,
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_outbound_payload_preview_sha256(artifact)
    return artifact


def create_provider_outbound_payload_preview(
    workspace_path: Path,
    boundary_id: str,
) -> dict[str, Any]:
    safe_boundary_id = validate_run_id(boundary_id)

    from atlas_agent.research.provider_credential_boundary import (
        find_provider_credential_boundary_by_id,
        load_and_validate_provider_credential_boundary,
    )

    boundary_path = find_provider_credential_boundary_by_id(workspace_path, safe_boundary_id)
    if boundary_path is None:
        raise ResearchSessionError("provider_credential_boundary_not_found")

    source_boundary = load_and_validate_provider_credential_boundary(boundary_path, workspace_path)

    preview_id = generate_run_id()
    artifact = build_provider_outbound_payload_preview_dict(
        source_boundary,
        preview_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    preview_dir = workspace_path / RESEARCH_DIR / symbol / "provider_outbound_payload_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_outbound_payload_preview_created",
        "provider_outbound_payload_preview_id": preview_id,
        "source_provider_credential_boundary_id": safe_boundary_id,
        "payload_preview_status": artifact["payload_preview_status"],
        "payload_body_stored": False,
        "outbound_request_sent": False,
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_outbound_payload_preview_{field_name}"
    return None


def safe_validate_provider_outbound_payload_preview_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_outbound_payload_preview_schema"

    if data.get("artifact_type") != "provider_outbound_payload_preview":
        return None, "provider_outbound_payload_preview_malformed"

    if data.get("contract_version") != PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_CONTRACT_VERSION:
        return None, "provider_outbound_payload_preview_malformed"

    try:
        validate_payload_preview_status(data.get("payload_preview_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_outbound_payload_preview_status"

    try:
        validate_payload_preview_scope(data.get("payload_preview_scope", ""))
    except ResearchSessionError:
        return None, "invalid_provider_outbound_payload_preview_status"

    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    if data.get("mode") != "paper":
        return None, "provider_outbound_payload_preview_malformed"

    for field in (
        "provider_outbound_payload_preview_id",
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
            return None, "invalid_provider_outbound_payload_preview_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_outbound_payload_preview_lineage"

    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_outbound_payload_preview_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_outbound_payload_preview_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_outbound_payload_preview_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_outbound_payload_preview_hash_mismatch"

    if workspace_path is not None and not for_replay:
        source_boundary_id = data.get("source_provider_credential_boundary_id", "")
        if source_boundary_id:
            try:
                from atlas_agent.research.provider_credential_boundary import (
                    find_provider_credential_boundary_by_id,
                    load_provider_credential_boundary,
                )

                boundary_path = find_provider_credential_boundary_by_id(workspace_path, source_boundary_id)
                if boundary_path is None:
                    return None, "provider_outbound_payload_preview_source_boundary_missing"
                boundary_data = load_provider_credential_boundary(boundary_path, workspace_path)
                stored_boundary_hash = data.get("source_credential_boundary_hash", "")
                actual_boundary_hash = boundary_data.get("artifact_hash", "")
                if stored_boundary_hash != actual_boundary_hash:
                    return None, "provider_outbound_payload_preview_source_boundary_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_outbound_payload_preview_source_boundary_missing"

    text_fields = [
        json.dumps(data.get("payload_shape", {})),
        json.dumps(data.get("payload_minimization_summary", {})),
        json.dumps(data.get("payload_redaction_summary", {})),
        json.dumps(data.get("blocked_fields", [])),
        json.dumps(data.get("omitted_fields", [])),
        json.dumps(data.get("allowed_field_summary", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_outbound_payload_preview_malformed"

    policy_summaries = [
        data.get("payload_preview_status", ""),
        data.get("payload_preview_scope", ""),
    ]
    if any(_has_forbidden_fragments(str(s)) for s in policy_summaries):
        return None, "provider_outbound_payload_preview_forbidden_payload_claim"

    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_outbound_payload_preview_malformed"

    # Return a cleaned copy
    cleaned = {k: v for k, v in data.items()}
    return cleaned, None


def validate_provider_outbound_payload_preview_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderOutboundPayloadPreviewValidationResult:
    data = load_provider_outbound_payload_preview(path, workspace_path)
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
            at == "provider_outbound_payload_preview",
            "artifact_type must be provider_outbound_payload_preview." if at != "provider_outbound_payload_preview" else "artifact_type is correct.",
        )
    )

    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_CONTRACT_VERSION,
            "contract_version must match current contract." if cv != PROVIDER_OUTBOUND_PAYLOAD_PREVIEW_CONTRACT_VERSION else "contract_version matches.",
        )
    )

    payload_preview_status = data.get("payload_preview_status", "")
    status_ok = payload_preview_status in _VALID_PREVIEW_STATUSES
    checks.append(
        _check_name(
            "payload_preview_status_valid",
            status_ok,
            "payload_preview_status is invalid." if not status_ok else "payload_preview_status is valid.",
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

    computed = provider_outbound_payload_preview_sha256(data)
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

    return ProviderOutboundPayloadPreviewValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation="Proceed with payload preview." if valid else "Reject artifact and investigate tampering.",
        warnings=warnings,
    )


def load_provider_outbound_payload_preview(path: Path, workspace_path: Path | None = None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception as e:
        raise ResearchSessionError("provider_outbound_payload_preview_malformed") from e

    cleaned, err = safe_validate_provider_outbound_payload_preview_data(data, workspace_path=workspace_path)
    if err:
        raise ResearchSessionError(err)
    if not cleaned:
        raise ResearchSessionError("provider_outbound_payload_preview_malformed")
    return cleaned


def load_and_validate_provider_outbound_payload_preview(path: Path, workspace_path: Path) -> dict[str, Any]:
    data = load_provider_outbound_payload_preview(path, workspace_path)
    res = validate_provider_outbound_payload_preview_artifact(path, workspace_path)
    if not res.valid:
        raise ResearchSessionError("invalid_provider_outbound_payload_preview_artifact")
    return data


def find_provider_outbound_payload_preview_by_id(workspace_path: Path, preview_id: str) -> Path | None:
    safe_id = validate_run_id(preview_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    for p in search_dir.rglob("provider_outbound_payload_previews/*.json"):
        if p.stem == safe_id:
            return p
    return None


def replay_provider_outbound_payload_preview(
    workspace_path: Path,
    preview_id: str,
) -> dict[str, Any]:
    safe_id = validate_run_id(preview_id)
    artifact_path = find_provider_outbound_payload_preview_by_id(workspace_path, safe_id)
    if not artifact_path:
        raise ResearchSessionError("provider_outbound_payload_preview_not_found")

    old_artifact = load_provider_outbound_payload_preview(artifact_path, workspace_path=None)

    source_boundary_id = old_artifact.get("source_provider_credential_boundary_id", "")
    from atlas_agent.research.provider_credential_boundary import (
        find_provider_credential_boundary_by_id,
        load_provider_credential_boundary,
    )

    boundary_path = find_provider_credential_boundary_by_id(workspace_path, source_boundary_id)
    if not boundary_path:
        raise ResearchSessionError("provider_outbound_payload_preview_source_boundary_missing")

    source_boundary = load_provider_credential_boundary(boundary_path, workspace_path)

    new_artifact = build_provider_outbound_payload_preview_dict(
        source_boundary,
        safe_id,
        workspace_path,
    )

    new_artifact["created_at"] = old_artifact.get("created_at", new_artifact["created_at"])
    new_artifact["artifact_hash"] = provider_outbound_payload_preview_sha256(new_artifact)

    old_hash = old_artifact.get("artifact_hash", "")
    new_hash = new_artifact["artifact_hash"]
    match = old_hash == new_hash

    return {
        "ok": True,
        "match": match,
        "provider_outbound_payload_preview_id": safe_id,
        "original_hash": old_hash,
        "replayed_hash": new_hash,
        "status": "research_provider_outbound_payload_preview_replay",
        "payload_body_stored": False,
        "outbound_request_sent": False,
    }


def iter_provider_outbound_payload_preview_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider outbound payload preview artifact metadata dicts, newest first.

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
        preview_dir = sym_dir / "provider_outbound_payload_previews"
        if not preview_dir.exists():
            continue
        for path in preview_dir.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                invalid_items.append({
                    "provider_outbound_payload_preview_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "payload_preview_status": "invalid",
                    "payload_preview_scope": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_outbound_payload_preview_artifact",
                })
                continue
            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_outbound_payload_preview_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "payload_preview_status": "invalid",
                    "payload_preview_scope": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_outbound_payload_preview_artifact",
                })
                continue
            cleaned, error = safe_validate_provider_outbound_payload_preview_data(raw, workspace_path=workspace_path)
            if error or cleaned is None:
                invalid_items.append({
                    "provider_outbound_payload_preview_id": "<invalid>",
                    "symbol": "<invalid>",
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "payload_preview_status": "invalid",
                    "payload_preview_scope": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "invalid_provider_outbound_payload_preview_artifact",
                })
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            items.append({
                "provider_outbound_payload_preview_id": cleaned.get("provider_outbound_payload_preview_id", path.stem),
                "source_provider_credential_boundary_id": cleaned.get("source_provider_credential_boundary_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", sym_dir.name),
                "payload_preview_status": cleaned.get("payload_preview_status", ""),
                "payload_preview_scope": cleaned.get("payload_preview_scope", ""),
                "artifact_path": rel_path,
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "created_at": cleaned.get("created_at", ""),
            })

    items.sort(key=lambda i: i["created_at"], reverse=True)
    # Append invalid items at the end so they are visible but don't pollute primary list ordering
    return items + invalid_items


def _find_latest_provider_outbound_payload_preview_for_run(workspace_path: Path, run_id: str) -> Path | None:
    safe_run_id = validate_run_id(run_id)
    search_dir = workspace_path / RESEARCH_DIR
    if not search_dir.exists():
        return None
    latest_path: Path | None = None
    latest_time = ""
    for p in search_dir.rglob("provider_outbound_payload_previews/*.json"):
        try:
            data = load_provider_outbound_payload_preview(p, workspace_path=None)
            if data.get("source_run_id") == safe_run_id:
                t = data.get("created_at", "")
                if not latest_time or t > latest_time:
                    latest_time = t
                    latest_path = p
        except Exception:
            pass
    return latest_path


def summarize_provider_outbound_payload_preview_state(workspace_path: Path, run_id: str) -> dict[str, Any]:
    safe_run_id = validate_run_id(run_id)
    artifact_path = _find_latest_provider_outbound_payload_preview_for_run(workspace_path, safe_run_id)

    if not artifact_path:
        return {
            "ok": True,
            "status": "missing_provider_outbound_payload_preview",
            "provider_outbound_payload_preview_id": None,
            "payload_preview_status": "not_recorded",
            "payload_body_stored": False,
            "outbound_request_sent": False,
            "credentials_loaded": False,
            "artifact_path": None,
        }

    try:
        data = load_and_validate_provider_outbound_payload_preview(artifact_path, workspace_path)
    except ResearchSessionError:
        return {
            "ok": True,
            "status": "invalid_provider_outbound_payload_preview",
            "provider_outbound_payload_preview_id": None,
            "payload_preview_status": "invalid",
            "payload_body_stored": False,
            "outbound_request_sent": False,
            "credentials_loaded": False,
            "artifact_path": None,
        }

    return {
        "ok": True,
        "status": "research_provider_outbound_payload_preview_summary",
        "provider_outbound_payload_preview_id": data.get("provider_outbound_payload_preview_id"),
        "payload_preview_status": data.get("payload_preview_status"),
        "payload_body_stored": False,
        "outbound_request_sent": False,
        "credentials_loaded": False,
        "artifact_path": data.get("artifact_path"),
    }
