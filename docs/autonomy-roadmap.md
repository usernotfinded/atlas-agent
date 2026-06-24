# Atlas Agent Autonomy Roadmap

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

Atlas Agent is intentionally **supervised by default** and is supervised, not autonomous. Bounded autonomy is a long-term product/research direction, not
a current capability. Every execution path that exists today is bounded by
deterministic risk gates, approval queues, kill-switch controls, and an auditable
decision record. Autonomy in this roadmap refers only to incremental, opt-in
improvements in local workflow orchestration, memory management, and research
summarization — never to unsupervised real-money trading or direct
AI-to-broker execution in the current release.

**No promise of profitability.** Atlas does not predict profits, guarantee returns, or claim that any strategy, backtest result, research artifact, or configuration will produce positive real-money outcomes. Past simulated or historical results do not guarantee future performance. Risk controls can reduce certain categories of unintended action, but they cannot eliminate trading risk, market risk, slippage, or the risk of loss. Use Paper Mode until you are fully confident in your own strategy, configuration, and risk limits.

**Roadmap timeline disclaimer:** All dates, versions, milestones, and sequencing in this document are planning estimates and subject to change without notice. They do not constitute commitments, guarantees, or release promises. Features may be reordered, deferred, or removed based on safety review, contributor bandwidth, and community feedback.

## Scope

In scope:
- Progressive automation of **paper/sandbox workflows** (research summarization, backtest orchestration, report generation, learning-loop suggestions).
- Clear status lifecycles where every actionable artifact requires **operator review or approval** before it can affect state.
- Improved **preflight and diagnostic automation** that remains read-only and broker-neutral.
- Tooling that helps operators prepare, review, and decide, without removing human judgment.

Out of scope:
- Unsupervised real-money execution without per-order human approval.
- Direct AI-to-broker order submission.
- Auto-approval of live orders, kill-switch overrides, or risk-limit changes.
- Any claim of production readiness, guaranteed performance, or safe live operation.

This roadmap applies to the current release planning line. All milestones remain
subordinate to the [Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md),
the live-submit safety contract, the `RiskManager`, approval gates, and the kill
switch.

## Autonomy levels

| Level | Name | What the agent may do | Default / gating |
|---|---|---|---|
| L0 | Research / paper assistant | Generate local research artifacts, run backtests, print dry-runs, generate reports. No orders. | Default-safe baseline. |
| L1 | Autonomous paper workflows | Run scheduled paper routines autonomously within deterministic limits. No broker contact. | Paper mode is the default runtime. |
| L2 | Live suggestions with human approval | Consume live broker snapshots for analysis and propose orders; every proposal requires explicit human approval. | Requires live config, credentials, and kill-switch normal state. |
| L3 | Bounded live-autonomy research concept | Not implemented; would require every live order to pass per-order human approval, strict RiskManager limits, and explicit opt-in. | Not enabled by default; not production-ready; not unattended-safe. |
| L4 | Broad autonomous live execution | Not a current capability or milestone. Any future consideration requires external legal, security, risk, operational, and regulatory review. | Not implemented; cannot be claimed without external review. |

### Cross-level invariants

- Deterministic risk gates and the kill switch apply at every level that touches orders or broker state.
- Approval queues are required for any live submit; the LLM/provider output is never treated as execution authority.
- Audit hash-chain records every gate decision, rejection, and state transition.
- The project does not support unsupervised real-money trading without human approval.

### Candidate status in the current planning line

- **CAND-005** is implemented as a local, fixture-first, read-only comparison of
  a stateful paper run against a recorded broker-like snapshot. It does not call
  broker APIs, load credentials, submit orders, or indicate live readiness.
- **CAND-006** remains future planning-only work for a gated live-submit
  conformance rehearsal. It is not implemented and does not enable real live
  trading.
- No candidate in the current planning line enables unsupervised real-money
  trading or direct AI-to-broker execution.

## Current state vs future state

Atlas Agent is designed as a **supervised, human-in-the-loop workspace**, not an unattended trading system. The autonomy roadmap moves from strict manual oversight toward limited, gated automation, while keeping live execution disabled by default and real-money autonomy off the table.

| Dimension | Current State | Future State Direction |
|---|---|---|
| **Default execution mode** | `paper` — local simulation only, no broker contact. | Paper remains the default; live remains opt-in only. |
| **Trust / approval model** | Manual review for live orders; proposals are advisory-only. | Gradual policy support for supervised paper automation; live submit stays approval-gated. |
| **Agent loop** | `atlas run --mode paper` can cycle autonomously against local data; live mode is analysis-only and does not submit orders. | Paper loop may run richer strategies locally; live loop remains analysis-only by default. |
| **Scheduler** | Paper routines may run autonomously; live routines must not bypass approval. | Scheduler stays paper-first; any live scheduling requires explicit opt-in and kill-switch checks. |
| **Research & learning loop** | Reflections, skill candidates, and learning suggestions are generated via static fallback and require human review/promotion. | Provider-assisted suggestions may improve quality, but skill activation and execution remain manual-only. |
| **Kill switch & risk gates** | Hard-coded deterministic gates and hierarchical kill switch are always active. | More granular safety policies and richer dead-man heartbeat configuration, with no relaxation of default-disabled live trading. |
| **Broker order submission** | Blocked by `can_submit=false`; Alpaca read-only sync is available only with explicit credentials and opt-in. | Additional broker adapters may mature, but every new adapter must implement the `Broker` interface and pass fail-closed guards. |

### What autonomy means today

- **Paper mode autonomy is allowed** — local simulation, backtests, research artifact generation, and dry-runs can run without human interaction because they touch no real money, no broker, and no provider (by default).
- **Paper strategy evaluation is allowed** — `atlas backtest compare` ranks bundled/sample-data strategy runs for paper-only follow-up and cannot promote a strategy to live trading.
- **Paper strategy robustness is allowed** — `atlas backtest robustness` evaluates deterministic synthetic regimes for paper-only follow-up and cannot promote a strategy to live trading.
- **Live mode is not autonomous** — even with live configuration, credentials, kill-switch normal state, and a valid opt-in record, every live submit still passes deterministic risk gates and approval checks before `place_order` is called.
- **Self-improvement is advisory-only** — reflections, skills, and learning suggestions produce local artifacts for review; they do not alter execution paths, activate skills, or submit orders automatically.

### What autonomy will never mean

The following remain **out of scope** unless the
[Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md) is
explicitly amended and all required external gates are satisfied:

- Autonomous real-money order submission without human approval.
- Removing or bypassing `RiskManager`, approval gates, kill switch, or audit hash-chain.
- Treating provider output as execution authority.
- Permitting live trading to continue when the operator is not actively monitoring the system.

## L0 — Research / Paper Assistant

L0 is the default and safest autonomy level. The human operator drives every step; Atlas acts as a supervised research and paper-trading assistant.

- **What the system does**
  - Generates local, deterministic, paper-only research artifacts (`atlas research run`, `plan`, `verify`, `evaluate`).
  - Produces structured thesis, risk notes, invalidation checks, and evaluation metrics from local data.
  - Supports a complete sandbox provider-preflight chain (`prompt`, `sandbox`, `simulate-provider`, `review-response`, `dossier`) without calling real providers or brokers.
  - Records all activity in local audit artifacts and tamper-evident manifests.

- **What the system never does at L0**
  - It does not call LLM or research providers over the network.
  - It does not read API keys or broker credentials.
  - It does not submit orders, create pending orders, or create approvals.
  - It does not authorize, enable, or perform live trading.

- **How to use it**
  ```bash
  atlas init demo-workspace --template routine-trader
  cd demo-workspace
  atlas discipline setup --manual --yes
  atlas config set market.symbol ATLAS-DEMO
  atlas research run --symbol ATLAS-DEMO
  atlas research plan <RUN_ID>
  atlas research verify <PLAN_ID>
  atlas research evaluate <PLAN_ID> --data data/sample/ohlcv.csv
  ```

- **Exit criteria to reach L1**
  - Operator can reliably produce, inspect, and validate paper-only research artifacts.
  - All workflows run locally with the deterministic provider and no network calls.
  - No live trading, broker submission, or autonomous execution is attempted or enabled.

## L1 — Autonomous Paper Workflows

Level 1 is **operator-supervised, local-only automation that runs entirely inside paper mode**. The agent can schedule or continuously run cycles, generate research and backtest artifacts, propose paper trades, and simulate those trades in the local `PaperBroker`. No live broker is contacted, no real orders are submitted, and provider execution remains locked by default.

### Scope
- `atlas agent run --mode paper` or scheduled routines run with `--mode paper`.
- Closed-market cycles are forced to paper mode.
- Deterministic `RiskManager` gates, kill switch, and tamper-evident audit logging are active on every cycle.

### Safety invariants at L1

| Invariant | L1 state |
|---|---|
| `trading_mode` | `paper` |
| `enable_live_trading` | `false` |
| `enable_live_submit` | `false` |
| Provider execution | Locked by default |
| Broker order submission | Blocked (`can_submit=false`) |
| `RiskManager` limits | Enforced on every proposal |
| Kill switch | Active; normal state required to run |
| Audit logging | Every cycle, rejection, and kill-switch event is recorded |
| Human approval for live orders | Required in any live path; live path is unreachable in L1 |

### What L1 is not

- **Not live trading.** Real-money order submission remains disabled and out of scope.
- **Not autonomous real-money execution.** All "autonomy" is confined to local simulation.
- **Not production-ready.** Paper results do not guarantee future performance, execution quality, liquidity, or live-trading safety; paper simulation still involves risk.
- **Not a provider unlock.** LLM/provider execution stays locked by default.

### Concrete demo

- [Autonomous Paper Workflow](autonomous-paper-workflow.md) — a deterministic, offline, no-credential L1 paper workflow demonstration. It is not a live-trading or production-readiness claim.
- [Paper Mode Provider Isolation](paper-provider-isolation.md) — paper-mode agentic workflows can run without an AI provider API key or network access; explicit `--offline` path and automatic missing-credential fallback are available. Live mode remains fail-closed.
- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Strategy Sensitivity Evaluation](paper-strategy-sensitivity.md) — deterministic sample-data strategy comparison with paper-only follow-up decisions.
- [Paper Strategy Robustness Report](paper-strategy-robustness.md) — deterministic synthetic multi-regime strategy robustness for paper-only follow-up.
- [Paper Portfolio Stress Constraints](paper-portfolio-stress.md) — deterministic synthetic stress checks for paper-only portfolio proposal follow-up.
- [v0.6.14 Paper Portfolio Evidence Bundle](releases/v0.6.14-paper-portfolio-evidence.md) — historical pre-cutover CAND-001 through CAND-007 paper portfolio evidence closure.
- [v0.6.14 Final Paper Portfolio Readiness Audit](releases/v0.6.14-final-readiness-audit.md) — historical pre-cutover CAND-008 Go/No-Go dossier preserved after the GitHub-only release.
- [Paper Human Review Pack](paper-human-review-pack.md) — v0.6.15 CAND-001 deterministic, offline, non-executable review dossier derived from paper portfolio evidence. No live trading, broker calls, provider calls, notifications, or orders.
- [Paper Human Review Ledger](paper-human-review-ledger.md) — v0.6.15 CAND-002 deterministic, offline, non-executable simulated human-review decision ledger derived from the CAND-001 review pack. No live approval, broker submission, provider calls, notifications, orders, or real human approval.
- [Paper Human Review Policy Simulator](paper-human-review-policy.md) — v0.6.15 CAND-003 deterministic, offline, non-executable policy simulation against the CAND-001 review pack and CAND-002 review ledger. Produces a blocked-live gate artifact; no live trading, broker submission, provider execution, notifications, orders, or real human approval.
- [Paper Human Review Replay and Regression Gate](paper-human-review-replay.md) — v0.6.15 CAND-004 deterministic, offline, non-executable replay and regression gate over the CAND-001 review pack, CAND-002 review ledger, and CAND-003 review policy. Verifies the paper chain remains intact and the live path stays blocked; no live trading, broker submission, provider execution, notifications, orders, or real human approval.
- [Paper Human Review Evidence Bundle and Candidate Closure Gate](releases/v0.6.15-paper-human-review-evidence.md) — v0.6.15 CAND-005 deterministic, offline, non-executable closure evidence bundle over the CAND-001 review pack, CAND-002 review ledger, CAND-003 review policy, and CAND-004 replay gate. Reuses the existing `atlas backtest portfolio-review-replay` command to produce `docs/releases/v0.6.15-paper-human-review-evidence.md` and `.json`; no live trading, broker submission, provider execution, notifications, orders, or real human approval.
- [v0.6.15 Final Human Review Release-Readiness Audit](releases/v0.6.15-final-readiness-audit.md) — v0.6.15 CAND-006 planning-only Go/No-Go dossier that audits the CAND-001 through CAND-005 paper human review chain for a future separately owner-authorized GitHub-only release cutover. Produces `docs/releases/v0.6.15-final-readiness-audit.md` and `.json`; no tag, release, PyPI publish, live trading, broker submission, provider execution, notifications, orders, or real human approval.
- [Autonomous Paper Decision Loop](autonomous-paper-loop.md) — v0.6.16 CAND-001/CAND-003 deterministic, offline, paper-only autonomous decision loop and stateful execution-neutral trading kernel. Runs on local sample/CSV data, routes proposed orders through `RiskManager` in paper mode, persists state, resumes from the last bar, prevents duplicate processing, and writes local audit artifacts and honest trading metrics. No live trading, broker submission, provider execution, notifications, orders, or credentials.

## L2 — Live Suggestions with Human Approval

L2 is the highest autonomy level Atlas Agent supports for live-market workflows. At L2 the agent may consume live broker snapshots, analyze real positions and exposure, and **propose** orders or safety actions. It does **not** submit orders, approve itself, or bypass any gate.

### What L2 allows

- **Live analysis-only consumption**: read-only sync of account balances, positions, and open orders from a configured broker.
- **Research and signal generation**: local, deterministic synthesis of market context and portfolio state.
- **Order proposals**: proposed orders are written to the local `pending_orders/` approval queue only when the configured approval policy requires it.
- **Safety-action planning**: emergency plans may be generated, but execution requires explicit operator approval.

### What L2 does not allow

- Direct AI-to-broker order submission.
- Self-approval of pending orders or safety plans.
- Automatic promotion of skill candidates or learning suggestions into runtime behavior.
- Skipping `RiskManager`, kill-switch, or opt-in checks.

### Required gates for any L2 proposal to reach a human

1. `TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true`.
2. A supported broker is configured with valid credentials.
3. Kill switch is in `normal` state.
4. `RiskManager` validates the proposal against active limits.
5. Approval policy requires manual review via `atlas approve-order`.
6. Live submit remains governed by the separate `can_submit` gate (`broker.enable_live_submit=false` by default).

### L2 execution model

- Proposals are **advisory-only** until a human operator explicitly approves them.
- In live analysis-only mode, proposals return `live_analysis_only` and create no pending order.
- In legacy/manual live paths, approved pending orders may be submitted only after every gate in the [Live-Submit Safety Contract](live-submit-safety-contract.md) passes.
- Every proposal, rejection, approval, and submit attempt is recorded in the tamper-evident audit hash-chain.

## L3 — Bounded Live Autonomy under Strict Risk Limits

L3 represents a tightly bounded live-autonomy research concept that Atlas is not implementing in v0.6.12. Any future exploration of L3 would require every live order to pass per-order human approval, strict RiskManager limits, explicit opt-in, and active operator oversight. This tier is **not production-ready**, **not unattended-safe**, and **not enabled by default**. It would only be considered for operators who have completed extensive paper-mode validation and can demonstrate operational readiness, and only after additional safety review.

### Required preconditions

All L3 runs require the base live-submit gates from [Live-Submit Safety Contract](live-submit-safety-contract.md) to be true, plus additional L3-specific constraints:

| Gate | Requirement |
|---|---|
| `trading_mode` | `live` only; paper or analysis-only modes do not enter L3. |
| `broker.enable_live_submit` | `true` with a broker whose status is `supported_opt_in`. |
| `l3_autonomy_enabled` | Explicit per-workspace opt-in record, separate from generic live submit. |
| Paper validation | A configurable minimum count of paper-validated strategy runs or backtests completed on the active symbol set. |
| Kill switch | `normal` state; heartbeat enabled and actively refreshed. |
| Market hours | Only active during configured market-open windows unless explicitly overridden. |
| Order approval mode | Manual per-order approval required; batch review may be used, but no auto-approval mode is enabled. |

### Hard bounds enforced at every cycle

L3 does not relax the `RiskManager`. The following limits are enforced on every proposed order and on the post-order projected portfolio state:

- **Single-order notional** — capped to a small, user-configured absolute value.
- **Position notional per symbol** — capped to a small, user-configured absolute value.
- **Total net exposure** — capped to a low percentage of the latest synced account equity.
- **Daily loss limit** — if realized + unrealized PnL for the day breaches the configured threshold, no new L3 orders are allowed until the next session or manual reset.
- **Symbol allowlist** — only explicitly listed symbols are eligible; blocklist entries fail closed.
- **Side and order-type allowlist** — long-only, simple market/limit orders; no options, leverage, shorting, or complex order types.
- **Maximum orders per interval** — evaluated per cycle.
- **Quote freshness** — market orders require a fresh validated quote; stale, crossed, or missing quotes block submission.

Every rejected order is recorded as a `risk_evaluation_blocked` or `live_submit_blocked` audit event with a bounded reason code and no secrets.

### What L3 is not

- L3 is **not** unsupervised autonomous trading. The operator remains responsible for configuration, broker selection, risk limits, and monitoring.
- L3 is **not** a profit guarantee. Strict limits reduce the speed and scale of unintended actions; they do not prevent losses.
- L3 is **not** production-ready. It is a bounded experimental tier requiring explicit opt-in, extensive paper validation, and active human oversight.
- L3 does **not** bypass the `RiskManager`, approval queues, kill switch, or audit hash-chain.

### Roadmap status

L3 bounded live autonomy is a future research concept and is not implemented in the current release. The default path remains paper-only with full manual approval for any live submit.

## L4 — Broad Autonomous Live Execution (Not a Current Capability)

L4 would describe a hypothetical future tier with broader execution authority.
**It is not a current capability or milestone and is not a project goal of Atlas Agent.**
Any future consideration of an L4-like path is governed by the
[Bounded Live Autonomy Governance](bounded-live-autonomy-governance.md) and
requires all external gates listed there.

Before L4 could even be considered, all of the following must be satisfied by
qualified external parties, not by self-assessment:

1. **Legal review** — Confirm compliance with securities, derivatives,
   consumer-protection, and local financial regulations for every intended
   jurisdiction.
2. **Security audit** — Independent review of broker adapters, credentials
   handling, kill-switch logic, audit hash-chain, approval integrity, and access
   controls.
3. **Operational audit** — Validate monitoring, incident response, failover
   behavior, and proof that the system fails closed under error or interruption.
4. **Risk audit** — Verify that deterministic risk gates remain hard-coded,
   non-overrideable by provider output, and independently testable.
5. **Regulatory approval where required** — Any necessary registrations,
   licenses, or no-action relief for the intended use case.

Even if those reviews pass, any broader autonomy remains **opt-in,
broker-neutral, and disabled by default**. It must preserve:

- Human-enablable kill switch and manual pause.
- Per-deployment risk limits that cannot be raised by autonomous logic.
- Tamper-evident audit logging for every autonomous decision.
- A clear "revert to paper" path that disables execution without deleting
  configuration.

Until these external gates are documented and accepted, Atlas stays at
supervised, approval-gated execution. Autonomous live trading is not a current
goal and is not implied by any demo or marketing language.

## Governance and safeguards

### 1. No direct AI-to-broker execution
- AI providers never call broker adapters or execution modules directly.
- Every tool call routes through the `ToolRegistry` and is subject to `RiskManager`, approval, and audit gates.

### 2. Default state is paper / sandbox
- `PaperBroker` is the default execution path.
- Live trading and live submit are disabled by default (`can_submit=false`).
- Provider execution remains locked by default and no credentials are loaded automatically.

### 3. Deterministic risk gates are separate from the LLM
- `RiskManager` enforces hard-coded limits on position size, single-trade notional, daily loss, exposure percentage, symbol lists, and leverage.
- Orders that violate limits are rejected and auditable.

### 4. Kill switch and fail-closed controls
- Hierarchical kill switch (`soft_pause`, `cancel_all`, `flatten_all`, `locked_down`) plus a dead-man heartbeat.
- Missing, unreadable, or corrupt kill-switch state fails closed to `locked_down`.

### 5. Human approval queues
- Proposed orders in paper or legacy/manual live paths are written to `pending_orders/` and require explicit CLI approval.
- Safety action plans require manual approval before execution.

### 6. Tamper-evident audit and manifest system
- All gate failures, risk rejections, kill-switch transitions, and submit attempts are recorded in the hash-chain with run manifests.
- Audit payloads redact secrets, headers, raw broker bodies, paths, and exception text.

### 7. Provider execution boundary
- Provider output is never treated as broker execution authority.
- The provider safety dossier/mock pipeline keeps provider execution locked and records an explicit trust-decision-blocker.

### 8. Reflections, skills, and learning suggestions are advisory-only
- Reflections, skill candidates, and learning suggestions use local artifacts with manual review and manual-only promotion/activation.
- Static fallback is the default; no provider calls, broker calls, or auto-execution occur.

### 9. Discipline profile gate
- An explicit user discipline profile is required before any agentic workflow runs; there is no operational default.
- Validation rejects phrases that attempt to override safety controls.

### 10. Broker-neutral adapter governance
- Every broker must implement the `Broker` interface and be listed in the support inventory.
- New or updated live submit paths require fail-closed guards, opt-in gates, and tests.

### 11. Dashboard and notifications remain safe-by-default
- The dashboard is strictly read-only, zero-secret, and exposes no trading controls.
- Notifications default to the dry-run transport and require explicit configuration to use network transports.

### 12. Backtesting is local-first and deterministic
- Backtests run against local CSV data without network calls and produce deterministic results.

### 13. Documentation and messaging constraints
- No claims that returns are guaranteed, that trading is without risk, that live trading is safe, that operation is unattended, or that autonomous trading readiness exists.
- Prefer "designed to block," "helps reduce," "requires explicit," and "may fail safely."

## Related docs

- [Live-Submit Safety Contract](live-submit-safety-contract.md)
- [Safety](safety.md)
- [Kill Switch Runbook](kill-switch.md)
- [Risk Model](risk-model.md)
- [Live Trading](live-trading.md)
- [Paper-Trading Guide](paper-trading-guide.md)
- [Pending Orders](pending-orders.md)
- [Broker Roadmap](broker-roadmap.md)
- [Product Demo Pack](product-demo-pack.md)
