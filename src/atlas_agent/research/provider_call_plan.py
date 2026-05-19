"""Provider call plan — local, auditable provider call-plan artifacts.

This module prepares local, auditable provider call-plan artifacts.
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
    find_sandbox_request_by_id,
    load_sandbox_request,
    sanitize_symbol,
    validate_run_id,
)

PROVIDER_CALL_PLAN_CONTRACT_VERSION = "research_provider_call_plan_v1"

_MAX_MODEL_ID_CHARS = 120
_MAX_REQUEST_SUMMARY_CHARS = 4000


def list_disabled_provider_call_targets() -> list[dict[str, Any]]:
    """Return metadata for all disabled provider call targets.

    No provider is enabled. No network calls are made.
    """
    return [
        {
            "provider_id": "custom-openai-compatible",
            "status": "disabled",
            "enabled": False,
            "network": False,
            "requires_api_key_when_enabled": True,
            "description": "OpenAI-compatible endpoint. Disabled.",
            "supported_request_shape": "chat_completions",
            "notes": "No API key configured. No network call made.",
        },
        {
            "provider_id": "custom-chat-completions-compatible",
            "status": "disabled",
            "enabled": False,
            "network": False,
            "requires_api_key_when_enabled": True,
            "description": "Chat completions compatible endpoint. Disabled.",
            "supported_request_shape": "chat_completions",
            "notes": "No API key configured. No network call made.",
        },
        {
            "provider_id": "custom-responses-compatible",
            "status": "disabled",
            "enabled": False,
            "network": False,
            "requires_api_key_when_enabled": True,
            "description": "Responses-compatible endpoint. Disabled.",
            "supported_request_shape": "responses",
            "notes": "No API key configured. No network call made.",
        },
        {
            "provider_id": "manual-external-provider",
            "status": "disabled",
            "enabled": False,
            "network": False,
            "requires_api_key_when_enabled": True,
            "description": "Manual external provider workflow. Disabled.",
            "supported_request_shape": "manual",
            "notes": "No API key configured. No network call made.",
        },
    ]


@dataclass(frozen=True)
class ProviderCallPlanValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_call_plan_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
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


def provider_call_plan_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in ("artifact_hash", "created_at")}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def build_provider_call_plan_dict(
    sandbox_request: dict[str, Any],
    provider_id: str,
    model_id: str,
    provider_call_plan_id: str,
) -> dict[str, Any]:
    """Build a provider call plan artifact dict in memory.

    No network. No API keys. No provider SDKs.
    """
    # Validate lineage IDs
    validate_contract_lineage_id(provider_call_plan_id, "provider_call_plan_id")
    sandbox_request_id = sandbox_request.get("sandbox_request_id", "")
    validate_contract_lineage_id(sandbox_request_id, "source_sandbox_request_id")
    prompt_packet_id = sandbox_request.get("prompt_packet_id", "")
    validate_contract_lineage_id(prompt_packet_id, "source_prompt_packet_id")
    source_run_id = sandbox_request.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    # Validate symbol
    symbol = validate_contract_symbol(sandbox_request.get("symbol", ""))

    # Validate provider and model
    safe_provider_id = validate_provider_id(provider_id)
    safe_model_id = validate_model_id(model_id)

    # Determine request shape from disabled metadata
    request_shape = "chat_completions"
    for target in list_disabled_provider_call_targets():
        if target["provider_id"] == safe_provider_id:
            request_shape = target["supported_request_shape"]
            break

    created_at = datetime.now(UTC)

    # Build deterministic request summary
    raw_summary = (
        f"Plan-only artifact for {safe_provider_id} / {safe_model_id}. "
        f"Derived from sandbox request {sandbox_request_id}. "
        f"Request shape: {request_shape}. No network call. No API key loaded."
    )
    request_summary = sanitize_call_plan_text(raw_summary, _MAX_REQUEST_SUMMARY_CHARS)

    # Constraints and forbidden actions
    constraints = [
        "Provider is disabled.",
        "No network request is made.",
        "No API key is read or loaded.",
        "No broker is contacted.",
        "No order is generated or submitted.",
        "No live trading is authorized.",
        "Execution mode is plan_only.",
    ]

    forbidden_actions = [
        "Execute live trade",
        "Submit order to broker",
        "Create pending order",
        "Authorize live trading",
        "Load or transmit API key",
        "Make network request to provider",
    ]

    # Hash lineage
    sandbox_content_hash = sandbox_request.get("content_hash", "")
    input_hash = hashlib.sha256(str(sandbox_content_hash).encode("utf-8")).hexdigest()

    # Redaction summary
    redacted_count = sum(1 for frag in FORBIDDEN_FRAGMENTS if frag in str(sandbox_request))
    redaction_summary = {
        "redacted_fragments_count": redacted_count,
        "forbidden_fragments_checked": len(FORBIDDEN_FRAGMENTS),
    }

    warnings = [
        "This is a plan-only artifact. No provider was called.",
        "Provider is disabled. Enablement requires explicit configuration and approval.",
    ]

    artifact_path_rel = f".atlas/research/{symbol}/provider_call_plans/{provider_call_plan_id}.json"

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_call_plan",
        "contract_version": PROVIDER_CALL_PLAN_CONTRACT_VERSION,
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "source_prompt_packet_id": prompt_packet_id,
        "source_run_id": source_run_id,
        "symbol": symbol,
        "mode": "paper",
        "provider_id": safe_provider_id,
        "model_id": safe_model_id,
        "provider_enabled": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "execution_mode": "plan_only",
        "request_shape": request_shape,
        "request_summary": request_summary,
        "input_hash": input_hash,
        "sandbox_request_hash": sandbox_content_hash,
        "constraints": constraints,
        "forbidden_actions": forbidden_actions,
        "redaction_summary": redaction_summary,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": {
            "max_summary_chars": _MAX_REQUEST_SUMMARY_CHARS,
            "source_sandbox_schema_version": sandbox_request.get("schema_version", ""),
        },
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_call_plan_sha256(artifact)
    return artifact


def create_provider_call_plan(
    workspace_path: Path,
    sandbox_request_id: str,
    provider_id: str,
    model_id: str,
) -> dict[str, Any]:
    """Create and persist a provider call plan artifact.

    Loads the sandbox request, builds the plan, and writes it to disk.
    """
    safe_sandbox_request_id = validate_run_id(sandbox_request_id)
    safe_provider_id = validate_provider_id(provider_id)
    safe_model_id = validate_model_id(model_id)

    sandbox_path = find_sandbox_request_by_id(workspace_path, safe_sandbox_request_id)
    if sandbox_path is None:
        raise ResearchSessionError("sandbox_request_not_found")

    sandbox_request = load_sandbox_request(sandbox_path, workspace_path)

    provider_call_plan_id = generate_run_id()
    artifact = build_provider_call_plan_dict(
        sandbox_request,
        safe_provider_id,
        safe_model_id,
        provider_call_plan_id,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    plan_dir = workspace_path / RESEARCH_DIR / symbol / "provider_call_plans"
    plan_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return artifact


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    """Return static error code if value contains forbidden fragments or unsafe chars."""
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_call_plan_{field_name}"
    return None


def safe_validate_provider_call_plan_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Strictly validate a loaded provider call plan artifact for read paths.

    Returns (cleaned_data, None) if valid, or (None, error_code) if invalid.
    Never includes raw tampered values in error codes.
    """
    # 1. schema_version
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_call_plan_schema"

    # 2. artifact_type
    if data.get("artifact_type") != "provider_call_plan":
        return None, "provider_call_plan_malformed"

    # 3. contract_version
    if data.get("contract_version") != PROVIDER_CALL_PLAN_CONTRACT_VERSION:
        return None, "provider_call_plan_malformed"

    # 4. mode and execution_mode
    if data.get("mode") != "paper":
        return None, "provider_call_plan_malformed"
    if data.get("execution_mode") != "plan_only":
        return None, "provider_call_plan_malformed"

    # 5. provider state flags
    if data.get("provider_enabled") is not False:
        return None, "provider_call_plan_malformed"
    if data.get("network_enabled") is not False:
        return None, "provider_call_plan_malformed"
    if data.get("credentials_loaded") is not False:
        return None, "provider_call_plan_malformed"
    if data.get("provider_call_allowed") is not False:
        return None, "provider_call_plan_malformed"

    # 6. lineage IDs — reject if unsafe (forbidden fragments or bad chars)
    for field in (
        "provider_call_plan_id",
        "source_sandbox_request_id",
        "source_prompt_packet_id",
        "source_run_id",
    ):
        value = data.get(field, "")
        try:
            validate_contract_lineage_id(value, field)
        except ResearchSessionError:
            return None, "invalid_provider_call_plan_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    # 7. symbol
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_call_plan_lineage"

    # 8. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_call_plan_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    # 9. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_call_plan_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    # 10. hash consistency
    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_call_plan_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_call_plan_hash_mismatch"

    # 11. source sandbox exists and hash matches (if workspace provided)
    if workspace_path is not None:
        sandbox_request_id = data.get("source_sandbox_request_id", "")
        if sandbox_request_id:
            try:
                sandbox_path = find_sandbox_request_by_id(workspace_path, sandbox_request_id)
                if sandbox_path is None:
                    return None, "provider_call_plan_source_missing"
                sandbox_data = load_sandbox_request(sandbox_path, workspace_path)
                stored_sandbox_hash = data.get("sandbox_request_hash", "")
                actual_sandbox_hash = sandbox_data.get("content_hash", "")
                if stored_sandbox_hash != actual_sandbox_hash:
                    return None, "provider_call_plan_source_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_call_plan_source_missing"

    # 12. no forbidden fragments in text fields
    text_fields = [
        data.get("request_summary", ""),
        data.get("request_shape", ""),
        json.dumps(data.get("constraints", [])),
        json.dumps(data.get("forbidden_actions", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_call_plan_malformed"

    # 13. path containment
    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_call_plan_malformed"

    # Return a cleaned copy with only safe fields
    cleaned = {
        "schema_version": data.get("schema_version", ""),
        "artifact_type": data.get("artifact_type", ""),
        "contract_version": data.get("contract_version", ""),
        "provider_call_plan_id": data.get("provider_call_plan_id", ""),
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
        "execution_mode": data.get("execution_mode", ""),
        "request_shape": data.get("request_shape", ""),
        "request_summary": data.get("request_summary", ""),
        "input_hash": data.get("input_hash", ""),
        "sandbox_request_hash": data.get("sandbox_request_hash", ""),
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


def validate_provider_call_plan_artifact(
    data: dict[str, Any],
    workspace_path: Path | None = None,
) -> ProviderCallPlanValidationResult:
    """Validate a provider call plan artifact against the local contract."""
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
            at == "provider_call_plan",
            "artifact_type must be provider_call_plan."
            if at != "provider_call_plan"
            else "artifact_type is correct.",
        )
    )

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_CALL_PLAN_CONTRACT_VERSION,
            "contract_version must match current contract."
            if cv != PROVIDER_CALL_PLAN_CONTRACT_VERSION
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

    # 5. execution_mode = plan_only
    execution_mode = data.get("execution_mode")
    checks.append(
        _check_name(
            "execution_mode_plan_only",
            execution_mode == "plan_only",
            "execution_mode must be plan_only."
            if execution_mode != "plan_only"
            else "execution_mode is plan_only.",
        )
    )

    # 6. provider state flags
    checks.append(
        _check_name(
            "provider_enabled_false",
            data.get("provider_enabled") is False,
            "provider_enabled must be False."
            if data.get("provider_enabled") is not False
            else "provider_enabled is False.",
        )
    )
    checks.append(
        _check_name(
            "network_enabled_false",
            data.get("network_enabled") is False,
            "network_enabled must be False."
            if data.get("network_enabled") is not False
            else "network_enabled is False.",
        )
    )
    checks.append(
        _check_name(
            "credentials_loaded_false",
            data.get("credentials_loaded") is False,
            "credentials_loaded must be False."
            if data.get("credentials_loaded") is not False
            else "credentials_loaded is False.",
        )
    )
    checks.append(
        _check_name(
            "provider_call_allowed_false",
            data.get("provider_call_allowed") is False,
            "provider_call_allowed must be False."
            if data.get("provider_call_allowed") is not False
            else "provider_call_allowed is False.",
        )
    )

    # 7. lineage IDs
    lineage_ok = True
    for field in (
        "provider_call_plan_id",
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
    computed_hash = provider_call_plan_sha256(data) if stored_hash else ""
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

    # 11. source sandbox exists and hash matches (if workspace provided)
    if workspace_path is not None:
        sandbox_request_id = data.get("source_sandbox_request_id", "")
        sandbox_hash_ok = False
        sandbox_found = False
        if sandbox_request_id:
            try:
                sandbox_path = find_sandbox_request_by_id(workspace_path, sandbox_request_id)
                if sandbox_path is not None:
                    sandbox_found = True
                    sandbox_data = load_sandbox_request(sandbox_path, workspace_path)
                    stored_sandbox_hash = data.get("sandbox_request_hash", "")
                    actual_sandbox_hash = sandbox_data.get("content_hash", "")
                    sandbox_hash_ok = stored_sandbox_hash == actual_sandbox_hash
            except ResearchSessionError:
                sandbox_hash_ok = False
        checks.append(
            _check_name(
                "source_sandbox_exists",
                sandbox_found,
                "Source sandbox request not found."
                if not sandbox_found
                else "Source sandbox request exists.",
            )
        )
        checks.append(
            _check_name(
                "source_sandbox_hash_matches",
                sandbox_hash_ok,
                "Source sandbox request hash does not match."
                if not sandbox_hash_ok
                else "Source sandbox request hash matches.",
            )
        )

    # 12. no forbidden fragments
    text_fields = [
        data.get("request_summary", ""),
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
    recommendation = "provider_call_plan_valid" if valid else "manual_review_required"
    if not valid:
        warnings.append("Provider call plan validation failed one or more safety checks.")

    return ProviderCallPlanValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def replay_provider_call_plan(
    workspace_path: Path,
    provider_call_plan_id: str,
) -> dict[str, Any]:
    """Replay a provider call plan by rebuilding it and comparing hashes."""
    safe_plan_id = validate_run_id(provider_call_plan_id)

    plan_path = find_provider_call_plan_by_id(workspace_path, safe_plan_id)
    if plan_path is None:
        raise ResearchSessionError("provider_call_plan_not_found")

    plan = load_and_validate_provider_call_plan(plan_path, workspace_path)

    sandbox_request_id = plan.get("source_sandbox_request_id", "")
    sandbox_path = find_sandbox_request_by_id(workspace_path, sandbox_request_id)
    if sandbox_path is None:
        raise ResearchSessionError("sandbox_request_not_found")

    sandbox_request = load_sandbox_request(sandbox_path, workspace_path)

    provider_id = plan.get("provider_id", "")
    model_id = plan.get("model_id", "")

    rebuilt = build_provider_call_plan_dict(
        sandbox_request,
        provider_id,
        model_id,
        safe_plan_id,
    )

    expected_hash = plan.get("artifact_hash", "")
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
            plan.get("provider_id") == rebuilt.get("provider_id"),
            "Provider ID consistent.",
        ),
        _check_name(
            "model_id_consistent",
            plan.get("model_id") == rebuilt.get("model_id"),
            "Model ID consistent.",
        ),
        _check_name(
            "symbol_consistent",
            plan.get("symbol") == rebuilt.get("symbol"),
            "Symbol consistent.",
        ),
    ]

    return {
        "match": match,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "checks": checks,
    }


def find_provider_call_plan_by_id(
    workspace_path: Path,
    plan_id: str,
) -> Path | None:
    """Find exactly one provider call plan artifact by provider_call_plan_id.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    safe_plan_id = validate_run_id(plan_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        plans_dir = sym_dir / "provider_call_plans"
        if not plans_dir.exists():
            continue
        candidate = plans_dir / f"{safe_plan_id}.json"
        if candidate.exists() and candidate.is_file():
            if candidate.is_symlink() and not _is_inside_workspace(candidate, workspace_path):
                continue
            matches.append(candidate)

    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_call_plan_id")
    return matches[0]


def load_provider_call_plan(path: Path, workspace_path: Path) -> dict[str, Any]:
    """Load a provider call plan JSON safely."""
    if not path.exists() or not path.is_file():
        raise ResearchSessionError("provider_call_plan_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_call_plan_malformed")
    data["artifact_path"] = path.relative_to(workspace_path).as_posix()
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError("unsupported_provider_call_plan_schema")
    return data


def load_and_validate_provider_call_plan(
    path: Path, workspace_path: Path
) -> dict[str, Any]:
    """Load and strictly validate a provider call plan. Fail closed on tampering."""
    data = load_provider_call_plan(path, workspace_path)
    cleaned, error = safe_validate_provider_call_plan_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_provider_call_plan_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider call plan artifact metadata dicts, newest first.

    Each item is validated before inclusion. Invalid artifacts are returned as
    safe sentinels without raw tampered values.
    """
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return []

    search_dirs: list[Path] = []
    if symbol is not None:
        safe = sanitize_symbol(symbol)
        search_dirs.append(research_dir / safe / "provider_call_plans")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                plans_dir = sym_dir / "provider_call_plans"
                if plans_dir.exists():
                    search_dirs.append(plans_dir)

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
                        "provider_call_plan_id": "<invalid>",
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
                        "provider_call_plan_id": "<invalid>",
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
            cleaned, error = safe_validate_provider_call_plan_data(data, workspace_path)
            if error or cleaned is None:
                items.append(
                    {
                        "provider_call_plan_id": "<invalid>",
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
                    "provider_call_plan_id": cleaned["provider_call_plan_id"],
                    "source_sandbox_request_id": cleaned["source_sandbox_request_id"],
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
