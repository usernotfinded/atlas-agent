# Paper Human Review Policy Simulator

> **v0.6.15 planning line.** Paper-only. Offline/no-provider/no-broker/no-network.
> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

The `atlas backtest portfolio-review-policy` command runs a deterministic,
paper-only, non-executable policy simulator against a paper human review pack
and ledger. The simulator evaluates every rule in `policy_rules` and records the
`policy_results`. The resulting artifact is strictly blocked-live: the live path
is blocked, broker submission is disallowed, provider execution is disallowed,
notification sending is disallowed, and real order generation is disallowed.
Only paper follow-up is allowed.

## What it does

- Reads or builds a paper human review pack and ledger from local sample data.
- Runs each policy rule against the upstream artifacts.
- Emits two artifacts:
  - `paper-human-review-policy.json`
  - `paper-human-review-policy.md`

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

Run the policy simulation against pre-existing CAND-001 and CAND-002 artifacts:

```bash
atlas backtest portfolio-review-policy \
  --review-pack /tmp/review-pack/paper-human-review-pack.json \
  --review-ledger /tmp/review-ledger/paper-human-review-ledger.json \
  --output-dir /tmp/review-policy
```

Build the upstream artifacts deterministically from local sample data in one
invocation:

```bash
atlas backtest portfolio-review-policy \
  --symbol DEMO-SYMBOL \
  --data data/sample/ohlcv_extended.csv \
  --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
  --output-dir /tmp/review-policy
```

## Policy rules

The `policy_rules` array contains the fixed rule set, for example:

- `require_non_executable_artifact` — artifact must declare `non_executable=true`.
- `require_paper_only_mode` — artifact must declare `mode=paper` and `paper_only=true`.
- `block_live_submit` — `live_submit_enabled` must be `false`.
- `block_broker_submission` — broker flags must be `false`.
- `block_provider_execution` — provider flags must be `false`.
- `block_real_notifications` — notification flags must be `false`.
- `block_order_generation` — order generation flags must be `false`.
- `require_manual_review_for_future_live_work` — future live work requires human review.
- `require_no_profit_claims` — upstream safety must declare `no_profit_claim=true`.
- `require_no_absolute_safety_claims` — upstream safety must declare `no_live_readiness_claim=true`.

## Overall policy statuses

- `paper_policy_passed_with_live_blocked` — all rules passed and the live path is blocked.
- `paper_policy_needs_more_evidence` — at least one rule needs more paper evidence.
- `paper_policy_manual_review_required` — a manual review is required.
- `paper_policy_blocked` — at least one rule blocked the policy.

## Policy result states

Each entry in `policy_results` can have one of the following states:

- `passed` — the rule passed.
- `blocked` — the rule blocked the policy.
- `needs_more_paper_evidence` — more paper evidence is required.
- `manual_review_required` — a human must review before proceeding.

## Gate summary

| Property | Value |
|---|---|
| `paper_follow_up_allowed` | `true` |
| `live_path_blocked` | `true` |
| `broker_submission_allowed` | `false` |
| `provider_execution_allowed` | `false` |
| `notification_sending_allowed` | `false` |
| `real_order_generation_allowed` | `false` |

The live path blocked row means the simulator explicitly denies every live
execution gate while permitting only paper follow-up.

## What This Policy Simulator Is NOT

- It is NOT live trading approval.
- It is NOT a real human decision or authorization.
- It is NOT an executable order or broker submission.
- It is NOT a claim that the portfolio, strategy, or system is ready for live trading.
- It is NOT a guarantee of profit and does not claim that risk is eliminated.
- It does NOT call brokers, providers, notification services, or any network API.

The output is simulated for paper review only.

## Human review is required

Before any future live-related work, a human reviewer must:

1. Confirm the policy report was generated offline from deterministic paper evidence.
2. Confirm no broker submission, provider call, notification, order generation, or real human approval occurred.
3. Confirm no live-readiness claim, no profit guarantee, and no absolute-safety claim was made.
4. Review the `policy_results`, `gate_summary`, and overall policy status.

## Demo

Run `bash scripts/demo_paper_human_review_policy.sh` to generate a deterministic
review policy simulation in a temporary directory.

## Relationship to v0.6.15

This feature is v0.6.15 CAND-003. The source/package version remains `0.6.14`,
`v0.6.15` remains the next planning line, and no tag, GitHub Release, or PyPI
publication is created by this candidate.
