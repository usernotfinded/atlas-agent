# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_execution_audit_packet.py
# PURPOSE: Link 10: seals the whole chain into one packet — the record a reviewer or an
#          auditor is handed. Hash-bound, so a doctored link no longer verifies.
# DEPS:    the upstream chain artifacts, research.sandbox_contracts
# ==============================================================================

"""Provider execution audit packet — local, auditable chain-consolidation artifact.

This module creates, validates, and replays provider execution audit packet artifacts.
It does NOT call any real provider, does NOT perform network requests,
does NOT read API keys, does NOT import provider SDKs, and does NOT touch brokers.

An audit packet consolidates the full research/provider-preflight chain:
research → prompt → sandbox → provider_call_plan → dry_run → state → audit_packet.

It answers:
- Which artifacts exist?
- Which hashes match?
- Which safety gates passed?
- Which gates still block real execution?
- What would be required in a future opt-in batch?
- Has any provider/API/network/credential/broker action happened? (Expected: no)
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

PROVIDER_EXECUTION_AUDIT_PACKET_CONTRACT_VERSION = "research_provider_execution_audit_packet_v1"

_PROVIDER_EXECUTION_AUDIT_PACKET_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_AUDIT_STATUS_CHARS = 120
_MAX_EXECUTION_STATUS_CHARS = 120

_VALID_AUDIT_STATUSES = {
    "audit_packet_ready",
    "manual_review_required",
    "audit_packet_invalid",
}

_VALID_EXECUTION_STATUSES = {
    "provider_execution_blocked",
    "provider_execution_not_implemented",
    "future_opt_in_required",
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
class ProviderExecutionAuditPacketValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets

    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_audit_packet_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
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


def validate_audit_status(value: str) -> str:
    """Validate audit_status. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_AUDIT_STATUSES:
        raise ResearchSessionError("invalid_provider_execution_audit_packet_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_audit_packet_status")
    return value


def validate_execution_status(value: str) -> str:
    """Validate execution_status. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_EXECUTION_STATUSES:
        raise ResearchSessionError("invalid_provider_execution_audit_packet_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_audit_packet_status")
    return value


def provider_execution_audit_packet_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_EXECUTION_AUDIT_PACKET_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _build_artifact_chain_summary(
    workspace_path: Path,
    source_state: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build safe, bounded summaries of the linked artifact chain."""
    chain: list[dict[str, Any]] = []

    def _add_summary(
        artifact_type: str,
        artifact_id_field: str,
        artifact_path_field: str,
        artifact_hash_field: str,
        source_data: dict[str, Any],
        required: bool = True,
    ) -> None:
        artifact_id = source_data.get(artifact_id_field, "")
        artifact_path = source_data.get(artifact_path_field, "")
        artifact_hash = source_data.get(artifact_hash_field, "")
        present = bool(artifact_id and artifact_path)
        warnings_count = len(source_data.get("warnings", []))
        chain.append({
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "artifact_path": artifact_path,
            "artifact_hash": artifact_hash,
            "validation_status": "present" if present else "missing",
            "required": required,
            "present": present,
            "warnings_count": warnings_count,
        })

    _add_summary(
        "research",
        "source_run_id",
        "source_run_id",
        "",
        source_state,
        required=True,
    )
    _add_summary(
        "prompt_packet",
        "source_prompt_packet_id",
        "source_prompt_packet_id",
        "",
        source_state,
        required=True,
    )
    _add_summary(
        "sandbox_request",
        "source_sandbox_request_id",
        "source_sandbox_request_id",
        "",
        source_state,
        required=True,
    )
    _add_summary(
        "provider_call_plan",
        "source_provider_call_plan_id",
        "source_provider_call_plan_id",
        "",
        source_state,
        required=True,
    )
    _add_summary(
        "provider_execution_dry_run",
        "source_provider_execution_dry_run_id",
        "source_provider_execution_dry_run_id",
        "",
        source_state,
        required=True,
    )
    _add_summary(
        "provider_execution_state",
        "provider_execution_state_id",
        "artifact_path",
        "artifact_hash",
        source_state,
        required=True,
    )

    return chain


def _build_safety_gate_summary(source_state: dict[str, Any]) -> dict[str, Any]:
    """Build a summary of safety gate status from the source state."""
    return {
        "provider_enabled": source_state.get("provider_enabled", False),
        "network_enabled": source_state.get("network_enabled", False),
        "credentials_loaded": source_state.get("credentials_loaded", False),
        "provider_call_allowed": source_state.get("provider_call_allowed", False),
        "actual_provider_call_made": source_state.get("actual_provider_call_made", False),
        "future_provider_execution_possible": source_state.get("future_provider_execution_possible", False),
        "requires_manual_unlock": source_state.get("requires_manual_unlock", False),
        "requires_credentials": source_state.get("requires_credentials", False),
        "requires_network": source_state.get("requires_network", False),
        "requires_provider_sdk": source_state.get("requires_provider_sdk", False),
        "state_gates_count": len(source_state.get("state_gates", [])),
        "forbidden_actions_count": len(source_state.get("forbidden_actions", [])),
    }


def _build_no_action_attestations() -> dict[str, bool]:
    """Return attestations that no actions were taken. All False by design."""
    return {
        "provider_called": False,
        "network_request_made": False,
        "api_key_read": False,
        "provider_sdk_imported": False,
        "trading_signal_generated": False,
        "approval_created": False,
        "pending_order_created": False,
        "broker_touched": False,
        "live_trading_authorized": False,
    }


def build_provider_execution_audit_packet_dict(
    source_state: dict[str, Any],
    provider_id: str,
    model_id: str,
    provider_execution_audit_packet_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    """Build a provider execution audit packet artifact dict in memory.

    No network. No API keys. No provider SDKs. No broker calls.
    """
    validate_contract_lineage_id(provider_execution_audit_packet_id, "provider_execution_audit_packet_id")

    source_provider_execution_state_id = source_state.get("provider_execution_state_id", "")
    validate_contract_lineage_id(source_provider_execution_state_id, "source_provider_execution_state_id")
    source_provider_execution_dry_run_id = source_state.get("source_provider_execution_dry_run_id", "")
    validate_contract_lineage_id(source_provider_execution_dry_run_id, "source_provider_execution_dry_run_id")
    source_provider_call_plan_id = source_state.get("source_provider_call_plan_id", "")
    validate_contract_lineage_id(source_provider_call_plan_id, "source_provider_call_plan_id")
    source_sandbox_request_id = source_state.get("source_sandbox_request_id", "")
    validate_contract_lineage_id(source_sandbox_request_id, "source_sandbox_request_id")
    source_prompt_packet_id = source_state.get("source_prompt_packet_id", "")
    validate_contract_lineage_id(source_prompt_packet_id, "source_prompt_packet_id")
    source_run_id = source_state.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    symbol = validate_contract_symbol(source_state.get("symbol", ""))
    safe_provider_id = validate_provider_id(provider_id)
    safe_model_id = validate_model_id(model_id)
    latest_state = source_state.get("state", "disabled")
    safe_audit_status = validate_audit_status("audit_packet_ready")
    safe_execution_status = validate_execution_status("provider_execution_blocked")

    created_at = datetime.now(UTC)

    artifact_chain = _build_artifact_chain_summary(workspace_path, source_state)
    safety_gate_summary = _build_safety_gate_summary(source_state)
    no_action_attestations = _build_no_action_attestations()

    # Hash checks
    hash_checks = [
        {
            "name": "source_state_hash_present",
            "passed": bool(source_state.get("artifact_hash", "")),
            "message": "Source state hash is present." if source_state.get("artifact_hash") else "Source state hash is missing.",
        },
        {
            "name": "source_dry_run_hash_present",
            "passed": bool(source_state.get("source_dry_run_hash", "")),
            "message": "Source dry-run hash is present." if source_state.get("source_dry_run_hash") else "Source dry-run hash is missing.",
        },
    ]

    # Blocking reasons from source state
    blocking_reasons = list(source_state.get("blocking_reasons", []))
    blocking_reasons.append("provider_execution_not_implemented")

    required_future_steps = [
        "Manual review of audit packet.",
        "Explicit opt-in for provider execution (future batch).",
        "Provider SDK import and integration (future batch).",
        "Credential loading and validation (future batch).",
        "Network enablement and firewall rules (future batch).",
        "Broker adapter configuration (future batch).",
        "Risk manager approval (future batch).",
    ]

    forbidden_actions = [
        "Execute live trade",
        "Submit order to broker",
        "Create pending order",
        "Authorize live trading",
        "Load or transmit API key",
        "Make network request to provider",
        "Actually call provider",
        "Import provider SDK",
        "Generate trading signal",
    ]

    source_state_hash = source_state.get("artifact_hash", "")
    input_hash = hashlib.sha256(str(source_state_hash).encode("utf-8")).hexdigest()

    redacted_count = sum(1 for frag in FORBIDDEN_FRAGMENTS if frag in str(source_state))
    redaction_summary = {
        "redacted_fragments_count": redacted_count,
        "forbidden_fragments_checked": len(FORBIDDEN_FRAGMENTS),
    }

    warnings = [
        "This is a local audit packet. No provider was called.",
        "Provider execution remains blocked and not implemented.",
        "All no-action attestations are False by design.",
        "Real provider execution requires explicit future opt-in.",
    ]

    artifact_path_rel = f".atlas/research/{symbol}/provider_execution_audit_packets/{provider_execution_audit_packet_id}.json"

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_execution_audit_packet",
        "contract_version": PROVIDER_EXECUTION_AUDIT_PACKET_CONTRACT_VERSION,
        "provider_execution_audit_packet_id": provider_execution_audit_packet_id,
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
        "latest_state": latest_state,
        "audit_status": safe_audit_status,
        "execution_status": safe_execution_status,
        "artifact_chain": artifact_chain,
        "hash_checks": hash_checks,
        "safety_gate_summary": safety_gate_summary,
        "blocking_reasons": blocking_reasons,
        "required_future_steps": required_future_steps,
        "forbidden_actions": forbidden_actions,
        "no_action_attestations": no_action_attestations,
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
        "input_hash": input_hash,
        "source_state_hash": source_state_hash,
        "redaction_summary": redaction_summary,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": {
            "source_state_schema_version": source_state.get("schema_version", ""),
            "source_state_contract_version": source_state.get("contract_version", ""),
        },
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_execution_audit_packet_sha256(artifact)
    return artifact


def create_provider_execution_audit_packet(
    workspace_path: Path,
    provider_execution_state_id: str,
) -> dict[str, Any]:
    """Create and persist a provider execution audit packet artifact.

    Loads the source state, builds the audit packet, and writes the artifact.
    """
    safe_state_id = validate_run_id(provider_execution_state_id)

    from atlas_agent.research.provider_execution_state import (
        find_provider_execution_state_by_id,
        load_and_validate_provider_execution_state,
    )

    state_path = find_provider_execution_state_by_id(workspace_path, safe_state_id)
    if state_path is None:
        raise ResearchSessionError("provider_execution_state_not_found")

    source_state = load_and_validate_provider_execution_state(state_path, workspace_path)

    provider_id = source_state.get("provider_id", "")
    model_id = source_state.get("model_id", "")

    audit_packet_id = generate_run_id()
    artifact = build_provider_execution_audit_packet_dict(
        source_state,
        provider_id,
        model_id,
        audit_packet_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    audit_dir = workspace_path / RESEARCH_DIR / symbol / "provider_execution_audit_packets"
    audit_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_execution_audit_packet_created",
        "provider_execution_audit_packet_id": audit_packet_id,
        "source_provider_execution_state_id": safe_state_id,
        "latest_state": artifact["latest_state"],
        "audit_status": artifact["audit_status"],
        "execution_status": artifact["execution_status"],
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    """Return static error code if value contains forbidden fragments or unsafe chars."""
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_execution_audit_packet_{field_name}"
    return None


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    """Return error code if any boolean safety flag is not False.

    Checks both top-level flags and nested no_action_attestations booleans.
    """
    for flag in _BOOLEAN_SAFETY_FLAGS:
        if data.get(flag) is not False:
            return "provider_execution_audit_packet_impossible_boolean"
    # Check nested no_action_attestations booleans
    attestations = data.get("no_action_attestations")
    if attestations is not None:
        if not isinstance(attestations, dict):
            return "provider_execution_audit_packet_impossible_boolean"
        for key, value in attestations.items():
            if value is not False:
                return "provider_execution_audit_packet_impossible_boolean"
    return None


def safe_validate_provider_execution_audit_packet_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """Strictly validate a loaded provider execution audit packet artifact for read paths.

    Returns (cleaned_data, None) if valid, or (None, error_code) if invalid.
    Never includes raw tampered values in error codes.

    When ``for_replay`` is True, the source state hash match is skipped so
    that replay can detect drift and report ``match=false``.
    """
    # 1. schema_version
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_execution_audit_packet_schema"

    # 2. artifact_type
    if data.get("artifact_type") != "provider_execution_audit_packet":
        return None, "provider_execution_audit_packet_malformed"

    # 3. contract_version
    if data.get("contract_version") != PROVIDER_EXECUTION_AUDIT_PACKET_CONTRACT_VERSION:
        return None, "provider_execution_audit_packet_malformed"

    # 4. audit_status / execution_status
    try:
        validate_audit_status(data.get("audit_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_audit_packet_status"
    try:
        validate_execution_status(data.get("execution_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_audit_packet_status"

    # 5. latest_state
    latest_state = data.get("latest_state", "")
    if not latest_state:
        return None, "invalid_provider_execution_audit_packet_status"
    if _has_forbidden_fragments(latest_state):
        return None, "invalid_provider_execution_audit_packet_status"

    # 6. boolean safety flags (all must be False)
    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    # 7. mode
    if data.get("mode") != "paper":
        return None, "provider_execution_audit_packet_malformed"

    # 8. lineage IDs — reject if unsafe
    for field in (
        "provider_execution_audit_packet_id",
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
            return None, "invalid_provider_execution_audit_packet_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    # 9. symbol
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_audit_packet_lineage"

    # 10. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_audit_packet_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    # 11. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_audit_packet_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    # 12. hash consistency
    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_execution_audit_packet_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_execution_audit_packet_hash_mismatch"

    # 13. source state exists and hash matches (if workspace provided)
    if workspace_path is not None and not for_replay:
        source_state_id = data.get("source_provider_execution_state_id", "")
        if source_state_id:
            try:
                from atlas_agent.research.provider_execution_state import (
                    find_provider_execution_state_by_id,
                    load_provider_execution_state,
                )

                state_path = find_provider_execution_state_by_id(workspace_path, source_state_id)
                if state_path is None:
                    return None, "provider_execution_audit_packet_source_state_missing"
                state_data = load_provider_execution_state(state_path, workspace_path)
                stored_state_hash = data.get("source_state_hash", "")
                actual_state_hash = state_data.get("artifact_hash", "")
                if stored_state_hash != actual_state_hash:
                    return None, "provider_execution_audit_packet_source_state_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_audit_packet_source_state_missing"

    # 14. no forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("artifact_chain", [])),
        json.dumps(data.get("hash_checks", [])),
        json.dumps(data.get("safety_gate_summary", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("required_future_steps", [])),
        json.dumps(data.get("forbidden_actions", [])),
        json.dumps(data.get("no_action_attestations", {})),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_execution_audit_packet_malformed"

    # 15. path containment
    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_execution_audit_packet_malformed"

    # Return a cleaned copy with only safe fields
    cleaned = {
        "schema_version": data.get("schema_version", ""),
        "artifact_type": data.get("artifact_type", ""),
        "contract_version": data.get("contract_version", ""),
        "provider_execution_audit_packet_id": data.get("provider_execution_audit_packet_id", ""),
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
        "latest_state": data.get("latest_state", ""),
        "audit_status": data.get("audit_status", ""),
        "execution_status": data.get("execution_status", ""),
        "artifact_chain": data.get("artifact_chain", []),
        "hash_checks": data.get("hash_checks", []),
        "safety_gate_summary": data.get("safety_gate_summary", {}),
        "blocking_reasons": data.get("blocking_reasons", []),
        "required_future_steps": data.get("required_future_steps", []),
        "forbidden_actions": data.get("forbidden_actions", []),
        "no_action_attestations": data.get("no_action_attestations", {}),
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
        "input_hash": data.get("input_hash", ""),
        "source_state_hash": data.get("source_state_hash", ""),
        "redaction_summary": data.get("redaction_summary", {}),
        "artifact_path": data.get("artifact_path", ""),
        "warnings": data.get("warnings", []),
        "metadata": data.get("metadata", {}),
        "artifact_hash": data.get("artifact_hash", ""),
        "created_at": data.get("created_at", ""),
    }
    return cleaned, None


def validate_provider_execution_audit_packet_artifact(
    data: dict[str, Any],
    workspace_path: Path | None = None,
) -> ProviderExecutionAuditPacketValidationResult:
    """Validate a provider execution audit packet artifact against the local contract."""
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
            at == "provider_execution_audit_packet",
            "artifact_type must be provider_execution_audit_packet."
            if at != "provider_execution_audit_packet"
            else "artifact_type is correct.",
        )
    )

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_EXECUTION_AUDIT_PACKET_CONTRACT_VERSION,
            "contract_version must match current contract."
            if cv != PROVIDER_EXECUTION_AUDIT_PACKET_CONTRACT_VERSION
            else "contract_version matches.",
        )
    )

    # 4. audit_status
    audit_status = data.get("audit_status", "")
    audit_ok = audit_status in _VALID_AUDIT_STATUSES
    checks.append(
        _check_name(
            "audit_status_valid",
            audit_ok,
            "audit_status is invalid." if not audit_ok else "audit_status is valid.",
        )
    )

    # 5. execution_status
    exec_status = data.get("execution_status", "")
    exec_ok = exec_status in _VALID_EXECUTION_STATUSES
    checks.append(
        _check_name(
            "execution_status_valid",
            exec_ok,
            "execution_status is invalid." if not exec_ok else "execution_status is valid.",
        )
    )

    # 6. latest_state
    latest_state = data.get("latest_state", "")
    state_ok = bool(latest_state) and not _has_forbidden_fragments(latest_state)
    checks.append(
        _check_name(
            "latest_state_safe",
            state_ok,
            "latest_state is unsafe or empty." if not state_ok else "latest_state is safe.",
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
        "provider_execution_audit_packet_id",
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
        computed = provider_execution_audit_packet_sha256(data)
        hash_ok = stored_hash == computed
    checks.append(
        _check_name(
            "artifact_hash_consistent",
            hash_ok,
            "artifact_hash does not match computed hash." if not hash_ok else "artifact_hash is consistent.",
        )
    )

    # 14. source state hash match (if workspace)
    if workspace_path is not None:
        source_state_id = data.get("source_provider_execution_state_id", "")
        source_hash_ok = False
        if source_state_id:
            try:
                from atlas_agent.research.provider_execution_state import (
                    find_provider_execution_state_by_id,
                    load_provider_execution_state,
                )

                state_path = find_provider_execution_state_by_id(workspace_path, source_state_id)
                if state_path is not None:
                    state_data = load_provider_execution_state(state_path, workspace_path)
                    stored_state_hash = data.get("source_state_hash", "")
                    actual_state_hash = state_data.get("artifact_hash", "")
                    source_hash_ok = stored_state_hash == actual_state_hash
            except Exception:
                pass
        checks.append(
            _check_name(
                "source_state_hash_match",
                source_hash_ok,
                "Source state hash does not match." if not source_hash_ok else "Source state hash matches.",
            )
        )

    # 15. forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("artifact_chain", [])),
        json.dumps(data.get("hash_checks", [])),
        json.dumps(data.get("safety_gate_summary", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("required_future_steps", [])),
        json.dumps(data.get("forbidden_actions", [])),
        json.dumps(data.get("no_action_attestations", {})),
    ]
    text_ok = not any(_has_forbidden_fragments(str(f)) for f in text_fields)
    checks.append(
        _check_name(
            "text_fields_forbidden_fragment_free",
            text_ok,
            "A text field contains a forbidden fragment." if not text_ok else "Text fields are clean.",
        )
    )

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    valid = failed == 0

    recommendation = (
        "provider_execution_audit_packet_valid"
        if valid
        else "manual_review_required"
    )

    if not valid:
        warnings.append("Audit packet validation failed. Manual review required.")

    return ProviderExecutionAuditPacketValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def replay_provider_execution_audit_packet(
    workspace_path: Path,
    provider_execution_audit_packet_id: str,
) -> dict[str, Any]:
    """Replay a provider execution audit packet from its source state and compare hashes.

    Read-only by default. Does not call providers, read API keys, or authorize trading.
    """
    safe_id = validate_run_id(provider_execution_audit_packet_id)

    audit_path = find_provider_execution_audit_packet_by_id(workspace_path, safe_id)
    if audit_path is None:
        raise ResearchSessionError("provider_execution_audit_packet_not_found")

    loaded_data = load_provider_execution_audit_packet(audit_path, workspace_path)
    cleaned, error = safe_validate_provider_execution_audit_packet_data(
        loaded_data, workspace_path, for_replay=True
    )
    if error:
        raise ResearchSessionError(error)

    source_state_id = loaded_data.get("source_provider_execution_state_id", "")
    from atlas_agent.research.provider_execution_state import (
        find_provider_execution_state_by_id,
        load_provider_execution_state,
    )

    state_path = find_provider_execution_state_by_id(workspace_path, source_state_id)
    if state_path is None:
        raise ResearchSessionError("provider_execution_state_not_found")
    source_state = load_provider_execution_state(state_path, workspace_path)

    provider_id = source_state.get("provider_id", "")
    model_id = source_state.get("model_id", "")

    rebuilt = build_provider_execution_audit_packet_dict(
        source_state,
        provider_id,
        model_id,
        safe_id,
        workspace_path,
    )

    expected_hash = loaded_data.get("artifact_hash", "")
    actual_hash = provider_execution_audit_packet_sha256(rebuilt)

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
        warnings.append("Audit packet hash mismatch. Source state or linked chain may have changed.")

    return {
        "match": expected_hash == actual_hash,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "checks": checks,
        "warnings": warnings,
    }


def find_provider_execution_audit_packet_by_id(
    workspace_path: Path,
    provider_execution_audit_packet_id: str,
) -> Path | None:
    """Find a provider execution audit packet artifact by its ID.

    Returns the path if found, None if not found, raises if ambiguous.
    """
    safe_id = validate_run_id(provider_execution_audit_packet_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        audit_dir = sym_dir / "provider_execution_audit_packets"
        if not audit_dir.exists():
            continue
        for path in audit_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("provider_execution_audit_packet_id") == safe_id:
                matches.append(path)

    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_execution_audit_packet_id")
    return matches[0] if matches else None


def load_provider_execution_audit_packet(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load a provider execution audit packet artifact from disk.

    Performs basic safety checks but does not fully validate.
    """
    if not path.exists():
        raise ResearchSessionError("provider_execution_audit_packet_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_execution_audit_packet_malformed")

    data["artifact_path"] = path.relative_to(workspace_path).as_posix()

    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError(
            f"Unsupported schema version: {sv} (expected {RESEARCH_ARTIFACT_SCHEMA_VERSION})"
        )

    return data


def load_and_validate_provider_execution_audit_packet(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load and strictly validate a provider execution audit packet artifact."""
    data = load_provider_execution_audit_packet(path, workspace_path)
    cleaned, error = safe_validate_provider_execution_audit_packet_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_provider_execution_audit_packet_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider execution audit packet artifact metadata dicts, newest first.

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
        audit_dir = sym_dir / "provider_execution_audit_packets"
        if not audit_dir.exists():
            continue
        for path in audit_dir.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                invalid_items.append({
                    "provider_execution_audit_packet_id": "<invalid>",
                    "source_provider_execution_state_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": sym_dir.name,
                    "latest_state": "<invalid>",
                    "audit_status": "<invalid>",
                    "execution_status": "<invalid>",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "provider_id": "<invalid>",
                    "model_id": "<invalid>",
                    "warnings_count": 0,
                    "_invalid": True,
                    "created_at": "",
                })
                continue

            sv = raw.get("schema_version")
            if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
                invalid_items.append({
                    "provider_execution_audit_packet_id": "<invalid>",
                    "source_provider_execution_state_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "latest_state": "unknown",
                    "audit_status": "invalid",
                    "execution_status": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "unsupported_provider_execution_audit_packet_schema",
                    "created_at": "",
                })
                continue

            cleaned, error = safe_validate_provider_execution_audit_packet_data(raw, workspace_path)
            if error:
                invalid_items.append({
                    "provider_execution_audit_packet_id": "<invalid>",
                    "source_provider_execution_state_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "latest_state": "unknown",
                    "audit_status": "invalid",
                    "execution_status": "invalid",
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
                "provider_execution_audit_packet_id": cleaned.get("provider_execution_audit_packet_id", ""),
                "source_provider_execution_state_id": cleaned.get("source_provider_execution_state_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", ""),
                "latest_state": cleaned.get("latest_state", ""),
                "audit_status": cleaned.get("audit_status", ""),
                "execution_status": cleaned.get("execution_status", ""),
                "created_at": cleaned.get("created_at", ""),
                "artifact_path": cleaned.get("artifact_path", ""),
                "provider_id": cleaned.get("provider_id", ""),
                "model_id": cleaned.get("model_id", ""),
                "warnings_count": len(cleaned.get("warnings", [])),
            })

    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    invalid_items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items + invalid_items
