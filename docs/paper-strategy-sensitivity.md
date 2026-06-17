# Paper Strategy Sensitivity Evaluation

**Status:** v0.6.13 planning line.
**Mode:** Paper-only.
**Connectivity:** Offline / no-provider / no-broker.
**Legal:** Not financial advice. Not a profit guarantee.
**Scope:** Not live readiness. Not autonomous live readiness.

## Purpose

The deterministic parameter/sensitivity testing provides a paper-only evaluation gate for strategies.
It extends the CAND-025 strategy evaluation by testing strategies across multiple parameter variants (e.g. short vs long moving average windows, or RSI oversold/overbought thresholds).
This supports staged autonomy by reducing the likelihood of overfitting to a single parameter set.

## Fixture

This command requires a deterministic offline OHLCV fixture, such as `data/sample/ohlcv_extended.csv`.
This data is **sample/synthetic** and deterministic. It is **not market-proof** and does not guarantee future performance on live markets.

## How to run

```bash
atlas backtest sensitivity \
  --data data/sample/ohlcv_extended.csv \
  --symbol DEMO-SYMBOL \
  --strategies buy_and_hold,moving_average_cross,rsi_mean_reversion \
  --output-dir <temp-dir>
```

This uses a temporary output directory, the `DEMO-SYMBOL`, and requires no live credentials or internet access.

## Output artifacts

- **JSON Report:** `strategy-sensitivity.json` (Structured test evidence)
- **Markdown Report:** `strategy-sensitivity.md` (Human-readable matrix and ranking)

## Sensitivity Gate Decisions

A strategy variant is evaluated and receives one of the following decisions:
- `paper_candidate`: The variant meets minimum backtest metrics (finite returns, valid drawdowns) and is eligible for more paper-only follow-up.
- `needs_more_testing`: The run completed, but metrics like total return or row count did not meet the required threshold.
- `rejected`: The run failed, or it hit a hard safety blocker (e.g. max drawdown exceeded demo thresholds).

**Explicit Constraint:** No decision implies live-readiness. Even a `paper_candidate` decision does NOT promote the strategy to live trading.

## Safety Boundaries

- **No provider calls.**
- **No broker calls.**
- **No credentials.**
- **No live trading.**
- **No autonomous live trading readiness.**

## Relationship to docs

- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Strategy Sensitivity Evaluation](paper-strategy-sensitivity.md)
- [Autonomous Paper Workflow](autonomous-paper-workflow.md)
- [Paper Provider Isolation](paper-provider-isolation.md)
- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
- [Live Submit Safety Contract](live-submit-safety-contract.md)
