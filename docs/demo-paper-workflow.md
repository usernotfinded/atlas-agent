# Demo: Paper Workflow

This demo shows Atlas Agent running in **paper mode**, the default and safest way to explore the system. No live broker orders are sent.

## Prerequisites

```bash
pip install -e .
```

## Steps

### 1. Create a workspace

```bash
atlas init demo-workspace --template routine-trader
```

Expected output:

```
Atlas Agent workspace created: .../demo-workspace (template: routine-trader)
```

### 2. Enter the workspace

```bash
cd demo-workspace
```

### 3. Validate configuration

```bash
atlas validate
```

Expected output:

```
Configuration valid. Default mode: paper
Live trading enabled: False
```

The default trading mode is **paper**, and live trading is disabled.

### 4. Configure a trading symbol

Atlas does not choose a trading symbol for you. Set one before running:

```bash
atlas config set market.symbol AAPL
```

Use any symbol supported by your broker/API provider and paper/live setup.

### 5. Run a paper cycle

```bash
atlas run --mode paper
```

Expected behavior:

- Config loads from `.atlas/config.toml`.
- The system detects the market state (open or closed).
- **Paper mode** is used; no live broker API calls are made.
- The `RiskManager` evaluates any simulated orders against your limits.
- The `AuditWriter` records events to `audit/events.jsonl`.
- If no AI provider is configured, agentic workflows fail closed and ask you to configure a provider.

Nothing is traded. Nothing leaves your machine.

## What to verify

1. `audit/events.jsonl` contains a `run_started` event.
2. No pending orders were created in `pending_orders/`.
3. The demo does not require live broker credentials.

## Paper/sandbox support note

Paper and sandbox support depends on the selected broker/API provider and asset class. Some providers offer crypto simulation or testnet environments; others may not. Atlas does not assume crypto support.

## Next steps

- Configure a provider with `atlas configure` or edit `.atlas/config.toml`.
- Run `atlas backtest run --symbol DEMO-SYMBOL --data data/sample/ohlcv.csv` to exercise the deterministic backtest engine with sample data (replace with your own symbol and data).
- Review `docs/demo-risk-rejection.md` to see how Atlas blocks unsafe orders.
