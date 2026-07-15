![Atlas Agent Banner](./assets/atlasagentbanner.png)

# Atlas Agent

<p align="center">
  <a href="https://github.com/usernotfinded/atlas-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/usernotfinded/atlas-agent/actions/workflows/ci.yml"><img src="https://github.com/usernotfinded/atlas-agent/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="#broker-neutral-provider-neutral"><img src="https://img.shields.io/badge/Positioning-Broker%20Neutral-blue?style=for-the-badge" alt="Broker Neutral"></a>
  <a href="docs/model-providers.md"><img src="https://img.shields.io/badge/Providers-Catalog-orange?style=for-the-badge" alt="Provider catalog"></a>
</p>

**Atlas Agent is a broker-neutral supervised trading workspace for deterministic
backtests, local paper workflows, provider-assisted analysis, trading memory,
approval queues, risk gates, and audit evidence.**

> **Current Status (v0.6.26)** — package/source version is `0.6.26`. `v0.6.26` is the current public GitHub release. `v0.6.25` is the historical previous public release. `v0.6.27` is the next planning line. Historical stable baseline is `v0.5.8`. PyPI was not published. See [CHANGELOG.md](CHANGELOG.md) for full release history.

> **Safety posture:** Not financial advice. Live trading is disabled by default,
> provider and broker capabilities are opt-in, and trading can result in substantial
> loss. Safety validation does not imply profitability or trading correctness.

## Quickstart

The canonical first run is paper-first, sandbox-only, offline-safe, and safe by default.
It requires Python 3.11 or newer and Bash; it requires no broker
credentials or provider API keys.

```bash
python3.11 -m pip install -e .
./scripts/demo_paper_workflow.sh
```

The script creates an isolated temporary workspace, applies
`atlas config set market.symbol ATLAS-DEMO`, initializes the required discipline
profile, validates local state, runs redacted diagnostics, previews a paper run,
executes the bundled `DEMO-SYMBOL` backtest, and verifies audit artifacts. It
leaves the temporary workspace available for inspection.

For this quickstart: no credentials loaded by the script; no broker/order path;
no provider call. The script inherits the caller's environment rather than
scrubbing it, so use a credential-clean shell when isolation matters.
Live trading disabled by default. The sample data and results demonstrate the
workflow, not future performance.

Useful read-only or local follow-up commands:

```bash
atlas --help
atlas validate
atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL
atlas backtest runs --validate --json
```

Use the [Paper-Trading Guide](docs/paper-trading-guide.md) for manual setup, the
[Reviewer Golden-Path Validation Guide](docs/reviewer-golden-path.md) for the
canonical verification sequence, and the [Demo Artifact Index](docs/demo-artifact-index.md)
for the evidence produced by the demo. Expected output is documented in
[Demo: Paper Workflow](docs/demo-paper-workflow.md); configuration-only diagnostics
are documented in [Broker and Provider Preflight Diagnostics](docs/preflight-diagnostics.md).

## Why Atlas?

Atlas combines provider-assisted reasoning with paper workflows, approval queues,
and deterministic risk gates while keeping model output separate from broker
authority.

### What this is

- A local-first research, backtesting, and paper-trading workbench.
- A control layer that keeps model reasoning separate from deterministic policy,
  broker adapters, approval, and risk gates.
- A provider-neutral framework with an offline `NullProvider`, executable
  OpenAI-compatible adapters, and additional catalog/scaffold integrations.
- A broker-neutral framework with a deterministic local paper broker and guarded
  adapter boundaries.
- A source of tamper-evident hash-chain and manifest evidence for the paths that
  use the hardened audit writer, plus separate operational event logs.
- An early-stage autonomous paper workflow for deterministic local simulation,
  not authority for unattended real-money execution.

The repository also contains a session-aware market-open/closed-market cycle,
but the canonical agent command currently selects the generic `AgentLoop`. Do not
assume automatic market-open execution or closed-market learning dispatch from
that command; both remain simulation/paper-first unless a separate path is
explicitly configured and authorized.

### What this is not

- **Not a live trading system by default.** Live submit requires multiple
  explicit gates and is not activated by analysis or broker sync. The current
  opt-in and approval integrity gaps mean this path is not security-hardened or
  production-ready.
- Not a broker, custodian, financial advisor, or broker recommendation service.
- Not proof that a strategy is correct or suitable for a user or market.
- Not a collection of operational model tools: the built-in agent tools currently
  use deterministic mock implementations for market, research, notification,
  shell, and order actions.

## System Status

| Capability | Current reality | Network / money boundary |
|---|---|---|
| Local workspace and CLI | Usable | Local configuration and artifacts. |
| Bundled backtesting | Usable | Canonical bundled strategies are deterministic, local-first, and make no network calls. Third-party strategy entry points run in-process and are not sandboxed. |
| Local paper workflow | Usable | Simulated orders only; no broker submission. |
| Autonomous paper workflow | Early-stage | Bounded local automation; no live authority. |
| Runtime AI providers | Beta | Offline fallback is available; explicitly configured executable adapters may make provider calls. |
| Research provider pipeline | Sandbox-only | Deterministic local provider only. External and LLM research providers are not enabled in this development tag; provider execution remains locked in this workflow. |
| Built-in agent tools | Contract/mock layer | Deterministic mocks, not live market or broker integrations. |
| Broker adapters | Beta / partial | Local paper is available. Alpaca contains guarded sync and opt-in submit code; other adapters are partial, disabled, or placeholders. |
| Live analysis and sync | Guarded | Read and analysis capabilities do not authorize submission. |
| Live submit | Disabled by default / pre-production | Guarded code is intended to keep `can_submit=false` until explicit gates pass, but known opt-in and approval-integrity gaps prevent a production-readiness claim. |
| Audit and manifests | Implemented, path-dependent | Hardened paths are tamper-evident, but live-submit blocked/attempted event emission is currently optional and best-effort; not every event sink is the hash-chain. |
| Dashboard | Basic | Strictly read-only and zero-secret by contract. |

`v0.6.26` is the current public GitHub release and source version.
`v0.6.27` is the next planning line. Provider-safety trust remains blocked: those
workflows are sandbox-only and do not authorize provider execution.
Live submit remains disabled by default; live trading disabled by default. There
are no profitability or trading-correctness claims.

## How the Safety Boundary Works

The model is a proposal source, never execution authority. Runtime live analysis
ends without creating execution state:

```text
provider output -> typed analysis/proposal -> live_analysis_only -> stop
```

The separately invoked live-submit path starts from an explicitly created order
intent; there is no automatic edge between these flows:

```text
order intent -> validation -> RiskManager -> pending order -> human approval
             -> live-submit gates -> durable submit-requested state
             -> broker adapter -> outcome state
```

- **Live-submit ingress validation** rejects malformed pending-order fields,
  unsupported enums, missing prices, and non-finite numeric values on the
  hardened submit path. Equivalent validation is not yet universal across every
  broker, risk, backtest, and legacy internal API.
- **RiskManager** applies deterministic limits outside model reasoning. Every
  configured limit still requires an enforcement test; configuration alone is
  not proof that a control is active.
- **Approval and submit state** keep proposal, human decision, submit attempt,
  and reconciliation distinct. A failed broker call can have an uncertain outcome
  and must not be retried blindly.
- **Kill switch and heartbeat/dead-man controls** participate in guarded runtime
  paths. They are designed to fail closed where enforced, but cannot eliminate
  operational or market risk.
- **Live-submit contract** documents the resolver, quote, sync, risk, state,
  audit, and final kill-switch gates. See
  [Live-Submit Safety Contract](docs/live-submit-safety-contract.md).
- **Audit evidence** uses stable identifiers, redaction, hash chains, and run
  manifests on hardened paths. Audit files and trading artifacts may still contain
  sensitive financial context and should not be shared casually. Current
  live-submit blocked/attempted event recording can be absent or fail without
  stopping the path, so submit state must not be described as complete audit
  evidence.

Broker order submission is blocked by `can_submit=false` by default. Running an
agent in a requested live-analysis mode does not submit orders; the separately
gated `submit-approved-order` workflow is the intended live-write boundary.

Provider execution follows an **artifact-based safety policy** in sandbox research
workflows, with policy decisions enforced at that workflow's execution boundary.
Order proposals are separately evaluated by the risk manager (`RiskManager`) on
paths that invoke it. There is no runtime network block on the host: an explicitly
configured executable provider adapter may make a network call.

### Connected trading agents

[AGENTS.md](AGENTS.md) is the operating contract for a trading agent connected to
Atlas. It defines the agent's preflight, evidence standard, no-trade conditions,
proposal payload, mode-specific authority, failure handling, and reporting format.
It is not a contributor or code-maintenance guide.

The current `atlas run` prompt does **not** automatically load the repository-root
`AGENTS.md`. Today it loads the fixed analyst boundary plus the workspace's
validated `.atlas/discipline.md`. An agent integration must explicitly supply
`AGENTS.md` as high-priority runtime instructions—or synchronize the policy into
the validated discipline/prompt path—before claiming that the connected model is
governed by it. Code-enforced risk, approval, kill-switch, and live-submit gates
remain authoritative either way.

Loading the policy alone is not sufficient. A connected integration must also
provide the model with verified mode, time, market status, active limits,
kill-switch state, portfolio and open-order state, and timestamped market data.
The bundled tools are currently mocks, and the stock runner does not expose every
required preflight fact to the model. Under this contract, that unextended runtime
must fail closed with `HOLD` rather than inventing the missing state.

## Broker-Neutral, Provider-Neutral

Atlas does not custody funds, bundle accounts, recommend a broker, or select a
model for the user. It is the control layer above user-selected providers,
credentials, broker adapters, and risk limits.

The provider catalog documents OpenRouter, OpenAI, Anthropic, Google Gemini,
DeepSeek, xAI / Grok, Z.ai/GLM, Kimi/Moonshot, Hugging Face, NVIDIA NIM, LM Studio,
local/Ollama/llama.cpp endpoints, and custom or OpenAI-compatible endpoints. A
catalog entry means Atlas recognizes or documents the provider; it does not mean
every entry has an executable adapter in this release. The currently executable
runtime surface is narrower, and Anthropic HTTP execution plus native Google
execution remain unconfigured in the minimal install. See
[Model Providers](docs/model-providers.md) for the capability details.

Web research remains provider-neutral at the architecture level; no single
external research service is the required or default choice.

For independent model comparisons, see the
[Vals AI Finance Agent Benchmark](https://www.vals.ai/benchmarks/fabv2). Atlas does
not endorse its rankings or any model.

Broker capability is also explicit and conservative:

- `paper` is the default deterministic local simulator.
- Alpaca contains beta read/sync and explicitly gated submit paths. Its remote
  paper endpoint still uses a network and is different from Atlas local paper mode;
  endpoint/environment reporting is still being hardened.
- Binance is partial, generic CCXT is disabled, and IBKR is a placeholder.
- Unknown brokers fail closed. See [Broker Support](docs/brokers.md).

## Core Workflows

### Backtesting

Backtests run against local OHLCV input and should produce identical results for
identical data, strategy, configuration, and seed.

```bash
atlas backtest run --symbol AAPL --data path/to/data.csv
atlas backtest compare --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL --output-dir artifacts/local/compare
atlas backtest robustness --fixtures data/sample/regimes/ohlcv_uptrend.csv,data/sample/regimes/ohlcv_downtrend.csv,data/sample/regimes/ohlcv_flat.csv,data/sample/regimes/ohlcv_volatile.csv --symbol DEMO-SYMBOL --output-dir artifacts/local/robustness
```

Historical results do not guarantee future performance. Evaluation references:
[strategy evaluation](docs/paper-strategy-evaluation.md),
[sensitivity](docs/paper-strategy-sensitivity.md),
[robustness](docs/paper-strategy-robustness.md),
[walk-forward stability](docs/paper-strategy-walk-forward.md),
[scorecard](docs/paper-strategy-scorecard.md), and
[portfolio stress](docs/paper-portfolio-stress.md).

### Paper research

The research artifact workflow is paper-only and analysis-only. Its provider is
deterministic and local; external and LLM providers are not enabled. It creates
versioned artifacts rather than orders. See
[Research Workflow](docs/research-workflow.md).

The command family includes `atlas research run`, `atlas research list`,
`atlas research show`, `atlas research plan`, `atlas research verify`,
`atlas research summary`, `atlas research evaluate`, `atlas research prompt`,
`atlas research simulate-provider`, `atlas research review-response`, and
`atlas research dossier`.

### CLI discovery

```bash
atlas --help
atlas backtest --help
```

| Family | Representative commands | Purpose |
|---|---|---|
| Workspace | `atlas init`, `atlas setup`, `atlas validate`, `atlas config set ...` | Create and validate a paper-first workspace. |
| Agent/paper | `atlas run --mode paper`, `atlas agent run --mode paper`, `atlas run-once --mode paper` | Analyze or simulate without the live-submit boundary. |
| Backtest | `atlas backtest run`, `compare`, `robustness`, `portfolio-stress`, `portfolio-monitor`, `portfolio-review-pack`, `portfolio-review-policy`, `portfolio-review-replay`, `list-strategies` | Deterministic local evaluation and paper review artifacts. |
| Research | `atlas research ...` | Paper-only artifact generation and inspection. |
| Risk and safety | `atlas risk status`, `atlas kill-switch status` | Inspect deterministic safety state. |
| Approval | `atlas approve-order <order_id>` | Mutating, explicit authorization action; it can enable a later separately gated submission. |
| Broker read path | `atlas broker sync` | Synchronize normalized account, position, and order data where supported. |
| Diagnostics | `atlas doctor`, `atlas memory doctor --json`, `atlas events doctor`, `atlas audit verify --all` | Read-only preflight, memory checks, and audit verification. |
| Deployment | `atlas deploy systemd`, `atlas deploy docker`, `atlas deploy vps` | Generate deployment helpers; does not authorize live submit. |

See the [CLI Compatibility Inventory](docs/cli-command-compatibility.md) for the
parser-level command contract.

## Configuration and Data Security

- `.atlas/config.toml` is for non-secret settings by design. Review it before
  sharing; do not place credentials or private financial data in it.
- `.env.atlas` is the gitignored credential store. Do not commit, print, or copy
  its values into issues, prompts, memory, logs, or examples.
- Provider-enabled prompts may include workspace memory. Review memory with
  `atlas memory doctor --json` before an external provider call.
- Audit, event, report, memory, pending-order, and portfolio artifacts are local
  operational data. Secret-shaped values are redacted on supported paths, but
  redaction is not a general privacy guarantee.
- The dashboard is read-only and must never expose credentials or write controls.

## Demos and Documentation

Start with these maintained walkthroughs:

- [Paper Workflow Script](scripts/demo_paper_workflow.sh) — canonical offline-safe first run.
- [Research Workflow Script](scripts/demo_research_workflow.sh) — paper-only research artifact chain.
- [Autonomous Paper Workflow](docs/autonomous-paper-workflow.md) and `scripts/demo_autonomous_paper_workflow.sh` — bounded local automation.
- [Paper Mode Provider Isolation](docs/paper-provider-isolation.md) — verifies the no-credential offline path.
- [Product Demo and Marketplace Readiness Pack](docs/product-demo-pack.md) and [Product Demo Walkthrough](scripts/demo_product_walkthrough.sh) — reviewer-facing paper workflows.

Safety and review references:

- [Provider Preflight Dry-Run](docs/demo/provider-preflight-demo.md)
- [Provider Safety Dossier](docs/provider-safety-dossier.md)
- [Risk Rejection](docs/demo-risk-rejection.md)
- [Audit Verification](docs/demo-audit.md)
- [Reviewer Trust Snapshot](docs/trust/reviewer-trust-snapshot.md)
- [External Reviewer Walkthrough](docs/external-reviewer-walkthrough.md)
- [Reviewer Checklist](docs/reviewer-checklist.md)
- [Public Launch Readiness](docs/public-launch-readiness.md)

The longer paper-evidence chain remains available through
[portfolio monitoring](docs/paper-portfolio-monitoring.md),
[human review pack](docs/paper-human-review-pack.md),
[human review ledger](docs/paper-human-review-ledger.md),
[human review policy](docs/paper-human-review-policy.md), and
[human review replay](docs/paper-human-review-replay.md). Historical bundles are
preserved in the [v0.6.13 paper autonomy evidence](docs/releases/v0.6.13-paper-autonomy-evidence.md),
[v0.6.14 portfolio evidence](docs/releases/v0.6.14-paper-portfolio-evidence.md),
[v0.6.14 readiness audit](docs/releases/v0.6.14-final-readiness-audit.md),
[v0.6.15 human review evidence](docs/releases/v0.6.15-paper-human-review-evidence.md),
and [v0.6.15 readiness audit](docs/releases/v0.6.15-final-readiness-audit.md).

No `assets/atlas-demo.gif` recording is checked in yet; the scripts and artifact
index are the canonical demo surface.

## Provider Safety Dossier

The provider safety dossier is a sandbox-only, paper-only workflow for inspecting
mock provider-response artifacts. It keeps research provider execution locked,
loads no credentials, and follows no broker/order path. It has no network enabled.
See [Provider Safety Dossier](docs/provider-safety-dossier.md).

## Telegram and Notifications

Notification channels are optional and disabled until configured. See
[Telegram Control](docs/telegram-control.md). Notifications do not bypass local
risk, approval, or live-submit gates.

## Development

Install the development dependencies, then choose the gate that matches the task.

```bash
python3.11 -m pip install -e '.[dev]'
./scripts/smoke_check.sh
./scripts/local_quick_check.sh
./scripts/release_check.sh --quick
./scripts/release_check.sh --research
./scripts/release_check.sh --full
```

`smoke_check.sh` is the narrow smoke loop, `local_quick_check.sh` is the balanced
pre-commit gate, and `release_check.sh --quick` delegates to the complete local
development gate. The full gate is required before a push or tag.

See [CONTRIBUTING.md](CONTRIBUTING.md) before changing runtime agents, providers,
tools, risk, execution, broker, safety, audit, or backtest code. `AGENTS.md`
governs the connected trading agent, not repository development. Security and
safety concerns should be reported privately through
[GitHub Security Advisories](https://github.com/usernotfinded/atlas-agent/security/advisories);
see [SECURITY.md](SECURITY.md).

For orientation and project posture, see the [Trust Center](docs/trust/README.md),
[Public FAQ](docs/public-faq.md), [Public Launch Messaging](docs/public-launch-messaging.md),
[Feedback Request Guide](docs/feedback-request-guide.md),
[Product Capability Inventory](docs/product-capability-inventory.md),
[Marketplace Listing](docs/marketplace-listing.md), and
[Autonomy Roadmap](docs/autonomy-roadmap.md).

## Release Assurance

Maintainers can create a local, non-publishing assurance pack:

```bash
python scripts/release_assurance.py --version v0.6.26 --output artifacts/release_assurance/v0.6.26-local-check
```

The local command and the `release-assurance.yml` workflow do not create tags,
publish packages, call providers, or enable trading.

## Release Process and Deployment

Release readiness is governed by the [Final RC Audit](docs/final-rc-audit.md),
[Final Release Candidate Checklist](docs/final-release-candidate-checklist.md),
[Stable Release Checklist](docs/stable-release-checklist.md), and
[Stable Release Decision](docs/stable-release-decision.md). Deployment options are
documented in [Deployment](docs/deployment.md); deployment does not grant live
authorization.

## Disclaimer

**NOT FINANCIAL ADVICE.** Atlas Agent is software, not a financial advisor. Trading
can lose real money. You are responsible for provider and broker selection,
credentials, configuration, risk limits, supervision, and financial outcomes. Use
paper mode while evaluating the system and your strategy.

---

Built by Natan Mucelli.
