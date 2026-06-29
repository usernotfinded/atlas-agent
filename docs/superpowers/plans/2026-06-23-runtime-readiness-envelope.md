# CAND-007 Runtime Readiness Envelope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `atlas agent readiness-envelope` as a deterministic, local-only, fixture-only, evidence-only runtime readiness envelope evaluator that consumes CAND-004/CAND-005/CAND-006 artifacts plus five static policy fixtures and records `runtime-readiness-envelope.json` and `runtime-readiness-envelope-report.md` without ever submitting orders, calling brokers/providers, loading credentials, or importing runtime trading modules.

**Architecture:** A stdlib-only engine (`src/atlas_agent/agent/runtime_readiness_envelope.py`) validates upstream artifacts by projection and CAND-007-owned fixtures by closed schema, evaluates a strict fail-closed gate sequence, and writes atomic artifacts. A configless CLI handler (`src/atlas_agent/agent/runtime_readiness_envelope_cli.py`) is routed by the existing narrow bootstrap pre-router. A static contract checker and subprocess import-trace tests enforce the safety boundary.

**Tech Stack:** Python 3.11+ stdlib only for CAND-007 runtime modules; pytest for tests; argparse for CLI.

---

## Non-Goals and Hard Boundaries

CAND-007 must not:

- Enable live trading or live submit.
- Submit, place, cancel, or flatten orders.
- Create real or pending orders.
- Call brokers, providers, the runtime kill switch, `OrderRouter`, or `RiskManager`.
- Load credentials, API keys, account IDs, or Atlas config on the CAND-007 route.
- Make network calls.
- Instantiate `Order`.
- Mutate runtime state.
- Claim live readiness, trading safety, profitability, or permission to submit orders.
- Bump the source/package version, create a tag, cut a GitHub Release, or publish to PyPI.

The output is an evidence-recording artifact only. The status `readiness_envelope_recorded` is not live readiness.

---

## Required Implementation Order

1. Core stdlib-only engine (validators, gate engine, artifact writer).
2. Configless CLI handler.
3. Bootstrap pre-router second route.
4. Engine, CLI, and import-trace tests.
5. Static contract checker.
6. Docs and release metadata updates.
7. Full validation.

Do not start by modifying the legacy CLI parser. The bootstrap pre-router is the P0 safety boundary.

---

## 1. Files to Add

- `src/atlas_agent/agent/runtime_readiness_envelope.py`
  - Closed-schema validators for the five CAND-007-owned fixtures.
  - Projection validators for CAND-004, CAND-005, CAND-006.
  - Secret/endpoint/URL scanner.
  - Timestamp and decimal normalization helpers.
  - Gate engine.
  - Artifact writer.
- `src/atlas_agent/agent/runtime_readiness_envelope_cli.py`
  - Argparse CLI with unsafe-flag deny list.
  - Text/JSON output rendering.
- `scripts/check_runtime_readiness_envelope_contract.py`
  - Static contract checker.
- `tests/test_runtime_readiness_envelope.py`
  - Engine feature tests.
- `tests/test_runtime_readiness_envelope_cli.py`
  - CLI tests.
- `tests/test_runtime_readiness_envelope_import_trace.py`
  - Subprocess import-boundary tests.
- `tests/test_runtime_readiness_envelope_contract.py`
  - Static-checker invocation tests.
- `docs/runtime-readiness-envelope.md`
  - User-facing command documentation.

Test fixture helpers live inside the test modules. Do not add checked-in secrets, broker credentials, account IDs, or real endpoints.

---

## 2. Files to Modify

- `src/atlas_agent/cli_bootstrap.py`
  - Add a second exact two-token route for `agent readiness-envelope`.
- `src/atlas_agent/cli.py`
  - Register a minimal legacy subparser for `agent readiness-envelope` so that
    delegated `atlas --workspace X agent readiness-envelope --help` behaves
    consistently. The subparser must not load broker/provider/config modules; it
    may print help describing the configless route and exit, or it may delegate to
    the configless `runtime_readiness_envelope_cli.main`. It must not implement
    live execution paths.
- `tests/fixtures/cli_command_contract.json`
  - Add `agent readiness-envelope` under the bootstrap-only commands section.
- `scripts/check_cli_command_compatibility.py`
  - Already supports bootstrap-only commands from CAND-006; ensure it reads the updated contract fixture.
- `tests/test_cli_command_compatibility.py`
  - Validate bootstrap-only command registration.
- `tests/test_package_distribution_check.py`
  - No entry-point change is required because `pyproject.toml` already points to `atlas_agent.cli_bootstrap:main`; verify the test still passes.
- `docs/architecture.md`
  - Document `agent readiness-envelope` as a second bootstrap-only configless route.
- `docs/cli-command-compatibility.md`
  - Document the second bootstrap-only command exception.
- `docs/runtime-readiness-envelope-design.md`
  - Mark design status as implemented after code lands (do not do this prematurely).
- `docs/autonomy-roadmap.md`
  - Mark CAND-007 implemented in planning.
- `docs/bounded-live-autonomy-governance.md`
  - Update staged-autonomy posture.
- `docs/shadow-live-readiness-contract.md`
  - Reference CAND-007 as the envelope evaluator, not a live path.
- `docs/gated-submit-conformance.md`
  - Add forward reference to CAND-007 as the next envelope stage.
- `docs/releases/v0.6.16-plan.md`
  - Add CAND-007 row.
- `docs/releases/v0.6.16-candidates.md`
  - Add CAND-007 implemented entry.
- `docs/releases/v0.6.16-candidate-selection.md`
  - Add "Why CAND-007 is eligible" section.
- `docs/releases/v0.6.16-candidates.json`
  - Add CAND-007 candidate object.
- `CHANGELOG.md`
  - Add CAND-007 entry under `[Unreleased]`.
- `scripts/dev_check.sh`
  - Wire CAND-007 checker and tests.
- `scripts/release_check.sh`
  - Wire CAND-007 checker and tests.

The actual CAND-007 implementation lives in the configless handler, but the legacy CLI parser must register a minimal subparser for `readiness-envelope` so that delegated `atlas --workspace X agent readiness-envelope --help` produces consistent help text. The legacy subparser must not implement live execution paths.

---

## 3. Public API Design

In `src/atlas_agent/agent/runtime_readiness_envelope.py`, expose stdlib-only APIs:

```python
APPROVED_FINAL_STATUSES: tuple[str, ...]
GATE_SEQUENCE: tuple[str, ...]
EVIDENCE_ONLY_DISCLAIMER: str
ReadinessEnvelopeInputs
GateResult
ReadinessEnvelopeReport
canonical_json_bytes(value: Any) -> bytes
fingerprint_json(value: Any) -> str
parse_as_of_utc(value: str) -> str
build_runtime_readiness_envelope_report(inputs: ReadinessEnvelopeInputs) -> ReadinessEnvelopeReport
write_runtime_readiness_envelope_artifacts(report: ReadinessEnvelopeReport, output_dir: Path) -> ReadinessEnvelopeReport
```

In `src/atlas_agent/agent/runtime_readiness_envelope_cli.py`, expose:

```python
build_parser() -> argparse.ArgumentParser
main(argv: list[str] | None = None) -> int
```

Allowed imports in CAND-007 runtime modules:

- `argparse`
- `dataclasses`
- `hashlib`
- `json`
- `os`
- `re`
- `tempfile`
- `decimal`
- `datetime` only for parsing supplied `--as-of` and fixture timestamps
- `pathlib`
- `typing`

No CAND-007 code may call `datetime.now()`, `date.today()`, `time.time()`, or equivalent wall-clock APIs for gate decisions.

---

## 4. CLI/Bootstrap Design

### 4.1 Bootstrap pre-router change

Modify `src/atlas_agent/cli_bootstrap.py`:

```python
"""Narrow CLI bootstrap pre-router.

Routes exactly two configless commands through dedicated stdlib-only paths:

    atlas agent submit-conformance
    atlas agent readiness-envelope

All other commands, including ``atlas --workspace X agent readiness-envelope``,
delegate unchanged to the legacy ``atlas_agent.cli:main`` entry point.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "agent":
        if args[1] == "submit-conformance":
            from atlas_agent.agent.gated_submit_conformance_cli import main as route_main
            return route_main(args[2:])
        if args[1] == "readiness-envelope":
            from atlas_agent.agent.runtime_readiness_envelope_cli import main as route_main
            return route_main(args[2:])
    from atlas_agent.cli import main as legacy_main
    return legacy_main(args)


if __name__ == "__main__":
    sys.exit(main())
```

### 4.2 Approved CLI

```bash
atlas agent readiness-envelope \
  --quality-gate <trading-quality-gate.json> \
  --shadow-comparison <shadow-live-comparison.json> \
  --submit-conformance <gated-submit-conformance.json> \
  --runtime-envelope <runtime-envelope.json> \
  --broker-capabilities <broker-capabilities.json> \
  --operator-policy <operator-policy.json> \
  --kill-switch-policy <kill-switch-policy.json> \
  --audit-policy <audit-policy.json> \
  --output-dir <dir> \
  --as-of <ISO-8601 UTC timestamp> \
  [--json]
```

Required options:

- `--quality-gate`
- `--shadow-comparison`
- `--submit-conformance`
- `--runtime-envelope`
- `--broker-capabilities`
- `--operator-policy`
- `--kill-switch-policy`
- `--audit-policy`
- `--output-dir`
- `--as-of`

Optional options:

- `--json`

### Task 1: Update bootstrap pre-router

**Files:**
- Modify: `src/atlas_agent/cli_bootstrap.py`
- Test: `tests/test_runtime_readiness_envelope_import_trace.py`

- [ ] **Step 1: Add the CAND-007 exact route**

Edit `src/atlas_agent/cli_bootstrap.py` to add the `elif args[1] == "readiness-envelope"` branch shown above.

- [ ] **Step 2: Verify existing delegation is preserved**

Run:

```bash
python -m pytest tests/test_gated_submit_conformance_import_trace.py -q
```

Expected: all existing CAND-006 import-trace tests still pass.

- [ ] **Step 3: Commit**

```bash
git add src/atlas_agent/cli_bootstrap.py
git commit -m "feat(cand-007): add readiness-envelope exact route to bootstrap pre-router"
```

### Task 1.5: Register minimal legacy CLI subparser

**Files:**
- Modify: `src/atlas_agent/cli.py`
- Test: `tests/test_cli_command_compatibility.py`

- [ ] **Step 1: Locate the `agent` subparser in `src/atlas_agent/cli.py`**

Find where CAND-006 or other `agent` subcommands are registered. Add a minimal `readiness-envelope` subparser:

```python
re_parser = agent_subparsers.add_parser(
    "readiness-envelope",
    help="Runtime readiness envelope evaluation (CAND-007) — simulated only.",
)
re_parser.add_argument(
    "--quality-gate", help="Path to CAND-004 trading-quality-gate.json."
)
re_parser.add_argument(
    "--shadow-comparison", help="Path to CAND-005 shadow-live-comparison.json."
)
re_parser.add_argument(
    "--submit-conformance", help="Path to CAND-006 gated-submit-conformance.json."
)
re_parser.add_argument(
    "--runtime-envelope", help="Path to the runtime envelope fixture."
)
re_parser.add_argument(
    "--broker-capabilities", help="Path to the broker capability manifest fixture."
)
re_parser.add_argument(
    "--operator-policy", help="Path to the operator policy fixture."
)
re_parser.add_argument(
    "--kill-switch-policy", help="Path to the kill-switch policy fixture."
)
re_parser.add_argument(
    "--audit-policy", help="Path to the audit policy fixture."
)
re_parser.add_argument("--output-dir", help="Output directory for artifacts.")
re_parser.add_argument("--as-of", help="ISO-8601 UTC timestamp.")
re_parser.add_argument("--json", action="store_true", help="Emit JSON on stdout.")
re_parser.set_defaults(func=_run_readiness_envelope_legacy_help)
```

Add the handler:

```python
def _run_readiness_envelope_legacy_help(args: argparse.Namespace) -> int:
    print("Runtime readiness envelope (CAND-007) is implemented configlessly as:")
    print("  atlas agent readiness-envelope ...")
    print("Use the configless form above; this delegated form is for --workspace compatibility only.")
    return 0 if getattr(args, "help", False) else 2
```

- [ ] **Step 2: Update the CLI command contract fixture**

Edit `tests/fixtures/cli_command_contract.json` and add `"readiness-envelope"` to the `"agent"` subcommands list (next to `"submit-conformance"`).

- [ ] **Step 3: Verify `--help` works in delegated form and contract tests pass**

Run:

```bash
python -m atlas_agent.cli --workspace /tmp agent readiness-envelope --help
python -m pytest tests/test_cli_command_compatibility.py -q
```

Expected: help text printed, exit 0; contract tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/cli.py
git commit -m "feat(cand-007): register minimal legacy subparser for delegated readiness-envelope"
```

---

## 5. Input Dataclass/Schema Design

### 5.1 `ReadinessEnvelopeInputs`

```python
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
```

### 5.2 `GateResult`

```python
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
```

### 5.3 `ReadinessEnvelopeReport`

```python
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
```

### 5.4 Approved statuses and gate sequence

```python
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
```

### Task 2: Scaffold engine constants and dataclasses

**Files:**
- Create: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write the constants test**

```python
def test_approved_statuses_include_required_values() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import APPROVED_FINAL_STATUSES
    for status in (
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
    ):
        assert status in APPROVED_FINAL_STATUSES
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_approved_statuses_include_required_values -v
```

Expected: FAIL with import error.

- [ ] **Step 2: Create the engine module with constants**

Write the constants and dataclasses section into `src/atlas_agent/agent/runtime_readiness_envelope.py`.

- [ ] **Step 3: Verify the test passes**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_approved_statuses_include_required_values -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): scaffold engine constants and dataclasses"
```

---

## 6. Projection Validation Design for CAND-004/CAND-005/CAND-006

### 6.1 CAND-004 projection

Accepted keys exactly:

- `artifact_type`
- `schema_version`
- `mode`
- `run_id`
- `symbol`
- `quality_state`
- `blockers`

Rules:

- Secret-scan the source artifact as a full object.
- Project the accepted keys into a closed validation object.
- `artifact_type == "trading_quality_gate"`.
- `schema_version` in `{"trading-quality-gate.v1", "1", 1}`.
- `mode == "paper"`.
- `quality_state == "eligible_for_shadow_live_quality_review"`.
- `blockers == []`.
- Return normalized dict with string `schema_version`.

### 6.2 CAND-005 projection

Accepted keys exactly:

- `artifact_type`
- `schema_version`
- `run_id`
- `symbol`
- `quality_state`
- `status`
- `freshness_assessment`
- `blockers`

Rules:

- Secret-scan the source artifact as a full object.
- Project the accepted keys into a closed validation object.
- `artifact_type == "shadow_live_comparison"`.
- `schema_version == "shadow-live-comparison.v1"`.
- `quality_state == "eligible_for_shadow_live_quality_review"`.
- `status == "matched"`.
- `blockers == []`.

### 6.3 CAND-006 projection

Accepted keys exactly:

- `artifact_type`
- `schema_version`
- `candidate`
- `mode`
- `run_id`
- `symbol`
- `status`
- `as_of`
- `safety_assertions`
- `dry_run_request`
- `blockers`

Rules:

- Secret-scan the source artifact as a full object.
- Project the accepted keys into a closed validation object.
- `artifact_type == "gated_submit_conformance"`.
- `schema_version == "gated-submit-conformance.v1"`.
- `candidate == "CAND-006"`.
- `mode == "simulated_only"`.
- `status == "dry_run_recorded"`.
- All `safety_assertions` values are `true`.
- `dry_run_request.transmission.allowed` is `false`.
- `dry_run_request.transmission.broker_adapter` is `null`.
- `dry_run_request.transmission.provider` is `null`.
- `blockers == []`.
- `as_of` is ISO-8601 UTC and is <= CAND-007 `--as-of`.
- `(CAND-007 as_of) - (CAND-006 as_of)` <= 24 hours.

### Task 3: Implement upstream projection validators

**Files:**
- Modify: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write a test for CAND-004 projection pass**

```python
def test_validate_quality_gate_projection_pass() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import _validate_quality_gate
    data = {
        "artifact_type": "trading_quality_gate",
        "schema_version": "trading-quality-gate.v1",
        "mode": "paper",
        "run_id": "run-123",
        "symbol": "AAPL",
        "quality_state": "eligible_for_shadow_live_quality_review",
        "blockers": [],
        "extra_field": "ignored",
    }
    result = _validate_quality_gate(data)
    assert result["artifact_type"] == "trading_quality_gate"
    assert "extra_field" not in result
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_validate_quality_gate_projection_pass -v
```

Expected: FAIL with `_validate_quality_gate` not defined.

- [ ] **Step 2: Implement `_validate_quality_gate`, `_validate_shadow_comparison`, and `_validate_submit_conformance`**

Add to `src/atlas_agent/agent/runtime_readiness_envelope.py`:

```python
_TRADING_QUALITY_GATE_ARTIFACT_TYPE = "trading_quality_gate"
_TRADING_QUALITY_GATE_SCHEMA_VERSIONS = ("trading-quality-gate.v1", 1, "1")
_SHADOW_LIVE_COMPARISON_ARTIFACT_TYPE = "shadow_live_comparison"
_SHADOW_LIVE_COMPARISON_SCHEMA_VERSION = "shadow-live-comparison.v1"
_GATED_SUBMIT_CONFORMANCE_ARTIFACT_TYPE = "gated_submit_conformance"
_GATED_SUBMIT_CONFORMANCE_SCHEMA_VERSION = "gated-submit-conformance.v1"


def _validate_quality_gate(data: dict[str, Any]) -> dict[str, Any]:
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
```

Implement the CAND-005 and CAND-006 validators similarly, with CAND-006 enforcing the freshness rule via `_parse_iso_timestamp`.

- [ ] **Step 3: Verify projection tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "projection or quality_gate or shadow_comparison or submit_conformance" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): add CAND-004/005/006 projection validators"
```

---

## 7. Closed-Schema Fixture Validation Design for CAND-007-Owned Fixtures

All five fixtures are closed-schema. Unknown top-level keys are rejected.

### 7.1 Runtime envelope fixture

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `fixture_mode`
- `run_id`
- `symbol`
- `allowed_modes`
- `forbidden_modes`
- `live_submit_enabled`
- `require_human_approval`
- `require_kill_switch_inactive`
- `require_risk_gate`
- `require_audit_recording`
- `require_broker_capability_manifest`
- `max_order_notional`
- `max_symbol_exposure`
- `max_daily_orders`
- `max_daily_notional`
- `supported_order_types`
- `supported_time_in_force`
- `expires_at`

Rules:

- `artifact_type == "runtime_readiness_envelope_fixture"`.
- `schema_version == "runtime-readiness-envelope-fixture.v1"`.
- `fixture_mode == "simulated/static"`.
- `allowed_modes` is a list containing at least `"paper"`, `"shadow_live_readonly"`, and `"simulated"`.
- `forbidden_modes` contains `"live"` and `"live_submit"`.
- `live_submit_enabled` is `false`.
- All `require_*` booleans are `true`.
- Decimal fields are positive canonical decimal strings.
- `max_daily_orders` is a positive integer.
- `supported_order_types` is non-empty and subset of `{"market", "limit"}`.
- `supported_time_in_force` is non-empty and subset of `{"day"}`.
- `expires_at` is ISO-8601 UTC and `> as_of`.

### 7.2 Broker capability manifest fixture

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `broker_label`
- `capabilities`
- `disabled_capabilities`
- `unsupported_order_types`
- `sandbox_only`
- `live_api_contact_allowed`
- `credentials_present`
- `endpoint_present`
- `captured_at`
- `expires_at`

Rules:

- `artifact_type == "broker_capability_manifest_fixture"`.
- `schema_version == "broker-capability-manifest-fixture.v1"`.
- `broker_label` starts with `local-`, `simulated-`, `fixture-`, or `redacted-`.
- `sandbox_only` is `true`.
- `live_api_contact_allowed` is `false`.
- `credentials_present` is `false`.
- `endpoint_present` is `false`.
- `capabilities` is an object with only boolean values.
- `disabled_capabilities` and `unsupported_order_types` are lists of strings.
- `expires_at` is ISO-8601 UTC and `> as_of`.

### 7.3 Operator policy fixture

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `requires_manual_review`
- `requires_explicit_approval`
- `approval_scope`
- `unattended_operation_allowed`
- `max_runtime_window_seconds`
- `max_actions_per_session`
- `allowed_symbols`
- `blocked_symbols`
- `expires_at`

Rules:

- `artifact_type == "operator_policy_fixture"`.
- `schema_version == "operator-policy-fixture.v1"`.
- `requires_manual_review` and `requires_explicit_approval` are `true`.
- `approval_scope` in `{"candidate_only", "simulated_only"}`.
- `unattended_operation_allowed` is `false`.
- `max_runtime_window_seconds` and `max_actions_per_session` are positive integers.
- `allowed_symbols` and `blocked_symbols` are lists of strings.
- Evaluated symbol must be in `allowed_symbols` if `allowed_symbols` is non-empty, and not in `blocked_symbols`.
- `expires_at` is ISO-8601 UTC and `> as_of`.

### 7.4 Kill-switch policy fixture

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `kill_switch_required`
- `default_state_on_missing_runtime`
- `default_state_on_unknown_runtime`
- `operator_override_allowed`
- `expires_at`

Rules:

- `artifact_type == "kill_switch_policy_fixture"`.
- `schema_version == "kill-switch-policy-fixture.v1"`.
- `kill_switch_required` is `true`.
- `default_state_on_missing_runtime` and `default_state_on_unknown_runtime` are `"blocked"`.
- `operator_override_allowed` is `false`.
- `expires_at` is ISO-8601 UTC and `> as_of`.

### 7.5 Audit policy fixture

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `audit_required`
- `append_only_required`
- `hash_chain_required`
- `local_artifact_recording_required`
- `live_audit_chain_claimed`
- `expires_at`

Rules:

- `artifact_type == "audit_policy_fixture"`.
- `schema_version == "audit-policy-fixture.v1"`.
- `audit_required`, `append_only_required`, `hash_chain_required`, and `local_artifact_recording_required` are `true`.
- `live_audit_chain_claimed` is `false`.
- `expires_at` is ISO-8601 UTC and `> as_of`.

### Task 4: Implement closed-schema fixture validators

**Files:**
- Modify: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write a failing test for runtime envelope fixture validation**

```python
def test_validate_runtime_envelope_fixture_pass() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import _validate_runtime_envelope_fixture
    data = {
        "artifact_type": "runtime_readiness_envelope_fixture",
        "schema_version": "runtime-readiness-envelope-fixture.v1",
        "fixture_mode": "simulated/static",
        "run_id": "run-123",
        "symbol": "AAPL",
        "allowed_modes": ["paper", "shadow_live_readonly", "simulated"],
        "forbidden_modes": ["live", "live_submit", "unsupervised_live"],
        "live_submit_enabled": False,
        "require_human_approval": True,
        "require_kill_switch_inactive": True,
        "require_risk_gate": True,
        "require_audit_recording": True,
        "require_broker_capability_manifest": True,
        "max_order_notional": "1000.00",
        "max_symbol_exposure": "5000.00",
        "max_daily_orders": 10,
        "max_daily_notional": "10000.00",
        "supported_order_types": ["market", "limit"],
        "supported_time_in_force": ["day"],
        "expires_at": "2026-06-24T12:00:00Z",
    }
    result = _validate_runtime_envelope_fixture(data, "2026-06-24T10:00:00Z")
    assert result["live_submit_enabled"] is False
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_validate_runtime_envelope_fixture_pass -v
```

Expected: FAIL.

- [ ] **Step 2: Implement the five closed-schema validators**

Add `_validate_runtime_envelope_fixture`, `_validate_broker_capability_manifest`, `_validate_operator_policy_fixture`, `_validate_kill_switch_policy_fixture`, and `_validate_audit_policy_fixture` to the engine module. Use the exact allowed-key sets and rules above.

- [ ] **Step 3: Verify fixture validation tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "fixture" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): add closed-schema validators for CAND-007-owned fixtures"
```

---

## 8. Universal Rejection Rules

Before schema validation, scan every loaded JSON object for:

### 8.1 Secret-like keys

```python
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
```

### 8.2 Secret-like value fragments

```python
_SECRET_VALUE_PATTERNS = (
    "bearer ",
    "sk-",
    "ghp_",
    "akia",
    ".env",
    ".env.atlas",
)
```

### 8.3 Endpoint-like keys

```python
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
```

### 8.4 URL/protocol value patterns

```python
_URL_PROTOCOL_PATTERNS = (
    "http://",
    "https://",
    "ws://",
    "wss://",
)
```

### 8.5 Forbidden fixture keys (explicitly prohibited)

```python
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
}
```

### 8.6 Scan implementation

```python
def _secret_value_match(lower_value: str, pattern: str) -> bool:
    return re.search(r"(?:^|\W)" + re.escape(pattern), lower_value) is not None


def _universal_reject_scan(obj: Any, path: str = "") -> list[str]:
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
            findings.extend(_universal_reject_scan(value, f"{path}.{key}" if path else key))
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
```

### Task 5: Implement universal rejection scanner

**Files:**
- Modify: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write a failing test for secret/endpoint/URL rejection**

```python
import pytest

def test_universal_reject_scan_finds_secret_key() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import _universal_reject_scan
    findings = _universal_reject_scan({"api_key": "x"})
    assert any("secret-like key" in f for f in findings)


def test_universal_reject_scan_finds_url_value() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import _universal_reject_scan
    findings = _universal_reject_scan({"note": "contact https://example.com"})
    assert any("url protocol value" in f for f in findings)
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_universal_reject_scan_finds_secret_key tests/test_runtime_readiness_envelope.py::test_universal_reject_scan_finds_url_value -v
```

Expected: FAIL.

- [ ] **Step 2: Implement `_universal_reject_scan`**

Add the scanner to the engine module.

- [ ] **Step 3: Verify tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "universal_reject" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): add universal rejection scanner for secrets, endpoints, and URLs"
```

---

## 9. Decimal and Timestamp Normalization

### 9.1 Canonical JSON

```python
def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def fingerprint_json(value: Any) -> str:
    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"sha256:{digest}"
```

### 9.2 Decimal normalization

```python
from decimal import Decimal, InvalidOperation


def _canonical_decimal_string(value: Any, *, allow_zero: bool = True) -> str:
    if not isinstance(value, str):
        raise ReadinessValidationError(f"expected decimal string, got {type(value).__name__}")
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
```

### 9.3 Timestamp normalization

```python
def _format_utc_timestamp(dt: Any) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_timestamp(value: str) -> Any | None:
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
    if not isinstance(value, str):
        raise ReadinessValidationError("as_of is not a string")
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        raise ReadinessValidationError(f"as_of is not a valid ISO-8601 UTC timestamp: {value!r}")
    return _format_utc_timestamp(parsed)
```

### Task 6: Implement canonicalization helpers

**Files:**
- Modify: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write failing tests for canonicalization**

```python
def test_canonical_json_bytes_sorts_keys() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import canonical_json_bytes
    assert canonical_json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_fingerprint_format() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import fingerprint_json
    fp = fingerprint_json({"a": 1})
    assert fp.startswith("sha256:")
    assert len(fp) == 7 + 64


def test_parse_as_of_utc_accepts_z() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import parse_as_of_utc
    assert parse_as_of_utc("2026-06-24T10:00:00Z") == "2026-06-24T10:00:00Z"


def test_parse_as_of_utc_rejects_non_utc() -> None:
    from atlas_agent.agent.runtime_readiness_envelope import parse_as_of_utc
    with pytest.raises(Exception):
        parse_as_of_utc("2026-06-24T10:00:00+01:00")
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_canonical_json_bytes_sorts_keys tests/test_runtime_readiness_envelope.py::test_fingerprint_format tests/test_runtime_readiness_envelope.py::test_parse_as_of_utc_accepts_z tests/test_runtime_readiness_envelope.py::test_parse_as_of_utc_rejects_non_utc -v
```

Expected: FAIL.

- [ ] **Step 2: Implement canonicalization helpers**

Add the functions above to the engine module.

- [ ] **Step 3: Verify tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "canonical or fingerprint or parse_as_of" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): add canonicalization, fingerprinting, and timestamp normalization"
```

---

## 10. Evidence Correlation Rules

After all inputs are loaded and validated, correlate them:

- `run_id` must be identical across CAND-004, CAND-005, CAND-006, and the runtime envelope fixture.
- `symbol` must be identical across CAND-004, CAND-005, CAND-006, the runtime envelope fixture, and the operator policy fixture.
- `candidate` in CAND-006 must be `"CAND-006"`.
- All upstream `blockers` lists must be empty.
- All CAND-007-owned fixture `expires_at` values must be `> as_of`.

### Task 7: Implement evidence correlation

**Files:**
- Modify: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write a failing test for run_id mismatch**

```python
def test_run_id_mismatch_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["quality_gate"]["run_id"] = "run-other"
    _write_fixture(inputs.quality_gate_path, fixtures["quality_gate"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "upstream_quality_blocked"
    assert report.exit_code == 2
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_run_id_mismatch_blocks -v
```

Expected: FAIL.

- [ ] **Step 2: Implement `_correlate_evidence` helper**

Add a helper that compares `run_id` and `symbol` across normalized inputs and returns blockers or an empty list.

- [ ] **Step 3: Verify correlation tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "run_id or symbol" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): add evidence correlation for run_id and symbol"
```

---

## 11. CAND-006 Freshness Rule

In the CAND-006 projection validator and gate:

- CAND-006 `as_of` must exist.
- CAND-006 `as_of <= CAND-007 --as-of`.
- `(CAND-007 as_of) - (CAND-006 as_of) <= 24 hours`.
- Violation maps to `submit_conformance_blocked`.

Implementation:

```python
def _cand006_age_hours(cand006_as_of: str, cand007_as_of: str) -> float:
    from datetime import timedelta
    dt6 = _parse_iso_timestamp(cand006_as_of)
    dt7 = _parse_iso_timestamp(cand007_as_of)
    if dt6 is None or dt7 is None:
        raise ReadinessValidationError("invalid timestamp for CAND-006 age check")
    diff = dt7 - dt6
    return diff.total_seconds() / 3600.0
```

In `_validate_submit_conformance`, after validating `as_of`, enforce:

```python
if _parse_iso_timestamp(as_of) > _parse_iso_timestamp(cand007_as_of):
    raise ReadinessValidationError("CAND-006 as_of is later than CAND-007 as_of")
if _cand006_age_hours(as_of, cand007_as_of) > 24.0:
    raise ReadinessValidationError("CAND-006 evidence is older than 24 hours")
```

The gate catches this and returns `submit_conformance_blocked`.

### Task 8: Implement CAND-006 freshness rule

**Files:**
- Modify: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write a failing test for stale CAND-006 evidence**

```python
def test_submit_conformance_stale_evidence_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["submit_conformance"]["as_of"] = "2026-06-23T09:00:00Z"
    _write_fixture(inputs.submit_conformance_path, fixtures["submit_conformance"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "submit_conformance_blocked"
    assert report.exit_code == 2
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_submit_conformance_stale_evidence_blocks -v
```

Expected: FAIL.

- [ ] **Step 2: Implement freshness check in `_validate_submit_conformance`**

Pass `cand007_as_of: str` into `_validate_submit_conformance` and enforce the two freshness rules.

- [ ] **Step 3: Verify freshness tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "stale or freshness" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): enforce 24-hour CAND-006 evidence freshness rule"
```

---

## 12. Gate Engine Design

Evaluate gates in strict order. Stop on first failure. Record downstream gates as `not_run`.

```python
def build_runtime_readiness_envelope_report(inputs: ReadinessEnvelopeInputs) -> ReadinessEnvelopeReport:
    as_of = parse_as_of_utc(inputs.as_of)
    gate_results: list[GateResult] = []
    blockers: list[str] = []
    final_status = "not_evaluated"

    try:
        normalized = _load_and_validate_all(inputs, as_of)
        gate_results.append(GateResult("schema_preflight", "pass", ""))
    except ReadinessValidationError as exc:
        gate_results.append(GateResult("schema_preflight", "fail", str(exc)))
        blockers.append(str(exc))
        final_status = "not_evaluated"
        # downstream gates remain not_run
        gate_results.extend([GateResult(g, "not_run", "") for g in GATE_SEQUENCE[1:]])
        return _build_report(inputs, as_of, gate_results, blockers, final_status, normalized=None)

    # Gate 2: CAND-004
    cand004 = normalized["quality_gate"]
    if (
        cand004["mode"] == "paper"
        and cand004["quality_state"] == "eligible_for_shadow_live_quality_review"
        and cand004["blockers"] == []
    ):
        gate_results.append(GateResult("cand004_evidence_gate", "pass", ""))
    else:
        reason = "CAND-004 quality gate is not in the required state"
        gate_results.append(GateResult("cand004_evidence_gate", "fail", reason))
        blockers.append(reason)
        final_status = "upstream_quality_blocked"
        gate_results.extend([GateResult(g, "not_run", "") for g in GATE_SEQUENCE[len(gate_results):]])
        return _build_report(inputs, as_of, gate_results, blockers, final_status, normalized)

    # Continue similarly for gates 3-9. On each failure, append the failed gate,
    # append `not_run` entries for `GATE_SEQUENCE[len(gate_results):]`, set the
    # matching failure status, and return `_build_report`.

    # After gate 9 passes, gate 10 (`envelope_synthesis_gate`) sets status to
    # `envelope_synthesized` with `exit_code=2` (recording has not happened yet).
    # Gate 11 (`artifact_recording_gate`) is handled by the writer, which promotes
    # the status to `readiness_envelope_recorded` with `exit_code=0` on success.
```

Define the input label order used for fingerprints, digests, and artifact references:

```python
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
```

`_build_report` signature and responsibilities:

```python
def _build_report(
    inputs: ReadinessEnvelopeInputs,
    as_of: str,
    gate_results: list[GateResult],
    blockers: list[str],
    status: str,
    normalized: dict[str, Any] | None,
) -> ReadinessEnvelopeReport:
    exit_code = 0 if status == "readiness_envelope_recorded" else 2
    fingerprints = _input_fingerprints(normalized) if normalized else {}
    input_digest = _compute_input_digest(as_of, fingerprints) if normalized else "sha256:" + "0" * 64
    evaluation_id = _evaluation_id(input_digest)
    envelope_digest = _compute_envelope_digest(as_of, fingerprints, normalized) if normalized else input_digest
    upstream_summaries = _build_upstream_summaries(normalized) if normalized else {}
    fixture_summaries = _build_fixture_summaries(normalized) if normalized else {}
    return ReadinessEnvelopeReport(
        artifact_type="runtime_readiness_envelope",
        schema_version="runtime-readiness-envelope.v1",
        candidate="CAND-007",
        mode="simulated_only",
        status=status,
        exit_code=exit_code,
        evaluation_id=evaluation_id,
        as_of=as_of,
        run_id=normalized["quality_gate"]["run_id"] if normalized else None,
        symbol=normalized["quality_gate"]["symbol"] if normalized else None,
        candidate_chain=("CAND-001", "CAND-002", "CAND-003", "CAND-004", "CAND-005", "CAND-006", "CAND-007"),
        gate_sequence=GATE_SEQUENCE,
        gates=tuple(gate_results),
        input_artifacts={label: _redact_path(getattr(inputs, f"{label}_path")) for label in _INPUT_LABELS},
        input_fingerprints=fingerprints,
        input_digest=input_digest,
        envelope_digest=envelope_digest,
        upstream_summaries=upstream_summaries,
        fixture_summaries=fixture_summaries,
        envelope_assertions=_envelope_assertions(normalized) if normalized else {},
        blocked_reasons=list(blockers),
        recording={"json_written": False, "markdown_written": False},
        disclaimer=EVIDENCE_ONLY_DISCLAIMER,
    )
```

Digest helper implementations:

```python
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
            "transmission_allowed": normalized["submit_conformance"]["dry_run_request"]["transmission"]["allowed"],
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
            "require_broker_capability_manifest": re_fixture["require_broker_capability_manifest"],
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
            "default_state_on_missing_runtime": ks_fixture["default_state_on_missing_runtime"],
            "default_state_on_unknown_runtime": ks_fixture["default_state_on_unknown_runtime"],
            "operator_override_allowed": ks_fixture["operator_override_allowed"],
        },
        "audit_policy": {
            "audit_required": au_fixture["audit_required"],
            "append_only_required": au_fixture["append_only_required"],
            "hash_chain_required": au_fixture["hash_chain_required"],
            "local_artifact_recording_required": au_fixture["local_artifact_recording_required"],
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
        "kill_switch_required": re_fixture["require_kill_switch_inactive"] and ks_fixture["kill_switch_required"],
        "risk_gate_required": re_fixture["require_risk_gate"],
        "audit_recording_required": re_fixture["require_audit_recording"] and au_fixture["audit_required"],
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
        "cand006_transmission_blocked": not sc["dry_run_request"]["transmission"]["allowed"],
    }
```

### Task 9: Implement gate engine

**Files:**
- Modify: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write a failing test for all-pass envelope**

```python
def test_valid_all_pass_envelope(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "envelope_synthesized"
    assert report.exit_code == 2  # recording has not happened yet
    assert all(g.status == "pass" for g in report.gates)
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_valid_all_pass_envelope -v
```

Expected: FAIL.

- [ ] **Step 2: Implement `build_runtime_readiness_envelope_report`**

Add the gate engine to the engine module, stopping at the first failed gate and recording downstream gates as `not_run`.

- [ ] **Step 3: Verify gate tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "gate or envelope" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): implement fail-closed gate engine"
```

---

## 13. Status Model

The report exposes exactly these statuses:

- `not_evaluated`
- `blocked`
- `upstream_quality_blocked`
- `shadow_evidence_blocked`
- `submit_conformance_blocked`
- `runtime_envelope_blocked`
- `broker_capability_blocked`
- `operator_policy_blocked`
- `kill_switch_policy_blocked`
- `audit_policy_blocked`
- `envelope_synthesized`
- `readiness_envelope_recorded`

`readiness_envelope_recorded` is the only status that exits `0`; all others exit `2`.

The status `envelope_synthesized` is an internal pre-recording status. The writer promotes it to `readiness_envelope_recorded` after both artifacts are atomically written.

### Task 10: Verify status model in tests

**Files:**
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Add a test that exercises each blocker status**

For each gate failure, write a test that produces the expected status and exit code. Example:

```python
def test_runtime_envelope_live_submit_enabled_blocks(tmp_path: Path) -> None:
    inputs, fixtures = _make_valid_inputs(tmp_path)
    fixtures["runtime_envelope"]["live_submit_enabled"] = True
    _write_fixture(inputs.runtime_envelope_path, fixtures["runtime_envelope"])
    report = build_runtime_readiness_envelope_report(inputs)
    assert report.status == "runtime_envelope_blocked"
    assert report.exit_code == 2
```

- [ ] **Step 2: Run status tests**

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "blocks" -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_runtime_readiness_envelope.py
git commit -m "test(cand-007): cover all blocker statuses"
```

---

## 14. Artifact Writer and Atomic Write Design

Artifacts:

- `runtime-readiness-envelope.json`
- `runtime-readiness-envelope-report.md`

JSON is authoritative. Markdown is informational.

Atomic write order:

1. Ensure output directory exists.
2. Build final JSON report dict in memory.
3. Build Markdown report string in memory.
4. Write Markdown temp file next to final path, flush, fsync.
5. Write JSON temp file next to final path, flush, fsync.
6. `os.replace(markdown_temp, runtime-readiness-envelope-report.md)`.
7. `os.replace(json_temp, runtime-readiness-envelope.json)` (JSON is the authoritative commit marker and is replaced last).
8. If both succeed, return a copy of the report with `status="readiness_envelope_recorded"`, `exit_code=0`, `recording={"json_written": true, "markdown_written": true}`.
9. If either fails, return a copy with `status="blocked"`, `exit_code=2`, and a recording blocker.

Before writing, reject path aliasing: resolve all input paths and final/temp output paths and ensure no input equals an output.

### Task 11: Implement artifact writer

**Files:**
- Modify: `src/atlas_agent/agent/runtime_readiness_envelope.py`
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Write a failing test for artifact recording**

```python
def test_write_artifacts_promotes_status(tmp_path: Path) -> None:
    from atlas_agent.agent.runtime_readiness_envelope import (
        build_runtime_readiness_envelope_report,
        write_runtime_readiness_envelope_artifacts,
    )
    inputs, _ = _make_valid_inputs(tmp_path)
    report = build_runtime_readiness_envelope_report(inputs)
    recorded = write_runtime_readiness_envelope_artifacts(report, tmp_path / "out")
    assert recorded.status == "readiness_envelope_recorded"
    assert recorded.exit_code == 0
    assert (tmp_path / "out" / "runtime-readiness-envelope.json").is_file()
    assert (tmp_path / "out" / "runtime-readiness-envelope-report.md").is_file()
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_write_artifacts_promotes_status -v
```

Expected: FAIL.

- [ ] **Step 2: Implement `_render_markdown_report` and `write_runtime_readiness_envelope_artifacts`**

Add the writer to the engine module.

- [ ] **Step 3: Verify writer tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -k "write or artifact" -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope.py tests/test_runtime_readiness_envelope.py
git commit -m "feat(cand-007): add atomic JSON/Markdown artifact writer"
```

---

## 15. JSON/Markdown Artifact Schema

### 15.1 JSON artifact

```json
{
  "artifact_type": "runtime_readiness_envelope",
  "schema_version": "runtime-readiness-envelope.v1",
  "candidate": "CAND-007",
  "mode": "simulated_only",
  "status": "readiness_envelope_recorded",
  "exit_code": 0,
  "evaluation_id": "re-<digest-prefix>",
  "as_of": "2026-06-24T10:00:00Z",
  "run_id": "run-123",
  "symbol": "AAPL",
  "candidate_chain": ["CAND-001", ..., "CAND-007"],
  "gate_sequence": [...],
  "gates": [...],
  "input_artifacts": {...},
  "input_fingerprints": {...},
  "input_digest": "sha256:...",
  "envelope_digest": "sha256:...",
  "upstream_summaries": {...},
  "fixture_summaries": {...},
  "envelope_assertions": {...},
  "blocked_reasons": [],
  "recording": {"json_written": true, "markdown_written": true},
  "disclaimer": "Runtime readiness envelope evaluation (CAND-007) — simulated only..."
}
```

### 15.2 Markdown artifact

Sections:

- Safety banner with exact disclaimer.
- Header: status, evaluation_id, as_of, symbol, run_id.
- Gate table.
- Upstream evidence summaries.
- Fixture summaries.
- Envelope assertions table.
- Blockers list.
- Disclaimer.

Must not include raw fixture contents, absolute paths, usernames, credentials, account IDs, endpoint URLs, stack traces, or raw broker/provider payloads.

### Task 12: Verify artifact schema

**Files:**
- Test: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Add schema assertions**

```python
def test_artifact_schema_contains_required_keys(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    report = build_runtime_readiness_envelope_report(inputs)
    recorded = write_runtime_readiness_envelope_artifacts(report, tmp_path / "out")
    json_path = tmp_path / "out" / "runtime-readiness-envelope.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["artifact_type"] == "runtime_readiness_envelope"
    assert data["candidate"] == "CAND-007"
    assert data["disclaimer"] == recorded.disclaimer
    assert data["envelope_digest"].startswith("sha256:")
```

- [ ] **Step 2: Run schema test**

```bash
python -m pytest tests/test_runtime_readiness_envelope.py::test_artifact_schema_contains_required_keys -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_runtime_readiness_envelope.py
git commit -m "test(cand-007): assert JSON artifact schema"
```

---

## 16. Redaction Strategy

Rules:

- Input paths stored in the report are basenames only.
- No absolute paths in artifacts or stdout/stderr.
- No usernames, home directories, or environment variables.
- No raw exception text printed by the CLI.
- No raw fixture bodies in Markdown.
- Secret-like inputs are rejected at preflight, not sanitized.

Implementation:

```python
def _redact_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return path.name
```

### Task 13: Verify redaction

**Files:**
- Test: `tests/test_runtime_readiness_envelope_cli.py`

- [ ] **Step 1: Add redaction test**

```python
def test_text_output_contains_no_absolute_paths(tmp_path: Path) -> None:
    inputs, _ = _make_valid_inputs(tmp_path)
    report = build_runtime_readiness_envelope_report(inputs)
    recorded = write_runtime_readiness_envelope_artifacts(report, tmp_path / "out")
    md = (tmp_path / "out" / "runtime-readiness-envelope-report.md").read_text(encoding="utf-8")
    assert str(tmp_path) not in md
```

- [ ] **Step 2: Run redaction test**

```bash
python -m pytest tests/test_runtime_readiness_envelope_cli.py::test_text_output_contains_no_absolute_paths -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_runtime_readiness_envelope_cli.py
git commit -m "test(cand-007): verify path redaction in artifacts"
```

---

## 17. CLI Parser Behavior and Unsafe Flag Rejection

### 17.1 CLI module

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from atlas_agent.agent.runtime_readiness_envelope import (
    ReadinessEnvelopeInputs,
    build_runtime_readiness_envelope_report,
    write_runtime_readiness_envelope_artifacts,
)

CLI_DESCRIPTION = """\
Runtime readiness envelope evaluation (CAND-007) — simulated only.

This command consumes CAND-004 trading-quality evidence, CAND-005 shadow-live
comparison evidence, CAND-006 gated submit conformance evidence, and five static
local policy fixtures. It evaluates them in strict fail-closed order and records
a runtime readiness envelope artifact if every gate passes.

This command does not submit orders, does not call broker or provider APIs, does
not load credentials, does not create real or pending orders, does not import
Order/OrderRouter/RiskManager/runtime kill switch, and does not claim live
readiness or permission to submit orders.\
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
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas agent readiness-envelope",
        description=CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--quality-gate", required=True)
    parser.add_argument("--shadow-comparison", required=True)
    parser.add_argument("--submit-conformance", required=True)
    parser.add_argument("--runtime-envelope", required=True)
    parser.add_argument("--broker-capabilities", required=True)
    parser.add_argument("--operator-policy", required=True)
    parser.add_argument("--kill-switch-policy", required=True)
    parser.add_argument("--audit-policy", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def _reject_unsafe_flags(argv: list[str] | None) -> None:
    args = argv if argv is not None else []
    for token in args:
        if token in _UNSAFE_FLAGS:
            print(f"error: unsafe flag rejected: {token}", file=sys.stderr)
            sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    _reject_unsafe_flags(argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    inputs = ReadinessEnvelopeInputs(
        quality_gate_path=Path(args.quality_gate),
        shadow_comparison_path=Path(args.shadow_comparison),
        submit_conformance_path=Path(args.submit_conformance),
        runtime_envelope_path=Path(args.runtime_envelope),
        broker_capabilities_path=Path(args.broker_capabilities),
        operator_policy_path=Path(args.operator_policy),
        kill_switch_policy_path=Path(args.kill_switch_policy),
        audit_policy_path=Path(args.audit_policy),
        output_dir=Path(args.output_dir),
        as_of=args.as_of,
    )

    try:
        report = build_runtime_readiness_envelope_report(inputs)
        if report.status == "envelope_synthesized":
            report = write_runtime_readiness_envelope_artifacts(report, inputs.output_dir)
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "not_evaluated", "error": str(exc), "exit_code": 2}, indent=2, sort_keys=True))
        else:
            print("status: not_evaluated")
            print(f"error: {exc}")
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_text_report(report)

    return report.exit_code
```

### Task 14: Implement configless CLI handler

**Files:**
- Create: `src/atlas_agent/agent/runtime_readiness_envelope_cli.py`
- Test: `tests/test_runtime_readiness_envelope_cli.py`

- [ ] **Step 1: Write a failing CLI test**

```python
def test_cli_help_contains_disclaimer() -> None:
    from atlas_agent.agent.runtime_readiness_envelope_cli import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    assert "simulated only" in help_text.lower()
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope_cli.py::test_cli_help_contains_disclaimer -v
```

Expected: FAIL.

- [ ] **Step 2: Create the CLI module**

Write `src/atlas_agent/agent/runtime_readiness_envelope_cli.py` with the parser, unsafe-flag rejection, and `main` function shown above.

- [ ] **Step 3: Verify CLI tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope_cli.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/atlas_agent/agent/runtime_readiness_envelope_cli.py tests/test_runtime_readiness_envelope_cli.py
git commit -m "feat(cand-007): add configless readiness-envelope CLI handler"
```

---

## 18. Static Checker Design

Create `scripts/check_runtime_readiness_envelope_contract.py`.

Required checks:

- Required files exist.
- `pyproject.toml` console script points to `atlas_agent.cli_bootstrap:main`.
- Bootstrap source contains exact routes `agent submit-conformance` and `agent readiness-envelope`.
- Bootstrap source does not import `atlas_agent.cli` at module import time.
- Legacy CLI source (`src/atlas_agent/cli.py`) registers a `readiness-envelope` subparser under `agent`.
- Core and CLI modules have only stdlib imports.
- `atlas_agent.agent.__init__` does not import CAND-007 modules as convenience exports.
- Core/CLI modules do not import forbidden Atlas packages:
  - `atlas_agent.brokers`
  - `atlas_agent.providers`
  - `atlas_agent.execution`
  - `atlas_agent.risk`
  - `atlas_agent.safety`
  - `atlas_agent.config`
- Core/CLI modules do not import forbidden network/credential packages:
  - `urllib`
  - `socket`
  - `requests`
  - `httpx`
  - `aiohttp`
  - `websockets`
  - `subprocess`
  - `dotenv`
  - `keyring`
- Core source contains all approved statuses in the approved order.
- Core source contains all gate IDs in order.
- Core source contains required artifact names.
- Core source enforces universal rejection rules:
  - secret-like keys/values
  - endpoint-like keys
  - URL protocols `http://`, `https://`, `ws://`, `wss://`
- Core source enforces 24-hour CAND-006 freshness rule.
- Core source enforces broker-label prefix rule (`local-`, `simulated-`, `fixture-`, `redacted-`).
- Core source enforces output-path aliasing protection.
- Source contains the exact evidence-only disclaimer constant.
- Docs contain the evidence-only disclaimer.
- Docs do not contain affirmative live-readiness/profit or implied safety claims.
- Stale-doc prevention: docs no longer say CAND-007 is future/unimplemented.

Support `--json`. Exit `0` on pass, `2` on findings.

### Task 15: Implement static checker

**Files:**
- Create: `scripts/check_runtime_readiness_envelope_contract.py`
- Test: `tests/test_runtime_readiness_envelope_contract.py`

- [ ] **Step 1: Write a failing test that runs the checker**

```python
def test_contract_checker_passes() -> None:
    import subprocess
    result = subprocess.run(
        ["python", "scripts/check_runtime_readiness_envelope_contract.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope_contract.py::test_contract_checker_passes -v
```

Expected: FAIL.

- [ ] **Step 2: Implement the static checker**

Create `scripts/check_runtime_readiness_envelope_contract.py` modeled on `scripts/check_gated_submit_conformance_contract.py`, with the additional CAND-007-specific checks above.

- [ ] **Step 3: Verify checker passes**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope_contract.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/check_runtime_readiness_envelope_contract.py tests/test_runtime_readiness_envelope_contract.py
git commit -m "feat(cand-007): add static contract checker"
```

---

## 19. Runtime Import-Trace Test Design

Create `tests/test_runtime_readiness_envelope_import_trace.py`.

Use subprocesses so each test starts with a clean module graph. The subprocess code imports `atlas_agent.cli_bootstrap.main`, runs the command, then emits sorted `sys.modules`.

Configless positive route:

- Build minimal valid fixtures in a temp directory.
- Call `main(["agent", "readiness-envelope", ...])`.
- Assert return code `0`.
- Assert forbidden modules are absent.

Runtime import-trace hard-fail list:

- `atlas_agent.brokers`
- `atlas_agent.providers`
- `atlas_agent.execution`
- `atlas_agent.risk`
- `atlas_agent.safety`
- `atlas_agent.config`
- `requests`
- `httpx`
- `aiohttp`
- `websockets`
- `socket`
- `openai`
- `anthropic`

Delegation tests:

- `main(["--help"])` delegates to legacy CLI and may import `atlas_agent.cli`.
- `main(["validate"])` delegates to legacy CLI.
- `main(["--workspace", "X", "agent", "readiness-envelope", ...])` delegates to legacy CLI.
- `main(["agent", "readiness-envelope-extra"])` delegates to legacy CLI.
- `main(["agent", "submit-conformance", ...])` still uses the CAND-006 configless path.

Explicit test names to include:

- `test_forbidden_modules_not_imported_on_any_configless_route`
- `test_legacy_cli_delegation_with_workspace`
- `test_cand006_configless_route_still_isolated`

### Task 16: Implement import-trace tests

**Files:**
- Create: `tests/test_runtime_readiness_envelope_import_trace.py`

- [ ] **Step 1: Write a failing import-trace test**

```python
def test_configless_route_avoids_forbidden_modules(tmp_path: Path) -> None:
    script = _build_import_trace_script(tmp_path)
    result = subprocess.run(
        ["python", str(script), "configless", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    modules = json.loads(result.stdout)
    for forbidden in ("atlas_agent.brokers", "atlas_agent.providers", "atlas_agent.risk"):
        assert forbidden not in modules, f"{forbidden} was imported"
```

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope_import_trace.py::test_configless_route_avoids_forbidden_modules -v
```

Expected: FAIL.

- [ ] **Step 2: Implement the import-trace test module**

Create `tests/test_runtime_readiness_envelope_import_trace.py` with subprocess helpers that generate fixtures, invoke the bootstrap, and assert module absence.

- [ ] **Step 3: Verify import-trace tests pass**

Run:

```bash
python -m pytest tests/test_runtime_readiness_envelope_import_trace.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_runtime_readiness_envelope_import_trace.py
git commit -m "test(cand-007): add runtime import-trace boundary tests"
```

---

## 20. Feature Tests

Engine tests in `tests/test_runtime_readiness_envelope.py` must cover:

- `test_valid_all_pass_envelope`
- `test_missing_quality_gate_blocks`
- `test_blocked_quality_gate_blocks`
- `test_missing_shadow_comparison_blocks`
- `test_shadow_comparison_minor_divergence_blocks`
- `test_missing_submit_conformance_blocks`
- `test_submit_conformance_not_recorded_blocks`
- `test_submit_conformance_transmission_enabled_blocks`
- `test_submit_conformance_stale_evidence_blocks`
- `test_runtime_envelope_live_submit_enabled_true_blocks`
- `test_runtime_envelope_empty_supported_order_types_blocks`
- `test_runtime_envelope_empty_supported_time_in_force_blocks`
- `test_broker_capability_credentials_present_true_blocks`
- `test_broker_capability_endpoint_present_true_blocks`
- `test_broker_label_prefix_enforced`
- `test_operator_policy_symbol_allow_and_block`
- `test_operator_policy_unattended_allowed_blocks`
- `test_kill_switch_policy_default_unknown_not_blocked_blocks`
- `test_audit_policy_hash_chain_not_required_blocks`
- `test_fixture_expiry_blocks`
- `test_unknown_fixture_fields_rejected`
- `test_secret_like_fields_rejected`
- `test_url_protocol_fields_rejected`
- `test_run_id_mismatch_blocks`
- `test_symbol_mismatch_blocks`
- `test_json_and_markdown_agree`
- `test_json_write_failure_rolls_back_status`
- `test_disclaimer_present_in_json_and_markdown`
- `test_output_path_alias_rejected`

Use a shared `_make_valid_inputs(tmp_path)` helper that writes all eight input files and returns `ReadinessEnvelopeInputs` plus a fixtures dict.

### Task 17: Expand engine feature tests

**Files:**
- Modify: `tests/test_runtime_readiness_envelope.py`

- [ ] **Step 1: Add remaining feature tests**

For each required test, mutate the relevant fixture, rebuild the report, and assert the expected status and exit code.

- [ ] **Step 2: Run all engine tests**

```bash
python -m pytest tests/test_runtime_readiness_envelope.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_runtime_readiness_envelope.py
git commit -m "test(cand-007): expand engine feature tests"
```

---

## 21. CLI Tests

CLI tests in `tests/test_runtime_readiness_envelope_cli.py` must cover:

- `--help` returns `0` and contains the safety disclaimer.
- `--json` emits valid JSON with `status == "readiness_envelope_recorded"` on success.
- Missing required flag returns exit code `2`.
- Each unsafe flag returns exit code `2`.
- Valid fixture set writes both artifacts and exits `0`.
- Unknown fixture fields are rejected.
- Output contains no absolute temp paths or secret-like values.
- Bootstrap delegates `validate`, `--help`, and unknown commands unchanged.
- Delegated commands receive argv unchanged.

### Task 18: Expand CLI tests

**Files:**
- Modify: `tests/test_runtime_readiness_envelope_cli.py`

- [ ] **Step 1: Add unsafe-flag and delegation tests**

```python
@pytest.mark.parametrize("flag", [
    "--live", "--submit", "--broker", "--provider", "--api-key",
    "--credentials", "--endpoint", "--account", "--account-id",
    "--client-order-id", "--place-order", "--order-router", "--risk-manager",
    "--mode", "--kill-switch-override",
])
def test_unsafe_flag_rejected(flag: str) -> None:
    from atlas_agent.agent.runtime_readiness_envelope_cli import main
    code = main([flag])
    assert code == 2
```

- [ ] **Step 2: Run all CLI tests**

```bash
python -m pytest tests/test_runtime_readiness_envelope_cli.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_runtime_readiness_envelope_cli.py
git commit -m "test(cand-007): expand CLI tests including unsafe flags"
```

---

## 22. Regression Tests

Add targeted regressions:

- `tests/test_cli.py::test_python_module_help_works` still passes.
- `tests/test_cli_smoke.py` still uses legacy `atlas_agent.cli.main` unaffected.
- `tests/test_cli_command_compatibility.py` passes with the new bootstrap-only exception.
- `tests/test_package_distribution_check.py` passes.
- `tests/test_autonomous_paper_quality.py` still passes.
- `tests/test_shadow_live_readonly.py` still passes.
- `tests/test_gated_submit_conformance.py` and its CLI/import-trace/contract tests still pass.
- No convenience imports are added to `atlas_agent.agent.__init__`.
- `atlas run --mode live` remains fail-closed unless fully configured.

### Task 19: Run regression suite

**Files:**
- Test: existing suite

- [ ] **Step 1: Run focused regression tests**

```bash
python -m pytest tests/test_cli_command_compatibility.py tests/test_package_distribution_check.py tests/test_autonomous_paper_quality.py tests/test_shadow_live_readonly.py tests/test_gated_submit_conformance.py tests/test_gated_submit_conformance_cli.py tests/test_gated_submit_conformance_import_trace.py tests/test_gated_submit_conformance_contract.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full pytest suite**

```bash
python -m pytest -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git commit -m "test(cand-007): confirm regression suite passes" --allow-empty
```

---

## 23. Docs/Release Metadata Updates

### 23.1 New user-facing doc

Create `docs/runtime-readiness-envelope.md` with:

- Command name and example invocation.
- Required inputs.
- Produced artifacts.
- Safety disclaimer.
- Exit codes.
- Description of the 11 gates.
- Description of statuses.
- Note that `readiness_envelope_recorded` is evidence-recording status only.

### 23.2 Release metadata updates

- `docs/releases/v0.6.16-plan.md`: add CAND-007 row.
- `docs/releases/v0.6.16-candidates.md`: add CAND-007 implemented entry.
- `docs/releases/v0.6.16-candidate-selection.md`: add "Why CAND-007 is eligible".
- `docs/releases/v0.6.16-candidates.json`: add CAND-007 candidate object with `status: "implemented"`.
- `CHANGELOG.md`: add CAND-007 under `[Unreleased]`.
- `docs/autonomy-roadmap.md`: mark CAND-007 implemented.
- `docs/bounded-live-autonomy-governance.md`: update staged-autonomy posture.
- `docs/shadow-live-readiness-contract.md`: reference CAND-007.
- `docs/gated-submit-conformance.md`: forward reference to CAND-007.
- `docs/architecture.md`: document second bootstrap-only route.
- `docs/cli-command-compatibility.md`: document second bootstrap-only command exception.

### 23.3 Scripts

- `scripts/dev_check.sh`: run CAND-007 checker and tests.
- `scripts/release_check.sh`: run CAND-007 checker and tests.

### Task 20: Update docs and release metadata

**Files:**
- Create: `docs/runtime-readiness-envelope.md`
- Modify: `docs/releases/v0.6.16-plan.md`, `docs/releases/v0.6.16-candidates.md`, `docs/releases/v0.6.16-candidate-selection.md`, `docs/releases/v0.6.16-candidates.json`, `CHANGELOG.md`, `docs/autonomy-roadmap.md`, `docs/bounded-live-autonomy-governance.md`, `docs/shadow-live-readiness-contract.md`, `docs/gated-submit-conformance.md`, `docs/architecture.md`, `docs/cli-command-compatibility.md`, `scripts/dev_check.sh`, `scripts/release_check.sh`

- [ ] **Step 1: Create user-facing doc**

Write `docs/runtime-readiness-envelope.md`.

- [ ] **Step 2: Update release metadata**

Add CAND-007 to the JSON and Markdown release files. No version bump, tag, release, or PyPI claim.

- [ ] **Step 3: Update validation scripts**

Append the CAND-007 checker and focused tests to `scripts/dev_check.sh` and `scripts/release_check.sh`.

- [ ] **Step 4: Run contract checker**

```bash
python scripts/check_runtime_readiness_envelope_contract.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs scripts CHANGELOG.md
git commit -m "docs(cand-007): add user docs and release metadata"
```

---

## 24. Validation Command List

### 24.1 Focused validation

```bash
python3.11 -m compileall src scripts
python3.11 scripts/check_runtime_readiness_envelope_contract.py
python3.11 scripts/check_runtime_readiness_envelope_contract.py --json
python3.11 -m pytest tests/test_runtime_readiness_envelope.py tests/test_runtime_readiness_envelope_cli.py tests/test_runtime_readiness_envelope_contract.py tests/test_runtime_readiness_envelope_import_trace.py -q
python3.11 -m pytest tests/test_cli_command_compatibility.py tests/test_package_distribution_check.py -q
python3.11 -m pytest tests/test_autonomous_paper_quality.py tests/test_shadow_live_readonly.py tests/test_gated_submit_conformance.py tests/test_gated_submit_conformance_cli.py tests/test_gated_submit_conformance_import_trace.py tests/test_gated_submit_conformance_contract.py -q
git diff --check
```

### 24.2 Required repo checks

```bash
pytest
pip check
atlas validate
atlas config set market.symbol AAPL
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
atlas run --mode paper
atlas run --mode live
```

`atlas run --mode live` should fail safely unless explicit live config, credentials, risk checks, and approval are present.

### Task 21: Run full validation

- [ ] **Step 1: Run focused validation commands**

```bash
python -m compileall src scripts
python scripts/check_runtime_readiness_envelope_contract.py
python -m pytest tests/test_runtime_readiness_envelope.py tests/test_runtime_readiness_envelope_cli.py tests/test_runtime_readiness_envelope_contract.py tests/test_runtime_readiness_envelope_import_trace.py -q
```

Expected: all pass.

- [ ] **Step 2: Run required repo checks**

```bash
pytest
pip check
atlas validate
atlas config set market.symbol AAPL
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
atlas run --mode paper
atlas run --mode live
```

Expected: `atlas run --mode live` fails safely.

- [ ] **Step 3: Final commit**

```bash
git commit -m "chore(cand-007): complete validation and release metadata" --allow-empty
```

---

## 25. Commit Plan

Commit 1: Bootstrap route.

- Modify `src/atlas_agent/cli_bootstrap.py`.
- Add initial import-trace delegation test.

Commit 2: Core engine scaffold and helpers.

- Add `src/atlas_agent/agent/runtime_readiness_envelope.py` constants, dataclasses, canonicalization, and timestamp helpers.

Commit 3: Projection validators.

- Add CAND-004/005/006 projection validators.

Commit 4: Closed-schema fixture validators.

- Add validators for the five CAND-007-owned fixtures.

Commit 5: Universal rejection scanner.

- Add secret/endpoint/URL scanner.

Commit 6: Gate engine.

- Add fail-closed gate sequence and report builder.

Commit 7: Artifact writer.

- Add atomic JSON/Markdown writer.

Commit 8: CLI handler.

- Add `src/atlas_agent/agent/runtime_readiness_envelope_cli.py`.

Commit 9: Engine, CLI, and import-trace tests.

- Add and expand all test modules.

Commit 10: Static checker.

- Add `scripts/check_runtime_readiness_envelope_contract.py`.

Commit 11: Docs and release metadata.

- Add user-facing doc and update release files.

Commit 12: Validation and wiring.

- Wire into dev/release check scripts and run validation.

---

## 26. Known Risks and Mitigations

| Risk | Mitigation |
|---|---|
| CAND-007 route imports legacy CLI and therefore brokers/config/risk. | Narrow bootstrap pre-router, import-trace tests, static checker. |
| Pre-router becomes a broad configless CLI refactor. | Exact two-token match only; all other commands delegate unchanged. |
| `atlas --workspace X agent readiness-envelope` bypasses config loading. | Pre-router only checks first two argv tokens. |
| Existing command behavior changes after CAND-007 route added. | Delegation regression tests for `--help`, `validate`, and legacy command smoke paths. |
| "Readiness envelope" mistaken for live readiness. | Full command name and status carry "No Live Submit" framing; disclaimer in every artifact and doc. |
| Broker capability manifest mistaken for broker certification. | `broker_label` prefix rule; `sandbox_only: true`; `live_api_contact_allowed: false`; docs state it is a static fixture. |
| Operator policy fixture mistaken for real approval. | Named `operator_policy_fixture`; `approval_scope` is `candidate_only` or `simulated_only`; docs state it is not real human approval. |
| Audit policy mistaken for live audit-chain proof. | `live_audit_chain_claimed: false`; CAND-007 writes local artifacts only. |
| Stale CAND-006 evidence accepted. | 24-hour freshness rule enforced in projection validator and gate. |
| Fixtures becoming too close to runtime config. | Keep fields static/declarative; no hooks, env vars, shell commands, free-form metadata. |
| Unsafe CLI flags sneaking in. | Explicit deny-list at parse time with exit code 2. |
| Partial artifact writes claim success. | JSON is the only authoritative commit marker; JSON write failure exits 2 and never reports `readiness_envelope_recorded`. |
| Markdown consumed as authoritative evidence. | Docs and tests state consumers must ignore Markdown without matching JSON `evaluation_id`. |
| Secret/path leakage in artifacts. | Reject secret-like inputs, basename-only artifact references, and redaction tests. |
| Runtime import-trace tests flaky due to incidental stdlib imports. | Hard-fail only on Atlas forbidden modules and non-stdlib network libraries at runtime; keep direct source import of `urllib` forbidden by the static checker. |
| CAND-007 doc left as "future" after implementation. | Static checker stale-doc prevention plus manual review before final commit. |

---

## Self-Review Checklist

**Spec coverage:**

- [ ] 26 required implementation plan sections are present.
- [ ] All 12 required statuses are defined and tested.
- [ ] All 11 gates are defined in order with first-failure halt.
- [ ] Projection validation for CAND-004/CAND-005/CAND-006 is covered.
- [ ] Closed-schema validation for five CAND-007-owned fixtures is covered.
- [ ] Universal rejection rules (secrets, endpoints, URLs) are covered.
- [ ] 24-hour CAND-006 freshness rule is covered.
- [ ] Broker-label prefix rule is covered.
- [ ] Output-path aliasing protection is covered.
- [ ] Unsafe CLI flag list includes all 15 flags.
- [ ] Artifact disclaimer is present in source, JSON, Markdown, and docs.
- [ ] Bootstrap routing rules are covered.
- [ ] Static checker design covers all required checks.
- [ ] Tests cover the full required list.
- [ ] Docs/release metadata updates are covered.
- [ ] Validation commands are listed.
- [ ] Commit plan is present.
- [ ] Known risks and mitigations are present.

**Placeholder scan:**

- [ ] No "TBD", "TODO", "implement later", or "fill in details".
- [ ] No "add appropriate error handling" without concrete code.
- [ ] No "similar to Task N" shortcuts.
- [ ] Every code step includes actual code.

**Type consistency:**

- [ ] `ReadinessEnvelopeInputs` field names match CLI argument names.
- [ ] `GateResult` fields match CAND-006 `GateResult` shape for reuse of rendering logic if copied.
- [ ] Status strings match `APPROVED_FINAL_STATUSES` exactly.
- [ ] Artifact names `_JSON_ARTIFACT_NAME` and `_MARKDOWN_ARTIFACT_NAME` are used consistently.

If any box is unchecked, add the missing task and re-scan before execution.
