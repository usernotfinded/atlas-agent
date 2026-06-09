![Atlas Agent Banner](./assets/atlasagentbanner.png)

# Atlas Agent

<p align="center">
  <a href="https://github.com/usernotfinded/atlas-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/usernotfinded/atlas-agent/actions/workflows/ci.yml"><img src="https://github.com/usernotfinded/atlas-agent/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="#broker-neutral-model"><img src="https://img.shields.io/badge/Positioning-Broker%20Neutral-blue?style=for-the-badge" alt="Broker Neutral"></a>
  <a href="docs/model-providers.md"><img src="https://img.shields.io/badge/Providers-11%2B-orange?style=for-the-badge" alt="11+ Providers"></a>
  <a href="https://github.com/usernotfinded"><img src="https://img.shields.io/badge/Built%20by-Natan%20Mucelli-blueviolet?style=for-the-badge" alt="Built by Natan Mucelli"></a>
</p>

**Atlas Agent turns your preferred LLM and broker/API provider into a supervised trading workspace, with market research, paper workflows, trading memory, audit logs, approval queues, and deterministic risk gates.**

> **Current Status (v0.6.6)** — package/source version is `0.6.6`; latest stable public release is [v0.6.6](docs/releases/v0.6.6.md) on GitHub. v0.6.5, v0.6.4, v0.6.3, v0.6.2, v0.6.1, and v0.6.0 are historical. PyPI was not published.

> **DISCLAIMER:** Not financial advice. Live trading is disabled by default. Live submit remains disabled by default. Atlas is broker-neutral: users choose their own model, broker/API provider, credentials, and risk limits. Trading involves significant risk of loss.

## Try Atlas in 5 minutes

Atlas Agent is **paper-first** and **safe by default**. No live trading, no broker credentials, and no provider API keys are required for this path.

```bash
# 1. Install
python3.11 -m pip install -e .

# 2. Create a workspace
atlas init my-workspace --template routine-trader
cd my-workspace
atlas discipline setup --manual --yes
atlas config set market.symbol DEMO-SYMBOL

# 3. Validate
atlas validate

# 4. Run the reproducible paper demo
./scripts/demo_paper_workflow.sh
```

This path installs Atlas locally, creates a safe paper workspace, validates the configuration, and runs the reproducible paper-mode demo. It produces local audit evidence only. It does not submit orders, call providers, use the network, or enable live trading.

### What this quick path shows

- Local install validation
- Paper-mode workspace setup
- Deterministic backtest on sample data
- Tamper-evident audit trail generation
- No live trading, no broker credentials, no provider calls

## Trust and Release Status

See the [Atlas Agent Trust Center](docs/trust/README.md) for the current public release, security posture, release assurance, provider audit evidence, updater delivery status, and explicit non-claims. The trust center is checked by `scripts/check_trust_center.py` to prevent stale public release/security messaging.

## Contributor Onboarding

See [Contributor Onboarding](docs/development/onboarding.md) for Python 3.11 setup, dev extras, safe local checks, evidence commands, generated artifact hygiene, GitHub Actions maintenance, and commands that require explicit owner approval. The onboarding docs are checked by `scripts/check_onboarding_docs.py`. Generated local evidence outputs are covered by [Generated Artifacts](docs/development/generated-artifacts.md) and checked by `scripts/check_generated_artifacts.py`. Workflow action version policy is covered by [GitHub Actions Maintenance](docs/development/github-actions.md) and checked by `scripts/check_github_actions_versions.py`. Direct-main maintainers can use [Main Health Report](docs/development/main-health.md) after a push to verify local `main`, `origin/main`, optional GitHub CI visibility, artifact hygiene, and release/tag safety.

Atlas is the broker-neutral control layer above user-selected models, broker/API providers, credentials, and risk limits. It treats the LLM as the reasoning engine and provides it with a toolset of **broker adapters** to perform web research, manage portfolios, and evaluate trade ideas through a rigorous deterministic **risk gates** layer.

## Demo

Run the reproducible paper-mode workflow:

```bash
./scripts/demo_paper_workflow.sh
```

The demo creates a temporary Atlas workspace, installs a safe discipline profile, sets the explicit `ATLAS-DEMO` paper symbol, runs `atlas validate`, shows a paper-mode dry run, runs a deterministic sample-data backtest with the `DEMO-SYMBOL` fixture, and verifies audit manifests when present.

It does not require live trading, real broker credentials, or private values. It is a paper-mode proof of workflow mechanics, not a live-trading setup or performance claim. No `assets/atlas-demo.gif` recording is checked in yet; the script is the reproducible demo artifact.

## Provider preflight dry-run demo

Run the local provider preflight smoke chain:

```bash
atlas providers smoke-preflight-chain \
  --provider openrouter \
  --model "openrouter/auto" \
  --purpose "research-summary" \
  --max-context-chars 4000 \
  --output-dir artifacts/provider_preflight_smoke/demo
```

This creates local audit evidence only: `call-plan.json`,
`validation-report.json`, `manifest.json`, `sha256sums.txt`, and
`smoke-report.json`. It does not call providers, use the network, load
credentials, import provider SDKs, touch brokers, enable live trading, create
pending orders, or approve orders.

Provider preflight artifacts are audit evidence only. They do not authorize
provider execution, broker execution, live trading, or order approval. For the
manual generate/validate/bundle/verify workflow, see
[Provider Preflight Dry-Run Demo](docs/demo/provider-preflight-demo.md).

Create a complete local provider audit pack in one run:

```bash
atlas providers audit-pack \
  --provider openrouter \
  --model "openrouter/auto" \
  --purpose "research-summary" \
  --max-context-chars 4000 \
  --output-dir artifacts/provider_audit_pack/<timestamp>
```

The audit pack adds an evidence index, Markdown report, compact JSON summary,
and `audit-pack-manifest.json`. It is local-only and non-authorizing; it does
not call providers, load credentials, use the network, touch brokers, or enable
execution. See [Provider Audit Pack](docs/security/provider-audit-pack.md). This pack can also be verified and generated in CI as a non-authorizing artifact.

## Provider capability inventory and readiness

Atlas also supports a local readiness gate to audit policy compliance:

```bash
atlas providers capability-inventory
atlas providers readiness-check \
  --provider openrouter \
  --model "openrouter/auto" \
  --purpose "research-summary"
```

These commands run strictly offline, do not load credentials, and the policy currently always evaluates to `preflight_only`.

## Why Atlas?

- **LLM-assisted market research**: Leverage advanced models to process market context and form data-driven theses.
- **Paper workflows**: Validate strategies using deterministic local **simulation** before risking capital. Every **market-open** session is designed to favor simulation until explicitly authorized. During **closed-market** hours, Atlas focuses on **learning** and research.
- **Deterministic risk gates**: Safety controls are decoupled from LLM reasoning to help reduce unintended actions.
- **Approval queues**: Live actions are designed to require explicit human confirmation via local queues.
- **Persistent trading memory**: Markdown journals allow the agent to carry lessons across sessions and improve its "user model" through a continuous **learning loop**.
- **Tamper-evident audit logs**: Cryptographic **hash-chain** tracking for accountability, **read-only** replay, and forensic review.
- **Bring-your-own model and provider**: **Provider-neutral** by design. You select the APIs, the models, and the credentials.

## Broker-Neutral Model

Atlas Agent does not bundle, force, custody, or recommend broker accounts. It is designed as the control layer above user-selected APIs.

- **No Custody**: Atlas never touches your funds. It communicates with your chosen broker via your own API credentials.
- **No Recommendations**: The framework does not prefer any specific broker or provider. You choose the integration that fits your regulatory and financial requirements.
- **Universal Interface**: Switch between your preferred endpoints through a single configuration point. Supports [OpenRouter](https://openrouter.ai) (200+ models), [NVIDIA NIM](https://build.nvidia.com), [z.ai/GLM](https://z.ai), [Kimi/Moonshot](https://platform.moonshot.ai), [Hugging Face](https://huggingface.co), [OpenAI](https://platform.openai.com/home), and other **custom endpoint** or **OpenAI-compatible** providers. For finance-specific deployments, the [Vals AI Finance Agent benchmark](https://www.vals.ai/benchmarks/fabv2) is a useful reference for model selection.

## System Status

| Component | Status | Description |
|---|---|---|
| **Local Workspace** | Usable | Core environment, CLI, and configuration management. |
| **Paper Workflow** | Usable | Deterministic local simulation with pricing. |
| **Risk Gates** | Implemented | Hard-coded limits for position size, notional, and symbols. |
| **Audit Logs** | Implemented | Tamper-evident hash-chain and run manifests. |
| **Broker/API Model** | Beta | Alpaca read-only live sync available. `AlpacaBrokerAdapter.get_order_by_client_order_id` supports reconciliation. Other adapters remain beta/deferred. |
| **Live Trading** | Disabled by default | Strictly opt-in; by default `can_submit=false` is enforced and `resolve_execution_broker("live")` returns `None`. Only after the explicit Batch 5.0 live-submit opt-in gates are all satisfied can `can_submit` become `true` and `resolve_execution_broker("live")` return a real broker. |
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

`v0.6.6` is the latest stable public release on GitHub. `v0.5.8` is a historical stable release. The `0.6.6` source version is tagged and released. The v0.6.6 patch release contains docs consistency, checker metadata, test coverage, and public release reference alignment improvements. No new runtime features, broker adapters, or provider integrations. PyPI was not published. After direct-main maintenance pushes, run `python3.11 scripts/main_health.py` for local post-push verification.

- Live trading is disabled by default.
- Provider execution remains locked.
- Trust remains blocked.
- No profitability or trading correctness claims.
- Not financial advice.

## Review and Feedback

New to the repo? Start with the [External Reviewer Walkthrough](docs/external-reviewer-walkthrough.md) for a 10–15 minute safe review path.

Key reviewer docs:
- **[Reviewer Checklist](docs/reviewer-checklist.md)** — checklist before trusting or recommending
- **[Public Launch Readiness](docs/public-launch-readiness.md)** — verified checks and disabled features
- **[Public Launch Messaging](docs/public-launch-messaging.md)** — safe draft messaging for feedback requests
- **[Public FAQ](docs/public-faq.md)** — answers to common questions
- **[Feedback Request Guide](docs/feedback-request-guide.md)** — how to ask for feedback safely
- **[Product Capability Inventory](docs/product-capability-inventory.md)** — capability matrix and public-claim boundaries
- **[Final RC Audit](docs/final-rc-audit.md)** — release-manager audit of the RC series
- **[Final Release Candidate Checklist](docs/final-release-candidate-checklist.md)** — go/no-go checklist
- **[Stable Release Decision](docs/stable-release-decision.md)** — decision record for stable v0.5.8
- **[Stable Release Checklist](docs/stable-release-checklist.md)** — pre-tag checklist
- **[Controlled Reviewer Outreach](docs/controlled-reviewer-outreach.md)** — safe copy-paste review requests

For full release history, see [CHANGELOG.md](CHANGELOG.md). Release engineering preflight is documented in [Release Candidate Cutover Dry Run](docs/release-candidate-cutover.md).

## Contributing and Security

We welcome contributions that respect the safe-by-default design. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, safety boundaries, and contribution rules. To report security or safety issues privately, use [GitHub Security Advisories](https://github.com/usernotfinded/atlas-agent/security/advisories). See [SECURITY.md](SECURITY.md) for the full security policy.


## Quickstart

Atlas Agent is **sandbox-only**, **paper-first**, and **offline-safe** by default. Live trading is disabled by default. No broker orders or credential loading happen in the quickstart flow. Provider execution in the research workflow is governed by artifact-based safety policy and the risk manager — there is no runtime network block, and resulting orders are prevented by deterministic risk gates.

**Not financial advice.** Trading involves significant risk of loss.

### 1. Install

```bash
python3.11 -m pip install -e .
atlas --help
```

### 2. Create a workspace

Most commands require an Atlas workspace.

```bash
atlas init my-workspace --template routine-trader
cd my-workspace
atlas discipline setup --manual --yes
atlas config set market.symbol DEMO-SYMBOL
```

### 3. Validate configuration

```bash
atlas validate
```

Expected: a readiness report. Missing provider API keys are expected and safe — Atlas does not require real credentials for paper and backtest workflows.

The `routine-trader` workspace template is packaged with Atlas Agent, so
`atlas init --template routine-trader` works from editable, wheel, and source
distribution installs without relying on the source repository checkout.

### 4. Run a safe local backtest

```bash
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
```

This runs a deterministic buy-and-hold backtest on local sample data. No network, no broker, no credentials.

### 5. Inspect provider safety dossiers

```bash
atlas research provider-safety-dossier-latest --json
atlas research provider-safety-dossier-list --status sandbox_chain_complete --limit 5 --json
```

If no dossier exists, the command returns `found: false` safely. No errors, no leaks, no broker/order path, no credentials loaded.

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
# Fast dev loop (no full pytest, no demos)
./scripts/release_check.sh --quick

# Research/sandbox gate (research tests + research demo)
./scripts/release_check.sh --research

# Full release gate (required before push/tag)
./scripts/release_check.sh --full
```

Quick and research modes are developer convenience only. Full mode remains required before push/tag.

### Paper research workflow

The research workflow is paper-only and analysis-only. All commands operate on local artifacts and do not submit orders, create approvals, or authorize live trading.

Research currently uses a deterministic local provider. External and LLM research providers are not enabled in this development tag. Research remains paper-only and analysis-only.

For detailed command behavior, artifact schemas, and safety boundaries, see [docs/research-workflow.md](docs/research-workflow.md).

Create a local research artifact:
- `atlas research run --symbol AAPL`

Discover and inspect existing artifacts:
- `atlas research list`
- `atlas research show RUN_ID`

Create a paper-only plan from a research artifact:
- `atlas research plan RUN_ID`

Verify a paper plan for completeness and safety:
- `atlas research verify PLAN_ID`

Evaluate a paper plan against local data:
- `atlas research evaluate PLAN_ID --data PATH`

Overview all research artifacts and plans:
- `atlas research summary`

Check local artifact health:
- `atlas research check-artifacts`

View artifact lineage/timeline:
- `atlas research timeline`

Show available research providers:
- `atlas research providers`

Generate a sanitized prompt packet from a research artifact:
- `atlas research prompt RUN_ID`

Simulate a deterministic provider response from a prompt packet:
- `atlas research simulate-provider PROMPT_PACKET_ID`

Review a provider response artifact deterministically:
- `atlas research review-response PROVIDER_RESPONSE_ID`

Build a deterministic dossier consolidating a research chain:
- `atlas research dossier RUN_ID`

## Provider Safety Dossier

The provider safety dossier is a **sandbox-only**, **offline mock workflow** that produces a local safety report for the provider response pipeline. It does not submit orders, call brokers, or enable live trading.

The chain works as follows:

1. **`mock_response_simulation`** — Generate a deterministic mock provider response from a local prompt packet. No network, no API keys.
2. **`mock_response_import_candidate`** — Import a locally prepared provider response JSON file for review. No real provider calls.
3. **`mock_response_review_sandbox`** — Run a deterministic sandbox review of the imported response against safety rules. No trust is granted.
4. **`mock_response_trust_decision_blocker`** — Record the explicit decision to **block** trust. The response is not trusted; execution remains locked.
5. **`mock_response_final_safety_seal`** — Apply a final local safety seal over the blocked chain. The seal is tamper-evident and offline.
6. **`provider_safety_dossier`** — Consolidate the entire chain into one summary artifact with hashes, lineage, and safety verdict.
7. **`provider_safety_dossier Markdown export`** — Export the dossier to a human-readable Markdown file with redacted paths and safe sentinels.
8. **`provider_safety_dossier discovery UX`** — List, filter, and discover dossiers by status without exposing raw invalid fields or absolute paths.

Key safety properties:

- **Sandbox-only** — The entire pipeline operates on local mock responses.
- **Offline mock workflow** — No external LLM or provider calls are made.
- **Provider execution remains locked** — No real provider calls are authorized.
- **Trust remains blocked** — Mock responses are explicitly not trusted.
- **No broker/order path** — No orders, approvals, or broker contact.
- **No credentials loaded** — `.env.atlas` is not read during dossier creation.
- **No network enabled** — All artifacts are local.
- **Live trading disabled by default** — The dossier is a report, not an execution trigger.
- **Safety validation does not imply profitability or trading correctness** — The dossier validates structural safety, not strategy performance.

Command examples:

```bash
atlas research provider-safety-dossier-latest --json
atlas research provider-safety-dossier-list --status sandbox_chain_complete --limit 5 --json
atlas research provider-safety-dossier-export <DOSSIER_ID> --format markdown --output reports/provider-safety-dossier.md
```

For the full public documentation, see [docs/provider-safety-dossier.md](docs/provider-safety-dossier.md). For a step-by-step workflow, see [docs/examples/provider-safety-dossier-workflow.md](docs/examples/provider-safety-dossier-workflow.md).

## Demos

Reproducible walkthroughs that show Atlas working as a broker-neutral supervised workspace:

- **[Paper Workflow Script](scripts/demo_paper_workflow.sh)** — create a temporary workspace, validate config, run a paper dry-run, execute a deterministic sample-data backtest, and verify audit artifacts.
- **[Research Workflow Script](scripts/demo_research_workflow.sh)** — create a temporary workspace, run the full paper-only research chain (run → list → show → plan → verify → evaluate → summary → check-artifacts → timeline → providers → prompt → sandbox → simulate-provider → review-response → dossier), validate JSON artifacts, and verify safety invariants.
- **[Paper Workflow](docs/demo-paper-workflow.md)** — create a workspace, validate config, and run a safe paper cycle with no live broker orders.
- **[Risk Rejection](docs/demo-risk-rejection.md)** — see how deterministic risk gates block unsafe orders before they reach a broker.
- **[Audit Verification](docs/demo-audit.md)** — verify the tamper-evident hash-chain and run manifests.

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

## Safety Model

*   **Simulation by Default**: Atlas Agent will never attempt live trading unless explicitly configured. Paper mode is the safest and default mode.
*   **Deterministic Guardrails**: Risk controls are hard-coded and separate from the LLM. If the LLM proposes an order that violates a risk rule, the `RiskManager` is designed to block it.
*   **Approval Gates**: Live orders can be configured to require manual approval via `atlas approve-order`. See [Pending Orders](docs/pending-orders.md) for details.
*   **Kill Switch**: Advanced emergency stop with hierarchical modes. The **dead-man heartbeat** monitoring ensures the system fails closed if the process is interrupted.
*   **Responsibility**: You are responsible for your API keys, broker permissions, and any financial outcomes. Atlas Agent provides the tools; you provide the oversight.
*   **Live-Submit Safety Contract**: See [docs/live-submit-safety-contract.md](docs/live-submit-safety-contract.md) for the complete default-behavior, gating, state-machine, and audit rules that apply to live order submission.

## Backtesting

Atlas Agent includes a deterministic, local-first backtesting engine to evaluate strategy behavior against historical benchmarks.

```bash
# Run a buy-and-hold backtest
atlas backtest run --symbol AAPL --data path/to/data.csv
```

**Note:** Backtesting is a research tool. Historical results do not guarantee future performance. Atlas does not predict profit; it measures strategy behavior against historical data.

## Telegram Control Plane

Atlas Agent does not enable a remote Telegram control plane by default. Any Telegram integration is optional, operator-supplied, and must remain gated by local risk controls, explicit approval, authentication, and secret redaction.

## Deployment and Cloud

Atlas is designed for local-first operation but can be deployed to a VPS, Docker container, or serverless job. Always ensure your environment variables are secured in your deployment target.

## Commands

| Command | Purpose |
| :--- | :--- |
| `atlas backtest run` | Run a deterministic backtest on historical CSV data. |
| `atlas broker sync` | Synchronize account, positions, and orders from the broker. |
| `atlas audit verify` | Verify the JSONL audit log hash-chain. |
| `atlas memory doctor --json` | Local diagnostic: inspect workspace memory health. No broker, no credentials. |
| `atlas events doctor` | Local diagnostic: inspect workspace events health. No broker, no credentials. |

## Disclaimer

**NOT FINANCIAL ADVICE.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss. Live trading can lose real money. You are solely responsible for your deployment, risk limits, and any financial results. Use Paper Mode until you are fully confident in your strategy and configuration.

---
Built by Natan Mucelli.

## Release assurance

After publishing a security release, maintainers can generate a local release assurance pack:

```bash
python scripts/release_assurance.py --version v0.6.6 --output artifacts/release_assurance/v0.6.6-local-check
```

The pack verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims.

It does not create tags, publish packages, call providers, enable trading, or modify runtime behavior.

## CI release assurance

`.github/workflows/release-assurance.yml` can be run manually with `workflow_dispatch` to generate a fresh release assurance pack in GitHub Actions.

The workflow verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims, then uploads the generated assurance pack as an artifact.

It is read-only and non-publishing. It does not create tags, create GitHub releases, publish to PyPI, use secrets, call providers, touch brokers, or enable trading.
