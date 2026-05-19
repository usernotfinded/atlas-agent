"""Provider execution dry-run — local, auditable preflight artifacts.

This module prepares local, auditable provider execution dry-run artifacts.
It does NOT call any real provider, does NOT perform network requests,
does NOT read API keys, and does NOT import provider SDKs.
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

PROVIDER_EXECUTION_DRY_RUN_CONTRACT_VERSION = "research_provider_execution_dry_run_v1"

_PROVIDER_EXECUTION_DRY_RUN_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_DRY_RUN_SUMMARY_CHARS = 4000


@dataclass(frozen=True)
class ProviderExecutionDryRunValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets

    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_dry_run_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
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


def provider_execution_dry_run_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_EXECUTION_DRY_RUN_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def build_provider_execution_dry_run_dict(
    source_call_plan: dict[str, Any],
    provider_id: str,
    model_id: str,
    provider_execution_dry_run_id: str,
) -> dict[str, Any]:
    """Build a provider execution dry-run artifact dict in memory.

    No network. No API keys. No provider SDKs.
    """
    # Validate lineage IDs
    validate_contract_lineage_id(provider_execution_dry_run_id, "provider_execution_dry_run_id")
    source_provider_call_plan_id = source_call_plan.get("provider_call_plan_id", "")
    validate_contract_lineage_id(source_provider_call_plan_id, "source_provider_call_plan_id")
    source_sandbox_request_id = source_call_plan.get("source_sandbox_request_id", "")
    validate_contract_lineage_id(source_sandbox_request_id, "source_sandbox_request_id")
    source_prompt_packet_id = source_call_plan.get("source_prompt_packet_id", "")
    validate_contract_lineage_id(source_prompt_packet_id, "source_prompt_packet_id")
    source_run_id = source_call_plan.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    # Validate symbol
    symbol = validate_contract_symbol(source_call_plan.get("symbol", ""))

    # Validate provider and model
    safe_provider_id = validate_provider_id(provider_id)
    safe_model_id = validate_model_id(model_id)

    # Determine request shape from disabled metadata
    request_shape = "chat_completions"
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets

    for target in list_disabled_provider_call_targets():
        if target["provider_id"] == safe_provider_id:
            request_shape = target["supported_request_shape"]
            break

    created_at = datetime.now(UTC)

    # Build deterministic dry-run summary
    raw_summary = (
        f"Dry-run preflight for {safe_provider_id} / {safe_model_id}. "
        f"Derived from provider call plan {source_provider_call_plan_id}. "
        f"Request shape: {request_shape}. No network call. No API key loaded. "
        f"Execution mode: dry_run_only."
    )
    dry_run_summary = sanitize_dry_run_text(raw_summary, _MAX_DRY_RUN_SUMMARY_CHARS)

    # Constraints and forbidden actions
    constraints = [
        "Provider is disabled.",
        "No network request is made.",
        "No API key is read or loaded.",
        "No broker is contacted.",
        "No order is generated or submitted.",
        "No live trading is authorized.",
        "Execution mode is dry_run_only.",
    ]

    forbidden_actions = [
        "Execute live trade",
        "Submit order to broker",
        "Create pending order",
        "Authorize live trading",
        "Load or transmit API key",
        "Make network request to provider",
        "Actually call provider",
    ]

    # Hash lineage
    source_plan_hash = source_call_plan.get("artifact_hash", "")
    input_hash = hashlib.sha256(str(source_plan_hash).encode("utf-8")).hexdigest()

    # Redaction summary
    redacted_count = sum(1 for frag in FORBIDDEN_FRAGMENTS if frag in str(source_call_plan))
    redaction_summary = {
        "redacted_fragments_count": redacted_count,
        "forbidden_fragments_checked": len(FORBIDDEN_FRAGMENTS),
    }

    warnings = [
        "This is a dry-run preflight artifact. No provider was called.",
        "Provider is disabled. Enablement requires explicit configuration and approval.",
        "actual_provider_call_made is False by design.",
    ]

    artifact_path_rel = f".atlas/research/{symbol}/provider_execution_dry_runs/{provider_execution_dry_run_id}.json"

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_execution_dry_run",
        "contract_version": PROVIDER_EXECUTION_DRY_RUN_CONTRACT_VERSION,
        "provider_execution_dry_run_id": provider_execution_dry_run_id,
        "source_provider_call_plan_id": source_provider_call_plan_id,
        "source_sandbox_request_id": source_sandbox_request_id,
        "source_prompt_packet_id": source_prompt_packet_id,
        "source_run_id": source_run_id,
        "symbol": symbol,
        "mode": "paper",
        "provider_id": safe_provider_id,
        "model_id": safe_model_id,
        "provider_enabled": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "would_call_provider": False,
        "actual_provider_call_made": False,
        "execution_mode": "dry_run_only",
        "request_shape": request_shape,
        "dry_run_summary": dry_run_summary,
        "input_hash": input_hash,
        "source_call_plan_hash": source_plan_hash,
        "constraints": constraints,
        "forbidden_actions": forbidden_actions,
        "redaction_summary": redaction_summary,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": {
            "max_summary_chars": _MAX_DRY_RUN_SUMMARY_CHARS,
            "source_call_plan_schema_version": source_call_plan.get("schema_version", ""),
        },
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_execution_dry_run_sha256(artifact)
    return artifact


def create_provider_execution_dry_run(
    workspace_path: Path,
    provider_call_plan_id: str,
) -> dict[str, Any]:
    """Create and persist a provider execution dry-run artifact.

    Loads the provider call plan, builds the dry-run artifact, and writes it to disk.
    """
    safe_plan_id = validate_run_id(provider_call_plan_id)

    from atlas_agent.research.provider_call_plan import (
        find_provider_call_plan_by_id,
        load_and_validate_provider_call_plan,
    )

    plan_path = find_provider_call_plan_by_id(workspace_path, safe_plan_id)
    if plan_path is None:
        raise ResearchSessionError("provider_call_plan_not_found")

    source_call_plan = load_and_validate_provider_call_plan(plan_path, workspace_path)

    provider_id = source_call_plan.get("provider_id", "")
    model_id = source_call_plan.get("model_id", "")

    dry_run_id = generate_run_id()
    artifact = build_provider_execution_dry_run_dict(
        source_call_plan,
        provider_id,
        model_id,
        dry_run_id,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    dry_run_dir = workspace_path / RESEARCH_DIR / symbol / "provider_execution_dry_runs"
    dry_run_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return artifact


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    """Return static error code if value contains forbidden fragments or unsafe chars."""
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_execution_dry_run_{field_name}"
    return None


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    """Return error code if any boolean safety flag is not False."""
    flags = [
        "provider_enabled",
        "network_enabled",
        "credentials_loaded",
        "provider_call_allowed",
        "would_call_provider",
        "actual_provider_call_made",
    ]
    for flag in flags:
        if data.get(flag) is not False:
            return "provider_execution_dry_run_impossible_boolean"
    return None


def _check_impossible_boolean_combinations(data: dict[str, Any]) -> str | None:
    """Detect impossible boolean combinations (e.g. call_allowed=false but actual_call=true)."""
    provider_call_allowed = data.get("provider_call_allowed")
    actual_provider_call_made = data.get("actual_provider_call_made")
    would_call_provider = data.get("would_call_provider")

    if actual_provider_call_made is True and provider_call_allowed is not True:
        return "provider_execution_dry_run_impossible_boolean"
    if would_call_provider is True and provider_call_allowed is not True:
        return "provider_execution_dry_run_impossible_boolean"
    if actual_provider_call_made is True and would_call_provider is not True:
        return "provider_execution_dry_run_impossible_boolean"
    return None


def safe_validate_provider_execution_dry_run_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Strictly validate a loaded provider execution dry-run artifact for read paths.

    Returns (cleaned_data, None) if valid, or (None, error_code) if invalid.
    Never includes raw tampered values in error codes.
    """
    # 1. schema_version
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_execution_dry_run_schema"

    # 2. artifact_type
    if data.get("artifact_type") != "provider_execution_dry_run":
        return None, "provider_execution_dry_run_malformed"

    # 3. contract_version
    if data.get("contract_version") != PROVIDER_EXECUTION_DRY_RUN_CONTRACT_VERSION:
        return None, "provider_execution_dry_run_malformed"

    # 4. mode and execution_mode
    if data.get("mode") != "paper":
        return None, "provider_execution_dry_run_malformed"
    if data.get("execution_mode") != "dry_run_only":
        return None, "provider_execution_dry_run_malformed"

    # 5. boolean safety flags (all must be False)
    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    # 5b. impossible boolean combinations
    error = _check_impossible_boolean_combinations(data)
    if error:
        return None, error

    # 6. lineage IDs — reject if unsafe
    for field in (
        "provider_execution_dry_run_id",
        "source_provider_call_plan_id",
        "source_sandbox_request_id",
        "source_prompt_packet_id",
        "source_run_id",
    ):
        value = data.get(field, "")
        try:
            validate_contract_lineage_id(value, field)
        except ResearchSessionError:
            return None, "invalid_provider_execution_dry_run_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    # 7. symbol
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_dry_run_lineage"

    # 8. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_dry_run_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    # 9. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_dry_run_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    # 10. hash consistency
    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_execution_dry_run_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_execution_dry_run_hash_mismatch"

    # 11. source call plan exists and hash matches (if workspace provided)
    if workspace_path is not None:
        source_plan_id = data.get("source_provider_call_plan_id", "")
        if source_plan_id:
            try:
                from atlas_agent.research.provider_call_plan import (
                    find_provider_call_plan_by_id,
                    load_provider_call_plan,
                )

                plan_path = find_provider_call_plan_by_id(workspace_path, source_plan_id)
                if plan_path is None:
                    return None, "provider_execution_dry_run_source_missing"
                plan_data = load_provider_call_plan(plan_path, workspace_path)
                stored_plan_hash = data.get("source_call_plan_hash", "")
                actual_plan_hash = plan_data.get("artifact_hash", "")
                if stored_plan_hash != actual_plan_hash:
                    return None, "provider_execution_dry_run_source_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_dry_run_source_missing"

    # 12. no forbidden fragments in text fields
    text_fields = [
        data.get("dry_run_summary", ""),
        data.get("request_shape", ""),
        json.dumps(data.get("constraints", [])),
        json.dumps(data.get("forbidden_actions", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_execution_dry_run_malformed"

    # 13. path containment
    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_execution_dry_run_malformed"

    # Return a cleaned copy with only safe fields
    cleaned = {
        "schema_version": data.get("schema_version", ""),
        "artifact_type": data.get("artifact_type", ""),
        "contract_version": data.get("contract_version", ""),
        "provider_execution_dry_run_id": data.get("provider_execution_dry_run_id", ""),
        "source_provider_call_plan_id": data.get("source_provider_call_plan_id", ""),
        "source_sandbox_request_id": data.get("source_sandbox_request_id", ""),
        "source_prompt_packet_id": data.get("source_prompt_packet_id", ""),
        "source_run_id": data.get("source_run_id", ""),
        "symbol": data.get("symbol", ""),
        "mode": data.get("mode", ""),
        "provider_id": data.get("provider_id", ""),
        "model_id": data.get("model_id", ""),
        "provider_enabled": data.get("provider_enabled", False),
        "network_enabled": data.get("network_enabled", False),
        "credentials_loaded": data.get("credentials_loaded", False),
        "provider_call_allowed": data.get("provider_call_allowed", False),
        "would_call_provider": data.get("would_call_provider", False),
        "actual_provider_call_made": data.get("actual_provider_call_made", False),
        "execution_mode": data.get("execution_mode", ""),
        "request_shape": data.get("request_shape", ""),
        "dry_run_summary": data.get("dry_run_summary", ""),
        "input_hash": data.get("input_hash", ""),
        "source_call_plan_hash": data.get("source_call_plan_hash", ""),
        "constraints": data.get("constraints", []),
        "forbidden_actions": data.get("forbidden_actions", []),
        "redaction_summary": data.get("redaction_summary", {}),
        "artifact_path": data.get("artifact_path", ""),
        "warnings": data.get("warnings", []),
        "metadata": data.get("metadata", {}),
        "artifact_hash": data.get("artifact_hash", ""),
        "created_at": data.get("created_at", ""),
    }
    return cleaned, None


def validate_provider_execution_dry_run_artifact(
    data: dict[str, Any],
    workspace_path: Path | None = None,
) -> ProviderExecutionDryRunValidationResult:
    """Validate a provider execution dry-run artifact against the local contract."""
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
            at == "provider_execution_dry_run",
            "artifact_type must be provider_execution_dry_run."
            if at != "provider_execution_dry_run"
            else "artifact_type is correct.",
        )
    )

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_EXECUTION_DRY_RUN_CONTRACT_VERSION,
            "contract_version must match current contract."
            if cv != PROVIDER_EXECUTION_DRY_RUN_CONTRACT_VERSION
            else "contract_version matches.",
        )
    )

    # 4. mode = paper
    mode = data.get("mode")
    checks.append(
        _check_name(
            "mode_is_paper",
            mode == "paper",
            "mode must be paper." if mode != "paper" else "mode is paper.",
        )
    )

    # 5. execution_mode = dry_run_only
    execution_mode = data.get("execution_mode")
    checks.append(
        _check_name(
            "execution_mode_dry_run_only",
            execution_mode == "dry_run_only",
            "execution_mode must be dry_run_only."
            if execution_mode != "dry_run_only"
            else "execution_mode is dry_run_only.",
        )
    )

    # 6. provider state flags
    for flag_name in (
        "provider_enabled",
        "network_enabled",
        "credentials_loaded",
        "provider_call_allowed",
        "would_call_provider",
        "actual_provider_call_made",
    ):
        checks.append(
            _check_name(
                f"{flag_name}_false",
                data.get(flag_name) is False,
                f"{flag_name} must be False."
                if data.get(flag_name) is not False
                else f"{flag_name} is False.",
            )
        )

    # 6b. impossible boolean combinations
    impossible = _check_impossible_boolean_combinations(data) is not None
    checks.append(
        _check_name(
            "no_impossible_booleans",
            not impossible,
            "Artifact contains impossible boolean combinations."
            if impossible
            else "No impossible boolean combinations found.",
        )
    )

    # 7. lineage IDs
    lineage_ok = True
    for field in (
        "provider_execution_dry_run_id",
        "source_provider_call_plan_id",
        "source_sandbox_request_id",
        "source_prompt_packet_id",
        "source_run_id",
    ):
        value = data.get(field, "")
        try:
            validate_contract_lineage_id(value, field)
        except ResearchSessionError:
            lineage_ok = False
    checks.append(
        _check_name(
            "lineage_ids_valid",
            lineage_ok,
            "Lineage IDs contain unsafe characters."
            if not lineage_ok
            else "Lineage IDs are valid.",
        )
    )

    # 8. symbol
    symbol_ok = True
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        symbol_ok = False
    checks.append(
        _check_name(
            "symbol_valid",
            symbol_ok,
            "Symbol is invalid." if not symbol_ok else "Symbol is valid.",
        )
    )

    # 9. provider target is disabled
    provider_id = data.get("provider_id", "")
    provider_disabled_ok = False
    try:
        validate_provider_id(provider_id)
        provider_disabled_ok = True
    except ResearchSessionError:
        provider_disabled_ok = False
    checks.append(
        _check_name(
            "provider_target_disabled",
            provider_disabled_ok,
            "Provider target is not in the disabled list."
            if not provider_disabled_ok
            else "Provider target is disabled.",
        )
    )

    # 9b. model_id safety
    model_id = data.get("model_id", "")
    model_ok = False
    try:
        validate_model_id(model_id)
        model_ok = True
    except ResearchSessionError:
        model_ok = False
    checks.append(
        _check_name(
            "model_id_safe",
            model_ok,
            "model_id contains unsafe characters or forbidden fragments."
            if not model_ok
            else "model_id is safe.",
        )
    )

    # 10. hash consistency
    stored_hash = data.get("artifact_hash", "")
    computed_hash = provider_execution_dry_run_sha256(data) if stored_hash else ""
    hash_ok = stored_hash == computed_hash
    checks.append(
        _check_name(
            "artifact_hash_consistent",
            hash_ok,
            "artifact_hash does not match computed hash."
            if not hash_ok
            else "artifact_hash is consistent.",
        )
    )

    # 11. source call plan exists and hash matches (if workspace provided)
    if workspace_path is not None:
        source_plan_id = data.get("source_provider_call_plan_id", "")
        plan_hash_ok = False
        plan_found = False
        if source_plan_id:
            try:
                from atlas_agent.research.provider_call_plan import (
                    find_provider_call_plan_by_id,
                    load_provider_call_plan,
                )

                plan_path = find_provider_call_plan_by_id(workspace_path, source_plan_id)
                if plan_path is not None:
                    plan_found = True
                    plan_data = load_provider_call_plan(plan_path, workspace_path)
                    stored_plan_hash = data.get("source_call_plan_hash", "")
                    actual_plan_hash = plan_data.get("artifact_hash", "")
                    plan_hash_ok = stored_plan_hash == actual_plan_hash
            except ResearchSessionError:
                plan_hash_ok = False
        checks.append(
            _check_name(
                "source_call_plan_exists",
                plan_found,
                "Source provider call plan not found."
                if not plan_found
                else "Source provider call plan exists.",
            )
        )
        checks.append(
            _check_name(
                "source_call_plan_hash_matches",
                plan_hash_ok,
                "Source provider call plan hash does not match."
                if not plan_hash_ok
                else "Source provider call plan hash matches.",
            )
        )

    # 12. no forbidden fragments
    text_fields = [
        data.get("dry_run_summary", ""),
        data.get("request_shape", ""),
        json.dumps(data.get("constraints", [])),
        json.dumps(data.get("forbidden_actions", [])),
    ]
    forbidden_found = any(_has_forbidden_fragments(str(f)) for f in text_fields)
    checks.append(
        _check_name(
            "no_forbidden_fragments",
            not forbidden_found,
            "Artifact contains forbidden fragments."
            if forbidden_found
            else "No forbidden fragments found.",
        )
    )

    # 13. path containment
    path = data.get("artifact_path", "")
    path_ok = not path.startswith("/") or ".atlas/research/" in path
    checks.append(
        _check_name(
            "artifact_path_contained",
            path_ok,
            "artifact_path is not workspace-relative."
            if not path_ok
            else "artifact_path is contained.",
        )
    )

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    valid = failed == 0
    recommendation = "provider_execution_dry_run_valid" if valid else "manual_review_required"
    if not valid:
        warnings.append("Provider execution dry-run validation failed one or more safety checks.")

    return ProviderExecutionDryRunValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def replay_provider_execution_dry_run(
    workspace_path: Path,
    provider_execution_dry_run_id: str,
) -> dict[str, Any]:
    """Replay a provider execution dry-run by rebuilding it and comparing hashes."""
    safe_dry_run_id = validate_run_id(provider_execution_dry_run_id)

    dry_run_path = find_provider_execution_dry_run_by_id(workspace_path, safe_dry_run_id)
    if dry_run_path is None:
        raise ResearchSessionError("provider_execution_dry_run_not_found")

    dry_run = load_and_validate_provider_execution_dry_run(dry_run_path, workspace_path)

    source_plan_id = dry_run.get("source_provider_call_plan_id", "")
    from atlas_agent.research.provider_call_plan import (
        find_provider_call_plan_by_id,
        load_and_validate_provider_call_plan,
    )

    plan_path = find_provider_call_plan_by_id(workspace_path, source_plan_id)
    if plan_path is None:
        raise ResearchSessionError("provider_call_plan_not_found")

    source_call_plan = load_and_validate_provider_call_plan(plan_path, workspace_path)

    provider_id = dry_run.get("provider_id", "")
    model_id = dry_run.get("model_id", "")

    rebuilt = build_provider_execution_dry_run_dict(
        source_call_plan,
        provider_id,
        model_id,
        safe_dry_run_id,
    )

    expected_hash = dry_run.get("artifact_hash", "")
    actual_hash = rebuilt.get("artifact_hash", "")

    match = expected_hash == actual_hash
    checks = [
        _check_name(
            "artifact_hash_match",
            match,
            "Artifact hash matches on replay." if match else "Artifact hash does not match on replay.",
        ),
        _check_name(
            "provider_id_consistent",
            dry_run.get("provider_id") == rebuilt.get("provider_id"),
            "Provider ID consistent.",
        ),
        _check_name(
            "model_id_consistent",
            dry_run.get("model_id") == rebuilt.get("model_id"),
            "Model ID consistent.",
        ),
        _check_name(
            "symbol_consistent",
            dry_run.get("symbol") == rebuilt.get("symbol"),
            "Symbol consistent.",
        ),
    ]

    return {
        "match": match,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "checks": checks,
    }


def find_provider_execution_dry_run_by_id(
    workspace_path: Path,
    dry_run_id: str,
) -> Path | None:
    """Find exactly one provider execution dry-run artifact by ID.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    safe_dry_run_id = validate_run_id(dry_run_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        dry_runs_dir = sym_dir / "provider_execution_dry_runs"
        if not dry_runs_dir.exists():
            continue
        candidate = dry_runs_dir / f"{safe_dry_run_id}.json"
        if candidate.exists() and candidate.is_file():
            if candidate.is_symlink() and not _is_inside_workspace(candidate, workspace_path):
                continue
            matches.append(candidate)

    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_execution_dry_run_id")
    return matches[0]


def load_provider_execution_dry_run(path: Path, workspace_path: Path) -> dict[str, Any]:
    """Load a provider execution dry-run JSON safely."""
    if not path.exists() or not path.is_file():
        raise ResearchSessionError("provider_execution_dry_run_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_execution_dry_run_malformed")
    data["artifact_path"] = path.relative_to(workspace_path).as_posix()
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError("unsupported_provider_execution_dry_run_schema")
    return data


def load_and_validate_provider_execution_dry_run(
    path: Path, workspace_path: Path
) -> dict[str, Any]:
    """Load and strictly validate a provider execution dry-run. Fail closed on tampering."""
    data = load_provider_execution_dry_run(path, workspace_path)
    cleaned, error = safe_validate_provider_execution_dry_run_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_provider_execution_dry_run_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider execution dry-run artifact metadata dicts, newest first.

    Each item is validated before inclusion. Invalid artifacts are returned as
    safe sentinels without raw tampered values.
    """
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        from atlas_agent.research.session import sanitize_symbol

        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "provider_execution_dry_runs")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                dry_runs_dir = sym_dir / "provider_execution_dry_runs"
                if dry_runs_dir.exists():
                    search_dirs.append(dry_runs_dir)

    items: list[dict[str, Any]] = []
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            rel_path = path.relative_to(workspace_path).as_posix()
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                items.append(
                    {
                        "provider_execution_dry_run_id": "<invalid>",
                        "symbol": "<invalid>",
                        "created_at": "",
                        "artifact_path": rel_path,
                        "provider_id": "unknown",
                        "model_id": "unknown",
                        "warnings_count": 1,
                        "_invalid": True,
                    }
                )
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                items.append(
                    {
                        "provider_execution_dry_run_id": "<invalid>",
                        "symbol": "<invalid>",
                        "created_at": "",
                        "artifact_path": rel_path,
                        "provider_id": "unknown",
                        "model_id": "unknown",
                        "warnings_count": 1,
                        "_invalid": True,
                    }
                )
                continue
            cleaned, error = safe_validate_provider_execution_dry_run_data(data, workspace_path)
            if error or cleaned is None:
                items.append(
                    {
                        "provider_execution_dry_run_id": "<invalid>",
                        "symbol": "<invalid>",
                        "created_at": data.get("created_at", ""),
                        "artifact_path": rel_path,
                        "provider_id": "unknown",
                        "model_id": "unknown",
                        "warnings_count": 1,
                        "_invalid": True,
                    }
                )
                continue
            items.append(
                {
                    "provider_execution_dry_run_id": cleaned["provider_execution_dry_run_id"],
                    "source_provider_call_plan_id": cleaned["source_provider_call_plan_id"],
                    "source_run_id": cleaned["source_run_id"],
                    "symbol": cleaned["symbol"],
                    "created_at": cleaned["created_at"],
                    "artifact_path": rel_path,
                    "provider_id": cleaned["provider_id"],
                    "model_id": cleaned["model_id"],
                    "warnings_count": len(cleaned.get("warnings", [])),
                }
            )

    def _sort_key(item: dict[str, Any]) -> str:
        if item.get("_invalid") or item.get("_malformed"):
            return ""
        return item["created_at"]

    items.sort(key=_sort_key, reverse=True)
    return items
