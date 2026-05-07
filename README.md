# Atlas Agent

The autonomous AI trading agent that runs on routines, memory, model rosters, broker adapters, and risk gates.

![MIT License](https://img.shields.io/badge/License-MIT-2DA44E)
![Built by Natan Mucelli](https://img.shields.io/badge/Built%20by-Natan%20Mucelli-111111)

Atlas Agent is a routine-based autonomous AI trading agent. It wakes up on scheduled routines, reads Markdown memory, researches markets, proposes trades, routes every execution path through deterministic risk controls, writes reports, updates memory, and can optionally sync state through GitHub.

It is designed around provider-agnostic AI access, broker adapters, and paper-first operation. Atlas Agent supports benchmark-informed model selection, Alpaca and broker execution adapters, Perplexity market research, ClickUp notifications, Markdown trade journals, scheduled remote routines, and gated live trading.

AI output is advisory. Broker execution stays behind strategy validation, `RiskManager`, the kill switch, audit logs, and approval gates.

## Features

**Benchmark-informed model reference.** Atlas Agent provides a ranked reference of finance-capable LLMs using the Vals AI Finance Agent benchmark. This helps users select the best single model for their agent.

**Routine-based autonomous operation.** Run pre-market, market open, midday, market close, and weekly routines locally, through cron, through GitHub Actions, or through remote coding agents.

**Markdown memory and trade journal.** Generated workspaces keep portfolio notes, watchlists, strategy rules, open positions, trade history, daily reports, and weekly reviews in plain Markdown.

**Single-model AI analyst.** Configure your preferred financial LLM through the `AIProvider` interface.

**Broker execution layer.** Use `PaperBroker` by default and route live integrations through broker adapters that implement the `Broker` interface.

**Deterministic risk manager.** Every order must pass deterministic checks for position size, daily loss, trade frequency, symbol policy, stop-loss requirements, leverage policy, and live-trading gates.

**Paper-first, live-gated execution.** Paper mode is the default. Live mode exists, but it requires explicit live config, broker credentials, risk approval, kill switch clearance, and manual approval gates.

**Perplexity research integration.** Pull market context through the Perplexity research adapter when configured, while failing safely when credentials are missing.

**ClickUp notifications.** Send compact routine updates, pending approval notices, and report summaries to ClickUp without printing tokens.

**GitHub-backed persistence.** Opt-in commit and push gates can sync selected memory and report state while refusing likely secrets.

**Backtesting and reports.** Run strategy backtests, generate JSON and Markdown reports, and keep CSV trade logs for review.

**Provider-agnostic design.** Switch AI providers through configuration and adapters without coupling strategy or execution code to one model vendor.

## Warning

Atlas Agent is experimental software. It is not financial advice. Trading can lose money. Live trading is disabled by default. No returns are guaranteed. Users are responsible for their own broker accounts, API keys, laws, taxes, and risk controls.

## Quick Install

```bash
git clone https://github.com/usernotfinded/atlas-agent.git
cd atlas-agent
python -m pip install -e .
atlas --help
```

## Getting Started

```bash
atlas init my-trader --template routine-trader
cd my-trader
atlas validate
atlas agent status
atlas agent plan
atlas agent run --mode auto
```

Run the agent. Atlas decides the operational cycle:
- When markets are closed, Atlas researches, simulates, updates memory, and paper-trades.
- When markets are open, Atlas can execute paper trades or create approval-gated live orders.

Advanced users can still run specific scheduled routines or manual actions:

```bash
atlas routine run pre_market --mode paper
atlas backtest --strategy moving_average --symbol BTC-USD
```

## How Atlas Agent Works

```text
Scheduled routine
→ Markdown memory
→ Market/research data
→ Benchmark-informed model reference
→ Single-model AI analyst
→ Strategy validation
→ RiskManager
→ Paper execution or pending live order
→ Reports + journal + notifications
→ Git sync
```

## CLI Quick Reference

| Command | Purpose |
| --- | --- |
| `atlas init` | Create a workspace from a template. |
| `atlas validate` | Check local configuration and create required runtime directories. |
| `atlas models list` | Show the benchmark-informed model reference. |
| `atlas models update-readme` | Refresh the benchmark reference in the README. |
| `atlas routine run pre_market --mode paper` | Run the pre-market routine in paper mode. |
| `atlas routine run market_open --mode paper` | Run the market-open routine in paper mode. |
| `atlas run-once --mode paper` | Execute one paper-mode strategy pass. |
| `atlas run-once --mode live` | Attempt one live-mode pass; fails safely unless all live gates pass. |
| `atlas approve-order <order_id>` | Approve a pending live order by ID. |
| `atlas backtest` | Run a backtest with the selected strategy and symbol. |
| `atlas research market --symbol SPY` | Request market research when the research adapter is configured. |
| `atlas notify clickup --file ...` | Send a ClickUp update from a local file when configured. |
| `atlas git-sync commit --message "routine update"` | Commit allowed routine state through the guarded Git sync path. |
| `atlas git-sync push` | Push allowed routine state through the guarded Git sync path. |
| `atlas kill-switch enable` | Enable the kill switch. |
| `atlas kill-switch disable` | Disable the kill switch. |

## Recommended models (from Vals.ai benchmarks)

Atlas Agent includes a reference ranking of finance-capable LLMs based on the Vals AI Finance Agent benchmark. This benchmark evaluates financial analyst tasks, not guaranteed trading performance.

<!-- ATLAS_MODEL_ROSTER_START -->

| Rank | Model | Score |
|---|---|---|
| 1 | Claude Opus 4.7 | 64.37% |
| 2 | Claude Sonnet 4.6 | 63.33% |
| 3 | Muse Spark | 60.59% |
| 4 | DeepSeek V4 | 60.39% |
| 5 | Claude Opus 4.6 (Thinking) | 60.05% |
| 6 | GPT 5.5 | N/A |
| 7 | Gemini 3.1 Pro Preview (02/26) | N/A |

<!-- ATLAS_MODEL_ROSTER_END -->

### Provider Setup

Set environment variables for the provider you want to enable. Do not put real keys in public files.

```bash
ANTHROPIC_API_KEY=...
# or
OPENAI_API_KEY=...
# or
DEEPSEEK_API_KEY=...
```

The benchmark reference improves model selection discipline, but it is not proof that Atlas will beat the market.

Manage the reference via CLI:

```bash
atlas models list
atlas models update-readme
```

## Provider Support

Atlas Agent keeps provider access adapter-based and model-agnostic:

- OpenAI-compatible APIs
- Claude / Anthropic
- DeepSeek
- Kimi / Moonshot
- Grok / xAI-compatible endpoints
- Gemini-compatible endpoints if configured
- OpenRouter
- Ollama/local wrappers
- Local command agents
- Custom endpoints

Switch providers through config; no code changes should be required.

## Routine Workflow

| Routine | Purpose |
| --- | --- |
| `pre_market` | Read memory, gather context, and prepare a paper-mode trading plan without placing orders. |
| `market_open` | Run strategy and AI review, then route paper orders or create pending live orders. |
| `midday_scan` | Review open positions, market context, news, and risk notes during the session. |
| `market_close` | Summarize the day, update memory, write reports, and capture execution outcomes. |
| `weekly_review` | Review process quality, rejected orders, risk behavior, and strategy evidence. |

Routine runs use a workspace lock so overlapping runs are refused.

## Paper vs Live

**Paper mode**

- Default operating mode.
- Safe for testing workflows, reports, routines, and strategy paths.
- Uses `PaperBroker`.
- Writes auditable paper execution records.

**Live mode**

- Exists for gated real broker execution.
- Disabled by default.
- Requires broker credentials.
- Requires `ENABLE_LIVE_TRADING=true`.
- Requires `RiskManager` pass.
- Requires approval.
- Can lose real money.

Safe defaults:

```bash
TRADING_MODE=paper
ENABLE_LIVE_TRADING=false
ORDER_APPROVAL_MODE=manual_live
ALLOW_LEVERAGE=false
```

## Project Structure

```text
src/atlas_agent/              Core package, CLI, providers, brokers, risk, routines
templates/routine-trader/     Workspace template for routine-based agents
routines/prompts/             Built-in routine prompts
skills/                       Operator skill notes for routine work
configs/                      Provider and broker examples
docs/                         Safety, setup, and release notes
tests/                        Unit tests for execution, safety, CLI, and routines
```

## Repository Sections

| Section | What to inspect |
| --- | --- |
| Safety model | `docs/safety.md`, `DISCLAIMER.md`, `AGENTS.md` |
| Routine template | `templates/routine-trader/` |
| Scheduled prompts | `routines/prompts/` |
| Execution code | `src/atlas_agent/execution/`, `src/atlas_agent/risk/`, `src/atlas_agent/brokers/` |
| Test coverage | `tests/` |

## Contributing

Contributions are welcome. Useful focus areas:

- broker sandbox validation
- provider adapters
- strategy plugins
- dashboard
- notification adapters
- safety tests

Keep live execution paper-first and approval-gated, preserve provider-agnostic architecture, and include tests for every execution path.

## Community and Resources

- Open issues and pull requests in the GitHub repository.
- Review `AGENTS.md` before changing trading, broker, provider, risk, approval, or audit behavior.
- Use `docs/release-checklist.md` before publishing a release.

## License

MIT — see LICENSE.

## Built By

Built by Natan Mucelli.
