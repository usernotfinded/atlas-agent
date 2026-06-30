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

> **Current Status (v0.6.17)** — package/source version is `0.6.17`. `v0.6.17` is the current public GitHub release. `v0.6.16` is the historical previous public release. `v0.6.18` is the next planning line. Historical stable baseline is `v0.5.8`. PyPI was not published. See [CHANGELOG.md](CHANGELOG.md) for full release history.

> **DISCLAIMER:** Not financial advice. Live trading is disabled by default. Atlas is broker-neutral: users choose their own model, broker/API provider, credentials, and risk limits. Trading involves significant risk of loss.

## Why Atlas?

### What this is

Atlas Agent is a **local-first research and paper-trading workbench** with deterministic safety gates, audit logs, and sandbox-only provider safety workflows.

- **LLM-assisted market research** — Leverage advanced models to process market context and form data-driven theses.
- **Paper workflows** — Validate strategies using deterministic local simulation before risking capital. Market-open sessions favor simulation until explicitly authorized; closed-market hours focus on learning and research.
- **Deterministic risk gates** — Safety controls are hard-coded and decoupled from LLM reasoning to help reduce unintended actions.
- **Approval queues** — Live actions require explicit human confirmation via local queues.
- **Persistent trading memory** — Markdown journals carry lessons across sessions through a continuous learning loop.
- **Tamper-evident audit logs** — Cryptographic hash-chain tracking for accountability, read-only replay, and forensic review.
- **Bring-your-own model and provider** — Provider-neutral by design. You select the APIs, the models, and the credentials.

### What this is not

- **Not a live trading system by default** — live trading requires explicit multi-factor opt-in. Not a broker (no custody). Not a financial advisor. Not autonomous.

## Quickstart

Atlas Agent is **paper-first** and **safe by default**. No live trading, no broker credentials, and no provider API keys are required.

```bash
python3.11 -m pip install -e .
./scripts/demo_paper_workflow.sh
```

This is the canonical first run. The script creates an isolated temporary
workspace, applies `atlas config set market.symbol ATLAS-DEMO`, validates local
paper state, runs redacted diagnostics, prints a paper dry-run, and executes the
bundled deterministic `DEMO-SYMBOL` backtest.

This quickstart is offline-safe, sandbox-only, and paper-first. No credentials loaded.
There is no broker/order path and no provider call. Live trading disabled by default.
Safety validation does not imply profitability or trading correctness.

Optional local inspection commands:

```bash
atlas --help
atlas validate
atlas backtest runs --validate --json
```

Use these canonical references instead of copying the workflow into another
guide:

- [Reviewer Golden-Path Validation Guide](docs/reviewer-golden-path.md) for the
  reviewer command sequence and release checks.
- [Paper-Trading Guide](docs/paper-trading-guide.md) for manual setup and the
  annotated fail-closed configuration.
- [Broker and Provider Preflight Diagnostics](docs/preflight-diagnostics.md)
  for the read-only `atlas doctor` contract.
- [Demo: Paper Workflow](docs/demo-paper-workflow.md) for expected output.
- [Demo Artifact Index](docs/demo-artifact-index.md) for generated local
  evidence.

### What is intentionally disabled

- **Live trading** requires explicit multi-factor opt-in, valid credentials, and kill-switch normal state.
- **Provider execution** remains locked — no real LLM/provider calls are made by default.
- **Broker order submission** is blocked by `can_submit=false`.
- **Credentials** are not loaded unless explicitly configured.

### Development checks

```bash
./scripts/release_check.sh --quick   # Fast dev loop
./scripts/release_check.sh --research # Research/sandbox gate
./scripts/release_check.sh --full    # Required before push/tag
```

### Paper research workflow

The research workflow is paper-only and analysis-only. All commands operate on local artifacts. External and LLM research providers are not enabled in this development tag. For detailed command behavior, artifact schemas, and safety boundaries, see [docs/research-workflow.md](docs/research-workflow.md).

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

`v0.6.17` is the current public GitHub release. `v0.6.16` is the historical previous public release. `v0.6.18` is the next planning line. The package/source version on main is `0.6.17`. Provider execution remains locked. Trust remains blocked. Live submit remains disabled by default. No profitability or trading correctness claims.

## Broker-Neutral Model

Atlas Agent does not bundle, force, custody, or recommend broker accounts. It is the control layer above user-selected models, broker/API providers, credentials, and risk limits. It treats the LLM as the reasoning engine and provides it with a toolset of **broker adapters** to perform web research, manage portfolios, and evaluate trade ideas through deterministic **risk gates**.

- **No Custody** — Atlas never touches your funds. It communicates with your chosen broker via your own API credentials.
- **No Recommendations** — The framework does not prefer any specific broker or provider.
- **Universal Interface** — Supports [OpenRouter](https://openrouter.ai) (200+ models), [OpenAI](https://platform.openai.com/home), [Anthropic](https://www.anthropic.com), [Google Gemini](https://ai.google.dev/gemini-api/docs), [DeepSeek](https://platform.deepseek.com/docs), [xAI / Grok](https://docs.x.ai), [Z.ai/GLM](https://www.z.ai), [Kimi/Moonshot](https://platform.moonshot.ai), [Hugging Face](https://huggingface.co), [NVIDIA NIM](https://build.nvidia.com) (cloud and local/on-prem), [LM Studio](https://lmstudio.ai/docs), local / Ollama / llama.cpp endpoints, and other **custom** or **OpenAI-compatible** providers. See [Model Providers](docs/model-providers.md) for the full catalog.

For guidance on which model to choose, see the [Vals AI Finance Agent Benchmark](https://www.vals.ai/benchmarks/fabv2).

## Safety Model

- **Deterministic Guardrails** — Risk controls are hard-coded and separate from the LLM. If the LLM proposes an order that violates a risk rule, the `RiskManager` blocks it.
- **Approval Gates** — Live orders can be configured to require manual approval via `atlas approve-order`. See [Pending Orders](docs/pending-orders.md).
- **Kill Switch** — Advanced emergency stop with hierarchical modes. Dead-man heartbeat monitoring ensures the system fails closed if the process is interrupted.
- **Live-Submit Safety Contract** — See [docs/live-submit-safety-contract.md](docs/live-submit-safety-contract.md) for the complete gating, state-machine, and audit rules.
- **Responsibility** — You are responsible for your API keys, broker permissions, and any financial outcomes.
- **Artifact-Based Safety Policy** — Provider execution follows an artifact-based safety policy enforced by the risk manager (`RiskManager`); there is no runtime network block on the host, so the policy is applied deterministically at the execution boundary.

## Backtesting

Atlas includes a deterministic, local-first backtesting engine to evaluate strategy behavior against historical benchmarks.

```bash
atlas backtest run --symbol AAPL --data path/to/data.csv
atlas backtest compare --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL --output-dir <temp-dir>
atlas backtest robustness --fixtures data/sample/regimes/ohlcv_uptrend.csv,data/sample/regimes/ohlcv_downtrend.csv,data/sample/regimes/ohlcv_flat.csv,data/sample/regimes/ohlcv_volatile.csv --symbol DEMO-SYMBOL --output-dir <temp-dir>
atlas backtest portfolio-stress --data data/sample/ohlcv_extended.csv --symbol DEMO-SYMBOL --output-dir <temp-dir>
atlas backtest portfolio-review-pack --data data/sample/ohlcv_extended.csv --symbol DEMO-SYMBOL --output-dir <temp-dir>
atlas backtest portfolio-review-policy --data data/sample/ohlcv_extended.csv --symbol DEMO-SYMBOL --output-dir <temp-dir>
atlas backtest portfolio-review-replay --data data/sample/ohlcv_extended.csv --symbol DEMO-SYMBOL --output-dir <temp-dir>
```

For paper-only strategy comparison, see
[Paper Strategy Evaluation](docs/paper-strategy-evaluation.md),
[Paper Strategy Sensitivity Evaluation](docs/paper-strategy-sensitivity.md), and
[Paper Strategy Robustness Report](docs/paper-strategy-robustness.md),
[Paper Strategy Walk-Forward Stability](docs/paper-strategy-walk-forward.md), and
[Paper Strategy Scorecard](docs/paper-strategy-scorecard.md), plus
[Paper Portfolio Stress Constraints](docs/paper-portfolio-stress.md). The
[v0.6.13 Paper Autonomy Evidence Bundle](docs/releases/v0.6.13-paper-autonomy-evidence.md)
collects CAND-021 through CAND-029 evidence for the historical planning line,
while the [v0.6.14 Paper Portfolio Evidence Bundle](docs/releases/v0.6.14-paper-portfolio-evidence.md)
and [v0.6.14 Final Paper Portfolio Readiness Audit](docs/releases/v0.6.14-final-readiness-audit.md)
preserve the historical pre-cutover evidence for the GitHub-only `v0.6.14`
release through CAND-008.
Historical results do not guarantee future performance.

## Configuration & Security

Atlas uses a dual-layer configuration system:

*   **`.atlas/config.toml`** — Non-secret configuration (symbol, trading hours, risk parameters). Safe to share.
*   **`.env.atlas`** — Sensitive API keys and broker secrets. Gitignored by default.

The dashboard is strictly **read-only** and must not expose secrets. Audit logs and diagnostics redact secrets and sensitive free-text. See [Model Providers](docs/model-providers.md) for provider/model selection and API key setup.

## Commands

The fastest way to explore the CLI:

```bash
atlas --help               # all top-level commands
atlas backtest --help      # subcommands for a group
```

Common command families:

| Family | Representative commands | Purpose |
| :--- | :--- | :--- |
| **Workspace setup** | `atlas init`, `atlas setup`, `atlas validate`, `atlas config set ...` | Create and configure a safe paper workspace. |
| **Paper workflow** | `atlas run --mode paper`, `atlas agent run --mode paper`, `atlas run-once --mode paper` | Run the agent in simulation without broker orders. |
| **Backtesting** | `atlas backtest run --data ... --symbol ...`, `atlas backtest compare --data ... --symbol ... --output-dir ...`, `atlas backtest robustness --fixtures ... --symbol ... --output-dir ...`, `atlas backtest portfolio-stress --data ... --symbol ... --output-dir ...`, `atlas backtest portfolio-monitor --data ... --symbol ... --output-dir ...`, `atlas backtest portfolio-review-pack --data ... --symbol ... --output-dir ...`, `atlas backtest portfolio-review-policy --data ... --symbol ... --output-dir ...`, `atlas backtest list-strategies` | Deterministic local strategy simulation and paper-only strategy comparison. |
| **Research** | `atlas research run --symbol ...`, `atlas research list`, `atlas research show`, `atlas research plan`, `atlas research verify`, `atlas research summary`, `atlas research evaluate`, `atlas research prompt`, `atlas research simulate-provider`, `atlas research review-response`, `atlas research dossier` | Paper-only artifact generation and inspection. |
| **Risk & safety** | `atlas risk status`, `atlas kill-switch status`, `atlas approve-order` | Inspect gates, kill switch, and approval queues. |
| **Broker (read-only)** | `atlas broker sync` | Synchronize account, positions, and orders from the broker. |
| **Diagnostics** | `atlas doctor`, `atlas memory doctor --json`, `atlas events doctor`, `atlas audit verify --all` | Local health and audit checks. `atlas doctor` inspects broker/provider config without network or execution. |
| **Deployment** | `atlas deploy systemd`, `atlas deploy docker`, `atlas deploy vps` | Deployment helpers. |

For a full parser-level inventory, see [docs/cli-command-compatibility.md](docs/cli-command-compatibility.md).
For the broker/provider diagnostic fields and safety limits, see
[Broker and Provider Preflight Diagnostics](docs/preflight-diagnostics.md).

## Demos

Reproducible walkthroughs that show Atlas working as a broker-neutral supervised workspace:

- **[Paper Workflow Script](scripts/demo_paper_workflow.sh)** — create a temporary workspace, validate config, run a paper dry-run, execute a deterministic sample-data backtest, and verify audit artifacts.
- **[Research Workflow Script](scripts/demo_research_workflow.sh)** — create a temporary workspace, run the full paper-only research chain, validate JSON artifacts, and verify safety invariants.
- **[Autonomous Paper Workflow](docs/autonomous-paper-workflow.md)** — deterministic, offline, no-credential L1 autonomy demo that runs paper-only CLI commands autonomously, verifies live paths fail safely, and produces local evidence artifacts. See `scripts/demo_autonomous_paper_workflow.sh`.
- **[Paper Mode Provider Isolation](docs/paper-provider-isolation.md)** — paper-mode workflows can run without an AI provider API key or network access; live mode remains fail-closed.
- **[Paper Strategy Evaluation](docs/paper-strategy-evaluation.md)** — deterministic sample-data strategy comparison with paper-only candidate/reject/needs-more-testing reports. See `scripts/demo_paper_strategy_evaluation.sh`.
- **[Paper Strategy Sensitivity Evaluation](docs/paper-strategy-sensitivity.md)** — deterministic parameter sensitivity matrix for paper-only follow-up. See `scripts/demo_paper_strategy_sensitivity.sh`.
- **[Paper Strategy Robustness Report](docs/paper-strategy-robustness.md)** — deterministic multi-regime synthetic fixture report for paper-only follow-up. See `scripts/demo_paper_strategy_robustness.sh`.
- **[Paper Strategy Walk-Forward Stability](docs/paper-strategy-walk-forward.md)** — deterministic rolling-window paper stability checks. See `scripts/demo_paper_strategy_walk_forward.sh`.
- **[Paper Strategy Scorecard](docs/paper-strategy-scorecard.md)** — paper-only candidate ledger across evaluation, sensitivity, robustness, and walk-forward gates. See `scripts/demo_paper_strategy_scorecard.sh`.
- **[Paper Portfolio Stress Constraints](docs/paper-portfolio-stress.md)** — deterministic paper-only synthetic stress checks for proposal drawdown, scenario loss, concentration, and cash guardrails. See `scripts/demo_paper_portfolio_stress.sh`.
- **[Paper Portfolio Monitoring Simulation](docs/paper-portfolio-monitoring.md)** — deterministic paper-only monitoring simulation windows with recheck/watchlist triggers over sample data. See `scripts/demo_paper_portfolio_monitoring.sh`.
- **[v0.6.13 Paper Autonomy Evidence Bundle](docs/releases/v0.6.13-paper-autonomy-evidence.md)** — planning-only CAND-021 through CAND-029 closure evidence with no release, tag, PyPI, or live-trading side effects.
- **[v0.6.14 Paper Portfolio Evidence Bundle](docs/releases/v0.6.14-paper-portfolio-evidence.md)** — historical pre-cutover CAND-001 through CAND-007 paper portfolio closure evidence.
- **[v0.6.14 Final Paper Portfolio Readiness Audit](docs/releases/v0.6.14-final-readiness-audit.md)** — historical pre-cutover CAND-008 Go/No-Go dossier preserved after the separately authorized GitHub-only release.
- **[Paper Human Review Pack](docs/paper-human-review-pack.md)** — deterministic, offline, non-executable review dossier derived from v0.6.14 paper portfolio evidence. See `scripts/demo_paper_human_review_pack.sh`.
- **[Paper Human Review Ledger](docs/paper-human-review-ledger.md)** — deterministic, offline, non-executable simulated human-review decision ledger derived from the CAND-001 review pack. See `scripts/demo_paper_human_review_ledger.sh`.
- **[Paper Human Review Policy Simulator](docs/paper-human-review-policy.md)** — v0.6.15 CAND-003 deterministic, offline, non-executable policy simulation against the CAND-001 review pack and CAND-002 review ledger. Produces a blocked-live gate artifact; no live trading, broker submission, provider execution, notifications, orders, or real human approval. See `scripts/demo_paper_human_review_policy.sh`.
- **[Paper Human Review Replay and Regression Gate](docs/paper-human-review-replay.md)** — v0.6.15 CAND-004 deterministic, offline, non-executable replay and regression gate over the CAND-001 review pack, CAND-002 review ledger, and CAND-003 review policy. Produces a replay artifact; no live trading, broker submission, provider execution, notifications, orders, or real human approval. See `scripts/demo_paper_human_review_replay.sh`.
- **[Paper Human Review Evidence Bundle](docs/releases/v0.6.15-paper-human-review-evidence.md)** — v0.6.15 CAND-005 deterministic, offline, non-executable candidate closure evidence bundle derived from the CAND-001 review pack, CAND-002 review ledger, CAND-003 review policy, and CAND-004 replay gate. Reuses the existing `atlas backtest portfolio-review-replay` command; produces closure artifacts `docs/releases/v0.6.15-paper-human-review-evidence.md` and `.json`. No live trading, broker submission, provider execution, notifications, orders, or real human approval. See `scripts/check_v0615_paper_human_review_evidence.py`.
- **[v0.6.15 Final Human Review Release-Readiness Audit](docs/releases/v0.6.15-final-readiness-audit.md)** — v0.6.15 CAND-006 planning-only Go/No-Go dossier that audits the CAND-001 through CAND-005 paper human review chain for a future separately owner-authorized GitHub-only release cutover. Produces `docs/releases/v0.6.15-final-readiness-audit.md` and `.json`; no tag, release, PyPI publish, live trading, broker submission, provider execution, notifications, orders, or real human approval. See `scripts/check_v0615_final_readiness_audit.py`.
- **[Product Demo and Marketplace Readiness Pack](docs/product-demo-pack.md)** — curated paper-only demos, safe copy templates, marketplace listing, autonomy roadmap, and reviewer-facing assets for public showcase and marketplace listings, all offline-safe and free of live-trading or profit claims.
- **[Product Demo Walkthrough Script](scripts/demo_product_walkthrough.sh)** — combined paper workflow, diagnostics, safety boundary, and artifact verification walkthrough for reviewers and marketplace evaluators.
- **[Product Demo Evidence Bundle](docs/product-demo-evidence.md)** — optional deterministic, reviewer-facing evidence package produced by the walkthrough script with `--output-dir`.
- **[Reviewer Trust Snapshot](docs/trust/reviewer-trust-snapshot.md)** — compact one-page release-identity and safety-posture summary for external reviewers, founders, and marketplace operators.
- **[Provider Preflight Dry-Run](docs/demo/provider-preflight-demo.md)** — local provider preflight smoke chain and manual pipeline.
- **[Provider Safety Dossier](docs/provider-safety-dossier.md)** — offline mock workflow for the provider response pipeline.
- **[Risk Rejection](docs/demo-risk-rejection.md)** — see how deterministic risk gates block unsafe orders.
- **[Audit Verification](docs/demo-audit.md)** — verify the tamper-evident hash-chain and run manifests.

No `assets/atlas-demo.gif` recording is checked in yet; the walkthroughs above are the canonical demo surface.

## Provider Safety Dossier

The provider safety dossier is a sandbox-only, paper-only workflow for inspecting and mocking the provider response pipeline. It keeps provider execution locked, loads no credentials, follows no broker/order path, and has no network enabled. See [docs/provider-safety-dossier.md](docs/provider-safety-dossier.md) for the offline mock workflow.

## Telegram & Notifications

Atlas supports optional notification channels. For Telegram control and alerts, see [docs/telegram-control.md](docs/telegram-control.md).

## Contributing and Security

We welcome contributions that respect the safe-by-default design. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, safety boundaries, and contribution rules. See the [Atlas Agent Trust Center](docs/trust/README.md) for security posture and release assurance. To report security or safety issues privately, use [GitHub Security Advisories](https://github.com/usernotfinded/atlas-agent/security/advisories). See [SECURITY.md](SECURITY.md) for the full security policy.

New to the repo? Start with the [External Reviewer Walkthrough](docs/external-reviewer-walkthrough.md), the [Reviewer Golden-Path Validation Guide](docs/reviewer-golden-path.md), and the [Product Demo and Marketplace Readiness Pack](docs/product-demo-pack.md). See also: [Reviewer Checklist](docs/reviewer-checklist.md) · [Public FAQ](docs/public-faq.md) · [Public Launch Readiness](docs/public-launch-readiness.md) · [Public Launch Messaging](docs/public-launch-messaging.md) · [Feedback Request Guide](docs/feedback-request-guide.md) · [Product Capability Inventory](docs/product-capability-inventory.md) · [Marketplace Listing](docs/marketplace-listing.md) · [Autonomy Roadmap](docs/autonomy-roadmap.md).

## Release Assurance

Maintainers can generate a local release assurance pack:

```bash
python scripts/release_assurance.py --version v0.6.16 --output artifacts/release_assurance/v0.6.16-local-check
```

Or run `.github/workflows/release-assurance.yml` via `workflow_dispatch` in GitHub Actions. Both are read-only and non-publishing — they do not create tags, publish packages, call providers, or enable trading.

## Release Process & Deployment

Release readiness is governed by the [Final RC Audit](docs/final-rc-audit.md), [Final Release Candidate Checklist](docs/final-release-candidate-checklist.md), [Stable Release Checklist](docs/stable-release-checklist.md), and [Stable Release Decision](docs/stable-release-decision.md) documents. For deployment options, see [docs/deployment.md](docs/deployment.md).

## Disclaimer

**NOT FINANCIAL ADVICE.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss. Live trading can lose real money. You are solely responsible for your deployment, risk limits, and any financial results. Use Paper Mode until you are fully confident in your strategy and configuration.

---

Built by Natan Mucelli.
