![Atlas Agent Banner](./assets/atlasagentbanner.png)

# Atlas Agent

<p align="center">
  <a href="https://github.com/usernotfinded/atlas-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/usernotfinded/atlas-agent/actions/workflows/ci.yml"><img src="https://github.com/usernotfinded/atlas-agent/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="#broker-neutral-model"><img src="https://img.shields.io/badge/Positioning-Broker%20Neutral-blue?style=for-the-badge" alt="Broker Neutral"></a>
  <a href="docs/model-providers.md"><img src="https://img.shields.io/badge/Providers-14%2B-orange?style=for-the-badge" alt="14+ Providers"></a>
  <a href="https://github.com/usernotfinded"><img src="https://img.shields.io/badge/Built%20by-Natan%20Mucelli-blueviolet?style=for-the-badge" alt="Built by Natan Mucelli"></a>
</p>

**Atlas Agent turns your preferred LLM and broker/API provider into a supervised trading workspace, with market research, paper workflows, trading memory, audit logs, approval queues, and deterministic risk gates.**

> **Current Status (v0.6.9)** — package/source version is `0.6.9`; latest stable public release is [v0.6.9](docs/releases/v0.6.9.md) on GitHub. v0.6.8, v0.6.7, v0.6.6, v0.6.5, v0.6.4, v0.6.3, v0.6.2, v0.6.1, and v0.6.0 are historical. PyPI was not published.

> **DISCLAIMER:** Not financial advice. Live trading is disabled by default. Live submit remains disabled by default. Atlas is broker-neutral: users choose their own model, broker/API provider, credentials, and risk limits. Trading involves significant risk of loss.

## Why Atlas?

- **LLM-assisted market research**: Leverage advanced models to process market context and form data-driven theses.
- **Paper workflows**: Validate strategies using deterministic local **simulation** before risking capital. Every **market-open** session is designed to favor simulation until explicitly authorized. During **closed-market** hours, Atlas focuses on **learning** and research.
- **Deterministic risk gates**: Safety controls are hard-coded and decoupled from LLM reasoning to help reduce unintended actions.
- **Approval queues**: Live actions are designed to require explicit human confirmation via local queues.
- **Persistent trading memory**: Markdown journals allow the agent to carry lessons across sessions and improve its "user model" through a continuous **learning loop**.
- **Tamper-evident audit logs**: Cryptographic **hash-chain** tracking for accountability, **read-only** replay, and forensic review.
- **Bring-your-own model and provider**: **Provider-neutral** by design. You select the APIs, the models, and the credentials.

## Try Atlas in 5 minutes

Atlas Agent is **paper-first** and **safe by default**. No live trading, no broker credentials, and no provider API keys are required for this path.

```bash
# 1. Install
python3.11 -m pip install -e .

# 2. Create a workspace
atlas init my-workspace --template routine-trader
cd my-workspace
atlas discipline setup --manual --yes
atlas config set market.symbol ATLAS-DEMO

# 3. Validate
atlas validate

# 4. Explore the CLI
atlas --help

# 5. Run the reproducible paper demo
./scripts/demo_paper_workflow.sh
```

This path installs Atlas locally, creates a safe paper workspace, validates the configuration, explores the CLI, and runs the reproducible paper-mode demo. It produces local audit evidence only. It does not submit orders, call providers, use the network, or enable live trading. No `assets/atlas-demo.gif` recording is checked in yet; the reproducible demo script and the documented expected-output guide are the canonical demo artifacts.

For the canonical reviewer path, see [External Reviewer Walkthrough](docs/external-reviewer-walkthrough.md). For expected demo output, see [Demo: Paper Workflow](docs/demo-paper-workflow.md). For an indexed view of every demo artifact, its path, and the safety invariant it demonstrates, see [Demo Artifact Index](docs/demo-artifact-index.md).

## Quickstart

Atlas Agent is **sandbox-only**, **paper-first**, and **offline-safe** by default. Live trading is disabled by default. No broker orders or credential loading happen in the quickstart flow. Provider execution in the research workflow is governed by artifact-based safety policy and the risk manager — there is no runtime network block, and resulting orders are prevented by deterministic risk gates.

**Not financial advice.** Trading involves significant risk of loss.

### 1. Install

```bash
python3.11 -m pip install -e .
atlas --help
```

### 2. Create a workspace

```bash
atlas init my-workspace --template routine-trader
cd my-workspace
atlas discipline setup --manual --yes
atlas config set market.symbol ATLAS-DEMO
```

### 3. Validate configuration

```bash
atlas validate
```

Expected: a readiness report. Missing provider API keys are expected and safe — Atlas does not require real credentials for paper and backtest workflows.

### 4. Run a safe local backtest

```bash
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
```

This runs a deterministic buy-and-hold backtest on local sample data. No network, no broker, no credentials.

### 5. Inspect provider safety dossiers

```bash
atlas research provider-safety-dossier-latest --json
```

If no dossier exists, the command returns `found: false` safely. No errors, no leaks, no broker/order path, no credentials loaded. For the full workflow, see [Provider Safety Dossier](docs/provider-safety-dossier.md).

### 6. Run local diagnostics (safe, no credentials)

```bash
atlas memory doctor --json
atlas events doctor
```

These are local diagnostics. They do not submit orders, enable live trading, or load credentials.

### What is intentionally disabled

- **Live trading** requires explicit multi-factor opt-in, valid credentials, and kill-switch normal state.
- **Provider execution** remains locked — no real LLM/provider calls are made by default.
- **Broker order submission** is blocked by `can_submit=false`.
- **Credentials** are not loaded unless explicitly configured.

### Development checks

Tiered local check scripts help avoid running the full heavy gate on every iteration:

```bash
./scripts/release_check.sh --quick   # Fast dev loop
./scripts/release_check.sh --research
./scripts/release_check.sh --full    # Required before push/tag
```

Quick and research modes are developer convenience only. Full mode remains required before push/tag.

### Paper research workflow

The research workflow is paper-only and analysis-only. All commands operate on local artifacts and do not submit orders, create approvals, or authorize live trading. External and LLM research providers are not enabled in this development tag. For detailed command behavior, artifact schemas, and safety boundaries, see [docs/research-workflow.md](docs/research-workflow.md).

## Trust and Release Status

See the [Atlas Agent Trust Center](docs/trust/README.md) for the current public release, security posture, release assurance, provider audit evidence, updater delivery status, and explicit non-claims.

## System Status

| Component | Status | Description |
|---|---|---|
| **Local Workspace** | Usable | Core environment, CLI, and configuration management. |
| **Paper Workflow** | Usable | Deterministic local simulation with pricing. |
| **Risk Gates** | Implemented | Hard-coded limits for position size, notional, and symbols. |
| **Audit Logs** | Implemented | Tamper-evident hash-chain and run manifests. |
| **Broker/API Model** | Beta | Alpaca read-only live sync available. Other adapters remain beta/deferred. |
| **Live Trading** | Disabled by default | Strictly opt-in; `can_submit=false` is enforced by default. |
| **Broker Integrations** | Beta | Early-stage adapters for third-party broker APIs. |
| **Self-Improvement** | Early-Stage | Skill refinement and Markdown-based memory persistence. |
| **Dashboard** | Basic | Read-only local HTML snapshot for system visibility. |

## What this is

Atlas Agent is a **local-first research and paper-trading workbench** with deterministic safety gates, audit logs, and sandbox-only provider safety workflows. It helps you:

- Run deterministic backtests on local CSV data
- Build and review paper-only research artifacts
- Inspect provider safety dossiers in an offline mock workflow
- Maintain trading memory and audit trails

## What this is not

- **Not a live trading system by default.** Live trading is disabled by default and requires explicit multi-factor opt-in.
- **Does not imply profitable outcomes.** Atlas does not predict profit, guarantee returns, or claim future performance.
- **Not a broker.** Atlas is broker-neutral and does not custody funds.
- **Not a licensed financial advisor.** This is software, not financial advice.
- **Not autonomous.** All live actions require explicit human confirmation when enabled.

## Current Development Status

`v0.6.9` is the latest stable public release on GitHub. `v0.6.8`, `v0.6.7`, `v0.6.6`, and `v0.5.8` are historical stable releases. The source package version on `main` is `0.6.9`; `v0.6.10` is the next planning line and is not yet tagged or released. The v0.6.9 patch release contains backtest report quality and validation improvements. No new runtime features, broker adapters, or provider integrations. PyPI was not published.

- Live trading is disabled by default.
- Provider execution remains locked.
- Trust remains blocked.
- No profitability or trading correctness claims.
- Not financial advice.

## Broker-Neutral Model

Atlas Agent does not bundle, force, custody, or recommend broker accounts. It is designed as the broker-neutral **control layer** above user-selected models, broker/API providers, credentials, and risk limits. It treats the LLM as the reasoning engine and provides it with a toolset of **broker adapters** to perform web research, manage portfolios, and evaluate trade ideas through deterministic **risk gates**.

- **No Custody**: Atlas never touches your funds. It communicates with your chosen broker via your own API credentials.
- **No Recommendations**: The framework does not prefer any specific broker or provider. You choose the integration that fits your regulatory and financial requirements.
- **Universal Interface**: Switch between your preferred endpoints through a single configuration point. Supports [OpenRouter](https://openrouter.ai) (200+ models), [OpenAI](https://platform.openai.com/home), [Anthropic](https://www.anthropic.com), [Google Gemini](https://ai.google.dev/gemini-api/docs), [DeepSeek](https://platform.deepseek.com/docs), [xAI / Grok](https://docs.x.ai), [Kimi/Moonshot](https://platform.moonshot.ai), [Hugging Face](https://huggingface.co) (including z.ai/GLM models), [NVIDIA NIM](https://build.nvidia.com) (cloud and local/on-prem), [LM Studio](https://lmstudio.ai/docs), local / Ollama / llama.cpp endpoints, and other **custom endpoint** or **OpenAI-compatible** providers. For finance-specific deployments, the [Vals AI Finance Agent benchmark](https://www.vals.ai/benchmarks/fabv2) is a useful reference for model selection.

## Safety Model

- **Live trading disabled by default**: Atlas will never attempt live trading unless explicitly configured. Paper mode is the safest and default mode.
- **Deterministic Guardrails**: Risk controls are hard-coded and separate from the LLM. If the LLM proposes an order that violates a risk rule, the `RiskManager` is designed to block it.
- **Approval Gates**: Live orders can be configured to require manual approval via `atlas approve-order`. See [Pending Orders](docs/pending-orders.md) for details.
- **Kill Switch**: Advanced emergency stop with hierarchical modes. The **dead-man heartbeat** monitoring ensures the system fails closed if the process is interrupted.
- **Responsibility**: You are responsible for your API keys, broker permissions, and any financial outcomes. Atlas Agent provides the tools; you provide the oversight.
- **Live-Submit Safety Contract**: See [docs/live-submit-safety-contract.md](docs/live-submit-safety-contract.md) for the complete default-behavior, gating, state-machine, and audit rules that apply to live order submission.

**Safety validation does not imply profitability or trading correctness.** Safety checks validate structural boundaries, not strategy performance.

## Backtesting

Atlas Agent includes a deterministic, local-first backtesting engine to evaluate strategy behavior against historical benchmarks.

```bash
atlas backtest run --symbol AAPL --data path/to/data.csv
```

Backtesting is a research tool. Historical results do not guarantee future performance. Atlas does not predict profit; it measures strategy behavior against historical data.

## Configuration & Security

Atlas Agent uses a dual-layer configuration system to balance portability and security:

*   **`.atlas/config.toml`**: Stores non-secret configuration like your default symbol, trading hours, and risk parameters.
*   **`.env.atlas`**: Stores sensitive API keys and broker secrets. This file is automatically ignored by Git and protected by the `atlas update` process.

**Security Rules:**
*   Secrets go in `.env.atlas`.
*   `.env.atlas` is gitignored.
*   The dashboard is strictly **read-only** and must not expose secrets.
*   Audit logs and diagnostics are designed to redact secrets and sensitive free-text.

See [Model Providers](docs/model-providers.md) for provider/model selection and API key setup.

## Commands

The fastest way to explore the CLI is:

```bash
atlas --help               # all top-level commands
atlas backtest --help      # subcommands for a group
```

Common command families:

| Family | Representative commands | Purpose |
| :--- | :--- | :--- |
| **Workspace setup** | `atlas init`, `atlas setup`, `atlas validate`, `atlas config set ...` | Create and configure a safe paper workspace. |
| **Paper workflow** | `atlas run --mode paper`, `atlas agent run --mode paper`, `atlas run-once --mode paper` | Run the agent in simulation without broker orders. |
| **Backtesting** | `atlas backtest run --data ... --symbol ...`, `atlas backtest list-strategies` | Deterministic local strategy simulation. |
| **Research** | `atlas research run --symbol ...`, `atlas research plan`, `atlas research verify`, `atlas research summary` | Paper-only artifact generation and inspection. |
| **Risk & safety** | `atlas risk status`, `atlas kill status`, `atlas kill-switch status`, `atlas approve-order` | Inspect gates, kill switch, and approval queues. |
| **Broker (read-only)** | `atlas broker sync` | Synchronize account, positions, and orders from the broker. |
| **Diagnostics** | `atlas memory doctor --json`, `atlas events doctor`, `atlas audit verify --all` | Local health and audit checks. |
| **Deployment** | `atlas deploy systemd`, `atlas deploy docker`, `atlas deploy vps` | Deployment helpers. |

For a full parser-level inventory, see [docs/cli-command-compatibility.md](docs/cli-command-compatibility.md).

## Demos

Reproducible walkthroughs that show Atlas working as a broker-neutral supervised workspace:

- **[Paper Workflow Script](scripts/demo_paper_workflow.sh)** — create a temporary workspace, validate config, run a paper dry-run, execute a deterministic sample-data backtest, and verify audit artifacts.
- **[Research Workflow Script](scripts/demo_research_workflow.sh)** — create a temporary workspace, run the full paper-only research chain, validate JSON artifacts, and verify safety invariants.
- **[Paper Workflow](docs/demo-paper-workflow.md)** — create a workspace, validate config, and run a safe paper cycle with no live broker orders.
- **[Provider Preflight Dry-Run Demo](docs/demo/provider-preflight-demo.md)** — local provider preflight smoke chain and manual pipeline.
- **[Provider Safety Dossier](docs/provider-safety-dossier.md)** — offline mock workflow for the provider response pipeline.
- **[Risk Rejection](docs/demo-risk-rejection.md)** — see how deterministic risk gates block unsafe orders before they reach a broker.
- **[Audit Verification](docs/demo-audit.md)** — verify the tamper-evident hash-chain and run manifests.

## Telegram Control Plane

Atlas Agent does not enable a remote Telegram control plane by default. Any Telegram integration is optional, operator-supplied, and must remain gated by local risk controls, explicit approval, authentication, and secret redaction.

## Deployment and Cloud

Atlas is designed for local-first operation but can be deployed to a VPS, Docker container, or serverless job. Always ensure your environment variables are secured in your deployment target.

## Contributing and Security

We welcome contributions that respect the safe-by-default design. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, safety boundaries, and contribution rules. To report security or safety issues privately, use [GitHub Security Advisories](https://github.com/usernotfinded/atlas-agent/security/advisories). See [SECURITY.md](SECURITY.md) for the full security policy.

## Review and Feedback

New to the repo? Start with the [External Reviewer Walkthrough](docs/external-reviewer-walkthrough.md) for a 10–15 minute safe review path.

Key reviewer docs:
- **[Reviewer Checklist](docs/reviewer-checklist.md)**
- **[Public Launch Readiness](docs/public-launch-readiness.md)**
- **[Public Launch Messaging](docs/public-launch-messaging.md)**
- **[Public FAQ](docs/public-faq.md)**
- **[Feedback Request Guide](docs/feedback-request-guide.md)**
- **[Product Capability Inventory](docs/product-capability-inventory.md)**
- **[Final RC Audit](docs/final-rc-audit.md)**
- **[Final Release Candidate Checklist](docs/final-release-candidate-checklist.md)**
- **[Stable Release Decision](docs/stable-release-decision.md)**
- **[Stable Release Checklist](docs/stable-release-checklist.md)**
- **[CHANGELOG.md](CHANGELOG.md)**

## Release Assurance

After publishing a security release, maintainers can generate a local release assurance pack:

```bash
python scripts/release_assurance.py --version v0.6.9 --output artifacts/release_assurance/v0.6.9-local-check
```

The pack verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims. It does not create tags, publish packages, call providers, enable trading, or modify runtime behavior.

`.github/workflows/release-assurance.yml` can be run manually with `workflow_dispatch` to generate a fresh pack in GitHub Actions. It is read-only and non-publishing: it does not create tags, create GitHub releases, publish to PyPI, use secrets, call providers, touch brokers, or enable trading.

## Disclaimer

**NOT FINANCIAL ADVICE.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss. Live trading can lose real money. You are solely responsible for your deployment, risk limits, and any financial results. Use Paper Mode until you are fully confident in your strategy and configuration.

---

Built by Natan Mucelli.
