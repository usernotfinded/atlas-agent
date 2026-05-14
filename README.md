![Atlas Agent Banner](./assets/atlasagentbanner.png)

# Atlas Agent

<p align="center">
  <a href="https://github.com/usernotfinded/atlas-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="#broker-neutral-model"><img src="https://img.shields.io/badge/Positioning-Broker%20Neutral-blue?style=for-the-badge" alt="Broker Neutral"></a>
  <a href="docs/model-providers.md"><img src="https://img.shields.io/badge/Providers-11%2B-orange?style=for-the-badge" alt="11+ Providers"></a>
  <a href="https://github.com/usernotfinded"><img src="https://img.shields.io/badge/Built%20by-Natan%20Mucelli-blueviolet?style=for-the-badge" alt="Built by Natan Mucelli"></a>
</p>

**Atlas Agent turns your preferred LLM and broker/API provider into a supervised trading workspace, with market research, paper workflows, trading memory, audit logs, approval queues, and deterministic risk gates.**

> **DISCLAIMER:** Not financial advice. Live trading is disabled by default. Atlas is broker-neutral: users choose their own model, broker/API provider, credentials, and risk limits. Trading involves significant risk of loss.

Atlas is the broker-neutral control layer above user-selected models, broker/API providers, credentials, and risk limits. It treats the LLM as the reasoning engine and provides it with a toolset of **broker adapters** to perform web research, manage portfolios, and evaluate trade ideas through a rigorous deterministic **risk gates** layer.

## Demo

Run the reproducible paper-mode workflow:

```bash
./scripts/demo_paper_workflow.sh
```

The demo creates a temporary Atlas workspace, installs a safe discipline profile, sets the explicit `ATLAS-DEMO` paper symbol, runs `atlas validate`, shows a paper-mode dry run, runs a deterministic sample-data backtest with the `DEMO-SYMBOL` fixture, and verifies audit manifests when present.

It does not require live trading, real broker credentials, or private values. It is a paper-mode proof of workflow mechanics, not a live-trading setup or performance claim. No `assets/atlas-demo.gif` recording is checked in yet; the script is the reproducible demo artifact.

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
| **Live Trading** | Disabled | Strictly opt-in; `can_submit=false` enforced. `resolve_execution_broker("live")` returns `None`. No live execution broker exposed. |
| **Broker Integrations** | Beta | Early-stage adapters for third-party broker APIs. |
| **Self-Improvement** | Early-Stage | Skill refinement and Markdown-based memory persistence. |
| **Dashboard** | Basic | Read-only local HTML snapshot for system visibility. |

## Current Status (v0.5.6.dev6)

Atlas is currently in active development. The current status of major features is reflected in the System Status matrix above. **Live trading | disabled by default**.

### What's New in v0.5.6.dev6
- **Post-submit state mutation helpers (Batch 4.8)**: `mark_acknowledged()`, `mark_submit_failed()`, `mark_submit_uncertain()`, and `mark_submit_prepare_failed()` in `submit_state.py` provide atomic, validated state transitions for the boundary immediately after broker submission.
- **`mark_acknowledged()`**: Transitions from `submit_requested` to `acknowledged` after broker confirmation. Sets `submitted_at`, `broker_order_id`, and `broker_status`. Updates the last `submit_attempt` entry in-place with `status="acknowledged"`.
- **`mark_submit_failed()`**: Transitions from `submit_requested` to `failed` after explicit broker rejection (4xx or rejected status). Keeps `submitted_at=null`. Sets `error_code` on the last submit attempt.
- **`mark_submit_uncertain()`**: Transitions from `submit_requested` to `submit_uncertain` for post-broker uncertainty (timeout, 5xx, transport, malformed response, CID mismatch after request may have been sent). Keeps `submitted_at=null`.
- **`mark_submit_prepare_failed()`**: Transitions from `submit_requested` to `submit_prepare_failed` for pre-broker local failure (resolver returns None, execution broker invalid). Keeps `submitted_at=null`. Restricted error codes: `execution_broker_unavailable`, `execution_broker_invalid`.
- **`submitted_at` semantics**: Set **only** after broker ACK (`acknowledged`). Remains `null` for `failed`, `submit_uncertain`, and `submit_prepare_failed`.
- **Static transition reasons**: Status transitions use static safe strings (`"broker_acknowledged"`, `"broker_rejected"`, `"broker_uncertain"`, `"execution_broker_failed"`). No raw `broker_order_id` or broker error text is interpolated into transition reasons.
- **Broker status allowlist**: `broker_status` is validated against a safe allowlist. Unknown values are rejected.
- **Broker order ID validation**: `broker_order_id` is validated as a safe non-empty string. Secret-shaped values (containing `API_KEY`, `SECRET`, `TOKEN`, `PASSWORD`) are rejected.
- **Error code allowlist expansion**: Added `execution_broker_unavailable` and `execution_broker_invalid` to the submit attempt error code allowlist.
- **Submit attempt status expansion**: Added `submit_prepare_failed` to the submit attempt status allowlist.
- **Helpers remain unwired from runtime**: `run_submit_execution()` does not import or call any new helper. No `broker.place_order` path was added. No `resolve_execution_broker("live")` call was added.
- **No live submit enabled**: `can_submit=false` for all live brokers. `resolve_execution_broker("live")` returns `None`. No live order execution path exists.

### What's New in v0.5.6.dev5
- **Pre-submit mutation wiring behind hard-disabled gate (Batch 4.7)**: `run_submit_execution()` now calls `mark_submit_requested()` **only after** `can_submit=true`, then immediately blocks with `broker_submit_not_implemented` before any broker submission.
- **Mocked `can_submit=true` path prepares `submit_requested` state**: When all safety gates pass under a mocked/test `can_submit=true` resolver, the pending file is atomically mutated to `status="submit_requested"` with `client_order_id`, `submit_requested_at`, a status transition, and a `submit_attempts` entry. `submitted_at` and `broker_order_id` remain `null`.
- **Production `can_submit=false` path still performs zero mutation**: Alpaca live broker continues to return `can_submit=false`, so production behavior is identical to Batch 4.6 — all gates run, then block with `can_submit_false` and no file mutation.
- **`broker_submit_not_implemented` hard block**: After `mark_submit_requested()` succeeds, `run_submit_execution()` returns `blocked_reason="broker_submit_not_implemented"` with the message *"Submit state prepared, but broker submission is not implemented in this release."*
- **No `broker.place_order` call**: Even in the mocked `can_submit=true` path, `place_order` is never called. `resolve_execution_broker("live")` is never called. `OrderRouter.route` is never called.
- **`submit_requested` rerun protection**: If a pending file is already in `submit_requested` state, `run_submit_execution()` blocks at the idempotency gate with `reconciliation_required` before sync/risk/mutation. No duplicate `submit_attempts` are appended.
- **Reconcile supports `submit_requested`**: `run_reconcile()` now accepts `submit_requested` as a valid reconcile status. Broker found → `duplicate_reconciled`; broker not found → `reconciliation_required`.
- **Dry-run blocks `submit_requested`**: `run_submit_dry_run()` treats `submit_requested` like `submit_uncertain` and `reconciliation_required`, blocking with no file mutation.
- **No live submit enabled**: `can_submit=false` for all live brokers. `resolve_execution_broker("live")` returns `None`. No live order execution path exists.

### What's New in v0.5.6.dev4
- **Submit state mutation boundary helpers (Batch 4.6)**: `build_submit_requested_payload()`, `mark_submit_requested()`, and `append_submit_attempt()` in `submit_state.py` provide tested, atomic, recoverable state-transition primitives for the boundary immediately before broker submission.
- **`submit_requested` payload construction**: Pure helper constructs the exact mutation that would occur before `broker.place_order` — setting `status="submit_requested"`, `client_order_id`, `submit_requested_at`, a status transition, and a `submit_attempts` entry.
- **UUID4 submit attempt IDs**: `attempt_id` is validated as a canonical UUID4 string. Non-UUID values (including secret-shaped strings) are rejected.
- **Actor and error_code allowlists**: `actor` is restricted to `{"submit:cli", "system"}`. `error_code` is restricted to an explicit safe enum (`broker_rejected_order`, `broker_unavailable`, `broker_transport_failed`, `malformed_broker_response`, `client_order_id_mismatch`, `order_not_found`, `unknown`).
- **Deterministic `client_order_id` validation**: Existing `client_order_id` in a pending file is validated against `compute_client_order_id(order_id, order_hash)`. Mismatched or invalid values are rejected; no silent overwrite occurs.
- **Helpers remain unwired from runtime submit execution**: `run_submit_execution()` continues to block at `can_submit=false` with zero file mutation. No CLI flag exposes the helpers.
- **No live submit enabled**: `can_submit=false` for all live brokers. `resolve_execution_broker("live")` returns `None`. No live order execution path exists.

### What's New in v0.5.6.dev3
- **`submit-approved-order` no-flag execution skeleton**: Runs all live submit safety gates — pending order validation, idempotency checks, live-trading gate, kill-switch gate, fresh read-only broker sync, and risk revalidation — before failing closed at `can_submit=false`.
- **Fresh live sync + risk revalidation**: Every no-flag submit performs a fresh `BrokerSyncService.sync()` and `RiskManager.evaluate_order(..., mode="live")` against the synced portfolio snapshot before the final `can_submit` gate.
- **Market orders blocked safely**: Market orders are rejected with `market_price_unavailable` until a safe quote source is integrated.
- **No pending file mutation / no `client_order_id` persistence**: The execution skeleton is strictly read-only with respect to pending order files. Missing `client_order_id` is computed deterministically but never persisted.
- **Live submit remains fully disabled**: `can_submit=false` for all live brokers. `resolve_execution_broker("live")` returns `None`. No live order execution path exists.

### What's New in v0.5.6.dev2
- **`submit-approved-order --dry-run`**: Validate all live submit gates without executing — includes deterministic `client_order_id` preview and idempotency checks.
- **`submit-approved-order --reconcile`**: Read-only broker reconciliation for approved orders. Queries the broker via `GET` only (`AlpacaBrokerAdapter.get_order_by_client_order_id`) to detect duplicate submits. Never calls `place_order`.
- **Idempotency state machine**: Pending orders track `submit_uncertain` and `reconciliation_required` states to prevent accidental duplicate submissions.
- **Live submit remains fully disabled**: `can_submit=false` for all live brokers. `resolve_execution_broker("live")` returns `None`. No live order execution path exists.

## Quickstart

```bash
# Install in editable mode
pip install -e .

# Create a workspace
atlas init <workspace> --template routine-trader
cd <workspace>

# Guided first-run setup
atlas setup

# Check your configuration
atlas validate

# Run your first paper-trading cycle
atlas run --mode paper
```

1. **`atlas setup`**: Guided setup walks through provider/model/auth, discipline profile, symbol selection, and a final readiness summary.
2. **`atlas run`**: Execution is explicit. Use `--mode paper` for safety and simulation. Live trading is designed to prevent orders without explicit configuration and multi-stage gates.

## Demos

Reproducible walkthroughs that show Atlas working as a broker-neutral supervised workspace:

- **[Paper Workflow Script](scripts/demo_paper_workflow.sh)** — create a temporary workspace, validate config, run a paper dry-run, execute a deterministic sample-data backtest, and verify audit artifacts.
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

## Backtesting

Atlas Agent includes a deterministic, local-first backtesting engine to evaluate strategy behavior against historical benchmarks.

```bash
# Run a buy-and-hold backtest
atlas backtest run --symbol AAPL --data path/to/data.csv
```

**Note:** Backtesting is a research tool. Historical results do not guarantee future performance. Atlas does not predict profit; it measures strategy behavior against historical data.

## Telegram Control Plane

Atlas Agent provides an optional Telegram interface for remote status updates and guarded action approval. This is a control-only layer; execution remains governed by the local risk manager.

## Deployment and Cloud

Atlas is designed for local-first operation but can be deployed to a VPS, Docker container, or serverless job. Always ensure your environment variables are secured in your deployment target.

## Commands

| Command | Purpose |
| :--- | :--- |
| `atlas backtest run` | Run a deterministic backtest on historical CSV data. |
| `atlas broker sync` | Synchronize account, positions, and orders from the broker. |
| `atlas audit verify` | Verify the JSONL audit log hash-chain. |

## Disclaimer

**NOT FINANCIAL ADVICE.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss. Live trading can lose real money. You are solely responsible for your deployment, risk limits, and any financial results. Use Paper Mode until you are fully confident in your strategy and configuration.

---
Built by Natan Mucelli.
