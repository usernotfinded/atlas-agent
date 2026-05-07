# AGENTS.md

## Mission

This is a real AI trading framework. It supports backtesting, paper trading, gated live trading, provider-agnostic AI analysis, broker adapters, risk controls, approval gates, scheduled routines, memory files, and audit logs.

## Hard Rules

- Do not remove live trading support.
- Do not make live trading default.
- Do not allow direct AI-to-broker execution.
- Do not bypass `RiskManager`.
- Do not bypass approval gates.
- Do not bypass the kill switch.
- Do not log secrets.
- Do not add profit claims.
- Do not enable leverage by default.
- Keep provider system model-agnostic.
- Keep broker system adapter-based.
- Every new broker must implement the `Broker` interface.
- Every new provider must implement the `AIProvider` interface.
- Every execution path must be tested.
- Every rejected order must be auditable.

## Required Checks

```bash
pytest
python -m atlas_agent.cli --help
atlas --help
atlas validate
atlas backtest --strategy moving_average --symbol BTC-USD
atlas run-once --mode paper
atlas run-once --mode live
```

Live mode should fail safely unless explicit live config, credentials, risk checks, and approval are present.

