# CAND-006 Gated Submit Conformance Rehearsal Implementation Plan

> **Candidate:** CAND-006  
> **Approved CLI:** `atlas agent submit-conformance`  
> **Scope:** deterministic, local-only, fixture-driven, simulated-only submit
> conformance rehearsal.  
> **Implementation status:** approved plan, not implemented by this document.

## Goal

Implement `atlas agent submit-conformance` as a deterministic, local-only,
fixture-driven conformance rehearsal.

The command consumes:

- CAND-004 trading-quality evidence.
- CAND-005 shadow-live comparison evidence.
- A hypothetical order intent fixture.
- A simulated kill-switch fixture.
- A simulated `RiskManager`-shaped risk envelope fixture.
- A simulated approval fixture.

It evaluates those inputs in strict fail-closed order and records a
non-transmittable dry-run submit request only if every gate passes.

## Non-Goals And Hard Boundaries

CAND-006 must not:

- Enable live trading.
- Submit orders.
- Create real orders.
- Create pending orders.
- Call brokers.
- Call providers.
- Load credentials.
- Load Atlas config for this route.
- Call the network.
- Instantiate `Order`.
- Import or invoke `OrderRouter`.
- Import or invoke `RiskManager`.
- Import runtime kill switch code.
- Mutate runtime state.
- Claim live readiness.

The output is a conformance rehearsal artifact only. It is not approval for live
trading, not proof of a real human approval, and not permission to submit orders.

## Required Implementation Order

Implement in this order:

1. Core stdlib-only engine.
2. Configless CLI handler.
3. Bootstrap pre-router.
4. Tests for core and CLI.
5. Runtime import-trace tests.
6. Static checker.
7. Docs and metadata.
8. Full release/dev validation.

Do not start by modifying the legacy CLI parser. The bootstrap pre-router is a
P0 safety boundary.

## Assumptions

- `atlas` currently resolves through the console entry point in `pyproject.toml`;
  CAND-006 will move that public console entry point to a narrow bootstrap
  module.
- `python -m atlas_agent.cli ...` remains the legacy CLI path and does not need
  to support `agent submit-conformance`.
- CAND-004 must have `quality_state ==
  "eligible_for_shadow_live_quality_review"`.
- CAND-005 must have `status == "matched"`.
- `minor_divergence` is deliberately blocked by CAND-006 even though CAND-005
  treats it as reviewable.
- `--as-of` is required for deterministic approval expiry evaluation.
- CAND-006 v1 has no user policy file. It uses fixed conservative rules:
  CAND-005 status must be exactly `matched`, all fixture gates are required, all
  freshness checks are required, and only `dry_run_recorded` exits `0`.

## 1. Files To Add

- `src/atlas_agent/cli_bootstrap.py`
- `src/atlas_agent/agent/gated_submit_conformance.py`
- `src/atlas_agent/agent/gated_submit_conformance_cli.py`
- `docs/gated-submit-conformance.md`
- `scripts/check_gated_submit_conformance_contract.py`
- `tests/test_gated_submit_conformance.py`
- `tests/test_gated_submit_conformance_cli.py`
- `tests/test_gated_submit_conformance_contract.py`
- `tests/test_gated_submit_conformance_import_trace.py`

Test fixture helpers may live inside the test modules. Do not add checked-in
sample secrets or checked-in broker/account fixtures.

## 2. Files To Modify

- `pyproject.toml`
  - Change the console script from `atlas_agent.cli:main` to
    `atlas_agent.cli_bootstrap:main`.
- `tests/test_package_distribution_check.py`
  - Update fake wheel entry point strings when exact entry point text is tested.
- `docs/architecture.md`
  - Document `atlas_agent.cli_bootstrap:main` as the public console entry point
    and `atlas_agent.cli:main` as the delegated legacy CLI.
- `docs/cli-command-compatibility.md`
  - Document the bootstrap-only command exception.
- `scripts/check_cli_command_compatibility.py`
  - Add support for a `bootstrap_only_commands` contract section.
- `tests/fixtures/cli_command_contract.json`
  - Add `"bootstrap_only_commands": ["agent submit-conformance"]`.
- `tests/test_cli_command_compatibility.py`
  - Validate bootstrap-only commands separately from legacy parser commands.
- `docs/shadow-live-readiness-contract.md`
- `docs/bounded-live-autonomy-governance.md`
- `docs/autonomy-roadmap.md`
- `docs/releases/v0.6.16-candidates.md`
- `docs/releases/v0.6.16-candidates.json`
- `docs/releases/v0.6.16-candidate-selection.md`
- `docs/releases/v0.6.16-plan.md`
- `CHANGELOG.md`
- `scripts/dev_check.sh`
- `scripts/release_check.sh`

Do not modify `src/atlas_agent/cli.py` for this route.

## 3. Public API Design

In `src/atlas_agent/agent/gated_submit_conformance.py`, expose stdlib-only APIs:

- `APPROVED_FINAL_STATUSES`
- `GATE_SEQUENCE`
- `SubmitConformanceInputs`
- `GateResult`
- `DryRunSubmitRequest`
- `SubmitConformanceReport`
- `canonical_json_bytes(value: Any) -> bytes`
- `fingerprint_json(value: Any) -> str`
- `parse_as_of_utc(value: str) -> str`
- `build_gated_submit_conformance_report(inputs: SubmitConformanceInputs) -> SubmitConformanceReport`
- `write_gated_submit_conformance_artifacts(report: SubmitConformanceReport, output_dir: str | Path) -> SubmitConformanceReport`

In `src/atlas_agent/agent/gated_submit_conformance_cli.py`, expose:

- `build_parser() -> argparse.ArgumentParser`
- `main(argv: list[str] | None = None) -> int`

Allowed imports in CAND-006 runtime modules:

- `argparse`
- `dataclasses`
- `hashlib`
- `json`
- `math`
- `os`
- `re`
- `tempfile`
- `decimal`
- `datetime` only for parsing supplied `--as-of` and fixture timestamps
- `pathlib`
- `typing`

No CAND-006 code may call `datetime.now()`, `date.today()`, `time.time()`, or
equivalent wall-clock APIs for gate decisions.

## 4. CLI Bootstrap / Pre-Router Design

Create `src/atlas_agent/cli_bootstrap.py`.

Module-level imports allowed only:

- `sys`
- stdlib typing primitives if needed

The bootstrap must be a narrow pre-router for exactly:

```text
atlas agent submit-conformance
```

Required behavior:

```python
def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "agent" and args[1] == "submit-conformance":
        from atlas_agent.agent.gated_submit_conformance_cli import main as route_main
        return route_main(args[2:])
    from atlas_agent.cli import main as legacy_main
    return legacy_main(args)
```

Do not route any other command through the configless path.

Explicit examples:

- Route configlessly: `atlas agent submit-conformance ...`
- Route configlessly: `atlas agent submit-conformance --help`
- Delegate unchanged: `atlas --help`
- Delegate unchanged: `atlas validate`
- Delegate unchanged: `atlas agent shadow-live ...`
- Delegate unchanged: `atlas --workspace X agent submit-conformance ...`
- Delegate unchanged: `atlas agent submit-conformance-extra ...`

Do not refactor the full CLI.

## CLI Design

Approved command:

```bash
atlas agent submit-conformance \
  --quality-gate <trading-quality-gate.json> \
  --shadow-comparison <shadow-live-comparison.json> \
  --order-intent <order-intent.json> \
  --kill-switch <kill-switch.json> \
  --risk-envelope <risk-envelope.json> \
  --approval <approval.json> \
  --output-dir <dir> \
  --as-of <ISO-8601 UTC timestamp> \
  [--json]
```

Required options:

- `--quality-gate`
- `--shadow-comparison`
- `--order-intent`
- `--kill-switch`
- `--risk-envelope`
- `--approval`
- `--output-dir`
- `--as-of`

Optional options:

- `--json`

CAND-006 v1 intentionally has no user policy file. `--policy` must not be
registered and must be rejected by argparse.

## 5. Dataclass / Schema Design

Approved final statuses:

- `not_evaluated`
- `blocked`
- `approval_required`
- `risk_blocked`
- `kill_switch_blocked`
- `shadow_divergence_blocked`
- `dry_run_ready`
- `dry_run_recorded`

Only `dry_run_recorded` exits `0`. Every other final status exits `2`.

Gate IDs, in required order:

1. `schema_preflight`
2. `cand004_quality_gate`
3. `cand005_shadow_live_comparison`
4. `kill_switch_fixture`
5. `risk_envelope_fixture`
6. `approval_fixture`
7. `dry_run_conversion`
8. `atomic_artifact_recording`

`GateResult` fields:

- `gate_id: str`
- `status: Literal["pass", "fail", "not_run"]`
- `reason: str`
- `details: dict[str, Any]`

`SubmitConformanceInputs` fields:

- `quality_gate_path: Path`
- `shadow_comparison_path: Path`
- `order_intent_path: Path`
- `kill_switch_path: Path`
- `risk_envelope_path: Path`
- `approval_path: Path`
- `output_dir: Path | None`
- `as_of: str`

There is no `SubmitConformanceInputs.policy` field in CAND-006 v1. Do not add
`--policy`, policy-file parsing, or policy-file dataclasses in the first
implementation.

`SubmitConformanceReport` top-level schema:

```json
{
  "artifact_type": "gated_submit_conformance",
  "schema_version": "gated-submit-conformance.v1",
  "candidate": "CAND-006",
  "mode": "simulated_only",
  "evaluation_id": "gsc-...",
  "as_of": "2026-06-23T12:00:00Z",
  "input_digest": "sha256:...",
  "status": "dry_run_recorded",
  "exit_code": 0,
  "gate_sequence": [],
  "gates": [],
  "input_artifacts": {},
  "input_fingerprints": {},
  "run_id": null,
  "intent_id": null,
  "symbol": null,
  "quality_gate_summary": {},
  "shadow_live_summary": {},
  "kill_switch_summary": {},
  "risk_summary": {},
  "approval_summary": {},
  "dry_run_request": null,
  "dry_run_request_fingerprint": null,
  "safety_assertions": {},
  "recording": {},
  "blockers": [],
  "disclaimer": "Simulated-only conformance rehearsal. Not live readiness and not permission to submit orders."
}
```

The final JSON must include:

- `evaluation_id`
- `input_digest`
- `dry_run_request_fingerprint` if a dry-run request is present
- `as_of`

## Closed Fixture Schemas

Every fixture schema below is closed:

- Unknown fields are rejected.
- Unsupported `schema_version` values are rejected.
- Secret-like keys are rejected at every nesting level.
- JSON objects are required where objects are specified.
- Numeric fixture fields called out as decimals must be JSON strings, not JSON
  numbers.
- Timestamps must pass the timestamp normalization rules in this plan.

### `gated_submit_order_intent`

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `intent_kind`
- `intent_id`
- `run_id`
- `symbol`
- `side`
- `quantity`
- `order_type`
- `limit_price`
- `time_in_force`
- `created_at`

Required keys:

- Always required: `artifact_type`, `schema_version`, `intent_kind`,
  `intent_id`, `run_id`, `symbol`, `side`, `quantity`, `order_type`,
  `time_in_force`, `created_at`.
- Required only for limit orders: `limit_price`.

Optional keys:

- `limit_price` only when `order_type == "limit"`.

Exact types:

- All fields are strings.
- `quantity` and `limit_price` are decimal strings, not JSON numbers.

Rules:

- `artifact_type == "gated_submit_order_intent"`.
- `schema_version == "gated-submit-order-intent.v1"`.
- `intent_kind in {"paper_proposal", "hypothetical"}`.
- `side in {"buy", "sell"}`.
- `order_type in {"market", "limit"}`.
- `time_in_force == "day"`.
- `quantity` is a positive canonical decimal string.
- `limit_price` is a positive canonical decimal string for limit orders.
- `limit_price` must be absent for market orders.
- `created_at` must be ISO-8601 UTC.
- `symbol` must be uppercase-like, bounded to 1-24 characters, and match
  `^[A-Z0-9][A-Z0-9._-]{0,23}$`.
- `intent_id` and `run_id` must be non-empty bounded strings, 1-128 characters,
  matching `^[A-Za-z0-9_.:-]+$`.
- Unknown fields are rejected.

Explicitly prohibited keys:

- `account`
- `account_id`
- `broker`
- `broker_id`
- `provider`
- `endpoint`
- `api_key`
- `token`
- `secret`
- `credential`
- `client_order_id`
- `broker_order_id`
- `leverage`
- `metadata`
- `headers`
- `auth`

### `gated_submit_kill_switch_fixture`

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `fixture_mode`
- `scope`
- `state`
- `captured_at`
- `expires_at`

Required keys:

- All allowed keys are required.

Optional keys:

- None.

Exact types:

- All fields are strings.

Rules:

- `artifact_type == "gated_submit_kill_switch_fixture"`.
- `schema_version == "gated-submit-kill-switch.v1"`.
- `fixture_mode == "simulated"`.
- `scope == "conformance_rehearsal_only"`.
- `state in {"inactive", "active", "unknown"}`.
- `captured_at` and `expires_at` must be ISO-8601 UTC.
- `expires_at >= as_of` is required for pass.
- `state == "inactive"` is required for pass.
- Unknown fields are rejected.

### `gated_submit_risk_envelope_fixture`

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `fixture_mode`
- `represents`
- `evaluation_mode`
- `intent_fingerprint`
- `captured_at`
- `expires_at`
- `decision`
- `evaluated_price`
- `evaluated_notional`
- `checks`
- `violations`
- `limits_digest`
- `portfolio_snapshot_digest`

Required keys:

- All allowed keys are required.

Optional keys:

- None.

Exact types:

- `artifact_type`, `schema_version`, `fixture_mode`, `represents`,
  `evaluation_mode`, `intent_fingerprint`, `captured_at`, `expires_at`,
  `decision`, `evaluated_price`, `evaluated_notional`, `limits_digest`, and
  `portfolio_snapshot_digest` are strings.
- `checks` is a JSON list of objects.
- Each check object's `rule` is a string.
- Each check object's `passed` is a boolean.
- `violations` is a JSON list.

Rules:

- `artifact_type == "gated_submit_risk_envelope_fixture"`.
- `schema_version == "gated-submit-risk-envelope.v1"`.
- `fixture_mode == "simulated"`.
- `represents == "RiskManager_evaluation"`.
- `evaluation_mode == "paper"`.
- `intent_fingerprint` must equal the actual order intent fingerprint.
- `decision in {"allowed", "blocked", "requires_approval"}`.
- `decision == "allowed"` is required for pass.
- Do not accept `requires_approval` as a risk pass.
- `evaluated_price` is a positive canonical decimal string.
- `evaluated_notional` is a non-negative canonical decimal string.
- `checks` is a non-empty list.
- Every check object has exactly `{"rule", "passed"}`.
- Every `check.rule` is a non-empty bounded string, 1-128 characters.
- Every `check.passed` must be `true` for pass.
- `violations` must be `[]`.
- `captured_at` and `expires_at` must be ISO-8601 UTC.
- `expires_at >= as_of` is required for pass.
- `limits_digest` and `portfolio_snapshot_digest` must start with `sha256:`.
- Unknown fields are rejected.

### `gated_submit_approval_fixture`

Allowed keys exactly:

- `artifact_type`
- `schema_version`
- `fixture_mode`
- `scope`
- `fixture_id`
- `intent_fingerprint`
- `risk_envelope_fingerprint`
- `decision`
- `actor_label`
- `approved_at`
- `expires_at`

Required keys:

- Always required: `artifact_type`, `schema_version`, `fixture_mode`, `scope`,
  `fixture_id`, `intent_fingerprint`, `risk_envelope_fingerprint`, `decision`,
  `approved_at`, `expires_at`.

Optional keys:

- `actor_label`.

Exact types:

- All fields are strings.
- `actor_label`, when present, is a string.

Rules:

- `artifact_type == "gated_submit_approval_fixture"`.
- `schema_version == "gated-submit-approval-fixture.v1"`.
- `fixture_mode == "simulated"`.
- `scope == "conformance_rehearsal_only"`.
- `fixture_id` is a non-empty bounded string, 1-128 characters, matching
  `^[A-Za-z0-9_.:-]+$`.
- `intent_fingerprint` must equal the actual order intent fingerprint.
- `risk_envelope_fingerprint` must equal the actual risk envelope fingerprint.
- `decision in {"approved", "denied"}`.
- `decision == "approved"` is required for pass.
- `actor_label` is optional, bounded, simulated-only, and never real identity
  proof.
- Allowed `actor_label` examples: `simulated-reviewer`, `fixture-approver`,
  `conformance-approval-fixture`.
- `approved_at` and `expires_at` must be ISO-8601 UTC.
- `expires_at >= as_of` is required for pass.
- Unknown fields are rejected.

### CAND-004 `trading_quality_gate` Minimal Accepted Fields

Accepted fields:

- `artifact_type`
- `schema_version`
- `mode`
- `run_id`
- `symbol`
- `quality_state`
- `blockers`

Exact types:

- `artifact_type`, `mode`, `run_id`, `symbol`, and `quality_state` are strings.
- `schema_version` is one of the supported string or integer values.
- `blockers` is a JSON list and must be empty for pass.

Rules:

- The source artifact is secret-scanned as a full object.
- CAND-006 then projects the exact accepted keys above into a closed validation
  object. Unknown keys in the projected validation object are rejected.
- Unsupported `schema_version` values are rejected.
- `artifact_type == "trading_quality_gate"`.
- `schema_version` must be in the supported set from CAND-005:
  `{"trading-quality-gate.v1", "1", 1}`.
- `mode == "paper"`.
- `quality_state == "eligible_for_shadow_live_quality_review"`.
- `blockers == []`.
- `run_id` and `symbol` must match CAND-005 and order intent.

### CAND-005 `shadow_live_comparison` Minimal Accepted Fields

Accepted fields:

- `artifact_type`
- `schema_version`
- `run_id`
- `symbol`
- `quality_state`
- `status`
- `freshness_assessment`
- `blockers`

Exact types:

- `artifact_type`, `schema_version`, `run_id`, `symbol`, `quality_state`, and
  `status` are strings.
- `freshness_assessment` is a JSON object.
- `blockers` is a JSON list and must be empty for pass.

Rules:

- The source artifact is secret-scanned as a full object.
- CAND-006 then projects the exact accepted keys above into a closed validation
  object. Unknown keys in the projected validation object are rejected.
- Unsupported `schema_version` values are rejected.
- `artifact_type == "shadow_live_comparison"`.
- `schema_version == "shadow-live-comparison.v1"`.
- `quality_state == "eligible_for_shadow_live_quality_review"`.
- `status == "matched"`.
- `minor_divergence` must block with `shadow_divergence_blocked`.
- `blockers == []`.
- `run_id` and `symbol` must match CAND-004 and order intent.
- Freshness must be recomputed from `as_of` if timestamp data is present in
  `freshness_assessment`.

## 6. Fingerprint / Canonicalization Design

Canonical JSON rules:

- `sort_keys=True`
- `separators=(",", ":")`
- `ensure_ascii=True`
- `allow_nan=False`
- UTF-8 encoding

Fingerprint format:

```text
sha256:<hex>
```

Compute fingerprints for:

- Every parsed input fixture.
- Combined input digest.
- Dry-run request payload.
- Final report payload before write.

`input_digest` is the fingerprint of this object:

```json
{
  "as_of": "...",
  "quality_gate": "sha256:...",
  "shadow_comparison": "sha256:...",
  "order_intent": "sha256:...",
  "kill_switch": "sha256:...",
  "risk_envelope": "sha256:...",
  "approval": "sha256:..."
}
```

`evaluation_id` is deterministic:

```text
gsc-<first-24-hex-chars-of-input-digest>
```

Reject NaN and Infinity at schema preflight.

## Numeric Normalization

Numeric fields in CAND-006 fixtures must be decimal strings, not JSON floats or
integers, for:

- Order intent `quantity`.
- Order intent `limit_price`.
- Risk `evaluated_price`.
- Risk `evaluated_notional`.

Implementation rules:

- Use `decimal.Decimal` internally.
- Reject JSON floats and JSON integers for decimal fixture fields.
- Reject `NaN`.
- Reject `Infinity` and `-Infinity`.
- Reject exponent notation in CAND-006 v1.
- Reject negative zero.
- Reject leading plus signs in canonical output.
- Canonical decimal strings strip unnecessary trailing zeros.
- `quantity > 0`.
- `limit_price > 0`.
- `evaluated_price > 0`.
- `evaluated_notional >= 0`.
- Fingerprints must use canonical decimal strings, not original user-provided
  decimal spellings.

Examples:

- `"001.2300"` normalizes to `"1.23"`.
- `"+1.0"` is rejected before canonicalization.
- `"-0"` is rejected.
- `"1e3"` is rejected.
- `1.0` is rejected because it is a JSON number, not a string.

## Timestamp Normalization

All CAND-006 fixture timestamps must be ISO-8601 UTC.

Accepted forms:

- `2026-06-24T10:00:00Z`
- `2026-06-24T10:00:00+00:00`

Both normalize to:

```text
2026-06-24T10:00:00Z
```

Rules:

- Non-UTC offsets are rejected.
- Naive timestamps are rejected.
- `--as-of` must also be ISO-8601 UTC.
- Normalized timestamps are used for fingerprints and artifact output.
- No wall-clock calls are allowed in CAND-006 modules.

## 7. Gate Engine Design

Evaluate gates strictly in approved order. Stop on the first failing gate. Mark
later gates as `not_run`.

### Gate 1: `schema_preflight`

Inputs:

- CAND-004 quality gate JSON.
- CAND-005 shadow comparison JSON.
- Order intent JSON.
- Kill-switch fixture JSON.
- Risk envelope fixture JSON.
- Approval fixture JSON.
- `--as-of`.

Required:

- Every path exists and is a readable JSON object.
- `--as-of` is an ISO-8601 UTC timestamp.
- `--as-of` is included in both JSON and Markdown outputs.
- Every CAND-006 fixture matches its closed schema.
- No parsed fixture contains NaN or Infinity.
- No parsed fixture contains secret-like keys or values.
- No output should expose absolute input paths.

Failure status: `not_evaluated`.

### Gate 2: `cand004_quality_gate`

Required:

- `artifact_type == "trading_quality_gate"`
- `mode == "paper"`
- `quality_state == "eligible_for_shadow_live_quality_review"`
- `blockers == []`

Failure status: `blocked`.

### Gate 3: `cand005_shadow_live_comparison`

CAND-006 intentionally narrows the CAND-005 default.

CAND-005 treats both `matched` and `minor_divergence` as reviewable. CAND-006
must require:

```text
shadow comparison status == "matched"
```

Required:

- `artifact_type == "shadow_live_comparison"`
- `schema_version == "shadow-live-comparison.v1"`
- `status == "matched"`

`minor_divergence` must block by default with:

```text
shadow_divergence_blocked
```

Failure status: `shadow_divergence_blocked`.

CAND-006 v1 has no user policy file. The default is fixed, hardcoded, and
cannot be widened by CLI input.

### Gate 4: `kill_switch_fixture`

Required:

- Closed schema `gated_submit_kill_switch_fixture` passes.
- `fixture_mode == "simulated"`
- `scope == "conformance_rehearsal_only"`
- `state == "inactive"`
- `expires_at >= as_of`

Failure status: `kill_switch_blocked`.

### Gate 5: `risk_envelope_fixture`

The risk fixture is RiskManager-shaped but must not import or invoke
`RiskManager`.

Required:

- Closed schema `gated_submit_risk_envelope_fixture` passes.
- `fixture_mode == "simulated"`
- `represents == "RiskManager_evaluation"`
- `evaluation_mode == "paper"`
- `intent_fingerprint` equals the actual order intent fingerprint.
- `decision == "allowed"`
- `violations == []`
- `checks` is a non-empty list
- Every check object has exactly `{"rule", "passed"}`.
- Every check has `passed is true`.
- `expires_at >= as_of`.

Do not accept:

```text
decision == "requires_approval"
```

Approval is a separate gate. It must not compensate for a non-allowed risk
decision.

Failure status: `risk_blocked`.

### Gate 6: `approval_fixture`

The approval fixture is simulated only. It is not proof of a real human
approval.

Required:

- Closed schema `gated_submit_approval_fixture` passes.
- `fixture_mode == "simulated"`.
- `scope == "conformance_rehearsal_only"`.
- `decision == "approved"`.
- `expires_at >= as_of`
- Approval scope fingerprints match order intent and risk envelope.

Actor handling:

- Use `actor_label`, not a real actor identity.
- `actor_label` is optional.
- If present, it must be bounded, redacted, and simulated-only.
- Allowed examples:
  - `simulated-reviewer`
  - `fixture-approver`
  - `conformance-approval-fixture`
- Never treat `actor_label` as real human approval proof.

Failure status: `approval_required`.

### Gate 7: `dry_run_conversion`

Build a non-transmittable dry-run request only after all prior gates pass.

Status after this gate: `dry_run_ready`.

### Gate 8: `atomic_artifact_recording`

Atomically record artifacts.

Status after successful authoritative JSON recording: `dry_run_recorded`.

## 8. Dry-Run Payload Design

Only create `dry_run_request` after all gates pass.

Payload:

```json
{
  "artifact_type": "non_transmittable_dry_run_submit_request",
  "schema_version": "gated-submit-dry-run-request.v1",
  "request_id": "cand006-...",
  "evaluation_id": "gsc-...",
  "as_of": "2026-06-23T12:00:00Z",
  "intent_id": "intent-001",
  "symbol": "AAPL",
  "side": "buy",
  "quantity": "1",
  "order_type": "limit",
  "limit_price": "100",
  "estimated_notional": "100",
  "source_fingerprints": {},
  "transmission": {
    "allowed": false,
    "reason": "CAND-006 simulated-only conformance rehearsal",
    "broker_adapter": null,
    "provider": null
  },
  "runtime_effects": {
    "order_instantiated": false,
    "pending_order_created": false,
    "broker_called": false,
    "provider_called": false,
    "credentials_loaded": false,
    "network_called": false,
    "runtime_state_mutated": false
  }
}
```

Do not include:

- `client_order_id`
- `broker_order_id`
- Pending-order path
- Account identifier
- Credential fields
- Raw approval body
- Raw broker/provider payload
- Raw stack traces

## 9. Artifact Writer Design

Approved artifacts:

- `gated-submit-conformance.json`
- `gated-submit-conformance-report.md`

JSON is the only authoritative commit marker. Markdown is informational.

Both artifacts must contain the same:

- `evaluation_id`
- `as_of`

Markdown consumers must ignore Markdown if:

- The matching JSON artifact is absent.
- The matching JSON artifact has a different `evaluation_id`.
- The matching JSON artifact has a different `as_of`.

Markdown sections:

- Safety banner.
- Final status.
- `evaluation_id`.
- `as_of`.
- Gate table.
- Redacted input artifact names.
- Input fingerprints and `input_digest`.
- Dry-run request summary, only if present.
- `dry_run_request_fingerprint`, if present.
- Blockers.
- Safety assertions.
- Disclaimer.

## 10. Atomic Write Strategy

Use same-directory temp files and `os.replace`.

Write order:

1. Ensure output directory exists.
2. Build final JSON report in memory.
3. Build Markdown report in memory.
4. Write Markdown temp file, flush, fsync.
5. Write JSON temp file, flush, fsync.
6. `os.replace(markdown_temp, gated-submit-conformance-report.md)`.
7. `os.replace(json_temp, gated-submit-conformance.json)`.

Authoritative semantics:

- JSON is the only authoritative commit marker.
- Markdown is informational.
- Both JSON and Markdown must include the same `evaluation_id`.
- Both JSON and Markdown must include the same `as_of`.
- If Markdown write succeeds but JSON write fails, CLI must exit `2`.
- If JSON write fails, the command must not print or report
  `dry_run_recorded`.
- If JSON write fails after `dry_run_conversion`, final reported status must be
  `dry_run_ready` or `blocked`, with a safe recording blocker.
- Consumers must ignore Markdown if the matching JSON artifact is absent or has
  a different `evaluation_id`.

Do not write any runtime state outside the selected output directory.

## Input/output Path Alias Rejection

Before writing artifacts, resolve all input paths and final/temp output paths
using `Path.resolve()`.

Reject if any input path aliases:

- `gated-submit-conformance.json`
- `gated-submit-conformance-report.md`
- Temporary output JSON path.
- Temporary output Markdown path.
- `output_dir` itself where inappropriate.

Also reject:

- Symlink aliasing.
- Same resolved inode/path.
- An `output_dir` placement that can overwrite input artifacts.
- `output_dir` inside an input file path parent pattern only if it can overwrite
  input artifacts.

Path-alias rejection runs before any output file write. The implementation may
compare resolved paths and, where files exist, device/inode identity. Failure
status is `not_evaluated` before dry-run conversion, or `blocked` if detected
during artifact recording.

## 11. Redaction Strategy

Preflight rejects secret-like inputs rather than sanitizing and proceeding.

Secret-like keys and values:

- `api_key`
- `apikey`
- `token`
- `password`
- `secret`
- `credential`
- `private_key`
- `auth_header`
- `authorization`
- `bearer `
- `sk-`
- `ghp_`
- `AKIA`
- `.env`
- `.env.atlas`

Output rules:

- Input paths are basenames only.
- No absolute paths.
- No home directory usernames.
- No raw exception text.
- No raw fixture bodies in Markdown.
- `actor_label` is redacted if too long, suspicious, or secret-like.
- Do not print secrets to stdout/stderr.

## 12. Static Checker Design

Create `scripts/check_gated_submit_conformance_contract.py`.

The checker is deterministic, local-only, and must not import runtime Atlas
modules beyond stdlib path reads.

Required checks:

- Required files exist.
- `pyproject.toml` console script points to `atlas_agent.cli_bootstrap:main`.
- Use AST checks for imports and calls where possible.
- Use token-aware or AST/string-literal-aware checks for forbidden calls. Do not
  rely only on broad substring scans.
- Bootstrap source contains the exact route `agent submit-conformance`.
- Bootstrap source does not import `atlas_agent.cli` at module import time.
- Bootstrap source does not route `--workspace X agent submit-conformance`
  through the configless path.
- Core and CAND-006 CLI modules have only stdlib imports.
- `atlas_agent.agent.__init__` does not import CAND-006 modules as convenience
  exports.
- Core/CLI modules do not import forbidden Atlas runtime packages:
  - `atlas_agent.brokers`
  - `atlas_agent.providers`
  - `atlas_agent.execution`
  - `atlas_agent.risk`
  - `atlas_agent.safety`
  - `atlas_agent.config`
- Core/CLI modules do not directly import or use forbidden dependency/network
  packages:
  - `urllib`
  - `socket`
  - `requests`
  - `httpx`
  - `aiohttp`
  - `websockets`
  - `subprocess`
  - `dotenv`
  - `keyring`
- Core source contains all approved statuses.
- Core source contains all gate IDs in the approved order.
- Core source contains approved artifact names.
- Core source contains the approved artifact schemas and closed-schema rejection
  logic.
- `--policy` is not present in CAND-006 v1 parser/source/docs except in this
  plan's explicit rejection requirement.
- Source does not contain forbidden runtime patterns:
  - `Order(`
  - `OrderRouter`
  - `RiskManager`
  - `place_order`
  - `submit_order`
  - `create_pending_order`
  - `load_atlas_secrets`
  - `AtlasConfig`
  - `datetime.now`
  - `date.today`
  - `time.time`
- Docs contain simulated-only, local-only, no-broker/provider, no-live-readiness
  language.
- Docs contain exact simulated-only disclaimers for the command and output
  artifacts.
- Forbidden-claim checks ignore negative disclaimer contexts but still fail on
  affirmative claims. Docs do not contain affirmative claims such as:
  - "risk free" (hyphenated form)
  - "guaranteed gains" (profit-like claims)
  - "live ready"
  - "safe to trade real money"
  - "production ready"

Support `--json`. Exit `0` on pass, `2` on findings.

## 13. Runtime Import-Trace Test Design

Create `tests/test_gated_submit_conformance_import_trace.py`.

Use subprocesses so each test starts with a clean module graph. The subprocess
code should import `atlas_agent.cli_bootstrap.main`, run the command, then emit
sorted `sys.modules`.

Configless positive route:

- Build minimal valid fixtures in a temp directory.
- Call `main(["agent", "submit-conformance", ...])`.
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

Handle incidental standard-library imports carefully. Do not fail the runtime
import trace merely because Python imports `urllib.parse` indirectly through
help, packaging, argparse internals, or other stdlib paths. Direct source import
of `urllib` remains forbidden by the static checker.

Delegation tests:

- `main(["--help"])` delegates to legacy CLI and may import `atlas_agent.cli`.
- `main(["validate"])` delegates to legacy CLI.
- `main(["--workspace", "X", "agent", "submit-conformance"])` delegates to
  legacy CLI and does not use the configless path.
- `main(["agent", "submit-conformance-extra"])` delegates to legacy CLI.

## 14. CLI Tests

Create `tests/test_gated_submit_conformance_cli.py`.

Cover:

- `--help` returns `0` and says simulated-only, local-only, no broker/provider
  calls, no live readiness.
- `atlas agent submit-conformance --help` avoids `atlas_agent.cli` import.
- `--policy` is rejected by argparse.
- Valid fixture set writes both artifacts and exits `0`.
- `--json` emits valid JSON with `status == "dry_run_recorded"`.
- Missing quality gate returns `2`, status `not_evaluated`.
- Quality gate blocked returns `2`, status `blocked`.
- Unknown fixture fields are rejected.
- CAND-004/CAND-005 `run_id` mismatch blocks.
- CAND-004/CAND-005 `symbol` mismatch blocks.
- Shadow status `minor_divergence` returns `2`, status
  `shadow_divergence_blocked`.
- Kill switch active returns `2`, status `kill_switch_blocked`.
- Risk `requires_approval` returns `2`, status `risk_blocked`.
- Risk `allowed == true` with `status == "allowed"` but empty `checks` returns
  `2`, status `risk_blocked`.
- Risk with any failed check returns `2`, status `risk_blocked`.
- Approval missing, expired, or unapproved returns `2`, status
  `approval_required`.
- `actor_label` is optional and simulated only.
- Output contains no absolute temp paths or secret-like values.
- Bootstrap delegates `validate`, `--help`, and unknown commands unchanged.
- Delegated commands receive argv unchanged.

## 15. Feature Tests

Create `tests/test_gated_submit_conformance.py`.

Cover:

- Valid all-pass fixtures produce `dry_run_ready` before writer and
  `dry_run_recorded` after writer.
- `evaluation_id` is deterministic and appears in both JSON and Markdown.
- `as_of` is required and appears in both JSON and Markdown.
- `--as-of` parser rejects non-UTC timestamps.
- Non-UTC fixture timestamps are rejected.
- Naive fixture timestamps are rejected.
- `+00:00` timestamps normalize to `Z`.
- No CAND-006 gate decision uses wall-clock time.
- Fingerprints are stable under input key reordering.
- `input_digest` changes when any input fixture changes.
- Decimal canonicalization is stable.
- JSON floats are rejected for decimal fixture fields.
- Risk envelope fingerprint mismatch blocks.
- Approval scope fingerprint mismatch blocks.
- Approval expiry uses supplied `as_of`, not wall clock.
- CAND-005 `minor_divergence` blocks by default.
- Dry-run request has `transmission.allowed == false`.
- Dry-run request has no `client_order_id`, `broker_order_id`, pending-order
  path, or account id.
- Input fixture hashes do not change after evaluation.
- Secret-like fixture input is rejected at preflight.
- Atomic writer writes deterministic JSON with sorted keys.
- Output JSON path equals input path is rejected.
- Output JSON path aliases input path is rejected.
- Output Markdown path equals input path is rejected.
- Output Markdown path aliases input path is rejected.
- Symlink output aliasing an input path is rejected.
- If Markdown exists but JSON is absent, helper/consumer tests treat the
  artifact set as uncommitted.
- Existing stale Markdown with missing JSON is ignored.
- If Markdown and JSON have different `evaluation_id`, helper/consumer tests
  reject the Markdown as informational only.
- JSON write failure after Markdown write exits `2` and never reports
  `dry_run_recorded`.

## 16. Regression Tests

Add targeted regressions:

- Existing `tests/test_cli.py::test_python_module_help_works` still passes.
- Existing `tests/test_cli_smoke.py` still uses legacy `atlas_agent.cli.main`
  unaffected.
- `tests/test_cli_command_compatibility.py` passes with the bootstrap-only
  exception.
- `tests/test_package_distribution_check.py` passes with the new entry point
  target.
- `tests/test_autonomous_paper_quality.py` still passes.
- `tests/test_shadow_live_readonly.py` still passes.
- `tests/test_submit_execution_safety_check.py` still passes.
- No convenience imports are added to `atlas_agent.agent.__init__`.
- `atlas run --mode live` remains fail-closed unless fully configured.

## 17. Docs / Release Metadata Updates

Update docs to say CAND-006 is implemented as a simulated-only conformance
rehearsal:

- `docs/gated-submit-conformance.md`
- `docs/shadow-live-readiness-contract.md`
- `docs/bounded-live-autonomy-governance.md`
- `docs/autonomy-roadmap.md`
- `docs/architecture.md`
- `docs/cli-command-compatibility.md`
- `docs/releases/v0.6.16-candidates.md`
- `docs/releases/v0.6.16-candidates.json`
- `docs/releases/v0.6.16-candidate-selection.md`
- `docs/releases/v0.6.16-plan.md`
- `CHANGELOG.md`

Required wording:

- Simulated only.
- Local fixture only.
- No live trading.
- No broker/provider calls.
- No credentials.
- No pending orders.
- No live readiness claim.
- `minor_divergence` blocks by default for CAND-006.
- Actor labels are simulated fixture labels, not real human approval proof.

No version bump, tag, GitHub release, or PyPI publication.

## 18. Validation Command List

Focused validation:

```bash
python3.11 -m compileall src scripts
python3.11 scripts/check_gated_submit_conformance_contract.py
python3.11 scripts/check_gated_submit_conformance_contract.py --json
python3.11 -m pytest tests/test_gated_submit_conformance.py tests/test_gated_submit_conformance_cli.py tests/test_gated_submit_conformance_contract.py tests/test_gated_submit_conformance_import_trace.py -q
python3.11 -m pytest tests/test_cli_command_compatibility.py tests/test_package_distribution_check.py -q
python3.11 -m pytest tests/test_autonomous_paper_quality.py tests/test_shadow_live_readonly.py tests/test_submit_execution_safety_check.py -q
git diff --check
```

Required repo checks:

```bash
pytest
pip check
atlas validate
atlas config set market.symbol AAPL
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
atlas run --mode paper
atlas run --mode live
```

`atlas run --mode live` should fail safely unless explicit live config,
credentials, risk checks, and approval are present.

## 19. Commit Plan

Commit 1: core engine and configless CAND-006 route.

- Add stdlib-only core engine.
- Add configless CLI handler.
- Add focused unit and CLI tests.

Commit 2: bootstrap and import isolation.

- Add bootstrap pre-router.
- Change `pyproject.toml`.
- Add runtime import-trace tests.
- Update package distribution and CLI compatibility tests.

Commit 3: static checker and gate wiring.

- Add static checker.
- Wire checker/tests into `scripts/dev_check.sh` and `scripts/release_check.sh`.

Commit 4: docs and release metadata.

- Add user-facing docs.
- Update governance, roadmap, architecture, release candidate metadata, and
  changelog.

## 20. Known Risks And Prevention

- Risk: CAND-006 route imports legacy CLI and therefore brokers/config/risk.
  - Prevention: bootstrap pre-router, runtime import-trace test, static checker.

- Risk: pre-router becomes a broad configless CLI refactor.
  - Prevention: exact-route match only for `agent submit-conformance`; all other
    commands delegate unchanged.

- Risk: `atlas --workspace X agent submit-conformance` bypasses config loading.
  - Prevention: pre-router only checks the first two argv tokens.

- Risk: existing command behavior changes after moving console entry point.
  - Prevention: delegation regression tests for `--help`, `validate`, and legacy
    command smoke paths.

- Risk: accidental live-submit behavior by reusing existing dry-run or approval
  modules.
  - Prevention: forbid all `atlas_agent.execution`, `Order`, `OrderRouter`,
    `RiskManager`, and pending-order APIs.

- Risk: CAND-005 `minor_divergence` accidentally passes.
  - Prevention: require exact `matched`; static checker and CLI tests assert
    `minor_divergence` maps to `shadow_divergence_blocked`.

- Risk: approval fixture is mistaken for real approval.
  - Prevention: use optional simulated `actor_label`; docs and artifacts state
    it is not real human approval proof.

- Risk: risk approval compensates for a failed risk decision.
  - Prevention: require risk fixture `decision == "allowed"`, non-empty checks,
    every check passed, and `violations == []` before approval fixture is
    evaluated.

- Risk: deterministic artifact drift from wall clock.
  - Prevention: require `--as-of`; forbid `datetime.now()` and equivalent APIs.

- Risk: partial artifact writes claim success.
  - Prevention: JSON is the only commit marker; JSON write failure exits `2` and
    never reports `dry_run_recorded`.

- Risk: Markdown is consumed as authoritative evidence.
  - Prevention: docs and tests state consumers must ignore Markdown without
    matching JSON `evaluation_id`.

- Risk: secret/path leakage in artifacts.
  - Prevention: reject secret-like inputs, basename-only artifact references,
    and redaction tests.

- Risk: runtime import-trace tests become flaky due to incidental stdlib imports.
  - Prevention: hard-fail only on Atlas forbidden modules and non-stdlib network
    libraries at runtime; keep direct source import of `urllib` forbidden by the
    static checker.
