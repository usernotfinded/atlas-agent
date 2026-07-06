# Bounded Live Autonomy Readiness Design (CAND-015)

## Goal

Provide a deterministic, local, evidence-only evaluator for the L2/L3 autonomy
boundary. CAND-015 is the next bounded step after CAND-008 (operator approval gate)
and remains simulated-only.

## Non-goals

- Enable unsupervised live order submission.
- Bypass `RiskManager`, approval queues, kill switch, heartbeat, deadman, audit
  hash-chain, live-submit opt-in, or `can_submit`.
- Load credentials or call real brokers/providers.
- Claim live readiness, production readiness, or that unsupervised execution of real-money trades is safe.
- Mutate runtime trading state.

## Architecture

```text
┌─────────────────────────────────────┐
│  atlas agent bounded-live-readiness │
│  (configless CLI via cli_bootstrap) │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│ bounded_live_autonomy_readiness_cli │
│   - argument parsing                │
│   - unsafe flag rejection           │
│   - output path aliasing guard      │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│ bounded_live_autonomy_readiness     │
│   - closed-schema fixture validation│
│   - upstream artifact projection    │
│   - fail-closed gate sequence       │
│   - artifact recording              │
└─────────────────────────────────────┘
```

## Evidence inputs

CAND-015 consumes:

- CAND-004 trading-quality gate evidence.
- CAND-005 shadow-live comparison evidence.
- CAND-006 gated submit conformance evidence.
- CAND-007 runtime readiness envelope evidence.
- CAND-008 operator approval gate evidence.

Plus five CAND-015-owned static fixtures:

- `bounded_autonomy_policy_fixture`
- `risk_limit_fixture`
- `symbol_allowlist_fixture`
- `heartbeat_deadman_fixture`
- `audit_redaction_fixture`

## Outputs

- `bounded-live-readiness.json`
- `bounded-live-readiness-report.md`

Both are local files only. They contain no absolute input paths, no credentials, no
raw broker payloads, and no raw provider output.

## Fail-closed principles

- Any schema violation blocks.
- Any missing upstream evidence blocks.
- Any non-zero upstream exit code blocks.
- Any upstream blocker blocks.
- Any policy that would enable L3 autonomy, live submit by default, auto-approval,
  unattended operation, or provider-authoritative execution blocks.
- Any symbol not on the explicit allowlist blocks.
- Any heartbeat/deadman policy that is not fail-closed blocks.
- Any audit redaction policy that is not comprehensive blocks.

## Status semantics

- `readiness_synthesized` — all gates passed; ready for artifact recording.
- `bounded_live_readiness_recorded` — artifacts written; exit code `0`.
- `blocked` — one or more gates failed; exit code `2`.

`bounded_live_readiness_recorded` is evidence-recording status only. It is not live
readiness, not trading safety, not profitability evidence, not permission to trade,
and not authorization to submit orders. The exact declaration is:
bounded_live_readiness_recorded is evidence-recording status only. This status is
not live readiness and never grants permission to submit orders.

## CLI safety

The CLI rejects unsafe flags such as `--live`, `--submit`, `--broker`, `--provider`,
`--api-key`, `--mode`, `--approve-live`, `--enable-l3`, and similar. It also rejects
`--workspace` when placed after `agent bounded-live-readiness`; the configless form
must be used.
