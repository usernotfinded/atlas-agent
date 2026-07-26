# Paper Strategy Evaluation

## Status

This is a v0.6.13 planning-line feature. It is paper-only, offline,
no-provider/no-broker/no-network, and uses bundled sample data by default.

This is not financial advice. It is not live readiness, not autonomous-live
readiness, not production-ready, and not a profit guarantee.

## Purpose

Paper strategy evaluation gives Atlas a deterministic way to compare multiple
backtest strategies on local OHLCV data and decide which strategies deserve
more paper follow-up.

This supports the staged autonomy path by adding a conservative L1 paper gate:
paper workflows can compare, rank, and reject strategies locally before any
future human-reviewed live suggestion path is considered.

## How to run

Use the bundled fixture and documentation symbol:

```bash
OUTPUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/atlas-paper-strategy-evaluation.XXXXXX")"
atlas backtest compare \
  --data data/sample/ohlcv.csv \
  --symbol DEMO-SYMBOL \
  --strategies buy_and_hold,moving_average_cross,rsi_mean_reversion \
  --output-dir "$OUTPUT_DIR"
```

The same flow is wrapped by:

```bash
bash scripts/demo_paper_strategy_evaluation.sh
```

## Output artifacts

The command writes generated, untracked artifacts into the selected output
directory:

- `strategy-evaluation.json`
- `strategy-evaluation.md`

The JSON artifact has `artifact_type: paper_strategy_evaluation`, `mode: paper`,
`provider_required: false`, `broker_required: false`, `network_required: false`,
and `live_readiness: false`.

## What each strategy entry reports

Every entry carries the same keys whether the run was evaluated or failed, so a
reader never has to branch on status:

| Key | Meaning |
|---|---|
| `parameters` | The parameters the run actually used, including defaults. |
| `metrics` | Return, drawdown, win rate, trade count, and related figures. |
| `benchmark` | The benchmark the run was measured against, plus `excess_return_pct`. |
| `paper_gate` | The follow-up decision and its reason. |
| `safety_blockers` | Risk-gate rejections recorded during the run. |
| `diagnostics` | Run id, status, blocked-order count, and the strategy validation record. |

`excess_return_pct` is the strategy's return minus the benchmark's. A ranking
without it can say which strategy placed first among those compared, but not
whether any of them beat simply holding the asset.

## Strategy parameters

Strategies run on their own defaults unless overridden:

```bash
atlas backtest compare \
  --data data/sample/ohlcv.csv \
  --symbol DEMO-SYMBOL \
  --strategies moving_average_cross \
  --strategy-parameters '{"moving_average_cross": {"short_window": 2, "long_window": 6}}' \
  --output-dir "$OUTPUT_DIR"
```

Malformed input fails the command rather than falling back to defaults: a
comparison that quietly ignored the requested parameters would report a run
nobody asked for. Overrides that parse are still coerced and range-checked by
each strategy's own parameter specs, and the risk gate applies unchanged — an
allocation above a notional or exposure limit is blocked at the engine.

## Paper gate decisions

Allowed paper gate decisions are:

- `paper_candidate` — eligible for more paper-only follow-up.
- `needs_more_testing` — deterministic run completed, but sample size, trade
  activity, or metrics are not enough for candidate status.
- `rejected` — the backtest failed, metrics were invalid, or a safety blocker
  such as a `RiskManager` rejection occurred.

No decision promotes a strategy to live trading. The gate is only for paper
research follow-up.

## Safety boundaries

- No provider calls.
- No broker calls.
- No credentials.
- No live trading.
- No autonomous live trading readiness.
- No profit guarantee.
- No version bump, tag, GitHub Release, or PyPI publication.

## Related documents

- [Autonomous Paper Workflow](autonomous-paper-workflow.md)
- [Paper Mode Provider Isolation](paper-provider-isolation.md)
- [Paper Strategy Sensitivity Evaluation](paper-strategy-sensitivity.md)
- [Paper Strategy Robustness Report](paper-strategy-robustness.md)
- [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md)
- [Live Submit Safety Contract](live-submit-safety-contract.md)
