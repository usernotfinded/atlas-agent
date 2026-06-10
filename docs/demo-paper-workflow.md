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

## Expected output

When the script succeeds, you will see output similar to:

```text
Atlas Agent paper workflow demo
Workspace: /tmp/atlas-agent-demo.XXXXXX
Symbol: ATLAS-DEMO
Sample-data backtest symbol: DEMO-SYMBOL
This demo is paper-only and does not require broker credentials.

$ atlas init ... --template routine-trader
Atlas Agent workspace created: ... (template: routine-trader)

$ atlas discipline setup --manual --yes
Discipline profile created at .atlas/discipline.md

$ atlas config set market.symbol ATLAS-DEMO
Updated market.symbol in config.toml

$ atlas validate
...
[✓] Live trading
    Disabled by default.
...
Status: not ready for agentic paper workflows
...

$ atlas run --mode paper --dry-run --symbol ATLAS-DEMO
Atlas Agent Plan
...
Plan: Market open. Paper trade cycle.

$ atlas backtest run --symbol DEMO-SYMBOL --data ...
Backtest complete: DEMO-SYMBOL
...
Report saved to: .atlas/backtests/.../result.json

$ atlas audit verify --all
No manifests found.

Demo complete. Review the temporary workspace at: ...
```

Notes:
- `atlas validate` may report `Status: not ready for agentic paper workflows` because no AI provider API key is configured. This is expected and safe; the backtest and dry-run steps still complete.
- `atlas audit verify --all` may report `No manifests found` because the dry-run does not create run manifests. This is expected.
- The backtest report path includes a timestamp; the exact path will vary.

## Expected artifacts

- A temporary workspace directory (printed at the start and end of the demo).
- `.atlas/config.toml` with `market.symbol = "ATLAS-DEMO"`.
- `.atlas/discipline.md` with the default safe discipline profile.
- `.atlas/backtests/bt-<timestamp>/result.json` and `report.md` from the deterministic sample-data backtest.

For a complete indexed view of each artifact, its content summary, and the safety invariant it demonstrates, see [Demo Artifact Index](demo-artifact-index.md).

## Success criteria

- The script exits with code `0`.
- No broker credentials or provider API keys are required.
- No live orders are submitted.
- The backtest runs and produces a local report.
- The workspace is created in a temporary directory and is safe to delete after review.

## Common failures

| Symptom | Likely cause | Resolution |
|---|---|---|
| `Missing prerequisite: sample data not found` | The repository was not cloned or `data/sample/ohlcv.csv` is missing. | Clone the repo and ensure sample data is present. |
| `atlas: command not found` or Python import error | Atlas is not installed in editable mode. | Run `python3.11 -m pip install -e .` from the repository root. |
| `Status: not ready for agentic paper workflows` | No AI provider API key is configured. | This is expected and safe for the demo. The backtest and dry-run still complete. |

## Safety note

This demo is **paper-only and local-only**. It does not:
- submit live orders,
- call provider APIs,
- use the network,
- load credentials,
- or enable live trading.

It is a proof of workflow mechanics, not a live-trading setup or performance claim.

## Paper/sandbox support note

Paper and sandbox support depends on the selected broker/API provider and asset class. Some providers offer crypto simulation or testnet environments; others may not. Atlas does not assume crypto support.

## Next steps

- Configure a provider with `atlas configure` or edit `.atlas/config.toml`.
- Run `atlas backtest run --symbol DEMO-SYMBOL --data data/sample/ohlcv.csv` to exercise the deterministic backtest engine with sample data (replace with your own symbol and data).
- Review `docs/demo-risk-rejection.md` to see how Atlas blocks unsafe orders.
