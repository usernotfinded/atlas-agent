# CAND-008 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement CAND-008 as a local, deterministic, evidence-only operator approval gate that consumes CAND-004/CAND-005/CAND-006/CAND-007 artifacts and CAND-008-owned static fixtures, then records an operator-approval-gate artifact without enabling execution.

**Architecture:** Mirror the CAND-006/CAND-007 configless CLI pattern: a pure Python engine module for validation/gating, a thin CLI wrapper, an exact two-token bootstrap route, and a static contract checker. All upstream artifacts are validated by projection; CAND-008-owned fixtures use closed schemas; no runtime trading objects, credentials, or network calls are ever loaded or instantiated.

**Tech Stack:** Python 3.11, `dataclasses`, `argparse`, `pathlib`, `hashlib`, `json`, `datetime`, `pytest`.

---

## 1. Objective

Implement CAND-008 as a local, deterministic, evidence-only operator approval gate. It consumes the upstream artifacts produced by CAND-004, CAND-005, CAND-006, and CAND-007, plus CAND-008-owned static local fixtures (operator identity, approval policy, kill-switch observation, operator acknowledgment) and a shared audit policy fixture.

The command records an `operator-approval-gate.json` artifact and an informational `operator-approval-gate-report.md` rendering. It does **not**:

- authorize live trading,
- approve real trades,
- authorize live order submission,
- instantiate `Order`, `OrderRouter`, `RiskManager`, `ApprovalManager`, or the runtime kill switch,
- load credentials or endpoints,
- mutate any runtime state or approval queue,
- create pending orders.

The only successful final status is `operator_gate_recorded`, and it is an evidence-recording status only.

---

## 2. Files to add

Create the following new files:

- `src/atlas_agent/agent/operator_approval_gate.py` — engine: validation, gate sequence, artifact synthesis.
- `src/atlas_agent/agent/operator_approval_gate_cli.py` — configless CLI handler.
- `scripts/check_operator_approval_gate_contract.py` — static contract checker.
- `tests/test_operator_approval_gate.py` — engine unit tests.
- `tests/test_operator_approval_gate_cli.py` — CLI tests.
- `tests/test_operator_approval_gate_contract.py` — contract checker tests.
- `tests/test_operator_approval_gate_import_trace.py` — import-boundary tests.
- `docs/operator-approval-gate.md` — user-facing command documentation.

Optional, only if consistent with existing repo patterns:

- `tests/test_operator_approval_gate_e2e.py` — end-to-end smoke test invoking the CLI via subprocess.

---

## 3. Files to update

Modify the following existing files:

- `src/atlas_agent/cli_bootstrap.py` — add exact two-token route `agent operator-approval-gate`.
- `src/atlas_agent/cli.py` — add minimal legacy subparser for `--help` and `--workspace` delegation.
- `scripts/dev_check.sh` — add the new contract checker to the quick check set.
- `scripts/release_check.sh` — add the new contract checker to the release check set.
- `docs/autonomy-roadmap.md` — add CAND-008 as a planning-only operator review stage.
- `docs/bounded-live-autonomy-governance.md` — add CAND-008 to the staged autonomy ladder.
- `docs/runtime-readiness-envelope.md` — add forward reference to CAND-008.
- `docs/releases/v0.6.16-plan.md` — add CAND-008 as a proposed candidate.
- `docs/releases/v0.6.16-candidates.md` — add CAND-008 as a proposed candidate.
- `docs/releases/v0.6.16-candidate-selection.md` — add "Why CAND-008 is eligible" section.
- `docs/releases/v0.6.16-candidates.json` — add CAND-008 candidate object with `status: "proposed"`.
- `CHANGELOG.md` — add CAND-008 planning-only entry under `[Unreleased]`.

Do not update `pyproject.toml`, `setup.py`, `setup.cfg`, or any package version file.

---

## 4. Engine implementation plan

### 4.1 Module skeleton

**File:** `src/atlas_agent/agent/operator_approval_gate.py`

**Step 1:** Add module docstring and imports.

```python
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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
```

**Step 2:** Define constants.

```python
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
```

**Step 3:** Define exception and dataclasses.

```python
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
```

**Step 4:** Add helper functions.

```python
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
```

---

## 5. Upstream projection validation plan

### 5.1 Load and scan upstream artifacts

For each upstream artifact:

1. Call `_load_json_object(path, label)`.
2. Call `_universal_reject_scan(raw, label, include_forbidden_keys=False)`.
3. If findings exist, raise `OperatorApprovalGateValidationError`.
4. Extract only the projected fields defined below.
5. Validate projected fields.

### 5.2 CAND-004 projection validator

**Step:** Add `_validate_quality_gate(data)`.

```python
def _validate_quality_gate(data: dict[str, Any]) -> dict[str, Any]:
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
```

### 5.3 CAND-005 projection validator

**Step:** Add `_validate_shadow_comparison(data)`.

```python
def _validate_shadow_comparison(data: dict[str, Any]) -> dict[str, Any]:
    artifact_type = _require_string(data.get("artifact_type"), "shadow_comparison.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "shadow_comparison.schema_version")
    run_id = _require_string(data.get("run_id"), "shadow_comparison.run_id")
    symbol = _require_string(data.get("symbol"), "shadow_comparison.symbol")
    quality_state = _require_string(data.get("quality_state"), "shadow_comparison.quality_state")
    status = _require_string(data.get("status"), "shadow_comparison.status")
    freshness_assessment = data.get("freshness_assessment")
    blockers = data.get("blockers")

    if artifact_type != _SHADOW_LIVE_COMPARISON_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("shadow_comparison artifact_type mismatch")
    if schema_version != _SHADOW_LIVE_COMPARISON_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("shadow_comparison schema_version mismatch")
    if not isinstance(freshness_assessment, dict):
        raise OperatorApprovalGateValidationError("shadow_comparison freshness_assessment must be an object")
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
```

### 5.4 CAND-006 projection validator

**Step:** Add `_validate_submit_conformance(data, cand008_as_of)`.

```python
def _validate_submit_conformance(data: dict[str, Any], cand008_as_of: str) -> dict[str, Any]:
    artifact_type = _require_string(data.get("artifact_type"), "submit_conformance.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "submit_conformance.schema_version")
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
        raise OperatorApprovalGateValidationError("submit_conformance safety_assertions must be an object")
    if not all(isinstance(v, bool) and v for v in safety_assertions.values()):
        raise OperatorApprovalGateValidationError("all submit_conformance safety_assertions must be true")
    if not isinstance(dry_run_request, dict):
        raise OperatorApprovalGateValidationError("submit_conformance dry_run_request must be an object")
    transmission = dry_run_request.get("transmission")
    if not isinstance(transmission, dict):
        raise OperatorApprovalGateValidationError("submit_conformance dry_run_request.transmission must be an object")
    if not isinstance(transmission.get("allowed"), bool):
        raise OperatorApprovalGateValidationError("submit_conformance dry_run_request.transmission.allowed must be a boolean")
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
        raise OperatorApprovalGateValidationError("submit_conformance as_of is later than CAND-008 as_of")
    if cand008_dt is not None:
        age_hours = (cand008_dt - as_of_dt).total_seconds() / 3600.0
        if age_hours > _MAX_EVIDENCE_AGE_HOURS:
            raise OperatorApprovalGateValidationError("submit_conformance evidence is older than 24 hours")

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
```

### 5.5 CAND-007 projection validator

**Step:** Add `_validate_readiness_envelope(data, cand008_as_of)`.

```python
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


def _validate_readiness_envelope(data: dict[str, Any], cand008_as_of: str) -> dict[str, Any]:
    artifact_type = _require_string(data.get("artifact_type"), "readiness_envelope.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "readiness_envelope.schema_version")
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
        raise OperatorApprovalGateValidationError("readiness_envelope artifact_type mismatch")
    if schema_version != _RUNTIME_READINESS_ENVELOPE_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("readiness_envelope schema_version mismatch")
    if candidate != "CAND-007":
        raise OperatorApprovalGateValidationError("readiness_envelope candidate must be CAND-007")
    if mode != "simulated_only":
        raise OperatorApprovalGateValidationError("readiness_envelope mode must be 'simulated_only'")
    if not isinstance(exit_code, int) or exit_code != 0:
        raise OperatorApprovalGateValidationError("readiness_envelope exit_code must be 0")
    if not isinstance(blockers, list):
        raise OperatorApprovalGateValidationError("readiness_envelope blockers must be a list")
    if not isinstance(envelope_assertions, dict):
        raise OperatorApprovalGateValidationError("readiness_envelope envelope_assertions must be an object")

    missing_assertions = _CAND007_REQUIRED_ASSERTIONS - set(envelope_assertions)
    if missing_assertions:
        raise OperatorApprovalGateValidationError(
            f"readiness_envelope missing required envelope_assertions: {sorted(missing_assertions)}"
        )
    if not all(isinstance(envelope_assertions[k], bool) and envelope_assertions[k] for k in _CAND007_REQUIRED_ASSERTIONS):
        raise OperatorApprovalGateValidationError("all required readiness_envelope envelope_assertions must be true")

    as_of_dt = _parse_or_fail(as_of, "readiness_envelope.as_of")
    cand008_dt = _parse_iso_timestamp(cand008_as_of)
    if cand008_dt is not None and as_of_dt > cand008_dt:
        raise OperatorApprovalGateValidationError("readiness_envelope as_of is later than CAND-008 as_of")
    if cand008_dt is not None:
        age_hours = (cand008_dt - as_of_dt).total_seconds() / 3600.0
        if age_hours > _MAX_EVIDENCE_AGE_HOURS:
            raise OperatorApprovalGateValidationError("readiness_envelope evidence is older than 24 hours")

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
```

---

## 6. Fixture validation plan

### 6.1 Operator identity fixture

**Step:** Add `_validate_operator_identity(data, as_of)`.

```python
def _validate_operator_identity(data: dict[str, Any], as_of: str) -> dict[str, Any]:
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

    artifact_type = _require_string(data.get("artifact_type"), "operator_identity.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "operator_identity.schema_version")
    if artifact_type != _OPERATOR_IDENTITY_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("operator_identity artifact_type mismatch")
    if schema_version != _OPERATOR_IDENTITY_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("operator_identity schema_version mismatch")

    operator_id = _require_string(data.get("operator_id"), "operator_identity.operator_id")
    _require_nonempty_bounded_id(operator_id, "operator_identity.operator_id")
    operator_role = _require_string(data.get("operator_role"), "operator_identity.operator_role")
    _require_nonempty_bounded_id(operator_role, "operator_identity.operator_role")
    operator_attestation_scope = _require_string(
        data.get("operator_attestation_scope"), "operator_identity.operator_attestation_scope"
    )
    if operator_attestation_scope != "evidence_only":
        raise OperatorApprovalGateValidationError("operator_identity operator_attestation_scope must be 'evidence_only'")

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
        raise OperatorApprovalGateValidationError("operator_identity expires_at must be later than as_of")

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        "operator_id": operator_id,
        "operator_role": operator_role,
        "operator_attestation_scope": operator_attestation_scope,
        "created_at": _format_utc_timestamp(created_at),
        "expires_at": _format_utc_timestamp(expires_at),
    }
```

### 6.2 Approval policy fixture

**Step:** Add `_validate_approval_policy(data, as_of)`.

```python
def _validate_approval_policy(data: dict[str, Any], as_of: str) -> dict[str, Any]:
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

    artifact_type = _require_string(data.get("artifact_type"), "approval_policy.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "approval_policy.schema_version")
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
            raise OperatorApprovalGateValidationError(f"approval_policy {field_name} must be a boolean")

    approval_scope = _require_string(data.get("approval_scope"), "approval_policy.approval_scope")
    if approval_scope != "evidence_only":
        raise OperatorApprovalGateValidationError("approval_policy approval_scope must be 'evidence_only'")

    max_review_age_seconds = data.get("max_review_age_seconds")
    if not isinstance(max_review_age_seconds, int) or isinstance(max_review_age_seconds, bool):
        raise OperatorApprovalGateValidationError("approval_policy max_review_age_seconds must be an integer")
    if max_review_age_seconds <= 0:
        raise OperatorApprovalGateValidationError("approval_policy max_review_age_seconds must be positive")

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "approval_policy.expires_at"),
        "approval_policy.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise OperatorApprovalGateValidationError("approval_policy expires_at must be later than as_of")

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
```

### 6.3 Kill-switch observation fixture

**Step:** Add `_validate_kill_switch_observation(data, as_of)`.

```python
def _validate_kill_switch_observation(data: dict[str, Any], as_of: str) -> dict[str, Any]:
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

    artifact_type = _require_string(data.get("artifact_type"), "kill_switch_observation.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "kill_switch_observation.schema_version")
    if artifact_type != _KILL_SWITCH_OBSERVATION_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("kill_switch_observation artifact_type mismatch")
    if schema_version != _KILL_SWITCH_OBSERVATION_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("kill_switch_observation schema_version mismatch")

    if not isinstance(data.get("kill_switch_required"), bool):
        raise OperatorApprovalGateValidationError("kill_switch_observation kill_switch_required must be a boolean")

    observed_state = _require_string(data.get("observed_state"), "kill_switch_observation.observed_state")
    if observed_state not in {"blocked", "inactive", "unknown"}:
        raise OperatorApprovalGateValidationError("kill_switch_observation observed_state invalid")

    observed_at = _parse_or_fail(
        _require_string(data.get("observed_at"), "kill_switch_observation.observed_at"),
        "kill_switch_observation.observed_at",
    )

    observation_source = _require_string(data.get("observation_source"), "kill_switch_observation.observation_source")
    if observation_source != "local_fixture":
        raise OperatorApprovalGateValidationError("kill_switch_observation observation_source must be 'local_fixture'")

    for field_name in ("override_attempted", "override_allowed"):
        if not isinstance(data.get(field_name), bool):
            raise OperatorApprovalGateValidationError(f"kill_switch_observation {field_name} must be a boolean")

    for field_name in ("default_on_missing", "default_on_unknown"):
        value = _require_string(data.get(field_name), f"kill_switch_observation.{field_name}")
        if value != "blocked":
            raise OperatorApprovalGateValidationError(f"kill_switch_observation {field_name} must be 'blocked'")

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "kill_switch_observation.expires_at"),
        "kill_switch_observation.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise OperatorApprovalGateValidationError("kill_switch_observation expires_at must be later than as_of")

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
```

### 6.4 Operator acknowledgment fixture

**Step:** Add `_validate_operator_acknowledgment(data, as_of)`.

```python
def _validate_operator_acknowledgment(data: dict[str, Any], as_of: str) -> dict[str, Any]:
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

    artifact_type = _require_string(data.get("artifact_type"), "operator_acknowledgment.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "operator_acknowledgment.schema_version")
    if artifact_type != _OPERATOR_ACKNOWLEDGMENT_ARTIFACT_TYPE:
        raise OperatorApprovalGateValidationError("operator_acknowledgment artifact_type mismatch")
    if schema_version != _OPERATOR_ACKNOWLEDGMENT_SCHEMA_VERSION:
        raise OperatorApprovalGateValidationError("operator_acknowledgment schema_version mismatch")

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
            raise OperatorApprovalGateValidationError(f"operator_acknowledgment {field_name} must be true")

    acknowledgment_text_digest = _require_string(
        data.get("acknowledgment_text_digest"), "operator_acknowledgment.acknowledgment_text_digest"
    )
    if acknowledgment_text_digest != _compute_acknowledgment_digest():
        raise OperatorApprovalGateValidationError("operator_acknowledgment digest mismatch")

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
        raise OperatorApprovalGateValidationError("operator_acknowledgment expires_at must be later than as_of")

    return {
        "artifact_type": artifact_type,
        "schema_version": schema_version,
        **{field_name: True for field_name in acknowledgment_fields},
        "acknowledgment_text_digest": acknowledgment_text_digest,
        "acknowledged_at": _format_utc_timestamp(acknowledged_at),
        "expires_at": _format_utc_timestamp(expires_at),
    }
```

### 6.5 Audit policy fixture

**Step:** Add `_validate_audit_policy(data, as_of)`.

```python
def _validate_audit_policy(data: dict[str, Any], as_of: str) -> dict[str, Any]:
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

    artifact_type = _require_string(data.get("artifact_type"), "audit_policy.artifact_type")
    schema_version = _require_string(data.get("schema_version"), "audit_policy.schema_version")
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
            raise OperatorApprovalGateValidationError(f"audit_policy {field_name} must be a boolean")

    expires_at = _parse_or_fail(
        _require_string(data.get("expires_at"), "audit_policy.expires_at"),
        "audit_policy.expires_at",
    )
    as_of_dt = _parse_iso_timestamp(as_of)
    if as_of_dt is not None and expires_at <= as_of_dt:
        raise OperatorApprovalGateValidationError("audit_policy expires_at must be later than as_of")

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
```

### 6.6 Universal load-and-scan wrapper

**Step:** Add `_load_and_validate_all(inputs, as_of)`.

```python
def _load_and_validate_all(inputs: OperatorApprovalGateInputs, as_of: str) -> dict[str, Any]:
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
            raise OperatorApprovalGateValidationError("universal rejection: " + "; ".join(findings))

    return {
        "quality_gate": _validate_quality_gate(raw["quality_gate"]),
        "shadow_comparison": _validate_shadow_comparison(raw["shadow_comparison"]),
        "submit_conformance": _validate_submit_conformance(raw["submit_conformance"], as_of),
        "readiness_envelope": _validate_readiness_envelope(raw["readiness_envelope"], as_of),
        "operator_identity": _validate_operator_identity(raw["operator_identity"], as_of),
        "approval_policy": _validate_approval_policy(raw["approval_policy"], as_of),
        "kill_switch_observation": _validate_kill_switch_observation(raw["kill_switch_observation"], as_of),
        "operator_acknowledgment": _validate_operator_acknowledgment(raw["operator_acknowledgment"], as_of),
        "audit_policy": _validate_audit_policy(raw["audit_policy"], as_of),
    }
```

---

## 7. Gate sequence implementation plan

### 7.1 Gate helpers

**Step:** Add gate helper factories.

```python
def _gate_pass(gate_id: str, details: dict[str, Any] | None = None) -> GateResult:
    return GateResult(gate_id=gate_id, status="pass", reason="", details=details or {})


def _gate_fail(gate_id: str, reason: str, details: dict[str, Any] | None = None) -> GateResult:
    return GateResult(gate_id=gate_id, status="fail", reason=reason, details=details or {})


def _gate_not_run(gate_id: str, reason: str = "prior gate failed") -> GateResult:
    return GateResult(gate_id=gate_id, status="not_run", reason=reason)
```

### 7.2 Correlation helper

**Step:** Add `_correlate_evidence(normalized)`.

```python
def _correlate_evidence(normalized: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    run_id = normalized["quality_gate"]["run_id"]
    symbol = normalized["quality_gate"]["symbol"]
    for label in ("shadow_comparison", "submit_conformance", "readiness_envelope"):
        if normalized[label]["run_id"] != run_id:
            blockers.append(f"run_id mismatch between quality_gate and {label}")
        if normalized[label]["symbol"] != symbol:
            blockers.append(f"symbol mismatch between quality_gate and {label}")
    return blockers
```

### 7.3 Main evaluator

**Step:** Add `build_operator_approval_gate_report(inputs)`.

Pseudo-code structure (implement exactly):

1. Parse `as_of`.
2. Initialize `gates = []`, `blockers = []`, `status = "not_evaluated"`.
3. Gate 1 `schema_preflight`: call `_load_and_validate_all`. On exception, fail gate, set downstream `not_run`, return report with `status = "not_evaluated"`.
4. Compute fingerprints, input_digest, evaluation_id.
5. Gate 2 `cand004_projection_gate`: check `mode == "paper"`, `quality_state == "eligible_for_shadow_live_quality_review"`, `blockers == []`. On failure, status `upstream_evidence_blocked`.
6. Gate 3 `cand005_projection_gate`: check `status == "matched"`, `blockers == []`. On failure, status `upstream_evidence_blocked`.
7. Gate 4 `cand006_projection_gate`: check `status == "dry_run_recorded"`, `blockers == []`, age ≤ 24h, all safety assertions true, `transmission.allowed == False`, `broker_adapter == None`, `provider == None`. On failure, status `upstream_evidence_blocked`.
8. Gate 5 `cand007_projection_gate`: check `status == "readiness_envelope_recorded"`, `mode == "simulated_only"`, `candidate == "CAND-007"`, `exit_code == 0`, `blockers == []`, age ≤ 24h, all required envelope assertions true. On failure, status `runtime_envelope_blocked`.
9. Gate 6 `cross_artifact_correlation_gate`: run `_correlate_evidence`. On failure, status `blocked`.
10. Gate 7 `operator_identity_gate`: fixture is valid by construction after preflight; check `operator_attestation_scope == "evidence_only"` and expiry. On failure, status `operator_identity_blocked`.
11. Gate 8 `approval_policy_gate`: check `live_trading_approval == False`, `live_submit_approval == False`, `unattended_operation_allowed == False`, `approval_scope == "evidence_only"`. On failure, status `approval_policy_blocked`.
12. Gate 9 `kill_switch_observation_gate`: check `observed_state == "blocked"`, `override_attempted == False`, `override_allowed == False`, `default_on_missing == "blocked"`, `default_on_unknown == "blocked"`. On failure, status `kill_switch_observation_blocked`.
13. Gate 10 `operator_acknowledgment_gate`: all acknowledgments true and digest valid by construction; check expiry. On failure, status `operator_acknowledgment_blocked`.
14. Gate 11 `audit_policy_gate`: check `audit_required`, `append_only_required`, `hash_chain_required`, `local_artifact_recording_required` are true; `live_audit_chain_claimed` is false. On failure, status `audit_policy_blocked`.
15. Gate 12 `approval_gate_synthesis`: synthesize report dict in memory. If any exception, status `blocked`. Otherwise status `operator_gate_synthesized`.
16. Gate 13 `artifact_recording_gate`: handled by writer; in the engine, append `_gate_not_run("artifact_recording_gate", "writer not invoked")`.

Each failure path must stop evaluation and mark all remaining gates `not_run`.

---

## 8. Status model plan

Implement exactly these statuses as string constants used in the engine, CLI, tests, and docs:

- `not_evaluated`
- `blocked`
- `upstream_evidence_blocked`
- `runtime_envelope_blocked`
- `operator_identity_blocked`
- `approval_policy_blocked`
- `kill_switch_observation_blocked`
- `operator_acknowledgment_blocked`
- `audit_policy_blocked`
- `operator_gate_synthesized`
- `operator_gate_recorded`

Forbidden statuses (raise contract-checker errors if present):

- `approved_for_live`
- `live_ready`
- `safe_to_trade`
- `ready_to_submit`
- `operator_approved_trade`
- `approved_to_trade`
- `ready_for_live`
- any equivalent wording discovered during review

Rules:

- `operator_gate_synthesized` is internal only and must not exit code `0`.
- Only `operator_gate_recorded` may produce exit code `0`.

---

## 9. Artifact output plan

### 9.1 JSON artifact

**Step:** Add `write_operator_approval_gate_artifacts(report, output_dir)`.

```python
def write_operator_approval_gate_artifacts(
    report: OperatorApprovalGateReport,
    output_dir: Path,
) -> OperatorApprovalGateReport:
    """Write the JSON artifact and Markdown report to output_dir.

    Returns a new report with status operator_gate_recorded if both writes
    succeed. Any write failure leaves the previous status unchanged.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / _JSON_ARTIFACT_NAME
    md_path = output_dir / _MARKDOWN_ARTIFACT_NAME

    try:
        json_path.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=True),
            encoding="utf-8",
        )
        md_path.write_text(
            _render_markdown_report(report),
            encoding="utf-8",
        )
    except Exception as exc:
        raise OperatorApprovalGateValidationError(f"artifact recording failed: {exc}") from None

    return replace(
        report,
        status="operator_gate_recorded",
        exit_code=0,
        recording={"json_written": True, "markdown_written": True},
        gates=tuple(
            GateResult(
                gate_id="artifact_recording_gate",
                status="pass",
                reason="artifacts recorded",
            )
            if g.gate_id == "artifact_recording_gate"
            else g
            for g in report.gates
        ),
    )
```

### 9.2 Markdown renderer

**Step:** Add `_render_markdown_report(report)`.

Render sections:

1. `# Operator Approval Gate Report (CAND-008)`
2. Metadata table: status, evaluation_id, as_of, symbol, run_id.
3. Gate table with pass/fail/not_run and reason.
4. Upstream evidence summaries (CAND-004 through CAND-007).
5. Operator summary.
6. Approval policy summary.
7. Kill-switch observation summary.
8. Acknowledgment summary.
9. Audit policy summary.
10. Approval gate assertions table.
11. Blockers list if any.
12. Disclaimer with exact evidence-only text.

Do not include raw upstream artifacts, credentials, account IDs, endpoints, broker/provider payloads, legal identity docs, phone numbers, unredacted emails, absolute paths, env vars, or stack traces.

### 9.3 Report builder

**Step:** Add `_build_report(...)` helper to construct `OperatorApprovalGateReport` from intermediate state.

Ensure all summaries are derived from normalized fixtures and never include raw upstream bodies.

---

## 10. CLI implementation plan

### 10.1 CLI module

**File:** `src/atlas_agent/agent/operator_approval_gate_cli.py`

**Step 1:** Add imports and description.

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from atlas_agent.agent.operator_approval_gate import (
    OperatorApprovalGateInputs,
    build_operator_approval_gate_report,
    write_operator_approval_gate_artifacts,
)

CLI_DESCRIPTION = """\
Operator approval gate evaluation (CAND-008) — evidence-only, simulated-only.

This command consumes CAND-004 trading-quality evidence, CAND-005 shadow-live
comparison evidence, CAND-006 gated submit conformance evidence, CAND-007 runtime
readiness envelope evidence, and CAND-008-owned static local fixtures. It
evaluates them in strict fail-closed order and records an operator approval gate
artifact if every gate passes.

This command does not submit orders, does not call broker or provider APIs, does
not load credentials, does not create real or pending orders, does not import
Order/OrderRouter/RiskManager/ApprovalManager/runtime kill switch, and does not
claim live readiness, trading safety, or permission to submit orders.
"""

_UNSAFE_FLAGS = {
    "--live",
    "--submit",
    "--broker",
    "--provider",
    "--api-key",
    "--credentials",
    "--endpoint",
    "--account",
    "--account-id",
    "--client-order-id",
    "--place-order",
    "--order-router",
    "--risk-manager",
    "--mode",
    "--kill-switch-override",
    "--approve-live",
    "--approve-submit",
    "--trade",
    "--execute",
}
```

**Step 2:** Add parser builder.

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas agent operator-approval-gate",
        description=CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--quality-gate", required=True)
    parser.add_argument("--shadow-comparison", required=True)
    parser.add_argument("--submit-conformance", required=True)
    parser.add_argument("--readiness-envelope", required=True)
    parser.add_argument("--operator-identity", required=True)
    parser.add_argument("--approval-policy", required=True)
    parser.add_argument("--kill-switch-observation", required=True)
    parser.add_argument("--operator-acknowledgment", required=True)
    parser.add_argument("--audit-policy", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--json", action="store_true")
    return parser
```

**Step 3:** Add unsafe-flag rejection.

```python
def _reject_unsafe_flags(argv: list[str] | None) -> int:
    args = argv if argv is not None else []
    for token in args:
        name = token.split("=", 1)[0]
        if name in _UNSAFE_FLAGS:
            print(f"error: unsafe flag rejected: {name}", file=sys.stderr)
            return 2
    return 0
```

**Step 4:** Add path aliasing check.

```python
def _resolve_unique_id(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.resolve().stat()
        return (stat.st_dev, stat.st_ino)
    except Exception:
        return None


def _check_path_aliasing(inputs: OperatorApprovalGateInputs, output_dir: Path) -> None:
    output_dir_id = _resolve_unique_id(output_dir)
    input_paths = [
        inputs.quality_gate_path,
        inputs.shadow_comparison_path,
        inputs.submit_conformance_path,
        inputs.readiness_envelope_path,
        inputs.operator_identity_path,
        inputs.approval_policy_path,
        inputs.kill_switch_observation_path,
        inputs.operator_acknowledgment_path,
        inputs.audit_policy_path,
    ]
    for path in input_paths:
        path_id = _resolve_unique_id(path)
        if path_id is not None and path_id == output_dir_id:
            raise OperatorApprovalGateValidationError(
                f"output_dir aliases input path: {path.name}"
            )
```

**Step 5:** Add main.

```python
def main(argv: list[str] | None = None) -> int:
    reject_code = _reject_unsafe_flags(argv)
    if reject_code != 0:
        return reject_code
    parser = build_parser()
    args = parser.parse_args(argv)

    inputs = OperatorApprovalGateInputs(
        quality_gate_path=Path(args.quality_gate),
        shadow_comparison_path=Path(args.shadow_comparison),
        submit_conformance_path=Path(args.submit_conformance),
        readiness_envelope_path=Path(args.readiness_envelope),
        operator_identity_path=Path(args.operator_identity),
        approval_policy_path=Path(args.approval_policy),
        kill_switch_observation_path=Path(args.kill_switch_observation),
        operator_acknowledgment_path=Path(args.operator_acknowledgment),
        audit_policy_path=Path(args.audit_policy),
        output_dir=Path(args.output_dir),
        as_of=args.as_of,
    )

    try:
        _check_path_aliasing(inputs, inputs.output_dir)
        report = build_operator_approval_gate_report(inputs)
        if report.status == "operator_gate_synthesized":
            report = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {"status": "not_evaluated", "error": str(exc), "exit_code": 2},
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("status: not_evaluated")
            print(f"error: {exc}")
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_text_report(report)

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
```

**Step 6:** Add text report printer.

```python
def _print_text_report(report: Any) -> None:
    print(f"status: {report.status}")
    print(f"evaluation_id: {report.evaluation_id}")
    print(f"as_of: {report.as_of}")
    print(f"symbol: {report.symbol or '-'}")
    print(f"run_id: {report.run_id or '-'}")
    print(f"input_digest: {report.input_digest}")
    print(f"approval_gate_digest: {report.approval_gate_digest}")
    print("gates:")
    for gate in report.gates:
        reason = f" ({gate.reason})" if gate.reason else ""
        print(f"  {gate.gate_id}: {gate.status}{reason}")
    if report.blockers:
        print("blockers:")
        for reason in report.blockers:
            print(f"  - {reason}")
    if report.status == "operator_gate_recorded":
        print("artifacts recorded.")
```

---

## 11. Bootstrap integration plan

### 11.1 Configless bootstrap route

**File:** `src/atlas_agent/cli_bootstrap.py`

**Step:** Update the `main` function.

```python
def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "agent":
        if args[1] == "submit-conformance":
            from atlas_agent.agent.gated_submit_conformance_cli import main as route_main
            return route_main(args[2:])
        if args[1] == "readiness-envelope":
            from atlas_agent.agent.runtime_readiness_envelope_cli import main as route_main
            return route_main(args[2:])
        if args[1] == "operator-approval-gate":
            from atlas_agent.agent.operator_approval_gate_cli import main as route_main
            return route_main(args[2:])
    from atlas_agent.cli import main as legacy_main
    return legacy_main(args)
```

Requirements:

- Exact route only (`args[1] == "operator-approval-gate"`).
- No wildcard matching.
- No config load on this path.
- The CLI module itself must not import `atlas_agent.cli`, broker/provider adapters, `RiskManager`, `OrderRouter`, `ApprovalManager`, runtime kill switch, or config modules.

### 11.2 Legacy CLI subparser

**File:** `src/atlas_agent/cli.py`

**Step:** Add a minimal subparser for `operator-approval-gate` that only supports `--help` and `--workspace` delegation.

Pattern (follow existing CAND-006/CAND-007 subparser style):

```python
def _add_operator_approval_gate_subparser(subparsers):
    parser = subparsers.add_parser(
        "operator-approval-gate",
        help="Operator approval gate evaluation (CAND-008) — evidence-only, simulated-only.",
    )
    parser.add_argument("--workspace", help=argparse.SUPPRESS)
    parser.add_argument("--quality-gate", help=argparse.SUPPRESS)
    parser.add_argument("--shadow-comparison", help=argparse.SUPPRESS)
    parser.add_argument("--submit-conformance", help=argparse.SUPPRESS)
    parser.add_argument("--readiness-envelope", help=argparse.SUPPRESS)
    parser.add_argument("--operator-identity", help=argparse.SUPPRESS)
    parser.add_argument("--approval-policy", help=argparse.SUPPRESS)
    parser.add_argument("--kill-switch-observation", help=argparse.SUPPRESS)
    parser.add_argument("--operator-acknowledgment", help=argparse.SUPPRESS)
    parser.add_argument("--audit-policy", help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", help=argparse.SUPPRESS)
    parser.add_argument("--as-of", help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(func=_delegate_operator_approval_gate)


def _delegate_operator_approval_gate(args):
    from atlas_agent.agent.operator_approval_gate_cli import main as route_main
    argv = ["operator-approval-gate"]
    # Reconstruct flags from args, then call route_main.
    # Implementation must not add live/submit/execute paths.
    return route_main(argv[1:])
```

The legacy subparser must not implement any runtime/live execution path. It exists only for `--help` consistency and `--workspace` delegation.

---

## 12. Static checker plan

### 12.1 Checker module

**File:** `scripts/check_operator_approval_gate_contract.py`

**Step 1:** Add shebang and imports.

```python
#!/usr/bin/env python3
"""Static contract checker for CAND-008 operator approval gate implementation."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
```

**Step 2:** Define expected constants and checks.

- Required files exist.
- `GATE_SEQUENCE` constant contains the 13 gates in order.
- `APPROVED_FINAL_STATUSES` constant contains all required statuses.
- Artifact names `operator-approval-gate.json` and `operator-approval-gate-report.md` appear.
- CLI name `operator-approval-gate` appears in `cli_bootstrap.py` and `cli.py`.
- Bootstrap route exact `agent operator-approval-gate` is present.
- Unsafe flag deny list covers all required flags.
- Forbidden imports/calls absent in engine and CLI:
  - `Order`, `OrderRouter`, `RiskManager`, `ApprovalManager`
  - broker adapters, provider adapters
  - runtime kill switch
  - config loading
  - credential/env loading
  - network libraries (`requests`, `httpx`, `urllib`, `websocket`)
- No `live`, `safe_to_trade`, `approved_for_live`, `ready_to_submit`, etc. in source/docs.
- No raw upstream artifact leakage: output JSON/Markdown must not contain upstream artifact names as dictionary keys with raw bodies.
- Disclaimer present in source and docs.
- `operator_gate_synthesized` is not treated as final success.
- CAND-007 projection rules present.
- Kill-switch gate requires blocked state and false overrides.
- Acknowledgment digest only, no literal canonical text in output artifact.
- Stale-doc prevention.

**Step 3:** Return exit code `0` on pass, `1` on failure, print findings.

---

## 13. Test plan

### 13.1 Engine tests

**File:** `tests/test_operator_approval_gate.py`

Implement the following tests using `tmp_path` fixtures and deterministic sample inputs:

1. `test_valid_all_pass_operator_gate` — all gates pass, status `operator_gate_recorded`.
2. `test_missing_cand004_blocks` — file missing.
3. `test_cand004_wrong_quality_state_blocks`.
4. `test_missing_cand005_blocks`.
5. `test_cand005_not_matched_blocks`.
6. `test_missing_cand006_blocks`.
7. `test_cand006_status_not_dry_run_recorded_blocks`.
8. `test_cand006_blockers_non_empty_blocks`.
9. `test_missing_cand007_blocks`.
10. `test_cand007_status_not_readiness_envelope_recorded_blocks`.
11. `test_cand007_blockers_non_empty_blocks`.
12. `test_cand007_mode_not_simulated_only_blocks`.
13. `test_cand007_candidate_not_cand007_blocks`.
14. `test_cand007_safety_assertion_false_blocks`.
15. `test_cand007_operator_policy_fail_closed_false_blocks`.
16. `test_cand007_all_upstream_statuses_accepted_false_blocks`.
17. `test_cand007_cand006_transmission_blocked_false_blocks`.
18. `test_run_id_mismatch_blocks`.
19. `test_symbol_mismatch_blocks`.
20. `test_missing_operator_identity_blocks`.
21. `test_expired_operator_identity_blocks`.
22. `test_operator_identity_unknown_field_blocks`.
23. `test_approval_policy_live_trading_approval_true_blocks`.
24. `test_approval_policy_live_submit_approval_true_blocks`.
25. `test_approval_policy_unattended_allowed_blocks`.
26. `test_approval_policy_unknown_field_blocks`.
27. `test_kill_switch_observation_unknown_blocks`.
28. `test_kill_switch_observation_inactive_blocks`.
29. `test_kill_switch_override_attempted_blocks`.
30. `test_kill_switch_override_allowed_true_blocks`.
31. `test_kill_switch_default_on_missing_not_blocked_blocks`.
32. `test_kill_switch_default_on_unknown_not_blocked_blocks`.
33. `test_operator_acknowledgment_missing_no_live_submit_blocks`.
34. `test_operator_acknowledgment_missing_no_trading_authorization_blocks`.
35. `test_operator_acknowledgment_digest_mismatch_blocks`.
36. `test_audit_policy_invalid_blocks`.
37. `test_secret_like_fields_rejected`.
38. `test_endpoint_like_fields_rejected`.
39. `test_url_protocol_values_rejected`.
40. `test_raw_artifact_leakage_rejected`.
41. `test_output_path_aliasing_rejected`.
42. `test_json_and_markdown_agree`.
43. `test_json_write_failure_rolls_back_status`.
44. `test_synthesis_failure_returns_blocked`.
45. `test_operator_gate_synthesized_is_not_final_success`.
46. `test_only_operator_gate_recorded_exits_zero`.
47. `test_disclaimer_present_in_json_and_markdown`.

### 13.2 CLI tests

**File:** `tests/test_operator_approval_gate_cli.py`

1. `test_help_contains_disclaimer`
2. `test_valid_cli_all_pass`
3. `test_json_output_mode`
4. `test_missing_required_flag_fails`
5. `test_unsafe_flag_rejected` parameterized over all unsafe flags.
6. `test_equals_syntax_rejected`
7. `test_workspace_before_agent_delegates_to_legacy`
8. `test_workspace_after_agent_rejected_by_configless`
9. `test_output_path_aliasing_rejected`

### 13.3 Contract tests

**File:** `tests/test_operator_approval_gate_contract.py`

1. `test_contract_checker_passes`
2. `test_checker_fails_if_route_missing`
3. `test_checker_fails_if_unsafe_flag_missing`
4. `test_checker_fails_if_forbidden_import_added`
5. `test_checker_fails_if_forbidden_status_appears`
6. `test_checker_fails_if_disclaimer_missing`
7. `test_checker_fails_if_cand007_assertion_omitted`
8. `test_checker_fails_if_acknowledgment_text_emitted`

### 13.4 Import-trace tests

**File:** `tests/test_operator_approval_gate_import_trace.py`

1. `test_configless_route_imports_no_forbidden_modules`
2. `test_help_route_imports_no_cli`
3. `test_valid_route_imports_no_cli`
4. `test_workspace_after_agent_rejected_without_cli_import`
5. `test_workspace_before_agent_delegates_to_legacy`
6. `test_run_mode_live_remains_fail_closed`
7. `test_all_configless_routes_avoid_forbidden_modules`

Use `sys.modules` snapshotting and subprocess-based import tracing.

### 13.5 Regression tests

Add to existing import-trace or e2e tests if appropriate:

- CAND-006 configless route still works.
- CAND-007 configless route still works.
- `atlas run --mode live` remains fail-closed.
- `scripts/check_cli_command_compatibility.py` still passes.

---

## 14. Docs/governance implementation plan

### 14.1 New docs

**File:** `docs/operator-approval-gate.md`

Include:

- Command name and purpose.
- Evidence-only disclaimer.
- Required inputs and flags.
- Unsafe flags list.
- Output files.
- Status semantics.
- Example invocation.
- Notes that v0.6.15 is current release and v0.6.16 is planning-only.

### 14.2 Updated docs

- `docs/autonomy-roadmap.md` — append CAND-008 as a planning-only operator review stage.
- `docs/bounded-live-autonomy-governance.md` — append CAND-008 to the staged ladder.
- `docs/runtime-readiness-envelope.md` — add "Next stage: CAND-008" forward reference.
- `docs/releases/v0.6.16-plan.md` — list CAND-008 as proposed.
- `docs/releases/v0.6.16-candidates.md` — list CAND-008 as proposed.
- `docs/releases/v0.6.16-candidate-selection.md` — add "Why CAND-008 is eligible".
- `docs/releases/v0.6.16-candidates.json` — add candidate object.
- `CHANGELOG.md` — add under `[Unreleased]`:
  `- Planning: CAND-008 Operator Approval Gate & Kill-Switch Observation Fixture Review.`

Rules for all docs:

- No live-readiness claim.
- No trade-approval claim.
- No permission-to-submit language.
- No profitability claim.
- No broker endorsement.
- v0.6.15 remains current public release.
- v0.6.16 remains candidate/planning-only.

---

## 15. Implementation phases

### Phase 0 — Baseline verification

**Files touched:** none (read-only).

**Expected diff:** none.

**Tests to run:**

```bash
git diff --check
python3.11 -m pytest tests/test_gated_submit_conformance*.py tests/test_runtime_readiness_envelope*.py -q
python3.11 scripts/check_gated_submit_conformance_contract.py
python3.11 scripts/check_runtime_readiness_envelope_contract.py
python3.11 scripts/check_cli_command_compatibility.py
atlas run --mode live
```

**Safety checks:** All existing tests pass; live mode fails safely.

**Rollback criteria:** Any existing test failure blocks Phase 1.

### Phase 1 — Engine skeleton and constants

**Files touched:** `src/atlas_agent/agent/operator_approval_gate.py`.

**Expected diff:** Add module docstring, imports, constants, exception, dataclasses, and helper functions.

**Tests to run:**

```bash
python3.11 -m compileall src/atlas_agent/agent/operator_approval_gate.py
python3.11 -c "from atlas_agent.agent.operator_approval_gate import GATE_SEQUENCE, APPROVED_FINAL_STATUSES; print(GATE_SEQUENCE)"
```

**Safety checks:** No forbidden imports; module compiles.

**Rollback criteria:** Revert the file if it imports anything forbidden.

### Phase 2 — Upstream projection validators

**Files touched:** `src/atlas_agent/agent/operator_approval_gate.py`.

**Expected diff:** Add `_validate_quality_gate`, `_validate_shadow_comparison`, `_validate_submit_conformance`, `_validate_readiness_envelope`.

**Tests to run:**

```bash
python3.11 -m pytest tests/test_operator_approval_gate.py::test_missing_cand004_blocks tests/test_operator_approval_gate.py::test_cand004_wrong_quality_state_blocks -v
```

Add tests as each validator lands.

**Safety checks:** Each validator rejects missing/wrong fields; never copies raw upstream bodies.

**Rollback criteria:** Revert if projection leaks raw upstream content.

### Phase 3 — CAND-008 fixture validators

**Files touched:** `src/atlas_agent/agent/operator_approval_gate.py`.

**Expected diff:** Add validators for operator identity, approval policy, kill-switch observation, operator acknowledgment, audit policy.

**Tests to run:**

```bash
python3.11 -m pytest tests/test_operator_approval_gate.py -k "operator_identity or approval_policy or kill_switch or acknowledgment or audit_policy" -v
```

**Safety checks:** Closed schemas reject unknown keys; kill-switch gate requires blocked state and false overrides.

**Rollback criteria:** Revert if any fixture validator accepts unknown keys or permissive values.

### Phase 4 — Gate evaluator

**Files touched:** `src/atlas_agent/agent/operator_approval_gate.py`.

**Expected diff:** Add `build_operator_approval_gate_report`, gate helpers, correlation helper, `_build_report`.

**Tests to run:**

```bash
python3.11 -m pytest tests/test_operator_approval_gate.py -q
```

**Safety checks:** First failure stops evaluation; downstream gates `not_run`; only `operator_gate_synthesized` after gate 12.

**Rollback criteria:** Revert if any gate continues after failure or wrong status is returned.

### Phase 5 — Artifact writer and Markdown renderer

**Files touched:** `src/atlas_agent/agent/operator_approval_gate.py`.

**Expected diff:** Add `_render_markdown_report` and `write_operator_approval_gate_artifacts`.

**Tests to run:**

```bash
python3.11 -m pytest tests/test_operator_approval_gate.py::test_valid_all_pass_operator_gate tests/test_operator_approval_gate.py::test_json_and_markdown_agree -v
```

**Safety checks:** Output JSON does not contain raw upstream artifacts; Markdown does not contain canonical acknowledgment text.

**Rollback criteria:** Revert if output leaks raw upstream bodies or literal canonical text.

### Phase 6 — CLI and bootstrap route

**Files touched:**

- `src/atlas_agent/agent/operator_approval_gate_cli.py`
- `src/atlas_agent/cli_bootstrap.py`
- `src/atlas_agent/cli.py`

**Expected diff:** Add CLI module, exact bootstrap route, minimal legacy subparser.

**Tests to run:**

```bash
atlas agent operator-approval-gate --help
python3.11 -m pytest tests/test_operator_approval_gate_cli.py -q
python3.11 -m pytest tests/test_operator_approval_gate_import_trace.py -q
```

**Safety checks:** Configless route avoids `atlas_agent.cli` import; unsafe flags reject; `--workspace` behavior correct.

**Rollback criteria:** Revert if import trace shows forbidden module load.

### Phase 7 — Static checker

**Files touched:** `scripts/check_operator_approval_gate_contract.py`, `scripts/dev_check.sh`, `scripts/release_check.sh`.

**Expected diff:** Add contract checker and register it in dev/release check scripts.

**Tests to run:**

```bash
python3.11 scripts/check_operator_approval_gate_contract.py
python3.11 -m pytest tests/test_operator_approval_gate_contract.py -q
bash scripts/dev_check.sh
```

**Safety checks:** Checker passes on current code and fails on injected violations.

**Rollback criteria:** Revert if checker has false positives or misses required checks.

### Phase 8 — Tests

**Files touched:** `tests/test_operator_approval_gate.py`, `tests/test_operator_approval_gate_cli.py`, `tests/test_operator_approval_gate_contract.py`, `tests/test_operator_approval_gate_import_trace.py`, optional `tests/test_operator_approval_gate_e2e.py`.

**Expected diff:** Add full test suites.

**Tests to run:**

```bash
python3.11 -m pytest tests/test_operator_approval_gate*.py -q
```

**Safety checks:** Coverage of all gates, failure modes, unsafe flags, import boundaries.

**Rollback criteria:** Revert any test that does not assert the documented behavior.

### Phase 9 — Docs/governance metadata

**Files touched:** docs listed in Section 14.

**Expected diff:** Add/update docs; add `[Unreleased]` CHANGELOG entry.

**Tests to run:**

```bash
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_bounded_autonomy_governance.py
```

**Safety checks:** No forbidden claims; no version bump; no release/tag/PyPI wording.

**Rollback criteria:** Revert any doc change implying live readiness.

### Phase 10 — Full verification and push

**Files touched:** none new.

**Expected diff:** clean working tree after final commit.

**Tests to run:** full verification matrix from Section 16.

**Safety checks:** All tests pass; live mode fail-closed; version unchanged.

**Rollback criteria:** If any check fails, fix in place or revert offending commit.

---

## 16. Verification matrix

Run these commands after implementation:

```bash
git diff --check
python3.11 -m compileall src scripts
python3.11 -m pytest tests/test_operator_approval_gate*.py -q
python3.11 -m pytest tests/test_gated_submit_conformance*.py tests/test_runtime_readiness_envelope*.py -q
python3.11 -m pytest tests/test_candidate_chain_e2e.py -q
python3.11 scripts/check_operator_approval_gate_contract.py
python3.11 scripts/check_gated_submit_conformance_contract.py
python3.11 scripts/check_runtime_readiness_envelope_contract.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 scripts/check_bounded_autonomy_governance.py
python3.11 scripts/check_cli_command_compatibility.py
atlas agent submit-conformance --help
atlas agent readiness-envelope --help
atlas agent operator-approval-gate --help
atlas run --mode live
bash scripts/release_check.sh --quick
```

Optional, if feasible:

```bash
python3.11 -m pytest -q --durations=25
```

---

## 17. Acceptance criteria

Implementation can be considered complete only if:

- All planned files exist.
- `scripts/check_operator_approval_gate_contract.py` passes.
- Targeted tests pass.
- Quick release check passes.
- `atlas run --mode live` remains fail-closed.
- No source/package version bump occurred.
- No tag, GitHub Release, or PyPI publication occurred.
- No live/trade/readiness claims exist in source or docs.
- CAND-008 outputs are evidence-only.
- Raw upstream artifacts do not leak into outputs.
- Unsafe flags are rejected at parse time.
- Import boundaries hold for the configless route.
- Final commit is pushed to `origin/main`.

---

## 18. Review plan after implementation

After implementation, require:

1. Implementation report summarizing files changed, tests run, and verification results.
2. Independent implementation review against this plan and the design doc.
3. Fix pass if review finds issues.
4. Final CAND-008 acceptance review.
5. Only then consider v0.6.16 release-readiness review.

Do not recommend release cutover immediately after implementation.

---

## Safety boundaries preserved

This plan preserves all required boundaries:

- No live trading.
- No live submit.
- No real orders.
- No pending orders.
- No approval queue entries.
- No broker/provider calls.
- No credentials.
- No endpoint URLs.
- No network calls.
- No live-mode enablement.
- No kill-switch override.
- No `Order` / `OrderRouter` / `RiskManager` / `ApprovalManager` / runtime kill-switch instantiation.
- No runtime kill-switch mutation.
- No raw upstream artifact copying.
- No live-readiness claims.
- No trading-safety claims.
- No profitability claims.
- No broker endorsement.
- No permission-to-submit language.
- `atlas run --mode live` remains fail-closed.
- Package version remains `0.6.15`.
- Public release remains `v0.6.15`.
- `v0.6.16` remains candidate/planning-only.

---

## Confirmation

No implementation code has been changed. Only this implementation-plan document has been created.

## Execution handoff

Plan complete and saved to `docs/operator-approval-gate-implementation-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per phase/task, review between tasks, fast iteration. REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`.
2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

Which approach would you like to use?
