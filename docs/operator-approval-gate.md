# Operator Approval Gate (CAND-008)

> **Scope:** evidence-only, simulated-only local artifact evaluation.
>
> **Status:** `operator_gate_recorded` is evidence-recording status only and is
> **not live readiness**, not permission to submit orders, and not a claim that
> the system is safe to trade real money.
>
> The status `operator_gate_recorded is evidence-recording status only`; it does
> not authorize live trading or order submission.

The operator approval gate is the final deterministic, fail-closed evaluation in
the CAND-004 → CAND-005 → CAND-006 → CAND-007 → CAND-008 evidence chain. It
consumes only local JSON artifacts and static local fixtures, evaluates a
13-gate sequence, and—if every gate passes—records two local artifacts:

- `operator-approval-gate.json`
- `operator-approval-gate-report.md`

Nothing in this gate submits orders, calls broker or provider APIs, loads
credentials, creates real or pending orders, mutates runtime approval queues or
kill-switch state, or performs network I/O.

## What the gate evaluates

The gate reads the following upstream evidence artifacts:

- CAND-004 `trading_quality_gate` artifact
- CAND-005 `shadow_live_comparison` artifact
- CAND-006 `gated_submit_conformance` artifact
- CAND-007 `runtime_readiness_envelope` artifact

It also reads the following CAND-008-owned static local fixtures:

- `operator_identity_fixture`
- `approval_policy_fixture`
- `kill_switch_observation_fixture`
- `operator_acknowledgment_fixture`
- `audit_policy_fixture`

The 13-gate fail-closed sequence is:

1. `schema_preflight` — closed-schema validation of every input.
2. `cand004_projection_gate` — upstream quality state must be accepted.
3. `cand005_projection_gate` — shadow comparison must be matched and fresh.
4. `cand006_projection_gate` — submit conformance must be `dry_run_recorded`,
   transmission blocked, and evidence recent.
5. `cand007_projection_gate` — readiness envelope must be
   `readiness_envelope_recorded`, `simulated_only`, `CAND-007`, with empty
   blockers and all required safety assertions true.
6. `cross_artifact_correlation_gate` — `run_id`, `symbol`, and candidate chain
   must align.
7. `operator_identity_gate` — identity fixture must be present, unexpired,
   scope-limited, and free of secret/endpoint/account identifiers.
8. `approval_policy_gate` — policy must require manual review, forbid live
   trading approval, forbid live submit approval, and forbid unattended
   operation.
9. `kill_switch_observation_gate` — observed state must be `blocked`, no
   override attempted or allowed, and defaults must be `blocked`.
10. `operator_acknowledgment_gate` — operator must acknowledge no live submit,
    no trading authorization, no profitability claim, no broker certification,
    evidence-only review scope, and forbidden unattended live operation. The
    acknowledgment digest must match the canonical text digest.
11. `audit_policy_gate` — audit must be required, append-only, hash-chained,
    local-only, and must not claim a live audit chain.
12. `approval_gate_synthesis` — summarize inputs and produce a deterministic
    approval gate digest.
13. `artifact_recording_gate` — atomically write `operator-approval-gate.json`
    and `operator-approval-gate-report.md` and verify that the raw upstream
    payload is not leaked.

If any gate fails, downstream gates are not run and the final status is one of
the deterministic blocked statuses (`not_evaluated`, `blocked`,
`upstream_evidence_blocked`, `runtime_envelope_blocked`,
`operator_identity_blocked`, `approval_policy_blocked`,
`kill_switch_observation_blocked`, `operator_acknowledgment_blocked`,
`audit_policy_blocked`).

## CLI usage

The gate is invoked through a configless CLI path:

```bash
atlas agent operator-approval-gate \
  --quality-gate path/to/trading_quality_gate.json \
  --shadow-comparison path/to/shadow_live_comparison.json \
  --submit-conformance path/to/gated_submit_conformance.json \
  --readiness-envelope path/to/runtime_readiness_envelope.json \
  --operator-identity path/to/operator_identity_fixture.json \
  --approval-policy path/to/approval_policy_fixture.json \
  --kill-switch-observation path/to/kill_switch_observation_fixture.json \
  --operator-acknowledgment path/to/operator_acknowledgment_fixture.json \
  --audit-policy path/to/audit_policy_fixture.json \
  --output-dir path/to/output \
  --as-of 2026-06-24T10:00:00Z
```

The command exits `0` only when the final status is `operator_gate_recorded`.
The `--json` flag emits the artifact content to stdout.

## Safety properties

- **No live trading.** The gate runs in `simulated_only` mode; any fixture or
  upstream artifact claiming live mode is rejected.
- **No live submit.** No order is submitted; no broker or provider API is
  called.
- **No credentials.** The engine does not load API keys, tokens, passwords, or
  secrets. It actively rejects fixture fields that look like credentials,
  endpoints, or account identifiers.
- **No network I/O.** Imports are restricted to the Python standard library plus
  the engine module itself.
- **No runtime state mutation.** The gate does not instantiate `Order`,
  `OrderRouter`, `RiskManager`, `ApprovalManager`, or the runtime kill switch.
- **No approval queue mutation.** The gate records evidence; it does not modify
  any approval queue or kill-switch state.
- **No release cutover.** A recorded gate artifact does not change the package
  version, tag a release, publish to PyPI, or enable live trading by default.

## Artifact output

`operator-approval-gate.json` contains a projected summary of the inputs,
per-gate results, deterministic digests, and a clear disclaimer. The canonical
acknowledgment text itself is **not** emitted in the artifact; only its digest is
recorded.

`operator-approval-gate-report.md` is a human-readable rendering of the same
information, suitable for local review and audit append-only recording.

## Relationship to governance

CAND-008 is the final evidence-recording step in the bounded-live-autonomy
planning chain. It records that a local operator reviewed local evidence under a
fail-closed policy. It does **not** grant permission to submit orders, does
**not** indicate live readiness, and does **not** authorize unattended live
trading.
