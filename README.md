# OmniTradeAI

Routine-based autonomous AI trader with multi-provider AI support, Alpaca execution, Markdown memory, risk gates, and scheduled operation.

OmniTradeAI is an open-source trading research and automation framework. It is paper-first, provider-agnostic, and built around repeatable routines that read Markdown memory, use configured research and AI adapters, route orders through deterministic risk controls, write reports, and optionally sync state through GitHub.

This is not financial advice. Trading can lose money. No returns are guaranteed.

## What It Does

- Scheduled trading routines for pre-market, market open, midday scan, market close, and weekly review.
- Markdown memory files for portfolio notes, watchlists, open positions, trade journal, strategy rules, daily notes, and weekly review.
- Paper trading by default with local sample data and audit logs.
- Live trading support with explicit configuration, broker credentials, risk checks, kill switch, and approval gates.
- AI provider adapters for hosted APIs, OpenAI-compatible APIs, local command agents, and local wrappers.
- Perplexity research wrapper for market context when configured.
- ClickUp notification wrapper for routine reports and pending approvals.
- GitHub persistence through opt-in commit and push gates.

## Quickstart

```bash
git clone https://github.com/<user>/omni-trade-ai.git
cd omni-trade-ai
python -m pip install -e . --no-build-isolation
omni-trade init my-trader --template routine-trader
cd my-trader
omni-trade validate
omni-trade routine run pre_market --mode paper
omni-trade routine run market_open --mode paper
```

Run a local backtest from either the project root or a generated workspace:

```bash
omni-trade backtest --strategy moving_average --symbol BTC-USD
```

Generate a GitHub Actions routine workflow:

```bash
omni-trade schedule github-actions --template routine-trader
```

## Provider Support

OmniTradeAI keeps AI access behind provider adapters. AI output is advisory and must not call brokers directly.

- Claude / Anthropic
- Codex / OpenAI-compatible endpoints
- DeepSeek
- Kimi
- Grok
- OpenRouter
- local command agents
- Ollama/local wrappers through OpenAI-compatible or command adapters
- deterministic null provider for tests

## Routine Workflow

Generated workspaces contain `memory/`, `routines/`, `skills/`, `reports/`, `pending_orders/`, and `audit/`.

- `pre_market`: research conditions, read memory, and write a paper trading plan. No orders.
- `market_open`: route paper orders or create pending live approvals.
- `midday_scan`: review open positions, news, and risk notes.
- `market_close`: summarize the day, update portfolio memory, and write the close report.
- `weekly_review`: review process quality, rejected orders, and strategy evidence.

Routine runs use a basic `.omni/locks/routine.lock` file so overlapping runs are refused. Use `omni-trade routine status` to inspect a lock and `omni-trade routine unlock` to remove a stale crash lock.

## Live Trading

Live trading exists, but it is disabled by default. It requires broker credentials, explicit live configuration, a risk pass, kill switch off, and approval before broker execution. Live trading can lose money and must be validated in broker sandbox or paper environments before any real account use.

Safe defaults:

```bash
TRADING_MODE=paper
ENABLE_LIVE_TRADING=false
ORDER_APPROVAL_MODE=manual_live
ALLOW_LEVERAGE=false
```

## Remote Routines

Routine prompts are compatible with:

- Claude Code
- Codex
- GitHub Actions
- cron
- local command agents or custom schedulers

Remote environments should inject secrets through environment variables or platform secret stores. Do not commit `.env`.

## Safety

- No AI direct-to-broker execution.
- `RiskManager` is mandatory before any order.
- Kill switch blocks execution.
- Live approval gate is required.
- Audit logs redact common secret fields.
- Generated pending orders and audit logs are ignored by default.
- Git sync refuses likely secrets and only commits memory/report state when explicitly enabled.
- No secrets belong in the repository.

## Limitations

- Not financial advice.
- No profit guarantee.
- Sandbox and paper testing are required before real money.
- Concurrent routine protection is basic.
- Broker integrations need real account validation.
- Backtests do not model every fee, tax, borrow, liquidity, latency, or slippage condition.
- AI provider output is untrusted and should be reviewed.

## Roadmap

- Broker sandbox test suite.
- Account reconciliation.
- Dashboard.
- Better strategy plugins.
- More notification adapters.
- Locking improvements.
- Multi-agent committee UI.

## Release Checks

See `docs/release-checklist.md` before publishing a public release.

## Disclaimer

OmniTradeAI is software for research, automation, and self-directed trading workflows. It is not investment, legal, tax, or financial advice. You are responsible for account security, trading decisions, broker permissions, regulatory obligations, and losses.

