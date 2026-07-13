# Public FAQ

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Is Atlas Agent a live trading bot?

No. Atlas Agent is a local-first research workbench. Live trading is disabled by default and requires explicit multi-factor opt-in before it can even be attempted.

## Can I use this with real money?

Not without extensive explicit configuration. By default, live trading is disabled, broker order submission is blocked by `can_submit=false`, and no credentials are loaded. Atlas is designed for paper and sandbox workflows first.

## Does it guarantee profitable trades?

No. Atlas does not predict profit, guarantee returns, or claim future performance. There is no promise of returns. Not financial advice.

## Does it connect to brokers by default?

No. Broker adapters are available in beta, but `resolve_execution_broker("live")` returns `None` by default and `can_submit` is `false` for all live brokers. No broker contact happens in the default verification path.

## Does it require API keys?

No. The default verification path (install, validate, backtest, inspect safety dossiers) requires no API keys, no credentials, and no network calls.

## What does paper/sandbox/preflight mean?

- **Paper**: Simulated trading on local data without real orders.
- **Sandbox**: Local mock workflows that do not call real providers or brokers.
- **Preflight**: Release-engineering checks and readiness reports that verify local state without enabling execution.

## What is provider execution?

Provider execution is the path through which Atlas would send prompts to an LLM/API provider and receive responses. In the current version, provider execution remains locked — no real provider calls are made by default. All provider workflows operate on local mock responses.

## What is trust blocked?

Mock provider responses in the safety workflow are explicitly not trusted. The `mock_response_trust_decision_blocker` artifact records a permanent decision to block trust. Even if provider execution were unlocked in the future, trust would remain blocked by default.

## What are deterministic safety gates?

Deterministic safety gates are hard-coded checks (position limits, notional limits, symbol restrictions, kill-switch state) that run independently of the LLM. If a proposed order violates a gate, the `RiskManager` blocks it before it reaches any broker.

## What should I run first?

```bash
python3.11 -m pip install -e .
atlas init my-workspace --template routine-trader
cd my-workspace
atlas discipline setup --manual --yes
atlas config set market.symbol DEMO-SYMBOL
atlas validate
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
```

No broker, no network, no credentials, no live trading.

## How can I review the project safely?

See [External Reviewer Walkthrough](external-reviewer-walkthrough.md) for a 10–15 minute safe review path that requires no credentials, no network, and no live trading.

## What kind of feedback is useful?

Technical feedback on:
- README and docs clarity
- Install friction
- CLI UX
- Safety model clarity
- CI/release gate design
- Whether a new reviewer understands what is disabled

See [Feedback Request Guide](feedback-request-guide.md) for details.

## What should not be posted in issues?

- Requests to enable live trading by default
- Requests to bypass safety gates
- Profitability or trading signal evaluations
- Broker setup help for real-money trading
- Credential or API key sharing

## Is this financial advice?

No. Atlas Agent is software, not a financial advisor. Not financial advice. Trading involves significant risk of loss.

## Is this production ready?

No. v0.6.22 is the latest stable public GitHub release and v0.6.21 and earlier releases are historical. It is ready for public review and technical feedback, but it is not a live-trading-ready or production-ready product. Live trading disabled by default. Provider execution remains locked. Trust remains blocked.
