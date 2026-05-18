"""LLM Provider Sandbox — local-only request contract scaffolding.

This module prepares bounded, local, replayable input contracts for future LLM
provider integration. It does NOT call any provider, network, or API. It does
NOT read API keys or secrets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.events.log import EventLogger, generate_run_id
from atlas_agent.research.sandbox_contracts import (
    CONTRACT_VERSION,
    FORBIDDEN_FRAGMENTS,
    MAX_CONTRACT_TEXT_CHARS,
    artifact_sha256,
    canonical_json_dumps,
    sanitize_contract_text,
    validate_contract_lineage_id,
    validate_contract_symbol,
)
from atlas_agent.research.session import (
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_DIR,
    ResearchSessionError,
    find_prompt_packet_by_id,
    load_prompt_packet,
    sanitize_symbol,
    validate_run_id,
)

MAX_SANDBOX_PAYLOAD_CHARS = MAX_CONTRACT_TEXT_CHARS


class LLMSandboxError(ResearchSessionError):
    pass


@dataclass(frozen=True)
class LLMSandboxRequest:
    sandbox_request_id: str
    prompt_packet_id: str
    source_run_id: str
    symbol: str
    mode: str
    provider: str
    request_payload: str
    system_boundary: dict[str, bool]
    explicit_boundaries: list[str]
    redaction_summary: dict[str, Any]
    warnings: list[str]
    artifact_path: str
    created_at: datetime
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMSandboxResponse:
    sandbox_response_id: str
    sandbox_request_id: str
    symbol: str
    mode: str
    provider: str
    response_payload: str
    safety_checks: list[dict[str, Any]]
    recommendation: str
    artifact_path: str
    created_at: datetime
    schema_version: str = RESEARCH_ARTIFACT_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMSandboxValidationResult:
    valid: bool
    checks: list[dict[str, Any]]
    recommendation: str
    warnings: list[str]


def _sanitize_sandbox_text(text: str) -> tuple[str, int]:
    """Redact forbidden fragments and return cleaned text plus redaction count."""
    cleaned = sanitize_contract_text(text, MAX_SANDBOX_PAYLOAD_CHARS)
    redacted_count = sum(1 for frag in FORBIDDEN_FRAGMENTS if frag in text)
    return cleaned, redacted_count


def _build_request_payload(prompt_packet: dict[str, Any]) -> tuple[str, int, bool]:
    """Build a bounded request payload from a prompt packet.

    Returns (payload, redacted_count, was_truncated).
    """
    user_context = prompt_packet.get("user_context", {})
    system_boundary = prompt_packet.get("system_boundary", {})
    allowed_uses = prompt_packet.get("allowed_uses", [])
    forbidden_uses = prompt_packet.get("forbidden_uses", [])

    parts: list[str] = []
    parts.append("=== SYSTEM BOUNDARY ===")
    for key, value in sorted(system_boundary.items()):
        parts.append(f"{key}: {value}")

    parts.append("")
    parts.append("=== ALLOWED USES ===")
    for use in allowed_uses:
        parts.append(f"- {use}")

    parts.append("")
    parts.append("=== FORBIDDEN USES ===")
    for use in forbidden_uses:
        parts.append(f"- {use}")

    parts.append("")
    parts.append("=== USER CONTEXT ===")
    for key, value in sorted(user_context.items()):
        parts.append(f"{key}: {value}")

    raw_payload = "\n".join(parts)
    cleaned_payload, redacted_count = _sanitize_sandbox_text(raw_payload)

    was_truncated = False
    if len(cleaned_payload) > MAX_SANDBOX_PAYLOAD_CHARS:
        cleaned_payload = cleaned_payload[:MAX_SANDBOX_PAYLOAD_CHARS]
        was_truncated = True

    return cleaned_payload, redacted_count, was_truncated


def _build_sandbox_request_dict(
    prompt_packet: dict[str, Any],
    safe_prompt_packet_id: str,
    sandbox_request_id: str,
) -> dict[str, Any]:
    """Build the sandbox request artifact dict in memory without writing to disk."""
    raw_symbol = prompt_packet.get("symbol", "")
    if not raw_symbol:
        raise ResearchSessionError("invalid_research_symbol")
    try:
        symbol = sanitize_symbol(raw_symbol)
    except Exception:
        raise ResearchSessionError("invalid_research_symbol")

    # Validate copied lineage fields before constructing any output or artifacts.
    loaded_prompt_packet_id = prompt_packet.get("prompt_packet_id", "")
    if not loaded_prompt_packet_id:
        raise ResearchSessionError("invalid_prompt_packet_id")
    try:
        validate_run_id(loaded_prompt_packet_id)
    except ResearchSessionError:
        raise ResearchSessionError("invalid_prompt_packet_id") from None

    source_run_id = prompt_packet.get("source_run_id", "")
    if not source_run_id:
        raise ResearchSessionError("invalid_source_run_id")
    try:
        validate_run_id(source_run_id)
    except ResearchSessionError:
        raise ResearchSessionError("invalid_source_run_id") from None

    created_at = datetime.now(UTC)
    request_payload, redacted_count, was_truncated = _build_request_payload(prompt_packet)

    system_boundary = {
        "paper_only": True,
        "analysis_only": True,
        "no_trading_advice": True,
        "no_live_trading_authorization": True,
        "no_broker_submit": True,
        "no_pending_orders": True,
        "no_approvals": True,
        "no_api_network_call": True,
        "no_financial_advice": True,
        "no_trading_signal_generation": True,
    }

    explicit_boundaries = [
        "This artifact is a local sandbox request only.",
        "No LLM provider is called.",
        "No network request is made.",
        "No API key is read.",
        "No broker is contacted.",
        "No order is generated.",
        "No approval is created.",
        "No live trading is authorized.",
    ]

    warnings = [
        "This is a deterministic local artifact. No LLM was consulted.",
        "Sandbox request is bounded and redacted; verify payload before any future provider use.",
    ]

    if was_truncated:
        warnings.append("Sandbox request payload was truncated to max length.")

    artifact_path_rel = f".atlas/research/{symbol}/sandbox_requests/{sandbox_request_id}.json"

    redaction_summary = {
        "redacted_fragments_count": redacted_count,
        "truncated": was_truncated,
    }

    artifact: dict[str, Any] = {
        "schema_version": RESEARCH_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "sandbox_request",
        "contract_version": CONTRACT_VERSION,
        "sandbox_request_id": sandbox_request_id,
        "prompt_packet_id": safe_prompt_packet_id,
        "source_run_id": source_run_id,
        "created_at": created_at.isoformat(),
        "symbol": symbol,
        "mode": "paper",
        "provider": "llm-sandbox",
        "request_payload": request_payload,
        "system_boundary": system_boundary,
        "explicit_boundaries": explicit_boundaries,
        "redaction_summary": redaction_summary,
        "warnings": warnings,
        "metadata": {
            "max_payload_chars": MAX_SANDBOX_PAYLOAD_CHARS,
            "source_schema_version": prompt_packet.get("schema_version", ""),
        },
        "artifact_path": artifact_path_rel,
    }

    artifact["content_hash"] = artifact_sha256(artifact)
    return artifact


def build_llm_sandbox_request_from_prompt_packet(
    workspace_path: Path,
    prompt_packet_id: str,
    event_logger: EventLogger | None = None,
) -> dict[str, Any]:
    """Build a local LLM sandbox request artifact from an existing prompt packet.

    No network. No API keys. No provider SDKs.
    """
    safe_prompt_packet_id = validate_run_id(prompt_packet_id)

    packet_path = find_prompt_packet_by_id(workspace_path, safe_prompt_packet_id)
    if packet_path is None:
        raise ResearchSessionError("prompt_packet_not_found")

    prompt_packet = load_prompt_packet(packet_path, workspace_path)

    sandbox_request_id = generate_run_id()
    artifact = _build_sandbox_request_dict(prompt_packet, safe_prompt_packet_id, sandbox_request_id)

    symbol = artifact["symbol"]
    artifact_path_rel = artifact["artifact_path"]
    artifact_path = workspace_path / artifact_path_rel
    sandbox_dir = workspace_path / RESEARCH_DIR / symbol / "sandbox_requests"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    if event_logger is not None:
        payload = {
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": safe_prompt_packet_id,
            "source_run_id": artifact["source_run_id"],
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "artifact_path": artifact_path_rel,
        }
        event_logger.log_event("research_sandbox_request_created", payload)

    return artifact


def validate_llm_sandbox_response(
    response_payload: str,
    source_sandbox_request_id: str,
) -> LLMSandboxValidationResult:
    """Validate a hypothetical LLM sandbox response payload locally.

    No network. No API keys.
    """
    checks: list[dict[str, Any]] = []
    warnings_list: list[str] = []

    # Check 1: payload not empty
    checks.append({
        "check": "response_payload_not_empty",
        "passed": bool(response_payload.strip()),
    })

    # Check 2: no forbidden fragments
    has_forbidden = any(frag in response_payload for frag in FORBIDDEN_FRAGMENTS)
    checks.append({
        "check": "no_forbidden_fragments",
        "passed": not has_forbidden,
    })

    # Check 3: bounded length
    checks.append({
        "check": "response_bounded",
        "passed": len(response_payload) <= MAX_SANDBOX_PAYLOAD_CHARS,
    })

    # Check 4: no live trading authorization language
    lower = response_payload.lower()
    live_auth_keywords = ["authorize live", "enable live trading", "submit live order", "place live order"]
    has_live_auth = any(kw in lower for kw in live_auth_keywords)
    checks.append({
        "check": "no_live_authorization_language",
        "passed": not has_live_auth,
    })

    all_passed = all(c["passed"] for c in checks)
    recommendation = "sandbox_response_valid" if all_passed else "manual_review_required"

    if not all_passed:
        warnings_list.append("Sandbox response validation failed one or more safety checks.")

    return LLMSandboxValidationResult(
        valid=all_passed,
        checks=checks,
        recommendation=recommendation,
        warnings=warnings_list,
    )


def sanitize_llm_sandbox_payload(text: str) -> str:
    """Sanitize a sandbox payload by redacting forbidden fragments."""
    cleaned, _ = _sanitize_sandbox_text(text)
    return cleaned
