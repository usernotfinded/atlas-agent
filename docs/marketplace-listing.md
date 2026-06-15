# Atlas Agent — Marketplace Listing

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss. Live trading is disabled by default.

## Title

**Atlas Agent — Local-First Paper Trading Safety Workbench**

## Tagline

A local-first, broker-neutral paper-trading workbench with deterministic risk gates, tamper-evident audit logs, and safe-by-default sandbox workflows.

## One-paragraph product description

Atlas Agent is a local-first, broker-neutral Python CLI workbench for sandbox, paper, and preflight trading research. It combines deterministic backtesting, paper-only workflows, provider-neutral research artifacts, tamper-evident audit logs, and deterministic risk gates. Live trading, provider execution, and broker order submission stay disabled by default, with no credentials required for the safe verification path. The framework is safe-by-default and paper-first: use it to experiment, validate strategies offline, and inspect safety boundaries before any real-money setup. Not financial advice.

## Target users

- Quantitative researchers and algorithmic traders who want to validate strategies in deterministic paper/sandbox mode before considering any live configuration.
- Python developers and CLI users who prefer a local-first workbench for AI-assisted market research, backtesting, and audit-trail generation without requiring credentials or network calls by default.
- Safety engineers and OSS reviewers who need deterministic risk gates, approval queues, tamper-evident audit logs, and kill switches to inspect agentic trading boundaries.

## Current capabilities

- **Local-first paper and sandbox trading workspace** — Run deterministic simulations and dry-runs without broker credentials or provider API keys; defaults to paper mode with live trading disabled.
- **Deterministic risk gates and safety controls** — Hard-coded `RiskManager` limits on position size, notional, and symbols operate independently of LLM reasoning to block unsafe orders.
- **Tamper-evident audit logs and run manifests** — SHA256 hash-chain, per-run manifests, and secret-redacted event logs support read-only replay and forensic review.
- **Bring-your-own model and provider-neutral research** — Compatible with 14+ provider profiles and custom OpenAI-compatible endpoints; users supply their own credentials, models, and risk limits.
- **Deterministic local backtesting and research artifacts** — Run CSV-based backtests and generate offline research artifacts with validated schemas for strategy exploration before any real capital.

## What is disabled

Atlas Agent ships with all real-money and real-provider paths locked by default:

- **Live trading** is disabled by default. Enabling it requires explicit multi-factor opt-in, valid broker credentials, a normal kill-switch state, and manual approval.
- **Provider execution** remains locked — no real LLM or API provider calls are made in the default workflow.
- **Broker order submission** is blocked by `can_submit=false`; `resolve_execution_broker("live")` returns `None` by default.
- **Credentials** are not loaded unless explicitly configured in `.env.atlas`.
- **Trust** remains blocked — mock provider responses in safety workflows are explicitly not trusted.

What is enabled by default: local paper trading, deterministic backtesting, audit-log generation, and read-only diagnostics. No API keys, broker accounts, or network access are required to install, validate, and run the demo workflows.

## Safety boundaries

Atlas Agent is a **paper-first, sandbox/preflight-first research workbench**. The default install is designed for safe local exploration, review, and verification without credentials, network calls, or live trading.

| Capability | Default state | How it is kept safe |
|---|---|---|
| Live trading | Disabled | `trading_mode` defaults to `paper`; `enable_live_trading=false`. |
| Broker order submission | Blocked | `can_submit=false` for all live brokers; live broker resolution returns `None`. |
| Provider execution | Locked | No real LLM/provider API calls are made by default. |
| Credential loading | None | `.env.atlas` is gitignored and not loaded unless explicitly configured. |
| Leverage | Disabled | `allow_leverage=false` in safe configurations. |
| Trust of mock responses | Blocked | Mock provider responses in safety workflows are explicitly not trusted. |

## Getting started

Atlas Agent requires **Python 3.11** and runs from a local checkout. No broker credentials or API keys are needed for the default verification path.

```bash
git clone https://github.com/usernotfinded/atlas-agent.git
cd atlas-agent
python3.11 -m pip install -e .
```

The canonical demo is a single script that creates a temporary paper workspace, validates configuration, runs redacted local diagnostics, prints a paper dry-run, executes the bundled deterministic backtest, and verifies local artifacts:

```bash
./scripts/demo_product_walkthrough.sh
```

What it does:
- Creates an isolated temporary workspace.
- Runs `atlas init`, `atlas discipline setup`, `atlas config set market.symbol ATLAS-DEMO`.
- Runs `atlas validate` and `atlas doctor --json` (read-only, no network).
- Runs `atlas run --mode paper --dry-run --symbol ATLAS-DEMO`.
- Runs `atlas backtest run --symbol DEMO-SYMBOL --data data/sample/ohlcv.csv`.
- Runs `atlas backtest runs --validate --json` and `atlas audit verify --all`.
- Prints a summary of what remains disabled.

### Manual quick commands

```bash
atlas init my-workspace --template routine-trader
cd my-workspace
atlas discipline setup --manual --yes
atlas config set market.symbol ATLAS-DEMO
atlas validate
atlas run --mode paper --dry-run --symbol ATLAS-DEMO
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
```

### Safety notes

- **Paper-first**: default mode is paper; no live orders are submitted.
- **No credentials required**: the default path uses no broker credentials or provider API keys.
- **No network calls**: the demo and backtest are local-only.
- **Provider execution remains locked**: no real LLM/provider calls are made by default.
- **Broker order submission is blocked** by `can_submit=false`.
- **Not financial advice**: simulations do not imply profitability or trading correctness.

For full details, see the [Paper-Trading Guide](paper-trading-guide.md), [Reviewer Golden-Path Validation Guide](reviewer-golden-path.md), [Demo: Paper Workflow](demo-paper-workflow.md), and [Product Demo Pack](product-demo-pack.md).

## Roadmap toward bounded autonomy

Atlas Agent is intentionally paper-first: the default path is local sandbox simulation, deterministic backtesting, and read-only broker preflight. The roadmap toward bounded autonomy expands supervised, human-in-the-loop workflows — paper strategy validation, analysis-only live sync, approval-gated order proposals, and, only after explicit multi-factor opt-in, live submit through layered deterministic gates. Autonomy is bounded by hard-coded `RiskManager` limits, mandatory approval queues, a hierarchical kill switch, and tamper-evident audit logs; the system fails closed, never treats provider output as execution authority, and leaves every live gate disabled by default. This is a research and safety-engineering roadmap, not a promise of hands-off profitability or production-ready autonomous trading.

See [Autonomy Roadmap](autonomy-roadmap.md) for the detailed levels.

## Disclaimer

> **Not financial advice.** Atlas Agent is a local-first, paper/sandbox/preflight research workbench for trading-agent safety, deterministic risk gates, and audit trails — not a financial advisor, not a live-trading-ready product, and not autonomous. Live trading is disabled by default, provider execution remains locked, broker order submission is blocked by `can_submit=false`, and no credentials are required for the default verification path. Trading involves significant risk of loss; past backtest or paper results do not guarantee future performance. You are solely responsible for your deployment, broker configurations, risk limits, and any financial outcomes.
