# Paper Strategy Scorecard

**Status:** v0.6.13 planning line; paper-only; synthetic/sample-data only; offline/no-provider/no-broker; not financial advice; not live readiness; no profit guarantee; not production-ready.

## Purpose

The paper strategy scorecard aggregates evaluation, sensitivity, robustness, and walk-forward paper evidence. It provides a conservative paper-only candidate ledger summarizing a strategy's multi-dimensional backtest results.

**Crucially, this is not a live promotion.** Candidate status does not imply future market performance and does not promote any strategy to live trading or autonomous live trading.

## Evidence Streams

The scorecard aggregates:
- **Strategy evaluation:** (Base metrics and performance)
- **Sensitivity matrix:** (Parameter stability)
- **Multi-regime robustness:** (Performance across synthetic deterministic regimes)
- **Walk-forward stability:** (Chronological step performance)

## How to run

The deterministic scorecard can be run using the `atlas backtest scorecard` command:

```bash
atlas backtest scorecard \
  --data data/sample/ohlcv_extended.csv \
  --fixtures data/sample/regimes/ohlcv_uptrend.csv,data/sample/regimes/ohlcv_downtrend.csv,data/sample/regimes/ohlcv_flat.csv,data/sample/regimes/ohlcv_volatile.csv \
  --symbol DEMO-SYMBOL \
  --strategies buy_and_hold,moving_average_cross,rsi_mean_reversion \
  --output-dir <temp-dir>
```

This uses the sample synthetic data fixture and `DEMO-SYMBOL`, and output artifacts to the temporary directory.

## Output Artifacts

The command produces:
- **`strategy-scorecard.json`**: A JSON envelope containing structured evidence streams, metric aggregations, rankings, and decisions.
- **`strategy-scorecard.md`**: A human-readable Markdown summary of the scorecard evaluation.

All generated output is untracked.

## Scorecard Decisions

A strategy will receive one of the following decisions:
- `paper_follow_up_candidate`: Strong evidence across all evaluation streams; approved for further paper-only follow-up.
- `paper_watchlist`: Strategy shows some sensitivity or mixed results but merits continued paper-only tracking.
- `needs_more_testing`: Evidence is incomplete, insufficient, or inconclusive.
- `rejected`: Hard failures, metrics violation, or safety blockers identified in one or more streams.

**No scorecard decision is an approval for live trading or production use.**

## Safety Boundaries

- **No provider calls:** Generates reports offline.
- **No broker calls:** Does not connect to live market adapters.
- **No credentials:** Requires zero private keys or credentials.
- **No live trading:** Explicitly isolated from execution APIs.
- **No autonomous live trading readiness:** Does not claim or prepare systems for autonomous execution in live environments.

## Relationship to other documentation

- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Strategy Sensitivity](paper-strategy-sensitivity.md)
- [Paper Strategy Robustness](paper-strategy-robustness.md)
- [Paper Strategy Walk-Forward](paper-strategy-walk-forward.md)
- [Autonomous Paper Workflow](autonomous-paper-workflow.md)
- [Paper Provider Isolation](paper-provider-isolation.md)
- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
- [Live Submit Safety Contract](live-submit-safety-contract.md)
