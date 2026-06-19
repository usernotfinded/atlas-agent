# Paper Portfolio Proposal Sandbox

**Status:** v0.6.14 planning line.
**Scope:** Paper-only. Offline/no-provider/no-broker.
**Disclaimer:** Not financial advice. Not live readiness. No profit guarantee.

## Purpose
Convert scorecard evidence into conservative paper-only portfolio proposals.
This is not real allocation advice and does not promote any strategy or portfolio to live trading.

## Inputs
- Strategy scorecard evidence generated deterministically
- Deterministic sample fixture
- Strategy list
- Allocation guardrails (e.g. `max_strategy_weight`, `min_cash_weight`)

## Output Artifacts
- JSON proposal (`paper-portfolio-proposal.json`)
- Markdown proposal (`paper-portfolio-proposal.md`)
- Untracked/generated artifacts

## Proposal Decisions
Allocations result in one of the following decisions:
- `paper_portfolio_proposal`
- `paper_watchlist_portfolio`
- `needs_more_testing`
- `rejected`

## Safety Boundaries
- No provider calls.
- No broker calls.
- No credentials.
- No live trading.
- No autonomous live trading readiness.

## Relationship to prior documentation
- [Paper Portfolio Stress Constraints](paper-portfolio-stress.md)
- [Paper Strategy Scorecard](paper-strategy-scorecard.md)
- [Paper Strategy Walk-Forward](paper-strategy-walk-forward.md)
- [Paper Strategy Robustness](paper-strategy-robustness.md)
- [Paper Strategy Sensitivity](paper-strategy-sensitivity.md)
- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Provider Isolation](paper-provider-isolation.md)
- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
