# AGENTS.md

## Mission

This is a real AI trading framework. It supports backtesting, paper trading, gated live trading, provider-agnostic AI analysis, broker adapters, risk controls, approval gates, scheduled routines, memory files, and audit logs.

## Hard Rules

- Work directly on main.
- Keep changes scoped and surgical.
- Do not remove live trading support.
- Do not make live trading default.
- Do not allow direct AI-to-broker execution.
- Do not bypass `RiskManager`.
- Do not bypass approval gates or the kill switch.
- Do not bypass the audit hash-chain or manifest system.
- Do not log or commit secrets or API-key-like strings.
- Do not add profit claims or wording implying zero risk.
- Do not enable leverage by default.
- Backtesting must be deterministic and local-first (no network calls).
- Keep provider system model-agnostic and neutral.
- Keep broker system adapter-based.
- Every new broker must implement the `Broker` interface.
- Every new provider must implement the `AIProvider` interface.
- Every execution path must be tested.
- Every rejected order must be auditable.
- The dashboard must remain strictly read-only and zero-secret.

## Required Checks

```bash
pytest
pip check
atlas validate
atlas backtest run --data data/sample/ohlcv.csv --symbol BTC-USD
atlas run --mode paper
atlas run --mode live  # Should fail safely unless fully configured
```

Live mode should fail safely unless explicit live config, credentials, risk checks, and approval are present.

