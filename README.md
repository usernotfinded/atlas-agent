![Atlas Agent Banner](./assets/atlasagentbanner.png)

# Atlas Agent

The self-improving AI trading agent built by Natan Mucelli.

<p align="center">
<a href="https://github.com/usernotfinded/atlas-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-FF4500?style=for-the-badge" alt="License: MIT"></a>
<a href="https://github.com/usernotfinded"><img src="https://img.shields.io/badge/Built%20by-Natan%20Mucelli-8A2BE2?style=for-the-badge" alt="Built by Natan Mucelli"></a>
</p>

Atlas Agent is the Hermes Agent for trading: a self-improving AI trading agent with broker adapters, deterministic risk gates, approval policy, audit logs, portfolio memory, and a built-in learning loop.

It researches markets, proposes and validates actions, searches conversation memory, deepens its user model, creates and improves skills from experience, sends knowledge nudges, writes reports, and updates memory. Atlas can run locally, on a VPS, beside GPU workers, or as serverless jobs, with Telegram as an optional control plane.

When markets are open, Atlas Agent runs the trading cycle through broker adapters and deterministic risk gates. If live execution is configured and permitted by policy, live orders still pass through approval, audit logging, kill-switch checks, and broker-specific gates. If live execution is not permitted, the same cycle can run in simulation.

When markets are closed, Atlas Agent does not force live execution. It uses the time to research, simulate, paper trade, reflect, improve skills, update memory, and prepare for the next market session.

Atlas Agent supports benchmark-informed model guidance, Alpaca and broker execution adapters, Perplexity market research, ClickUp notifications, Markdown trade journals, scheduled remote routines, gated live trading, and guarded GitHub-backed persistence.

AI output is advisory. Broker execution stays behind strategy validation, `RiskManager`, the kill switch, audit logs, and approval gates.

## Features

**Benchmark-informed model reference.** Atlas Agent provides a ranked reference of finance-capable LLMs using the Vals AI Finance Agent benchmark. This is model-selection guidance for choosing which models to connect, not mandatory runtime orchestration. It does not guarantee trading performance.

**Agent-first autonomous operation.** Run `atlas`, `atlas status`, and `atlas plan` as the primary UX. Named routines remain available for advanced scheduling and inspection.

**MVP learning loop.** Closed-market routines can review reports, rejected orders, research notes, operator feedback, and memory files to improve future behavior. This is an initial implementation.

**Skills from experience.** Atlas can draft, revise, and archive reusable skill notes from observed work patterns. Current MVP behavior uses deterministic skill normalization and pattern-based skill mining.

**Conversation memory and user model.** Workspace memory can capture preferences, constraints, lessons, trading style, and conversation summaries for later search.

**Markdown memory and trade journal.** Generated workspaces keep portfolio notes, watchlists, strategy rules, open positions, trade history, daily reports, and weekly reviews in plain Markdown.

**Configurable AI analyst.** Configure your preferred financial LLM through the `AIProvider` interface.

**Broker execution layer.** Use `PaperBroker` by default and route live integrations through broker adapters that implement the `Broker` interface.

**Deterministic risk manager.** Every order must pass deterministic checks for position size, daily loss, trade frequency, symbol policy, stop-loss requirements, leverage policy, and live-trading gates.

**Live-gated execution.** Live mode exists, but it requires explicit live config, broker credentials, risk approval, kill switch clearance, and manual approval gates.

**Telegram control-plane scaffolding.** Optional Telegram diagnostics can check configuration. A full polling/webhook bot is planned for future releases.

**Deployment templates.** Atlas includes templates for VPS, Docker, systemd, and serverless jobs.

**Perplexity research integration.** Pull market context through the Perplexity research adapter when configured.

**ClickUp notifications.** Send compact routine updates, pending approval notices, and report summaries to ClickUp without printing tokens.

**GitHub-backed persistence.** Opt-in commit and push gates can sync selected memory and report state while refusing likely secrets.

**Backtesting and reports.** Run strategy backtests, generate JSON and Markdown reports, and keep CSV trade logs for review.

**Provider-agnostic design.** Switch AI providers through configuration and adapters without coupling strategy or execution code to one model vendor.

## Warning

Trading can lose money. Atlas Agent is software, not financial advice. Users are responsible for broker accounts, laws, taxes, risk limits, credentials, and deployment choices. Live trading is never the default and must pass explicit configuration, broker credentials, deterministic risk gates, approval policy, kill-switch checks, and audit logging.

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
atlas
```

`atlas` starts one autonomous agent cycle. It decides the operational cycle:
- When markets are open, Atlas Agent runs the trading cycle through broker adapters and deterministic risk gates. If live execution is configured and permitted by policy, live orders still pass through approval, audit logging, kill-switch checks, and broker-specific gates. If live execution is not permitted, the same cycle can run in simulation.
- When markets are closed, Atlas Agent does not force live execution. It researches, simulates, paper trades, reflects, improves skills, updates memory, and prepares for the next market session.

## Top-level Commands

Atlas provides convenience commands for the primary agent workflow:

- `atlas`: Start one autonomous cycle.
- `atlas status`: Show current agent state and mode (alias for `atlas agent status`).
- `atlas plan`: Explain the next agent cycle (alias for `atlas agent plan`).
- `atlas run --continuous`: Keep the agent running.
- `atlas run --dry-run`: Preview the next cycle without executing (alias for `atlas plan`).

Advanced users can still run specific scheduled routines or manual actions using the `atlas agent ...` and `atlas routine ...` commands.

```bash
atlas routine run pre_market --mode paper
atlas backtest --strategy moving_average --symbol BTC-USD
```

## How Atlas Agent Works

```text
Scheduled routine
→ Markdown memory
→ Market/research data
→ Model-selection guidance (README/setup-time reference only)
→ Configured AIProvider
→ Strategy validation
→ RiskManager
→ Paper execution or pending live order
→ Reports + journal + notifications + Telegram (Scaffolding)
→ Learning loop (MVP) + skills + memory updates
→ Guarded Git sync
```

## MVP learning loop

Atlas closes the loop after agent cycles. It reads the trade journal, daily notes, weekly reviews, past conversations, user preferences, open-position notes, rejected orders, reports, and research context.

Learning outputs are reviewable: lessons learned, reflection reports, proposed skills, and memory nudges. Atlas does not silently overwrite core strategy rules or live-trading policy.

## Skills from experience

Atlas can turn repeated observations into proposed skill notes, improve proposed skills, approve useful skills, and archive stale guidance. Skills are operating knowledge for research, reporting, planning, and review; they are not broker permissions and cannot authorize direct execution.

Skill states:

- `skills/proposed/`: drafts created from journal and reflection evidence.
- `skills/active/`: user-approved operating knowledge.
- `skills/archived/`: stale or retired guidance.

Useful commands:

```bash
atlas skills list
atlas skills create-from-journal
atlas skills improve
atlas skills approve <skill_name>
atlas skills archive <skill_name>
```

## Conversation memory and user model

Atlas workspaces can keep searchable conversation summaries, preferences, constraints, lessons learned, mistakes, trading style, and a user profile. This lets the agent adapt to the operator over time while keeping secrets out of memory files and public reports.

Memory files include:

- `memory/conversations/`
- `memory/user_profile.md`
- `memory/preferences.md`
- `memory/trading_style.md`
- `memory/lessons_learned.md`
- `memory/mistakes.md`

Useful commands:

```bash
atlas memory ingest --file conversation.md
atlas memory search "risk"
atlas user remember "Prefer lower turnover unless conviction is high."
atlas user show
```

## Telegram control plane

Telegram is an optional remote control plane for a deployed agent. It can request status, plans, runs, learning, reflection, positions, pending-order review, approval or rejection, kill-switch actions, memory lookup, and skill listings. Telegram commands are control input only; live orders still require the same risk, approval, broker, kill-switch, and audit path.

Supported command surface:

- `/status`
- `/plan`
- `/run`
- `/learn`
- `/reflect`
- `/positions`
- `/pending`
- `/approve <order_id>`
- `/reject <order_id>`
- `/kill`
- `/resume`
- `/memory <query>`
- `/skills`

Telegram is optional. It must authorize user IDs through configuration and must never expose bot tokens, broker credentials, provider keys, or account secrets.

## Cloud deployment

Atlas can run locally, on a small VPS, in Docker, under systemd, as scheduled serverless jobs, or beside GPU workers for local heavy models and custom research pipelines. It is designed for lightweight VPS deployments depending on provider, workload, and model choices.

Deployment paths:

- small VPS for continuous agent operation
- Docker or systemd for long-running cloud VMs
- serverless jobs for scheduled research, learning, reports, and sync
- GPU clusters for local heavy models or custom research pipelines
- Telegram remote control for status, plans, learning, memory lookup, and guarded actions

Keep secrets in local environment files or platform secret stores, validate the workspace before continuous operation, and keep broker execution in the main guarded Atlas process.

## CLI Quick Reference

| Command | Purpose |
| --- | --- |
| `atlas` | Start one autonomous cycle (alias for `atlas agent run --once`). |
| `atlas status` | Show market state, mode, broker, kill switch, and pending-order status. |
| `atlas plan` | Explain the next open-market or closed-market cycle. |
| `atlas run --continuous` | Keep the agent running in autonomous mode. |
| `atlas init` | Create a workspace from a template. |
| `atlas validate` | Check local configuration and create required runtime directories. |
| `atlas agent status` | Show market state, mode, broker, kill switch, and pending-order status. |
| `atlas agent plan` | Explain the next open-market or closed-market cycle. |
| `atlas agent run --once` | Run one agent cycle based on current market state and policy. |
| `atlas agent learn` | Run the learning loop and write a learning report. |
| `atlas agent reflect` | Generate a reflection report from memory and recent work. |
| `atlas skills list` | Show active, proposed, and archived skills. |
| `atlas skills create-from-journal` | Propose skills from journal evidence. |
| `atlas skills improve` | Normalize proposed skills without approving them. |
| `atlas memory search "risk"` | Search Markdown memory and conversation history. |
| `atlas user show` | Show the current user model summary. |
| `atlas telegram test` | Run a no-network Telegram configuration diagnostic. |
| `atlas deploy docker` | Generate or report Docker deployment files. |
| `atlas deploy systemd` | Generate or report a systemd service. |
| `atlas models list` | Show the benchmark-informed model reference. |
| `atlas models update --source vals-finance-agent` | Refresh `configs/model_roster.yaml` from Vals/cache/fallback data. |
| `atlas models update-readme` | Refresh the benchmark reference in the README. |
| `atlas models doctor` | Validate model-roster config and README marker health. |
| `atlas routine run pre_market --mode paper` | Advanced: run the pre-market routine directly. |
| `atlas routine run market_open --mode paper` | Advanced: run the market-open routine directly in simulation. |
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

Atlas Agent includes a reference ranking of finance-capable LLMs based on the Vals AI Finance Agent benchmark. This benchmark evaluates financial analyst tasks, not guaranteed trading performance. The roster is model-selection guidance only; Atlas runs through the configured `AIProvider`, and users may choose any supported provider or model. The model roster is guidance for choosing models to connect. It updates the recommended-model table in this README. It is not mandatory runtime orchestration and does not guarantee trading performance.

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
ANTHROPIC_API_KEY=<SET_IN_ENV>
# or
OPENAI_API_KEY=<SET_IN_ENV>
# or
DEEPSEEK_API_KEY=<SET_IN_ENV>
```

The benchmark reference improves model selection discipline, but it does not predict trading outcomes.

Manage the reference via CLI:

```bash
atlas models list
atlas models update --source vals-finance-agent
atlas models update-readme
atlas models doctor
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

- Simulation path for testing workflows, reports, routines, and strategy paths.
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

Keep live execution approval-gated, preserve provider-agnostic architecture, and include tests for every execution path.

## Community and Resources

- Open issues and pull requests in the GitHub repository.
- Review `AGENTS.md` before changing trading, broker, provider, risk, approval, or audit behavior.
- Use `docs/release-checklist.md` before publishing a release.

## License

MIT — see LICENSE.

## Built By

Built by Natan Mucelli.
