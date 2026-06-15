# Paper-Trading Guide

> **Not financial advice.** Atlas Agent is software, not a financial advisor.
> Trading and simulated trading involve uncertainty, and historical or simulated
> results do not guarantee future performance.

This guide is the canonical local setup path for Atlas Agent paper workflows.
Paper mode records simulated activity locally and does not submit orders to a
live broker.

## Safety Boundary

The workflow below:

- keeps `trading_mode = "paper"`;
- keeps live trading and live submit disabled;
- uses no broker credentials or provider API keys;
- makes no provider, broker, exchange, or remote API calls;
- runs only a dry-run and a deterministic sample-data backtest;
- preserves risk checks, approval gates, the kill switch, and audit behavior.

Paper results are simulations. They do not prove profitability, execution
quality, liquidity, or suitability for live trading.

## Fastest Safe Demo

From the repository root:

```bash
./scripts/demo_paper_workflow.sh
```

The script creates a new temporary workspace, configures a demo symbol, runs
local validation and redacted diagnostics, prints a paper dry-run, executes a
deterministic backtest, and verifies any local audit manifests. It refuses to
reuse an existing `DEMO_WORKSPACE`.

See [Demo: Paper Workflow](demo-paper-workflow.md) for expected output and
[Demo Artifact Index](demo-artifact-index.md) for the generated file map.

## Manual Setup

### 1. Install the local checkout

```bash
python3.11 -m pip install -e .
```

### 2. Create a separate workspace

```bash
atlas init paper-workspace --template routine-trader
cd paper-workspace
```

Do not reuse a live-trading workspace for this walkthrough.

### 3. Create the discipline profile

```bash
atlas discipline setup --manual --yes
```

The discipline profile is required by agentic workflows. Creating it does not
authorize provider execution, broker execution, or live trading.

### 4. Set an explicit demonstration symbol

```bash
atlas config set market.symbol ATLAS-DEMO
```

`ATLAS-DEMO` is a documentation symbol. The bundled backtest fixture uses
`DEMO-SYMBOL`.

### 5. Validate local safety state

```bash
atlas validate
atlas doctor --json
```

Confirm that validation reports paper mode and disabled live trading.
`atlas doctor` is read-only: it reports local credential presence and safety
state using redacted values, skips network checks, and does not construct a
submit-capable broker client.

See [Broker and Provider Preflight Diagnostics](preflight-diagnostics.md) for
the complete output and safety contract.

### 6. Print the paper plan without execution

```bash
atlas run --mode paper --dry-run --symbol ATLAS-DEMO
```

The dry-run prints the planned workflow. It does not call a provider, contact a
broker, create an approval, create a pending live order, or submit an order.

### 7. Run the deterministic local backtest

From the repository root, or with an absolute path to the fixture:

```bash
atlas backtest run \
  --data data/sample/ohlcv.csv \
  --symbol DEMO-SYMBOL
```

The backtest reads the local CSV and writes local report artifacts. It makes no
network calls.

### 8. Inspect local evidence

```bash
atlas backtest runs --validate --json
atlas audit verify --all
```

An empty audit-manifest result is valid after a dry-run because dry-run does not
create a run manifest.

## Annotated Safe Configuration

The checked-in example at
[`examples/paper_trading_demo/config.toml`](../examples/paper_trading_demo/config.toml)
contains only non-secret local settings:

```toml
trading_mode = "paper"

[broker]
provider = "none"
enable_live_trading = false
enable_live_submit = false
paper_broker_default = "paper"

[market]
symbol = "ATLAS-DEMO"

[risk]
allow_leverage = false
max_order_notional = 100.0
max_position_notional = 100.0
max_portfolio_exposure = 1000.0

[audit]
enabled = true
redact_secrets = true
log_raw_prompts = false
log_provider_text = false
```

Important properties:

- `provider = "none"` avoids configuring a live broker adapter.
- Both live opt-ins remain `false`.
- Leverage remains disabled.
- Audit redaction remains enabled.
- No API keys, tokens, passwords, account IDs, or webhook URLs belong in this
  file.

Use `atlas config set` for normal edits. Treat the example as a review aid, not
as permission to remove or relax any gate.

## Expected Safe Failures

- Missing provider credentials can make a non-dry-run agentic command fail
  closed. That is expected.
- `atlas doctor` may report `missing_credentials`, `paper_only_available`, or
  `disabled_by_safety_policy`. Those are local readiness states, not errors that
  should be bypassed.
- Live mode must remain blocked unless every separate live configuration,
  credential, risk, approval, kill-switch, audit, and opt-in requirement is
  satisfied.

## Review Checklist

- `atlas validate` reports paper mode.
- `atlas doctor --json` reports `"execution_enabled": false`.
- `.atlas/config.toml` contains no secrets.
- `broker.enable_live_trading` and `broker.enable_live_submit` are false.
- The command uses `--mode paper --dry-run`.
- Backtest input is the bundled local CSV.
- No pending live orders or approvals are created.

For the canonical reviewer sequence, continue with the
[Reviewer Golden-Path Validation Guide](reviewer-golden-path.md).
