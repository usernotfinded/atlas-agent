# Gated Submit Conformance Rehearsal (CAND-006)

`atlas agent submit-conformance` is a **simulated-only** conformance rehearsal.
It consumes CAND-004 quality-gate evidence, CAND-005 shadow-live comparison
evidence, a hypothetical order-intent fixture, and simulated kill-switch,
risk-envelope, and approval fixtures.

The command evaluates the fixtures in strict fail-closed order and records a
non-transmittable dry-run submit request only if every gate passes.

## What this command does

- Validates all fixtures against closed schemas.
- Replays the CAND-004 quality gate and CAND-005 shadow-live comparison.
- Checks a simulated kill-switch fixture.
- Checks a simulated `RiskManager` risk-envelope fixture.
- Checks a simulated approval fixture.
- Converts the order intent into a dry-run submit request with transmission
  explicitly blocked.
- Writes two artifacts deterministically:
  - `gated-submit-conformance.json` (authoritative)
  - `gated-submit-conformance-report.md` (informational)

## What this command does NOT do

This command is a conformance rehearsal only. It:

- **does not submit orders** to any broker or exchange.
- **does not call broker APIs** or provider APIs.
- **does not load credentials**, API keys, tokens, secrets, or account
  identifiers.
- **does not create real or pending orders**.
- **does not instantiate runtime `Order`, `OrderRouter`, `RiskManager`,
  `ApprovalManager`, or kill-switch objects**.
- **does not claim live readiness** or permission to submit orders.
- **does not mutate broker, portfolio, or live state**.

This command is a rehearsal artifact. It is **not live readiness** and it is **not permission to submit orders**.

## Determinism and local-only operation

All evaluation is deterministic and local. The only timestamp that influences
gate decisions is the caller-supplied `--as-of` value. No wall-clock time is
used to decide whether a fixture is expired or valid.

## Artifacts

### `gated-submit-conformance.json`

The JSON artifact is the authoritative record. Consumers must ignore the
Markdown report if the JSON artifact is absent or if the `evaluation_id` in the
Markdown report does not match the JSON artifact.

### `gated-submit-conformance-report.md`

The Markdown report is a human-readable rendering of the JSON artifact. It is
provided for convenience and is not authoritative.

## Exit codes

| Exit code | Meaning |
|-----------|---------|
| `0`       | Every gate passed and the dry-run request was recorded (`dry_run_recorded`). |
| `2`       | Any other final status (`not_evaluated`, `blocked`, `approval_required`, `risk_blocked`, `kill_switch_blocked`, `shadow_divergence_blocked`, `dry_run_ready`). |

A status of `dry_run_ready` means every gate passed but the artifact writer was
not invoked or the JSON write failed. A non-zero exit code is always returned
unless the authoritative JSON artifact is successfully written after all gates
pass.

## Safety assertions

The report JSON includes the following safety assertions, all `true`:

- `simulated_only`
- `no_live_submit`
- `no_broker_called`
- `no_provider_called`
- `no_credentials_loaded`
- `no_runtime_state_mutation`
- `no_order_instantiated`
- `transmission_blocked`
- `json_authoritative`

## Relationship to other candidates

- CAND-004 produces `trading-quality-gate.json`.
- CAND-005 produces `shadow-live-comparison.json`.
- CAND-006 consumes both, plus hypothetical order-intent and simulated
  kill-switch, risk-envelope, and approval fixtures, to rehearse the submit
  gate without ever submitting an order.
- CAND-007 (`atlas agent readiness-envelope`) is the next envelope stage. It
  consumes CAND-004, CAND-005, and CAND-006 evidence plus five static local
  policy fixtures to evaluate whether the candidate chain forms a coherent,
  internally consistent, fail-closed runtime readiness envelope. CAND-007 is an
  envelope evaluator, not a live path; it does not submit orders or indicate
  live readiness. The status `readiness_envelope_recorded` is evidence-recording
  status only.

## See also

- [`docs/bounded-live-autonomy-governance.md`](bounded-live-autonomy-governance.md)
- [`docs/autonomous-paper-quality-gate.md`](autonomous-paper-quality-gate.md)
- [`docs/shadow-live-readonly-comparison.md`](shadow-live-readonly-comparison.md)
