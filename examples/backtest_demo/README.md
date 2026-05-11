# Backtest Demo

Atlas Agent v0.4.0 includes a deterministic
, local-first backtesting engine.

## Basic Run
Run a buy-and-hold backtest on the sample dataset:
```bash
atlas backtest run --symbol <SYMBOL> --data data/sample/ohlcv.csv
```

## Advanced Configuration
You can configure the simulation parameters:
```bash
atlas backtest run \
  --symbol <SYMBOL> \
  --data data/sample/ohlcv.csv \
  --initial-equity 50000 \
  --slippage-bps 10 \
  --commission-bps 5 \
  --json
```

## Results
Every run generates a report in `.atlas/backtests/<run_id>/`:
- `result.json`: Machine-readable results and metrics.
- `audit.log` (if enabled): Tamper-evident record of all simulated orders and risk decisions.

**Note:** Backtesting uses local CSV data and does not require API keys or network access. It is a simulation tool and historical results are not financial advice.

