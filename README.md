# Atlas Agent

Routine-based autonomous AI trading agent with self-updating financial LLM selection, broker execution, Markdown memory, scheduled routines, approval gates, and deterministic risk controls.

Atlas Agent connects top financial LLMs, market research, broker execution, persistent memory, and risk-gated autonomous trading routines. It is paper-first, provider-agnostic, and built around repeatable routines that read Markdown memory, use configured research and AI adapters, route orders through deterministic risk controls, write reports, and optionally sync state through GitHub.

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
git clone https://github.com/<user>/atlas-agent.git
cd atlas-agent
python -m pip install -e . --no-build-isolation
atlas init my-trader --template routine-trader
cd my-trader
atlas validate
atlas routine run pre_market --mode paper
atlas routine run market_open --mode paper
```

The old `omni-trade` CLI is deprecated and will be removed in a future version. Use `atlas`.

Run a local backtest from either the project root or a generated workspace:

```bash
atlas backtest --strategy moving_average --symbol BTC-USD
```

Generate a GitHub Actions routine workflow:

```bash
atlas schedule github-actions --template routine-trader
```

Update and inspect the finance LLM roster:

```bash
atlas models update --source vals-finance-agent
atlas models list
atlas models select --top 7
atlas models doctor
```

## Provider Support

Atlas Agent keeps AI access behind provider adapters. AI output is advisory and must not call brokers directly.

- Claude / Anthropic
- Codex / OpenAI-compatible endpoints
- DeepSeek
- Kimi
- Grok
- OpenRouter
- local command agents
- Ollama/local wrappers through OpenAI-compatible or command adapters
- deterministic null provider for tests

## Self-Updating Finance Model Roster

Atlas Agent can maintain a ranked roster of financial LLMs using the Vals AI Finance Agent benchmark. The benchmark ranking is treated as an input, not as a guarantee of trading performance. Atlas Agent filters the roster through the providers and API keys configured by the user.

The roster is used by the AI committee to select up to seven models for trading analysis roles:

- Lead Financial Analyst
- Fundamental Analyst
- Market Research Analyst
- Technical Analyst
- Risk Challenger
- Execution Planner
- Final Arbiter

Atlas Agent maintains a user-editable model roster in `configs/model_roster.yaml` and model/API mappings in `configs/model_sources.yaml`. The roster updater reads the Vals AI Finance Agent benchmark, caches results in `.atlas/cache/model_roster.json`, and falls back to cached or built-in entries when live fetch or parsing fails.

Model names on public leaderboards do not always match provider API IDs. Treat `model_id` values in `configs/model_sources.yaml` as editable placeholders unless you have verified them with your provider or gateway.

## Routine Workflow

Generated workspaces contain `memory/`, `routines/`, `skills/`, `reports/`, `pending_orders/`, and `audit/`.

- `pre_market`: research conditions, read memory, and write a paper trading plan. No orders.
- `market_open`: route paper orders or create pending live approvals.
- `midday_scan`: review open positions, news, and risk notes.
- `market_close`: summarize the day, update portfolio memory, and write the close report.
- `weekly_review`: review process quality, rejected orders, and strategy evidence.

Routine runs use a basic `.atlas/locks/routine.lock` file so overlapping runs are refused. Use `atlas routine status` to inspect a lock and `atlas routine unlock` to remove a stale crash lock.

`--models auto` loads the top usable roster models and assigns committee roles. If fewer than seven API keys are configured, Atlas Agent reuses available models or records disabled placeholders. The AI committee can only produce proposed decisions; broker execution still goes through deterministic risk checks, approval gates, and broker adapters.

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

Atlas Agent is software for research, automation, and self-directed trading workflows. It is not investment, legal, tax, or financial advice. You are responsible for account security, trading decisions, broker permissions, regulatory obligations, and losses.
