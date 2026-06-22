# Paper Human Review Replay and Regression Gate

> **v0.6.15 planning line.** Paper-only. Offline/no-provider/no-broker/no-network.
> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

The `atlas backtest portfolio-review-replay` command performs a deterministic
replay over the paper human review pack, ledger, and policy artifacts. It
reproduces the CAND-001, CAND-002, and CAND-003 outputs from stable inputs,
records a reproducible replay artifact, and runs a regression gate that
explicitly verifies the paper chain remains intact and the live path stays
blocked. The replay is simulated: it records non-binding replay entries and a
gate summary that denies live approval, broker submission, provider execution,
notification sending, real order generation, and real human approval, while
allowing only paper follow-up.

## What it does

- Reads or builds the CAND-001 review pack, CAND-002 review ledger, and CAND-003
  review policy from local sample data.
- Replays each upstream artifact deterministically and records
  `regression_checks`.
- Produces a non-executable replay report with `replay` entries and a gate
  summary.
- Emits two artifacts:
  - `paper-human-review-replay.json`
  - `paper-human-review-replay.md`

## What it does NOT do

- It does NOT enable live trading.
- It does NOT generate executable orders.
- It does NOT submit anything to brokers.
- It does NOT call providers.
- It does NOT send notifications.
- It does NOT claim live readiness or autonomous live trading readiness.
- It is NOT financial advice, NOT live ready, and NOT a profit guarantee.
- It does NOT record real human approval.
- It makes NO account-specific instructions.
- It makes NO absolute safety claims and NO claims that risk is eliminated.

## Safety disclaimer

This command and its output are strictly paper-only and non-executable.
There is no broker submission, no provider calls, no real notifications,
no orders generated, no real human approval, no account-specific instructions,
no profit guarantees, no absolute safety claims, no claims that risk is
eliminated, no live-readiness claim, and no autonomous live trading readiness
claim. Human review is required before any future live-related work.

## Safety assertions

| Property | Value |
|---|---|
| `non_executable` | `true` |
| `paper_only` | `true` |
| `provider_required` | `false` |
| `broker_required` | `false` |
| `network_required` | `false` |
| `live_submit_enabled` | `false` |
| `orders_generated` | `false` |
| `notifications_sent` | `false` |
| `real_human_approval` | `false` |
| `not_financial_advice` | `true` |
| `not_live_ready` | `true` |

## CLI usage

Run the replay and regression gate against pre-existing CAND-001, CAND-002, and
CAND-003 artifacts:

```bash
atlas backtest portfolio-review-replay \
  --review-pack /tmp/review-pack/paper-human-review-pack.json \
  --review-ledger /tmp/review-ledger/paper-human-review-ledger.json \
  --review-policy /tmp/review-policy/paper-human-review-policy.json \
  --output-dir /tmp/review-replay
```

Build the upstream artifacts deterministically from local sample data in one
invocation:

```bash
atlas backtest portfolio-review-replay \
  --symbol DEMO-SYMBOL \
  --data data/sample/ohlcv_extended.csv \
  --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
  --output-dir /tmp/review-replay
```

## Replayed artifacts

The replay reads or builds these paper-only artifacts:

- `paper-human-review-pack.json` — CAND-001 review pack.
- `paper-human-review-ledger.json` — CAND-002 review ledger.
- `paper-human-review-policy.json` — CAND-003 review policy.

## Regression checks

The `regression_checks` array verifies deterministic replay invariants:

- `artifact_types_and_schemas_valid` — upstream artifacts have expected types and schemas.
- `paper_only_preserved` — every artifact declares `paper_only=true`.
- `non_executable_preserved` — every artifact declares `non_executable=true`.
- `live_path_blocked` — `live_submit_enabled` is `false` and live paths are blocked.
- `broker_provider_network_disabled` — broker, provider, and network flags are `false`.
- `notifications_and_orders_disabled` — notifications and order generation flags are `false`.
- `no_real_human_approval` — `real_human_approval` is `false` in every upstream artifact.
- `safety_claims_preserved` — upstream safety declares no profit claim and no live-readiness claim.
- `upstream_source_digests_consistent` — upstream digests are stable across replay.
- `stable_replay_canonicalization` — replay output is byte-stable for identical inputs.

## Overall replay statuses

- `paper_review_replay_passed` — replay succeeded, the paper chain is intact, and the live path is blocked.
- `paper_review_replay_follow_up` — more paper evidence is required before the regression gate is trusted.
- `paper_review_replay_rejected` — replay output did not match expectations or upstream digests were unstable.

## Gate summary

| Property | Value |
|---|---|
| `deterministic_replay_passed` | `true` |
| `paper_chain_intact` | `true` |
| `paper_follow_up_allowed` | `true` |
| `live_path_blocked` | `true` |
| `broker_submission_allowed` | `false` |
| `provider_execution_allowed` | `false` |
| `notification_sending_allowed` | `false` |
| `real_order_generation_allowed` | `false` |
| `real_human_approval` | `false` |

The gate summary confirms deterministic replay passed, paper chain intact,
paper follow up allowed, and live path blocked. The live path blocked row means
the regression gate explicitly denies every live execution gate while
permitting only paper follow-up. The `paper_chain_intact` and
`deterministic_replay_passed` rows mean the replay confirms the paper chain
remains intact.

## What This Replay Gate Is NOT

- It is NOT live trading approval.
- It is NOT a real human decision or authorization.
- It is NOT an executable order or broker submission.
- It is NOT a claim that the portfolio, strategy, or system is ready for live trading.
- It is NOT a guarantee of profit and does not claim that risk is eliminated.
- It does NOT call brokers, providers, notification services, or any network API.

The output is simulated for paper review only.

## Human review is required

Before any future live-related work, a human reviewer must:

1. Confirm the replay was generated offline from deterministic paper evidence.
2. Confirm no broker submission, provider call, notification, order generation, or real human approval occurred.
3. Confirm no live-readiness claim, no profit guarantee, and no absolute-safety claim was made.
4. Review the `regression_checks`, `replayed_artifacts`, `gate_summary`, and overall replay status.

## Demo

Run `bash scripts/demo_paper_human_review_replay.sh` to generate a deterministic
review replay and regression gate in a temporary directory.

## Relationship to v0.6.15

This feature is v0.6.15 CAND-004. The source/package version remains `0.6.14`,
`v0.6.15` remains the next planning line, and no tag, GitHub Release, or PyPI
publication is created by this candidate.

The replay gate closes the paper human review chain started by
[Paper Human Review Pack](paper-human-review-pack.md) (CAND-001), continued by
[Paper Human Review Ledger](paper-human-review-ledger.md) (CAND-002), and
validated by [Paper Human Review Policy Simulator](paper-human-review-policy.md)
(CAND-003).
