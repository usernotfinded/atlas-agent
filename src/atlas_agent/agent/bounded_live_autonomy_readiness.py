"""Bounded live autonomy readiness gate (CAND-015) — evidence-only, simulated-only.

This module evaluates upstream CAND-004/CAND-005/CAND-006/CAND-007/CAND-008
artifacts by projection and CAND-015-owned static fixtures by closed schema,
then evaluates a strict fail-closed gate sequence for the L2/L3 autonomy
boundary. It performs no network calls, loads no credentials, and instantiates
no trading or risk objects.
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
    "operator_policy_blocked",
    "autonomy_policy_blocked",
    "risk_limit_blocked",
    "symbol_policy_blocked",
    "heartbeat_deadman_blocked",
    "audit_redaction_blocked",
    "l2_l3_boundary_blocked",
    "readiness_synthesized",
    "bounded_live_readiness_recorded",
)

GATE_SEQUENCE = (
    "schema_preflight",
    "cand004_projection_gate",
    "cand005_projection_gate",
    "cand006_projection_gate",
    "cand007_projection_gate",
    "cand008_projection_gate",
    "cross_artifact_correlation_gate",
    "bounded_autonomy_policy_gate",
    "risk_limit_gate",
    "symbol_allowlist_gate",
    "heartbeat_deadman_gate",
    "audit_redaction_gate",
    "l2_l3_boundary_gate",
    "readiness_synthesis_gate",
    "artifact_recording_gate",
)

EVIDENCE_ONLY_DISCLAIMER = (
    "Bounded live autonomy readiness evaluation (CAND-015) — evidence-only and simulated-only. "
    "bounded_live_readiness_recorded is evidence-recording status only. "
    "It is not live readiness, not trading safety, not profitability evidence, "
    "not permission to trade, and not authorization to submit orders. "
    "L3 bounded live autonomy remains a future research concept; this gate only records "
    "whether the supplied local evidence and policy fixtures satisfy the declared L2/L3 boundary."
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
    "CAND-015",
)

ARTIFACT_TYPE = "bounded_live_autonomy_readiness"
SCHEMA_VERSION = "bounded-live-autonomy-readiness.v1"
MODE = "evidence_only"
CANDIDATE = "CAND-015"

_CAND007_ACCEPTED_STATUS = "readiness_envelope_recorded"
_CAND008_ACCEPTED_STATUS = "operator_gate_recorded"

_JSON_ARTIFACT_NAME = "bounded-live-readiness.json"
_MARKDOWN_ARTIFACT_NAME = "bounded-live-readiness-report.md"

_TRADING_QUALITY_GATE_ARTIFACT_TYPE = "trading_quality_gate"
_TRADING_QUALITY_GATE_SCHEMA_VERSIONS = ("trading-quality-gate.v1", 1, "1")
_SHADOW_LIVE_COMPARISON_ARTIFACT_TYPE = "shadow_live_comparison"
_SHADOW_LIVE_COMPARISON_SCHEMA_VERSION = "shadow-live-comparison.v1"
_GATED_SUBMIT_CONFORMANCE_ARTIFACT_TYPE = "gated_submit_conformance"
_GATED_SUBMIT_CONFORMANCE_SCHEMA_VERSION = "gated-submit-conformance.v1"
_RUNTIME_READINESS_ENVELOPE_ARTIFACT_TYPE = "runtime_readiness_envelope"
_RUNTIME_READINESS_ENVELOPE_SCHEMA_VERSION = "runtime-readiness-envelope.v1"
_OPERATOR_APPROVAL_GATE_ARTIFACT_TYPE = "operator_approval_gate"
_OPERATOR_APPROVAL_GATE_SCHEMA_VERSION = "operator-approval-gate.v1"

_BOUNDED_AUTONOMY_POLICY_ARTIFACT_TYPE = "bounded_autonomy_policy_fixture"
_BOUNDED_AUTONOMY_POLICY_SCHEMA_VERSION = "bounded-autonomy-policy-fixture.v1"
_RISK_LIMIT_ARTIFACT_TYPE = "risk_limit_fixture"
_RISK_LIMIT_SCHEMA_VERSION = "risk-limit-fixture.v1"
_SYMBOL_ALLOWLIST_ARTIFACT_TYPE = "symbol_allowlist_fixture"
_SYMBOL_ALLOWLIST_SCHEMA_VERSION = "symbol-allowlist-fixture.v1"
_HEARTBEAT_DEADMAN_ARTIFACT_TYPE = "heartbeat_deadman_fixture"
_HEARTBEAT_DEADMAN_SCHEMA_VERSION = "heartbeat-deadman-fixture.v1"
_AUDIT_REDACTION_ARTIFACT_TYPE = "audit_redaction_fixture"
_AUDIT_REDACTION_SCHEMA_VERSION = "audit-redaction-fixture.v1"

_INPUT_LABELS = (
    "quality_gate",
    "shadow_comparison",
    "submit_conformance",
    "readiness_envelope",
    "operator_approval_gate",
    "bounded_autonomy_policy",
    "risk_limit",
    "symbol_allowlist",
    "heartbeat_deadman",
    "audit_redaction",
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

_CAND008_REQUIRED_ASSERTIONS = {
    "cand007_status_accepted",
    "cand007_mode_simulated_only",
    "cand007_blockers_empty",
    "cand007_safety_assertions_accepted",
    "operator_identity_valid",
    "approval_policy_fail_closed",
    "kill_switch_observed_blocked",
    "operator_acknowledgments_all_true",
    "audit_policy_fail_closed",
    "no_credentials_in_fixtures",
    "no_endpoints_in_fixtures",
    "no_account_ids_in_fixtures",
    "no_raw_upstream_leakage",
}


class BoundedLiveAutonomyReadinessValidationError(Exception):
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
class BoundedLiveAutonomyReadinessInputs:
    quality_gate_path: Path
    shadow_comparison_path: Path
    submit_conformance_path: Path
    readiness_envelope_path: Path
    operator_approval_gate_path: Path
    bounded_autonomy_policy_path: Path
    risk_limit_path: Path
    symbol_allowlist_path: Path
    heartbeat_deadman_path: Path
    audit_redaction_path: Path
    output_dir: Path | None
    as_of: str


@dataclass(frozen=True)
class BoundedLiveAutonomyReadinessReport:
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
    readiness_digest: str
    upstream_summaries: dict[str, Any]
    fixture_summaries: dict[str, Any]
    readiness_assertions: dict[str, bool]
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
            "input_fingerprints": self.input_fingerprints,
            "input_digest": self.input_digest,
            "readiness_digest": self.readiness_digest,
            "upstream_summaries": self.upstream_summaries,
            "fixture_summaries": self.fixture_summaries,
            "readiness_assertions": self.readiness_assertions,
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
        raise BoundedLiveAutonomyReadinessValidationError("as_of is not a string")
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise BoundedLiveAutonomyReadinessValidationError(
            f"as_of is not a valid ISO-8601 UTC timestamp: {value!r}"
        )
    return _format_utc_timestamp(parsed)


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise BoundedLiveAutonomyReadinessValidationError(f"{name} must be a string")
    return value


def _require_exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise BoundedLiveAutonomyReadinessValidationError(
            f"{label} contains unknown keys: {sorted(unknown)}"
        )


def _require_nonempty_bounded_id(value: str, name: str) -> None:
    if not value:
        raise BoundedLiveAutonomyReadinessValidationError(f"{name} must be non-empty")
    if len(value) > 128:
        raise BoundedLiveAutonomyReadinessValidationError(f"{name} exceeds 128 characters")
    if not _ID_RE.match(value):
        raise BoundedLiveAutonomyReadinessValidationError(f"{name} contains invalid characters")


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
        raise BoundedLiveAutonomyReadinessValidationError(f"{label} file not found: {path.name}")
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise BoundedLiveAutonomyReadinessValidationError(f"failed to read {label}: {exc}") from None
    if not text.strip():
        raise BoundedLiveAutonomyReadinessValidationError(f"{label} file is empty")
    try:
        data = json.loads(text, parse_constant=lambda c: c)
    except json.JSONDecodeError as exc:
        raise BoundedLiveAutonomyReadinessValidationError(f"{label} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise BoundedLiveAutonomyReadinessValidationError(f"{label} is not a JSON object")
    raw_text = text.lower()
    for constant in ("nan", "infinity", "-infinity"):
        if constant in raw_text:
            raise BoundedLiveAutonomyReadinessValidationError(
                f"{label} contains forbidden JSON constant: {constant}"
            )
    return data


def _input_fingerprints(normalized: dict[str, Any]) -> dict[str, str]:
    return {label: fingerprint_json(value) for label, value in normalized.items()}


def _compute_input_digest(as_of: str, fingerprints: dict[str, str]) -> str:
    payload = {"as_of": as_of}
    for label in _INPUT_LABELS:
        payload[label] = fingerprints[label]
    return fingerprint_json(payload)


def _compute_readiness_digest(
    as_of: str,
    fingerprints: dict[str, str],
    upstream_summaries: dict[str, Any],
    readiness_assertions: dict[str, bool],
) -> str:
    payload = {
        "as_of": as_of,
        "fingerprints": {label: fingerprints.get(label, "") for label in _INPUT_LABELS},
        "upstream_summaries": upstream_summaries,
        "readiness_assertions": readiness_assertions,
    }
    return fingerprint_json(payload)


def _evaluation_id(input_digest: str) -> str:
    return f"blar-{input_digest.replace('sha256:', '')[:24]}"


def _redact_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.name


def _resolve_unique_id(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.resolve().stat()
        return (stat.st_dev, stat.st_ino)
    except Exception:
        return None


def _check_path_aliasing(inputs: BoundedLiveAutonomyReadinessInputs, output_dir: Path) -> None:
    """Fail closed if an input path aliases the output directory."""
    output_dir_id = _resolve_unique_id(output_dir)
    if output_dir_id is None:
        return
    input_paths = [
        inputs.quality_gate_path,
        inputs.shadow_comparison_path,
        inputs.submit_conformance_path,
        inputs.readiness_envelope_path,
        inputs.operator_approval_gate_path,
        inputs.bounded_autonomy_policy_path,
        inputs.risk_limit_path,
        inputs.symbol_allowlist_path,
        inputs.heartbeat_deadman_path,
        inputs.audit_redaction_path,
    ]
    for path in input_paths:
        path_id = _resolve_unique_id(path)
        if path_id is not None and path_id == output_dir_id:
            raise BoundedLiveAutonomyReadinessValidationError(
                f"output_dir aliases input path: {path.name}"
            )


def _parse_or_fail(value: str, label: str) -> datetime:
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise BoundedLiveAutonomyReadinessValidationError(
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
        raise BoundedLiveAutonomyReadinessValidationError("quality_gate artifact_type mismatch")
    if schema_version not in _TRADING_QUALITY_GATE_SCHEMA_VERSIONS:
        raise BoundedLiveAutonomyReadinessValidationError("quality_gate schema_version mismatch")
    if not isinstance(blockers, list):
        raise BoundedLiveAutonomyReadinessValidationError("quality_gate blockers must be a list")

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
        raise BoundedLiveAutonomyReadinessValidationError("shadow_comparison artifact_type mismatch")
    if schema_version != _SHADOW_LIVE_COMPARISON_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError("shadow_comparison schema_version mismatch")
    if not isinstance(freshness_assessment, dict):
        raise BoundedLiveAutonomyReadinessValidationError(
            "shadow_comparison freshness_assessment must be an object"
        )
    if not isinstance(blockers, list):
        raise BoundedLiveAutonomyReadinessValidationError("shadow_comparison blockers must be a list")

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
    data: dict[str, Any], cand015_as_of: str
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
        raise BoundedLiveAutonomyReadinessValidationError("submit_conformance artifact_type mismatch")
    if schema_version != _GATED_SUBMIT_CONFORMANCE_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError("submit_conformance schema_version mismatch")
    if candidate != "CAND-006":
        raise BoundedLiveAutonomyReadinessValidationError("submit_conformance candidate must be CAND-006")
    if mode != "simulated_only":
        raise BoundedLiveAutonomyReadinessValidationError("submit_conformance mode must be 'simulated_only'")
    if not isinstance(safety_assertions, dict):
        raise BoundedLiveAutonomyReadinessValidationError(
            "submit_conformance safety_assertions must be an object"
        )
    if not all(isinstance(v, bool) and v for v in safety_assertions.values()):
        raise BoundedLiveAutonomyReadinessValidationError(
            "all submit_conformance safety_assertions must be true"
        )
    if not isinstance(dry_run_request, dict):
        raise BoundedLiveAutonomyReadinessValidationError(
            "submit_conformance dry_run_request must be an object"
        )
    transmission = dry_run_request.get("transmission")
    if not isinstance(transmission, dict):
        raise BoundedLiveAutonomyReadinessValidationError(
            "submit_conformance dry_run_request.transmission must be an object"
        )
    if not isinstance(transmission.get("allowed"), bool):
        raise BoundedLiveAutonomyReadinessValidationError(
            "submit_conformance dry_run_request.transmission.allowed must be a boolean"
        )
    for field_name in ("broker_adapter", "provider"):
        value = transmission.get(field_name)
        if value is not None and not isinstance(value, str):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"submit_conformance dry_run_request.transmission.{field_name} must be null or a string"
            )
    if not isinstance(blockers, list):
        raise BoundedLiveAutonomyReadinessValidationError("submit_conformance blockers must be a list")

    as_of_dt = _parse_or_fail(as_of, "submit_conformance.as_of")
    cand015_dt = _parse_iso_timestamp(cand015_as_of)
    if cand015_dt is not None and as_of_dt > cand015_dt:
        raise BoundedLiveAutonomyReadinessValidationError(
            "submit_conformance as_of is later than CAND-015 as_of"
        )
    if cand015_dt is not None:
        age_hours = (cand015_dt - as_of_dt).total_seconds() / 3600.0
        if age_hours > _MAX_EVIDENCE_AGE_HOURS:
            raise BoundedLiveAutonomyReadinessValidationError(
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
    data: dict[str, Any], cand015_as_of: str
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
        raise BoundedLiveAutonomyReadinessValidationError(
            "readiness_envelope artifact_type mismatch"
        )
    if schema_version != _RUNTIME_READINESS_ENVELOPE_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError(
            "readiness_envelope schema_version mismatch"
        )
    if candidate != "CAND-007":
        raise BoundedLiveAutonomyReadinessValidationError(
            "readiness_envelope candidate must be CAND-007"
        )
    if mode != "simulated_only":
        raise BoundedLiveAutonomyReadinessValidationError(
            "readiness_envelope mode must be 'simulated_only'"
        )
    if not isinstance(exit_code, int) or exit_code != 0:
        raise BoundedLiveAutonomyReadinessValidationError("readiness_envelope exit_code must be 0")
    if not isinstance(blockers, list):
        raise BoundedLiveAutonomyReadinessValidationError(
            "readiness_envelope blockers must be a list"
        )
    if not isinstance(envelope_assertions, dict):
        raise BoundedLiveAutonomyReadinessValidationError(
            "readiness_envelope envelope_assertions must be an object"
        )

    missing_assertions = _CAND007_REQUIRED_ASSERTIONS - set(envelope_assertions)
    if missing_assertions:
        raise BoundedLiveAutonomyReadinessValidationError(
            f"readiness_envelope missing required envelope_assertions: {sorted(missing_assertions)}"
        )
    if not all(
        isinstance(envelope_assertions[k], bool) and envelope_assertions[k]
        for k in _CAND007_REQUIRED_ASSERTIONS
    ):
        raise BoundedLiveAutonomyReadinessValidationError(
            "all required readiness_envelope envelope_assertions must be true"
        )

    as_of_dt = _parse_or_fail(as_of, "readiness_envelope.as_of")
    cand015_dt = _parse_iso_timestamp(cand015_as_of)
    if cand015_dt is not None and as_of_dt > cand015_dt:
        raise BoundedLiveAutonomyReadinessValidationError(
            "readiness_envelope as_of is later than CAND-015 as_of"
        )
    if cand015_dt is not None:
        age_hours = (cand015_dt - as_of_dt).total_seconds() / 3600.0
        if age_hours > _MAX_EVIDENCE_AGE_HOURS:
            raise BoundedLiveAutonomyReadinessValidationError(
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


def _validate_operator_approval_gate(
    data: dict[str, Any], cand015_as_of: str
) -> dict[str, Any]:
    """Project CAND-008 to accepted keys and validate the approval gate assertions."""
    artifact_type = _require_string(
        data.get("artifact_type"), "operator_approval_gate.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "operator_approval_gate.schema_version"
    )
    candidate = _require_string(data.get("candidate"), "operator_approval_gate.candidate")
    mode = _require_string(data.get("mode"), "operator_approval_gate.mode")
    status = _require_string(data.get("status"), "operator_approval_gate.status")
    exit_code = data.get("exit_code")
    as_of = _require_string(data.get("as_of"), "operator_approval_gate.as_of")
    run_id = data.get("run_id")
    symbol = data.get("symbol")
    blockers = data.get("blockers")
    approval_gate_assertions = data.get("approval_gate_assertions")

    if artifact_type != _OPERATOR_APPROVAL_GATE_ARTIFACT_TYPE:
        raise BoundedLiveAutonomyReadinessValidationError(
            "operator_approval_gate artifact_type mismatch"
        )
    if schema_version != _OPERATOR_APPROVAL_GATE_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError(
            "operator_approval_gate schema_version mismatch"
        )
    if candidate != "CAND-008":
        raise BoundedLiveAutonomyReadinessValidationError(
            "operator_approval_gate candidate must be CAND-008"
        )
    if mode != "evidence_only":
        raise BoundedLiveAutonomyReadinessValidationError(
            "operator_approval_gate mode must be 'evidence_only'"
        )
    if not isinstance(exit_code, int) or exit_code != 0:
        raise BoundedLiveAutonomyReadinessValidationError(
            "operator_approval_gate exit_code must be 0"
        )
    if not isinstance(blockers, list):
        raise BoundedLiveAutonomyReadinessValidationError(
            "operator_approval_gate blockers must be a list"
        )
    if not isinstance(approval_gate_assertions, dict):
        raise BoundedLiveAutonomyReadinessValidationError(
            "operator_approval_gate approval_gate_assertions must be an object"
        )

    missing_assertions = _CAND008_REQUIRED_ASSERTIONS - set(approval_gate_assertions)
    if missing_assertions:
        raise BoundedLiveAutonomyReadinessValidationError(
            f"operator_approval_gate missing required approval_gate_assertions: {sorted(missing_assertions)}"
        )
    if not all(
        isinstance(approval_gate_assertions[k], bool) and approval_gate_assertions[k]
        for k in _CAND008_REQUIRED_ASSERTIONS
    ):
        raise BoundedLiveAutonomyReadinessValidationError(
            "all required operator_approval_gate approval_gate_assertions must be true"
        )

    as_of_dt = _parse_or_fail(as_of, "operator_approval_gate.as_of")
    cand015_dt = _parse_iso_timestamp(cand015_as_of)
    if cand015_dt is not None and as_of_dt > cand015_dt:
        raise BoundedLiveAutonomyReadinessValidationError(
            "operator_approval_gate as_of is later than CAND-015 as_of"
        )
    if cand015_dt is not None:
        age_hours = (cand015_dt - as_of_dt).total_seconds() / 3600.0
        if age_hours > _MAX_EVIDENCE_AGE_HOURS:
            raise BoundedLiveAutonomyReadinessValidationError(
                "operator_approval_gate evidence is older than 24 hours"
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
        "approval_gate_assertions": approval_gate_assertions,
    }


def _validate_bounded_autonomy_policy(
    data: dict[str, Any], as_of: str
) -> dict[str, Any]:
    """Closed-schema validation for the bounded autonomy policy fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "policy_scope",
        "l3_autonomy_enabled",
        "live_submit_enabled_by_default",
        "provider_output_authoritative",
        "manual_approval_required",
        "unattended_operation_allowed",
        "auto_approval_allowed",
        "requires_explicit_opt_in",
        "requires_active_operator_oversight",
        "requires_paper_validation",
        "min_paper_validation_runs",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "bounded_autonomy_policy")

    artifact_type = _require_string(
        data.get("artifact_type"), "bounded_autonomy_policy.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "bounded_autonomy_policy.schema_version"
    )
    if artifact_type != _BOUNDED_AUTONOMY_POLICY_ARTIFACT_TYPE:
        raise BoundedLiveAutonomyReadinessValidationError(
            "bounded_autonomy_policy artifact_type mismatch"
        )
    if schema_version != _BOUNDED_AUTONOMY_POLICY_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError(
            "bounded_autonomy_policy schema_version mismatch"
        )

    policy_scope = _require_string(
        data.get("policy_scope"), "bounded_autonomy_policy.policy_scope"
    )
    if policy_scope != "l2_l3_readiness_evaluation":
        raise BoundedLiveAutonomyReadinessValidationError(
            "bounded_autonomy_policy policy_scope must be 'l2_l3_readiness_evaluation'"
        )

    for field_name in (
        "l3_autonomy_enabled",
        "live_submit_enabled_by_default",
        "provider_output_authoritative",
        "manual_approval_required",
        "unattended_operation_allowed",
        "auto_approval_allowed",
        "requires_explicit_opt_in",
        "requires_active_operator_oversight",
        "requires_paper_validation",
    ):
        if not isinstance(data.get(field_name), bool):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"bounded_autonomy_policy {field_name} must be a boolean"
            )

    min_paper_validation_runs = data.get("min_paper_validation_runs")
    if not isinstance(min_paper_validation_runs, int) or isinstance(min_paper_validation_runs, bool):
        raise BoundedLiveAutonomyReadinessValidationError(
            "bounded_autonomy_policy min_paper_validation_runs must be an integer"
        )
    if min_paper_validation_runs < 0:
        raise BoundedLiveAutonomyReadinessValidationError(
            "bounded_autonomy_policy min_paper_validation_runs must be non-negative"
        )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "bounded_autonomy_policy.expires_at"),
        "bounded_autonomy_policy.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise BoundedLiveAutonomyReadinessValidationError(
            "bounded_autonomy_policy expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "policy_scope": policy_scope,
        "l3_autonomy_enabled": data["l3_autonomy_enabled"],
        "live_submit_enabled_by_default": data["live_submit_enabled_by_default"],
        "provider_output_authoritative": data["provider_output_authoritative"],
        "manual_approval_required": data["manual_approval_required"],
        "unattended_operation_allowed": data["unattended_operation_allowed"],
        "auto_approval_allowed": data["auto_approval_allowed"],
        "requires_explicit_opt_in": data["requires_explicit_opt_in"],
        "requires_active_operator_oversight": data["requires_active_operator_oversight"],
        "requires_paper_validation": data["requires_paper_validation"],
        "min_paper_validation_runs": min_paper_validation_runs,
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_risk_limit(data: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Closed-schema validation for the risk limit fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "max_single_order_notional",
        "max_position_notional_per_symbol",
        "max_total_net_exposure_pct",
        "max_daily_loss_notional",
        "max_orders_per_interval",
        "quote_freshness_required_seconds",
        "allowed_sides",
        "allowed_order_types",
        "leverage_allowed",
        "shorting_allowed",
        "options_allowed",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "risk_limit")

    artifact_type = _require_string(
        data.get("artifact_type"), "risk_limit.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "risk_limit.schema_version"
    )
    if artifact_type != _RISK_LIMIT_ARTIFACT_TYPE:
        raise BoundedLiveAutonomyReadinessValidationError("risk_limit artifact_type mismatch")
    if schema_version != _RISK_LIMIT_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError("risk_limit schema_version mismatch")

    for field_name in (
        "max_single_order_notional",
        "max_position_notional_per_symbol",
        "max_total_net_exposure_pct",
        "max_daily_loss_notional",
    ):
        value = _require_string(data.get(field_name), f"risk_limit.{field_name}")
        if value.startswith("-"):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"risk_limit {field_name} must be non-negative"
            )
        if not value.replace(".", "", 1).isdigit():
            raise BoundedLiveAutonomyReadinessValidationError(
                f"risk_limit {field_name} must be a non-negative decimal string"
            )

    for field_name in (
        "max_orders_per_interval",
        "quote_freshness_required_seconds",
    ):
        value = data.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"risk_limit {field_name} must be an integer"
            )
        if value <= 0:
            raise BoundedLiveAutonomyReadinessValidationError(
                f"risk_limit {field_name} must be positive"
            )

    for field_name in ("allowed_sides", "allowed_order_types"):
        value = data.get(field_name)
        if not isinstance(value, list):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"risk_limit {field_name} must be a list"
            )
        if not all(isinstance(v, str) for v in value):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"risk_limit {field_name} must be strings"
            )

    for field_name in (
        "leverage_allowed",
        "shorting_allowed",
        "options_allowed",
    ):
        if not isinstance(data.get(field_name), bool):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"risk_limit {field_name} must be a boolean"
            )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "risk_limit.expires_at"),
        "risk_limit.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise BoundedLiveAutonomyReadinessValidationError(
            "risk_limit expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "max_single_order_notional": data["max_single_order_notional"],
        "max_position_notional_per_symbol": data["max_position_notional_per_symbol"],
        "max_total_net_exposure_pct": data["max_total_net_exposure_pct"],
        "max_daily_loss_notional": data["max_daily_loss_notional"],
        "max_orders_per_interval": data["max_orders_per_interval"],
        "quote_freshness_required_seconds": data["quote_freshness_required_seconds"],
        "allowed_sides": data["allowed_sides"],
        "allowed_order_types": data["allowed_order_types"],
        "leverage_allowed": data["leverage_allowed"],
        "shorting_allowed": data["shorting_allowed"],
        "options_allowed": data["options_allowed"],
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_symbol_allowlist(data: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Closed-schema validation for the symbol allowlist fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "allowlist_mode",
        "allowed_symbols",
        "blocked_symbols",
        "allow_empty_blocklist",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "symbol_allowlist")

    artifact_type = _require_string(
        data.get("artifact_type"), "symbol_allowlist.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "symbol_allowlist.schema_version"
    )
    if artifact_type != _SYMBOL_ALLOWLIST_ARTIFACT_TYPE:
        raise BoundedLiveAutonomyReadinessValidationError(
            "symbol_allowlist artifact_type mismatch"
        )
    if schema_version != _SYMBOL_ALLOWLIST_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError(
            "symbol_allowlist schema_version mismatch"
        )

    allowlist_mode = _require_string(
        data.get("allowlist_mode"), "symbol_allowlist.allowlist_mode"
    )
    if allowlist_mode != "explicit_allowlist":
        raise BoundedLiveAutonomyReadinessValidationError(
            "symbol_allowlist allowlist_mode must be 'explicit_allowlist'"
        )

    allowed_symbols = data.get("allowed_symbols")
    if not isinstance(allowed_symbols, list):
        raise BoundedLiveAutonomyReadinessValidationError(
            "symbol_allowlist allowed_symbols must be a list"
        )
    if not allowed_symbols:
        raise BoundedLiveAutonomyReadinessValidationError(
            "symbol_allowlist allowed_symbols must not be empty"
        )
    for symbol in allowed_symbols:
        if not isinstance(symbol, str):
            raise BoundedLiveAutonomyReadinessValidationError(
                "symbol_allowlist allowed_symbols must be strings"
            )
        if not _SYMBOL_RE.match(symbol):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"symbol_allowlist invalid symbol: {symbol}"
            )

    blocked_symbols = data.get("blocked_symbols")
    if not isinstance(blocked_symbols, list):
        raise BoundedLiveAutonomyReadinessValidationError(
            "symbol_allowlist blocked_symbols must be a list"
        )
    for symbol in blocked_symbols:
        if not isinstance(symbol, str):
            raise BoundedLiveAutonomyReadinessValidationError(
                "symbol_allowlist blocked_symbols must be strings"
            )

    if not isinstance(data.get("allow_empty_blocklist"), bool):
        raise BoundedLiveAutonomyReadinessValidationError(
            "symbol_allowlist allow_empty_blocklist must be a boolean"
        )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "symbol_allowlist.expires_at"),
        "symbol_allowlist.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise BoundedLiveAutonomyReadinessValidationError(
            "symbol_allowlist expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "allowlist_mode": allowlist_mode,
        "allowed_symbols": allowed_symbols,
        "blocked_symbols": blocked_symbols,
        "allow_empty_blocklist": data["allow_empty_blocklist"],
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_heartbeat_deadman(data: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Closed-schema validation for the heartbeat/deadman fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "heartbeat_required",
        "heartbeat_interval_seconds",
        "deadman_required",
        "deadman_ttl_seconds",
        "missing_heartbeat_fails_closed",
        "stale_heartbeat_fails_closed",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "heartbeat_deadman")

    artifact_type = _require_string(
        data.get("artifact_type"), "heartbeat_deadman.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "heartbeat_deadman.schema_version"
    )
    if artifact_type != _HEARTBEAT_DEADMAN_ARTIFACT_TYPE:
        raise BoundedLiveAutonomyReadinessValidationError(
            "heartbeat_deadman artifact_type mismatch"
        )
    if schema_version != _HEARTBEAT_DEADMAN_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError(
            "heartbeat_deadman schema_version mismatch"
        )

    for field_name in (
        "heartbeat_required",
        "deadman_required",
        "missing_heartbeat_fails_closed",
        "stale_heartbeat_fails_closed",
    ):
        if not isinstance(data.get(field_name), bool):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"heartbeat_deadman {field_name} must be a boolean"
            )

    for field_name in (
        "heartbeat_interval_seconds",
        "deadman_ttl_seconds",
    ):
        value = data.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"heartbeat_deadman {field_name} must be an integer"
            )
        if value <= 0:
            raise BoundedLiveAutonomyReadinessValidationError(
                f"heartbeat_deadman {field_name} must be positive"
            )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "heartbeat_deadman.expires_at"),
        "heartbeat_deadman.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise BoundedLiveAutonomyReadinessValidationError(
            "heartbeat_deadman expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "heartbeat_required": data["heartbeat_required"],
        "heartbeat_interval_seconds": data["heartbeat_interval_seconds"],
        "deadman_required": data["deadman_required"],
        "deadman_ttl_seconds": data["deadman_ttl_seconds"],
        "missing_heartbeat_fails_closed": data["missing_heartbeat_fails_closed"],
        "stale_heartbeat_fails_closed": data["stale_heartbeat_fails_closed"],
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_audit_redaction(data: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Closed-schema validation for the audit redaction fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "redacts_secrets",
        "redacts_api_keys",
        "redacts_account_ids",
        "redacts_raw_broker_payloads",
        "redacts_raw_provider_output",
        "redacts_paths",
        "redacts_exception_text",
        "audit_hash_chain_required",
        "manifest_required",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "audit_redaction")

    artifact_type = _require_string(
        data.get("artifact_type"), "audit_redaction.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "audit_redaction.schema_version"
    )
    if artifact_type != _AUDIT_REDACTION_ARTIFACT_TYPE:
        raise BoundedLiveAutonomyReadinessValidationError(
            "audit_redaction artifact_type mismatch"
        )
    if schema_version != _AUDIT_REDACTION_SCHEMA_VERSION:
        raise BoundedLiveAutonomyReadinessValidationError(
            "audit_redaction schema_version mismatch"
        )

    for field_name in (
        "redacts_secrets",
        "redacts_api_keys",
        "redacts_account_ids",
        "redacts_raw_broker_payloads",
        "redacts_raw_provider_output",
        "redacts_paths",
        "redacts_exception_text",
        "audit_hash_chain_required",
        "manifest_required",
    ):
        if not isinstance(data.get(field_name), bool):
            raise BoundedLiveAutonomyReadinessValidationError(
                f"audit_redaction {field_name} must be a boolean"
            )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "audit_redaction.expires_at"),
        "audit_redaction.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise BoundedLiveAutonomyReadinessValidationError(
            "audit_redaction expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "redacts_secrets": data["redacts_secrets"],
        "redacts_api_keys": data["redacts_api_keys"],
        "redacts_account_ids": data["redacts_account_ids"],
        "redacts_raw_broker_payloads": data["redacts_raw_broker_payloads"],
        "redacts_raw_provider_output": data["redacts_raw_provider_output"],
        "redacts_paths": data["redacts_paths"],
        "redacts_exception_text": data["redacts_exception_text"],
        "audit_hash_chain_required": data["audit_hash_chain_required"],
        "manifest_required": data["manifest_required"],
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _load_and_validate_all(
    inputs: BoundedLiveAutonomyReadinessInputs,
) -> dict[str, Any]:
    """Load and closed-schema validate every input fixture."""
    paths = {
        "quality_gate": inputs.quality_gate_path,
        "shadow_comparison": inputs.shadow_comparison_path,
        "submit_conformance": inputs.submit_conformance_path,
        "readiness_envelope": inputs.readiness_envelope_path,
        "operator_approval_gate": inputs.operator_approval_gate_path,
        "bounded_autonomy_policy": inputs.bounded_autonomy_policy_path,
        "risk_limit": inputs.risk_limit_path,
        "symbol_allowlist": inputs.symbol_allowlist_path,
        "heartbeat_deadman": inputs.heartbeat_deadman_path,
        "audit_redaction": inputs.audit_redaction_path,
    }
    fixture_labels = {
        "bounded_autonomy_policy",
        "risk_limit",
        "symbol_allowlist",
        "heartbeat_deadman",
        "audit_redaction",
    }
    raw: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        raw[label] = _load_json_object(path, label)
        secrets = _universal_reject_scan(
            raw[label],
            label,
            include_forbidden_keys=(label in fixture_labels),
        )
        if secrets:
            raise BoundedLiveAutonomyReadinessValidationError(
                "secret-like content rejected: " + "; ".join(secrets)
            )

    as_of = inputs.as_of
    normalized: dict[str, Any] = {
        "quality_gate": _validate_quality_gate(raw["quality_gate"]),
        "shadow_comparison": _validate_shadow_comparison(raw["shadow_comparison"]),
        "submit_conformance": _validate_submit_conformance(raw["submit_conformance"], as_of),
        "readiness_envelope": _validate_readiness_envelope(raw["readiness_envelope"], as_of),
        "operator_approval_gate": _validate_operator_approval_gate(raw["operator_approval_gate"], as_of),
        "bounded_autonomy_policy": _validate_bounded_autonomy_policy(raw["bounded_autonomy_policy"], as_of),
        "risk_limit": _validate_risk_limit(raw["risk_limit"], as_of),
        "symbol_allowlist": _validate_symbol_allowlist(raw["symbol_allowlist"], as_of),
        "heartbeat_deadman": _validate_heartbeat_deadman(raw["heartbeat_deadman"], as_of),
        "audit_redaction": _validate_audit_redaction(raw["audit_redaction"], as_of),
    }
    return normalized


def _build_upstream_summaries(normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "quality_gate": {
            "artifact_type": normalized["quality_gate"]["artifact_type"],
            "schema_version": normalized["quality_gate"]["schema_version"],
            "run_id": normalized["quality_gate"]["run_id"],
            "symbol": normalized["quality_gate"]["symbol"],
            "quality_state": normalized["quality_gate"]["quality_state"],
            "blocker_count": len(normalized["quality_gate"]["blockers"]),
        },
        "shadow_comparison": {
            "artifact_type": normalized["shadow_comparison"]["artifact_type"],
            "schema_version": normalized["shadow_comparison"]["schema_version"],
            "run_id": normalized["shadow_comparison"]["run_id"],
            "symbol": normalized["shadow_comparison"]["symbol"],
            "status": normalized["shadow_comparison"]["status"],
            "blocker_count": len(normalized["shadow_comparison"]["blockers"]),
        },
        "submit_conformance": {
            "artifact_type": normalized["submit_conformance"]["artifact_type"],
            "schema_version": normalized["submit_conformance"]["schema_version"],
            "run_id": normalized["submit_conformance"]["run_id"],
            "symbol": normalized["submit_conformance"]["symbol"],
            "status": normalized["submit_conformance"]["status"],
            "blocker_count": len(normalized["submit_conformance"]["blockers"]),
            "transmission_allowed": normalized["submit_conformance"]["dry_run_request"]["transmission"]["allowed"],
        },
        "readiness_envelope": {
            "artifact_type": normalized["readiness_envelope"]["artifact_type"],
            "schema_version": normalized["readiness_envelope"]["schema_version"],
            "run_id": normalized["readiness_envelope"]["run_id"],
            "symbol": normalized["readiness_envelope"]["symbol"],
            "status": normalized["readiness_envelope"]["status"],
            "blocker_count": len(normalized["readiness_envelope"]["blockers"]),
        },
        "operator_approval_gate": {
            "artifact_type": normalized["operator_approval_gate"]["artifact_type"],
            "schema_version": normalized["operator_approval_gate"]["schema_version"],
            "run_id": normalized["operator_approval_gate"]["run_id"],
            "symbol": normalized["operator_approval_gate"]["symbol"],
            "status": normalized["operator_approval_gate"]["status"],
            "blocker_count": len(normalized["operator_approval_gate"]["blockers"]),
        },
    }


def _build_fixture_summaries(normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "bounded_autonomy_policy": {
            "policy_scope": normalized["bounded_autonomy_policy"]["policy_scope"],
            "l3_autonomy_enabled": normalized["bounded_autonomy_policy"]["l3_autonomy_enabled"],
            "live_submit_enabled_by_default": normalized["bounded_autonomy_policy"]["live_submit_enabled_by_default"],
            "provider_output_authoritative": normalized["bounded_autonomy_policy"]["provider_output_authoritative"],
            "manual_approval_required": normalized["bounded_autonomy_policy"]["manual_approval_required"],
            "unattended_operation_allowed": normalized["bounded_autonomy_policy"]["unattended_operation_allowed"],
            "auto_approval_allowed": normalized["bounded_autonomy_policy"]["auto_approval_allowed"],
            "requires_explicit_opt_in": normalized["bounded_autonomy_policy"]["requires_explicit_opt_in"],
            "requires_active_operator_oversight": normalized["bounded_autonomy_policy"]["requires_active_operator_oversight"],
            "requires_paper_validation": normalized["bounded_autonomy_policy"]["requires_paper_validation"],
            "min_paper_validation_runs": normalized["bounded_autonomy_policy"]["min_paper_validation_runs"],
        },
        "risk_limit": {
            "max_single_order_notional": normalized["risk_limit"]["max_single_order_notional"],
            "max_position_notional_per_symbol": normalized["risk_limit"]["max_position_notional_per_symbol"],
            "max_total_net_exposure_pct": normalized["risk_limit"]["max_total_net_exposure_pct"],
            "max_daily_loss_notional": normalized["risk_limit"]["max_daily_loss_notional"],
            "max_orders_per_interval": normalized["risk_limit"]["max_orders_per_interval"],
            "quote_freshness_required_seconds": normalized["risk_limit"]["quote_freshness_required_seconds"],
            "allowed_sides": normalized["risk_limit"]["allowed_sides"],
            "allowed_order_types": normalized["risk_limit"]["allowed_order_types"],
            "leverage_allowed": normalized["risk_limit"]["leverage_allowed"],
            "shorting_allowed": normalized["risk_limit"]["shorting_allowed"],
            "options_allowed": normalized["risk_limit"]["options_allowed"],
        },
        "symbol_allowlist": {
            "allowlist_mode": normalized["symbol_allowlist"]["allowlist_mode"],
            "allowed_symbol_count": len(normalized["symbol_allowlist"]["allowed_symbols"]),
            "blocked_symbol_count": len(normalized["symbol_allowlist"]["blocked_symbols"]),
        },
        "heartbeat_deadman": {
            "heartbeat_required": normalized["heartbeat_deadman"]["heartbeat_required"],
            "heartbeat_interval_seconds": normalized["heartbeat_deadman"]["heartbeat_interval_seconds"],
            "deadman_required": normalized["heartbeat_deadman"]["deadman_required"],
            "deadman_ttl_seconds": normalized["heartbeat_deadman"]["deadman_ttl_seconds"],
            "missing_heartbeat_fails_closed": normalized["heartbeat_deadman"]["missing_heartbeat_fails_closed"],
            "stale_heartbeat_fails_closed": normalized["heartbeat_deadman"]["stale_heartbeat_fails_closed"],
        },
        "audit_redaction": {
            "redacts_secrets": normalized["audit_redaction"]["redacts_secrets"],
            "redacts_api_keys": normalized["audit_redaction"]["redacts_api_keys"],
            "redacts_account_ids": normalized["audit_redaction"]["redacts_account_ids"],
            "redacts_raw_broker_payloads": normalized["audit_redaction"]["redacts_raw_broker_payloads"],
            "redacts_raw_provider_output": normalized["audit_redaction"]["redacts_raw_provider_output"],
            "audit_hash_chain_required": normalized["audit_redaction"]["audit_hash_chain_required"],
            "manifest_required": normalized["audit_redaction"]["manifest_required"],
        },
    }


def _evaluate_schema_preflight(normalized: dict[str, Any]) -> GateResult:
    return GateResult(
        gate_id="schema_preflight",
        status="pass",
        reason="all inputs passed closed-schema validation",
        details={"input_count": len(_INPUT_LABELS)},
    )


def _evaluate_cand004_projection_gate(normalized: dict[str, Any]) -> GateResult:
    blockers = normalized["quality_gate"]["blockers"]
    if blockers:
        return GateResult(
            gate_id="cand004_projection_gate",
            status="fail",
            reason="CAND-004 trading-quality gate has blockers",
            details={"blockers": blockers},
        )
    return GateResult(
        gate_id="cand004_projection_gate",
        status="pass",
        reason="CAND-004 trading-quality gate has no blockers",
        details={},
    )


def _evaluate_cand005_projection_gate(normalized: dict[str, Any]) -> GateResult:
    blockers = normalized["shadow_comparison"]["blockers"]
    if blockers:
        return GateResult(
            gate_id="cand005_projection_gate",
            status="fail",
            reason="CAND-005 shadow-live comparison has blockers",
            details={"blockers": blockers},
        )
    return GateResult(
        gate_id="cand005_projection_gate",
        status="pass",
        reason="CAND-005 shadow-live comparison has no blockers",
        details={},
    )


def _evaluate_cand006_projection_gate(normalized: dict[str, Any]) -> GateResult:
    blockers = normalized["submit_conformance"]["blockers"]
    transmission_allowed = normalized["submit_conformance"]["dry_run_request"]["transmission"]["allowed"]
    if blockers:
        return GateResult(
            gate_id="cand006_projection_gate",
            status="fail",
            reason="CAND-006 gated submit conformance has blockers",
            details={"blockers": blockers},
        )
    if transmission_allowed:
        return GateResult(
            gate_id="cand006_projection_gate",
            status="fail",
            reason="CAND-006 dry-run transmission must be blocked",
            details={"transmission_allowed": transmission_allowed},
        )
    return GateResult(
        gate_id="cand006_projection_gate",
        status="pass",
        reason="CAND-006 gated submit conformance has no blockers and transmission is blocked",
        details={},
    )


def _evaluate_cand007_projection_gate(normalized: dict[str, Any]) -> GateResult:
    blockers = normalized["readiness_envelope"]["blockers"]
    if blockers:
        return GateResult(
            gate_id="cand007_projection_gate",
            status="fail",
            reason="CAND-007 runtime readiness envelope has blockers",
            details={"blockers": blockers},
        )
    return GateResult(
        gate_id="cand007_projection_gate",
        status="pass",
        reason="CAND-007 runtime readiness envelope has no blockers",
        details={},
    )


def _evaluate_cand008_projection_gate(normalized: dict[str, Any]) -> GateResult:
    blockers = normalized["operator_approval_gate"]["blockers"]
    if blockers:
        return GateResult(
            gate_id="cand008_projection_gate",
            status="fail",
            reason="CAND-008 operator approval gate has blockers",
            details={"blockers": blockers},
        )
    return GateResult(
        gate_id="cand008_projection_gate",
        status="pass",
        reason="CAND-008 operator approval gate has no blockers",
        details={},
    )


def _evaluate_cross_artifact_correlation_gate(normalized: dict[str, Any]) -> GateResult:
    symbol = normalized["quality_gate"]["symbol"]
    mismatched: list[str] = []
    for label in ("shadow_comparison", "submit_conformance", "readiness_envelope"):
        if normalized[label]["symbol"] != symbol:
            mismatched.append(label)
    run_id = normalized["quality_gate"]["run_id"]
    for label in ("shadow_comparison", "submit_conformance", "readiness_envelope"):
        if normalized[label]["run_id"] != run_id:
            mismatched.append(label)
    if mismatched:
        return GateResult(
            gate_id="cross_artifact_correlation_gate",
            status="fail",
            reason="upstream artifact symbol/run_id mismatch",
            details={"mismatched_labels": sorted(set(mismatched))},
        )
    return GateResult(
        gate_id="cross_artifact_correlation_gate",
        status="pass",
        reason="upstream artifacts share symbol and run_id",
        details={"symbol": symbol, "run_id": run_id},
    )


def _evaluate_bounded_autonomy_policy_gate(normalized: dict[str, Any]) -> GateResult:
    policy = normalized["bounded_autonomy_policy"]
    failures: list[str] = []
    if policy["l3_autonomy_enabled"]:
        failures.append("l3_autonomy_enabled must be false for evidence-only evaluation")
    if policy["live_submit_enabled_by_default"]:
        failures.append("live_submit_enabled_by_default must be false")
    if policy["provider_output_authoritative"]:
        failures.append("provider_output_authoritative must be false")
    if not policy["manual_approval_required"]:
        failures.append("manual_approval_required must be true")
    if policy["unattended_operation_allowed"]:
        failures.append("unattended_operation_allowed must be false")
    if policy["auto_approval_allowed"]:
        failures.append("auto_approval_allowed must be false")
    if not policy["requires_explicit_opt_in"]:
        failures.append("requires_explicit_opt_in must be true")
    if not policy["requires_active_operator_oversight"]:
        failures.append("requires_active_operator_oversight must be true")
    if not policy["requires_paper_validation"]:
        failures.append("requires_paper_validation must be true")
    if failures:
        return GateResult(
            gate_id="bounded_autonomy_policy_gate",
            status="fail",
            reason="bounded autonomy policy is not fail-closed",
            details={"failures": failures},
        )
    return GateResult(
        gate_id="bounded_autonomy_policy_gate",
        status="pass",
        reason="bounded autonomy policy is fail-closed",
        details={"min_paper_validation_runs": policy["min_paper_validation_runs"]},
    )


def _evaluate_risk_limit_gate(normalized: dict[str, Any]) -> GateResult:
    risk = normalized["risk_limit"]
    failures: list[str] = []
    if risk["leverage_allowed"]:
        failures.append("leverage_allowed must be false")
    if risk["shorting_allowed"]:
        failures.append("shorting_allowed must be false")
    if risk["options_allowed"]:
        failures.append("options_allowed must be false")
    if "market" not in risk["allowed_order_types"] and "limit" not in risk["allowed_order_types"]:
        failures.append("allowed_order_types must include market or limit")
    if "buy" not in risk["allowed_sides"]:
        failures.append("allowed_sides must include buy")
    if float(risk["max_total_net_exposure_pct"]) > 10.0:
        failures.append("max_total_net_exposure_pct must be <= 10.0")
    if failures:
        return GateResult(
            gate_id="risk_limit_gate",
            status="fail",
            reason="risk limits are not sufficiently bounded",
            details={"failures": failures},
        )
    return GateResult(
        gate_id="risk_limit_gate",
        status="pass",
        reason="risk limits are bounded and conservative",
        details={},
    )


def _evaluate_symbol_allowlist_gate(normalized: dict[str, Any]) -> GateResult:
    allowlist = normalized["symbol_allowlist"]
    symbol = normalized["quality_gate"]["symbol"]
    failures: list[str] = []
    if symbol not in allowlist["allowed_symbols"]:
        failures.append(f"symbol {symbol} is not in allowed_symbols")
    if symbol in allowlist["blocked_symbols"]:
        failures.append(f"symbol {symbol} is in blocked_symbols")
    if failures:
        return GateResult(
            gate_id="symbol_allowlist_gate",
            status="fail",
            reason="symbol allowlist policy fails for evaluated symbol",
            details={"failures": failures},
        )
    return GateResult(
        gate_id="symbol_allowlist_gate",
        status="pass",
        reason="evaluated symbol is allowed and not blocked",
        details={"allowed_symbol_count": len(allowlist["allowed_symbols"])},
    )


def _evaluate_heartbeat_deadman_gate(normalized: dict[str, Any]) -> GateResult:
    hd = normalized["heartbeat_deadman"]
    failures: list[str] = []
    if not hd["heartbeat_required"]:
        failures.append("heartbeat_required must be true")
    if not hd["deadman_required"]:
        failures.append("deadman_required must be true")
    if not hd["missing_heartbeat_fails_closed"]:
        failures.append("missing_heartbeat_fails_closed must be true")
    if not hd["stale_heartbeat_fails_closed"]:
        failures.append("stale_heartbeat_fails_closed must be true")
    if failures:
        return GateResult(
            gate_id="heartbeat_deadman_gate",
            status="fail",
            reason="heartbeat/deadman policy is not fail-closed",
            details={"failures": failures},
        )
    return GateResult(
        gate_id="heartbeat_deadman_gate",
        status="pass",
        reason="heartbeat/deadman policy is fail-closed",
        details={},
    )


def _evaluate_audit_redaction_gate(normalized: dict[str, Any]) -> GateResult:
    audit = normalized["audit_redaction"]
    failures: list[str] = []
    for field_name in (
        "redacts_secrets",
        "redacts_api_keys",
        "redacts_account_ids",
        "redacts_raw_broker_payloads",
        "redacts_raw_provider_output",
        "redacts_paths",
        "redacts_exception_text",
        "audit_hash_chain_required",
        "manifest_required",
    ):
        if not audit[field_name]:
            failures.append(f"{field_name} must be true")
    if failures:
        return GateResult(
            gate_id="audit_redaction_gate",
            status="fail",
            reason="audit redaction policy is not fail-closed",
            details={"failures": failures},
        )
    return GateResult(
        gate_id="audit_redaction_gate",
        status="pass",
        reason="audit redaction policy is fail-closed",
        details={},
    )


def _evaluate_l2_l3_boundary_gate(normalized: dict[str, Any]) -> GateResult:
    """Hard gate asserting the L2/L3 boundary invariants."""
    policy = normalized["bounded_autonomy_policy"]
    risk = normalized["risk_limit"]
    symbol = normalized["quality_gate"]["symbol"]
    failures: list[str] = []

    if policy["l3_autonomy_enabled"]:
        failures.append("L3 autonomy must not be enabled")
    if policy["provider_output_authoritative"]:
        failures.append("provider output must not be treated as execution authority")
    if not policy["manual_approval_required"]:
        failures.append("manual approval must be required")
    if policy["auto_approval_allowed"]:
        failures.append("auto-approval must not be allowed")
    if policy["unattended_operation_allowed"]:
        failures.append("unattended operation must not be allowed")
    if policy["live_submit_enabled_by_default"]:
        failures.append("live submit must not be enabled by default")
    if risk["leverage_allowed"]:
        failures.append("leverage must not be allowed")
    if risk["shorting_allowed"]:
        failures.append("shorting must not be allowed")
    if risk["options_allowed"]:
        failures.append("options must not be allowed")
    if symbol in normalized["symbol_allowlist"]["blocked_symbols"]:
        failures.append("evaluated symbol must not be blocked")

    if failures:
        return GateResult(
            gate_id="l2_l3_boundary_gate",
            status="fail",
            reason="L2/L3 boundary invariants violated",
            details={"failures": failures},
        )
    return GateResult(
        gate_id="l2_l3_boundary_gate",
        status="pass",
        reason="L2/L3 boundary invariants satisfied",
        details={},
    )


def _evaluate_readiness_synthesis_gate(
    gates: tuple[GateResult, ...],
) -> GateResult:
    failed = [g.gate_id for g in gates if g.status == "fail"]
    if failed:
        return GateResult(
            gate_id="readiness_synthesis_gate",
            status="fail",
            reason="one or more upstream or policy gates failed",
            details={"failed_gates": failed},
        )
    return GateResult(
        gate_id="readiness_synthesis_gate",
        status="pass",
        reason="all gates passed; readiness can be recorded",
        details={},
    )


def _build_readiness_assertions(normalized: dict[str, Any]) -> dict[str, bool]:
    policy = normalized["bounded_autonomy_policy"]
    risk = normalized["risk_limit"]
    hd = normalized["heartbeat_deadman"]
    audit = normalized["audit_redaction"]
    return {
        "cand004_blockers_empty": len(normalized["quality_gate"]["blockers"]) == 0,
        "cand005_blockers_empty": len(normalized["shadow_comparison"]["blockers"]) == 0,
        "cand006_blockers_empty": len(normalized["submit_conformance"]["blockers"]) == 0,
        "cand006_transmission_blocked": not normalized["submit_conformance"]["dry_run_request"]["transmission"]["allowed"],
        "cand007_blockers_empty": len(normalized["readiness_envelope"]["blockers"]) == 0,
        "cand008_blockers_empty": len(normalized["operator_approval_gate"]["blockers"]) == 0,
        "l3_autonomy_disabled": not policy["l3_autonomy_enabled"],
        "live_submit_disabled_by_default": not policy["live_submit_enabled_by_default"],
        "provider_output_non_authoritative": not policy["provider_output_authoritative"],
        "manual_approval_required": policy["manual_approval_required"],
        "no_unattended_operation": not policy["unattended_operation_allowed"],
        "no_auto_approval": not policy["auto_approval_allowed"],
        "explicit_opt_in_required": policy["requires_explicit_opt_in"],
        "active_operator_oversight_required": policy["requires_active_operator_oversight"],
        "paper_validation_required": policy["requires_paper_validation"],
        "no_leverage": not risk["leverage_allowed"],
        "no_shorting": not risk["shorting_allowed"],
        "no_options": not risk["options_allowed"],
        "heartbeat_required": hd["heartbeat_required"],
        "deadman_required": hd["deadman_required"],
        "missing_heartbeat_fails_closed": hd["missing_heartbeat_fails_closed"],
        "stale_heartbeat_fails_closed": hd["stale_heartbeat_fails_closed"],
        "audit_hash_chain_required": audit["audit_hash_chain_required"],
        "manifest_required": audit["manifest_required"],
        "redacts_secrets": audit["redacts_secrets"],
        "redacts_raw_broker_payloads": audit["redacts_raw_broker_payloads"],
        "redacts_raw_provider_output": audit["redacts_raw_provider_output"],
        "symbol_allowlist_strict": normalized["symbol_allowlist"]["allowlist_mode"] == "explicit_allowlist",
    }


def _build_blockers(gates: tuple[GateResult, ...]) -> list[str]:
    blockers: list[str] = []
    for gate in gates:
        if gate.status == "fail":
            blockers.append(f"{gate.gate_id}: {gate.reason}")
    return blockers


def _artifact_recording_gate(
    report: BoundedLiveAutonomyReadinessReport,
) -> BoundedLiveAutonomyReadinessReport:
    """Promote a synthesized report to recorded; otherwise return it unchanged."""
    if report.status != "readiness_synthesized":
        return report
    recording = {
        "json_artifact": _JSON_ARTIFACT_NAME,
        "markdown_artifact": _MARKDOWN_ARTIFACT_NAME,
        "recorded_at": _format_utc_timestamp(datetime.now(timezone.utc)),
    }
    return replace(
        report,
        status="bounded_live_readiness_recorded",
        exit_code=0,
        recording=recording,
    )


def _gate_pass(gate_id: str, reason: str = "") -> GateResult:
    return GateResult(gate_id=gate_id, status="pass", reason=reason or "passed")


def _gate_fail(gate_id: str, reason: str) -> GateResult:
    return GateResult(gate_id=gate_id, status="fail", reason=reason)


def _gate_not_run(gate_id: str) -> GateResult:
    return GateResult(gate_id=gate_id, status="not_run", reason="not run due to prior failure")


def build_bounded_live_autonomy_readiness_report(
    inputs: BoundedLiveAutonomyReadinessInputs,
) -> BoundedLiveAutonomyReadinessReport:
    """Build the CAND-015 bounded live autonomy readiness report.

    Loads and validates all inputs in a fail-closed try/except. Any validation or
    I/O error fails the schema_preflight gate and short-circuits the remaining
    gates to ``not_run``.
    """
    as_of = parse_as_of_utc(inputs.as_of)

    gates: list[GateResult] = []
    blockers: list[str] = []
    status = "not_evaluated"
    exit_code = 2
    normalized: dict[str, Any] | None = None
    fingerprints: dict[str, str] = {}
    input_digest = ""
    evaluation_id = ""
    upstream_summaries: dict[str, Any] = {}
    fixture_summaries: dict[str, Any] = {}
    readiness_assertions: dict[str, bool] = {}
    readiness_digest = ""
    run_id: str | None = None
    symbol: str | None = None

    try:
        _check_path_aliasing(inputs, inputs.output_dir if inputs.output_dir is not None else Path("."))
        normalized = _load_and_validate_all(inputs)
        fingerprints = _input_fingerprints(normalized)
        input_digest = _compute_input_digest(as_of, fingerprints)
        evaluation_id = _evaluation_id(input_digest)
        upstream_summaries = _build_upstream_summaries(normalized)
        fixture_summaries = _build_fixture_summaries(normalized)
        run_id = normalized["quality_gate"]["run_id"]
        symbol = normalized["quality_gate"]["symbol"]

        gate_evaluators = [
            _evaluate_schema_preflight,
            _evaluate_cand004_projection_gate,
            _evaluate_cand005_projection_gate,
            _evaluate_cand006_projection_gate,
            _evaluate_cand007_projection_gate,
            _evaluate_cand008_projection_gate,
            _evaluate_cross_artifact_correlation_gate,
            _evaluate_bounded_autonomy_policy_gate,
            _evaluate_risk_limit_gate,
            _evaluate_symbol_allowlist_gate,
            _evaluate_heartbeat_deadman_gate,
            _evaluate_audit_redaction_gate,
            _evaluate_l2_l3_boundary_gate,
        ]
        for evaluator in gate_evaluators:
            gates.append(evaluator(normalized))
            if gates[-1].status == "fail":
                for gate_id in GATE_SEQUENCE[len(gates) :]:
                    gates.append(_gate_not_run(gate_id))
                break
        else:
            gates.append(_evaluate_readiness_synthesis_gate(tuple(gates)))

        readiness_assertions = _build_readiness_assertions(normalized)
        readiness_digest = _compute_readiness_digest(
            as_of, fingerprints, upstream_summaries, readiness_assertions
        )
        blockers = _build_blockers(tuple(gates))

        status = "readiness_synthesized" if not blockers else "blocked"
        exit_code = 0 if not blockers else 2
    except BoundedLiveAutonomyReadinessValidationError as exc:
        gates.append(_gate_fail("schema_preflight", str(exc)))
        blockers.append(f"schema_preflight: {exc}")
        for gate_id in GATE_SEQUENCE[1:]:
            gates.append(_gate_not_run(gate_id))
        status = "blocked"
        exit_code = 2

    input_artifacts: dict[str, str | None] = {
        label: _redact_path(getattr(inputs, f"{label}_path"))
        for label in _INPUT_LABELS
    }

    if not input_digest:
        input_digest = fingerprint_json({"as_of": as_of})
    if not evaluation_id:
        evaluation_id = _evaluation_id(input_digest)
    if not readiness_digest:
        readiness_digest = fingerprint_json({"as_of": as_of})

    report = BoundedLiveAutonomyReadinessReport(
        artifact_type=ARTIFACT_TYPE,
        schema_version=SCHEMA_VERSION,
        candidate=CANDIDATE,
        mode=MODE,
        status=status,
        exit_code=exit_code,
        evaluation_id=evaluation_id,
        as_of=as_of,
        run_id=run_id,
        symbol=symbol,
        candidate_chain=CANDIDATE_CHAIN,
        gate_sequence=GATE_SEQUENCE,
        gates=tuple(gates),
        input_artifacts=input_artifacts,
        input_paths={label: getattr(inputs, f"{label}_path") for label in _INPUT_LABELS},
        input_fingerprints=fingerprints,
        input_digest=input_digest,
        readiness_digest=readiness_digest,
        upstream_summaries=upstream_summaries,
        fixture_summaries=fixture_summaries,
        readiness_assertions=readiness_assertions,
        blockers=blockers,
        recording={},
        disclaimer=EVIDENCE_ONLY_DISCLAIMER,
    )

    return report


def _render_markdown_report(report: BoundedLiveAutonomyReadinessReport) -> str:
    lines: list[str] = []
    lines.append("# Bounded Live Autonomy Readiness Report (CAND-015)")
    lines.append("")
    lines.append("> **Evidence-only and simulated-only.** This report is a local artifact. "
                 "`bounded_live_readiness_recorded` is evidence-recording status only. "
                 "It is not live readiness, not trading safety, not profitability evidence, "
                 "not permission to trade, and not authorization to submit orders.")
    lines.append("")
    lines.append(f"- **status:** {report.status}")
    lines.append(f"- **evaluation_id:** {report.evaluation_id}")
    lines.append(f"- **as_of:** {report.as_of}")
    lines.append(f"- **symbol:** {report.symbol or '-'}")
    lines.append(f"- **run_id:** {report.run_id or '-'}")
    lines.append(f"- **input_digest:** {report.input_digest}")
    lines.append(f"- **readiness_digest:** {report.readiness_digest}")
    lines.append("")
    lines.append("## Gates")
    lines.append("")
    for gate in report.gates:
        lines.append(f"- `{gate.gate_id}`: {gate.status} — {gate.reason}")
    lines.append("")
    if report.blockers:
        lines.append("## Blockers")
        lines.append("")
        for blocker in report.blockers:
            lines.append(f"- {blocker}")
        lines.append("")
    lines.append("## Readiness Assertions")
    lines.append("")
    for assertion, value in sorted(report.readiness_assertions.items()):
        lines.append(f"- `{assertion}`: {value}")
    lines.append("")
    lines.append("## Disclaimer")
    lines.append("")
    lines.append(report.disclaimer)
    lines.append("")
    return "\n".join(lines)


def write_bounded_live_autonomy_readiness_artifacts(
    report: BoundedLiveAutonomyReadinessReport,
    output_dir: Path,
) -> BoundedLiveAutonomyReadinessReport:
    """Write the JSON and Markdown artifacts to ``output_dir``.

    If the report is ``readiness_synthesized`` it is first promoted to
    ``bounded_live_readiness_recorded``. Any I/O failure returns a ``blocked``
    report.
    """
    recorded = _artifact_recording_gate(report)
    if recorded.status != "bounded_live_readiness_recorded":
        return recorded

    output_dir = Path(output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return replace(
            recorded,
            status="blocked",
            exit_code=2,
            blockers=recorded.blockers + [f"artifact_recording_gate: {exc}"],
        )

    json_path = output_dir / _JSON_ARTIFACT_NAME
    md_path = output_dir / _MARKDOWN_ARTIFACT_NAME

    try:
        json_path.write_text(
            json.dumps(recorded.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        md_path.write_text(_render_markdown_report(recorded), encoding="utf-8")
    except Exception as exc:
        return replace(
            recorded,
            status="blocked",
            exit_code=2,
            blockers=recorded.blockers + [f"artifact_recording_gate: {exc}"],
        )

    recording = dict(recorded.recording)
    recording["json_path"] = str(json_path.name)
    recording["markdown_path"] = str(md_path.name)
    return replace(recorded, recording=recording)
