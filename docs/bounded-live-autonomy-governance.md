# Bounded Live Autonomy Governance

> **Status:** planning and governance only. This document does **not** authorize,
> implement, or enable autonomous live trading in the current release.

> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss. Past performance does not
> guarantee future results.

This document defines the governance framework for how Atlas Agent may, over the
long term, explore bounded autonomous live trading while keeping the current
release honest, safe, and fully opt-in.

Autonomy is a product direction, not a current capability. The goal is to reduce
manual friction progressively, but only inside hard safety boundaries that
remain disabled by default.

## Product North Star

The long-term product direction is to move from supervised, human-in-the-loop
workflows toward bounded, opt-in, auditable autonomy:

- More autonomous **paper/sandbox** workflows first.
- Live **analysis and suggestions** with explicit human approval next.
- A tightly bounded **live-autonomy research tier** only after extensive paper
  validation, explicit opt-in, active oversight, and additional safety review.
- Any broader autonomous live-trading direction only after external legal,
  security, operational, risk, and regulatory review.

This direction is intentionally conservative. More autonomy is valuable only if
it is bounded, reversible, auditable, fail-closed, and explicitly opt-in.

## Current release truth

As of the current release line (`v0.6.12` public, `v0.6.13` planning only):

- Autonomous live trading is **not implemented**.
- The system is **not autonomous-live-trading ready**.
- The system is **not production-ready** for unattended or real-money trading.
- Live trading and live submit remain **disabled by default**.
- Provider/LLM output is **never** treated as broker execution authority.
- Every live submit path is gated by deterministic risk controls, approval queues,
  kill-switch checks, and audit logging.
- No profit, risk elimination, claims that live trading is safe, or
  autonomous-trading-readiness claims are made.

## Staged autonomy ladder

| Level | Name | What the agent may do | Status |
|---|---|---|---|
| **L0** | Research / paper assistant | Generate local research artifacts, run backtests, print dry-runs, generate reports. No orders. | Implemented; default-safe baseline. |
| **L1** | Autonomous paper workflows | Run scheduled paper routines autonomously within deterministic limits. No broker contact. | Implemented; paper mode is the default runtime. |
| **L2** | Live analysis and suggestions with human approval | Consume live broker snapshots for analysis and propose orders; every proposal requires explicit human approval. | Implemented as analysis-only/suggestion path; live submit remains approval-gated. |
| **L3** | Bounded live-autonomy research tier | A tightly bounded research concept requiring per-order human approval, strict RiskManager limits, explicit opt-in, and active operator oversight. | **Not implemented.** Not production-ready; not unattended-safe; not enabled by default. |
| **L4** | Broad autonomous live execution | A hypothetical future tier with broader execution authority. | **Not a current capability or milestone.** Cannot be claimed or pursued without external legal, security, risk, operational, and regulatory review. |

### What each level is not

- **L0–L1 are not live trading.** They touch no real money, no broker, and no provider by default. See [Paper Mode Provider Isolation](paper-provider-isolation.md) for the provider-free paper path.
- **Paper strategy evaluation is L1 research only.** It ranks sample-data
  backtests for paper follow-up; see [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Strategy Sensitivity Evaluation](paper-strategy-sensitivity.md).
- **L2 is not autonomous order submission.** Proposals are advisory until a human approves them.
- **L3 is not unsupervised trading.** The operator remains responsible for configuration, broker selection, risk limits, and monitoring.
- **L4 is not a current goal.** It is a hypothetical direction that requires explicit external gates before any consideration.

## Hard invariants

These invariants apply at every level that touches orders or broker state, and
must remain true for any future autonomy work:

1. **Live trading is disabled by default.** No run starts in live mode without explicit configuration.
2. **Live submit is disabled by default.** `can_submit` evaluates to `false` unless every opt-in gate is satisfied.
3. **Provider output is never execution authority.** LLM/provider suggestions route through deterministic gates; they cannot directly submit orders.
4. **Broker execution remains gated.** Every broker adapter implements the `Broker` interface and passes fail-closed guards.
5. **RiskManager remains deterministic and mandatory.** Hard-coded limits on position size, notional, daily loss, exposure, symbols, and leverage are enforced independently of LLM reasoning.
6. **Kill switch remains mandatory and fail-closed.** Hierarchical kill-switch controls plus a dead-man heartbeat must be present and active.
7. **Approval queues remain mandatory where applicable.** Live submit requires explicit human approval unless a future, separately approved, narrowly scoped policy changes this.
8. **Audit hash-chain records every decision and submit attempt.** All gate failures, risk rejections, kill-switch transitions, and submit attempts are tamper-evident and redacted.
9. **No credentials, secrets, or private financial data in repo/tests/docs examples.** All credentials are loaded only from explicit user configuration.
10. **No profit, risk elimination, claims that live trading is safe, or autonomous-trading-readiness claims.** Public messaging stays conservative and verifiable.

## External gates before any L4-like path

Before Atlas Agent could consider any L4-like broad autonomous live-trading
capability, all of the following must be satisfied by qualified external parties,
not by self-assessment:

- **Legal review** — Confirm compliance with securities, derivatives,
  consumer-protection, and local financial regulations for every intended
  jurisdiction.
- **Independent security audit** — Review broker adapters, credentials handling,
  kill-switch logic, audit hash-chain integrity, approval integrity, and access
  controls.
- **Operational audit** — Validate monitoring, incident response, failover
  behavior, and proof that the system fails closed under error or interruption.
- **Risk audit** — Verify that deterministic risk gates remain hard-coded,
  non-overrideable by provider output, and independently testable.
- **Broker-adapter audit** — Confirm every adapter implements fail-closed behavior
  and cannot bypass resolver guards.
- **Regulatory/compliance review** — Any registrations, licenses, or no-action
  relief required for the intended use case.

Even if all reviews pass, any broader autonomy remains opt-in, broker-neutral,
and disabled by default. It must preserve:

- A human-enablable kill switch and manual pause.
- Per-deployment risk limits that cannot be raised by autonomous logic.
- Tamper-evident audit logging for every autonomous decision.
- A clear "revert to paper" path that disables execution without deleting
  configuration.

## Governance principles

- **Autonomy is a direction, not a release claim.** Each release is evaluated on
  its actual implemented capabilities, not on the long-term vision.
- **Prefer bounded over broad.** A narrow, well-governed autonomy feature is
  better than a wide, unreviewed one.
- **Prefer reversible over permanent.** Every autonomy feature must have a clear
  disable/revert path.
- **Prefer auditable over opaque.** Every autonomous decision must leave a
  tamper-evident record.
- **Prefer fail-closed over fail-operational.** Missing configuration, corrupt
  state, or operator absence must block execution, not allow it.

## Relationship to other documents

- [Autonomy Roadmap](autonomy-roadmap.md) — staged autonomy levels and current/future state.
- [Autonomous Paper Workflow](autonomous-paper-workflow.md) — concrete L1 autonomy proof (paper-only, local-only, no broker/provider contact).
- [Paper Strategy Evaluation](paper-strategy-evaluation.md)
- [Paper Strategy Sensitivity Evaluation](paper-strategy-sensitivity.md) — deterministic paper-only strategy comparison and follow-up gate.
- [Live-Submit Safety Contract](live-submit-safety-contract.md) — detailed gating for any live submit.
- [Risk Model](risk-model.md) — deterministic risk gate design.
- [Kill Switch Runbook](kill-switch.md) — kill-switch controls and escalation.
- [Broker Roadmap](broker-roadmap.md) — broker adapter support and fail-closed behavior.
- [Product Capability Inventory](product-capability-inventory.md) — current capability truth.

---

*This governance document was introduced in the `v0.6.13` planning line
(CAND-022). It does not change runtime behavior, enable live trading, or claim
autonomous live-trading readiness.*
