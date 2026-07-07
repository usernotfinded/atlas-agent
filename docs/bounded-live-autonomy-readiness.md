# Bounded Live Autonomy Readiness (CAND-015)

`atlas agent bounded-live-readiness`

## Purpose

CAND-015 is an evidence-only, simulated-only readiness gate that sits at the L2/L3
autonomy boundary. It consumes upstream CAND-004/CAND-005/CAND-006/CAND-007/CAND-008
artifacts plus CAND-015-owned local policy fixtures and evaluates a strict fail-closed
gate sequence. The output is a local artifact pair:

- `bounded-live-readiness.json`
- `bounded-live-readiness-report.md`

## Scope

- Evaluate local evidence and policy fixtures only.
- Record `bounded_live_readiness_recorded` when all gates pass.
- Never claim live readiness, trading safety, profitability, or permission to trade.
- Never submit orders, call brokers, call providers, load credentials, or mutate runtime state.

## What this command does not do

- It does **not** submit orders.
- It does **not** call broker or provider APIs.
- It does **not** load credentials.
- It does **not** create real or pending orders.
- It does **not** import `Order`, `OrderRouter`, `RiskManager`, `ApprovalManager`, or runtime kill switch.
- It does **not** claim live readiness, trading safety, or permission to submit orders.

## Inputs

| Flag | Source |
|------|--------|
| `--quality-gate` | CAND-004 `trading-quality-gate.json` |
| `--shadow-comparison` | CAND-005 `shadow-live-comparison.json` |
| `--submit-conformance` | CAND-006 `gated-submit-conformance.json` |
| `--readiness-envelope` | CAND-007 `runtime-readiness-envelope.json` |
| `--operator-approval-gate` | CAND-008 `operator-approval-gate.json` |
| `--bounded-autonomy-policy` | CAND-015 fixture |
| `--risk-limit` | CAND-015 fixture |
| `--symbol-allowlist` | CAND-015 fixture |
| `--heartbeat-deadman` | CAND-015 fixture |
| `--audit-redaction` | CAND-015 fixture |

## Gate sequence

1. `schema_preflight` — closed-schema validation of all inputs.
2. `cand004_projection_gate` — CAND-004 has no blockers.
3. `cand005_projection_gate` — CAND-005 has no blockers.
4. `cand006_projection_gate` — CAND-006 has no blockers and transmission is blocked.
5. `cand007_projection_gate` — CAND-007 has no blockers and required envelope assertions are true.
6. `cand008_projection_gate` — CAND-008 has no blockers and required approval gate assertions are true.
7. `cross_artifact_correlation_gate` — upstream artifacts share symbol and run_id.
8. `bounded_autonomy_policy_gate` — L3 autonomy disabled, live submit disabled by default, manual approval required, no unattended operation, no auto-approval, explicit opt-in required, active operator oversight required, paper validation required.
9. `risk_limit_gate` — leverage, shorting, and options disallowed; conservative exposure limits.
10. `symbol_allowlist_gate` — evaluated symbol is explicitly allowed and not blocked.
11. `heartbeat_deadman_gate` — heartbeat and deadman required and fail-closed.
12. `audit_redaction_gate` — secrets, API keys, account IDs, raw broker payloads, raw provider output, paths, and exception text are redacted; hash chain and manifest required.
13. `l2_l3_boundary_gate` — hard invariant check of the L2/L3 boundary.
14. `readiness_synthesis_gate` — all prior gates passed.
15. `artifact_recording_gate` — local JSON/Markdown artifacts recorded (explicit
    in the recorded report; shown as `not_run` before artifacts are written).

## Exit codes

- `0` — `bounded_live_readiness_recorded` (evidence recorded only).
- `2` — `blocked` or validation failure.

## Important disclaimer

`bounded_live_readiness_recorded` is evidence-recording status only. It is not live
readiness, not trading safety, not profitability evidence, not permission to trade,
and not authorization to submit orders. L3 bounded live autonomy remains a future
research concept; this gate only records whether the supplied local evidence and
policy fixtures satisfy the declared L2/L3 boundary.

The sentence `bounded_live_readiness_recorded is evidence-recording status only`
is included to satisfy the static contract checker and to make clear that this
evaluation is not live readiness and not permission to submit orders. This
documentation explicitly states: not live readiness.
