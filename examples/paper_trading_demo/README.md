# Paper Trading Demo

> **Not financial advice.** Simulated results do not guarantee future
> performance.

Paper mode is the default Atlas Agent workflow. It records simulated activity
locally and does not submit orders to a live broker.

## Reproducible Demo

From the repository root:

```bash
./scripts/demo_paper_workflow.sh
```

The script creates a new temporary workspace, validates fail-closed settings,
runs a paper dry-run, and executes the bundled deterministic backtest.

## Manual Dry-Run

```bash
atlas init paper-workspace --template routine-trader
cd paper-workspace
atlas discipline setup --manual --yes
atlas config set market.symbol ATLAS-DEMO
atlas validate
atlas doctor --json
atlas run --mode paper --dry-run --symbol ATLAS-DEMO
```

The adjacent [`config.toml`](config.toml) is a non-secret review example. It
keeps live trading, live submit, and leverage disabled. Do not add credentials
to it.

See the canonical [Paper-Trading Guide](../../docs/paper-trading-guide.md) for
the complete workflow, safety boundary, backtest step, and expected failures.
Reviewers should use the
[Reviewer Golden-Path Validation Guide](../../docs/reviewer-golden-path.md) as
the single runnable verification sequence.
