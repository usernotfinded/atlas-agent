"""Sandbox contract helpers — deterministic hashing, validation, and sanitization.

No network. No API keys. No provider SDKs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any



CONTRACT_VERSION = "research_sandbox_contract_v1"

FORBIDDEN_FRAGMENTS = (
    "/Users/",
    "/private/var/",
    "Authorization",
    "Bearer",
    "APCA",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "API_KEY",
    "sk-",
    "broker.example.com",
)

MAX_CONTRACT_TEXT_CHARS = 12000

REQUIRED_SANDBOX_BOUNDARY_KEYS = {
    "paper_only",
    "analysis_only",
    "no_trading_advice",
    "no_live_trading_authorization",
    "no_broker_submit",
    "no_pending_orders",
    "no_approvals",
    "no_api_network_call",
    "no_financial_advice",
    "no_trading_signal_generation",
}

LINEAGE_ID_FIELDS = {
    "run_id",
    "source_run_id",
    "prompt_packet_id",
    "source_prompt_packet_id",
    "sandbox_request_id",
    "source_sandbox_request_id",
    "provider_response_id",
    "response_review_id",
    "dossier_id",
}


@dataclass(frozen=True)
class SandboxValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


@dataclass(frozen=True)
class ProviderResponseValidationResult:
    valid: bool
    passed_checks: int
    failed_checks: int
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def canonical_json_dumps(data: dict[str, Any]) -> str:
    """Return deterministic, sorted JSON with no extra whitespace."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def artifact_sha256(data: dict[str, Any]) -> str:
    """Return SHA-256 hex digest of canonical JSON, excluding volatile/hash fields."""
    copy = {k: v for k, v in data.items() if k not in ("content_hash", "artifact_hash", "created_at")}
    canonical = canonical_json_dumps(copy)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_name(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "message": message}


def _has_forbidden_fragments(value: str) -> bool:
    return any(frag in value for frag in FORBIDDEN_FRAGMENTS)


def sanitize_contract_text(value: str, max_chars: int = MAX_CONTRACT_TEXT_CHARS) -> str:
    """Redact forbidden fragments and bound length."""
    if not isinstance(value, str):
        value = str(value)
    cleaned = value
    for frag in FORBIDDEN_FRAGMENTS:
        cleaned = cleaned.replace(frag, "<redacted>")
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
    return cleaned


def validate_contract_lineage_id(value: str, field_name: str) -> str:
    """Validate a lineage ID strictly. Fail closed. Never echo the value."""
    from atlas_agent.research.session import ResearchSessionError, validate_run_id

    if not value:
        raise ResearchSessionError(f"invalid_{field_name}")
    try:
        validate_run_id(value)
    except ResearchSessionError:
        raise ResearchSessionError(f"invalid_{field_name}") from None
    return value


def validate_contract_symbol(value: str) -> str:
    """Validate and sanitize a contract symbol."""
    from atlas_agent.research.session import (
        InvalidResearchSymbolError,
        ResearchSessionError,
        sanitize_symbol,
    )

    if not value:
        raise ResearchSessionError("invalid_contract_symbol")
    try:
        return sanitize_symbol(value)
    except InvalidResearchSymbolError:
        raise ResearchSessionError("invalid_contract_symbol") from None


def validate_sandbox_request_artifact(data: dict[str, Any]) -> SandboxValidationResult:
    """Validate a sandbox request artifact against the local contract."""
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    # 1. schema_version
    sv = data.get("schema_version")
    checks.append(_check_name(
        "schema_version_supported",
        sv == "1",
        "Schema version must be 1." if sv != "1" else "Schema version is supported.",
    ))

    # 2. artifact_type
    at = data.get("artifact_type")
    checks.append(_check_name(
        "artifact_type_correct",
        at == "sandbox_request",
        "artifact_type must be sandbox_request." if at != "sandbox_request" else "artifact_type is correct.",
    ))

    # 3. contract_version
    cv = data.get("contract_version")
    checks.append(_check_name(
        "contract_version_present",
        cv == CONTRACT_VERSION,
        "contract_version must match current contract." if cv != CONTRACT_VERSION else "contract_version matches.",
    ))

    # 4. mode = paper
    mode = data.get("mode")
    checks.append(_check_name(
        "mode_is_paper",
        mode == "paper",
        "mode must be paper." if mode != "paper" else "mode is paper.",
    ))

    # 5. provider is local/sandbox
    provider = data.get("provider")
    checks.append(_check_name(
        "provider_is_local",
        provider in ("llm-sandbox", "external-local-import"),
        "provider must be a local sandbox." if provider not in ("llm-sandbox", "external-local-import") else "provider is local.",
    ))

    # 6. lineage IDs
    from atlas_agent.research.session import ResearchSessionError

    lineage_ok = True
    for field in ("sandbox_request_id", "prompt_packet_id", "source_run_id"):
        value = data.get(field, "")
        try:
            validate_contract_lineage_id(value, field)
        except ResearchSessionError:
            lineage_ok = False
    checks.append(_check_name(
        "lineage_ids_valid",
        lineage_ok,
        "Lineage IDs contain unsafe characters." if not lineage_ok else "Lineage IDs are valid.",
    ))

    # 7. symbol
    symbol_ok = True
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        symbol_ok = False
    checks.append(_check_name(
        "symbol_valid",
        symbol_ok,
        "Symbol is invalid." if not symbol_ok else "Symbol is valid.",
    ))

    # 8. system_boundary keys
    sb = data.get("system_boundary", {})
    sb_keys_ok = REQUIRED_SANDBOX_BOUNDARY_KEYS.issubset(set(sb.keys()))
    checks.append(_check_name(
        "system_boundary_complete",
        sb_keys_ok,
        "system_boundary is missing required keys." if not sb_keys_ok else "system_boundary is complete.",
    ))

    # 9. explicit_boundaries present
    eb = data.get("explicit_boundaries", [])
    eb_ok = isinstance(eb, list) and len(eb) > 0
    checks.append(_check_name(
        "explicit_boundaries_present",
        eb_ok,
        "explicit_boundaries must be a non-empty list." if not eb_ok else "explicit_boundaries are present.",
    ))

    # 10. request_payload no forbidden fragments
    payload = data.get("request_payload", "")
    payload_forbidden = _has_forbidden_fragments(payload)
    checks.append(_check_name(
        "request_payload_safe",
        not payload_forbidden,
        "request_payload contains forbidden fragments." if payload_forbidden else "request_payload is safe.",
    ))

    # 11. artifact_path containment (workspace-relative, not absolute outside)
    path = data.get("artifact_path", "")
    path_ok = not path.startswith("/") or ".atlas/research/" in path
    checks.append(_check_name(
        "artifact_path_contained",
        path_ok,
        "artifact_path is not workspace-relative." if not path_ok else "artifact_path is contained.",
    ))

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    valid = failed == 0
    recommendation = "sandbox_request_valid" if valid else "manual_review_required"
    if not valid:
        warnings.append("Sandbox request validation failed one or more safety checks.")

    return SandboxValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )


def validate_external_provider_response_payload(data: dict[str, Any]) -> ProviderResponseValidationResult:
    """Validate an externally-imported provider response payload."""
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    # 1. schema_version
    sv = data.get("schema_version")
    checks.append(_check_name(
        "schema_version_supported",
        sv == "1",
        "Schema version must be 1." if sv != "1" else "Schema version is supported.",
    ))

    # 2. artifact_type
    at = data.get("artifact_type")
    checks.append(_check_name(
        "artifact_type_correct",
        at == "provider_response",
        "artifact_type must be provider_response." if at != "provider_response" else "artifact_type is correct.",
    ))

    # 3. mode = paper
    mode = data.get("mode")
    checks.append(_check_name(
        "mode_is_paper",
        mode == "paper",
        "mode must be paper." if mode != "paper" else "mode is paper.",
    ))

    # 4. provider state
    provider = data.get("provider")
    checks.append(_check_name(
        "provider_is_imported_local",
        provider == "external-local-import",
        "provider must be external-local-import." if provider != "external-local-import" else "provider is external-local-import.",
    ))

    # 5. provider_status
    status = data.get("provider_status")
    checks.append(_check_name(
        "provider_status_untrusted",
        status == "imported_untrusted",
        "provider_status must be imported_untrusted." if status != "imported_untrusted" else "provider_status is imported_untrusted.",
    ))

    # 6. lineage IDs
    from atlas_agent.research.session import ResearchSessionError

    lineage_ok = True
    for field in ("provider_response_id", "source_sandbox_request_id", "source_prompt_packet_id", "source_run_id"):
        value = data.get(field, "")
        try:
            validate_contract_lineage_id(value, field)
        except ResearchSessionError:
            lineage_ok = False
    checks.append(_check_name(
        "lineage_ids_valid",
        lineage_ok,
        "Lineage IDs contain unsafe characters." if not lineage_ok else "Lineage IDs are valid.",
    ))

    # 7. symbol
    symbol_ok = True
    try:
        validate_contract_symbol(data.get("symbol", ""))
    except ResearchSessionError:
        symbol_ok = False
    checks.append(_check_name(
        "symbol_valid",
        symbol_ok,
        "Symbol is invalid." if not symbol_ok else "Symbol is valid.",
    ))

    # 8. response summary safe
    summary = data.get("response_summary", "")
    summary_forbidden = _has_forbidden_fragments(summary)
    checks.append(_check_name(
        "response_summary_safe",
        not summary_forbidden,
        "response_summary contains forbidden fragments." if summary_forbidden else "response_summary is safe.",
    ))

    # 9. response sections safe
    sections = data.get("response_sections", [])
    sections_ok = isinstance(sections, list)
    sections_forbidden = False
    if sections_ok:
        for sec in sections:
            if isinstance(sec, dict):
                text = str(sec.get("content", ""))
                if _has_forbidden_fragments(text):
                    sections_forbidden = True
                    break
    checks.append(_check_name(
        "response_sections_safe",
        not sections_forbidden,
        "response_sections contain forbidden fragments." if sections_forbidden else "response_sections are safe.",
    ))

    # 10. recommendation safe
    rec = data.get("recommendation", "")
    disallowed_recs = {"approved", "trade", "buy", "sell", "execute", "submit", "authorization"}
    rec_ok = rec not in disallowed_recs
    checks.append(_check_name(
        "recommendation_safe",
        rec_ok,
        "recommendation contains disallowed value." if not rec_ok else "recommendation is safe.",
    ))

    # 11. artifact_path containment
    path = data.get("artifact_path", "")
    path_ok = not path.startswith("/") or ".atlas/research/" in path
    checks.append(_check_name(
        "artifact_path_contained",
        path_ok,
        "artifact_path is not workspace-relative." if not path_ok else "artifact_path is contained.",
    ))

    passed = sum(1 for c in checks if c["passed"])
    failed = len(checks) - passed
    valid = failed == 0
    recommendation = "provider_response_review_required" if valid else "manual_review_required"
    if not valid:
        warnings.append("Provider response validation failed one or more safety checks.")

    return ProviderResponseValidationResult(
        valid=valid,
        passed_checks=passed,
        failed_checks=failed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings,
    )
