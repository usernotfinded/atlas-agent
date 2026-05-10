![Atlas Agent Banner](./assets/atlasagentbanner.png)

# Atlas Agent

**Atlas Agent is a self-improving AI trading agent that connects financial LLMs, broker tools, persistent memory, and deterministic risk controls into one local-first trading workspace.**

Atlas Agent is built for precision and safety. It treats the LLM as the reasoning engine and provides it with a professional-grade toolset to research markets, manage portfolios, and execute trades through a rigorous deterministic risk layer.

- **Local-first:** Your data, memory, and credentials stay on your machine.
- **Simulation-driven:** Paper mode is the default and safest mode for all operations. Live trading requires explicit configuration.
- **Tool-driven:** 49 builtin tool schemas for research, analysis, and execution.
- **Risk-gated:** Every action passes through a separate, deterministic guardrail system.

Use the model stack that fits your trading workflow — [OpenRouter](https://openrouter.ai), [NVIDIA NIM](https://build.nvidia.com), [Xiaomi MiMo](https://platform.xiaomimimo.com), [z.ai/GLM](https://z.ai), [Kimi/Moonshot](https://platform.moonshot.ai), [MiniMax](https://www.minimax.io), [Hugging Face](https://huggingface.co), [OpenAI](https://platform.openai.com/home), [DeepSeek](https://platform.deepseek.com/usage) or any OpenAI-compatible/custom endpoint. Atlas Agent is provider-neutral by design: configure your provider once, switch models through `atlas configure`, and keep the execution, memory, and risk-control layers unchanged.

For finance-specific deployments, prefer models with strong results on dedicated finance-agent evaluations. The [Vals AI Finance Agent benchmark](https://www.vals.ai/benchmarks/finance_agent) is the recommended reference when selecting a model for market research, trading reasoning, and portfolio analysis.

## What Atlas Agent Is

Atlas Agent is a workspace where an AI agent lives, learns, and trades.

*   **The Agent:** A financial LLM (Claude, OpenAI, DeepSeek, etc.) acts as the decision-maker, processing market context and memory to form a thesis.
*   **The Tools:** How the agent interacts with the world. From pulling OHLCV data and web research to executing orders and updating trade journals.
*   **The Memory:** Persistent Markdown journals and logs allow the agent to carry lessons across sessions, deepening its "user model" and improving its skills over time.
*   **The Guardrails:** Deterministic risk controls (position sizing, daily loss limits, symbol policies) are decoupled from LLM reasoning to ensure safety.
*   **Simulation and Learning:** The default safety mode. Atlas Agent uses a high-fidelity `PaperBroker` for simulation without financial risk. During **closed-market** hours, Atlas focuses on research and the built-in **learning loop** to improve future planning.

## Current Status (v0.3.0)

| Component | Status | Description |
|---|---:|---|
| Setup Wizard | Implemented | First-run onboarding with persistent ASCII banner, keyboard-driven setup, and safe reconfiguration through `atlas configure`. |
| Provider-Neutral Models | Implemented | Supports OpenRouter, NVIDIA NIM, z.ai/GLM, Kimi/Moonshot, Hugging Face, OpenAI, and custom/OpenAI-compatible endpoints without lock-in. |
| Tool Registry | Implemented | 49 builtin tool schemas with JSON Schema validation, provider normalization, and compatibility aliases for legacy tool names. |
| Agent Loop | Implemented | Tool-driven autonomous reasoning loop replacing legacy routines. |
| Audit Hash-Chain | Implemented | Tamper-evident audit logs for accountability, replay, and post-trade review. |
| Audit Manifests / Root Hash | Implemented | Run-level manifests and root hash verification to prevent tail deletion. |
| Portfolio Risk Manager | Implemented | Deterministic gates for position size, loss limits, live trading safety, and symbol policy. |
| Pending Orders Risk | Implemented | Worst-reasonable exposure projection aggregating current positions and active pending orders. |
| Kill Switch | Implemented | Advanced hierarchical state machine with dead-man heartbeat protection. |
| Safety Action Planner | Implemented | Generates deterministic, approval-gated action plans for emergency cancellation and flattening. |
| Safety Action Executor | Implemented | Protected proxy to execute safety plans without bypassing risk or audit gates. |
| Broker Sync Layer | Implemented | Provider-neutral synchronization of account state, positions, and orders. |
| Backtesting Foundation | Implemented | Deterministic, local-first engine with risk integration and audit logging. |
| Local Dashboard | Implemented | Minimal, read-only local HTML dashboard for system visibility. |
| Live Trading | Disabled by Default | Explicit opt-in only. All unconfigured runs default to paper simulation. |

## Quickstart

```bash
# Install in editable mode
pip install -e .

# Start the setup wizard
atlas

# Check your configuration
atlas validate

# Run your first paper-trading cycle
atlas run --mode paper

# Keep Atlas updated
atlas update
```

1. **`atlas`**: Running bare `atlas` for the first time opens the interactive setup wizard. The wizard keeps the ASCII banner visible and collects your provider and broker credentials securely. Bare `atlas` never starts trading automatically.
2. **`atlas run`**: Execution is explicit. Use `--mode paper` for safety and simulation. Live trading requires explicit configuration and broker sync.
3. **`atlas update`**: The official way to update. It preserves your `.env.atlas` and local configurations without overwriting sensitive files.

## Configuration & Security

Atlas Agent uses a dual-layer configuration system to balance portability and security:

*   **`.atlas/config.json`**: Stores non-secret configuration like your default symbol, trading hours, and risk parameters.
*   **`.env.atlas`**: Stores sensitive API keys and broker secrets. This file is automatically ignored by Git and protected by the `atlas update` process.

**Security Rules:**
*   Secrets go in `.env.atlas`.
*   `.env.atlas` is gitignored.
*   The dashboard is strictly read-only and must not expose secrets.
*   Audit logs, manifests, and diagnostics must not contain secrets or raw prompts with sensitive data.
*   The update system must not overwrite sensitive files.

Atlas Agent can optionally connect to a configurable web research provider for market/news lookup and external context gathering. The provider is user-selected. Atlas should not require or prefer a specific research vendor. Examples include hosted search APIs, self-hosted metasearch, browser automation providers, or custom HTTP/OpenAI-compatible endpoints.

```bash
# Optional generic research provider secret
ATLAS_RESEARCH_API_KEY=...
```

## Update System

Do not use `git pull` as your primary update path. Use the built-in update command:

```bash
atlas update
```

The updater is designed to safely sync the latest Atlas Agent code while preserving your sensitive local files, including `.env`, `.env.atlas`, and custom workspace configs.

## Safety Model

*   **Simulation by Default**: Atlas Agent will never attempt live trading unless explicitly configured. Paper mode is the safest and default mode. Every **market-open** session begins with a simulation check.
*   **Broker Sync & Adapters**: Broker sync is required before any live decisions are made. Execution is normalized through secure broker adapters that implement strict validation.
*   **Deterministic Guardrails**: Risk controls and **risk gates** are hard-coded and separate from the LLM. If the LLM proposes an order that violates a risk rule, the `RiskManager` will block it before it reaches the broker.
*   **Approval Gates**: Live orders can be configured to require manual approval via `atlas approve-order`. Safety execution plans require approval unless explicitly simulated or approved.
*   **Kill Switch**: Advanced emergency stop with heartbeat monitoring for all trading activity.
*   **Dashboard**: The local dashboard provides a read-only snapshot of the system state, ensuring no trades can be triggered inadvertently from the UI.
*   **Responsibility**: You are responsible for your API keys, broker permissions, and any financial outcomes. Atlas Agent provides the tools; you provide the oversight.

## Backtesting

Atlas Agent includes a deterministic, local-first backtesting engine to evaluate strategies against historical data.

- **Deterministic Execution**: Orders are filled based on historical price action with configurable slippage and commission.
- **Risk Integration**: Every simulated trade is validated by the `RiskManager` before execution.
- **Audit Integration**: Backtest runs generate tamper-evident audit events, ensuring reproducibility.
- **Local-First**: No network calls are made during backtesting; all data is loaded from local CSV files.

```bash
# Run a buy-and-hold backtest
atlas backtest run --symbol AAPL --data path/to/data.csv

# Backtest with specific initial equity and JSON output
atlas backtest run --symbol AAPL --data data.csv --initial-equity 50000 --json
```

**Note:** Backtesting is a simulation tool for research purposes. Historical results do not guarantee future performance and are not financial advice.

## Architecture (v2 Direction)

```text
User / Scheduler / Event
     ↓
Agent Loop (Reasoning + Memory)
     ↓
Tool Registry (49 Builtin Tools)
     ↓
Market Data / Research / Memory / Broker / Update
     ↓
Guardrails + Audit + Risk Controls
```

## Commands

| Command | Purpose |
| :--- | :--- |
| `atlas` | Open setup wizard or show status. |
| `atlas configure` | Re-run the interactive setup wizard. |
| `atlas validate` | Check local configuration and safety gates. |
| `atlas backtest run` | Run a deterministic backtest on historical CSV data. |
| `atlas run --mode paper` | Start the autonomous agent in simulation. |
| `atlas update` | Safely update Atlas Agent to the latest version. |
| `atlas audit verify` | Verify the JSONL audit log hash-chain. |
| `atlas audit verify --all` | Verify all run-level audit manifests in the workspace. |
| `atlas risk status` | View the current configuration of the Portfolio Risk Manager. |
| `atlas kill status` | Check the status of the global kill switch and heartbeat. |
| `atlas kill plan --mode flatten-all` | Generate a safety action plan without executing it. |
| `atlas kill execute-plan --plan emergency_plan.json --paper` | Execute an approved safety plan or force a paper simulation. |
| `atlas broker sync` | Synchronize account, positions, and orders from the broker. |
| `atlas dashboard` | Generate a local, read-only HTML dashboard reflecting system state. |

## Telegram Control Plane

Atlas Agent provides an optional Telegram interface for remote status updates and guarded action approval. This is a control-only layer; execution remains governed by the local risk manager.

## Deployment and Cloud

Atlas is designed for local-first operation but can be deployed to a VPS, Docker container, or serverless job for continuous monitoring. Always ensure your environment variables are secured in your deployment target.

## Disclaimer

**NOT FINANCIAL ADVICE.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss. Live trading can lose real money. You are solely responsible for your deployment, risk limits, and any financial results. Use Paper Mode until you are fully confident in your strategy and configuration.

---
Built by Natan Mucelli.
