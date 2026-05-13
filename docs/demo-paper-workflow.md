# Demo: Paper Workflow

This demo shows Atlas Agent running in **paper mode**, the default and safest way to explore the system. No live broker orders are sent.

For a reproducible terminal run, use:

```bash
./scripts/demo_paper_workflow.sh
```

The script creates a temporary workspace, writes a safe discipline profile, sets `ATLAS-DEMO`, validates the workspace, runs a paper dry-run, runs the deterministic sample-data backtest with the `DEMO-SYMBOL` fixture, and verifies audit manifests when present.

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

### 4. Configure a demo trading symbol

Atlas does not choose a trading symbol for you. Set one before running:

```bash
atlas config set market.symbol ATLAS-DEMO
```

For real workflows outside this demo, choose a symbol supported by your selected data or broker/API provider.

### 5. Create a discipline profile

Agentic workflows require an explicit discipline profile. For the demo, create the default safe template:

```bash
atlas discipline setup --manual --yes
```

### 6. Run a paper dry-run

```bash
atlas run --mode paper --dry-run --symbol ATLAS-DEMO
```

Expected behavior:

- Config loads from `.atlas/config.toml`.
- The CLI prints the planned paper workflow without contacting a live broker.
- **Paper mode** is used; no live broker API calls are made.
- If no AI provider is configured, non-dry-run agentic workflows fail closed and ask you to configure a provider.

No live orders are sent.

## What to verify

1. `.atlas/config.toml` contains `market.symbol = "ATLAS-DEMO"`.
2. `.atlas/discipline.md` exists and validates.
3. No pending orders were created in `pending_orders/`.
4. The demo does not require live broker credentials.

## Paper/sandbox support note

Paper and sandbox support depends on the selected broker/API provider and asset class. Some providers offer crypto simulation or testnet environments; others may not. Atlas does not assume crypto support.

## Next steps

- Configure a provider with `atlas configure` or edit `.atlas/config.toml`.
- Run `atlas backtest run --symbol DEMO-SYMBOL --data data/sample/ohlcv.csv` to exercise the deterministic backtest engine with sample data (replace with your own symbol and data).
- Review `docs/demo-risk-rejection.md` to see how Atlas blocks unsafe orders.
