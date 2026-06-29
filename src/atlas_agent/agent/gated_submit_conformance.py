from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal


APPROVED_FINAL_STATUSES = (
    "not_evaluated",
    "blocked",
    "approval_required",
    "risk_blocked",
    "kill_switch_blocked",
    "shadow_divergence_blocked",
    "dry_run_ready",
    "dry_run_recorded",
)

GATE_SEQUENCE = (
    "schema_preflight",
    "cand004_quality_gate",
    "cand005_shadow_live_comparison",
    "kill_switch_fixture",
    "risk_envelope_fixture",
    "approval_fixture",
    "dry_run_conversion",
    "atomic_artifact_recording",
)

_ARTIFACT_TYPE_ORDER_INTENT = "gated_submit_order_intent"
_SCHEMA_VERSION_ORDER_INTENT = "gated-submit-order-intent.v1"
_ARTIFACT_TYPE_KILL_SWITCH = "gated_submit_kill_switch_fixture"
_SCHEMA_VERSION_KILL_SWITCH = "gated-submit-kill-switch.v1"
_ARTIFACT_TYPE_RISK = "gated_submit_risk_envelope_fixture"
_SCHEMA_VERSION_RISK = "gated-submit-risk-envelope.v1"
_ARTIFACT_TYPE_APPROVAL = "gated_submit_approval_fixture"
_SCHEMA_VERSION_APPROVAL = "gated-submit-approval-fixture.v1"

_TRADING_QUALITY_GATE_ARTIFACT_TYPE = "trading_quality_gate"
_TRADING_QUALITY_GATE_SCHEMA_VERSIONS = ("trading-quality-gate.v1", 1, "1")
_SHADOW_LIVE_COMPARISON_ARTIFACT_TYPE = "shadow_live_comparison"
_SHADOW_LIVE_COMPARISON_SCHEMA_VERSION = "shadow-live-comparison.v1"

_JSON_ARTIFACT_NAME = "gated-submit-conformance.json"
_MARKDOWN_ARTIFACT_NAME = "gated-submit-conformance-report.md"

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,23}$")
_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")

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

_FORBIDDEN_FIXTURE_KEYS = {
    "account",
    "account_id",
    "broker",
    "broker_id",
    "provider",
    "endpoint",
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


class ConformanceValidationError(Exception):
    """Raised when a fixture or input fails closed-schema validation."""

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
class SubmitConformanceInputs:
    quality_gate_path: Path
    shadow_comparison_path: Path
    order_intent_path: Path
    kill_switch_path: Path
    risk_envelope_path: Path
    approval_path: Path
    output_dir: Path | None
    as_of: str


@dataclass(frozen=True)
class DryRunSubmitRequest:
    artifact_type: str
    schema_version: str
    request_id: str
    evaluation_id: str
    as_of: str
    intent_id: str
    symbol: str
    side: str
    quantity: str
    order_type: str
    limit_price: str | None
    estimated_notional: str
    source_fingerprints: dict[str, str]
    transmission: dict[str, Any]
    runtime_effects: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "evaluation_id": self.evaluation_id,
            "as_of": self.as_of,
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "estimated_notional": self.estimated_notional,
            "source_fingerprints": self.source_fingerprints,
            "transmission": self.transmission,
            "runtime_effects": self.runtime_effects,
        }


@dataclass(frozen=True)
class SubmitConformanceReport:
    artifact_type: str
    schema_version: str
    candidate: str
    mode: str
    evaluation_id: str
    as_of: str
    input_digest: str
    status: str
    exit_code: int
    gate_sequence: tuple[str, ...]
    gates: tuple[GateResult, ...]
    input_artifacts: dict[str, str | None]
    input_fingerprints: dict[str, str]
    run_id: str | None
    intent_id: str | None
    symbol: str | None
    quality_gate_summary: dict[str, Any]
    shadow_live_summary: dict[str, Any]
    kill_switch_summary: dict[str, Any]
    risk_summary: dict[str, Any]
    approval_summary: dict[str, Any]
    dry_run_request: DryRunSubmitRequest | None
    dry_run_request_fingerprint: str | None
    safety_assertions: dict[str, bool]
    recording: dict[str, Any]
    blockers: list[str]
    disclaimer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "candidate": self.candidate,
            "mode": self.mode,
            "evaluation_id": self.evaluation_id,
            "as_of": self.as_of,
            "input_digest": self.input_digest,
            "status": self.status,
            "exit_code": self.exit_code,
            "gate_sequence": list(self.gate_sequence),
            "gates": [g.to_dict() for g in self.gates],
            "input_artifacts": self.input_artifacts,
            "input_fingerprints": self.input_fingerprints,
            "run_id": self.run_id,
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "quality_gate_summary": self.quality_gate_summary,
            "shadow_live_summary": self.shadow_live_summary,
            "kill_switch_summary": self.kill_switch_summary,
            "risk_summary": self.risk_summary,
            "approval_summary": self.approval_summary,
            "dry_run_request": (
                self.dry_run_request.to_dict() if self.dry_run_request else None
            ),
            "dry_run_request_fingerprint": self.dry_run_request_fingerprint,
            "safety_assertions": self.safety_assertions,
            "recording": self.recording,
            "blockers": self.blockers,
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


def parse_as_of_utc(value: str) -> str:
    """Parse and normalize an ISO-8601 UTC timestamp string.

    Accepts ``2026-06-24T10:00:00Z`` and ``2026-06-24T10:00:00+00:00``.
    Rejects naive timestamps, non-UTC offsets, and non-ISO strings.
    """
    if not isinstance(value, str):
        raise ConformanceValidationError("as_of is not a string")
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise ConformanceValidationError(
            f"as_of is not a valid ISO-8601 UTC timestamp: {value!r}"
        )
    return _format_utc_timestamp(parsed)


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


def _canonical_decimal_string(value: Any, *, allow_zero: bool = True) -> str:
    """Normalize a decimal string and reject non-canonical or invalid forms."""
    if not isinstance(value, str):
        raise ConformanceValidationError(
            f"expected decimal string, got {type(value).__name__}"
        )
    if "e" in value.lower():
        raise ConformanceValidationError("exponent notation is not allowed")
    if value.startswith("+"):
        raise ConformanceValidationError("leading plus sign is not allowed")
    try:
        dec = Decimal(value)
    except InvalidOperation as exc:
        raise ConformanceValidationError(f"invalid decimal: {exc}") from None
    if dec.is_nan() or not dec.is_finite():
        raise ConformanceValidationError("NaN and Infinity are not allowed")
    if dec == 0 and dec.as_tuple().sign == 1:
        raise ConformanceValidationError("negative zero is not allowed")
    if not allow_zero and dec == 0:
        raise ConformanceValidationError("zero is not allowed")
    canonical = format(dec.normalize(), "f")
    # Re-normalize integral values to plain digits.
    try:
        if Decimal(canonical) == Decimal(canonical).to_integral_value():
            canonical = str(Decimal(canonical).to_integral_value())
    except InvalidOperation:
        pass
    return canonical


def _positive_decimal_string(value: Any) -> str:
    s = _canonical_decimal_string(value, allow_zero=False)
    if Decimal(s) <= 0:
        raise ConformanceValidationError("value must be positive")
    return s


def _non_negative_decimal_string(value: Any) -> str:
    s = _canonical_decimal_string(value)
    if Decimal(s) < 0:
        raise ConformanceValidationError("value must be non-negative")
    return s


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ConformanceValidationError(f"{name} must be a string")
    return value


def _require_exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ConformanceValidationError(
            f"{label} contains unknown keys: {sorted(unknown)}"
        )


def _require_nonempty_bounded_id(value: str, name: str) -> None:
    if not value:
        raise ConformanceValidationError(f"{name} must be non-empty")
    if len(value) > 128:
        raise ConformanceValidationError(f"{name} exceeds 128 characters")
    if not _ID_RE.match(value):
        raise ConformanceValidationError(f"{name} contains invalid characters")


def _secret_value_match(lower_value: str, pattern: str) -> bool:
    """Return True if ``pattern`` appears as a secret-like token in the value."""
    # Require the pattern to start at a word boundary so that benign substrings
    # such as the "sk-" inside "risk-envelope" are not flagged.
    return re.search(r"(?:^|\W)" + re.escape(pattern), lower_value) is not None


def _secret_scan(obj: Any, path: str = "") -> list[str]:
    """Return a list of secret-like findings in a parsed JSON object."""
    findings: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = key.lower()
            if key_lower in _SECRET_KEYS:
                findings.append(f"secret-like key at {path}: {key}")
            if key_lower in _FORBIDDEN_FIXTURE_KEYS:
                findings.append(f"forbidden key at {path}: {key}")
            for pattern in _SECRET_VALUE_PATTERNS:
                if _secret_value_match(key_lower, pattern):
                    findings.append(f"secret-like key fragment at {path}: {key}")
            findings.extend(_secret_scan(value, f"{path}.{key}" if path else key))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            findings.extend(_secret_scan(value, f"{path}[{idx}]"))
    elif isinstance(obj, str):
        lower = obj.lower()
        for pattern in _SECRET_VALUE_PATTERNS:
            if _secret_value_match(lower, pattern):
                findings.append(f"secret-like value at {path}: {pattern!r}")
    return findings


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    """Load a JSON object from a path, rejecting non-objects and NaN/Infinity."""
    if not path.is_file():
        raise ConformanceValidationError(f"{label} file not found: {path.name}")
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ConformanceValidationError(f"failed to read {label}: {exc}") from None
    if not text.strip():
        raise ConformanceValidationError(f"{label} file is empty")
    try:
        data = json.loads(text, parse_constant=lambda c: c)
    except json.JSONDecodeError as exc:
        raise ConformanceValidationError(f"{label} is not valid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ConformanceValidationError(f"{label} is not a JSON object")
    # Reject JSON constants such as NaN/Infinity that leak through.
    raw_text = text.lower()
    for constant in ("nan", "infinity", "-infinity"):
        if constant in raw_text:
            raise ConformanceValidationError(
                f"{label} contains forbidden JSON constant: {constant}"
            )
    return data


def _validate_order_intent(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "artifact_type",
        "schema_version",
        "intent_kind",
        "intent_id",
        "run_id",
        "symbol",
        "side",
        "quantity",
        "order_type",
        "limit_price",
        "time_in_force",
        "created_at",
    }
    _require_exact_keys(data, allowed, "order_intent")

    artifact_type = _require_string(data.get("artifact_type"), "order_intent.artifact_type")
    schema_version = _require_string(
        data.get("schema_version"), "order_intent.schema_version"
    )
    if artifact_type != _ARTIFACT_TYPE_ORDER_INTENT:
        raise ConformanceValidationError("order_intent artifact_type mismatch")
    if schema_version != _SCHEMA_VERSION_ORDER_INTENT:
        raise ConformanceValidationError("order_intent schema_version mismatch")

    intent_kind = _require_string(data.get("intent_kind"), "order_intent.intent_kind")
    if intent_kind not in {"paper_proposal", "hypothetical"}:
        raise ConformanceValidationError("order_intent intent_kind invalid")

    intent_id = _require_string(data.get("intent_id"), "order_intent.intent_id")
    run_id = _require_string(data.get("run_id"), "order_intent.run_id")
    symbol = _require_string(data.get("symbol"), "order_intent.symbol")
    _require_nonempty_bounded_id(intent_id, "order_intent.intent_id")
    _require_nonempty_bounded_id(run_id, "order_intent.run_id")
    if not _SYMBOL_RE.match(symbol):
        raise ConformanceValidationError("order_intent symbol invalid")

    side = _require_string(data.get("side"), "order_intent.side")
    if side not in {"buy", "sell"}:
        raise ConformanceValidationError("order_intent side invalid")

    order_type = _require_string(data.get("order_type"), "order_intent.order_type")
    if order_type not in {"market", "limit"}:
        raise ConformanceValidationError("order_intent order_type invalid")

    time_in_force = _require_string(
        data.get("time_in_force"), "order_intent.time_in_force"
    )
    if time_in_force != "day":
        raise ConformanceValidationError("order_intent time_in_force invalid")

    quantity = _positive_decimal_string(data.get("quantity"))

    limit_price: str | None = None
    if order_type == "limit":
        if "limit_price" not in data:
            raise ConformanceValidationError(
                "order_intent limit_price is required for limit orders"
            )
        limit_price = _positive_decimal_string(data.get("limit_price"))
    elif "limit_price" in data:
        raise ConformanceValidationError(
            "order_intent limit_price must be absent for market orders"
        )

    created_at = _require_string(data.get("created_at"), "order_intent.created_at")
    created_at = _format_utc_timestamp(_parse_or_fail(created_at, "order_intent.created_at"))

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "intent_kind": intent_kind,
        "intent_id": intent_id,
        "run_id": run_id,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "limit_price": limit_price,
        "time_in_force": time_in_force,
        "created_at": created_at,
    }


def _parse_or_fail(value: str, label: str) -> Any:
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise ConformanceValidationError(f"{label} is not a valid ISO-8601 UTC timestamp")
    return parsed


def _validate_kill_switch(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "artifact_type",
        "schema_version",
        "fixture_mode",
        "scope",
        "state",
        "captured_at",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "kill_switch")

    artifact_type = _require_string(data.get("artifact_type"), "kill_switch.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "kill_switch.schema_version")
    if artifact_type != _ARTIFACT_TYPE_KILL_SWITCH:
        raise ConformanceValidationError("kill_switch artifact_type mismatch")
    if schema_version != _SCHEMA_VERSION_KILL_SWITCH:
        raise ConformanceValidationError("kill_switch schema_version mismatch")

    fixture_mode = _require_string(data.get("fixture_mode"), "kill_switch.fixture_mode")
    if fixture_mode != "simulated":
        raise ConformanceValidationError("kill_switch fixture_mode must be 'simulated'")

    scope = _require_string(data.get("scope"), "kill_switch.scope")
    if scope != "conformance_rehearsal_only":
        raise ConformanceValidationError("kill_switch scope invalid")

    state = _require_string(data.get("state"), "kill_switch.state")
    if state not in {"inactive", "active", "unknown"}:
        raise ConformanceValidationError("kill_switch state invalid")

    captured_at = _format_utc_timestamp(
        _parse_or_fail(
            _require_string(data.get("captured_at"), "kill_switch.captured_at"),
            "kill_switch.captured_at",
        )
    )
    expires_at = _format_utc_timestamp(
        _parse_or_fail(
            _require_string(data.get("expires_at"), "kill_switch.expires_at"),
            "kill_switch.expires_at",
        )
    )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "fixture_mode": fixture_mode,
        "scope": scope,
        "state": state,
        "captured_at": captured_at,
        "expires_at": expires_at,
    }


def _validate_risk_envelope(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "artifact_type",
        "schema_version",
        "fixture_mode",
        "represents",
        "evaluation_mode",
        "intent_fingerprint",
        "captured_at",
        "expires_at",
        "decision",
        "evaluated_price",
        "evaluated_notional",
        "checks",
        "violations",
        "limits_digest",
        "portfolio_snapshot_digest",
    }
    _require_exact_keys(data, allowed, "risk_envelope")

    artifact_type = _require_string(data.get("artifact_type"), "risk_envelope.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "risk_envelope.schema_version")
    if artifact_type != _ARTIFACT_TYPE_RISK:
        raise ConformanceValidationError("risk_envelope artifact_type mismatch")
    if schema_version != _SCHEMA_VERSION_RISK:
        raise ConformanceValidationError("risk_envelope schema_version mismatch")

    fixture_mode = _require_string(data.get("fixture_mode"), "risk_envelope.fixture_mode")
    if fixture_mode != "simulated":
        raise ConformanceValidationError("risk_envelope fixture_mode must be 'simulated'")

    represents = _require_string(data.get("represents"), "risk_envelope.represents")
    if represents != "RiskManager_evaluation":
        raise ConformanceValidationError("risk_envelope represents invalid")

    evaluation_mode = _require_string(
        data.get("evaluation_mode"), "risk_envelope.evaluation_mode"
    )
    if evaluation_mode != "paper":
        raise ConformanceValidationError("risk_envelope evaluation_mode must be 'paper'")

    intent_fingerprint = _require_string(
        data.get("intent_fingerprint"), "risk_envelope.intent_fingerprint"
    )
    decision = _require_string(data.get("decision"), "risk_envelope.decision")
    if decision not in {"allowed", "blocked", "requires_approval"}:
        raise ConformanceValidationError("risk_envelope decision invalid")

    evaluated_price = _positive_decimal_string(data.get("evaluated_price"))
    evaluated_notional = _non_negative_decimal_string(data.get("evaluated_notional"))

    captured_at = _format_utc_timestamp(
        _parse_or_fail(
            _require_string(data.get("captured_at"), "risk_envelope.captured_at"),
            "risk_envelope.captured_at",
        )
    )
    expires_at = _format_utc_timestamp(
        _parse_or_fail(
            _require_string(data.get("expires_at"), "risk_envelope.expires_at"),
            "risk_envelope.expires_at",
        )
    )

    limits_digest = _require_string(data.get("limits_digest"), "risk_envelope.limits_digest")
    portfolio_snapshot_digest = _require_string(
        data.get("portfolio_snapshot_digest"), "risk_envelope.portfolio_snapshot_digest"
    )
    for digest, name in (
        (limits_digest, "limits_digest"),
        (portfolio_snapshot_digest, "portfolio_snapshot_digest"),
    ):
        if not digest.startswith("sha256:"):
            raise ConformanceValidationError(f"risk_envelope {name} must start with sha256:")

    checks_raw = data.get("checks")
    if not isinstance(checks_raw, list):
        raise ConformanceValidationError("risk_envelope checks must be a list")
    checks: list[dict[str, Any]] = []
    for idx, check in enumerate(checks_raw):
        if not isinstance(check, dict):
            raise ConformanceValidationError(f"risk_envelope check[{idx}] is not an object")
        _require_exact_keys(check, {"rule", "passed"}, f"risk_envelope.check[{idx}]")
        rule = _require_string(check.get("rule"), f"risk_envelope.check[{idx}].rule")
        if not rule:
            raise ConformanceValidationError(
                f"risk_envelope check[{idx}].rule must be non-empty"
            )
        if len(rule) > 128:
            raise ConformanceValidationError(
                f"risk_envelope check[{idx}].rule exceeds 128 characters"
            )
        passed = check.get("passed")
        if not isinstance(passed, bool):
            raise ConformanceValidationError(
                f"risk_envelope check[{idx}].passed must be a boolean"
            )
        checks.append({"rule": rule, "passed": passed})

    violations = data.get("violations")
    if not isinstance(violations, list):
        raise ConformanceValidationError("risk_envelope violations must be a list")

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "fixture_mode": fixture_mode,
        "represents": represents,
        "evaluation_mode": evaluation_mode,
        "intent_fingerprint": intent_fingerprint,
        "decision": decision,
        "evaluated_price": evaluated_price,
        "evaluated_notional": evaluated_notional,
        "captured_at": captured_at,
        "expires_at": expires_at,
        "checks": checks,
        "violations": violations,
        "limits_digest": limits_digest,
        "portfolio_snapshot_digest": portfolio_snapshot_digest,
    }


def _validate_approval(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "artifact_type",
        "schema_version",
        "fixture_mode",
        "scope",
        "fixture_id",
        "intent_fingerprint",
        "risk_envelope_fingerprint",
        "decision",
        "actor_label",
        "approved_at",
        "expires_at",
    }
    _require_exact_keys(data, allowed, "approval")

    artifact_type = _require_string(data.get("artifact_type"), "approval.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "approval.schema_version")
    if artifact_type != _ARTIFACT_TYPE_APPROVAL:
        raise ConformanceValidationError("approval artifact_type mismatch")
    if schema_version != _SCHEMA_VERSION_APPROVAL:
        raise ConformanceValidationError("approval schema_version mismatch")

    fixture_mode = _require_string(data.get("fixture_mode"), "approval.fixture_mode")
    if fixture_mode != "simulated":
        raise ConformanceValidationError("approval fixture_mode must be 'simulated'")

    scope = _require_string(data.get("scope"), "approval.scope")
    if scope != "conformance_rehearsal_only":
        raise ConformanceValidationError("approval scope invalid")

    fixture_id = _require_string(data.get("fixture_id"), "approval.fixture_id")
    _require_nonempty_bounded_id(fixture_id, "approval.fixture_id")

    intent_fingerprint = _require_string(
        data.get("intent_fingerprint"), "approval.intent_fingerprint"
    )
    risk_envelope_fingerprint = _require_string(
        data.get("risk_envelope_fingerprint"), "approval.risk_envelope_fingerprint"
    )

    decision = _require_string(data.get("decision"), "approval.decision")
    if decision not in {"approved", "denied"}:
        raise ConformanceValidationError("approval decision invalid")

    actor_label: str | None = None
    if "actor_label" in data:
        actor_label = _require_string(data.get("actor_label"), "approval.actor_label")
        if actor_label:
            if len(actor_label) > 128:
                raise ConformanceValidationError("approval.actor_label exceeds 128 characters")
            # Reject secret-like actor labels without blocking simulated examples.
            lower = actor_label.lower()
            if any(pattern in lower for pattern in ("api_key", "token", "secret", "password")):
                raise ConformanceValidationError("approval.actor_label looks secret-like")

    approved_at = _format_utc_timestamp(
        _parse_or_fail(
            _require_string(data.get("approved_at"), "approval.approved_at"),
            "approval.approved_at",
        )
    )
    expires_at = _format_utc_timestamp(
        _parse_or_fail(
            _require_string(data.get("expires_at"), "approval.expires_at"),
            "approval.expires_at",
        )
    )

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "fixture_mode": fixture_mode,
        "scope": scope,
        "fixture_id": fixture_id,
        "intent_fingerprint": intent_fingerprint,
        "risk_envelope_fingerprint": risk_envelope_fingerprint,
        "decision": decision,
        "actor_label": actor_label,
        "approved_at": approved_at,
        "expires_at": expires_at,
    }


def _validate_quality_gate(data: dict[str, Any]) -> dict[str, Any]:
    """Project CAND-004 to accepted keys and normalize for downstream gates."""
    accepted = {
        "artifact_type",
        "schema_version",
        "mode",
        "run_id",
        "symbol",
        "quality_state",
        "blockers",
    }
    _require_exact_keys(data, accepted, "quality_gate (projected)")

    artifact_type = _require_string(
        data.get("artifact_type"), "quality_gate.artifact_type"
    )
    schema_version = data.get("schema_version")
    mode = _require_string(data.get("mode"), "quality_gate.mode")
    run_id = _require_string(data.get("run_id"), "quality_gate.run_id")
    symbol = _require_string(data.get("symbol"), "quality_gate.symbol")
    quality_state = _require_string(
        data.get("quality_state"), "quality_gate.quality_state"
    )
    blockers = data.get("blockers")

    if artifact_type != _TRADING_QUALITY_GATE_ARTIFACT_TYPE:
        raise ConformanceValidationError("quality_gate artifact_type mismatch")
    if schema_version not in _TRADING_QUALITY_GATE_SCHEMA_VERSIONS:
        raise ConformanceValidationError("quality_gate schema_version mismatch")
    if not isinstance(blockers, list):
        raise ConformanceValidationError("quality_gate blockers must be a list")

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "mode": mode,
        "run_id": run_id,
        "symbol": symbol,
        "quality_state": quality_state,
        "blockers": blockers,
    }


def _validate_shadow_comparison(data: dict[str, Any]) -> dict[str, Any]:
    """Project CAND-005 to accepted keys and normalize for downstream gates."""
    accepted = {
        "artifact_type",
        "schema_version",
        "run_id",
        "symbol",
        "quality_state",
        "status",
        "freshness_assessment",
        "blockers",
    }
    _require_exact_keys(data, accepted, "shadow_comparison (projected)")

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
        raise ConformanceValidationError("shadow_comparison artifact_type mismatch")
    if schema_version != _SHADOW_LIVE_COMPARISON_SCHEMA_VERSION:
        raise ConformanceValidationError("shadow_comparison schema_version mismatch")
    if not isinstance(freshness_assessment, dict):
        raise ConformanceValidationError("shadow_comparison freshness_assessment must be an object")
    if not isinstance(blockers, list):
        raise ConformanceValidationError("shadow_comparison blockers must be a list")

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


def _load_and_validate_all(
    inputs: SubmitConformanceInputs,
) -> dict[str, Any]:
    """Load and closed-schema validate every input fixture.

    Returns a dict of normalized fixture dicts keyed by label. Raises
    ConformanceValidationError on any closed-schema failure.
    """
    paths = {
        "quality_gate": inputs.quality_gate_path,
        "shadow_comparison": inputs.shadow_comparison_path,
        "order_intent": inputs.order_intent_path,
        "kill_switch": inputs.kill_switch_path,
        "risk_envelope": inputs.risk_envelope_path,
        "approval": inputs.approval_path,
    }
    raw: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        raw[label] = _load_json_object(path, label)
        secrets = _secret_scan(raw[label], label)
        if secrets:
            raise ConformanceValidationError(
                "secret-like content rejected: " + "; ".join(secrets)
            )

    normalized: dict[str, Any] = {
        "order_intent": _validate_order_intent(raw["order_intent"]),
        "kill_switch": _validate_kill_switch(raw["kill_switch"]),
        "risk_envelope": _validate_risk_envelope(raw["risk_envelope"]),
        "approval": _validate_approval(raw["approval"]),
        "quality_gate": _validate_quality_gate(raw["quality_gate"]),
        "shadow_comparison": _validate_shadow_comparison(raw["shadow_comparison"]),
    }
    return normalized


def _timestamp_not_before(timestamp: str, as_of: str) -> bool:
    """Return True if ``timestamp`` is at or after ``as_of``."""
    return _parse_iso_timestamp(timestamp) >= _parse_iso_timestamp(as_of)


def _input_fingerprints(normalized: dict[str, Any]) -> dict[str, str]:
    return {label: fingerprint_json(value) for label, value in normalized.items()}


def _compute_input_digest(as_of: str, fingerprints: dict[str, str]) -> str:
    payload = {
        "as_of": as_of,
        "quality_gate": fingerprints["quality_gate"],
        "shadow_comparison": fingerprints["shadow_comparison"],
        "order_intent": fingerprints["order_intent"],
        "kill_switch": fingerprints["kill_switch"],
        "risk_envelope": fingerprints["risk_envelope"],
        "approval": fingerprints["approval"],
    }
    return fingerprint_json(payload)


def _evaluation_id(input_digest: str) -> str:
    return f"gsc-{input_digest.replace('sha256:', '')[:24]}"


def _redact_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.name


def _safety_assertions() -> dict[str, bool]:
    return {
        "simulated_only": True,
        "no_live_submit": True,
        "no_broker_called": True,
        "no_provider_called": True,
        "no_credentials_loaded": True,
        "no_runtime_state_mutation": True,
        "no_order_instantiated": True,
        "transmission_blocked": True,
        "json_authoritative": True,
    }


def _build_dry_run_request(
    evaluation_id: str,
    as_of: str,
    order_intent: dict[str, Any],
    risk_envelope: dict[str, Any],
    fingerprints: dict[str, str],
) -> DryRunSubmitRequest:
    intent_id = order_intent["intent_id"]
    symbol = order_intent["symbol"]
    side = order_intent["side"]
    quantity = order_intent["quantity"]
    order_type = order_intent["order_type"]
    limit_price = order_intent.get("limit_price")
    estimated_notional = risk_envelope["evaluated_notional"]

    request_id_payload = {
        "intent_id": intent_id,
        "evaluation_id": evaluation_id,
        "as_of": as_of,
    }
    request_id = "cand006-" + fingerprint_json(request_id_payload).replace("sha256:", "")[:16]

    return DryRunSubmitRequest(
        artifact_type="non_transmittable_dry_run_submit_request",
        schema_version="gated-submit-dry-run-request.v1",
        request_id=request_id,
        evaluation_id=evaluation_id,
        as_of=as_of,
        intent_id=intent_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price,
        estimated_notional=estimated_notional,
        source_fingerprints=dict(fingerprints),
        transmission={
            "allowed": False,
            "reason": "CAND-006 simulated-only conformance rehearsal",
            "broker_adapter": None,
            "provider": None,
        },
        runtime_effects={
            "order_instantiated": False,
            "pending_order_created": False,
            "broker_called": False,
            "provider_called": False,
            "credentials_loaded": False,
            "network_called": False,
            "runtime_state_mutated": False,
        },
    )


def _gate_pass(gate_id: str, details: dict[str, Any] | None = None) -> GateResult:
    return GateResult(gate_id=gate_id, status="pass", reason="", details=details or {})


def _gate_fail(
    gate_id: str, reason: str, details: dict[str, Any] | None = None
) -> GateResult:
    return GateResult(gate_id=gate_id, status="fail", reason=reason, details=details or {})


def _gate_not_run(gate_id: str, reason: str = "prior gate failed") -> GateResult:
    return GateResult(gate_id=gate_id, status="not_run", reason=reason)


def _check_path_aliases(inputs: SubmitConformanceInputs) -> list[str]:
    """Reject output paths that alias any input path or each other."""
    errors: list[str] = []
    if inputs.output_dir is None:
        return errors

    input_paths = [
        ("quality_gate", inputs.quality_gate_path),
        ("shadow_comparison", inputs.shadow_comparison_path),
        ("order_intent", inputs.order_intent_path),
        ("kill_switch", inputs.kill_switch_path),
        ("risk_envelope", inputs.risk_envelope_path),
        ("approval", inputs.approval_path),
    ]

    try:
        output_dir = inputs.output_dir.resolve()
    except Exception as exc:
        return [f"output_dir cannot be resolved: {exc}"]

    resolved_inputs: dict[str, Path] = {}
    for label, path in input_paths:
        try:
            resolved = path.resolve()
        except Exception as exc:
            errors.append(f"{label} path cannot be resolved: {exc}")
            continue
        resolved_inputs[label] = resolved
        if resolved == output_dir:
            errors.append(f"output_dir aliases {label} input path")

    def _alias_check(candidate: Path, name: str) -> None:
        try:
            resolved = candidate.resolve()
        except Exception as exc:
            errors.append(f"{name} cannot be resolved: {exc}")
            return
        if resolved in resolved_inputs.values():
            errors.append(f"{name} aliases an input path")
        # If the output directory is the same as an input parent, a misnamed
        # output artifact could overwrite an input. We allow different basenames
        # only after this check has already rejected identical resolved paths.

    json_out = output_dir / _JSON_ARTIFACT_NAME
    md_out = output_dir / _MARKDOWN_ARTIFACT_NAME
    _alias_check(json_out, "output JSON artifact")
    _alias_check(md_out, "output Markdown artifact")

    return errors


def build_gated_submit_conformance_report(
    inputs: SubmitConformanceInputs,
) -> SubmitConformanceReport:
    """Evaluate all gates in strict fail-closed order and build a report.

    This function performs no I/O beyond reading the input fixture files supplied
    in ``inputs``. Artifact writing is a separate step.
    """
    as_of = parse_as_of_utc(inputs.as_of)

    gates: list[GateResult] = []
    blockers: list[str] = []
    status = "not_evaluated"
    dry_run_request: DryRunSubmitRequest | None = None
    dry_run_request_fingerprint: str | None = None
    recording: dict[str, Any] = {}

    # Gate 1: schema_preflight
    try:
        alias_errors = _check_path_aliases(inputs)
        if alias_errors:
            raise ConformanceValidationError("; ".join(alias_errors))
        normalized = _load_and_validate_all(inputs)
        gates.append(_gate_pass("schema_preflight"))
    except ConformanceValidationError as exc:
        gates.append(_gate_fail("schema_preflight", str(exc)))
        blockers.append(f"schema_preflight: {exc}")
        status = "not_evaluated"
        # Remaining gates are not_run.
        for gate_id in GATE_SEQUENCE[1:]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gates=tuple(gates),
            status=status,
            blockers=blockers,
            dry_run_request=None,
            dry_run_request_fingerprint=None,
            recording=recording,
            normalized=None,
        )

    fingerprints = _input_fingerprints(normalized)
    input_digest = _compute_input_digest(as_of, fingerprints)
    evaluation_id = _evaluation_id(input_digest)

    order_intent = normalized["order_intent"]
    quality_gate = normalized["quality_gate"]
    shadow_comparison = normalized["shadow_comparison"]
    kill_switch = normalized["kill_switch"]
    risk_envelope = normalized["risk_envelope"]
    approval = normalized["approval"]

    # Gate 2: cand004_quality_gate
    if quality_gate.get("artifact_type") != _TRADING_QUALITY_GATE_ARTIFACT_TYPE:
        gates.append(_gate_fail("cand004_quality_gate", "artifact_type mismatch"))
        blockers.append("cand004_quality_gate: artifact_type mismatch")
        status = "blocked"
    elif quality_gate.get("mode") != "paper":
        gates.append(_gate_fail("cand004_quality_gate", "mode is not 'paper'"))
        blockers.append("cand004_quality_gate: mode is not 'paper'")
        status = "blocked"
    elif quality_gate.get("quality_state") != "eligible_for_shadow_live_quality_review":
        gates.append(
            _gate_fail(
                "cand004_quality_gate",
                f"quality_state is '{quality_gate.get('quality_state')}'",
            )
        )
        blockers.append(
            f"cand004_quality_gate: quality_state is '{quality_gate.get('quality_state')}'"
        )
        status = "blocked"
    elif quality_gate.get("blockers"):
        gates.append(
            _gate_fail("cand004_quality_gate", "quality_gate blockers non-empty")
        )
        blockers.append("cand004_quality_gate: blockers non-empty")
        status = "blocked"
    elif quality_gate.get("run_id") != order_intent.get("run_id"):
        gates.append(_gate_fail("cand004_quality_gate", "run_id mismatch"))
        blockers.append("cand004_quality_gate: run_id mismatch")
        status = "blocked"
    elif quality_gate.get("symbol") != order_intent.get("symbol"):
        gates.append(_gate_fail("cand004_quality_gate", "symbol mismatch"))
        blockers.append("cand004_quality_gate: symbol mismatch")
        status = "blocked"
    else:
        gates.append(_gate_pass("cand004_quality_gate"))

    if status != "not_evaluated":
        for gate_id in GATE_SEQUENCE[GATE_SEQUENCE.index("cand004_quality_gate") + 1 :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gates=tuple(gates),
            status=status,
            blockers=blockers,
            dry_run_request=None,
            dry_run_request_fingerprint=None,
            recording=recording,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )

    # Gate 3: cand005_shadow_live_comparison
    if shadow_comparison.get("artifact_type") != _SHADOW_LIVE_COMPARISON_ARTIFACT_TYPE:
        gates.append(_gate_fail("cand005_shadow_live_comparison", "artifact_type mismatch"))
        blockers.append("cand005_shadow_live_comparison: artifact_type mismatch")
        status = "shadow_divergence_blocked"
    elif shadow_comparison.get("schema_version") != _SHADOW_LIVE_COMPARISON_SCHEMA_VERSION:
        gates.append(_gate_fail("cand005_shadow_live_comparison", "schema_version mismatch"))
        blockers.append("cand005_shadow_live_comparison: schema_version mismatch")
        status = "shadow_divergence_blocked"
    elif shadow_comparison.get("status") != "matched":
        gates.append(
            _gate_fail(
                "cand005_shadow_live_comparison",
                f"status is '{shadow_comparison.get('status')}', required 'matched'",
            )
        )
        blockers.append(
            f"cand005_shadow_live_comparison: status is '{shadow_comparison.get('status')}'"
        )
        status = "shadow_divergence_blocked"
    elif shadow_comparison.get("blockers"):
        gates.append(
            _gate_fail("cand005_shadow_live_comparison", "shadow_comparison blockers non-empty")
        )
        blockers.append("cand005_shadow_live_comparison: blockers non-empty")
        status = "shadow_divergence_blocked"
    elif shadow_comparison.get("run_id") != order_intent.get("run_id"):
        gates.append(_gate_fail("cand005_shadow_live_comparison", "run_id mismatch"))
        blockers.append("cand005_shadow_live_comparison: run_id mismatch")
        status = "shadow_divergence_blocked"
    elif shadow_comparison.get("symbol") != order_intent.get("symbol"):
        gates.append(_gate_fail("cand005_shadow_live_comparison", "symbol mismatch"))
        blockers.append("cand005_shadow_live_comparison: symbol mismatch")
        status = "shadow_divergence_blocked"
    else:
        gates.append(_gate_pass("cand005_shadow_live_comparison"))

    if status != "not_evaluated":
        for gate_id in GATE_SEQUENCE[GATE_SEQUENCE.index("cand005_shadow_live_comparison") + 1 :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gates=tuple(gates),
            status=status,
            blockers=blockers,
            dry_run_request=None,
            dry_run_request_fingerprint=None,
            recording=recording,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )

    # Gate 4: kill_switch_fixture
    if kill_switch.get("state") != "inactive":
        gates.append(
            _gate_fail(
                "kill_switch_fixture",
                f"kill switch state is '{kill_switch.get('state')}'",
            )
        )
        blockers.append(f"kill_switch_fixture: state is '{kill_switch.get('state')}'")
        status = "kill_switch_blocked"
    elif not _timestamp_not_before(kill_switch.get("expires_at", ""), as_of):
        gates.append(_gate_fail("kill_switch_fixture", "kill switch fixture expired"))
        blockers.append("kill_switch_fixture: expired")
        status = "kill_switch_blocked"
    else:
        gates.append(_gate_pass("kill_switch_fixture"))

    if status != "not_evaluated":
        for gate_id in GATE_SEQUENCE[GATE_SEQUENCE.index("kill_switch_fixture") + 1 :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gates=tuple(gates),
            status=status,
            blockers=blockers,
            dry_run_request=None,
            dry_run_request_fingerprint=None,
            recording=recording,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )

    # Gate 5: risk_envelope_fixture
    risk_fingerprint = fingerprints["risk_envelope"]
    intent_fingerprint = fingerprints["order_intent"]
    risk_failures: list[str] = []
    if risk_envelope.get("intent_fingerprint") != intent_fingerprint:
        risk_failures.append("intent_fingerprint mismatch")
    if risk_envelope.get("decision") != "allowed":
        risk_failures.append(f"decision is '{risk_envelope.get('decision')}'")
    if risk_envelope.get("violations"):
        risk_failures.append("violations list is non-empty")
    checks = risk_envelope.get("checks", [])
    if not checks:
        risk_failures.append("checks list is empty")
    elif any(not check.get("passed") for check in checks):
        risk_failures.append("one or more risk checks failed")
    if not _timestamp_not_before(risk_envelope.get("expires_at", ""), as_of):
        risk_failures.append("risk envelope expired")

    if risk_failures:
        reason = "; ".join(risk_failures)
        gates.append(_gate_fail("risk_envelope_fixture", reason))
        blockers.append(f"risk_envelope_fixture: {reason}")
        status = "risk_blocked"
    else:
        gates.append(_gate_pass("risk_envelope_fixture"))

    if status != "not_evaluated":
        for gate_id in GATE_SEQUENCE[GATE_SEQUENCE.index("risk_envelope_fixture") + 1 :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gates=tuple(gates),
            status=status,
            blockers=blockers,
            dry_run_request=None,
            dry_run_request_fingerprint=None,
            recording=recording,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )

    # Gate 6: approval_fixture
    approval_failures: list[str] = []
    if approval.get("decision") != "approved":
        approval_failures.append(f"decision is '{approval.get('decision')}'")
    if approval.get("intent_fingerprint") != intent_fingerprint:
        approval_failures.append("intent_fingerprint mismatch")
    if approval.get("risk_envelope_fingerprint") != risk_fingerprint:
        approval_failures.append("risk_envelope_fingerprint mismatch")
    if not _timestamp_not_before(approval.get("expires_at", ""), as_of):
        approval_failures.append("approval fixture expired")

    if approval_failures:
        reason = "; ".join(approval_failures)
        gates.append(_gate_fail("approval_fixture", reason))
        blockers.append(f"approval_fixture: {reason}")
        status = "approval_required"
    else:
        gates.append(_gate_pass("approval_fixture"))

    if status != "not_evaluated":
        for gate_id in GATE_SEQUENCE[GATE_SEQUENCE.index("approval_fixture") + 1 :]:
            gates.append(_gate_not_run(gate_id))
        return _build_report(
            inputs=inputs,
            as_of=as_of,
            gates=tuple(gates),
            status=status,
            blockers=blockers,
            dry_run_request=None,
            dry_run_request_fingerprint=None,
            recording=recording,
            normalized=normalized,
            fingerprints=fingerprints,
            input_digest=input_digest,
            evaluation_id=evaluation_id,
        )

    # Gate 7: dry_run_conversion
    dry_run_request = _build_dry_run_request(
        evaluation_id=evaluation_id,
        as_of=as_of,
        order_intent=order_intent,
        risk_envelope=risk_envelope,
        fingerprints=fingerprints,
    )
    dry_run_request_fingerprint = fingerprint_json(dry_run_request.to_dict())
    gates.append(_gate_pass("dry_run_conversion"))
    status = "dry_run_ready"

    # Gate 8: atomic_artifact_recording is handled by the writer. The report
    # returned here represents the state before writing.
    gates.append(_gate_not_run("atomic_artifact_recording", "writer not invoked"))

    return _build_report(
        inputs=inputs,
        as_of=as_of,
        gates=tuple(gates),
        status=status,
        blockers=blockers,
        dry_run_request=dry_run_request,
        dry_run_request_fingerprint=dry_run_request_fingerprint,
        recording=recording,
        normalized=normalized,
        fingerprints=fingerprints,
        input_digest=input_digest,
        evaluation_id=evaluation_id,
    )


def _build_report(
    inputs: SubmitConformanceInputs,
    as_of: str,
    gates: tuple[GateResult, ...],
    status: str,
    blockers: list[str],
    dry_run_request: DryRunSubmitRequest | None,
    dry_run_request_fingerprint: str | None,
    recording: dict[str, Any],
    normalized: dict[str, Any] | None,
    fingerprints: dict[str, str] | None = None,
    input_digest: str | None = None,
    evaluation_id: str | None = None,
) -> SubmitConformanceReport:
    if normalized is None:
        order_intent = None
        quality_gate = {}
        shadow_comparison = {}
        kill_switch = {}
        risk_envelope = {}
        approval = {}
    else:
        order_intent = normalized["order_intent"]
        quality_gate = normalized["quality_gate"]
        shadow_comparison = normalized["shadow_comparison"]
        kill_switch = normalized["kill_switch"]
        risk_envelope = normalized["risk_envelope"]
        approval = normalized["approval"]

    if fingerprints is None:
        fingerprints = {}
    if input_digest is None:
        input_digest = ""
    if evaluation_id is None:
        evaluation_id = ""

    exit_code = 0 if status == "dry_run_recorded" else 2

    input_artifacts = {
        "quality_gate": _redact_path(inputs.quality_gate_path),
        "shadow_comparison": _redact_path(inputs.shadow_comparison_path),
        "order_intent": _redact_path(inputs.order_intent_path),
        "kill_switch": _redact_path(inputs.kill_switch_path),
        "risk_envelope": _redact_path(inputs.risk_envelope_path),
        "approval": _redact_path(inputs.approval_path),
    }

    return SubmitConformanceReport(
        artifact_type="gated_submit_conformance",
        schema_version="gated-submit-conformance.v1",
        candidate="CAND-006",
        mode="simulated_only",
        evaluation_id=evaluation_id,
        as_of=as_of,
        input_digest=input_digest,
        status=status,
        exit_code=exit_code,
        gate_sequence=GATE_SEQUENCE,
        gates=gates,
        input_artifacts=input_artifacts,
        input_fingerprints=fingerprints,
        run_id=order_intent.get("run_id") if order_intent else None,
        intent_id=order_intent.get("intent_id") if order_intent else None,
        symbol=order_intent.get("symbol") if order_intent else None,
        quality_gate_summary={
            "artifact_type": quality_gate.get("artifact_type"),
            "schema_version": quality_gate.get("schema_version"),
            "mode": quality_gate.get("mode"),
            "quality_state": quality_gate.get("quality_state"),
            "blockers": quality_gate.get("blockers", []),
        },
        shadow_live_summary={
            "artifact_type": shadow_comparison.get("artifact_type"),
            "schema_version": shadow_comparison.get("schema_version"),
            "status": shadow_comparison.get("status"),
            "blockers": shadow_comparison.get("blockers", []),
        },
        kill_switch_summary={
            "state": kill_switch.get("state"),
            "expires_at": kill_switch.get("expires_at"),
        },
        risk_summary={
            "decision": risk_envelope.get("decision"),
            "evaluated_price": risk_envelope.get("evaluated_price"),
            "evaluated_notional": risk_envelope.get("evaluated_notional"),
            "checks_passed": (
                all(check.get("passed") for check in risk_envelope.get("checks", []))
                if risk_envelope.get("checks")
                else False
            ),
            "expires_at": risk_envelope.get("expires_at"),
        },
        approval_summary={
            "decision": approval.get("decision"),
            "actor_label": approval.get("actor_label"),
            "expires_at": approval.get("expires_at"),
        },
        dry_run_request=dry_run_request,
        dry_run_request_fingerprint=dry_run_request_fingerprint,
        safety_assertions=_safety_assertions(),
        recording=recording,
        blockers=blockers,
        disclaimer=(
            "Simulated-only conformance rehearsal. Not live readiness and not permission to submit orders."
        ),
    )


def _render_markdown(report: SubmitConformanceReport) -> str:
    lines: list[str] = []
    lines.append("# Gated Submit Conformance Rehearsal Report")
    lines.append("")
    lines.append("> **Status:** simulated-only conformance rehearsal. This report does **not** "
                 "authorize live trading, live submit, or real order submission.")
    lines.append("")
    lines.append(f"- **evaluation_id:** `{report.evaluation_id}`")
    lines.append(f"- **as_of:** `{report.as_of}`")
    lines.append(f"- **final_status:** `{report.status}`")
    lines.append(f"- **exit_code:** `{report.exit_code}`")
    lines.append("")
    lines.append("## Gate table")
    lines.append("")
    lines.append("| Gate | Status | Reason |")
    lines.append("|---|---|---|")
    for gate in report.gates:
        reason = gate.reason or "-"
        lines.append(f"| `{gate.gate_id}` | `{gate.status}` | {reason} |")
    lines.append("")
    lines.append("## Input artifacts")
    lines.append("")
    for label, name in report.input_artifacts.items():
        fp = report.input_fingerprints.get(label, "")
        lines.append(f"- **{label}:** `{name or '-'}` ({fp})")
    lines.append(f"- **input_digest:** `{report.input_digest}`")
    lines.append("")
    if report.dry_run_request is not None:
        lines.append("## Dry-run submit request summary")
        lines.append("")
        req = report.dry_run_request
        lines.append(f"- **request_id:** `{req.request_id}`")
        lines.append(f"- **intent_id:** `{req.intent_id}`")
        lines.append(f"- **symbol:** `{req.symbol}`")
        lines.append(f"- **side:** `{req.side}`")
        lines.append(f"- **quantity:** `{req.quantity}`")
        lines.append(f"- **order_type:** `{req.order_type}`")
        if req.limit_price:
            lines.append(f"- **limit_price:** `{req.limit_price}`")
        lines.append(f"- **estimated_notional:** `{req.estimated_notional}`")
        lines.append(f"- **transmission.allowed:** `{req.transmission.get('allowed')}`")
        lines.append(f"- **transmission.reason:** {req.transmission.get('reason')}")
        lines.append("")
        lines.append(f"**dry_run_request_fingerprint:** `{report.dry_run_request_fingerprint}`")
        lines.append("")
    if report.blockers:
        lines.append("## Blockers")
        lines.append("")
        for blocker in report.blockers:
            lines.append(f"- {blocker}")
        lines.append("")
    lines.append("## Safety assertions")
    lines.append("")
    for assertion, value in report.safety_assertions.items():
        lines.append(f"- **{assertion}:** `{value}`")
    lines.append("")
    lines.append("## Disclaimer")
    lines.append("")
    lines.append(report.disclaimer)
    lines.append("")
    return "\n".join(lines)


def _atomic_write_text(output_dir: Path, filename: str, content: str) -> Path:
    """Write ``content`` to ``output_dir / filename`` atomically via os.replace."""
    fd, temp_path = tempfile.mkstemp(dir=output_dir, suffix=f".{filename}.tmp")
    temp_file = Path(temp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        dest = output_dir / filename
        os.replace(temp_file, dest)
        return dest
    except Exception:
        try:
            temp_file.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def write_gated_submit_conformance_artifacts(
    report: SubmitConformanceReport,
    output_dir: str | Path,
) -> SubmitConformanceReport:
    """Atomically write the JSON and Markdown artifacts for a report.

    Returns an updated report with status ``dry_run_recorded`` on success. If the
    JSON write fails, the report status remains ``dry_run_ready`` and a recording
    blocker is appended.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Markdown is informational; write it first.
    markdown = _render_markdown(report)
    try:
        _atomic_write_text(out, _MARKDOWN_ARTIFACT_NAME, markdown)
    except Exception as exc:
        report.blockers.append(f"markdown write failed: {exc}")
        return report

    json_text = json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=True)
    try:
        _atomic_write_text(out, _JSON_ARTIFACT_NAME, json_text + "\n")
    except Exception as exc:
        report.blockers.append(f"json write failed: {exc}")
        # JSON is the authoritative commit marker. Do not claim recorded.
        return report

    object.__setattr__(report, "recording", {"json_written": True, "markdown_written": True})
    # Only promote a rehearsal that actually passed every gate to recorded.
    if report.status == "dry_run_ready":
        object.__setattr__(report, "status", "dry_run_recorded")
        object.__setattr__(report, "exit_code", 0)
    return report
