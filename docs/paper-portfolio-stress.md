# Paper Portfolio Stress Constraints

## Status

v0.6.14 planning line. Paper-only. Offline/no-provider/no-broker/no-network.
Not financial advice. Not live readiness. Not a profit guarantee.

## Purpose

Stress-test paper portfolio proposals under deterministic synthetic scenarios.
This is not real allocation advice, does not submit orders, and does not
promote any strategy or portfolio to live trading.

## Inputs

- A paper portfolio proposal from `atlas backtest portfolio-proposal`
- A deterministic sample OHLCV fixture such as `data/sample/ohlcv_extended.csv`
- A local strategy list
- Paper stress constraints for drawdown, scenario loss, concentration, and cash

## Stress Scenarios

- `flash_crash`: broad negative shock with a small partial rebound
- `volatility_spike`: alternating large up/down paper returns
- `liquidity_gap`: one-time gap down with limited recovery
- `sideways_chop`: noisy flat movement
- `slow_drawdown`: gradual sustained decline

## Output Artifacts

The command writes untracked/generated artifacts to the requested output
directory:

- JSON stress report: `paper-portfolio-stress.json`
- Markdown stress report: `paper-portfolio-stress.md`

## Stress Decisions

- `paper_stress_pass`: all paper stress constraints pass; paper-only follow-up only
- `paper_stress_watchlist`: scenario remains valid but weak near a paper guardrail
- `needs_more_testing`: metrics are valid but proposal evidence is insufficient or inconclusive
- `rejected`: hard failure, invalid weights, invalid metrics, or stress breach

## Safety Boundaries

- No provider calls
- No broker calls
- No credentials
- No live trading
- No autonomous live trading readiness
- No production readiness claim
- No orders are submitted
- Stress pass is not future-performance proof

## Relationship to v0.6.14 CAND-001

CAND-002 builds on the CAND-001 paper portfolio proposal sandbox:

- [Paper Portfolio Proposal Sandbox](paper-portfolio-proposal.md)
- `scripts/demo_paper_portfolio_proposal.sh`
- `scripts/check_paper_portfolio_proposal.py`
- `tests/test_paper_portfolio_proposal.py`
