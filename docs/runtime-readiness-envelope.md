# Runtime Readiness Envelope Evaluation (CAND-007)

`atlas agent readiness-envelope` is a **simulated-only** runtime readiness envelope evaluator.

It consumes CAND-004 trading-quality evidence, CAND-005 shadow-live comparison evidence,
CAND-006 gated submit conformance evidence, and five static local policy fixtures. It evaluates
them in strict fail-closed order and records a runtime readiness envelope artifact if every
gate passes.

> **Evidence-only disclaimer.** `readiness_envelope_recorded` is evidence-recording status only.
> It is not live readiness, not trading safety, not profitability evidence, and not permission to
> submit orders.

## What this command does

- Validates three upstream artifacts by closed projection (CAND-004, CAND-005, CAND-006).
- Validates five CAND-007-owned static policy fixtures against closed schemas.
- Scans every fixture for secret-like, endpoint-like, and URL/protocol content.
- Correlates evidence by `run_id` and `symbol`.
- Enforces a 24-hour freshness bound on CAND-006 evidence relative to the caller-supplied `--as-of`.
- Evaluates 11 fail-closed gates in strict order.
- Writes two artifacts deterministically:
  - `runtime-readiness-envelope.json` (authoritative)
  - `runtime-readiness-envelope-report.md` (informational)

## What this command does NOT do

This command is an envelope evaluator only. It:

- **does not submit orders** to any broker or exchange.
- **does not call broker APIs** or provider APIs.
- **does not load credentials**, API keys, tokens, secrets, or account identifiers.
- **does not create real or pending orders**.
- **does not instantiate runtime `Order`, `OrderRouter`, `RiskManager`, `ApprovalManager`, or kill-switch objects**.
- **does not claim live readiness**, trading safety, profitability, or permission to submit orders.
- **does not mutate broker, portfolio, or live state**.

## Command

```bash
atlas agent readiness-envelope \
  --quality-gate reports/autonomous_paper_quality/trading-quality-gate.json \
  --shadow-comparison reports/shadow_live/shadow-live-comparison.json \
  --submit-conformance reports/gated_submit_conformance/gated-submit-conformance.json \
  --runtime-envelope fixtures/runtime-envelope.json \
  --broker-capabilities fixtures/broker-capabilities.json \
  --operator-policy fixtures/operator-policy.json \
  --kill-switch-policy fixtures/kill-switch-policy.json \
  --audit-policy fixtures/audit-policy.json \
  --output-dir reports/runtime_readiness_envelope \
  --as-of 2026-06-24T10:00:00Z \
  [--json]
```

### Required inputs

| Flag | Description |
|---|---|
| `--quality-gate` | Path to CAND-004 `trading-quality-gate.json`. |
| `--shadow-comparison` | Path to CAND-005 `shadow-live-comparison.json`. |
| `--submit-conformance` | Path to CAND-006 `gated-submit-conformance.json`. |
| `--runtime-envelope` | Path to the runtime envelope fixture. |
| `--broker-capabilities` | Path to the broker capability manifest fixture. |
| `--operator-policy` | Path to the operator policy fixture. |
| `--kill-switch-policy` | Path to the kill-switch policy fixture. |
| `--audit-policy` | Path to the audit policy fixture. |
| `--output-dir` | Output directory for artifacts. |
| `--as-of` | ISO-8601 UTC timestamp used for expiry and evidence-age checks. |

### Optional inputs

| Flag | Description |
|---|---|
| `--json` | Emit the report as JSON on stdout. |

## Produced artifacts

### `runtime-readiness-envelope.json`

The JSON artifact is the authoritative record. Consumers must ignore the Markdown report if the
JSON artifact is absent or if the `evaluation_id` in the Markdown report does not match the JSON
artifact.

### `runtime-readiness-envelope-report.md`

The Markdown report is a human-readable rendering of the JSON artifact. It is provided for
convenience and is not authoritative.

## Determinism and local-only operation

All evaluation is deterministic and local. The only timestamp that influences gate decisions is
the caller-supplied `--as-of` value. No wall-clock time is used to decide whether a fixture is
expired or valid.

## Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0`       | Every gate passed and artifacts recorded (`readiness_envelope_recorded`). |
| `2`       | Any other final status or CLI error. |

## Gate sequence

Gates are evaluated in strict fail-closed order. Evaluation stops at the first failed gate;
downstream gates are recorded as `not_run`.

| # | Gate ID | Failure status |
|---|---|---|
| 1 | `schema_preflight` | `not_evaluated` |
| 2 | `cand004_evidence_gate` | `upstream_quality_blocked` |
| 3 | `cand005_evidence_gate` | `shadow_evidence_blocked` |
| 4 | `cand006_evidence_gate` | `submit_conformance_blocked` |
| 5 | `runtime_envelope_fixture_gate` | `runtime_envelope_blocked` |
| 6 | `broker_capability_manifest_gate` | `broker_capability_blocked` |
| 7 | `operator_policy_fixture_gate` | `operator_policy_blocked` |
| 8 | `kill_switch_policy_fixture_gate` | `kill_switch_policy_blocked` |
| 9 | `audit_policy_fixture_gate` | `audit_policy_blocked` |
| 10 | `envelope_synthesis_gate` | `blocked` |
| 11 | `artifact_recording_gate` | `blocked` (if JSON write fails) |

Only successful completion of gate 11 returns exit code `0`.

## Statuses

| Status | Meaning |
|---|---|
| `not_evaluated` | Preflight validation failed before any evidence gate could run. |
| `blocked` | A generic blocker was encountered, including an artifact write failure. |
| `upstream_quality_blocked` | CAND-004 quality gate is not in the required state. |
| `shadow_evidence_blocked` | CAND-005 shadow-live comparison is not `matched` or has blockers. |
| `submit_conformance_blocked` | CAND-006 submit conformance is not `dry_run_recorded`, is stale, or has blockers. |
| `runtime_envelope_blocked` | The runtime envelope fixture violates the closed schema or live-submit policy. |
| `broker_capability_blocked` | The broker capability manifest fixture violates credential/endpoint/broker-label rules. |
| `operator_policy_blocked` | The operator policy fixture violates manual-approval, unattended-operation, or symbol rules. |
| `kill_switch_policy_blocked` | The kill-switch policy fixture does not require a fail-closed kill switch. |
| `audit_policy_blocked` | The audit policy fixture does not require local artifact recording and hash-chain recording. |
| `envelope_synthesized` | All evidence and fixture gates passed; the envelope has been synthesized but not yet recorded. |
| `readiness_envelope_recorded` | Both JSON and Markdown artifacts were written successfully. |

The status `readiness_envelope_recorded` is **evidence-recording status only**. It is not live
readiness, not trading safety, not profitability evidence, and not permission to submit orders.

## Relationship to other candidates

- CAND-004 produces `trading-quality-gate.json`.
- CAND-005 produces `shadow-live-comparison.json`.
- CAND-006 produces `gated-submit-conformance.json`.
- CAND-007 consumes all three, plus five static local policy fixtures, to evaluate whether the
candidate chain forms a coherent, internally consistent, fail-closed runtime readiness envelope
for future supervised live-path design work.
- CAND-008 is the next stage: an operator approval gate that consumes CAND-004, CAND-005,
  CAND-006, and CAND-007 artifacts plus CAND-008 static fixtures to record an evidence-only
  operator approval gate artifact. See [`docs/operator-approval-gate.md`](operator-approval-gate.md).

## See also

- [`docs/runtime-readiness-envelope-design.md`](runtime-readiness-envelope-design.md)
- [`docs/bounded-live-autonomy-governance.md`](bounded-live-autonomy-governance.md)
- [`docs/gated-submit-conformance.md`](gated-submit-conformance.md)
- [`docs/shadow-live-readiness-contract.md`](shadow-live-readiness-contract.md)
- [`docs/autonomous-paper-quality-gate.md`](autonomous-paper-quality-gate.md)
- [`docs/shadow-live-readonly-comparison.md`](shadow-live-readonly-comparison.md)
- [`docs/operator-approval-gate.md`](operator-approval-gate.md)
