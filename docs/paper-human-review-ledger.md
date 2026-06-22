# Paper Human Review Ledger

> **v0.6.15 planning line.** Paper-only. Offline/no-provider/no-broker/no-network.
> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

The `atlas backtest portfolio-review-ledger` command generates a deterministic,
paper-only, non-executable human review decision ledger from a paper human
review pack. The ledger is simulated: it records non-binding decision entries
and a gate summary that explicitly denies live approval, broker submission, and
real human approval, while allowing only paper follow-up.

## What it does

- Reads or builds a paper human review pack from local sample data.
- Produces a non-executable ledger with simulated decision entries.
- Emits two artifacts:
  - `paper-human-review-ledger.json`
  - `paper-human-review-ledger.md`

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

Generate a ledger from a pre-existing CAND-001 review pack:

```bash
atlas backtest portfolio-review-ledger \
  --review-pack /tmp/review-pack/paper-human-review-pack.json \
  --output-dir /tmp/review-ledger
```

Generate a ledger and build the review pack deterministically from local
sample data in one invocation:

```bash
atlas backtest portfolio-review-ledger \
  --symbol DEMO-SYMBOL \
  --data data/sample/ohlcv_extended.csv \
  --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
  --output-dir /tmp/review-ledger
```

## Review ledger statuses

- `paper_review_ledger_open` — ledger is open for human review.
- `paper_review_ledger_follow_up` — one or more paper-only follow-up decisions were raised.
- `paper_review_ledger_rejected` — the underlying pack was rejected from review.

## Decision statuses

- `paper_follow_up_allowed` — follow-up is constrained to paper workflows only.
- `needs_more_paper_evidence` — additional paper evidence is required.
- `rejected_from_paper_follow_up` — item was rejected from paper follow-up.
- `manual_review_required` — a human must review the item before any follow-up.
- `blocked_by_missing_evidence` — decision blocked by missing evidence.

## Human review is required

Before any future live-related work, a human reviewer must:

1. Confirm the ledger was generated offline from deterministic paper evidence.
2. Confirm no broker submission, provider call, notification, order generation, or real human approval occurred.
3. Confirm no live-readiness claim, no profit guarantee, and no absolute-safety claim was made.
4. Decide whether to perform more paper testing, reject the candidate, or queue it for later review.

## Demo

Run `bash scripts/demo_paper_human_review_ledger.sh` to generate a deterministic
review ledger in a temporary directory.

## Relationship to v0.6.15

This feature is v0.6.15 CAND-002. The source/package version remains `0.6.14`,
`v0.6.15` remains the next planning line, and no tag, GitHub Release, or PyPI
publication is created by this candidate.

The next step in the v0.6.15 planning line is the
[Paper Human Review Policy Simulator](paper-human-review-policy.md) (CAND-003), which
evaluates the CAND-001 review pack and this CAND-002 ledger against explicit
blocked-live policy rules. The chain closes with the
[Paper Human Review Replay and Regression Gate](paper-human-review-replay.md)
(CAND-004), which replays the CAND-001/002/003 artifacts and verifies the paper
chain remains intact.
