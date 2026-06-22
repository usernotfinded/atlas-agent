# Paper Human Review Pack

> **v0.6.15 planning line.** Paper-only. Offline/no-provider/no-broker/no-network.
> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

The `atlas backtest portfolio-review-pack` command generates a deterministic,
paper-only, non-executable human review dossier from existing paper portfolio
evidence. It is the safest next step toward human-approved live suggestions:
it helps a human reviewer understand what the paper system would like reviewed
next, while making it impossible to confuse the output with an executable
trading instruction.

## What it does

- Reads or builds paper portfolio evidence (proposal, stress, monitoring,
  recheck, dossier, replay) from local sample data.
- Produces a non-executable review pack with explicit review items.
- Emits two artifacts:
  - `paper-human-review-pack.json`
  - `paper-human-review-pack.md`

## What it does NOT do

- It does NOT enable live trading.
- It does NOT generate executable orders.
- It does NOT submit anything to brokers.
- It does NOT call providers.
- It does NOT send notifications.
- It does NOT claim live readiness or autonomous live trading readiness.
- It is NOT financial advice, NOT live ready, and NOT a profit guarantee.
- It makes NO account-specific instructions.
- It makes NO absolute safety claims and NO claims that risk is eliminated.

## Safety disclaimer

This command and its output are strictly paper-only and non-executable.
There is no broker submission, no provider calls, no real notifications,
no orders generated, no account-specific instructions, no profit guarantees,
no absolute safety claims, no claims that risk is eliminated, no live-readiness
claim, and no autonomous live trading readiness claim. Human review is required
before any future live-related work.

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
| `not_financial_advice` | `true` |
| `not_live_ready` | `true` |

## CLI usage

```bash
atlas backtest portfolio-review-pack \
  --symbol DEMO-SYMBOL \
  --data data/sample/ohlcv_extended.csv \
  --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
  --output-dir /tmp/review-pack
```

## Review pack statuses

- `paper_review_pack_open` — review pack is open for human review.
- `paper_review_pack_follow_up` — one or more paper-only follow-up items were raised.
- `paper_review_pack_rejected` — the underlying dossier was rejected from review.

## Review item statuses

- `needs_human_review` — a human must review the item before any follow-up.
- `needs_more_paper_testing` — additional paper testing is required.
- `rejected_from_review` — item was rejected from review.
- `paper_only_follow_up` — follow-up is constrained to paper workflows only.

## Human review is required

Before any future live-related work, a human reviewer must:

1. Confirm the pack was generated offline from deterministic paper evidence.
2. Confirm no broker submission, provider call, notification, or order generation occurred.
3. Confirm no live-readiness claim, no profit guarantee, and no absolute-safety claim was made.
4. Decide whether to perform more paper testing, reject the candidate, or queue it for later review.

## Demo

Run `bash scripts/demo_paper_human_review_pack.sh` to generate a deterministic
review pack in a temporary directory.

## Relationship to v0.6.15

This feature is v0.6.15 CAND-001. The source/package version remains `0.6.14`,
`v0.6.15` remains the next planning line, and no tag, GitHub Release, or PyPI
publication is created by this candidate.
