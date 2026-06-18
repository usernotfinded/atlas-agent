# Paper Strategy Robustness Report

**Status:** v0.6.13 planning line.
**Mode:** Paper-only.
**Connectivity:** Offline / no-provider / no-broker / no-network.
**Legal:** Not financial advice. No profit guarantee.
**Scope:** Not live-readiness. Not autonomous-live-readiness.

## Purpose

Multi-regime robustness testing evaluates paper strategy behavior across several
deterministic synthetic market regimes. It extends CAND-025 strategy evaluation
and CAND-026 parameter sensitivity by checking whether a strategy only behaves
well on one fixture or deserves more paper-only follow-up across different
conditions.

This report is a paper research artifact only. It does not prove market
performance and does not promote any strategy to live trading.

## Fixtures

The bundled fixtures are deterministic, synthetic/sample OHLCV data:

- `data/sample/regimes/ohlcv_uptrend.csv` — steadily rising synthetic prices.
- `data/sample/regimes/ohlcv_downtrend.csv` — steadily falling synthetic prices.
- `data/sample/regimes/ohlcv_flat.csv` — flat/choppy synthetic prices.
- `data/sample/regimes/ohlcv_volatile.csv` — wider synthetic price swings.

They are useful for local repeatability and overfit detection only. They do not
prove future market performance.

## How to run

```bash
atlas backtest robustness \
  --fixtures data/sample/regimes/ohlcv_uptrend.csv,data/sample/regimes/ohlcv_downtrend.csv,data/sample/regimes/ohlcv_flat.csv,data/sample/regimes/ohlcv_volatile.csv \
  --symbol DEMO-SYMBOL \
  --strategies buy_and_hold,moving_average_cross,rsi_mean_reversion \
  --output-dir <temp-dir>
```

This uses `DEMO-SYMBOL`, local sample fixtures, and a temporary output
directory. It requires no provider keys, broker credentials, internet access, or
live mode.

## Output artifacts

- `strategy-robustness.json` — structured multi-regime paper evidence.
- `strategy-robustness.md` — human-readable regime matrix, ranking, and safety
  notes.

Generated artifacts should remain untracked unless a later evidence task
explicitly requests a checked-in sample.

## Robustness gate decisions

- `robust_paper_follow_up`: at least one variant completed every synthetic
  regime with valid paper-candidate gates; paper-only follow-up only.
- `regime_sensitive_needs_more_testing`: mixed valid results suggest regime
  sensitivity or possible one-fixture overfit.
- `needs_more_testing`: valid data exists, but evidence is insufficient for
  robust paper follow-up.
- `rejected`: a run failed, metrics were invalid, or a safety blocker exists.

No decision promotes a strategy to live trading. Even
`robust_paper_follow_up` is not live-readiness.

## Safety boundaries

- No provider calls.
- No broker calls.
- No credentials.
- No live trading.
- No autonomous-live-readiness.
- No production trading readiness.
- Robustness across synthetic fixtures does not imply future performance.

## Relationship to docs

- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Strategy Sensitivity Evaluation](paper-strategy-sensitivity.md)
- [Autonomous Paper Workflow](autonomous-paper-workflow.md)
- [Paper Provider Isolation](paper-provider-isolation.md)
- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
- [Live Submit Safety Contract](live-submit-safety-contract.md)
