# Backtest Report Schema Contract

## Overview

Backtest JSON reports produced by `atlas backtest run --report json` (and the
`result.json` files written to `.atlas/backtests/<run_id>/`) follow a stable
schema contract so that downstream tooling, tests, and reviewers can detect
silent structural drift.

## Schema Version

Current version: `backtest.report.v1`

This version is injected into every JSON report as `schema_version`.

## Required Top-Level Fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | `string` | Schema version identifier |
| `run_id` | `string` | Unique backtest run identifier |
| `status` | `string` | One of `completed`, `failed`, `blocked` |
| `config` | `object` | Backtest configuration snapshot |
| `metrics` | `object` | Computed performance metrics |
| `strategy_metadata` | `object` | Strategy name, version, parameters |
| `fills` | `array` | Executed trade fills |
| `equity_curve` | `array` | Per-observation equity values |
| `diagnostics` | `object` | Blocked orders, validation issues, etc. |
| `generated_at` | `string` | ISO timestamp when the report was rendered |
| `disclaimer` | `string` | Required research disclaimer |
| `report_type` | `string` | Always `backtest_research_summary` |

## Required Config Fields

| Field | Type | Description |
|---|---|---|
| `run_id` | `string` | Same as top-level `run_id` |
| `symbol` | `string` | Ticker symbol under test |
| `data_path` | `string` | Path to the CSV data file |
| `initial_equity` | `number` | Starting cash |
| `strategy_mode` | `string` | Strategy identifier |

Optional config fields (present when used):

| Field | Type | Description |
|---|---|---|
| `start_date` | `string` | Inclusive start date (`YYYY-MM-DD` or ISO) |
| `end_date` | `string` | Inclusive end date (`YYYY-MM-DD` or ISO) |

## Required Metric Fields

| Field | Type | Description |
|---|---|---|
| `total_return_pct` | `number` | Percentage total return |
| `max_drawdown_pct` | `number` | Percentage max drawdown |
| `trade_count` | `number` | Number of fills |
| `final_equity` | `number` | Ending portfolio value |
| `initial_equity` | `number` | Starting portfolio value |

Optional metric fields (present when computable):

| Field | Type | Description |
|---|---|---|
| `annualized_return_pct` | `number` | Annualized return estimate |
| `win_rate` | `number` | Fraction of winning closed trades |
| `sharpe_ratio` | `number` | Sharpe ratio estimate |
| `best_trade_pct` | `number` | Best single trade return |
| `worst_trade_pct` | `number` | Worst single trade return |
| `average_trade_pct` | `number` | Average trade return |
| `exposure_time_pct` | `number` | Percentage of time in market |
| `buy_and_hold_return_pct` | `number` | Benchmark return |

## Fill Item Fields

Each item in `fills` is an object with at least:

| Field | Type | Description |
|---|---|---|
| `side` | `string` | `"buy"` or `"sell"` |
| `symbol` | `string` | Ticker symbol |
| `quantity` | `number` | Shares/contracts filled |
| `price` | `number` | Fill price |
| `notional` | `number` | Gross notional value |

Optional fill fields:

| Field | Type | Description |
|---|---|---|
| `realized_pnl` | `number` | Realized profit/loss on sell fills |
| `commission` | `number` | Commission paid |
| `slippage` | `number` | Slippage cost |

## Equity Curve Item Fields

Each item in `equity_curve` is an object with:

| Field | Type | Description |
|---|---|---|
| `timestamp` | `string` | ISO timestamp |
| `equity` | `number` | Portfolio equity at that observation |

## Validation

Use `atlas_agent.backtest.report_schema.validate_backtest_report(data)` to
validate a report dict programmatically (raises on first error), or use
`collect_backtest_report_schema_errors(data)` to collect all schema violations
in one pass. You can also run:

```bash
python scripts/check_backtest_report_schema.py
```

to validate all existing `.atlas/backtests/*/result.json` files.

You can also validate existing runs via the CLI:

```bash
atlas backtest runs --validate --json
```

## Backward Compatibility

- New optional fields may be added without bumping the schema version.
- Removing a required field or changing its type requires a new schema version.
