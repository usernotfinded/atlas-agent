"""Operator approval gate engine (CAND-008) — evidence-only, simulated-only.

This module validates upstream CAND-004/CAND-005/CAND-006/CAND-007 artifacts by
projection and CAND-008-owned static fixtures by closed schema, then evaluates a
strict fail-closed gate sequence. It performs no network calls, loads no
credentials, and instantiates no trading or risk objects.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal


APPROVED_FINAL_STATUSES = (
    "not_evaluated",
    "blocked",
    "upstream_evidence_blocked",
    "runtime_envelope_blocked",
    "operator_identity_blocked",
    "approval_policy_blocked",
    "kill_switch_observation_blocked",
    "operator_acknowledgment_blocked",
    "audit_policy_blocked",
    "operator_gate_synthesized",
    "operator_gate_recorded",
)

GATE_SEQUENCE = (
    "schema_preflight",
    "cand004_projection_gate",
    "cand005_projection_gate",
    "cand006_projection_gate",
    "cand007_projection_gate",
    "cross_artifact_correlation_gate",
    "operator_identity_gate",
    "approval_policy_gate",
    "kill_switch_observation_gate",
    "operator_acknowledgment_gate",
    "audit_policy_gate",
    "approval_gate_synthesis",
    "artifact_recording_gate",
)

EVIDENCE_ONLY_DISCLAIMER = (
    "Operator approval gate evaluation (CAND-008) — evidence-only and simulated-only. "
    "operator_gate_recorded is evidence-recording status only. "
    "It is not live readiness, not trading safety, not profitability evidence, "
    "not real human approval to trade, and not permission to submit orders."
)

CANDIDATE_CHAIN = (
    "CAND-001",
    "CAND-002",
    "CAND-003",
    "CAND-004",
    "CAND-005",
    "CAND-006",
    "CAND-007",
    "CAND-008",
)

ARTIFACT_TYPE = "operator_approval_gate"
SCHEMA_VERSION = "operator-approval-gate.v1"
MODE = "evidence_only"
CANDIDATE = "CAND-008"

_JSON_ARTIFACT_NAME = "operator-approval-gate.json"
_MARKDOWN_ARTIFACT_NAME = "operator-approval-gate-report.md"

_TRADING_QUALITY_GATE_ARTIFACT_TYPE = "trading_quality_gate"
_TRADING_QUALITY_GATE_SCHEMA_VERSIONS = ("trading-quality-gate.v1", 1, "1")
_SHADOW_LIVE_COMPARISON_ARTIFACT_TYPE = "shadow_live_comparison"
_SHADOW_LIVE_COMPARISON_SCHEMA_VERSION = "shadow-live-comparison.v1"
_GATED_SUBMIT_CONFORMANCE_ARTIFACT_TYPE = "gated_submit_conformance"
_GATED_SUBMIT_CONFORMANCE_SCHEMA_VERSION = "gated-submit-conformance.v1"
_RUNTIME_READINESS_ENVELOPE_ARTIFACT_TYPE = "runtime_readiness_envelope"
_RUNTIME_READINESS_ENVELOPE_SCHEMA_VERSION = "runtime-readiness-envelope.v1"

_OPERATOR_IDENTITY_ARTIFACT_TYPE = "operator_identity_fixture"
_OPERATOR_IDENTITY_SCHEMA_VERSION = "operator-identity-fixture.v1"
_APPROVAL_POLICY_ARTIFACT_TYPE = "approval_policy_fixture"
_APPROVAL_POLICY_SCHEMA_VERSION = "approval-policy-fixture.v1"
_KILL_SWITCH_OBSERVATION_ARTIFACT_TYPE = "kill_switch_observation_fixture"
_KILL_SWITCH_OBSERVATION_SCHEMA_VERSION = "kill-switch-observation-fixture.v1"
_OPERATOR_ACKNOWLEDGMENT_ARTIFACT_TYPE = "operator_acknowledgment_fixture"
_OPERATOR_ACKNOWLEDGMENT_SCHEMA_VERSION = "operator-acknowledgment-fixture.v1"
_AUDIT_POLICY_ARTIFACT_TYPE = "audit_policy_fixture"
_AUDIT_POLICY_SCHEMA_VERSION = "audit-policy-fixture.v1"

_INPUT_LABELS = (
    "quality_gate",
    "shadow_comparison",
    "submit_conformance",
    "readiness_envelope",
    "operator_identity",
    "approval_policy",
    "kill_switch_observation",
    "operator_acknowledgment",
    "audit_policy",
)

_MAX_EVIDENCE_AGE_HOURS = 24.0

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "credential",
    "private_key",
    "auth_header",
    "authorization",
}

_SECRET_VALUE_PATTERNS = (
    "bearer ",
    "sk-",
    "ghp_",
    "akia",
    ".env",
    ".env.atlas",
)

_ENDPOINT_KEYS = {
    "endpoint",
    "url",
    "base_url",
    "api_url",
    "websocket_url",
    "host",
    "headers",
    "auth",
    "authorization",
}

_URL_PROTOCOL_PATTERNS = (
    "http://",
    "https://",
    "ws://",
    "wss://",
)

_FORBIDDEN_FIXTURE_KEYS = {
    "account",
    "account_id",
    "broker",
    "broker_id",
    "provider",
    "api_key",
    "token",
    "secret",
    "credential",
    "client_order_id",
    "broker_order_id",
    "leverage",
    "metadata",
    "headers",
    "auth",
    "phone",
    "phone_number",
    "email",
    "legal_identity",
    "signature",
}

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,23}$")

_CANONICAL_ACKNOWLEDGMENT_TEXT = (
    "I acknowledge that this operator approval gate (CAND-008) is evidence-only, "
    "simulated-only, and non-executing. It does not authorize live trading, live "
    "submit, real order submission, or unattended operation. It does not certify any "
    "broker, guarantee profitability, or eliminate trading risk. The review is a "
    "local artifact for a hypothetical future supervised evaluation only, with no "
    "execution implied."
)

_CAND007_REQUIRED_ASSERTIONS = {
    "live_submit_forbidden",
    "human_approval_required",
    "kill_switch_required",
    "risk_gate_required",
    "audit_recording_required",
    "broker_manifest_required",
    "operator_policy_fail_closed",
    "all_upstream_statuses_accepted",
    "no_credentials_in_fixtures",
    "no_endpoints_in_fixtures",
    "no_account_ids_in_fixtures",
    "cand006_transmission_blocked",
}


class OperatorApprovalGateValidationError(Exception):
    """Raised when a fixture or input fails closed-schema or projection validation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    status: Literal["pass", "fail", "not_run"]
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status,
            "reason": self.reason,
            "details": self.details,
        }


@dataclass(frozen=True)
class OperatorApprovalGateInputs:
    quality_gate_path: Path
    shadow_comparison_path: Path
    submit_conformance_path: Path
    readiness_envelope_path: Path
    operator_identity_path: Path
    approval_policy_path: Path
    kill_switch_observation_path: Path
    operator_acknowledgment_path: Path
    audit_policy_path: Path
    output_dir: Path | None
    as_of: str


@dataclass(frozen=True)
class OperatorApprovalGateReport:
    artifact_type: str
    schema_version: str
    candidate: str
    mode: str
    status: str
    exit_code: int
    evaluation_id: str
    as_of: str
    run_id: str | None
    symbol: str | None
    candidate_chain: tuple[str, ...]
    gate_sequence: tuple[str, ...]
    gates: tuple[GateResult, ...]
    input_artifacts: dict[str, str | None]
    input_paths: dict[str, Path]
    input_fingerprints: dict[str, str]
    input_digest: str
    approval_gate_digest: str
    upstream_summaries: dict[str, Any]
    operator_summary: dict[str, Any]
    approval_policy_summary: dict[str, Any]
    kill_switch_observation_summary: dict[str, Any]
    acknowledgment_summary: dict[str, Any]
    audit_policy_summary: dict[str, Any]
    approval_gate_assertions: dict[str, bool]
    blockers: list[str]
    recording: dict[str, Any]
    disclaimer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "candidate": self.candidate,
            "mode": self.mode,
            "status": self.status,
            "exit_code": self.exit_code,
            "evaluation_id": self.evaluation_id,
            "as_of": self.as_of,
            "run_id": self.run_id,
            "symbol": self.symbol,
            "candidate_chain": list(self.candidate_chain),
            "gate_sequence": list(self.gate_sequence),
            "gates": [g.to_dict() for g in self.gates],
            "input_artifacts": self.input_artifacts,
            "input_paths": {label: str(path) for label, path in self.input_paths.items()},
            "input_fingerprints": self.input_fingerprints,
            "input_digest": self.input_digest,
            "approval_gate_digest": self.approval_gate_digest,
            "upstream_summaries": self.upstream_summaries,
            "operator_summary": self.operator_summary,
            "approval_policy_summary": self.approval_policy_summary,
            "kill_switch_observation_summary": self.kill_switch_observation_summary,
            "acknowledgment_summary": self.acknowledgment_summary,
            "audit_policy_summary": self.audit_policy_summary,
            "approval_gate_assertions": self.approval_gate_assertions,
            "blockers": self.blockers,
            "recording": self.recording,
            "disclaimer": self.disclaimer,
        }


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 JSON bytes for fingerprinting."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def fingerprint_json(value: Any) -> str:
    """Return a stable sha256 fingerprint string for a JSON-serializable value."""
    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"sha256:{digest}"


def _format_utc_timestamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_timestamp(value: str) -> datetime | None:
    """Parse an ISO timestamp, returning a UTC datetime or None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    candidate = text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        return None
    return parsed.astimezone(timezone.utc)


def parse_as_of_utc(value: str) -> str:
    """Parse and normalize an ISO-8601 UTC timestamp string."""
    if not isinstance(value, str):
        raise OperatorApprovalGateValidationError("as_of is not a string")
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise OperatorApprovalGateValidationError(
            f"as_of is not a valid ISO-8601 UTC timestamp: {value!r}"
        )
    return _format_utc_timestamp(parsed)


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise OperatorApprovalGateValidationError(f"{name} must be a string")
    return value


def _require_exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise OperatorApprovalGateValidationError(
            f"{label} contains unknown keys: {sorted(unknown)}"
        )


def _require_nonempty_bounded_id(value: str, name: str) -> None:
    if not value:
        raise OperatorApprovalGateValidationError(f"{name} must be non-empty")
    if len(value) > 128:
        raise OperatorApprovalGateValidationError(f"{name} exceeds 128 characters")
    if not _ID_RE.match(value):
        raise OperatorApprovalGateValidationError(f"{name} contains invalid characters")


def _secret_value_match(lower_value: str, pattern: str) -> bool:
    """Return True if ``pattern`` appears as a secret-like token in the value."""
    return re.search(r"(?:^|\W)" + re.escape(pattern), lower_value) is not None


def _universal_reject_scan(
    obj: Any, path: str = "", *, include_forbidden_keys: bool = True
) -> list[str]:
    """Return secret/endpoint/URL findings in a parsed JSON object."""
    findings: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = key.lower()
            if key_lower in _SECRET_KEYS:
                findings.append(f"secret-like key at {path}: {key}")
            if key_lower in _ENDPOINT_KEYS:
                findings.append(f"endpoint-like key at {path}: {key}")
            if include_forbidden_keys and key_lower in _FORBIDDEN_FIXTURE_KEYS:
                findings.append(f"forbidden key at {path}: {key}")
            for pattern in _SECRET_VALUE_PATTERNS:
                if _secret_value_match(key_lower, pattern):
                    findings.append(f"secret-like key fragment at {path}: {key}")
            for pattern in _URL_PROTOCOL_PATTERNS:
                if _secret_value_match(key_lower, pattern):
                    findings.append(f"url-like key fragment at {path}: {key}")
            findings.extend(
                _universal_reject_scan(
                    value,
                    f"{path}.{key}" if path else key,
                    include_forbidden_keys=include_forbidden_keys,
                )
            )
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            findings.extend(
                _universal_reject_scan(
                    value,
                    f"{path}[{idx}]",
                    include_forbidden_keys=include_forbidden_keys,
                )
            )
    elif isinstance(obj, str):
        lower = obj.lower()
        for pattern in _SECRET_VALUE_PATTERNS:
            if _secret_value_match(lower, pattern):
                findings.append(f"secret-like value at {path}: {pattern!r}")
        for pattern in _URL_PROTOCOL_PATTERNS:
            if _secret_value_match(lower, pattern):
                findings.append(f"url protocol value at {path}: {pattern!r}")
    return findings


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    """Load a JSON object from a path, rejecting non-objects and NaN/Infinity."""
    if not path.is_file():
        raise OperatorApprovalGateValidationError(f"{label} file not found: {path.name}")
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise OperatorApprovalGateValidationError(f"failed to read {label}: {exc}") from None
    if not text.strip():
        raise OperatorApprovalGateValidationError(f"{label} file is empty")
    try:
        data = json.loads(text, parse_constant=lambda c: c)
    except json.JSONDecodeError as exc:
        raise OperatorApprovalGateValidationError(f"{label} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise OperatorApprovalGateValidationError(f"{label} is not a JSON object")
    raw_text = text.lower()
    for constant in ("nan", "infinity", "-infinity"):
        if constant in raw_text:
            raise OperatorApprovalGateValidationError(
                f"{label} contains forbidden JSON constant: {constant}"
            )
    return data


def _compute_acknowledgment_digest() -> str:
    digest = hashlib.sha256(_CANONICAL_ACKNOWLEDGMENT_TEXT.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _input_fingerprints(normalized: dict[str, Any]) -> dict[str, str]:
    return {label: fingerprint_json(value) for label, value in normalized.items()}


def _compute_input_digest(as_of: str, fingerprints: dict[str, str]) -> str:
    payload = {"as_of": as_of}
    for label in _INPUT_LABELS:
        payload[label] = fingerprints[label]
    return fingerprint_json(payload)


def _compute_approval_gate_digest(
    as_of: str,
    fingerprints: dict[str, str],
    upstream_summaries: dict[str, Any],
    approval_gate_assertions: dict[str, bool],
) -> str:
    payload = {
        "as_of": as_of,
        "fingerprints": {label: fingerprints.get(label, "") for label in _INPUT_LABELS},
        "upstream_summaries": upstream_summaries,
        "approval_gate_assertions": approval_gate_assertions,
    }
    return fingerprint_json(payload)


def _evaluation_id(input_digest: str) -> str:
    return f"oag-{input_digest.replace('sha256:', '')[:24]}"


def _redact_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.name


def _parse_or_fail(value: str, label: str) -> datetime:
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise OperatorApprovalGateValidationError(
            f"{label} is not a valid ISO-8601 UTC timestamp"
        )
    return parsed


def _validate_quality_gate(data: dict[str, Any]) -> dict[str, Any]:
    """Project CAND-004 to accepted keys and normalize for downstream gates."""
    artifact_type = _require_string(data.get("artifact_type"), "quality_gate.artifact_type")
    schema_version = data.get("schema_version")
    mode = _require_string(data.get("mode"), "quality_gate.mode")
    run_id = _require_string(data.get("run_id"), "quality_gate.run_id")
    symbol = _require_string(data.get("symbol"), "quality_gate.symbol")
    quality_state = _require_string(data.get("quality_state"), "quality_gate.quality_state")
    blockers = data.get("blockers")

    if artifact_type != _TRADING_QUALITY_GATE_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("quality_gate artifact_type mismatch")
    if schema_version not in _TRADING_QUALITY_GATE_SCHEMA_VERSIONS:
        raise OperatorApprovalGateValidationError("quality_gate schema_version mismatch")
    if not isinstance(blockers, list):
        raise OperatorApprovalGateValidationError("quality_gate blockers must be a list")

    return {
        "artifact_type": artifact_type,
        "schema_version": str(schema_version),
        "mode": mode,
        "run_id": run_id,
        "symbol": symbol,
        "quality_state": quality_state,
        "blockers": blockers,
    }


def _validate_shadow_comparison(data: dict[str, Any]) -> dict[str, Any]:
    """Project CAND-005 to accepted keys and normalize for downstream gates."""
    artifact_type = _require_string(
        data.get("artifact_type"), "shadow_comparison.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "shadow_comparison.schema_version"
    )
    run_id = _require_string(data.get("run_id"), "shadow_comparison.run_id")
    symbol = _require_string(data.get("symbol"), "shadow_comparison.symbol")
    quality_state = _require_string(
        data.get("quality_state"), "shadow_comparison.quality_state"
    )
    status = _require_string(data.get("status"), "shadow_comparison.status")
    freshness_assessment = data.get("freshness_assessment")
    blockers = data.get("blockers")

    if artifact_type != _SHADOW_LIVE_COMPARISON_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("shadow_comparison artifact_type mismatch")
    if schema_version != _SHADOW_LIVE_COMPARISON_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("shadow_comparison schema_version mismatch")
    if not isinstance(freshness_assessment, dict):
        raise OperatorApprovalGateValidationError(
            "shadow_comparison freshness_assessment must be an object"
        )
    if not isinstance(blockers, list):
        raise OperatorApprovalGateValidationError("shadow_comparison blockers must be a list")

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "run_id": run_id,
        "symbol": symbol,
        "quality_state": quality_state,
        "status": status,
        "freshness_assessment": freshness_assessment,
        "blockers": blockers,
    }


def _validate_submit_conformance(
    data: dict[str, Any], cand008_as_of: str
) -> dict[str, Any]:
    """Project CAND-006 to accepted keys and validate freshness."""
    artifact_type = _require_string(
        data.get("artifact_type"), "submit_conformance.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "submit_conformance.schema_version"
    )
    candidate = _require_string(data.get("candidate"), "submit_conformance.candidate")
    mode = _require_string(data.get("mode"), "submit_conformance.mode")
    run_id = _require_string(data.get("run_id"), "submit_conformance.run_id")
    symbol = _require_string(data.get("symbol"), "submit_conformance.symbol")
    status = _require_string(data.get("status"), "submit_conformance.status")
    as_of = _require_string(data.get("as_of"), "submit_conformance.as_of")
    safety_assertions = data.get("safety_assertions")
    dry_run_request = data.get("dry_run_request")
    blockers = data.get("blockers")

    if artifact_type != _GATED_SUBMIT_CONFORMANCE_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("submit_conformance artifact_type mismatch")
    if schema_version != _GATED_SUBMIT_CONFORMANCE_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("submit_conformance schema_version mismatch")
    if candidate != "CAND-006":
        raise OperatorApprovalGateValidationError("submit_conformance candidate must be CAND-006")
    if mode != "simulated_only":
        raise OperatorApprovalGateValidationError("submit_conformance mode must be 'simulated_only'")
    if not isinstance(safety_assertions, dict):
        raise OperatorApprovalGateValidationError(
            "submit_conformance safety_assertions must be an object"
        )
    if not all(isinstance(v, bool) and v for v in safety_assertions.values()):
        raise OperatorApprovalGateValidationError(
            "all submit_conformance safety_assertions must be true"
        )
    if not isinstance(dry_run_request, dict):
        raise OperatorApprovalGateValidationError(
            "submit_conformance dry_run_request must be an object"
        )
    transmission = dry_run_request.get("transmission")
    if not isinstance(transmission, dict):
        raise OperatorApprovalGateValidationError(
            "submit_conformance dry_run_request.transmission must be an object"
        )
    if not isinstance(transmission.get("allowed"), bool):
        raise OperatorApprovalGateValidationError(
            "submit_conformance dry_run_request.transmission.allowed must be a boolean"
        )
    for field_name in ("broker_adapter", "provider"):
        value = transmission.get(field_name)
        if value is not None and not isinstance(value, str):
            raise OperatorApprovalGateValidationError(
                f"submit_conformance dry_run_request.transmission.{field_name} must be null or a string"
            )
    if not isinstance(blockers, list):
        raise OperatorApprovalGateValidationError("submit_conformance blockers must be a list")

    as_of_dt = _parse_or_fail(as_of, "submit_conformance.as_of")
    cand008_dt = _parse_iso_timestamp(cand008_as_of)
    if cand008_dt is not None and as_of_dt > cand008_dt:
        raise OperatorApprovalGateValidationError(
            "submit_conformance as_of is later than CAND-008 as_of"
        )
    if cand008_dt is not None:
        age_hours = (cand008_dt - as_of_dt).total_seconds() / 3600.0
        if age_hours > _MAX_EVIDENCE_AGE_HOURS:
            raise OperatorApprovalGateValidationError(
                "submit_conformance evidence is older than 24 hours"
            )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "candidate": candidate,
        "mode": mode,
        "run_id": run_id,
        "symbol": symbol,
        "status": status,
        "as_of": as_of,
        "safety_assertions": safety_assertions,
        "dry_run_request": dry_run_request,
        "blockers": blockers,
    }


def _validate_readiness_envelope(
    data: dict[str, Any], cand008_as_of: str
) -> dict[str, Any]:
    """Project CAND-007 to accepted keys and validate the envelope assertions."""
    artifact_type = _require_string(
        data.get("artifact_type"), "readiness_envelope.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "readiness_envelope.schema_version"
    )
    candidate = _require_string(data.get("candidate"), "readiness_envelope.candidate")
    mode = _require_string(data.get("mode"), "readiness_envelope.mode")
    status = _require_string(data.get("status"), "readiness_envelope.status")
    exit_code = data.get("exit_code")
    as_of = _require_string(data.get("as_of"), "readiness_envelope.as_of")
    run_id = _require_string(data.get("run_id"), "readiness_envelope.run_id")
    symbol = _require_string(data.get("symbol"), "readiness_envelope.symbol")
    blockers = data.get("blockers")
    envelope_assertions = data.get("envelope_assertions")

    if artifact_type != _RUNTIME_READINESS_ENVELOPE_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError(
            "readiness_envelope artifact_type mismatch"
        )
    if schema_version != _RUNTIME_READINESS_ENVELOPE_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError(
            "readiness_envelope schema_version mismatch"
        )
    if candidate != "CAND-007":
        raise OperatorApprovalGateValidationError(
            "readiness_envelope candidate must be CAND-007"
        )
    if mode != "simulated_only":
        raise OperatorApprovalGateValidationError(
            "readiness_envelope mode must be 'simulated_only'"
        )
    if not isinstance(exit_code, int) or exit_code != 0:
        raise OperatorApprovalGateValidationError("readiness_envelope exit_code must be 0")
    if not isinstance(blockers, list):
        raise OperatorApprovalGateValidationError(
            "readiness_envelope blockers must be a list"
        )
    if not isinstance(envelope_assertions, dict):
        raise OperatorApprovalGateValidationError(
            "readiness_envelope envelope_assertions must be an object"
        )

    missing_assertions = _CAND007_REQUIRED_ASSERTIONS - set(envelope_assertions)
    if missing_assertions:
        raise OperatorApprovalGateValidationError(
            f"readiness_envelope missing required envelope_assertions: {sorted(missing_assertions)}"
        )
    if not all(
        isinstance(envelope_assertions[k], bool) and envelope_assertions[k]
        for k in _CAND007_REQUIRED_ASSERTIONS
    ):
        raise OperatorApprovalGateValidationError(
            "all required readiness_envelope envelope_assertions must be true"
        )

    as_of_dt = _parse_or_fail(as_of, "readiness_envelope.as_of")
    cand008_dt = _parse_iso_timestamp(cand008_as_of)
    if cand008_dt is not None and as_of_dt > cand008_dt:
        raise OperatorApprovalGateValidationError(
            "readiness_envelope as_of is later than CAND-008 as_of"
        )
    if cand008_dt is not None:
        age_hours = (cand008_dt - as_of_dt).total_seconds() / 3600.0
        if age_hours > _MAX_EVIDENCE_AGE_HOURS:
            raise OperatorApprovalGateValidationError(
                "readiness_envelope evidence is older than 24 hours"
            )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "candidate": candidate,
        "mode": mode,
        "status": status,
        "exit_code": exit_code,
        "as_of": as_of,
        "run_id": run_id,
        "symbol": symbol,
        "blockers": blockers,
        "envelope_assertions": envelope_assertions,
    }


def _validate_operator_identity(data: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Closed-schema validation for the operator identity fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "operator_id",
        "operator_role",
        "operator_attestation_scope",
        "created_at",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "operator_identity")

    artifact_type = _require_string(
        data.get("artifact_type"), "operator_identity.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "operator_identity.schema_version"
    )
    if artifact_type != _OPERATOR_IDENTITY_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("operator_identity artifact_type mismatch")
    if schema_version != _OPERATOR_IDENTITY_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("operator_identity schema_version mismatch")

    operator_id = _require_string(data.get("operator_id"), "operator_identity.operator_id")
    _require_nonempty_bounded_id(operator_id, "operator_identity.operator_id")
    operator_role = _require_string(
        data.get("operator_role"), "operator_identity.operator_role"
    )
    _require_nonempty_bounded_id(operator_role, "operator_identity.operator_role")
    operator_attestation_scope = _require_string(
        data.get("operator_attestation_scope"), "operator_identity.operator_attestation_scope"
    )
    if operator_attestation_scope != "evidence_only":
        raise OperatorApprovalGateValidationError(
            "operator_identity operator_attestation_scope must be 'evidence_only'"
        )

    created_at = _parse_or_fail(
        _require_string(data.get("created_at"), "operator_identity.created_at"),
        "operator_identity.created_at",
    )
    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "operator_identity.expires_at"),
        "operator_identity.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise OperatorApprovalGateValidationError(
            "operator_identity expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "operator_id": operator_id,
        "operator_role": operator_role,
        "operator_attestation_scope": operator_attestation_scope,
        "created_at": _format_utc_timestamp(created_at),
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_approval_policy(data: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Closed-schema validation for the approval policy fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "requires_manual_review",
        "requires_explicit_acknowledgment",
        "approval_scope",
        "live_trading_approval",
        "live_submit_approval",
        "unattended_operation_allowed",
        "max_review_age_seconds",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "approval_policy")

    artifact_type = _require_string(
        data.get("artifact_type"), "approval_policy.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "approval_policy.schema_version"
    )
    if artifact_type != _APPROVAL_POLICY_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("approval_policy artifact_type mismatch")
    if schema_version != _APPROVAL_POLICY_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("approval_policy schema_version mismatch")

    for field_name in (
        "requires_manual_review",
        "requires_explicit_acknowledgment",
        "live_trading_approval",
        "live_submit_approval",
        "unattended_operation_allowed",
    ):
        if not isinstance(data.get(field_name), bool):
            raise OperatorApprovalGateValidationError(
                f"approval_policy {field_name} must be a boolean"
            )

    approval_scope = _require_string(
        data.get("approval_scope"), "approval_policy.approval_scope"
    )
    if approval_scope != "evidence_only":
        raise OperatorApprovalGateValidationError(
            "approval_policy approval_scope must be 'evidence_only'"
        )

    max_review_age_seconds = data.get("max_review_age_seconds")
    if not isinstance(max_review_age_seconds, int) or isinstance(max_review_age_seconds, bool):
        raise OperatorApprovalGateValidationError(
            "approval_policy max_review_age_seconds must be an integer"
        )
    if max_review_age_seconds <= 0:
        raise OperatorApprovalGateValidationError(
            "approval_policy max_review_age_seconds must be positive"
        )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "approval_policy.expires_at"),
        "approval_policy.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise OperatorApprovalGateValidationError(
            "approval_policy expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "requires_manual_review": data["requires_manual_review"],
        "requires_explicit_acknowledgment": data["requires_explicit_acknowledgment"],
        "approval_scope": approval_scope,
        "live_trading_approval": data["live_trading_approval"],
        "live_submit_approval": data["live_submit_approval"],
        "unattended_operation_allowed": data["unattended_operation_allowed"],
        "max_review_age_seconds": max_review_age_seconds,
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_kill_switch_observation(
    data: dict[str, Any], as_of: str
) -> dict[str, Any]:
    """Closed-schema validation for the kill-switch observation fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "kill_switch_required",
        "observed_state",
        "observed_at",
        "observation_source",
        "override_attempted",
        "override_allowed",
        "default_on_missing",
        "default_on_unknown",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "kill_switch_observation")

    artifact_type = _require_string(
        data.get("artifact_type"), "kill_switch_observation.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "kill_switch_observation.schema_version"
    )
    if artifact_type != _KILL_SWITCH_OBSERVATION_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError(
            "kill_switch_observation artifact_type mismatch"
        )
    if schema_version != _KILL_SWITCH_OBSERVATION_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError(
            "kill_switch_observation schema_version mismatch"
        )

    if not isinstance(data.get("kill_switch_required"), bool):
        raise OperatorApprovalGateValidationError(
            "kill_switch_observation kill_switch_required must be a boolean"
        )

    observed_state = _require_string(
        data.get("observed_state"), "kill_switch_observation.observed_state"
    )
    if observed_state not in {"blocked", "inactive", "unknown"}:
        raise OperatorApprovalGateValidationError(
            "kill_switch_observation observed_state invalid"
        )

    observed_at = _parse_or_fail(
        _require_string(data.get("observed_at"), "kill_switch_observation.observed_at"),
        "kill_switch_observation.observed_at",
    )

    observation_source = _require_string(
        data.get("observation_source"), "kill_switch_observation.observation_source"
    )
    if observation_source != "local_fixture":
        raise OperatorApprovalGateValidationError(
            "kill_switch_observation observation_source must be 'local_fixture'"
        )

    for field_name in ("override_attempted", "override_allowed"):
        if not isinstance(data.get(field_name), bool):
            raise OperatorApprovalGateValidationError(
                f"kill_switch_observation {field_name} must be a boolean"
            )

    for field_name in ("default_on_missing", "default_on_unknown"):
        value = _require_string(
            data.get(field_name), f"kill_switch_observation.{field_name}"
        )
        if value != "blocked":
            raise OperatorApprovalGateValidationError(
                f"kill_switch_observation {field_name} must be 'blocked'"
            )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "kill_switch_observation.expires_at"),
        "kill_switch_observation.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise OperatorApprovalGateValidationError(
            "kill_switch_observation expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "kill_switch_required": data["kill_switch_required"],
        "observed_state": observed_state,
        "observed_at": _format_utc_timestamp(observed_at),
        "observation_source": observation_source,
        "override_attempted": data["override_attempted"],
        "override_allowed": data["override_allowed"],
        "default_on_missing": data["default_on_missing"],
        "default_on_unknown": data["default_on_unknown"],
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_operator_acknowledgment(
    data: dict[str, Any], as_of: str
) -> dict[str, Any]:
    """Closed-schema validation for the operator acknowledgment fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "acknowledged_no_live_submit",
        "acknowledged_no_trading_authorization",
        "acknowledged_no_profitability_claim",
        "acknowledged_no_broker_certification",
        "acknowledged_review_is_evidence_only",
        "acknowledged_unattended_live_forbidden",
        "acknowledgment_text_digest",
        "acknowledged_at",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "operator_acknowledgment")

    artifact_type = _require_string(
        data.get("artifact_type"), "operator_acknowledgment.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "operator_acknowledgment.schema_version"
    )
    if artifact_type != _OPERATOR_ACKNOWLEDGMENT_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError(
            "operator_acknowledgment artifact_type mismatch"
        )
    if schema_version != _OPERATOR_ACKNOWLEDGMENT_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError(
            "operator_acknowledgment schema_version mismatch"
        )

    acknowledgment_fields = (
        "acknowledged_no_live_submit",
        "acknowledged_no_trading_authorization",
        "acknowledged_no_profitability_claim",
        "acknowledged_no_broker_certification",
        "acknowledged_review_is_evidence_only",
        "acknowledged_unattended_live_forbidden",
    )
    for field_name in acknowledgment_fields:
        if data.get(field_name) is not True:
            raise OperatorApprovalGateValidationError(
                f"operator_acknowledgment {field_name} must be true"
            )

    acknowledgment_text_digest = _require_string(
        data.get("acknowledgment_text_digest"),
        "operator_acknowledgment.acknowledgment_text_digest",
    )
    if acknowledgment_text_digest != _compute_acknowledgment_digest():
        raise OperatorApprovalGateValidationError(
            "operator_acknowledgment digest mismatch"
        )

    acknowledged_at = _parse_or_fail(
        _require_string(data.get("acknowledged_at"), "operator_acknowledgment.acknowledged_at"),
        "operator_acknowledgment.acknowledged_at",
    )
    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "operator_acknowledgment.expires_at"),
        "operator_acknowledgment.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise OperatorApprovalGateValidationError(
            "operator_acknowledgment expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        **{field_name: True for field_name in acknowledgment_fields},
        "acknowledgment_text_digest": acknowledgment_text_digest,
        "acknowledged_at": _format_utc_timestamp(acknowledged_at),
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_audit_policy(data: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Closed-schema validation for the audit policy fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "audit_required",
        "append_only_required",
        "hash_chain_required",
        "local_artifact_recording_required",
        "live_audit_chain_claimed",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "audit_policy")

    artifact_type = _require_string(
        data.get("artifact_type"), "audit_policy.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "audit_policy.schema_version"
    )
    if artifact_type != _AUDIT_POLICY_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("audit_policy artifact_type mismatch")
    if schema_version != _AUDIT_POLICY_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("audit_policy schema_version mismatch")

    for field_name in (
        "audit_required",
        "append_only_required",
        "hash_chain_required",
        "local_artifact_recording_required",
        "live_audit_chain_claimed",
    ):
        if not isinstance(data.get(field_name), bool):
            raise OperatorApprovalGateValidationError(
                f"audit_policy {field_name} must be a boolean"
            )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "audit_policy.expires_at"),
        "audit_policy.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise OperatorApprovalGateValidationError(
            "audit_policy expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "audit_required": data["audit_required"],
        "append_only_required": data["append_only_required"],
        "hash_chain_required": data["hash_chain_required"],
        "local_artifact_recording_required": data["local_artifact_recording_required"],
        "live_audit_chain_claimed": data["live_audit_chain_claimed"],
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _load_and_validate_all(
    inputs: OperatorApprovalGateInputs, as_of: str
) -> dict[str, Any]:
    """Load every input fixture, scan it, and validate by projection or closed schema."""
    paths = {label: getattr(inputs, f"{label}_path") for label in _INPUT_LABELS}
    fixture_labels = {
        "operator_identity",
        "approval_policy",
        "kill_switch_observation",
        "operator_acknowledgment",
        "audit_policy",
    }
    raw: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        raw[label] = _load_json_object(path, label)
        findings = _universal_reject_scan(
            raw[label],
            label,
            include_forbidden_keys=(label in fixture_labels),
        )
        if findings:
            raise OperatorApprovalGateValidationError(
                "universal rejection: " + "; ".join(findings)
            )

    return {
        "quality_gate": _validate_quality_gate(raw["quality_gate"]),
        "shadow_comparison": _validate_shadow_comparison(raw["shadow_comparison"]),
        "submit_conformance": _validate_submit_conformance(raw["submit_conformance"], as_of),
        "readiness_envelope": _validate_readiness_envelope(raw["readiness_envelope"], as_of),
        "operator_identity": _validate_operator_identity(raw["operator_identity"], as_of),
        "approval_policy": _validate_approval_policy(raw["approval_policy"], as_of),
        "kill_switch_observation": _validate_kill_switch_observation(
            raw["kill_switch_observation"], as_of
        ),
        "operator_acknowledgment": _validate_operator_acknowledgment(
            raw["operator_acknowledgment"], as_of
        ),
        "audit_policy": _validate_audit_policy(raw["audit_policy"], as_of),
    }


def _gate_pass(gate_id: str, details: dict[str, Any] | None = None) -> GateResult:
    return GateResult(gate_id=gate_id, status="pass", reason="", details=details or {})


def _gate_fail(
    gate_id: str, reason: str, details: dict[str, Any] | None = None
) -> GateResult:
    return GateResult(gate_id=gate_id, status="fail", reason=reason, details=details or {})


def _gate_not_run(gate_id: str, reason: str = "prior gate failed") -> GateResult:
    return GateResult(gate_id=gate_id, status="not_run", reason=reason)


def _correlate_evidence(normalized: dict[str, Any]) -> list[str]:
    """Return correlation blockers across upstream artifacts."""
    blockers: list[str] = []
    run_id = normalized["quality_gate"]["run_id"]
    symbol = normalized["quality_gate"]["symbol"]
    for label in ("shadow_comparison", "submit_conformance", "readiness_envelope"):
        if normalized[label]["run_id"] != run_id:
            blockers.append(f"run_id mismatch between quality_gate and {label}")
        if normalized[label]["symbol"] != symbol:
            blockers.append(f"symbol mismatch between quality_gate and {label}")
    return blockers


def _build_upstream_summaries(normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "cand004": {
            "artifact_type": normalized["quality_gate"]["artifact_type"],
            "schema_version": normalized["quality_gate"]["schema_version"],
            "mode": normalized["quality_gate"]["mode"],
            "quality_state": normalized["quality_gate"]["quality_state"],
            "blockers": normalized["quality_gate"]["blockers"],
        },
        "cand005": {
            "artifact_type": normalized["shadow_comparison"]["artifact_type"],
            "schema_version": normalized["shadow_comparison"]["schema_version"],
            "status": normalized["shadow_comparison"]["status"],
            "blockers": normalized["shadow_comparison"]["blockers"],
        },
        "cand006": {
            "artifact_type": normalized["submit_conformance"]["artifact_type"],
            "schema_version": normalized["submit_conformance"]["schema_version"],
            "status": normalized["submit_conformance"]["status"],
            "as_of": normalized["submit_conformance"]["as_of"],
            "transmission_allowed": normalized["submit_conformance"]["dry_run_request"][
                "transmission"
            ]["allowed"],
            "blockers": normalized["submit_conformance"]["blockers"],
        },
        "cand007": {
            "artifact_type": normalized["readiness_envelope"]["artifact_type"],
            "schema_version": normalized["readiness_envelope"]["schema_version"],
            "candidate": normalized["readiness_envelope"]["candidate"],
            "mode": normalized["readiness_envelope"]["mode"],
            "status": normalized["readiness_envelope"]["status"],
            "exit_code": normalized["readiness_envelope"]["exit_code"],
            "as_of": normalized["readiness_envelope"]["as_of"],
            "blockers": normalized["readiness_envelope"]["blockers"],
        },
    }


def _build_operator_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    op = normalized["operator_identity"]
    return {
        "operator_id": op["operator_id"],
        "operator_role": op["operator_role"],
        "operator_attestation_scope": op["operator_attestation_scope"],
        "fixture_status": "valid",
    }


def _build_approval_policy_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    ap = normalized["approval_policy"]
    return {
        "requires_manual_review": ap["requires_manual_review"],
        "requires_explicit_acknowledgment": ap["requires_explicit_acknowledgment"],
        "approval_scope": ap["approval_scope"],
        "live_trading_approval": ap["live_trading_approval"],
        "live_submit_approval": ap["live_submit_approval"],
        "unattended_operation_allowed": ap["unattended_operation_allowed"],
        "max_review_age_seconds": ap["max_review_age_seconds"],
    }


def _build_kill_switch_observation_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    ks = normalized["kill_switch_observation"]
    return {
        "kill_switch_required": ks["kill_switch_required"],
        "observed_state": ks["observed_state"],
        "observed_at": ks["observed_at"],
        "observation_source": ks["observation_source"],
        "override_attempted": ks["override_attempted"],
        "override_allowed": ks["override_allowed"],
        "default_on_missing": ks["default_on_missing"],
        "default_on_unknown": ks["default_on_unknown"],
    }


def _build_acknowledgment_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    ack = normalized["operator_acknowledgment"]
    return {
        "acknowledged_no_live_submit": ack["acknowledged_no_live_submit"],
        "acknowledged_no_trading_authorization": ack["acknowledged_no_trading_authorization"],
        "acknowledged_no_profitability_claim": ack["acknowledged_no_profitability_claim"],
        "acknowledged_no_broker_certification": ack["acknowledged_no_broker_certification"],
        "acknowledged_review_is_evidence_only": ack["acknowledged_review_is_evidence_only"],
        "acknowledged_unattended_live_forbidden": ack["acknowledged_unattended_live_forbidden"],
        "acknowledgment_text_digest": ack["acknowledgment_text_digest"],
        "acknowledged_at": ack["acknowledged_at"],
    }


def _build_audit_policy_summary(normalized: dict[str, Any]) -> dict[str, Any]:
    au = normalized["audit_policy"]
    return {
        "audit_required": au["audit_required"],
        "append_only_required": au["append_only_required"],
        "hash_chain_required": au["hash_chain_required"],
        "local_artifact_recording_required": au["local_artifact_recording_required"],
        "live_audit_chain_claimed": au["live_audit_chain_claimed"],
    }


def _build_approval_gate_assertions(normalized: dict[str, Any]) -> dict[str, bool]:
    sc = normalized["submit_conformance"]
    re = normalized["readiness_envelope"]
    op = normalized["operator_identity"]
    ap = normalized["approval_policy"]
    ks = normalized["kill_switch_observation"]
    ack = normalized["operator_acknowledgment"]
    au = normalized["audit_policy"]
    return {
        "cand007_status_accepted": re["status"] == "readiness_envelope_recorded",
        "cand007_mode_simulated_only": re["mode"] == "simulated_only",
        "cand007_blockers_empty": re["blockers"] == [],
        "cand007_safety_assertions_accepted": all(
            re["envelope_assertions"].get(k, False) for k in _CAND007_REQUIRED_ASSERTIONS
        ),
        "operator_identity_valid": op["operator_attestation_scope"] == "evidence_only",
        "approval_policy_fail_closed": (
            ap["live_trading_approval"] is False
            and ap["live_submit_approval"] is False
            and ap["unattended_operation_allowed"] is False
            and ap["approval_scope"] == "evidence_only"
        ),
        "kill_switch_observed_blocked": ks["observed_state"] == "blocked",
        "operator_acknowledgments_all_true": all(
            ack.get(field, False)
            for field in (
                "acknowledged_no_live_submit",
                "acknowledged_no_trading_authorization",
                "acknowledged_no_profitability_claim",
                "acknowledged_no_broker_certification",
                "acknowledged_review_is_evidence_only",
                "acknowledged_unattended_live_forbidden",
            )
        ),
        "audit_policy_fail_closed": (
            au["audit_required"]
            and au["append_only_required"]
            and au["hash_chain_required"]
            and au["local_artifact_recording_required"]
            and not au["live_audit_chain_claimed"]
        ),
        "no_credentials_in_fixtures": True,
        "no_endpoints_in_fixtures": True,
        "no_account_ids_in_fixtures": True,
        "no_raw_upstream_leakage": True,
        "cand006_transmission_blocked": not sc["dry_run_request"]["transmission"]["allowed"],
    }


def _build_report(
    inputs: OperatorApprovalGateInputs,
    as_of: str,
    gate_results: list[GateResult],
    blockers: list[str],
    status: str,
    normalized: dict[str, Any] | None,
    fingerprints: dict[str, str] | None = None,
    input_digest: str | None = None,
    evaluation_id: str | None = None,
) -> OperatorApprovalGateReport:
    if fingerprints is None:
        fingerprints = {}
    if input_digest is None:
        input_digest = "sha256:" + "0" * 64
    if evaluation_id is None:
        evaluation_id = ""

    exit_code = 0 if status == "operator_gate_recorded" else 2

    input_artifacts = {
        label: _redact_path(getattr(inputs, f"{label}_path")) for label in _INPUT_LABELS
    }
    input_paths = {
        label: getattr(inputs, f"{label}_path") for label in _INPUT_LABELS
    }

    upstream_summaries = _build_upstream_summaries(normalized) if normalized else {}
    operator_summary = _build_operator_summary(normalized) if normalized else {}
    approval_policy_summary = (
        _build_approval_policy_summary(normalized) if normalized else {}
    )
    kill_switch_observation_summary = (
        _build_kill_switch_observation_summary(normalized) if normalized else {}
    )
    acknowledgment_summary = (
        _build_acknowledgment_summary(normalized) if normalized else {}
    )
    audit_policy_summary = _build_audit_policy_summary(normalized) if normalized else {}
    approval_gate_assertions = (
        _build_approval_gate_assertions(normalized) if normalized else {}
    )

    approval_gate_digest = _compute_approval_gate_digest(
        as_of,
        fingerprints,
        upstream_summaries,
        approval_gate_assertions,
    )

    return OperatorApprovalGateReport(
        artifact_type=ARTIFACT_TYPE,
        schema_version=SCHEMA_VERSION,
        candidate=CANDIDATE,
        mode=MODE,
        status=status,
        exit_code=exit_code,
        evaluation_id=evaluation_id,
        as_of=as_of,
        run_id=normalized["quality_gate"]["run_id"] if normalized else None,
        symbol=normalized["quality_gate"]["symbol"] if normalized else None,
        candidate_chain=CANDIDATE_CHAIN,
        gate_sequence=GATE_SEQUENCE,
        gates=tuple(gate_results),
        input_artifacts=input_artifacts,
        input_paths=input_paths,
        input_fingerprints=fingerprints,
        input_digest=input_digest,
        approval_gate_digest=approval_gate_digest,
        upstream_summaries=upstream_summaries,
        operator_summary=operator_summary,
        approval_policy_summary=approval_policy_summary,
        kill_switch_observation_summary=kill_switch_observation_summary,
        acknowledgment_summary=acknowledgment_summary,
        audit_policy_summary=audit_policy_summary,
        approval_gate_assertions=approval_gate_assertions,
        blockers=list(blockers),
        recording={"json_written": False, "markdown_written": False},
        disclaimer=EVIDENCE_ONLY_DISCLAIMER,
    )


def build_operator_approval_gate_report(
    inputs: OperatorApprovalGateInputs,
) -> OperatorApprovalGateReport:
    """Evaluate all gates in strict fail-closed order and build a report.

    This function performs no I/O beyond reading the input fixture files supplied
    in ``inputs``. Artifact writing is a separate step.
    """
    as_of = parse_as_of_utc(inputs.as_of)

    gates: list[GateResult] = []
    blockers: list[str] = []
    status = "not_evaluated"

    # Gate 1: schema_preflight
    try:
        normalized = _load_and_validate_all(inputs, as_of)
        gates.append(_gate_pass("schema_preflight"))
    except OperatorApprovalGateValidationError as exc:
        gates.append(_gate_fail("schema_preflight", str(exc)))
        blockers.append(f"schema_preflight: {exc}")
        status = "not_evaluated"
        for gate_id in GATE_SEQUENCE[1:]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=None,
        )

    fingerprints = _input_fingerprints(normalized)
    input_digest = _compute_input_digest(as_of, fingerprints)
    evaluation_id = _evaluation_id(input_digest)

    quality_gate = normalized["quality_gate"]
    shadow_comparison = normalized["shadow_comparison"]
    submit_conformance = normalized["submit_conformance"]
    readiness_envelope = normalized["readiness_envelope"]
    operator_identity = normalized["operator_identity"]
    approval_policy = normalized["approval_policy"]
    kill_switch_observation = normalized["kill_switch_observation"]
    operator_acknowledgment = normalized["operator_acknowledgment"]
    audit_policy = normalized["audit_policy"]

    # Gate 2: cand004_projection_gate
    cand004_failures: list[str] = []
    if quality_gate["mode"] != "paper":
        cand004_failures.append("quality_gate mode is not 'paper'")
    if quality_gate["quality_state"] != "eligible_for_shadow_live_quality_review":
        cand004_failures.append(
            f"quality_gate quality_state is '{quality_gate['quality_state']}'"
        )
    if quality_gate["blockers"]:
        cand004_failures.append("quality_gate blockers are non-empty")
    if cand004_failures:
        reason = "; ".join(cand004_failures)
        gates.append(_gate_fail("cand004_projection_gate", reason))
        blockers.append(f"cand004_projection_gate: {reason}")
        status = "upstream_evidence_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("cand004_projection_gate"))

    # Gate 3: cand005_projection_gate
    cand005_failures: list[str] = []
    if shadow_comparison["status"] != "matched":
        cand005_failures.append(
            f"shadow_comparison status is '{shadow_comparison['status']}'"
        )
    if shadow_comparison["blockers"]:
        cand005_failures.append("shadow_comparison blockers are non-empty")
    if cand005_failures:
        reason = "; ".join(cand005_failures)
        gates.append(_gate_fail("cand005_projection_gate", reason))
        blockers.append(f"cand005_projection_gate: {reason}")
        status = "upstream_evidence_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("cand005_projection_gate"))

    # Gate 4: cand006_projection_gate
    cand006_failures: list[str] = []
    if submit_conformance["status"] != "dry_run_recorded":
        cand006_failures.append(
            f"submit_conformance status is '{submit_conformance['status']}'"
        )
    if submit_conformance["blockers"]:
        cand006_failures.append("submit_conformance blockers are non-empty")
    if not all(submit_conformance["safety_assertions"].values()):
        cand006_failures.append("not all submit_conformance safety_assertions are true")
    transmission = submit_conformance["dry_run_request"]["transmission"]
    if transmission["allowed"] is not False:
        cand006_failures.append("submit_conformance transmission is not blocked")
    if transmission["broker_adapter"] is not None:
        cand006_failures.append("submit_conformance broker_adapter is not null")
    if transmission["provider"] is not None:
        cand006_failures.append("submit_conformance provider is not null")
    if cand006_failures:
        reason = "; ".join(cand006_failures)
        gates.append(_gate_fail("cand006_projection_gate", reason))
        blockers.append(f"cand006_projection_gate: {reason}")
        status = "upstream_evidence_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("cand006_projection_gate"))

    # Gate 5: cand007_projection_gate
    cand007_failures: list[str] = []
    if readiness_envelope["status"] != "readiness_envelope_recorded":
        cand007_failures.append(
            f"readiness_envelope status is '{readiness_envelope['status']}'"
        )
    if readiness_envelope["mode"] != "simulated_only":
        cand007_failures.append(
            f"readiness_envelope mode is '{readiness_envelope['mode']}'"
        )
    if readiness_envelope["candidate"] != "CAND-007":
        cand007_failures.append(
            f"readiness_envelope candidate is '{readiness_envelope['candidate']}'"
        )
    if readiness_envelope["exit_code"] != 0:
        cand007_failures.append(
            f"readiness_envelope exit_code is {readiness_envelope['exit_code']}"
        )
    if readiness_envelope["blockers"]:
        cand007_failures.append("readiness_envelope blockers are non-empty")
    if not all(readiness_envelope["envelope_assertions"].values()):
        cand007_failures.append("not all readiness_envelope envelope_assertions are true")
    if cand007_failures:
        reason = "; ".join(cand007_failures)
        gates.append(_gate_fail("cand007_projection_gate", reason))
        blockers.append(f"cand007_projection_gate: {reason}")
        status = "runtime_envelope_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("cand007_projection_gate"))

    # Gate 6: cross_artifact_correlation_gate
    correlation_blockers = _correlate_evidence(normalized)
    if correlation_blockers:
        reason = "; ".join(correlation_blockers)
        gates.append(_gate_fail("cross_artifact_correlation_gate", reason))
        blockers.append(f"cross_artifact_correlation_gate: {reason}")
        status = "blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("cross_artifact_correlation_gate"))

    # Gate 7: operator_identity_gate
    op_failures: list[str] = []
    if operator_identity["operator_attestation_scope"] != "evidence_only":
        op_failures.append("operator_identity attestation scope is not 'evidence_only'")
    if op_failures:
        reason = "; ".join(op_failures)
        gates.append(_gate_fail("operator_identity_gate", reason))
        blockers.append(f"operator_identity_gate: {reason}")
        status = "operator_identity_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("operator_identity_gate"))

    # Gate 8: approval_policy_gate
    ap_failures: list[str] = []
    if approval_policy["live_trading_approval"] is not False:
        ap_failures.append("approval_policy live_trading_approval is true")
    if approval_policy["live_submit_approval"] is not False:
        ap_failures.append("approval_policy live_submit_approval is true")
    if approval_policy["unattended_operation_allowed"] is not False:
        ap_failures.append("approval_policy unattended_operation_allowed is true")
    if approval_policy["approval_scope"] != "evidence_only":
        ap_failures.append("approval_policy approval_scope is not 'evidence_only'")
    if ap_failures:
        reason = "; ".join(ap_failures)
        gates.append(_gate_fail("approval_policy_gate", reason))
        blockers.append(f"approval_policy_gate: {reason}")
        status = "approval_policy_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("approval_policy_gate"))

    # Gate 9: kill_switch_observation_gate
    ks_failures: list[str] = []
    if kill_switch_observation["observed_state"] != "blocked":
        ks_failures.append(
            f"kill_switch_observation observed_state is '{kill_switch_observation['observed_state']}'"
        )
    if kill_switch_observation["override_attempted"] is not False:
        ks_failures.append("kill_switch_observation override_attempted is true")
    if kill_switch_observation["override_allowed"] is not False:
        ks_failures.append("kill_switch_observation override_allowed is true")
    if kill_switch_observation["default_on_missing"] != "blocked":
        ks_failures.append(
            "kill_switch_observation default_on_missing is not 'blocked'"
        )
    if kill_switch_observation["default_on_unknown"] != "blocked":
        ks_failures.append(
            "kill_switch_observation default_on_unknown is not 'blocked'"
        )
    if ks_failures:
        reason = "; ".join(ks_failures)
        gates.append(_gate_fail("kill_switch_observation_gate", reason))
        blockers.append(f"kill_switch_observation_gate: {reason}")
        status = "kill_switch_observation_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("kill_switch_observation_gate"))

    # Gate 10: operator_acknowledgment_gate
    ack_failures: list[str] = []
    if operator_acknowledgment["acknowledgment_text_digest"] != _compute_acknowledgment_digest():
        ack_failures.append("operator_acknowledgment digest mismatch")
    if ack_failures:
        reason = "; ".join(ack_failures)
        gates.append(_gate_fail("operator_acknowledgment_gate", reason))
        blockers.append(f"operator_acknowledgment_gate: {reason}")
        status = "operator_acknowledgment_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("operator_acknowledgment_gate"))

    # Gate 11: audit_policy_gate
    au_failures: list[str] = []
    for field_name in (
        "audit_required",
        "append_only_required",
        "hash_chain_required",
        "local_artifact_recording_required",
    ):
        if audit_policy[field_name] is not True:
            au_failures.append(f"audit_policy {field_name} is false")
    if audit_policy["live_audit_chain_claimed"] is not False:
        au_failures.append("audit_policy live_audit_chain_claimed is true")
    if au_failures:
        reason = "; ".join(au_failures)
        gates.append(_gate_fail("audit_policy_gate", reason))
        blockers.append(f"audit_policy_gate: {reason}")
        status = "audit_policy_blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
    gates.append(_gate_pass("audit_policy_gate"))

    # Gate 12: approval_gate_synthesis
    try:
        # Synthesize the report dict in memory to prove the artifact is buildable.
        _ = _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status="operator_gate_synthesized",
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )
        gates.append(_gate_pass("approval_gate_synthesis"))
        status = "operator_gate_synthesized"
    except Exception as exc:
        gates.append(_gate_fail("approval_gate_synthesis", str(exc)))
        blockers.append(f"approval_gate_synthesis: {exc}")
        status = "blocked"
        for gate_id in GATE_SEQUENCE[len(gates) :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gate_results=gates,
            blockers=blockers,
            status=status,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )

    # Gate 13: artifact_recording_gate is handled by the writer. The report
    # returned here represents the state before writing.
    gates.append(_gate_not_run("artifact_recording_gate", "writer not invoked"))

    return _build_report(
        inputs=inputs,
        as_of=as_of,
        gate_results=gates,
        blockers=blockers,
        status=status,
        normalized=normalized,
        fingerprints=fingerprints,
        input_digest=input_digest,
        evaluation_id=evaluation_id,
    )


_InputEntry = tuple[str, Path, tuple[int, int] | None]


def _replace_gate_status(
    gates: tuple[GateResult, ...],
    gate_id: str,
    status: Literal["pass", "fail", "not_run"],
    reason: str = "",
) -> tuple[GateResult, ...]:
    """Return a new gate sequence with the matching gate updated."""
    return tuple(
        GateResult(
            gate_id=g.gate_id,
            status=status,
            reason=reason,
            details=g.details,
        )
        if g.gate_id == gate_id
        else g
        for g in gates
    )


def _resolve_input_entries(report: OperatorApprovalGateReport) -> list[_InputEntry]:
    """Resolve input artifact paths and capture device/inode identities."""
    entries: list[_InputEntry] = []
    for label in _INPUT_LABELS:
        path = report.input_paths.get(label)
        if path is None:
            continue
        if not path.is_absolute():
            # Relative names in the report cannot be resolved; skip identity check.
            entries.append((label, path, None))
            continue
        try:
            resolved = path.resolve()
        except Exception as exc:
            raise OperatorApprovalGateValidationError(
                f"input path {label} cannot be resolved: {exc}"
            ) from None
        identity: tuple[int, int] | None = None
        if resolved.exists():
            try:
                st = resolved.stat()
                identity = (st.st_dev, st.st_ino)
            except Exception:
                identity = None
        entries.append((label, resolved, identity))
    return entries


def _candidate_aliases_input(
    candidate: Path, input_entries: list[_InputEntry]
) -> str | None:
    """Return an error string if ``candidate`` aliases an input path."""
    try:
        cand_resolved = candidate.resolve()
    except Exception:
        return None
    cand_identity: tuple[int, int] | None = None
    if cand_resolved.exists():
        try:
            st = cand_resolved.stat()
            cand_identity = (st.st_dev, st.st_ino)
        except Exception:
            cand_identity = None
    for label, resolved, identity in input_entries:
        if cand_resolved == resolved:
            return f"{candidate.name} aliases input path {label}"
        if cand_identity is not None and identity is not None and cand_identity == identity:
            return f"{candidate.name} is a hard link alias of input path {label}"
    return None


def _check_output_path_aliases(
    output_dir: Path, input_entries: list[_InputEntry]
) -> str | None:
    """Reject output directory or artifact paths that alias an input path."""
    try:
        output_dir_resolved = output_dir.resolve()
    except Exception as exc:
        return f"output_dir cannot be resolved: {exc}"
    if output_dir.exists() and not output_dir.is_dir():
        return "output_dir exists and is not a directory"

    out_identity: tuple[int, int] | None = None
    if output_dir_resolved.exists():
        try:
            st = output_dir_resolved.stat()
            out_identity = (st.st_dev, st.st_ino)
        except Exception:
            out_identity = None

    for label, resolved, identity in input_entries:
        if resolved == output_dir_resolved:
            return f"output_dir aliases input path {label}"
        if identity is not None and out_identity is not None and identity == out_identity:
            return f"output_dir is a hard link alias of input path {label}"

    for name, filename in (
        ("JSON artifact", _JSON_ARTIFACT_NAME),
        ("Markdown artifact", _MARKDOWN_ARTIFACT_NAME),
    ):
        candidate = output_dir_resolved / filename
        alias = _candidate_aliases_input(candidate, input_entries)
        if alias is not None:
            return f"{name} {alias}"

    return None


def _write_temp_file(
    output_dir: Path,
    filename: str,
    content: str,
    input_entries: list[_InputEntry],
) -> Path:
    """Create a flushed, fsync'd temp file next to ``filename`` and return its path."""
    fd, temp_name = tempfile.mkstemp(dir=output_dir, suffix=f".{filename}.tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        alias = _candidate_aliases_input(temp_path, input_entries)
        if alias is not None:
            raise OperatorApprovalGateValidationError(f"temporary file {alias}")

        return temp_path
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _blocked_writer_report(
    report: OperatorApprovalGateReport, reason: str
) -> OperatorApprovalGateReport:
    """Return a new report indicating the artifact writer was blocked."""
    return replace(
        report,
        status="blocked",
        exit_code=2,
        gates=_replace_gate_status(
            report.gates,
            "artifact_recording_gate",
            "fail",
            reason=reason,
        ),
        recording={"json_written": False, "markdown_written": False},
        blockers=list(report.blockers) + [reason],
    )


def _escape_md_table_cell(value: str) -> str:
    """Escape characters that would break a Markdown table cell."""
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`")


def _render_markdown_report(report: OperatorApprovalGateReport) -> str:
    """Render an informational Markdown report from an operator approval gate report.

    The Markdown artifact must never contain raw fixture bodies, absolute paths,
    usernames, credentials, account IDs, endpoint URLs, stack traces, or raw
    broker/provider payloads.
    """
    lines: list[str] = []
    lines.append(
        "> **Safety notice:** " + report.disclaimer
    )
    lines.append("")
    lines.append("# Operator Approval Gate Report (CAND-008)")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    for key, value in (
        ("status", report.status),
        ("evaluation_id", report.evaluation_id),
        ("as_of", report.as_of),
        ("symbol", report.symbol or "-"),
        ("run_id", report.run_id or "-"),
    ):
        lines.append(f"| {key} | `{value}` |")
    lines.append("")

    lines.append("## Gates")
    lines.append("")
    lines.append("| Gate | Status | Reason |")
    lines.append("|------|--------|--------|")
    for gate in report.gates:
        reason = _escape_md_table_cell(gate.reason) if gate.reason else "-"
        lines.append(f"| `{gate.gate_id}` | `{gate.status}` | {reason} |")
    lines.append("")

    lines.append("## Upstream evidence summaries")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.upstream_summaries, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    lines.append("## Operator summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.operator_summary, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    lines.append("## Approval policy summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.approval_policy_summary, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    lines.append("## Kill-switch observation summary")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(report.kill_switch_observation_summary, indent=2, sort_keys=True)
    )
    lines.append("```")
    lines.append("")

    lines.append("## Acknowledgment summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.acknowledgment_summary, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    lines.append("## Audit policy summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.audit_policy_summary, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    lines.append("## Approval gate assertions")
    lines.append("")
    lines.append("| Assertion | Value |")
    lines.append("|-----------|-------|")
    for assertion, value in report.approval_gate_assertions.items():
        lines.append(f"| `{assertion}` | `{value}` |")
    lines.append("")

    lines.append("## Input artifacts")
    lines.append("")
    for label, name in report.input_artifacts.items():
        fp = report.input_fingerprints.get(label, "")
        lines.append(f"- **{label}:** `{name or '-'} ({fp})`")
    lines.append("")

    lines.append("## Blockers")
    lines.append("")
    if report.blockers:
        for reason in report.blockers:
            lines.append(f"- {reason}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Disclaimer")
    lines.append("")
    lines.append(report.disclaimer)
    lines.append("")

    return "\n".join(lines)


def write_operator_approval_gate_artifacts(
    report: OperatorApprovalGateReport,
    output_dir: Path,
) -> OperatorApprovalGateReport:
    """Atomically write the JSON and Markdown artifacts for a report.

    JSON is the authoritative artifact and is replaced last. Markdown is
    informational. If either write fails, the function returns a report with
    ``status="blocked"`` and ``recording`` set to false.
    """
    if report.status != "operator_gate_synthesized":
        return _blocked_writer_report(report, "report is not ready for recording")

    if (
        not report.gates
        or report.gates[-1].gate_id != "artifact_recording_gate"
        or report.gates[-1].status != "not_run"
    ):
        return _blocked_writer_report(
            report, "artifact_recording_gate is not in expected not_run state"
        )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return _blocked_writer_report(
            report, f"artifact writer failed to create output directory: {exc}"
        )

    try:
        input_entries = _resolve_input_entries(report)
    except OperatorApprovalGateValidationError as exc:
        return _blocked_writer_report(report, str(exc))

    alias_error = _check_output_path_aliases(output_dir, input_entries)
    if alias_error is not None:
        return _blocked_writer_report(
            report, f"artifact writer path alias rejected: {alias_error}"
        )

    recorded_report = replace(
        report,
        status="operator_gate_recorded",
        exit_code=0,
        gates=_replace_gate_status(
            report.gates,
            "artifact_recording_gate",
            "pass",
            reason="artifacts recorded",
        ),
        recording={"json_written": True, "markdown_written": True},
        blockers=list(report.blockers),
    )

    markdown = _render_markdown_report(recorded_report)
    try:
        md_temp = _write_temp_file(
            output_dir, _MARKDOWN_ARTIFACT_NAME, markdown, input_entries
        )
    except Exception as exc:
        return _blocked_writer_report(report, f"markdown write failed: {exc}")

    json_text = json.dumps(
        recorded_report.to_dict(),
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    )
    try:
        json_temp = _write_temp_file(
            output_dir, _JSON_ARTIFACT_NAME, json_text + "\n", input_entries
        )
    except Exception as exc:
        try:
            md_temp.unlink(missing_ok=True)
        except Exception:
            pass
        return _blocked_writer_report(report, f"json write failed: {exc}")

    md_final = output_dir / _MARKDOWN_ARTIFACT_NAME
    json_final = output_dir / _JSON_ARTIFACT_NAME
    try:
        os.replace(md_temp, md_final)
        os.replace(json_temp, json_final)
    except Exception as exc:
        for p in (md_final, json_final, md_temp, json_temp):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        return _blocked_writer_report(report, f"artifact replacement failed: {exc}")

    return recorded_report
