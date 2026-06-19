# Paper Portfolio Monitoring Simulation

## Status

v0.6.14 planning line. Paper-only. Offline/no-provider/no-broker/no-network.
No real notification sending. Not financial advice. Not live readiness.
Not a profit guarantee. Not production-ready.

## Purpose

Simulate paper-only recheck/watchlist behaviour from paper portfolio proposal
and stress artifacts over deterministic local sample data monitoring windows.

This is not live monitoring, not a real-time alerting system, not broker
monitoring, not provider monitoring, and not real allocation advice. It does
not submit orders, does not contact providers or brokers, does not send real
notifications, and does not promote any strategy or portfolio to live trading
or autonomous live trading.

## Inputs

- A paper portfolio proposal from `atlas backtest portfolio-proposal`
- A paper portfolio stress report from `atlas backtest portfolio-stress`
- A deterministic sample OHLCV fixture such as `data/sample/ohlcv_extended.csv`
- A local strategy list
- Monitoring rules: `monitor_window`, `recheck_threshold`, allocation and
  drawdown constraints

## Monitoring Triggers

- `allocation_drift`: simulated allocation drift exceeds the recheck threshold
  over a monitoring window
- `cash_reserve_breach`: cash reserve weight falls below the minimum
- `drawdown_breach`: simulated portfolio drawdown exceeds the paper guardrail
- `stress_watchlist`: stress report status is watchlist or needs-more-testing
- `stale_artifact`: proposal or stress status is rejected or insufficient
- `insufficient_data`: not enough return periods for a monitoring window

## Output Artifacts

The command writes untracked/generated artifacts to the requested output
directory:

- JSON monitoring report: `paper-portfolio-monitoring.json`
- Markdown monitoring report: `paper-portfolio-monitoring.md`

## Monitoring Decisions

- `paper_monitor_ok`: all paper-only simulated monitoring constraints pass;
  paper-only follow-up only. This is not a live readiness indicator.
- `paper_monitor_watchlist`: weak or borderline paper-only result; human
  review recommended
- `needs_recheck`: data/artifacts are valid but require another paper run
  or more evidence
- `rejected`: invalid artifact, hard breach, or unacceptable simulated risk

Even `paper_monitor_ok` does NOT imply live readiness, production readiness,
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
- Monitoring pass is not future-performance proof
- Monitoring pass is not live-readiness or autonomous-live-readiness

## Relationship to v0.6.14 CAND-001/CAND-002

CAND-003 builds on the CAND-001 paper portfolio proposal sandbox and
CAND-002 paper portfolio stress constraints:

- [Paper Portfolio Proposal Sandbox](paper-portfolio-proposal.md)
- [Paper Portfolio Stress Constraints](paper-portfolio-stress.md)
- `scripts/demo_paper_portfolio_proposal.sh`
- `scripts/demo_paper_portfolio_stress.sh`
- `scripts/check_paper_portfolio_proposal.py`
- `scripts/check_paper_portfolio_stress.py`
- `tests/test_paper_portfolio_proposal.py`
- `tests/test_paper_portfolio_stress.py`
