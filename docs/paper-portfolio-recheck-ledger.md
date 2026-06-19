# Paper Portfolio Recheck Ledger and Human Review Queue

## Status

v0.6.14 planning line. Paper-only. Offline/no-provider/no-broker/no-network.
No real notification sending. Not financial advice. Not live readiness.
Not a profit guarantee. Not production-ready.

## Purpose

Generate a deterministic paper-only recheck ledger and human review queue that
consumes simulated paper portfolio proposal, stress, and monitoring artifacts.

This is not live monitoring, not a real-time alerting system, not broker
monitoring, not provider monitoring, and not real allocation advice. It does
not submit orders, does not contact providers or brokers, does not send real
notifications, and does not promote any strategy or portfolio to live trading
or autonomous live trading.

## Inputs

- A deterministic sample OHLCV fixture such as `data/sample/ohlcv_extended.csv`
- A local strategy list
- Recheck boundaries: `monitor_window`, `recheck_threshold`, allocation and
  drawdown constraints

## Output Artifacts

The command writes untracked/generated artifacts to the requested output
directory:

- JSON recheck ledger report: `paper-portfolio-recheck-ledger.json`
- Markdown review queue report: `paper-portfolio-review-queue.md`

## Recheck Decisions

- `paper_review_clear`: no review triggers found; paper-only follow-up only.
- `paper_review_watchlist`: trigger detected requiring human paper-only review.
- `paper_recheck_required`: artifact needs re-generation or more evidence.
- `paper_rejected`: hard breach detected, offline sandbox rejected.

Even `paper_review_clear` does NOT imply live readiness, production readiness,
or autonomous live trading readiness. It is not a profit guarantee and
does not imply future performance.

## Safety Boundaries

- No provider calls
- No broker calls
- No credentials
- No live trading
- No notifications sent
- No autonomous live trading readiness
- No production readiness claim
- No orders are submitted
- Review pass is not future-performance proof
- Review pass is not live-readiness or autonomous-live-readiness

## Relationship to v0.6.14 CAND-001/CAND-002/CAND-003

CAND-004 builds on the previous paper portfolio artifacts:

- [Paper Portfolio Proposal Sandbox](paper-portfolio-proposal.md)
- [Paper Portfolio Stress Constraints](paper-portfolio-stress.md)
- [Paper Portfolio Monitoring](paper-portfolio-monitoring.md)
