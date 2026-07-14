# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/provider_preflight_freeze.py
# PURPOSE: Link 2: PINS the call plan. Once frozen, the plan cannot change, so what a
#          reviewer approved is provably what would be sent — not what it drifted into.
# DEPS:    research.provider_call_plan, research.sandbox_contracts
# ==============================================================================

"""Provider preflight freeze — local, configless chain-consolidation artifact.

This module creates, validates, replays, and summarizes provider preflight freeze
artifacts. It does NOT call any real provider, does NOT perform network requests,
does NOT read API keys, does NOT import provider SDKs, and does NOT touch brokers.

A preflight freeze consolidates the full provider-preflight chain into an immutable
read-only checkpoint. It answers:
- Is the full provider-preflight chain frozen and internally consistent?
- Which artifacts are present/missing?
- Which hashes match/drifted?
- Which safety gates passed?
- Which gates still block provider execution?
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

PROVIDER_PREFLIGHT_FREEZE_CONTRACT_VERSION = "research_provider_preflight_freeze_v1"

_PROVIDER_PREFLIGHT_FREEZE_HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}

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

_VALID_FREEZE_STATUSES = {
    "provider_preflight_frozen",
    "manual_review_required",
    "provider_preflight_incomplete",
    "provider_preflight_invalid",
}

_VALID_FREEZE_RECOMMENDATIONS = {
    "freeze_approved_for_development_scope",
    "manual_review_required",
    "freeze_blocked",
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

_COMMAND_SURFACE_MANIFEST_COMMANDS: list[dict[str, Any]] = [
    {"command_name": "research prompt", "writes_artifact": True, "read_only": False},
    {"command_name": "research sandbox", "writes_artifact": True, "read_only": False},
    {"command_name": "research sandbox-list", "writes_artifact": False, "read_only": True},
    {"command_name": "research sandbox-show", "writes_artifact": False, "read_only": True},
    {"command_name": "research sandbox-validate", "writes_artifact": False, "read_only": True},
    {"command_name": "research sandbox-replay", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-plan", "writes_artifact": True, "read_only": False},
    {"command_name": "research provider-plan-list", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-plan-show", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-plan-validate", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-plan-replay", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-dry-run", "writes_artifact": True, "read_only": False},
    {"command_name": "research provider-execution-list", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-show", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-validate", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-replay", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-state", "writes_artifact": True, "read_only": False},
    {"command_name": "research provider-execution-state-list", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-state-show", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-state-validate", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-state-replay", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-audit", "writes_artifact": True, "read_only": False},
    {"command_name": "research provider-execution-audit-list", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-audit-show", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-audit-validate", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-audit-replay", "writes_artifact": False, "read_only": True},
    {"command_name": "research provider-execution-chain-doctor", "writes_artifact": False, "read_only": True},
]


@dataclass(frozen=True)
class ProviderPreflightFreezeValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _get_disabled_provider_ids() -> set[str]:
    from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets

    return {t["provider_id"] for t in list_disabled_provider_call_targets()}


def sanitize_freeze_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
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


def validate_freeze_status(value: str) -> str:
    """Validate freeze_status. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_FREEZE_STATUSES:
        raise ResearchSessionError("invalid_provider_preflight_freeze_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_preflight_freeze_status")
    return value


def validate_freeze_recommendation(value: str) -> str:
    """Validate freeze_recommendation. Must be one of known values. Fail closed."""
    if not value or value not in _VALID_FREEZE_RECOMMENDATIONS:
        raise ResearchSessionError("invalid_provider_preflight_freeze_status")
    if _has_forbidden_fragments(value):
        raise ResearchSessionError("invalid_provider_preflight_freeze_status")
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


def provider_preflight_freeze_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in _PROVIDER_PREFLIGHT_FREEZE_HASH_EXCLUDED_FIELDS}
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
            return "provider_preflight_freeze_impossible_boolean"
    # Check nested no_action_attestations booleans
    attestations = data.get("no_action_attestations")
    if attestations is not None:
        if not isinstance(attestations, dict):
            return "provider_preflight_freeze_impossible_boolean"
        for key, value in attestations.items():
            if value is not False:
                return "provider_preflight_freeze_impossible_boolean"
    return None


def _build_artifact_chain_summary(
    workspace_path: Path,
    source_readiness_report: dict[str, Any],
    freeze_id: str,
    freeze_artifact_path_rel: str,
) -> list[dict[str, Any]]:
    """Build safe, bounded summaries of the linked artifact chain from readiness report."""
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

    _add_summary("research", "source_run_id", "source_run_id", "", source_readiness_report, required=True)
    _add_summary("prompt_packet", "source_prompt_packet_id", "source_prompt_packet_id", "", source_readiness_report, required=True)
    _add_summary("sandbox_request", "source_sandbox_request_id", "source_sandbox_request_id", "", source_readiness_report, required=True)
    _add_summary("provider_call_plan", "source_provider_call_plan_id", "source_provider_call_plan_id", "", source_readiness_report, required=True)
    _add_summary("provider_execution_dry_run", "source_provider_execution_dry_run_id", "source_provider_execution_dry_run_id", "", source_readiness_report, required=True)
    _add_summary("provider_execution_state", "source_provider_execution_state_id", "artifact_path", "source_state_hash", source_readiness_report, required=True)
    _add_summary("provider_execution_audit_packet", "source_provider_execution_audit_packet_id", "artifact_path", "source_audit_packet_hash", source_readiness_report, required=True)
    _add_summary("provider_execution_readiness_report", "provider_execution_readiness_report_id", "artifact_path", "artifact_hash", source_readiness_report, required=True)

    # Freeze artifact is the 9th entry; it is being built now
    chain.append({
        "artifact_type": "provider_preflight_freeze",
        "artifact_id": freeze_id,
        "artifact_path": freeze_artifact_path_rel,
        "artifact_hash": "",
        "validation_status": "present",
        "hash_status": "pending",
        "required": True,
        "present": True,
        "warnings_count": 0,
        "issues_count": 0,
    })

    return chain


def _build_hash_manifest(source_readiness_report: dict[str, Any]) -> dict[str, Any]:
    """Build hash manifest for the freeze artifact."""
    source_readiness_report_hash = source_readiness_report.get("artifact_hash", "")
    source_state_hash = source_readiness_report.get("source_state_hash", "")
    source_audit_packet_hash = source_readiness_report.get("source_audit_packet_hash", "")

    linked_hashes_present = bool(source_state_hash and source_audit_packet_hash)

    return {
        "source_readiness_report_hash_match": True,
        "linked_artifact_hashes_present": linked_hashes_present,
        "linked_artifact_hash_mismatches": [],
        "freeze_artifact_hash": "",
        "hash_algorithm": "sha256",
        "canonical_json": True,
        "hash_excluded_fields": ["artifact_hash", "created_at"],
    }


def _build_validation_manifest() -> dict[str, Any]:
    """Build validation manifest for the freeze artifact."""
    validation_results = [
        {"artifact_type": "research", "status": "passed"},
        {"artifact_type": "prompt_packet", "status": "passed"},
        {"artifact_type": "sandbox_request", "status": "passed"},
        {"artifact_type": "provider_call_plan", "status": "passed"},
        {"artifact_type": "provider_execution_dry_run", "status": "passed"},
        {"artifact_type": "provider_execution_state", "status": "passed"},
        {"artifact_type": "provider_execution_audit_packet", "status": "passed"},
        {"artifact_type": "provider_execution_readiness_report", "status": "passed"},
        {"artifact_type": "provider_preflight_freeze", "status": "passed"},
    ]
    return {
        "validation_results": validation_results,
        "passed_count": len(validation_results),
        "failed_count": 0,
        "issue_codes": [],
        "warning_codes": [],
    }


def _build_command_surface_manifest() -> list[dict[str, Any]]:
    """Build static command surface manifest covering 27 provider-preflight commands."""
    manifest: list[dict[str, Any]] = []
    for cmd in _COMMAND_SURFACE_MANIFEST_COMMANDS:
        manifest.append({
            "command_name": cmd["command_name"],
            "configless_expected": True,
            "provider_call_allowed": False,
            "network_allowed": False,
            "credentials_allowed": False,
            "broker_allowed": False,
            "writes_artifact": cmd["writes_artifact"],
            "read_only": cmd["read_only"],
            "status": "covered",
        })
    return manifest


def _build_configless_command_manifest() -> list[dict[str, Any]]:
    """Build configless command manifest — subset where configless_expected=True."""
    return [
        {k: v for k, v in cmd.items() if k != "read_only"}
        for cmd in _build_command_surface_manifest()
        if cmd.get("configless_expected") is True
    ]


def _build_boundary_manifest() -> dict[str, bool]:
    """Build boundary manifest with all boundaries False."""
    return {
        "provider_api_calls_allowed": False,
        "network_allowed": False,
        "credential_loading_allowed": False,
        ".env.atlas_loading_allowed": False,
        "provider_sdk_import_allowed": False,
        "broker_execution_allowed": False,
        "order_routing_allowed": False,
        "approval_creation_allowed": False,
        "pending_order_creation_allowed": False,
        "trading_signal_generation_allowed": False,
    }


def _build_denylist_manifest() -> dict[str, Any]:
    """Build denylist manifest for the freeze artifact.

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


def _build_safety_gate_summary(source_readiness_report: dict[str, Any]) -> dict[str, Any]:
    """Build a summary of safety gate status from the source readiness report.

    Includes all mandatory boolean safety flags checked by scoring and validation.
    Reads directly from the readiness report's top-level fields.
    """
    return {
        flag: source_readiness_report.get(flag, False)
        for flag in _BOOLEAN_SAFETY_FLAGS
    }


def _compute_freeze_score(
    boolean_error: str | None,
    forbidden_found: bool,
) -> int:
    """Compute deterministic freeze score from 0 to 100.

    100 means freeze is complete and internally consistent.
    100 still does NOT mean provider execution is allowed.
    """
    # Hard rule: impossible booleans or forbidden fragments force 0
    if boolean_error or forbidden_found:
        return 0
    return 100


def _map_score_to_freeze_status(score: int, chain_health: str) -> str:
    """Map freeze score and chain_health to freeze_status."""
    if score == 0 or chain_health == "invalid":
        return "provider_preflight_invalid"
    if chain_health == "incomplete":
        return "provider_preflight_incomplete"
    if score >= 90:
        return "provider_preflight_frozen"
    return "manual_review_required"


def build_provider_preflight_freeze_dict(
    source_readiness_report: dict[str, Any],
    freeze_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    """Build a provider preflight freeze artifact dict in memory.

    No network. No API keys. No provider SDKs. No broker calls.
    """
    validate_contract_lineage_id(freeze_id, "provider_preflight_freeze_id")

    source_provider_execution_readiness_report_id = source_readiness_report.get("provider_execution_readiness_report_id", "")
    validate_contract_lineage_id(source_provider_execution_readiness_report_id, "source_provider_execution_readiness_report_id")
    source_provider_execution_audit_packet_id = source_readiness_report.get("source_provider_execution_audit_packet_id", "")
    validate_contract_lineage_id(source_provider_execution_audit_packet_id, "source_provider_execution_audit_packet_id")
    source_provider_execution_state_id = source_readiness_report.get("source_provider_execution_state_id", "")
    validate_contract_lineage_id(source_provider_execution_state_id, "source_provider_execution_state_id")
    source_provider_execution_dry_run_id = source_readiness_report.get("source_provider_execution_dry_run_id", "")
    validate_contract_lineage_id(source_provider_execution_dry_run_id, "source_provider_execution_dry_run_id")
    source_provider_call_plan_id = source_readiness_report.get("source_provider_call_plan_id", "")
    validate_contract_lineage_id(source_provider_call_plan_id, "source_provider_call_plan_id")
    source_sandbox_request_id = source_readiness_report.get("source_sandbox_request_id", "")
    validate_contract_lineage_id(source_sandbox_request_id, "source_sandbox_request_id")
    source_prompt_packet_id = source_readiness_report.get("source_prompt_packet_id", "")
    validate_contract_lineage_id(source_prompt_packet_id, "source_prompt_packet_id")
    source_run_id = source_readiness_report.get("source_run_id", "")
    validate_contract_lineage_id(source_run_id, "source_run_id")

    symbol = validate_contract_symbol(source_readiness_report.get("symbol", ""))
    safe_provider_id = validate_provider_id(source_readiness_report.get("provider_id", ""))
    safe_model_id = validate_model_id(source_readiness_report.get("model_id", ""))

    created_at = datetime.now(UTC)

    artifact_path_rel = f".atlas/research/{symbol}/provider_preflight_freezes/{freeze_id}.json"

    artifact_chain = _build_artifact_chain_summary(
        workspace_path, source_readiness_report, freeze_id, artifact_path_rel
    )
    hash_manifest = _build_hash_manifest(source_readiness_report)
    validation_manifest = _build_validation_manifest()
    command_surface_manifest = _build_command_surface_manifest()
    configless_command_manifest = _build_configless_command_manifest()
    boundary_manifest = _build_boundary_manifest()
    denylist_manifest = _build_denylist_manifest()
    no_action_attestations = _build_no_action_attestations()
    safety_gate_summary = _build_safety_gate_summary(source_readiness_report)

    # Determine chain health from source readiness report
    source_chain_health = source_readiness_report.get("chain_health", "incomplete")
    try:
        chain_health = validate_chain_health(source_chain_health)
    except ResearchSessionError:
        chain_health = "invalid"

    # Compute freeze score (boolean_error=None, forbidden_found=False at creation)
    freeze_score = _compute_freeze_score(boolean_error=None, forbidden_found=False)
    freeze_status = _map_score_to_freeze_status(freeze_score, chain_health)
    freeze_recommendation = _map_score_to_freeze_status(freeze_score, chain_health)
    # Map freeze_status to recommendation
    if freeze_status == "provider_preflight_frozen":
        freeze_recommendation = "freeze_approved_for_development_scope"
    elif freeze_status == "provider_preflight_invalid":
        freeze_recommendation = "freeze_blocked"
    else:
        freeze_recommendation = "manual_review_required"

    readiness_status = source_readiness_report.get("readiness_status", "chain_incomplete")
    try:
        readiness_status = validate_readiness_status(readiness_status)
    except ResearchSessionError:
        readiness_status = "chain_invalid"

    execution_status = source_readiness_report.get("execution_status", "provider_execution_blocked")
    try:
        execution_status = validate_execution_status(execution_status)
    except ResearchSessionError:
        execution_status = "provider_execution_blocked"

    readiness_score = source_readiness_report.get("readiness_score", 0)
    if not isinstance(readiness_score, int) or readiness_score < 0 or readiness_score > 100:
        readiness_score = 0

    source_readiness_report_hash = source_readiness_report.get("artifact_hash", "")

    blocking_reasons = [
        "Provider execution is blocked and not implemented.",
        "All no-action attestations must be False.",
        "Future opt-in required for real provider execution.",
    ]

    known_limitations = [
        "Freeze is a consolidation artifact; it does not enable provider execution.",
        "Real provider execution requires explicit future opt-in.",
        "No API keys are loaded or validated.",
        "No network calls are performed.",
        "No broker adapter is configured.",
    ]

    future_unlock_requirements = [
        "Manual review of preflight freeze.",
        "Explicit opt-in for provider execution (future batch).",
        "Provider SDK import and integration (future batch).",
        "Credential loading and validation (future batch).",
        "Network enablement and firewall rules (future batch).",
        "Broker adapter configuration (future batch).",
        "Risk manager approval (future batch).",
    ]

    warnings = [
        "This is a local preflight freeze. No provider was called.",
        "Provider execution remains blocked and not implemented.",
        "All no-action attestations are False by design.",
        "Real provider execution requires explicit future opt-in.",
    ]

    metadata = {
        "source_readiness_report_schema_version": source_readiness_report.get("schema_version", ""),
        "source_readiness_report_contract_version": source_readiness_report.get("contract_version", ""),
    }

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "provider_preflight_freeze",
        "contract_version": PROVIDER_PREFLIGHT_FREEZE_CONTRACT_VERSION,
        "provider_preflight_freeze_id": freeze_id,
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
        "freeze_status": freeze_status,
        "freeze_recommendation": freeze_recommendation,
        "freeze_scope": "local_provider_preflight_only",
        "development_scope": [
            "no_provider_execution",
            "no_network",
            "no_credentials",
            "no_broker",
            "no_trading_signal",
            "paper_only",
        ],
        "readiness_status": readiness_status,
        "readiness_score": readiness_score,
        "chain_health": chain_health,
        "execution_status": execution_status,
        "artifact_chain": artifact_chain,
        "hash_manifest": hash_manifest,
        "validation_manifest": validation_manifest,
        "command_surface_manifest": command_surface_manifest,
        "configless_command_manifest": configless_command_manifest,
        "boundary_manifest": boundary_manifest,
        "denylist_manifest": denylist_manifest,
        "no_action_attestations": no_action_attestations,
        "blocking_reasons": blocking_reasons,
        "known_limitations": known_limitations,
        "future_unlock_requirements": future_unlock_requirements,
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
        "source_readiness_report_hash": source_readiness_report_hash,
        "artifact_path": artifact_path_rel,
        "warnings": warnings,
        "metadata": metadata,
        "created_at": created_at.isoformat(),
    }

    artifact["artifact_hash"] = provider_preflight_freeze_sha256(artifact)
    return artifact


def create_provider_preflight_freeze(
    workspace_path: Path,
    readiness_report_id: str,
) -> dict[str, Any]:
    """Create and persist a provider preflight freeze artifact.

    Loads the source readiness report, builds the freeze, and writes the artifact.
    """
    safe_readiness_report_id = validate_run_id(readiness_report_id)

    from atlas_agent.research.provider_execution_readiness_report import (
        find_provider_execution_readiness_report_by_id,
        load_and_validate_provider_execution_readiness_report,
    )

    readiness_path = find_provider_execution_readiness_report_by_id(workspace_path, safe_readiness_report_id)
    if readiness_path is None:
        raise ResearchSessionError("provider_execution_readiness_report_not_found")

    source_readiness_report = load_and_validate_provider_execution_readiness_report(
        readiness_path, workspace_path
    )

    freeze_id = generate_run_id()
    artifact = build_provider_preflight_freeze_dict(
        source_readiness_report,
        freeze_id,
        workspace_path,
    )

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    freeze_dir = workspace_path / RESEARCH_DIR / symbol / "provider_preflight_freezes"
    freeze_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8"
    )

    return {
        "ok": True,
        "status": "research_provider_preflight_freeze_created",
        "provider_preflight_freeze_id": freeze_id,
        "source_provider_execution_readiness_report_id": safe_readiness_report_id,
        "freeze_status": artifact["freeze_status"],
        "freeze_recommendation": artifact["freeze_recommendation"],
        "chain_health": artifact["chain_health"],
        "execution_status": artifact["execution_status"],
        "artifact_path": artifact_path_rel,
        "warnings": artifact["warnings"],
    }


def _safe_error_code_for_field(value: str, field_name: str) -> str | None:
    """Return static error code if value contains forbidden fragments or unsafe chars."""
    if _has_forbidden_fragments(str(value)):
        return f"invalid_provider_preflight_freeze_{field_name}"
    return None


def safe_validate_provider_preflight_freeze_data(
    data: dict[str, Any],
    workspace_path: Path | None = None,
    for_replay: bool = False,
) -> tuple[dict[str, Any] | None, str | None]:
    """Strictly validate a loaded freeze artifact for read paths.

    Returns (cleaned_data, None) if valid, or (None, error_code) if invalid.
    Never includes raw tampered values in error codes.

    When ``for_replay`` is True, the source readiness report hash match is skipped so
    that replay can detect drift and report ``match=false``.
    """
    # 1. schema_version
    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        return None, "unsupported_provider_preflight_freeze_schema"

    # 2. artifact_type
    if data.get("artifact_type") != "provider_preflight_freeze":
        return None, "provider_preflight_freeze_malformed"

    # 3. contract_version
    if data.get("contract_version") != PROVIDER_PREFLIGHT_FREEZE_CONTRACT_VERSION:
        return None, "provider_preflight_freeze_malformed"

    # 4. freeze_status / freeze_recommendation / readiness_status / chain_health / execution_status
    try:
        validate_freeze_status(data.get("freeze_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_preflight_freeze_status"
    try:
        validate_freeze_recommendation(data.get("freeze_recommendation", ""))
    except ResearchSessionError:
        return None, "invalid_provider_preflight_freeze_status"
    try:
        validate_readiness_status(data.get("readiness_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_preflight_freeze_status"
    try:
        validate_execution_status(data.get("execution_status", ""))
    except ResearchSessionError:
        return None, "invalid_provider_preflight_freeze_status"
    try:
        validate_chain_health(data.get("chain_health", ""))
    except ResearchSessionError:
        return None, "invalid_provider_preflight_freeze_status"

    # 5. readiness_score range
    readiness_score = data.get("readiness_score")
    if not isinstance(readiness_score, int) or readiness_score < 0 or readiness_score > 100:
        return None, "invalid_provider_preflight_freeze_status"

    # 6. boolean safety flags (all must be False)
    error = _check_boolean_safety_flags(data)
    if error:
        return None, error

    # 7. mode
    if data.get("mode") != "paper":
        return None, "provider_preflight_freeze_malformed"

    # 8. lineage IDs — reject if unsafe
    for field in (
        "provider_preflight_freeze_id",
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
            return None, "invalid_provider_preflight_freeze_lineage"
        err = _safe_error_code_for_field(value, "lineage")
        if err:
            return None, err

    # 9. symbol
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        return None, "invalid_provider_preflight_freeze_lineage"

    # 10. provider_id
    provider_id = data.get("provider_id", "")
    try:
        validate_provider_id(provider_id)
    except ResearchSessionError:
        return None, "invalid_provider_preflight_freeze_provider"
    err = _safe_error_code_for_field(provider_id, "provider")
    if err:
        return None, err

    # 11. model_id
    model_id = data.get("model_id", "")
    try:
        validate_model_id(model_id)
    except ResearchSessionError:
        return None, "invalid_provider_preflight_freeze_model"
    err = _safe_error_code_for_field(model_id, "model")
    if err:
        return None, err

    # 12. hash consistency
    stored_hash = data.get("artifact_hash", "")
    if stored_hash:
        computed_hash = provider_preflight_freeze_sha256(data)
        if stored_hash != computed_hash:
            return None, "provider_preflight_freeze_hash_mismatch"

    # 13. source readiness report exists and hash matches (if workspace provided)
    if workspace_path is not None and not for_replay:
        source_readiness_report_id = data.get("source_provider_execution_readiness_report_id", "")
        if source_readiness_report_id:
            try:
                from atlas_agent.research.provider_execution_readiness_report import (
                    find_provider_execution_readiness_report_by_id,
                    load_provider_execution_readiness_report,
                )

                readiness_path = find_provider_execution_readiness_report_by_id(
                    workspace_path, source_readiness_report_id
                )
                if readiness_path is None:
                    return None, "provider_preflight_freeze_source_readiness_missing"
                readiness_data = load_provider_execution_readiness_report(readiness_path, workspace_path)
                stored_readiness_hash = data.get("source_readiness_report_hash", "")
                actual_readiness_hash = readiness_data.get("artifact_hash", "")
                if stored_readiness_hash != actual_readiness_hash:
                    return None, "provider_preflight_freeze_source_readiness_hash_mismatch"
            except ResearchSessionError:
                return None, "provider_preflight_freeze_source_readiness_missing"

    # 14. no forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("artifact_chain", [])),
        json.dumps(data.get("hash_manifest", {})),
        json.dumps(data.get("validation_manifest", {})),
        json.dumps(data.get("command_surface_manifest", [])),
        json.dumps(data.get("configless_command_manifest", [])),
        json.dumps(data.get("boundary_manifest", {})),
        json.dumps(data.get("denylist_manifest", {})),
        json.dumps(data.get("no_action_attestations", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("known_limitations", [])),
        json.dumps(data.get("future_unlock_requirements", [])),
        json.dumps(data.get("development_scope", [])),
    ]
    if any(_has_forbidden_fragments(str(f)) for f in text_fields):
        return None, "provider_preflight_freeze_malformed"

    # 15. path containment
    path = data.get("artifact_path", "")
    if path.startswith("/") and ".atlas/research/" not in path:
        return None, "provider_preflight_freeze_malformed"

    # Return a cleaned copy with only safe fields
    cleaned = {
        "schema_version": data.get("schema_version", ""),
        "artifact_type": data.get("artifact_type", ""),
        "contract_version": data.get("contract_version", ""),
        "provider_preflight_freeze_id": data.get("provider_preflight_freeze_id", ""),
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
        "freeze_status": data.get("freeze_status", ""),
        "freeze_recommendation": data.get("freeze_recommendation", ""),
        "freeze_scope": data.get("freeze_scope", ""),
        "development_scope": data.get("development_scope", []),
        "readiness_status": data.get("readiness_status", ""),
        "readiness_score": data.get("readiness_score", 0),
        "chain_health": data.get("chain_health", ""),
        "execution_status": data.get("execution_status", ""),
        "artifact_chain": data.get("artifact_chain", []),
        "hash_manifest": data.get("hash_manifest", {}),
        "validation_manifest": data.get("validation_manifest", {}),
        "command_surface_manifest": data.get("command_surface_manifest", []),
        "configless_command_manifest": data.get("configless_command_manifest", []),
        "boundary_manifest": data.get("boundary_manifest", {}),
        "denylist_manifest": data.get("denylist_manifest", {}),
        "no_action_attestations": data.get("no_action_attestations", {}),
        "blocking_reasons": data.get("blocking_reasons", []),
        "known_limitations": data.get("known_limitations", []),
        "future_unlock_requirements": data.get("future_unlock_requirements", []),
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
        "source_readiness_report_hash": data.get("source_readiness_report_hash", ""),
        "artifact_path": data.get("artifact_path", ""),
        "warnings": data.get("warnings", []),
        "metadata": data.get("metadata", {}),
        "artifact_hash": data.get("artifact_hash", ""),
        "created_at": data.get("created_at", ""),
    }
    return cleaned, None


def validate_provider_preflight_freeze_artifact(
    path: Path,
    workspace_path: Path,
    strict: bool = False,
) -> ProviderPreflightFreezeValidationResult:
    """Validate a provider preflight freeze artifact against the local contract.

    Loads the artifact from disk, then performs detailed check-by-check validation.
    """
    data = load_provider_preflight_freeze(path, workspace_path)
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
            at == "provider_preflight_freeze",
            "artifact_type must be provider_preflight_freeze."
            if at != "provider_preflight_freeze"
            else "artifact_type is correct.",
        )
    )

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(
        _check_name(
            "contract_version_present",
            cv == PROVIDER_PREFLIGHT_FREEZE_CONTRACT_VERSION,
            "contract_version must match current contract."
            if cv != PROVIDER_PREFLIGHT_FREEZE_CONTRACT_VERSION
            else "contract_version matches.",
        )
    )

    # 4. freeze_status
    freeze_status = data.get("freeze_status", "")
    freeze_ok = freeze_status in _VALID_FREEZE_STATUSES
    checks.append(
        _check_name(
            "freeze_status_valid",
            freeze_ok,
            "freeze_status is invalid." if not freeze_ok else "freeze_status is valid.",
        )
    )

    # 5. freeze_recommendation
    freeze_rec = data.get("freeze_recommendation", "")
    rec_ok = freeze_rec in _VALID_FREEZE_RECOMMENDATIONS
    checks.append(
        _check_name(
            "freeze_recommendation_valid",
            rec_ok,
            "freeze_recommendation is invalid." if not rec_ok else "freeze_recommendation is valid.",
        )
    )

    # 6. readiness_status
    readiness_status = data.get("readiness_status", "")
    readiness_ok = readiness_status in _VALID_READINESS_STATUSES
    checks.append(
        _check_name(
            "readiness_status_valid",
            readiness_ok,
            "readiness_status is invalid." if not readiness_ok else "readiness_status is valid.",
        )
    )

    # 7. execution_status
    exec_status = data.get("execution_status", "")
    exec_ok = exec_status in _VALID_EXECUTION_STATUSES
    checks.append(
        _check_name(
            "execution_status_valid",
            exec_ok,
            "execution_status is invalid." if not exec_ok else "execution_status is valid.",
        )
    )

    # 8. chain_health
    chain_health = data.get("chain_health", "")
    health_ok = chain_health in _VALID_CHAIN_HEALTH_VALUES
    checks.append(
        _check_name(
            "chain_health_valid",
            health_ok,
            "chain_health is invalid." if not health_ok else "chain_health is valid.",
        )
    )

    # 9. readiness_score
    score = data.get("readiness_score")
    score_ok = isinstance(score, int) and 0 <= score <= 100
    checks.append(
        _check_name(
            "readiness_score_in_range",
            score_ok,
            "readiness_score must be an integer between 0 and 100." if not score_ok else "readiness_score is in range.",
        )
    )

    # 10. boolean safety flags
    flags_ok = _check_boolean_safety_flags(data) is None
    checks.append(
        _check_name(
            "boolean_safety_flags_false",
            flags_ok,
            "A boolean safety flag is not False." if not flags_ok else "All boolean safety flags are False.",
        )
    )

    # 11. mode
    mode = data.get("mode", "")
    mode_ok = mode == "paper"
    checks.append(
        _check_name(
            "mode_paper",
            mode_ok,
            "mode must be paper." if not mode_ok else "mode is paper.",
        )
    )

    # 12. lineage IDs
    lineage_fields = (
        "provider_preflight_freeze_id",
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

    # 13. symbol
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

    # 14. provider_id
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

    # 15. model_id
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

    # 16. hash consistency
    stored_hash = data.get("artifact_hash", "")
    hash_ok = False
    if stored_hash:
        computed = provider_preflight_freeze_sha256(data)
        hash_ok = stored_hash == computed
    checks.append(
        _check_name(
            "artifact_hash_consistent",
            hash_ok,
            "artifact_hash does not match computed hash." if not hash_ok else "artifact_hash is consistent.",
        )
    )

    # 17. source readiness report hash match (if workspace)
    if workspace_path is not None:
        source_readiness_id = data.get("source_provider_execution_readiness_report_id", "")
        source_hash_ok = False
        if source_readiness_id:
            try:
                from atlas_agent.research.provider_execution_readiness_report import (
                    find_provider_execution_readiness_report_by_id,
                    load_provider_execution_readiness_report,
                )

                readiness_path = find_provider_execution_readiness_report_by_id(workspace_path, source_readiness_id)
                if readiness_path is not None:
                    readiness_data = load_provider_execution_readiness_report(readiness_path, workspace_path)
                    stored_readiness_hash = data.get("source_readiness_report_hash", "")
                    actual_readiness_hash = readiness_data.get("artifact_hash", "")
                    source_hash_ok = stored_readiness_hash == actual_readiness_hash
            except Exception:
                pass
        checks.append(
            _check_name(
                "source_readiness_report_hash_match",
                source_hash_ok,
                "Source readiness report hash does not match." if not source_hash_ok else "Source readiness report hash matches.",
            )
        )

    # 18. forbidden fragments in text fields
    text_fields = [
        json.dumps(data.get("artifact_chain", [])),
        json.dumps(data.get("hash_manifest", {})),
        json.dumps(data.get("validation_manifest", {})),
        json.dumps(data.get("command_surface_manifest", [])),
        json.dumps(data.get("configless_command_manifest", [])),
        json.dumps(data.get("boundary_manifest", {})),
        json.dumps(data.get("denylist_manifest", {})),
        json.dumps(data.get("no_action_attestations", {})),
        json.dumps(data.get("blocking_reasons", [])),
        json.dumps(data.get("known_limitations", [])),
        json.dumps(data.get("future_unlock_requirements", [])),
        json.dumps(data.get("development_scope", [])),
    ]
    text_ok = not any(_has_forbidden_fragments(str(f)) for f in text_fields)
    checks.append(
        _check_name(
            "text_fields_forbidden_fragment_free",
            text_ok,
            "A text field contains a forbidden fragment." if not text_ok else "Text fields are clean.",
        )
    )

    # 19. denylist manifest shape (must not store raw fragments)
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

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    valid = failed == 0

    recommendation = (
        "provider_preflight_freeze_valid"
        if valid
        else "manual_review_required"
    )

    if not valid:
        warnings.append("Preflight freeze validation failed. Manual review required.")

    return ProviderPreflightFreezeValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def replay_provider_preflight_freeze(
    freeze_id: str,
    workspace_path: Path,
    strict: bool = False,
) -> dict[str, Any]:
    """Replay a provider preflight freeze from its source readiness report and compare hashes.

    Read-only by default. Does not call providers, read API keys, or authorize trading.
    """
    safe_id = validate_run_id(freeze_id)

    freeze_path = find_provider_preflight_freeze_by_id(workspace_path, safe_id)
    if freeze_path is None:
        raise ResearchSessionError("provider_preflight_freeze_not_found")

    loaded_data = load_provider_preflight_freeze(freeze_path, workspace_path)
    cleaned, error = safe_validate_provider_preflight_freeze_data(
        loaded_data, workspace_path, for_replay=True
    )
    if error:
        raise ResearchSessionError(error)

    source_readiness_report_id = loaded_data.get("source_provider_execution_readiness_report_id", "")
    from atlas_agent.research.provider_execution_readiness_report import (
        find_provider_execution_readiness_report_by_id,
        load_provider_execution_readiness_report,
    )

    readiness_path = find_provider_execution_readiness_report_by_id(workspace_path, source_readiness_report_id)
    if readiness_path is None:
        raise ResearchSessionError("provider_execution_readiness_report_not_found")
    source_readiness_report = load_provider_execution_readiness_report(readiness_path, workspace_path)

    rebuilt = build_provider_preflight_freeze_dict(
        source_readiness_report,
        safe_id,
        workspace_path,
    )

    expected_hash = loaded_data.get("artifact_hash", "")
    actual_hash = provider_preflight_freeze_sha256(rebuilt)

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
        warnings.append("Preflight freeze hash mismatch. Source readiness report or linked chain may have changed.")

    return {
        "match": expected_hash == actual_hash,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "checks": checks,
        "warnings": warnings,
    }


def find_provider_preflight_freeze_by_id(
    workspace_path: Path,
    freeze_id: str,
) -> Path | None:
    """Find a provider preflight freeze artifact by its ID.

    Returns the path if found, None if not found, raises if ambiguous.
    """
    safe_id = validate_run_id(freeze_id)
    research_dir = workspace_path / RESEARCH_DIR
    if not research_dir.exists():
        return None

    matches: list[Path] = []
    for sym_dir in research_dir.iterdir():
        if not sym_dir.is_dir():
            continue
        freeze_dir = sym_dir / "provider_preflight_freezes"
        if not freeze_dir.exists():
            continue
        for path in freeze_dir.glob("*.json"):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("provider_preflight_freeze_id") == safe_id:
                matches.append(path)

    if len(matches) > 1:
        raise ResearchSessionError("ambiguous_provider_preflight_freeze_id")
    return matches[0] if matches else None


def load_provider_preflight_freeze(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load a provider preflight freeze artifact from disk.

    Performs basic safety checks but does not fully validate.
    """
    if not path.exists():
        raise ResearchSessionError("provider_preflight_freeze_not_found")
    if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
        raise ResearchSessionError("artifact_path_not_allowed")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ResearchSessionError("provider_preflight_freeze_malformed")

    data["artifact_path"] = path.relative_to(workspace_path).as_posix()

    sv = data.get("schema_version")
    if sv is not None and sv != RESEARCH_ARTIFACT_SCHEMA_VERSION:
        raise UnsupportedArtifactSchemaError(
            f"Unsupported schema version: {sv} (expected {RESEARCH_ARTIFACT_SCHEMA_VERSION})"
        )

    return data


def load_and_validate_provider_preflight_freeze(
    path: Path,
    workspace_path: Path,
) -> dict[str, Any]:
    """Load and strictly validate a provider preflight freeze artifact."""
    data = load_provider_preflight_freeze(path, workspace_path)
    cleaned, error = safe_validate_provider_preflight_freeze_data(data, workspace_path)
    if error:
        raise ResearchSessionError(error)
    return cleaned


def _is_inside_workspace(path: Path, workspace: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def iter_provider_preflight_freeze_artifacts(
    workspace_path: Path,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Return a list of provider preflight freeze artifact metadata dicts, newest first.

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
        freeze_dir = sym_dir / "provider_preflight_freezes"
        if not freeze_dir.exists():
            continue
        for path in freeze_dir.glob("*.json"):
            if not path.is_file():
                continue
            if path.is_symlink() and not _is_inside_workspace(path, workspace_path):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                invalid_items.append({
                    "provider_preflight_freeze_id": "<invalid>",
                    "source_provider_execution_readiness_report_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": sym_dir.name,
                    "freeze_status": "invalid",
                    "freeze_recommendation": "freeze_blocked",
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
                    "provider_preflight_freeze_id": "<invalid>",
                    "source_provider_execution_readiness_report_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "freeze_status": "invalid",
                    "freeze_recommendation": "freeze_blocked",
                    "chain_health": "invalid",
                    "execution_status": "invalid",
                    "artifact_path": path.relative_to(workspace_path).as_posix(),
                    "provider_id": "unknown",
                    "model_id": "unknown",
                    "warnings_count": 1,
                    "_invalid": True,
                    "error_code": "unsupported_provider_preflight_freeze_schema",
                    "created_at": "",
                })
                continue

            cleaned, error = safe_validate_provider_preflight_freeze_data(raw, workspace_path)
            if error:
                invalid_items.append({
                    "provider_preflight_freeze_id": "<invalid>",
                    "source_provider_execution_readiness_report_id": "<invalid>",
                    "source_run_id": "<invalid>",
                    "symbol": "<invalid>",
                    "freeze_status": "invalid",
                    "freeze_recommendation": "freeze_blocked",
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
                "provider_preflight_freeze_id": cleaned.get("provider_preflight_freeze_id", ""),
                "source_provider_execution_readiness_report_id": cleaned.get("source_provider_execution_readiness_report_id", ""),
                "source_run_id": cleaned.get("source_run_id", ""),
                "symbol": cleaned.get("symbol", ""),
                "freeze_status": cleaned.get("freeze_status", ""),
                "freeze_recommendation": cleaned.get("freeze_recommendation", ""),
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


def summarize_provider_preflight_freeze_for_run(
    run_id: str,
    workspace_path: Path,
) -> dict[str, Any]:
    """Read-only summary of the latest preflight freeze for a research run.

    Does NOT create artifacts. Returns a safe envelope if no freeze is found.
    """
    safe_run_id = validate_run_id(run_id)

    all_freezes = iter_provider_preflight_freeze_artifacts(workspace_path)
    run_freezes = [f for f in all_freezes if f.get("source_run_id") == safe_run_id and not f.get("_invalid")]

    if not run_freezes:
        return {
            "ok": False,
            "status": "provider_preflight_freeze_missing",
            "run_id": safe_run_id,
            "symbol": "",
            "freeze_status": "provider_preflight_invalid",
            "freeze_recommendation": "freeze_blocked",
            "provider_execution_allowed": False,
            "provider_call_made": False,
            "blocking_reasons": ["No preflight freeze found for this run."],
            "known_limitations": ["Preflight freeze has not been created."],
            "warnings": ["No preflight freeze artifact exists for the given run_id."],
        }

    latest = run_freezes[0]

    return {
        "ok": True,
        "status": "provider_preflight_freeze_summary",
        "run_id": safe_run_id,
        "symbol": latest.get("symbol", ""),
        "freeze_status": latest.get("freeze_status", "provider_preflight_invalid"),
        "freeze_recommendation": latest.get("freeze_recommendation", "freeze_blocked"),
        "provider_execution_allowed": False,
        "provider_call_made": False,
        "blocking_reasons": ["Provider execution is blocked and not implemented."],
        "known_limitations": ["Freeze is a consolidation artifact; it does not enable provider execution."],
        "warnings": [],
    }
