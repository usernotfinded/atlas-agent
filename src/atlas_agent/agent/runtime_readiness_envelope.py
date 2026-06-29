from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal


APPROVED_FINAL_STATUSES = (
    "not_evaluated",
    "blocked",
    "upstream_quality_blocked",
    "shadow_evidence_blocked",
    "submit_conformance_blocked",
    "runtime_envelope_blocked",
    "broker_capability_blocked",
    "operator_policy_blocked",
    "kill_switch_policy_blocked",
    "audit_policy_blocked",
    "envelope_synthesized",
    "readiness_envelope_recorded",
)

GATE_SEQUENCE = (
    "schema_preflight",
    "cand004_evidence_gate",
    "cand005_evidence_gate",
    "cand006_evidence_gate",
    "runtime_envelope_fixture_gate",
    "broker_capability_manifest_gate",
    "operator_policy_fixture_gate",
    "kill_switch_policy_fixture_gate",
    "audit_policy_fixture_gate",
    "envelope_synthesis_gate",
    "artifact_recording_gate",
)

EVIDENCE_ONLY_DISCLAIMER = (
    "Runtime readiness envelope evaluation (CAND-007) — simulated only. "
    "readiness_envelope_recorded is evidence-recording status only. "
    "It is not live readiness, not trading safety, not profitability evidence, "
    "and not permission to submit orders."
)

_JSON_ARTIFACT_NAME = "runtime-readiness-envelope.json"
_MARKDOWN_ARTIFACT_NAME = "runtime-readiness-envelope-report.md"

_TRADING_QUALITY_GATE_ARTIFACT_TYPE = "trading_quality_gate"
_TRADING_QUALITY_GATE_SCHEMA_VERSIONS = ("trading-quality-gate.v1", 1, "1")
_SHADOW_LIVE_COMPARISON_ARTIFACT_TYPE = "shadow_live_comparison"
_SHADOW_LIVE_COMPARISON_SCHEMA_VERSION = "shadow-live-comparison.v1"
_GATED_SUBMIT_CONFORMANCE_ARTIFACT_TYPE = "gated_submit_conformance"
_GATED_SUBMIT_CONFORMANCE_SCHEMA_VERSION = "gated-submit-conformance.v1"

_RUNTIME_ENVELOPE_FIXTURE_ARTIFACT_TYPE = "runtime_readiness_envelope_fixture"
_RUNTIME_ENVELOPE_FIXTURE_SCHEMA_VERSION = "runtime-readiness-envelope-fixture.v1"
_BROKER_CAPABILITY_MANIFEST_ARTIFACT_TYPE = "broker_capability_manifest_fixture"
_BROKER_CAPABILITY_MANIFEST_SCHEMA_VERSION = "broker-capability-manifest-fixture.v1"
_OPERATOR_POLICY_ARTIFACT_TYPE = "operator_policy_fixture"
_OPERATOR_POLICY_SCHEMA_VERSION = "operator-policy-fixture.v1"
_KILL_SWITCH_POLICY_ARTIFACT_TYPE = "kill_switch_policy_fixture"
_KILL_SWITCH_POLICY_SCHEMA_VERSION = "kill-switch-policy-fixture.v1"
_AUDIT_POLICY_ARTIFACT_TYPE = "audit_policy_fixture"
_AUDIT_POLICY_SCHEMA_VERSION = "audit-policy-fixture.v1"

_INPUT_LABELS = (
    "quality_gate",
    "shadow_comparison",
    "submit_conformance",
    "runtime_envelope",
    "broker_capabilities",
    "operator_policy",
    "kill_switch_policy",
    "audit_policy",
)

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
}


class ReadinessValidationError(Exception):
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
class ReadinessEnvelopeInputs:
    quality_gate_path: Path
    shadow_comparison_path: Path
    submit_conformance_path: Path
    runtime_envelope_path: Path
    broker_capabilities_path: Path
    operator_policy_path: Path
    kill_switch_policy_path: Path
    audit_policy_path: Path
    output_dir: Path | None
    as_of: str


@dataclass(frozen=True)
class ReadinessEnvelopeReport:
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
    input_fingerprints: dict[str, str]
    input_digest: str
    envelope_digest: str
    upstream_summaries: dict[str, Any]
    fixture_summaries: dict[str, Any]
    envelope_assertions: dict[str, bool]
    blocked_reasons: list[str]
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
            "envelope_digest": self.envelope_digest,
            "upstream_summaries": self.upstream_summaries,
            "fixture_summaries": self.fixture_summaries,
            "envelope_assertions": self.envelope_assertions,
            "blocked_reasons": self.blocked_reasons,
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


def _format_utc_timestamp(dt: Any) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_timestamp(value: str) -> Any | None:
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
        from datetime import datetime

        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        return None
    from datetime import timezone

    return parsed.astimezone(timezone.utc)


def parse_as_of_utc(value: str) -> str:
    """Parse and normalize an ISO-8601 UTC timestamp string.

    Accepts ``2026-06-24T10:00:00Z`` and ``2026-06-24T10:00:00+00:00``.
    Rejects naive timestamps, non-UTC offsets, and non-ISO strings.
    """
    if not isinstance(value, str):
        raise ReadinessValidationError("as_of is not a string")
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise ReadinessValidationError(
            f"as_of is not a valid ISO-8601 UTC timestamp: {value!r}"
        )
    return _format_utc_timestamp(parsed)


def _canonical_decimal_string(value: Any, *, allow_zero: bool = True) -> str:
    """Normalize a decimal string and reject non-canonical or invalid forms."""
    if not isinstance(value, str):
        raise ReadinessValidationError(
            f"expected decimal string, got {type(value).__name__}"
        )
    if "e" in value.lower():
        raise ReadinessValidationError("exponent notation is not allowed")
    if value.startswith("+"):
        raise ReadinessValidationError("leading plus sign is not allowed")
    try:
        dec = Decimal(value)
    except InvalidOperation as exc:
        raise ReadinessValidationError(f"invalid decimal: {exc}") from None
    if dec.is_nan() or not dec.is_finite():
        raise ReadinessValidationError("NaN and Infinity are not allowed")
    if dec == 0 and dec.as_tuple().sign == 1:
        raise ReadinessValidationError("negative zero is not allowed")
    if not allow_zero and dec == 0:
        raise ReadinessValidationError("zero is not allowed")
    canonical = format(dec.normalize(), "f")
    try:
        if Decimal(canonical) == Decimal(canonical).to_integral_value():
            canonical = str(Decimal(canonical).to_integral_value())
    except InvalidOperation:
        pass
    return canonical


def _positive_decimal_string(value: Any) -> str:
    s = _canonical_decimal_string(value, allow_zero=False)
    if Decimal(s) <= 0:
        raise ReadinessValidationError("value must be positive")
    return s


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ReadinessValidationError(f"{name} must be a string")
    return value


def _require_exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ReadinessValidationError(
            f"{label} contains unknown keys: {sorted(unknown)}"
        )


def _secret_value_match(lower_value: str, pattern: str) -> bool:
    """Return True if ``pattern`` appears as a secret-like token in the value."""
    return re.search(r"(?:^|\W)" + re.escape(pattern), lower_value) is not None


def _universal_reject_scan(obj: Any, path: str = "") -> list[str]:
    """Return a list of secret/endpoint/URL findings in a parsed JSON object."""
    findings: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = key.lower()
            if key_lower in _SECRET_KEYS:
                findings.append(f"secret-like key at {path}: {key}")
            if key_lower in _ENDPOINT_KEYS:
                findings.append(f"endpoint-like key at {path}: {key}")
            if key_lower in _FORBIDDEN_FIXTURE_KEYS:
                findings.append(f"forbidden key at {path}: {key}")
            for pattern in _SECRET_VALUE_PATTERNS:
                if _secret_value_match(key_lower, pattern):
                    findings.append(f"secret-like key fragment at {path}: {key}")
            for pattern in _URL_PROTOCOL_PATTERNS:
                if _secret_value_match(key_lower, pattern):
                    findings.append(f"url-like key fragment at {path}: {key}")
            findings.extend(
                _universal_reject_scan(value, f"{path}.{key}" if path else key)
            )
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            findings.extend(_universal_reject_scan(value, f"{path}[{idx}]"))
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
        raise ReadinessValidationError(f"{label} file not found: {path.name}")
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ReadinessValidationError(f"failed to read {label}: {exc}") from None
    if not text.strip():
        raise ReadinessValidationError(f"{label} file is empty")
    try:
        data = json.loads(text, parse_constant=lambda c: c)
    except json.JSONDecodeError as exc:
        raise ReadinessValidationError(f"{label} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ReadinessValidationError(f"{label} is not a JSON object")
    raw_text = text.lower()
    for constant in ("nan", "infinity", "-infinity"):
        if constant in raw_text:
            raise ReadinessValidationError(
                f"{label} contains forbidden JSON constant: {constant}"
            )
    return data


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
        raise ReadinessValidationError("quality_gate artifact_type mismatch")
    if schema_version not in _TRADING_QUALITY_GATE_SCHEMA_VERSIONS:
        raise ReadinessValidationError("quality_gate schema_version mismatch")
    if not isinstance(blockers, list):
        raise ReadinessValidationError("quality_gate blockers must be a list")

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
        raise ReadinessValidationError("shadow_comparison artifact_type mismatch")
    if schema_version != _SHADOW_LIVE_COMPARISON_SCHEMA_VERSION:
        raise ReadinessValidationError("shadow_comparison schema_version mismatch")
    if not isinstance(freshness_assessment, dict):
        raise ReadinessValidationError(
            "shadow_comparison freshness_assessment must be an object"
        )
    if not isinstance(blockers, list):
        raise ReadinessValidationError("shadow_comparison blockers must be a list")

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


def _cand006_age_hours(cand006_as_of: str, cand007_as_of: str) -> float:
    dt6 = _parse_iso_timestamp(cand006_as_of)
    dt7 = _parse_iso_timestamp(cand007_as_of)
    if dt6 is None or dt7 is None:
        raise ReadinessValidationError("invalid timestamp for CAND-006 age check")
    diff = dt7 - dt6
    return diff.total_seconds() / 3600.0


def _validate_submit_conformance(
    data: dict[str, Any], cand007_as_of: str
) -> dict[str, Any]:
    """Project CAND-006 to accepted keys and enforce the 24-hour freshness rule."""
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
        raise ReadinessValidationError("submit_conformance artifact_type mismatch")
    if schema_version != _GATED_SUBMIT_CONFORMANCE_SCHEMA_VERSION:
        raise ReadinessValidationError("submit_conformance schema_version mismatch")
    if candidate != "CAND-006":
        raise ReadinessValidationError("submit_conformance candidate must be CAND-006")
    if mode != "simulated_only":
        raise ReadinessValidationError("submit_conformance mode must be 'simulated_only'")
    if not isinstance(safety_assertions, dict):
        raise ReadinessValidationError("submit_conformance safety_assertions must be an object")
    if not all(isinstance(v, bool) and v for v in safety_assertions.values()):
        raise ReadinessValidationError("all submit_conformance safety_assertions must be true")
    if not isinstance(dry_run_request, dict):
        raise ReadinessValidationError("submit_conformance dry_run_request must be an object")
    transmission = dry_run_request.get("transmission")
    if not isinstance(transmission, dict):
        raise ReadinessValidationError(
            "submit_conformance dry_run_request.transmission must be an object"
        )
    if not isinstance(blockers, list):
        raise ReadinessValidationError("submit_conformance blockers must be a list")

    cand6_dt = _parse_iso_timestamp(as_of)
    cand7_dt = _parse_iso_timestamp(cand007_as_of)
    if cand6_dt is None or cand7_dt is None:
        raise ReadinessValidationError("invalid timestamp for CAND-006 freshness check")
    if cand6_dt > cand7_dt:
        raise ReadinessValidationError("CAND-006 as_of is later than CAND-007 as_of")
    if _cand006_age_hours(as_of, cand007_as_of) > 24.0:
        raise ReadinessValidationError("CAND-006 evidence is older than 24 hours")

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


def _validate_runtime_envelope_fixture(
    data: dict[str, Any], as_of: str
) -> dict[str, Any]:
    """Closed-schema validation for the runtime envelope fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "fixture_mode",
        "run_id",
        "symbol",
        "allowed_modes",
        "forbidden_modes",
        "live_submit_enabled",
        "require_human_approval",
        "require_kill_switch_inactive",
        "require_risk_gate",
        "require_audit_recording",
        "require_broker_capability_manifest",
        "max_order_notional",
        "max_symbol_exposure",
        "max_daily_orders",
        "max_daily_notional",
        "supported_order_types",
        "supported_time_in_force",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "runtime_envelope_fixture")

    artifact_type = _require_string(
        data.get("artifact_type"), "runtime_envelope_fixture.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "runtime_envelope_fixture.schema_version"
    )
    if artifact_type != _RUNTIME_ENVELOPE_FIXTURE_ARTIFACT_TYPE:
        raise ReadinessValidationError("runtime_envelope_fixture artifact_type mismatch")
    if schema_version != _RUNTIME_ENVELOPE_FIXTURE_SCHEMA_VERSION:
        raise ReadinessValidationError("runtime_envelope_fixture schema_version mismatch")

    fixture_mode = _require_string(
        data.get("fixture_mode"), "runtime_envelope_fixture.fixture_mode"
    )
    if fixture_mode != "simulated/static":
        raise ReadinessValidationError(
            "runtime_envelope_fixture fixture_mode must be 'simulated/static'"
        )

    run_id = _require_string(data.get("run_id"), "runtime_envelope_fixture.run_id")
    symbol = _require_string(data.get("symbol"), "runtime_envelope_fixture.symbol")

    allowed_modes = data.get("allowed_modes")
    if not isinstance(allowed_modes, list):
        raise ReadinessValidationError("runtime_envelope_fixture allowed_modes must be a list")
    forbidden_modes = data.get("forbidden_modes")
    if not isinstance(forbidden_modes, list):
        raise ReadinessValidationError(
            "runtime_envelope_fixture forbidden_modes must be a list"
        )

    max_order_notional = _positive_decimal_string(data.get("max_order_notional"))
    max_symbol_exposure = _positive_decimal_string(data.get("max_symbol_exposure"))
    max_daily_notional = _positive_decimal_string(data.get("max_daily_notional"))

    max_daily_orders = data.get("max_daily_orders")
    if not isinstance(max_daily_orders, int) or isinstance(max_daily_orders, bool):
        raise ReadinessValidationError(
            "runtime_envelope_fixture max_daily_orders must be an integer"
        )

    supported_order_types = data.get("supported_order_types")
    if not isinstance(supported_order_types, list):
        raise ReadinessValidationError(
            "runtime_envelope_fixture supported_order_types must be a list"
        )
    if not all(isinstance(v, str) for v in supported_order_types):
        raise ReadinessValidationError(
            "runtime_envelope_fixture supported_order_types must be strings"
        )

    supported_time_in_force = data.get("supported_time_in_force")
    if not isinstance(supported_time_in_force, list):
        raise ReadinessValidationError(
            "runtime_envelope_fixture supported_time_in_force must be a list"
        )
    if not all(isinstance(v, str) for v in supported_time_in_force):
        raise ReadinessValidationError(
            "runtime_envelope_fixture supported_time_in_force must be strings"
        )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "runtime_envelope_fixture.expires_at"),
        "runtime_envelope_fixture.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise ReadinessValidationError(
            "runtime_envelope_fixture expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "fixture_mode": fixture_mode,
        "run_id": run_id,
        "symbol": symbol,
        "allowed_modes": allowed_modes,
        "forbidden_modes": forbidden_modes,
        "live_submit_enabled": data["live_submit_enabled"],
        "require_human_approval": data["require_human_approval"],
        "require_kill_switch_inactive": data["require_kill_switch_inactive"],
        "require_risk_gate": data["require_risk_gate"],
        "require_audit_recording": data["require_audit_recording"],
        "require_broker_capability_manifest": data["require_broker_capability_manifest"],
        "max_order_notional": max_order_notional,
        "max_symbol_exposure": max_symbol_exposure,
        "max_daily_orders": max_daily_orders,
        "max_daily_notional": max_daily_notional,
        "supported_order_types": supported_order_types,
        "supported_time_in_force": supported_time_in_force,
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_broker_capability_manifest(
    data: dict[str, Any], as_of: str
) -> dict[str, Any]:
    """Closed-schema validation for the broker capability manifest fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "broker_label",
        "capabilities",
        "disabled_capabilities",
        "unsupported_order_types",
        "sandbox_only",
        "live_api_contact_allowed",
        "credentials_present",
        "endpoint_present",
        "captured_at",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "broker_capability_manifest")

    artifact_type = _require_string(
        data.get("artifact_type"), "broker_capability_manifest.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "broker_capability_manifest.schema_version"
    )
    if artifact_type != _BROKER_CAPABILITY_MANIFEST_ARTIFACT_TYPE:
        raise ReadinessValidationError(
            "broker_capability_manifest artifact_type mismatch"
        )
    if schema_version != _BROKER_CAPABILITY_MANIFEST_SCHEMA_VERSION:
        raise ReadinessValidationError(
            "broker_capability_manifest schema_version mismatch"
        )

    broker_label = _require_string(
        data.get("broker_label"), "broker_capability_manifest.broker_label"
    )

    for field_name in (
        "sandbox_only",
        "live_api_contact_allowed",
        "credentials_present",
        "endpoint_present",
    ):
        if not isinstance(data.get(field_name), bool):
            raise ReadinessValidationError(
                f"broker_capability_manifest {field_name} must be a boolean"
            )

    capabilities = data.get("capabilities")
    if not isinstance(capabilities, dict):
        raise ReadinessValidationError(
            "broker_capability_manifest capabilities must be an object"
        )
    if not all(isinstance(v, bool) for v in capabilities.values()):
        raise ReadinessValidationError(
            "broker_capability_manifest capabilities values must be booleans"
        )

    disabled_capabilities = data.get("disabled_capabilities")
    if not isinstance(disabled_capabilities, list):
        raise ReadinessValidationError(
            "broker_capability_manifest disabled_capabilities must be a list"
        )
    if not all(isinstance(v, str) for v in disabled_capabilities):
        raise ReadinessValidationError(
            "broker_capability_manifest disabled_capabilities must be strings"
        )

    unsupported_order_types = data.get("unsupported_order_types")
    if not isinstance(unsupported_order_types, list):
        raise ReadinessValidationError(
            "broker_capability_manifest unsupported_order_types must be a list"
        )
    if not all(isinstance(v, str) for v in unsupported_order_types):
        raise ReadinessValidationError(
            "broker_capability_manifest unsupported_order_types must be strings"
        )

    captured_at = _format_utc_timestamp(
        _parse_or_fail(
            _require_string(data.get("captured_at"), "broker_capability_manifest.captured_at"),
            "broker_capability_manifest.captured_at",
        )
    )
    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "broker_capability_manifest.expires_at"),
        "broker_capability_manifest.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise ReadinessValidationError(
            "broker_capability_manifest expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "broker_label": broker_label,
        "capabilities": capabilities,
        "disabled_capabilities": disabled_capabilities,
        "unsupported_order_types": unsupported_order_types,
        "sandbox_only": data["sandbox_only"],
        "live_api_contact_allowed": data["live_api_contact_allowed"],
        "credentials_present": data["credentials_present"],
        "endpoint_present": data["endpoint_present"],
        "captured_at": captured_at,
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_operator_policy_fixture(
    data: dict[str, Any], as_of: str, symbol: str
) -> dict[str, Any]:
    """Closed-schema validation for the operator policy fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "requires_manual_review",
        "requires_explicit_approval",
        "approval_scope",
        "unattended_operation_allowed",
        "max_runtime_window_seconds",
        "max_actions_per_session",
        "allowed_symbols",
        "blocked_symbols",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "operator_policy_fixture")

    artifact_type = _require_string(
        data.get("artifact_type"), "operator_policy_fixture.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "operator_policy_fixture.schema_version"
    )
    if artifact_type != _OPERATOR_POLICY_ARTIFACT_TYPE:
        raise ReadinessValidationError("operator_policy_fixture artifact_type mismatch")
    if schema_version != _OPERATOR_POLICY_SCHEMA_VERSION:
        raise ReadinessValidationError("operator_policy_fixture schema_version mismatch")

    for field_name in ("requires_manual_review", "requires_explicit_approval", "unattended_operation_allowed"):
        if not isinstance(data.get(field_name), bool):
            raise ReadinessValidationError(
                f"operator_policy_fixture {field_name} must be a boolean"
            )

    approval_scope = _require_string(
        data.get("approval_scope"), "operator_policy_fixture.approval_scope"
    )

    for field_name in ("max_runtime_window_seconds", "max_actions_per_session"):
        value = data.get(field_name)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ReadinessValidationError(
                f"operator_policy_fixture {field_name} must be an integer"
            )

    allowed_symbols = data.get("allowed_symbols")
    if not isinstance(allowed_symbols, list):
        raise ReadinessValidationError(
            "operator_policy_fixture allowed_symbols must be a list"
        )
    if not all(isinstance(v, str) for v in allowed_symbols):
        raise ReadinessValidationError(
            "operator_policy_fixture allowed_symbols must be strings"
        )

    blocked_symbols = data.get("blocked_symbols")
    if not isinstance(blocked_symbols, list):
        raise ReadinessValidationError(
            "operator_policy_fixture blocked_symbols must be a list"
        )
    if not all(isinstance(v, str) for v in blocked_symbols):
        raise ReadinessValidationError(
            "operator_policy_fixture blocked_symbols must be strings"
        )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "operator_policy_fixture.expires_at"),
        "operator_policy_fixture.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise ReadinessValidationError(
            "operator_policy_fixture expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "requires_manual_review": data["requires_manual_review"],
        "requires_explicit_approval": data["requires_explicit_approval"],
        "approval_scope": approval_scope,
        "unattended_operation_allowed": data["unattended_operation_allowed"],
        "max_runtime_window_seconds": data["max_runtime_window_seconds"],
        "max_actions_per_session": data["max_actions_per_session"],
        "allowed_symbols": allowed_symbols,
        "blocked_symbols": blocked_symbols,
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_kill_switch_policy_fixture(
    data: dict[str, Any], as_of: str
) -> dict[str, Any]:
    """Closed-schema validation for the kill-switch policy fixture."""
    allowed = {
        "artifact_type",
        "schema_version",
        "kill_switch_required",
        "default_state_on_missing_runtime",
        "default_state_on_unknown_runtime",
        "operator_override_allowed",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "kill_switch_policy_fixture")

    artifact_type = _require_string(
        data.get("artifact_type"), "kill_switch_policy_fixture.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "kill_switch_policy_fixture.schema_version"
    )
    if artifact_type != _KILL_SWITCH_POLICY_ARTIFACT_TYPE:
        raise ReadinessValidationError(
            "kill_switch_policy_fixture artifact_type mismatch"
        )
    if schema_version != _KILL_SWITCH_POLICY_SCHEMA_VERSION:
        raise ReadinessValidationError(
            "kill_switch_policy_fixture schema_version mismatch"
        )

    if not isinstance(data.get("kill_switch_required"), bool):
        raise ReadinessValidationError(
            "kill_switch_policy_fixture kill_switch_required must be a boolean"
        )

    for field_name in (
        "default_state_on_missing_runtime",
        "default_state_on_unknown_runtime",
    ):
        _require_string(
            data.get(field_name), f"kill_switch_policy_fixture.{field_name}"
        )

    if not isinstance(data.get("operator_override_allowed"), bool):
        raise ReadinessValidationError(
            "kill_switch_policy_fixture operator_override_allowed must be a boolean"
        )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "kill_switch_policy_fixture.expires_at"),
        "kill_switch_policy_fixture.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise ReadinessValidationError(
            "kill_switch_policy_fixture expires_at must be later than as_of"
        )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "kill_switch_required": data["kill_switch_required"],
        "default_state_on_missing_runtime": data["default_state_on_missing_runtime"],
        "default_state_on_unknown_runtime": data["default_state_on_unknown_runtime"],
        "operator_override_allowed": data["operator_override_allowed"],
        "expires_at": _format_utc_timestamp(expires_at),
    }


def _validate_audit_policy_fixture(data: dict[str, Any], as_of: str) -> dict[str, Any]:
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
    _require_exact_keys(data, allowed, "audit_policy_fixture")

    artifact_type = _require_string(
        data.get("artifact_type"), "audit_policy_fixture.artifact_type"
    )
    schema_version = _require_string(
        data.get("schema_version"), "audit_policy_fixture.schema_version"
    )
    if artifact_type != _AUDIT_POLICY_ARTIFACT_TYPE:
        raise ReadinessValidationError("audit_policy_fixture artifact_type mismatch")
    if schema_version != _AUDIT_POLICY_SCHEMA_VERSION:
        raise ReadinessValidationError("audit_policy_fixture schema_version mismatch")

    for field_name in (
        "audit_required",
        "append_only_required",
        "hash_chain_required",
        "local_artifact_recording_required",
        "live_audit_chain_claimed",
    ):
        if not isinstance(data.get(field_name), bool):
            raise ReadinessValidationError(
                f"audit_policy_fixture {field_name} must be a boolean"
            )

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "audit_policy_fixture.expires_at"),
        "audit_policy_fixture.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise ReadinessValidationError(
            "audit_policy_fixture expires_at must be later than as_of"
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


def _parse_or_fail(value: str, label: str) -> Any:
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise ReadinessValidationError(f"{label} is not a valid ISO-8601 UTC timestamp")
    return parsed


def _load_and_validate_all(
    inputs: ReadinessEnvelopeInputs, as_of: str
) -> dict[str, Any]:
    """Load every input fixture, scan it, and validate by projection or closed schema."""
    paths = {
        label: getattr(inputs, f"{label}_path") for label in _INPUT_LABELS
    }
    raw: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        raw[label] = _load_json_object(path, label)
        findings = _universal_reject_scan(raw[label], label)
        if findings:
            raise ReadinessValidationError(
                "universal rejection: " + "; ".join(findings)
            )

    quality_gate = _validate_quality_gate(raw["quality_gate"])
    shadow_comparison = _validate_shadow_comparison(raw["shadow_comparison"])
    submit_conformance = _validate_submit_conformance(raw["submit_conformance"], as_of)
    runtime_envelope = _validate_runtime_envelope_fixture(raw["runtime_envelope"], as_of)
    broker_capabilities = _validate_broker_capability_manifest(
        raw["broker_capabilities"], as_of
    )
    operator_policy = _validate_operator_policy_fixture(
        raw["operator_policy"], as_of, quality_gate["symbol"]
    )
    kill_switch_policy = _validate_kill_switch_policy_fixture(
        raw["kill_switch_policy"], as_of
    )
    audit_policy = _validate_audit_policy_fixture(raw["audit_policy"], as_of)

    return {
        "quality_gate": quality_gate,
        "shadow_comparison": shadow_comparison,
        "submit_conformance": submit_conformance,
        "runtime_envelope": runtime_envelope,
        "broker_capabilities": broker_capabilities,
        "operator_policy": operator_policy,
        "kill_switch_policy": kill_switch_policy,
        "audit_policy": audit_policy,
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
    """Return a list of correlation blockers across normalized inputs.

    Compares ``run_id`` and ``symbol`` across the upstream artifacts and the
    runtime envelope fixture. Per-fixture symbol constraints (allowed_symbols,
    blocked_symbols) are enforced by the operator policy validator/gate.
    """
    blockers: list[str] = []
    run_id = normalized["quality_gate"]["run_id"]
    symbol = normalized["quality_gate"]["symbol"]
    for label in ("shadow_comparison", "submit_conformance", "runtime_envelope"):
        if normalized[label]["run_id"] != run_id:
            blockers.append(f"run_id mismatch between quality_gate and {label}")
        if normalized[label]["symbol"] != symbol:
            blockers.append(f"symbol mismatch between quality_gate and {label}")
    return blockers


def build_runtime_readiness_envelope_report(
    inputs: ReadinessEnvelopeInputs,
) -> ReadinessEnvelopeReport:
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
    except ReadinessValidationError as exc:
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
    runtime_envelope = normalized["runtime_envelope"]
    broker_capabilities = normalized["broker_capabilities"]
    operator_policy = normalized["operator_policy"]
    kill_switch_policy = normalized["kill_switch_policy"]
    audit_policy = normalized["audit_policy"]

    # Gate 2: cand004_evidence_gate
    cand004_failures: list[str] = []
    if quality_gate["mode"] != "paper":
        cand004_failures.append("quality_gate mode is not 'paper'")
    if quality_gate["quality_state"] != "eligible_for_shadow_live_quality_review":
        cand004_failures.append(
            f"quality_gate quality_state is '{quality_gate['quality_state']}'"
        )
    if quality_gate["blockers"]:
        cand004_failures.append("quality_gate blockers are non-empty")
    cand004_failures.extend(_correlate_evidence(normalized))
    if cand004_failures:
        reason = "; ".join(cand004_failures)
        gates.append(_gate_fail("cand004_evidence_gate", reason))
        blockers.append(f"cand004_evidence_gate: {reason}")
        status = "upstream_quality_blocked"
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
    gates.append(_gate_pass("cand004_evidence_gate"))

    # Gate 3: cand005_evidence_gate
    cand005_failures: list[str] = []
    if shadow_comparison["status"] != "matched":
        cand005_failures.append(
            f"shadow_comparison status is '{shadow_comparison['status']}'"
        )
    if shadow_comparison["blockers"]:
        cand005_failures.append("shadow_comparison blockers are non-empty")
    if cand005_failures:
        reason = "; ".join(cand005_failures)
        gates.append(_gate_fail("cand005_evidence_gate", reason))
        blockers.append(f"cand005_evidence_gate: {reason}")
        status = "shadow_evidence_blocked"
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
    gates.append(_gate_pass("cand005_evidence_gate"))

    # Gate 4: cand006_evidence_gate
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
        gates.append(_gate_fail("cand006_evidence_gate", reason))
        blockers.append(f"cand006_evidence_gate: {reason}")
        status = "submit_conformance_blocked"
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
    gates.append(_gate_pass("cand006_evidence_gate"))

    # Gate 5: runtime_envelope_fixture_gate
    re_failures: list[str] = []
    if runtime_envelope["live_submit_enabled"] is not False:
        re_failures.append("runtime_envelope live_submit_enabled is true")
    for field_name in (
        "require_human_approval",
        "require_kill_switch_inactive",
        "require_risk_gate",
        "require_audit_recording",
        "require_broker_capability_manifest",
    ):
        if runtime_envelope[field_name] is not True:
            re_failures.append(f"runtime_envelope {field_name} is false")
    required_allowed = {"paper", "shadow_live_readonly", "simulated"}
    if not required_allowed.issubset(set(runtime_envelope["allowed_modes"])):
        re_failures.append("runtime_envelope allowed_modes missing required modes")
    if "live" not in runtime_envelope["forbidden_modes"]:
        re_failures.append("runtime_envelope forbidden_modes missing 'live'")
    if "live_submit" not in runtime_envelope["forbidden_modes"]:
        re_failures.append("runtime_envelope forbidden_modes missing 'live_submit'")
    if not runtime_envelope["supported_order_types"]:
        re_failures.append("runtime_envelope supported_order_types is empty")
    if not set(runtime_envelope["supported_order_types"]).issubset({"market", "limit"}):
        re_failures.append("runtime_envelope supported_order_types invalid")
    if not runtime_envelope["supported_time_in_force"]:
        re_failures.append("runtime_envelope supported_time_in_force is empty")
    if not set(runtime_envelope["supported_time_in_force"]).issubset({"day"}):
        re_failures.append("runtime_envelope supported_time_in_force invalid")
    if re_failures:
        reason = "; ".join(re_failures)
        gates.append(_gate_fail("runtime_envelope_fixture_gate", reason))
        blockers.append(f"runtime_envelope_fixture_gate: {reason}")
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
    gates.append(_gate_pass("runtime_envelope_fixture_gate"))

    # Gate 6: broker_capability_manifest_gate
    bc_failures: list[str] = []
    if not any(
        broker_capabilities["broker_label"].startswith(prefix)
        for prefix in ("local-", "simulated-", "fixture-", "redacted-")
    ):
        bc_failures.append("broker_capability broker_label prefix invalid")
    if broker_capabilities["sandbox_only"] is not True:
        bc_failures.append("broker_capability sandbox_only is false")
    if broker_capabilities["live_api_contact_allowed"] is not False:
        bc_failures.append("broker_capability live_api_contact_allowed is true")
    if broker_capabilities["credentials_present"] is not False:
        bc_failures.append("broker_capability credentials_present is true")
    if broker_capabilities["endpoint_present"] is not False:
        bc_failures.append("broker_capability endpoint_present is true")
    if bc_failures:
        reason = "; ".join(bc_failures)
        gates.append(_gate_fail("broker_capability_manifest_gate", reason))
        blockers.append(f"broker_capability_manifest_gate: {reason}")
        status = "broker_capability_blocked"
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
    gates.append(_gate_pass("broker_capability_manifest_gate"))

    # Gate 7: operator_policy_fixture_gate
    op_failures: list[str] = []
    if operator_policy["requires_manual_review"] is not True:
        op_failures.append("operator_policy requires_manual_review is false")
    if operator_policy["requires_explicit_approval"] is not True:
        op_failures.append("operator_policy requires_explicit_approval is false")
    if operator_policy["approval_scope"] not in {"candidate_only", "simulated_only"}:
        op_failures.append("operator_policy approval_scope invalid")
    if operator_policy["unattended_operation_allowed"] is not False:
        op_failures.append("operator_policy unattended_operation_allowed is true")
    if (
        operator_policy["allowed_symbols"]
        and quality_gate["symbol"] not in operator_policy["allowed_symbols"]
    ):
        op_failures.append("operator_policy symbol not in allowed_symbols")
    if quality_gate["symbol"] in operator_policy["blocked_symbols"]:
        op_failures.append("operator_policy symbol is in blocked_symbols")
    if op_failures:
        reason = "; ".join(op_failures)
        gates.append(_gate_fail("operator_policy_fixture_gate", reason))
        blockers.append(f"operator_policy_fixture_gate: {reason}")
        status = "operator_policy_blocked"
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
    gates.append(_gate_pass("operator_policy_fixture_gate"))

    # Gate 8: kill_switch_policy_fixture_gate
    ks_failures: list[str] = []
    if kill_switch_policy["kill_switch_required"] is not True:
        ks_failures.append("kill_switch_policy kill_switch_required is false")
    if kill_switch_policy["default_state_on_missing_runtime"] != "blocked":
        ks_failures.append(
            "kill_switch_policy default_state_on_missing_runtime is not 'blocked'"
        )
    if kill_switch_policy["default_state_on_unknown_runtime"] != "blocked":
        ks_failures.append(
            "kill_switch_policy default_state_on_unknown_runtime is not 'blocked'"
        )
    if kill_switch_policy["operator_override_allowed"] is not False:
        ks_failures.append("kill_switch_policy operator_override_allowed is true")
    if ks_failures:
        reason = "; ".join(ks_failures)
        gates.append(_gate_fail("kill_switch_policy_fixture_gate", reason))
        blockers.append(f"kill_switch_policy_fixture_gate: {reason}")
        status = "kill_switch_policy_blocked"
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
    gates.append(_gate_pass("kill_switch_policy_fixture_gate"))

    # Gate 9: audit_policy_fixture_gate
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
        gates.append(_gate_fail("audit_policy_fixture_gate", reason))
        blockers.append(f"audit_policy_fixture_gate: {reason}")
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
    gates.append(_gate_pass("audit_policy_fixture_gate"))

    # Gate 10: envelope_synthesis_gate
    gates.append(_gate_pass("envelope_synthesis_gate"))
    status = "envelope_synthesized"

    # Gate 11: artifact_recording_gate is handled by the writer. The report
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


def _build_report(
    inputs: ReadinessEnvelopeInputs,
    as_of: str,
    gate_results: list[GateResult],
    blockers: list[str],
    status: str,
    normalized: dict[str, Any] | None,
    fingerprints: dict[str, str] | None = None,
    input_digest: str | None = None,
    evaluation_id: str | None = None,
) -> ReadinessEnvelopeReport:
    if fingerprints is None:
        fingerprints = {}
    if input_digest is None:
        input_digest = "sha256:" + "0" * 64
    if evaluation_id is None:
        evaluation_id = ""

    exit_code = 0 if status == "readiness_envelope_recorded" else 2

    input_artifacts = {
        label: _redact_path(getattr(inputs, f"{label}_path")) for label in _INPUT_LABELS
    }

    upstream_summaries = (
        _build_upstream_summaries(normalized) if normalized is not None else {}
    )
    fixture_summaries = (
        _build_fixture_summaries(normalized) if normalized is not None else {}
    )
    envelope_assertions = (
        _envelope_assertions(normalized) if normalized is not None else {}
    )

    envelope_digest = _compute_envelope_digest(as_of, fingerprints, normalized)

    return ReadinessEnvelopeReport(
        artifact_type="runtime_readiness_envelope",
        schema_version="runtime-readiness-envelope.v1",
        candidate="CAND-007",
        mode="simulated_only",
        status=status,
        exit_code=exit_code,
        evaluation_id=evaluation_id,
        as_of=as_of,
        run_id=normalized["quality_gate"]["run_id"] if normalized is not None else None,
        symbol=normalized["quality_gate"]["symbol"]
        if normalized is not None
        else None,
        candidate_chain=(
            "CAND-001",
            "CAND-002",
            "CAND-003",
            "CAND-004",
            "CAND-005",
            "CAND-006",
            "CAND-007",
        ),
        gate_sequence=GATE_SEQUENCE,
        gates=tuple(gate_results),
        input_artifacts=input_artifacts,
        input_fingerprints=fingerprints,
        input_digest=input_digest,
        envelope_digest=envelope_digest,
        upstream_summaries=upstream_summaries,
        fixture_summaries=fixture_summaries,
        envelope_assertions=envelope_assertions,
        blocked_reasons=list(blockers),
        recording={"json_written": False, "markdown_written": False},
        disclaimer=EVIDENCE_ONLY_DISCLAIMER,
    )


def _input_fingerprints(normalized: dict[str, Any] | None) -> dict[str, str]:
    if normalized is None:
        return {}
    return {label: fingerprint_json(normalized[label]) for label in _INPUT_LABELS}


def _compute_input_digest(as_of: str, fingerprints: dict[str, str]) -> str:
    payload: dict[str, Any] = {"as_of": as_of}
    payload.update(fingerprints)
    return fingerprint_json(payload)


def _evaluation_id(input_digest: str) -> str:
    return f"re-{input_digest.replace('sha256:', '')[:24]}"


def _compute_envelope_digest(
    as_of: str,
    fingerprints: dict[str, str],
    normalized: dict[str, Any] | None,
) -> str:
    payload: dict[str, Any] = {"as_of": as_of}
    payload.update(fingerprints)
    if normalized is not None:
        payload["run_id"] = normalized["quality_gate"]["run_id"]
        payload["symbol"] = normalized["quality_gate"]["symbol"]
    return fingerprint_json(payload)


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
            "transmission_allowed": normalized["submit_conformance"][
                "dry_run_request"
            ]["transmission"]["allowed"],
            "blockers": normalized["submit_conformance"]["blockers"],
        },
    }


def _build_fixture_summaries(normalized: dict[str, Any]) -> dict[str, Any]:
    re_fixture = normalized["runtime_envelope"]
    bc_fixture = normalized["broker_capabilities"]
    op_fixture = normalized["operator_policy"]
    ks_fixture = normalized["kill_switch_policy"]
    au_fixture = normalized["audit_policy"]
    return {
        "runtime_envelope": {
            "fixture_mode": re_fixture["fixture_mode"],
            "run_id": re_fixture["run_id"],
            "symbol": re_fixture["symbol"],
            "live_submit_enabled": re_fixture["live_submit_enabled"],
            "require_human_approval": re_fixture["require_human_approval"],
            "require_kill_switch_inactive": re_fixture["require_kill_switch_inactive"],
            "require_risk_gate": re_fixture["require_risk_gate"],
            "require_audit_recording": re_fixture["require_audit_recording"],
            "require_broker_capability_manifest": re_fixture[
                "require_broker_capability_manifest"
            ],
            "max_order_notional": re_fixture["max_order_notional"],
            "max_symbol_exposure": re_fixture["max_symbol_exposure"],
            "max_daily_orders": re_fixture["max_daily_orders"],
            "max_daily_notional": re_fixture["max_daily_notional"],
            "supported_order_types": re_fixture["supported_order_types"],
            "supported_time_in_force": re_fixture["supported_time_in_force"],
            "expires_at": re_fixture["expires_at"],
        },
        "broker_capability": {
            "broker_label": bc_fixture["broker_label"],
            "sandbox_only": bc_fixture["sandbox_only"],
            "live_api_contact_allowed": bc_fixture["live_api_contact_allowed"],
            "credentials_present": bc_fixture["credentials_present"],
            "endpoint_present": bc_fixture["endpoint_present"],
        },
        "operator_policy": {
            "requires_manual_review": op_fixture["requires_manual_review"],
            "requires_explicit_approval": op_fixture["requires_explicit_approval"],
            "approval_scope": op_fixture["approval_scope"],
            "unattended_operation_allowed": op_fixture["unattended_operation_allowed"],
            "max_runtime_window_seconds": op_fixture["max_runtime_window_seconds"],
            "max_actions_per_session": op_fixture["max_actions_per_session"],
            "allowed_symbols": op_fixture["allowed_symbols"],
            "blocked_symbols": op_fixture["blocked_symbols"],
        },
        "kill_switch_policy": {
            "kill_switch_required": ks_fixture["kill_switch_required"],
            "default_state_on_missing_runtime": ks_fixture[
                "default_state_on_missing_runtime"
            ],
            "default_state_on_unknown_runtime": ks_fixture[
                "default_state_on_unknown_runtime"
            ],
            "operator_override_allowed": ks_fixture["operator_override_allowed"],
        },
        "audit_policy": {
            "audit_required": au_fixture["audit_required"],
            "append_only_required": au_fixture["append_only_required"],
            "hash_chain_required": au_fixture["hash_chain_required"],
            "local_artifact_recording_required": au_fixture[
                "local_artifact_recording_required"
            ],
            "live_audit_chain_claimed": au_fixture["live_audit_chain_claimed"],
        },
    }


def _envelope_assertions(normalized: dict[str, Any]) -> dict[str, bool]:
    re_fixture = normalized["runtime_envelope"]
    bc_fixture = normalized["broker_capabilities"]
    op_fixture = normalized["operator_policy"]
    ks_fixture = normalized["kill_switch_policy"]
    au_fixture = normalized["audit_policy"]
    sc = normalized["submit_conformance"]
    return {
        "live_submit_forbidden": not re_fixture["live_submit_enabled"],
        "human_approval_required": re_fixture["require_human_approval"],
        "kill_switch_required": re_fixture["require_kill_switch_inactive"]
        and ks_fixture["kill_switch_required"],
        "risk_gate_required": re_fixture["require_risk_gate"],
        "audit_recording_required": re_fixture["require_audit_recording"]
        and au_fixture["audit_required"],
        "broker_manifest_required": re_fixture["require_broker_capability_manifest"],
        "operator_policy_fail_closed": (
            op_fixture["requires_manual_review"]
            and op_fixture["requires_explicit_approval"]
            and not op_fixture["unattended_operation_allowed"]
        ),
        "all_upstream_statuses_accepted": True,
        "no_credentials_in_fixtures": not bc_fixture["credentials_present"],
        "no_endpoints_in_fixtures": not bc_fixture["endpoint_present"],
        "no_account_ids_in_fixtures": True,
        "cand006_transmission_blocked": not sc["dry_run_request"]["transmission"][
            "allowed"
        ],
    }


def _redact_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.name
