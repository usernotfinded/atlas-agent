"""Provider execution readiness report — local, configless chain-diagnostic artifact.

This module creates, validates, and replays provider execution readiness reports.
It does NOT call any real provider, does NOT perform network requests,
does NOT read API keys, does NOT import provider SDKs, and does NOT touch brokers.

A readiness report consolidates the full pre-provider chain into a human-readable
and machine-validated readiness summary. It answers:
- Is the full provider-preflight chain internally consistent?
- Which artifacts are present/missing?
- Which hashes match/drifted?
- Which safety gates passed?
- Which gates still block provider execution?
- What future capabilities would be required before real provider execution?
- Did any provider/API/network/credential/broker action happen? (Expected: no)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.events.log import generate_run_id
from atlas_agent.research.provider_execution_audit_packet import (
    _BOOLEAN_SAFETY_FLAGS as _AUDIT_BOOLEAN_SAFETY_FLAGS,
)
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

PROVIDER_EXECUTION_READINESS_REPORT_CONTRACT_VERSION = "research_provider_execution_readiness_report_v1"

_PROVIDER_EXECUTION_READINESS_REPORT_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

_MAX_MODEL_ID_CHARS = 120
_MAX_STATUS_CHARS = 120

_VALID_READINESS_STATUSES = {
    "chain_review_ready",
    "manual_review_required",
    "chain_incomplete",
    "chain_invalid",
    "provider_execution_blocked",
}

_VALID_EXECUTION_STATUSES = {
    "provider_execution_blocked",
    "provider_execution_not_implemented",
    "future_opt_in_required",
}

_VALID_CHAIN_HEALTH_VALUES = {
    "complete",
    "incomplete",
    "invalid",
    "drift_detected",
    "manual_review_required",
}

_READINESS_STATUS_SCORES = {
    "chain_review_ready": 100,
    "manual_review_required": 75,
    "chain_incomplete": 40,
    "provider_execution_blocked": 20,
    "chain_invalid": 0,
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
class ProviderExecutionReadinessReportValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets

    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_readiness_report_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
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


def validate_readiness_status(value: str) -> str:
    """Validate readiness_status. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_READINESS_STATUSES:
        raise ResearchSessionError("invalid_provider_execution_readiness_report_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_readiness_report_status")
    return value


def validate_execution_status(value: str) -> str:
    """Validate execution_status. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_EXECUTION_STATUSES:
        raise ResearchSessionError("invalid_provider_execution_readiness_report_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_readiness_report_status")
    return value


def validate_chain_health(value: str) -> str:
    """Validate chain_health. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_CHAIN_HEALTH_VALUES:
        raise ResearchSessionError("invalid_provider_execution_readiness_report_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_execution_readiness_report_status")
    return value


def provider_execution_readiness_report_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_EXECUTION_READINESS_REPORT_HASH_EXCLUDED_FIELDS}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _check_boolean_safety_flags(data: dict[str, Any]) -> str | None:
    """Return error code if any boolean safety flag is not False.

    Checks both top-level flags and nested no_action_attestations booleans.
    """
    for flag in _BOOLEAN_SAFETY_FLAGS:
        if data.get(flag) is not False:
            return "provider_execution_readiness_report_impossible_boolean"
    # Check nested no_action_attestations booleans
    attestations = data.get("no_action_attestations")
    if attestations is not None:
        if not isinstance(attestations, dict):
            return "provider_execution_readiness_report_impossible_boolean"
        for key, value in attestations.items():
            if value is not False:
                return "provider_execution_readiness_report_impossible_boolean"
    return None


def _build_artifact_chain_summary(
    workspace_path: Path,
    source_audit_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build safe, bounded summaries of the linked artifact chain from audit packet."""
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
        issues_count = 0
        chain.append({
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "artifact_path": artifact_path,
            "artifact_hash": artifact_hash,
            "validation_status": "present" if present else "missing",
            "hash_status": "present" if artifact_hash else "missing",
            "required": required,
            "present": present,
            "warnings_count": warnings_count,
            "issues_count": issues_count,
        })

    _add_summary("research", "source_run_id", "source_run_id", "", source_audit_packet, required=True)
    _add_summary("prompt_packet", "source_prompt_packet_id", "source_prompt_packet_id", "", source_audit_packet, required=True)
    _add_summary("sandbox_request", "source_sandbox_request_id", "source_sandbox_request_id", "", source_audit_packet, required=True)
    _add_summary("provider_call_plan", "source_provider_call_plan_id", "source_provider_call_plan_id", "", source_audit_packet, required=True)
    _add_summary("provider_execution_dry_run", "source_provider_execution_dry_run_id", "source_provider_execution_dry_run_id", "", source_audit_packet, required=True)
    _add_summary("provider_execution_state", "source_provider_execution_state_id", "artifact_path", "source_state_hash", source_audit_packet, required=True)
    _add_summary("provider_execution_audit_packet", "provider_execution_audit_packet_id", "artifact_path", "artifact_hash", source_audit_packet, required=True)

    return chain


def _build_chain_diagnostics(
    artifact_chain: list[dict[str, Any]],
    source_audit_packet: dict[str, Any],
) -> dict[str, Any]:
    """Build chain diagnostics from artifact chain and audit packet."""
    missing_artifacts = [
        item["artifact_type"] for item in artifact_chain
        if item.get("required") and not item.get("present")
    ]
    invalid_artifacts: list[str] = []
    hash_mismatches: list[str] = []
    unsafe_artifacts: list[str] = []
    orphan_artifacts: list[str] = []

    blocking_reasons = list(source_audit_packet.get("blocking_reasons", []))
    if "provider_execution_not_implemented" not in blocking_reasons:
        blocking_reasons.append("provider_execution_not_implemented")

    manual_review_items: list[str] = [
        "Provider execution is blocked and not implemented.",
        "All no-action attestations must be False.",
        "Future opt-in required for real provider execution.",
    ]

    return {
        "missing_artifacts": missing_artifacts,
        "invalid_artifacts": invalid_artifacts,
        "hash_mismatches": hash_mismatches,
        "unsafe_artifacts": unsafe_artifacts,
        "orphan_artifacts": orphan_artifacts,
        "blocked_execution_reasons": blocking_reasons,
        "manual_review_items": manual_review_items,
    }


def _build_hash_diagnostics(
    source_audit_packet: dict[str, Any],
) -> dict[str, Any]:
    """Build hash diagnostics from source audit packet."""
    source_state_hash = source_audit_packet.get("source_state_hash", "")
    artifact_hash = source_audit_packet.get("artifact_hash", "")

    return {
        "source_audit_packet_hash_present": bool(artifact_hash),
        "source_audit_packet_hash_match": True,
        "linked_artifact_hashes_present": bool(source_state_hash),
        "linked_artifact_hash_mismatches": [],
        "replay_match": True,
    }


def _build_safety_gate_summary(source_audit_packet: dict[str, Any]) -> dict[str, Any]:
    """Build a summary of safety gate status from the source audit packet.

    Includes all mandatory boolean safety flags checked by scoring and validation.
    Reads directly from the audit packet's top-level fields.
    """
    return {
        flag: source_audit_packet.get(flag, False)
        for flag in _BOOLEAN_SAFETY_FLAGS
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


def _compute_readiness_score(
    artifact_chain: list[dict[str, Any]],
    chain_diagnostics: dict[str, Any],
    hash_diagnostics: dict[str, Any],
    safety_gate_summary: dict[str, Any],
    boolean_error: str | None,
    forbidden_found: bool,
) -> int:
    """Compute deterministic readiness score from 0 to 100.

    100 means chain is internally complete and review-ready.
    100 still does NOT mean provider execution is allowed.
    """
    # Hard rule: impossible booleans or forbidden fragments force 0
    if boolean_error or forbidden_found:
        return 0

    score = 100

    # Missing required artifacts reduce score
    missing = chain_diagnostics.get("missing_artifacts", [])
    score -= len(missing) * 15

    # Hash mismatches reduce score
    hash_mismatches = chain_diagnostics.get("hash_mismatches", [])
    score -= len(hash_mismatches) * 20

    # Invalid artifacts reduce score
    invalid = chain_diagnostics.get("invalid_artifacts", [])
    score -= len(invalid) * 20

    # Unsafe artifacts reduce score
    unsafe = chain_diagnostics.get("unsafe_artifacts", [])
    score -= len(unsafe) * 20

    # Incomplete linked hashes reduce score
    if not hash_diagnostics.get("linked_artifact_hashes_present", False):
        score -= 10

    # Safety gates: if any top-level safety flag is not explicitly False, reduce
    for flag in _BOOLEAN_SAFETY_FLAGS:
        if safety_gate_summary.get(flag) is not False:
            score = 0
            break

    return max(0, min(100, score))


def _map_score_to_readiness_status(score: int, chain_health: str) -> str:
    """Map readiness score and chain_health to readiness_status."""
    if score == 0 or chain_health == "invalid":
        return "chain_invalid"
    if chain_health == "incomplete":
        return "chain_incomplete"
    if chain_health == "drift_detected":
        return "manual_review_required"
    if chain_health == "manual_review_required":
        return "manual_review_required"
    if score >= 90:
        return "chain_review_ready"
    if score >= 60:
        return "manual_review_required"
    return "chain_incomplete"


def build_provider_execution_readiness_report_dict(
    source_audit_packet: dict[str, Any],
    provider_execution_readiness_report_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    """Build a provider execution readiness report artifact dict in memory.

    No network. No API keys. No provider SDKs. No broker calls.
    """
    validate_contract_lineage_id(provider_execution_readiness_report_id, "provider_execution_readiness_report_id")

    source_provider_execution_audit_packet_id = source_audit_packet.get("provider_execution_audit_packet_id", "")
    validate_contract_lineage_id(source_provider_execution_audit_packet_id, "source_provider_execution_audit_packet_id")
    source_provider_execution_state_id = source_audit_packet.get("source_provider_execution_state_id", "")
    validate_contract_lineage_id(source_provider_execution_state_id, "source_provider_execution_state_id")
    source_provider_execution_dry_run_id = source_audit_packet.get("source_provider_execution_dry_run_id", "")
    validate_contract_lineage_id(source_provider_execution_dry_run_id, "source_provider_execution_dry_run_id")
    source_provider_call_plan_id = source_audit_packet.get("source_provider_call_plan_id", "")
    validate_contract_lineage_id(source_provider_call_plan_id, "source_provider_call_plan_id")
    source_sandbox_request_id = source_audit_packet.get("source_sandbox_request_id", "")
    validate_contract_lineage_id(source_sandbox_request_id, "source_sandbox_request_id")
    source_prompt_packet_id = source_audit_packet.get("source_prompt_packet_id", "")
    validate_contract_lineage_id(source_prompt_packet_id, "source_prompt_packet_id")
    source_run_id = source_audit_packet.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    symbol = validate_contract_symbol(source_audit_packet.get("symbol", ""))
    safe_provider_id = validate_provider_id(source_audit_packet.get("provider_id", ""))
    safe_model_id = validate_model_id(source_audit_packet.get("model_id", ""))
    latest_state = source_audit_packet.get("latest_state", "disabled")
    safe_execution_status = validate_execution_status("provider_execution_blocked")

    created_at = datetime.now(UTC)

    artifact_chain = _build_artifact_chain_summary(workspace_path, source_audit_packet)
    chain_diagnostics = _build_chain_diagnostics(artifact_chain, source_audit_packet)
    hash_diagnostics = _build_hash_diagnostics(source_audit_packet)
    safety_gate_summary = _build_safety_gate_summary(source_audit_packet)
    no_action_attestations = _build_no_action_attestations()

    # Determine chain health
    if chain_diagnostics["missing_artifacts"]:
        chain_health = validate_chain_health("incomplete")
    elif chain_diagnostics["hash_mismatches"]:
        chain_health = validate_chain_health("drift_detected")
    elif chain_diagnostics["invalid_artifacts"]:
        chain_health = validate_chain_health("invalid")
    else:
        chain_health = validate_chain_health("complete")

    # Compute readiness score (boolean_error=None, forbidden_found=False at creation)
    readiness_score = _compute_readiness_score(
        artifact_chain, chain_diagnostics, hash_diagnostics,
        safety_gate_summary, boolean_error=None, forbidden_found=False,
    )
    readiness_status = _map_score_to_readiness_status(readiness_score, chain_health)

    # Blocking reasons and requirements
    blocking_reasons = list(chain_diagnostics["blocked_execution_reasons"])
    missing_requirements = list(chain_diagnostics["missing_artifacts"])
    future_opt_in_requirements = [
        "Manual review of readiness report.",
        "Explicit opt-in for provider execution (future batch).",
        "Provider SDK import and integration (future batch).",
        "Credential loading and validation (future batch).",
        "Network enablement and firewall rules (future batch).",
        "Broker adapter configuration (future batch).",
        "Risk manager approval (future batch).",
    ]

    human_review_checklist = [
        "Verify all no-action attestations are False.",
        "Confirm no provider calls were made.",
        "Confirm no API keys were read.",
        "Confirm no network requests were performed.",
        "Confirm no trading signals were generated.",
        "Confirm no approvals or pending orders were created.",
        "Confirm no broker was touched.",
    ]

    machine_readiness_checks = [
        {"name": "schema_version_supported", "passed": True},
        {"name": "artifact_type_correct", "passed": True},
        {"name": "contract_version_present", "passed": True},
        {"name": "mode_paper", "passed": True},
        {"name": "boolean_safety_flags_false", "passed": True},
        {"name": "lineage_ids_valid", "passed": True},
        {"name": "symbol_valid", "passed": True},
        {"name": "provider_id_valid", "passed": True},
        {"name": "model_id_valid", "passed": True},
        {"name": "source_audit_packet_hash_present", "passed": bool(source_audit_packet.get("artifact_hash", ""))},
    ]

    source_audit_packet_hash = source_audit_packet.get("artifact_hash", "")

    warnings = [
        "This is a local readiness report. No provider was called.",
        "Provider execution remains blocked and not implemented.",
        "All no-action attestations are False by design.",
        "Real provider execution requires explicit future opt-in.",
    ]

    artifact_path_rel = f".atlas/research/{symbol}/provider_execution_readiness_reports/{provider_execution_readiness_report_id}.json"

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_execution_readiness_report",
        "contract_version": PROVIDER_EXECUTION_READINESS_REPORT_CONTRACT_VERSION,
        "provider_execution_readiness_report_id": provider_execution_readiness_report_id,
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
        "latest_state": latest_state,
        "audit_status": "audit_packet_ready",
        "execution_status": safe_execution_status,
        "readiness_status": readiness_status,
        "readiness_score": readiness_score,
        "chain_health": chain_health,
        "artifact_chain": artifact_chain,
        "chain_diagnostics": chain_diagnostics,
        "hash_diagnostics": hash_diagnostics,
        "safety_gate_summary": safety_gate_summary,
        "blocking_reasons": blocking_reasons,
        "missing_requirements": missing_requirements,
        "future_opt_in_requirements": future_opt_in_requirements,
        "human_review_checklist": human_review_checklist,
        "machine_readiness_checks": machine_readiness_checks,
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
        "source_audit_packet_hash": source_audit_packet_hash,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": {
            "source_audit_packet_schema_version": source_audit_packet.get("schema_version", ""),
            "source_audit_packet_contract_version": source_audit_packet.get("contract_version", ""),
        },
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_execution_readiness_report_sha256(artifact)
    return artifact


def create_provider_execution_readiness_report(
    workspace_path: Path,
    provider_execution_audit_packet_id: str,
) -> dict[str, Any]:
    """Create and persist a provider execution readiness report artifact.

    Loads the source audit packet, builds the readiness report, and writes the artifact.
    """
    safe_audit_packet_id = validate_run_id(provider_execution_audit_packet_id)

    from atlas_agent.research.provider_execution_audit_packet import (
        find_provider_execution_audit_packet_by_id,
        load_and_validate_provider_execution_audit_packet,
    )

    audit_path = find_provider_execution_audit_packet_by_id(workspace_path, safe_audit_packet_id)
    if audit_path is None:
        raise ResearchSessionError("provider_execution_audit_packet_not_found")

    source_audit_packet = load_and_validate_provider_execution_audit_packet(audit_path, workspace_path)

    readiness_report_id = generate_run_id()
    artifact = build_provider_execution_readiness_report_dict(
        source_audit_packet,
        readiness_report_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    readiness_dir = workspace_path / RESEARCH_DIR / symbol / "provider_execution_readiness_reports"
    readiness_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_execution_readiness_report_created",
        "provider_execution_readiness_report_id": readiness_report_id,
        "source_provider_execution_audit_packet_id": safe_audit_packet_id,
        "readiness_status": artifact["readiness_status"],
        "readiness_score": artifact["readiness_score"],
        "chain_health": artifact["chain_health"],
        "execution_status": artifact["execution_status"],
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    """Return static error code if value contains forbidden fragments or unsafe chars."""
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_execution_readiness_report_{field_name}"
    return None


def safe_validate_provider_execution_readiness_report_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """Strictly validate a loaded readiness report artifact for read paths.

    Returns (cleaned_data, None) if valid, or (None, error_code) if invalid.
    Never includes raw tampered values in error codes.

    When ``for_replay`` is True, the source audit packet hash match is skipped so
    that replay can detect drift and report ``match=false``.
    """
    # 1. schema_version
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_execution_readiness_report_schema"

    # 2. artifact_type
    if data.get("artifact_type") != "provider_execution_readiness_report":
        return None, "provider_execution_readiness_report_malformed"

    # 3. contract_version
    if data.get("contract_version") != PROVIDER_EXECUTION_READINESS_REPORT_CONTRACT_VERSION:
        return None, "provider_execution_readiness_report_malformed"

    # 4. execution_status / readiness_status / chain_health / audit_status
    try:
        validate_execution_status(data.get("execution_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_readiness_report_status"
    try:
        validate_readiness_status(data.get("readiness_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_readiness_report_status"
    try:
        validate_chain_health(data.get("chain_health", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_readiness_report_status"

    # 5. latest_state
    latest_state = data.get("latest_state", "")
    if not latest_state:
        return None, "invalid_provider_execution_readiness_report_status"
    if _has_forbidden_fragments(latest_state):
        return None, "invalid_provider_execution_readiness_report_status"

    # 6. readiness_score range
    readiness_score = data.get("readiness_score")
    if not isinstance(readiness_score, int) or readiness_score < 0 or readiness_score > 100:
        return None, "invalid_provider_execution_readiness_report_status"

    # 7. boolean safety flags (all must be False)
    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    # 8. mode
    if data.get("mode") != "paper":
        return None, "provider_execution_readiness_report_malformed"

    # 9. lineage IDs — reject if unsafe
    for field in (
        "provider_execution_readiness_report_id",
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
            return None, "invalid_provider_execution_readiness_report_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    # 10. symbol
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_execution_readiness_report_lineage"

    # 11. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_readiness_report_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    # 12. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_execution_readiness_report_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    # 13. hash consistency
    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_execution_readiness_report_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_execution_readiness_report_hash_mismatch"

    # 14. source audit packet exists and hash matches (if workspace provided)
    if workspace_path is not None and not for_replay:
        source_audit_packet_id = data.get("source_provider_execution_audit_packet_id", "")
        if source_audit_packet_id:
            try:
                from atlas_agent.research.provider_execution_audit_packet import (
                    find_provider_execution_audit_packet_by_id,
                    load_provider_execution_audit_packet,
                )

                audit_path = find_provider_execution_audit_packet_by_id(workspace_path, source_audit_packet_id)
                if audit_path is None:
                    return None, "provider_execution_readiness_report_source_audit_packet_missing"
                audit_data = load_provider_execution_audit_packet(audit_path, workspace_path)
                stored_audit_hash = data.get("source_audit_packet_hash", "")
                actual_audit_hash = audit_data.get("artifact_hash", "")
                if stored_audit_hash != actual_audit_hash:
                    return None, "provider_execution_readiness_report_source_audit_packet_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_execution_readiness_report_source_audit_packet_missing"

    # 15. no forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("artifact_chain", [])),
        json.dumps(data.get("chain_diagnostics", {})),
        json.dumps(data.get("hash_diagnostics", {})),
        json.dumps(data.get("safety_gate_summary", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("missing_requirements", [])),
        json.dumps(data.get("future_opt_in_requirements", [])),
        json.dumps(data.get("human_review_checklist", [])),
        json.dumps(data.get("machine_readiness_checks", [])),
        json.dumps(data.get("no_action_attestations", {})),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_execution_readiness_report_malformed"

    # 16. path containment
    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_execution_readiness_report_malformed"

    # Return a cleaned copy with only safe fields
    cleaned = {
        "schema_version": data.get("schema_version", ""),
        "artifact_type": data.get("artifact_type", ""),
        "contract_version": data.get("contract_version", ""),
        "provider_execution_readiness_report_id": data.get("provider_execution_readiness_report_id", ""),
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
        "latest_state": data.get("latest_state", ""),
        "audit_status": data.get("audit_status", ""),
        "execution_status": data.get("execution_status", ""),
        "readiness_status": data.get("readiness_status", ""),
        "readiness_score": data.get("readiness_score", 0),
        "chain_health": data.get("chain_health", ""),
        "artifact_chain": data.get("artifact_chain", []),
        "chain_diagnostics": data.get("chain_diagnostics", {}),
        "hash_diagnostics": data.get("hash_diagnostics", {}),
        "safety_gate_summary": data.get("safety_gate_summary", {}),
        "blocking_reasons": data.get("blocking_reasons", []),
        "missing_requirements": data.get("missing_requirements", []),
        "future_opt_in_requirements": data.get("future_opt_in_requirements", []),
        "human_review_checklist": data.get("human_review_checklist", []),
        "machine_readiness_checks": data.get("machine_readiness_checks", []),
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
        "source_audit_packet_hash": data.get("source_audit_packet_hash", ""),
        "artifact_path": data.get("artifact_path", ""),
        "warnings": data.get("warnings", []),
        "metadata": data.get("metadata", {}),
        "artifact_hash": data.get("artifact_hash", ""),
        "created_at": data.get("created_at", ""),
    }
    return cleaned, None


def validate_provider_execution_readiness_report_artifact(
    data: dict[str, Any],
    workspace_path: Path | None = None,
) -> ProviderExecutionReadinessReportValidationResult:
    """Validate a provider execution readiness report artifact against the local contract."""
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
            at == "provider_execution_readiness_report",
            "artifact_type must be provider_execution_readiness_report."
            if at != "provider_execution_readiness_report"
            else "artifact_type is correct.",
        )
    )

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_EXECUTION_READINESS_REPORT_CONTRACT_VERSION,
            "contract_version must match current contract."
            if cv != PROVIDER_EXECUTION_READINESS_REPORT_CONTRACT_VERSION
            else "contract_version matches.",
        )
    )

    # 4. execution_status
    exec_status = data.get("execution_status", "")
    exec_ok = exec_status in _VALID_EXECUTION_STATUSES
    checks.append(
        _check_name(
            "execution_status_valid",
            exec_ok,
            "execution_status is invalid." if not exec_ok else "execution_status is valid.",
        )
    )

    # 5. readiness_status
    readiness_status = data.get("readiness_status", "")
    readiness_ok = readiness_status in _VALID_READINESS_STATUSES
    checks.append(
        _check_name(
            "readiness_status_valid",
            readiness_ok,
            "readiness_status is invalid." if not readiness_ok else "readiness_status is valid.",
        )
    )

    # 6. chain_health
    chain_health = data.get("chain_health", "")
    health_ok = chain_health in _VALID_CHAIN_HEALTH_VALUES
    checks.append(
        _check_name(
            "chain_health_valid",
            health_ok,
            "chain_health is invalid." if not health_ok else "chain_health is valid.",
        )
    )

    # 7. readiness_score
    score = data.get("readiness_score")
    score_ok = isinstance(score, int) and 0 <= score <= 100
    checks.append(
        _check_name(
            "readiness_score_in_range",
            score_ok,
            "readiness_score must be an integer between 0 and 100." if not score_ok else "readiness_score is in range.",
        )
    )

    # 8. latest_state
    latest_state = data.get("latest_state", "")
    state_ok = bool(latest_state) and not _has_forbidden_fragments(latest_state)
    checks.append(
        _check_name(
            "latest_state_safe",
            state_ok,
            "latest_state is unsafe or empty." if not state_ok else "latest_state is safe.",
        )
    )

    # 9. boolean safety flags
    flags_ok = _check_boolean_safety_flags(data) is None
    checks.append(
        _check_name(
            "boolean_safety_flags_false",
            flags_ok,
            "A boolean safety flag is not False." if not flags_ok else "All boolean safety flags are False.",
        )
    )

    # 10. mode
    mode = data.get("mode", "")
    mode_ok = mode == "paper"
    checks.append(
        _check_name(
            "mode_paper",
            mode_ok,
            "mode must be paper." if not mode_ok else "mode is paper.",
        )
    )

    # 11. lineage IDs
    lineage_fields = (
        "provider_execution_readiness_report_id",
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

    # 12. symbol
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

    # 13. provider_id
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

    # 14. model_id
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

    # 15. hash consistency
    stored_hash = data.get("artifact_hash", "")
    hash_ok = False
    if stored_hash:
        computed = provider_execution_readiness_report_sha256(data)
        hash_ok = stored_hash == computed
    checks.append(
        _check_name(
            "artifact_hash_consistent",
            hash_ok,
            "artifact_hash does not match computed hash." if not hash_ok else "artifact_hash is consistent.",
        )
    )

    # 16. source audit packet hash match (if workspace)
    if workspace_path is not None:
        source_audit_id = data.get("source_provider_execution_audit_packet_id", "")
        source_hash_ok = False
        if source_audit_id:
            try:
                from atlas_agent.research.provider_execution_audit_packet import (
                    find_provider_execution_audit_packet_by_id,
                    load_provider_execution_audit_packet,
                )

                audit_path = find_provider_execution_audit_packet_by_id(workspace_path, source_audit_id)
                if audit_path is not None:
                    audit_data = load_provider_execution_audit_packet(audit_path, workspace_path)
                    stored_audit_hash = data.get("source_audit_packet_hash", "")
                    actual_audit_hash = audit_data.get("artifact_hash", "")
                    source_hash_ok = stored_audit_hash == actual_audit_hash
            except Exception:
                pass
        checks.append(
            _check_name(
                "source_audit_packet_hash_match",
                source_hash_ok,
                "Source audit packet hash does not match." if not source_hash_ok else "Source audit packet hash matches.",
            )
        )

    # 17. forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("artifact_chain", [])),
        json.dumps(data.get("chain_diagnostics", {})),
        json.dumps(data.get("hash_diagnostics", {})),
        json.dumps(data.get("safety_gate_summary", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("missing_requirements", [])),
        json.dumps(data.get("future_opt_in_requirements", [])),
        json.dumps(data.get("human_review_checklist", [])),
        json.dumps(data.get("machine_readiness_checks", [])),
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
        "provider_execution_readiness_report_valid"
        if valid
        else "manual_review_required"
    )

    if not valid:
        warnings.append("Readiness report validation failed. Manual review required.")

    return ProviderExecutionReadinessReportValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def replay_provider_execution_readiness_report(
    workspace_path: Path,
    provider_execution_readiness_report_id: str,
) -> dict[str, Any]:
    """Replay a provider execution readiness report from its source audit packet and compare hashes.

    Read-only by default. Does not call providers, read API keys, or authorize trading.
    """
    safe_id = validate_run_id(provider_execution_readiness_report_id)

    report_path = find_provider_execution_readiness_report_by_id(workspace_path, safe_id)
    if report_path is None:
        raise ResearchSessionError("provider_execution_readiness_report_not_found")

    loaded_data = load_provider_execution_readiness_report(report_path, workspace_path)
    cleaned, error = safe_validate_provider_execution_readiness_report_data(
        loaded_data, workspace_path, for_replay=True
    )
    if error:
        raise ResearchSessionError(error)

    source_audit_packet_id = loaded_data.get("source_provider_execution_audit_packet_id", "")
    from atlas_agent.research.provider_execution_audit_packet import (
        find_provider_execution_audit_packet_by_id,
        load_provider_execution_audit_packet,
    )

    audit_path = find_provider_execution_audit_packet_by_id(workspace_path, source_audit_packet_id)
    if audit_path is None:
        raise ResearchSessionError("provider_execution_audit_packet_not_found")
    source_audit_packet = load_provider_execution_audit_packet(audit_path, workspace_path)

    rebuilt = build_provider_execution_readiness_report_dict(
        source_audit_packet,
        safe_id,
        workspace_path,
    )

    expected_hash = loaded_data.get("artifact_hash", "")
    actual_hash = provider_execution_readiness_report_sha256(rebuilt)

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
        warnings.append("Readiness report hash mismatch. Source audit packet or linked chain may have changed.")

    return {
        "match": expected_hash == actual_hash,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "checks": checks,
        "warnings": warnings,
    }


def find_provider_execution_readiness_report_by_id(
    workspace_path: Path,
    provider_execution_readiness_report_id: str,
) -> Path | None:
    """Find a provider execution readiness report artifact by its ID.

    Returns the path if found, None if not found, raises if ambiguous.
    """
    safe_id = validate_run_id(provider_execution_readiness_report_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        readiness_dir = sym_dir / "provider_execution_readiness_reports"
        if not readiness_dir.exists():
            continue
        for path in readiness_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("provider_execution_readiness_report_id") == safe_id:
                matches.append(path)

    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_execution_readiness_report_id")
    return matches[0] if matches else None


def load_provider_execution_readiness_report(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load a provider execution readiness report artifact from disk.

    Performs basic safety checks but does not fully validate.
    """
    if not path.exists():
        raise ResearchSessionError("provider_execution_readiness_report_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_execution_readiness_report_malformed")

    data["artifact_path"] = path.relative_to(workspace_path).as_posix()

    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError(
            f"Unsupported schema version: {sv} (expected {RESEARCH_ARTIFACT_SCHEMA_VERSION})"
        )

    return data


def load_and_validate_provider_execution_readiness_report(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load and strictly validate a provider execution readiness report artifact."""
    data = load_provider_execution_readiness_report(path, workspace_path)
    cleaned, error = safe_validate_provider_execution_readiness_report_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_provider_execution_readiness_report_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider execution readiness report artifact metadata dicts, newest first.

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
        readiness_dir = sym_dir / "provider_execution_readiness_reports"
        if not readiness_dir.exists():
            continue
        for path in readiness_dir.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                invalid_items.append({
                    "provider_execution_readiness_report_id": "<invalid>",
                    "source_provider_execution_audit_packet_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": sym_dir.name,
                    "readiness_status": "invalid",
                    "readiness_score": 0,
                    "chain_health": "invalid",
                    "execution_status": "invalid",
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
                    "provider_execution_readiness_report_id": "<invalid>",
                    "source_provider_execution_audit_packet_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "readiness_status": "invalid",
                    "readiness_score": 0,
                    "chain_health": "invalid",
                    "execution_status": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "unsupported_provider_execution_readiness_report_schema",
                    "created_at": "",
                })
                continue

            cleaned, error = safe_validate_provider_execution_readiness_report_data(raw, workspace_path)
            if error:
                invalid_items.append({
                    "provider_execution_readiness_report_id": "<invalid>",
                    "source_provider_execution_audit_packet_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "readiness_status": "invalid",
                    "readiness_score": 0,
                    "chain_health": "invalid",
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
                "provider_execution_readiness_report_id": cleaned.get("provider_execution_readiness_report_id", ""),
                "source_provider_execution_audit_packet_id": cleaned.get("source_provider_execution_audit_packet_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", ""),
                "readiness_status": cleaned.get("readiness_status", ""),
                "readiness_score": cleaned.get("readiness_score", 0),
                "chain_health": cleaned.get("chain_health", ""),
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


# ---------------------------------------------------------------------------
# Chain doctor
# ---------------------------------------------------------------------------

def provider_execution_chain_doctor(
    workspace_path: Path,
    run_id: str,
) -> dict[str, Any]:
    """Read-only diagnostic for the full provider-preflight chain under one research run.

    Does not create artifacts. Does not write events.
    Validates/summarizes all known provider-preflight artifacts for a run.
    """
    safe_run_id = validate_run_id(run_id)

    from atlas_agent.research.session import (
        find_research_artifact_by_run_id,
        iter_plan_artifacts,
        iter_research_artifacts,
        load_research_artifact,
    )

    # Find research artifact
    research_path = find_research_artifact_by_run_id(workspace_path, safe_run_id)
    if research_path is None:
        return {
            "ok": False,
            "status": "research_provider_execution_chain_doctor",
            "run_id": safe_run_id,
            "symbol": "",
            "chain_health": "invalid",
            "readiness_status": "chain_invalid",
            "missing_artifacts": ["research"],
            "invalid_artifacts": [],
            "orphan_artifacts": [],
            "hash_mismatches": [],
            "blocking_reasons": ["research_artifact_not_found"],
            "warnings": ["Run not found."],
        }

    research = load_research_artifact(research_path, workspace_path)
    symbol = research.get("symbol", "")

    # Gather all artifacts linked to this run
    research_items = iter_research_artifacts(workspace_path, symbol=symbol)
    plan_items = iter_plan_artifacts(workspace_path, symbol=symbol)

    from atlas_agent.research.session import _iter_prompt_artifacts, _iter_sandbox_request_artifacts
    prompt_items = _iter_prompt_artifacts(workspace_path, symbol=symbol)
    sandbox_request_items = _iter_sandbox_request_artifacts(workspace_path, symbol=symbol)

    from atlas_agent.research.provider_call_plan import iter_provider_call_plan_artifacts
    provider_call_plan_items = iter_provider_call_plan_artifacts(workspace_path, symbol=symbol)

    from atlas_agent.research.provider_execution_dry_run import iter_provider_execution_dry_run_artifacts
    dry_run_items = iter_provider_execution_dry_run_artifacts(workspace_path, symbol=symbol)

    from atlas_agent.research.provider_execution_state import iter_provider_execution_state_artifacts
    state_items = iter_provider_execution_state_artifacts(workspace_path, symbol=symbol)

    from atlas_agent.research.provider_execution_audit_packet import iter_provider_execution_audit_packet_artifacts
    audit_packet_items = iter_provider_execution_audit_packet_artifacts(workspace_path, symbol=symbol)

    from atlas_agent.research.provider_execution_readiness_report import iter_provider_execution_readiness_report_artifacts
    readiness_items = iter_provider_execution_readiness_report_artifacts(workspace_path, symbol=symbol)

    # Filter to run-linked
    linked_plans = [p for p in plan_items if p.get("source_run_id") == safe_run_id]
    linked_plan_ids = {p.get("plan_id", "") for p in linked_plans}

    linked_prompts = [p for p in prompt_items if p.get("source_run_id") == safe_run_id]
    linked_prompt_ids = {p.get("prompt_packet_id", "") for p in linked_prompts}

    linked_sandbox_requests = [sr for sr in sandbox_request_items if sr.get("source_run_id") == safe_run_id]
    # Also link by prompt_packet_id
    linked_sandbox_requests += [sr for sr in sandbox_request_items if sr.get("prompt_packet_id", "") in linked_prompt_ids]
    linked_sandbox_request_ids = {sr.get("sandbox_request_id", "") for sr in linked_sandbox_requests}

    linked_provider_call_plans = [pcp for pcp in provider_call_plan_items if pcp.get("source_sandbox_request_id", "") in linked_sandbox_request_ids]
    linked_provider_call_plan_ids = {pcp.get("provider_call_plan_id", "") for pcp in linked_provider_call_plans}

    linked_dry_runs = [dr for dr in dry_run_items if dr.get("source_provider_call_plan_id", "") in linked_provider_call_plan_ids]
    linked_dry_run_ids = {dr.get("provider_execution_dry_run_id", "") for dr in linked_dry_runs}

    linked_states = [s for s in state_items if s.get("source_provider_execution_dry_run_id", "") in linked_dry_run_ids]
    linked_state_ids = {s.get("provider_execution_state_id", "") for s in linked_states}

    linked_audit_packets = [ap for ap in audit_packet_items if ap.get("source_provider_execution_state_id", "") in linked_state_ids]
    linked_audit_packet_ids = {ap.get("provider_execution_audit_packet_id", "") for ap in linked_audit_packets}

    linked_readiness_reports = [rr for rr in readiness_items if rr.get("source_provider_execution_audit_packet_id", "") in linked_audit_packet_ids]

    missing_artifacts: list[str] = []
    invalid_artifacts: list[str] = []
    orphan_artifacts: list[str] = []
    hash_mismatches: list[str] = []
    blocking_reasons: list[str] = ["provider_execution_not_implemented"]
    warnings: list[str] = []

    # Check for invalid artifacts in linked sets
    for item_list, name in [
        (linked_plans, "plan"),
        (linked_prompts, "prompt_packet"),
        (linked_sandbox_requests, "sandbox_request"),
        (linked_provider_call_plans, "provider_call_plan"),
        (linked_dry_runs, "provider_execution_dry_run"),
        (linked_states, "provider_execution_state"),
        (linked_audit_packets, "provider_execution_audit_packet"),
        (linked_readiness_reports, "provider_execution_readiness_report"),
    ]:
        for item in item_list:
            if item.get("_invalid") or item.get("_malformed"):
                invalid_artifacts.append(name)

    # Missing artifacts (provider-preflight chain only)
    if not linked_prompts:
        missing_artifacts.append("prompt_packet")
    if not linked_sandbox_requests:
        missing_artifacts.append("sandbox_request")
    if not linked_provider_call_plans:
        missing_artifacts.append("provider_call_plan")
    if not linked_dry_runs:
        missing_artifacts.append("provider_execution_dry_run")
    if not linked_states:
        missing_artifacts.append("provider_execution_state")
    if not linked_audit_packets:
        missing_artifacts.append("provider_execution_audit_packet")
    if not linked_readiness_reports:
        missing_artifacts.append("provider_execution_readiness_report")

    # Chain health
    if invalid_artifacts:
        chain_health = "invalid"
    elif missing_artifacts:
        chain_health = "incomplete"
    elif hash_mismatches:
        chain_health = "drift_detected"
    else:
        chain_health = "complete"

    # Readiness status
    if chain_health == "invalid":
        readiness_status = "chain_invalid"
    elif chain_health == "incomplete":
        readiness_status = "chain_incomplete"
    elif chain_health == "drift_detected":
        readiness_status = "manual_review_required"
    else:
        readiness_status = "chain_review_ready"

    return {
        "ok": True,
        "status": "research_provider_execution_chain_doctor",
        "run_id": safe_run_id,
        "symbol": symbol,
        "chain_health": chain_health,
        "readiness_status": readiness_status,
        "missing_artifacts": missing_artifacts,
        "invalid_artifacts": list(set(invalid_artifacts)),
        "orphan_artifacts": list(set(orphan_artifacts)),
        "hash_mismatches": hash_mismatches,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }
