# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_execution_state.py
# PURPOSE: Link 6: the opt-in state machine. Tracks whether provider execution is
#          unlocked, and refuses any transition that is not explicitly authorised.
# DEPS:    research.sandbox_contracts
# ==============================================================================

"""Provider execution opt-in state machine — local, auditable state artifacts.

This module defines and validates local provider execution opt-in state artifacts.
It does NOT call any real provider, does NOT perform network requests,
does NOT read API keys, and does NOT import provider SDKs.

Even the most permissive state (provider_call_allowed_but_not_implemented) still
does not allow real provider calls in this batch.
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

PROVIDER_EXECUTION_STATE_CONTRACT_VERSION = "research_provider_execution_state_v1"

_PROVIDER_EXECUTION_STATE_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_TRANSITION_REASON_CHARS = 2000

VALID_STATES = {
    "disabled",
    "dry_run_only",
    "manual_unlock_required",
    "provider_call_allowed_but_not_implemented",
}

# States that require manual unlock
_REQUIRES_MANUAL_UNLOCK = {"manual_unlock_required", "provider_call_allowed_but_not_implemented"}

# States that conceptually need credentials/network/SDK in a future implementation
_REQUIRES_CREDENTIALS = {"provider_call_allowed_but_not_implemented"}
_REQUIRES_NETWORK = {"provider_call_allowed_but_not_implemented"}
_REQUIRES_PROVIDER_SDK = {"provider_call_allowed_but_not_implemented"}


@dataclass(frozen=True)
class ProviderExecutionStateValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets

    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_state_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
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


def validate_state_name(value: str) -> str:
    """Validate state name. Must be one of known states. Fail closed."""
    if not value or value not in VALID_STATES:
        raise ResearchSessionError("invalid_provider_execution_state_name")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_state_name")
    return value


def provider_execution_state_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_EXECUTION_STATE_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def evaluate_provider_execution_state_transition(
    current_state: str,
    requested_state: str,
    source_dry_run: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Evaluate whether a state transition is allowed.

    Returns (transition_allowed, blocking_reasons).
    """
    blocking_reasons: list[str] = []

    # Validate state names
    try:
        validate_state_name(requested_state)
    except ResearchSessionError:
        blocking_reasons.append("invalid_requested_state")
        return False, blocking_reasons

    try:
        validate_state_name(current_state)
    except ResearchSessionError:
        blocking_reasons.append("invalid_current_state")
        return False, blocking_reasons

    # Validate source dry-run
    if source_dry_run is None:
        blocking_reasons.append("source_dry_run_missing")
        return False, blocking_reasons

    # Check dry-run booleans (must all be False)
    for flag in (
        "provider_enabled",
        "network_enabled",
        "credentials_loaded",
        "provider_call_allowed",
        "would_call_provider",
        "actual_provider_call_made",
    ):
        if source_dry_run.get(flag) is not False:
            blocking_reasons.append(f"source_dry_run_unsafe_{flag}")

    # Check dry-run execution mode
    if source_dry_run.get("execution_mode") != "dry_run_only":
        blocking_reasons.append("source_dry_run_unsafe_execution_mode")

    # Check dry-run mode
    if source_dry_run.get("mode") != "paper":
        blocking_reasons.append("source_dry_run_unsafe_mode")

    if blocking_reasons:
        return False, blocking_reasons

    # Allowed transitions
    allowed_transitions = {
        "disabled": {"dry_run_only", "disabled"},
        "dry_run_only": {"manual_unlock_required", "disabled"},
        "manual_unlock_required": {"provider_call_allowed_but_not_implemented", "disabled"},
        "provider_call_allowed_but_not_implemented": {"disabled"},
    }

    if requested_state not in allowed_transitions.get(current_state, set()):
        blocking_reasons.append("transition_not_allowed")
        return False, blocking_reasons

    # Even provider_call_allowed_but_not_implemented blocks actual execution
    if requested_state == "provider_call_allowed_but_not_implemented":
        blocking_reasons.append("provider_execution_not_implemented")
        # Transition is still allowed, but with a blocking reason for awareness

    return True, blocking_reasons


def _determine_current_state(workspace_path: Path, source_dry_run_id: str) -> str:
    """Determine the current state for a dry-run by finding the latest state artifact."""
    safe_id = validate_run_id(source_dry_run_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return "disabled"

    latest_state: str | None = None
    latest_created: str = ""

    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        states_dir = sym_dir / "provider_execution_states"
        if not states_dir.exists():
            continue
        for path in states_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("source_provider_execution_dry_run_id") != safe_id:
                continue
            created = data.get("created_at", "")
            if created >= latest_created:
                latest_created = created
                latest_state = data.get("state", "disabled")

    return latest_state or "disabled"


def build_provider_execution_state_dict(
    source_dry_run: dict[str, Any],
    provider_id: str,
    model_id: str,
    previous_state: str,
    requested_state: str,
    transition_allowed: bool,
    transition_reason: str,
    provider_execution_state_id: str,
) -> dict[str, Any]:
    """Build a provider execution state artifact dict in memory.

    No network. No API keys. No provider SDKs.
    """
    validate_contract_lineage_id(provider_execution_state_id, "provider_execution_state_id")
    source_provider_execution_dry_run_id = source_dry_run.get("provider_execution_dry_run_id", "")
    validate_contract_lineage_id(source_provider_execution_dry_run_id, "source_provider_execution_dry_run_id")
    source_provider_call_plan_id = source_dry_run.get("source_provider_call_plan_id", "")
    validate_contract_lineage_id(source_provider_call_plan_id, "source_provider_call_plan_id")
    source_sandbox_request_id = source_dry_run.get("source_sandbox_request_id", "")
    validate_contract_lineage_id(source_sandbox_request_id, "source_sandbox_request_id")
    source_prompt_packet_id = source_dry_run.get("source_prompt_packet_id", "")
    validate_contract_lineage_id(source_prompt_packet_id, "source_prompt_packet_id")
    source_run_id = source_dry_run.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    symbol = validate_contract_symbol(source_dry_run.get("symbol", ""))
    safe_provider_id = validate_provider_id(provider_id)
    safe_model_id = validate_model_id(model_id)
    safe_state = validate_state_name(requested_state)
    safe_previous = validate_state_name(previous_state)

    created_at = datetime.now(UTC)

    # Build deterministic transition reason
    raw_reason = (
        f"State transition from {safe_previous} to {safe_state}. "
        f"Transition allowed: {transition_allowed}. "
        f"Source dry-run: {source_provider_execution_dry_run_id}. "
        f"No provider call made. No API key loaded. No network request."
    )
    safe_transition_reason = sanitize_state_text(raw_reason, _MAX_TRANSITION_REASON_CHARS)

    # Blocking reasons based on state
    blocking_reasons: list[str] = []
    if safe_state == "provider_call_allowed_but_not_implemented":
        blocking_reasons.append("provider_execution_not_implemented")

    # State gates
    state_gates = [
        "Provider is disabled.",
        "No network request is made.",
        "No API key is read or loaded.",
        "No broker is contacted.",
        "No order is generated or submitted.",
        "No live trading is authorized.",
        f"Execution state: {safe_state}.",
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
    source_dry_run_hash = source_dry_run.get("artifact_hash", "")
    input_hash = hashlib.sha256(str(source_dry_run_hash).encode("utf-8")).hexdigest()

    # Redaction summary
    redacted_count = sum(1 for frag in FORBIDDEN_FRAGMENTS if frag in str(source_dry_run))
    redaction_summary = {
        "redacted_fragments_count": redacted_count,
        "forbidden_fragments_checked": len(FORBIDDEN_FRAGMENTS),
    }

    warnings = [
        "This is a state-machine skeleton artifact. No provider was called.",
        "Provider is disabled. Enablement requires explicit configuration and approval.",
        "actual_provider_call_made is False by design.",
        "future_provider_execution_possible is False by design.",
    ]

    artifact_path_rel = f".atlas/research/{symbol}/provider_execution_states/{provider_execution_state_id}.json"

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_execution_state",
        "contract_version": PROVIDER_EXECUTION_STATE_CONTRACT_VERSION,
        "provider_execution_state_id": provider_execution_state_id,
        "source_provider_execution_dry_run_id": source_provider_execution_dry_run_id,
        "source_provider_call_plan_id": source_provider_call_plan_id,
        "source_sandbox_request_id": source_sandbox_request_id,
        "source_prompt_packet_id": source_prompt_packet_id,
        "source_run_id": source_run_id,
        "symbol": symbol,
        "mode": "paper",
        "state": safe_state,
        "previous_state": safe_previous,
        "requested_state": safe_state,
        "transition_allowed": transition_allowed,
        "transition_reason": safe_transition_reason,
        "provider_id": safe_provider_id,
        "model_id": safe_model_id,
        "provider_enabled": False,
        "network_enabled": False,
        "credentials_loaded": False,
        "provider_call_allowed": False,
        "actual_provider_call_made": False,
        "future_provider_execution_possible": False,
        "requires_manual_unlock": safe_state in _REQUIRES_MANUAL_UNLOCK,
        "requires_credentials": safe_state in _REQUIRES_CREDENTIALS,
        "requires_network": safe_state in _REQUIRES_NETWORK,
        "requires_provider_sdk": safe_state in _REQUIRES_PROVIDER_SDK,
        "blocking_reasons": blocking_reasons,
        "state_gates": state_gates,
        "forbidden_actions": forbidden_actions,
        "input_hash": input_hash,
        "source_dry_run_hash": source_dry_run_hash,
        "redaction_summary": redaction_summary,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": {
            "max_transition_reason_chars": _MAX_TRANSITION_REASON_CHARS,
            "source_dry_run_schema_version": source_dry_run.get("schema_version", ""),
        },
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_execution_state_sha256(artifact)
    return artifact


def create_provider_execution_state(
    workspace_path: Path,
    provider_execution_dry_run_id: str,
    requested_state: str,
) -> dict[str, Any]:
    """Create and persist a provider execution state transition artifact.

    Loads the source dry-run, evaluates the transition, and writes the state artifact.
    """
    safe_dry_run_id = validate_run_id(provider_execution_dry_run_id)
    safe_requested_state = validate_state_name(requested_state)

    from atlas_agent.research.provider_execution_dry_run import (
        find_provider_execution_dry_run_by_id,
        load_and_validate_provider_execution_dry_run,
    )

    dry_run_path = find_provider_execution_dry_run_by_id(workspace_path, safe_dry_run_id)
    if dry_run_path is None:
        raise ResearchSessionError("provider_execution_dry_run_not_found")

    source_dry_run = load_and_validate_provider_execution_dry_run(dry_run_path, workspace_path)

    current_state = _determine_current_state(workspace_path, safe_dry_run_id)

    transition_allowed, blocking_reasons = evaluate_provider_execution_state_transition(
        current_state,
        safe_requested_state,
        source_dry_run,
    )

    if not transition_allowed:
        return {
            "ok": False,
            "status": "provider_execution_state_transition_blocked",
            "transition_allowed": False,
            "blocking_reasons": blocking_reasons,
            "warnings": ["Transition blocked. No artifact written."],
        }

    provider_id = source_dry_run.get("provider_id", "")
    model_id = source_dry_run.get("model_id", "")

    state_id = generate_run_id()
    artifact = build_provider_execution_state_dict(
        source_dry_run,
        provider_id,
        model_id,
        current_state,
        safe_requested_state,
        transition_allowed,
        safe_requested_state,
        state_id,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    states_dir = workspace_path / RESEARCH_DIR / symbol / "provider_execution_states"
    states_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_execution_state_created",
        "provider_execution_state_id": state_id,
        "source_provider_execution_dry_run_id": safe_dry_run_id,
        "previous_state": current_state,
        "state": safe_requested_state,
        "requested_state": safe_requested_state,
        "transition_allowed": True,
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    """Return static error code if value contains forbidden fragments or unsafe chars."""
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_execution_state_{field_name}"
    return None


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    """Return error code if any boolean safety flag is not False."""
    flags = [
        "provider_enabled",
        "network_enabled",
        "credentials_loaded",
        "provider_call_allowed",
        "actual_provider_call_made",
        "future_provider_execution_possible",
    ]
    for flag in flags:
        if data.get(flag) is not False:
            return "provider_execution_state_impossible_boolean"
    return None


def safe_validate_provider_execution_state_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """Strictly validate a loaded provider execution state artifact for read paths.

    Returns (cleaned_data, None) if valid, or (None, error_code) if invalid.
    Never includes raw tampered values in error codes.

    When ``for_replay`` is True, the source dry-run hash match is skipped so
    that replay can detect drift and report ``match=false``.
    """
    # 1. schema_version
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_execution_state_schema"

    # 2. artifact_type
    if data.get("artifact_type") != "provider_execution_state":
        return None, "provider_execution_state_malformed"

    # 3. contract_version
    if data.get("contract_version") != PROVIDER_EXECUTION_STATE_CONTRACT_VERSION:
        return None, "provider_execution_state_malformed"

    # 4. state names
    try:
        validate_state_name(data.get("state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_state_name"
    try:
        validate_state_name(data.get("previous_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_state_name"
    try:
        validate_state_name(data.get("requested_state", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_state_name"

    # 5. boolean safety flags (all must be False)
    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    # 6. mode
    if data.get("mode") != "paper":
        return None, "provider_execution_state_malformed"

    # 7. lineage IDs — reject if unsafe
    for field in (
        "provider_execution_state_id",
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
            return None, "invalid_provider_execution_state_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    # 8. symbol
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_state_lineage"

    # 9. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_state_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    # 10. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_state_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    # 11. hash consistency
    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_execution_state_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_execution_state_hash_mismatch"

    # 12. source dry-run exists and hash matches (if workspace provided)
    # Skip hash match when validating for replay so drift is reported as match=false.
    if workspace_path is not None and not for_replay:
        source_dry_run_id = data.get("source_provider_execution_dry_run_id", "")
        if source_dry_run_id:
            try:
                from atlas_agent.research.provider_execution_dry_run import (
                    find_provider_execution_dry_run_by_id,
                    load_provider_execution_dry_run,
                )

                dry_run_path = find_provider_execution_dry_run_by_id(workspace_path, source_dry_run_id)
                if dry_run_path is None:
                    return None, "provider_execution_state_source_dry_run_missing"
                dry_run_data = load_provider_execution_dry_run(dry_run_path, workspace_path)
                stored_dry_run_hash = data.get("source_dry_run_hash", "")
                actual_dry_run_hash = dry_run_data.get("artifact_hash", "")
                if stored_dry_run_hash != actual_dry_run_hash:
                    return None, "provider_execution_state_source_dry_run_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_state_source_dry_run_missing"

    # 13. no forbidden fragments in text fields
    text_fields = [
        data.get("transition_reason", ""),
        json.dumps(data.get("state_gates", [])),
        json.dumps(data.get("forbidden_actions", [])),
        json.dumps(data.get("blocking_reasons", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_execution_state_malformed"

    # 14. path containment
    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_execution_state_malformed"

    # Return a cleaned copy with only safe fields
    cleaned = {
        "schema_version": data.get("schema_version", ""),
        "artifact_type": data.get("artifact_type", ""),
        "contract_version": data.get("contract_version", ""),
        "provider_execution_state_id": data.get("provider_execution_state_id", ""),
        "source_provider_execution_dry_run_id": data.get("source_provider_execution_dry_run_id", ""),
        "source_provider_call_plan_id": data.get("source_provider_call_plan_id", ""),
        "source_sandbox_request_id": data.get("source_sandbox_request_id", ""),
        "source_prompt_packet_id": data.get("source_prompt_packet_id", ""),
        "source_run_id": data.get("source_run_id", ""),
        "symbol": data.get("symbol", ""),
        "mode": data.get("mode", ""),
        "state": data.get("state", ""),
        "previous_state": data.get("previous_state", ""),
        "requested_state": data.get("requested_state", ""),
        "transition_allowed": data.get("transition_allowed", False),
        "transition_reason": data.get("transition_reason", ""),
        "provider_id": data.get("provider_id", ""),
        "model_id": data.get("model_id", ""),
        "provider_enabled": data.get("provider_enabled", False),
        "network_enabled": data.get("network_enabled", False),
        "credentials_loaded": data.get("credentials_loaded", False),
        "provider_call_allowed": data.get("provider_call_allowed", False),
        "actual_provider_call_made": data.get("actual_provider_call_made", False),
        "future_provider_execution_possible": data.get("future_provider_execution_possible", False),
        "requires_manual_unlock": data.get("requires_manual_unlock", False),
        "requires_credentials": data.get("requires_credentials", False),
        "requires_network": data.get("requires_network", False),
        "requires_provider_sdk": data.get("requires_provider_sdk", False),
        "blocking_reasons": data.get("blocking_reasons", []),
        "state_gates": data.get("state_gates", []),
        "forbidden_actions": data.get("forbidden_actions", []),
        "input_hash": data.get("input_hash", ""),
        "source_dry_run_hash": data.get("source_dry_run_hash", ""),
        "redaction_summary": data.get("redaction_summary", {}),
        "artifact_path": data.get("artifact_path", ""),
        "warnings": data.get("warnings", []),
        "metadata": data.get("metadata", {}),
        "artifact_hash": data.get("artifact_hash", ""),
        "created_at": data.get("created_at", ""),
    }
    return cleaned, None


def validate_provider_execution_state_artifact(
    data: dict[str, Any],
    workspace_path: Path | None = None,
) -> ProviderExecutionStateValidationResult:
    """Validate a provider execution state artifact against the local contract."""
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
            at == "provider_execution_state",
            "artifact_type must be provider_execution_state."
            if at != "provider_execution_state"
            else "artifact_type is correct.",
        )
    )

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_EXECUTION_STATE_CONTRACT_VERSION,
            "contract_version must match current contract."
            if cv != PROVIDER_EXECUTION_STATE_CONTRACT_VERSION
            else "contract_version matches.",
        )
    )

    # 4. state names
    state = data.get("state", "")
    state_ok = state in VALID_STATES
    checks.append(
        _check_name(
            "state_valid",
            state_ok,
            "State name is invalid." if not state_ok else "State name is valid.",
        )
    )

    prev_state = data.get("previous_state", "")
    prev_ok = prev_state in VALID_STATES
    checks.append(
        _check_name(
            "previous_state_valid",
            prev_ok,
            "Previous state name is invalid." if not prev_ok else "Previous state name is valid.",
        )
    )

    req_state = data.get("requested_state", "")
    req_ok = req_state in VALID_STATES
    checks.append(
        _check_name(
            "requested_state_valid",
            req_ok,
            "Requested state name is invalid." if not req_ok else "Requested state name is valid.",
        )
    )

    # 5. mode = paper
    mode = data.get("mode")
    checks.append(
        _check_name(
            "mode_is_paper",
            mode == "paper",
            "mode must be paper." if mode != "paper" else "mode is paper.",
        )
    )

    # 6. boolean safety flags
    for flag_name in (
        "provider_enabled",
        "network_enabled",
        "credentials_loaded",
        "provider_call_allowed",
        "actual_provider_call_made",
        "future_provider_execution_possible",
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

    # 7. lineage IDs
    lineage_ok = True
    for field in (
        "provider_execution_state_id",
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
    computed_hash = provider_execution_state_sha256(data) if stored_hash else ""
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

    # 11. source dry-run exists and hash matches (if workspace provided)
    if workspace_path is not None:
        source_dry_run_id = data.get("source_provider_execution_dry_run_id", "")
        dry_run_hash_ok = False
        dry_run_found = False
        if source_dry_run_id:
            try:
                from atlas_agent.research.provider_execution_dry_run import (
                    find_provider_execution_dry_run_by_id,
                    load_provider_execution_dry_run,
                )

                dry_run_path = find_provider_execution_dry_run_by_id(workspace_path, source_dry_run_id)
                if dry_run_path is not None:
                    dry_run_found = True
                    dry_run_data = load_provider_execution_dry_run(dry_run_path, workspace_path)
                    stored_dry_run_hash = data.get("source_dry_run_hash", "")
                    actual_dry_run_hash = dry_run_data.get("artifact_hash", "")
                    dry_run_hash_ok = stored_dry_run_hash == actual_dry_run_hash
            except ResearchSessionError:
                dry_run_hash_ok = False
        checks.append(
            _check_name(
                "source_dry_run_exists",
                dry_run_found,
                "Source provider execution dry-run not found."
                if not dry_run_found
                else "Source provider execution dry-run exists.",
            )
        )
        checks.append(
            _check_name(
                "source_dry_run_hash_matches",
                dry_run_hash_ok,
                "Source provider execution dry-run hash does not match."
                if not dry_run_hash_ok
                else "Source provider execution dry-run hash matches.",
            )
        )

    # 12. no forbidden fragments
    text_fields = [
        data.get("transition_reason", ""),
        json.dumps(data.get("state_gates", [])),
        json.dumps(data.get("forbidden_actions", [])),
        json.dumps(data.get("blocking_reasons", [])),
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
    recommendation = "provider_execution_state_valid" if valid else "manual_review_required"
    if not valid:
        warnings.append("Provider execution state validation failed one or more safety checks.")

    return ProviderExecutionStateValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def replay_provider_execution_state(
    workspace_path: Path,
    provider_execution_state_id: str,
) -> dict[str, Any]:
    """Replay a provider execution state by rebuilding it and comparing hashes.

    A source dry-run hash mismatch is reported as ``match=false`` in the replay
    envelope, not as a generic error.
    """
    safe_state_id = validate_run_id(provider_execution_state_id)

    state_path = find_provider_execution_state_by_id(workspace_path, safe_state_id)
    if state_path is None:
        raise ResearchSessionError("provider_execution_state_not_found")

    state = load_provider_execution_state(state_path, workspace_path)
    cleaned, error = safe_validate_provider_execution_state_data(
        state, workspace_path, for_replay=True
    )
    if error:
        raise ResearchSessionError(error)
    state = cleaned

    source_dry_run_id = state.get("source_provider_execution_dry_run_id", "")
    from atlas_agent.research.provider_execution_dry_run import (
        find_provider_execution_dry_run_by_id,
        load_and_validate_provider_execution_dry_run,
    )

    dry_run_path = find_provider_execution_dry_run_by_id(workspace_path, source_dry_run_id)
    if dry_run_path is None:
        raise ResearchSessionError("provider_execution_dry_run_not_found")

    source_dry_run = load_and_validate_provider_execution_dry_run(dry_run_path, workspace_path)

    provider_id = state.get("provider_id", "")
    model_id = state.get("model_id", "")
    previous_state = state.get("previous_state", "disabled")
    requested_state = state.get("requested_state", "disabled")
    transition_allowed = state.get("transition_allowed", False)

    rebuilt = build_provider_execution_state_dict(
        source_dry_run,
        provider_id,
        model_id,
        previous_state,
        requested_state,
        transition_allowed,
        requested_state,
        safe_state_id,
    )

    expected_hash = state.get("artifact_hash", "")
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
            state.get("provider_id") == rebuilt.get("provider_id"),
            "Provider ID consistent.",
        ),
        _check_name(
            "model_id_consistent",
            state.get("model_id") == rebuilt.get("model_id"),
            "Model ID consistent.",
        ),
        _check_name(
            "symbol_consistent",
            state.get("symbol") == rebuilt.get("symbol"),
            "Symbol consistent.",
        ),
        _check_name(
            "state_consistent",
            state.get("state") == rebuilt.get("state"),
            "State consistent.",
        ),
    ]

    warnings = [
        "This is a state-machine replay. No provider was called.",
        "Provider is disabled. Enablement requires explicit configuration and approval.",
    ]
    if not match:
        warnings.append(
            "Replay hash mismatch: source provider execution dry-run may have changed since state creation."
        )

    return {
        "match": match,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "checks": checks,
        "warnings": warnings,
    }


def find_provider_execution_state_by_id(
    workspace_path: Path,
    state_id: str,
) -> Path | None:
    """Find exactly one provider execution state artifact by ID.

    Returns the path, or None if not found.
    Raises ResearchSessionError if ambiguous.
    """
    safe_state_id = validate_run_id(state_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        states_dir = sym_dir / "provider_execution_states"
        if not states_dir.exists():
            continue
        candidate = states_dir / f"{safe_state_id}.json"
        if candidate.exists() and candidate.is_file():
            if candidate.is_symlink() and not _is_inside_workspace(candidate, workspace_path):
                continue
            matches.append(candidate)

    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_execution_state_id")
    return matches[0]


def load_provider_execution_state(path: Path, workspace_path: Path) -> dict[str, Any]:
    """Load a provider execution state JSON safely."""
    if not path.exists() or not path.is_file():
        raise ResearchSessionError("provider_execution_state_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_execution_state_malformed")
    data["artifact_path"] = path.relative_to(workspace_path).as_posix()
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError("unsupported_provider_execution_state_schema")
    return data


def load_and_validate_provider_execution_state(
    path: Path, workspace_path: Path
) -> dict[str, Any]:
    """Load and strictly validate a provider execution state. Fail closed on tampering."""
    data = load_provider_execution_state(path, workspace_path)
    cleaned, error = safe_validate_provider_execution_state_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_provider_execution_state_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider execution state artifact metadata dicts, newest first.

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
        search_dirs.append(research_dir / safe / "provider_execution_states")
    else:
        for sym_dir in research_dir.iterdir():
            if sym_dir.is_dir():
                states_dir = sym_dir / "provider_execution_states"
                if states_dir.exists():
                    search_dirs.append(states_dir)

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
                        "provider_execution_state_id": "<invalid>",
                        "symbol": "<invalid>",
                        "created_at": "",
                        "artifact_path": rel_path,
                        "provider_id": "unknown",
                        "model_id": "unknown",
                        "state": "<invalid>",
                        "warnings_count": 1,
                        "_invalid": True,
                    }
                )
                continue
            sv = data.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                items.append(
                    {
                        "provider_execution_state_id": "<invalid>",
                        "symbol": "<invalid>",
                        "created_at": "",
                        "artifact_path": rel_path,
                        "provider_id": "unknown",
                        "model_id": "unknown",
                        "state": "<invalid>",
                        "warnings_count": 1,
                        "_invalid": True,
                    }
                )
                continue
            cleaned, error = safe_validate_provider_execution_state_data(data, workspace_path)
            if error or cleaned is None:
                items.append(
                    {
                        "provider_execution_state_id": "<invalid>",
                        "symbol": "<invalid>",
                        "created_at": data.get("created_at", ""),
                        "artifact_path": rel_path,
                        "provider_id": "unknown",
                        "model_id": "unknown",
                        "state": "<invalid>",
                        "warnings_count": 1,
                        "_invalid": True,
                    }
                )
                continue
            items.append(
                {
                    "provider_execution_state_id": cleaned["provider_execution_state_id"],
                    "source_provider_execution_dry_run_id": cleaned["source_provider_execution_dry_run_id"],
                    "source_run_id": cleaned["source_run_id"],
                    "symbol": cleaned["symbol"],
                    "state": cleaned["state"],
                    "previous_state": cleaned["previous_state"],
                    "transition_allowed": cleaned["transition_allowed"],
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
