# Paper Strategy Walk-Forward Stability

**Status:** v0.6.13 planning line
**Safety Boundaries:** Paper-only, offline/no-provider/no-broker/no-network
**Disclaimer:** Not financial advice. not live-readiness. No profit guarantee.

## Purpose

Walk-forward stability testing for paper follow-up. It extends CAND-025 strategy evaluation, CAND-026 sensitivity, and CAND-027 robustness to evaluate a strategy across multiple chronological rolling windows, producing stability metrics. This helps detect whether a strategy variant is overfit to a single window or remains reasonably stable across time.

## Data

Uses a deterministic OHLCV fixture: `data/sample/ohlcv_extended.csv`.
This is sample/synthetic/deterministic data. It does not prove market performance and does not imply future performance.

## How to Run

```bash
atlas backtest walk-forward \
  --data data/sample/ohlcv_extended.csv \
  --symbol DEMO-SYMBOL \
  --strategies buy_and_hold,moving_average_cross,rsi_mean_reversion \
  --window-size 60 \
  --step-size 30 \
  --output-dir /tmp/atlas-walk-forward
```

## Output Artifacts

- `strategy-walk-forward.json`: Deterministic JSON report.
- `strategy-walk-forward.md`: Markdown summary.
These are untracked generated artifacts.

## Walk-Forward Gate Decisions

Allowed decisions:
- `robust_paper_follow_up`: Stable across windows, paper-only follow-up.
- `window_sensitive_needs_more_testing`: Mixed valid results, potential single-window overfit.
- `needs_more_testing`: Valid data exists but is insufficient.
- `rejected`: A run failed, metrics were invalid, or a safety blocker exists.

Explicitly no live promotion is made by any decision.

## Safety Boundaries

- No provider calls.
- No broker calls.
- No credentials required.
- No live trading.
- No autonomous live trading readiness.

## Relationship to Docs

- [paper-strategy-evaluation.md](paper-strategy-evaluation.md)
- [paper-strategy-sensitivity.md](paper-strategy-sensitivity.md)
- [paper-strategy-robustness.md](paper-strategy-robustness.md)
- [autonomous-paper-workflow.md](autonomous-paper-workflow.md)
- [paper-provider-isolation.md](paper-provider-isolation.md)
- [bounded-live-autonomy-governance.md](bounded-live-autonomy-governance.md)
- [live-submit-safety-contract.md](live-submit-safety-contract.md)
