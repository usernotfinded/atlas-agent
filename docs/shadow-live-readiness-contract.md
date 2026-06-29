# Shadow-Live Readiness Contract (CAND-001 / CAND-005)

> **Status:** planning-only governance document. This contract does **not**
> implement, authorize, or enable live trading. It describes a future read-only
> mode that may be explored after paper autonomy is proven and before any gated
> live submit work begins.
>
> **Update:** CAND-005 implements a strictly local, fixture-first, read-only
> comparison only. It does not implement shadow-live broker sync, live order
> submission, or live-trading readiness. CAND-006 is implemented as a
> simulated-only gated submit conformance rehearsal; it does not submit orders,
> call brokers or providers, load credentials, or indicate live readiness.
> CAND-007 is implemented as a simulated-only runtime readiness envelope
> evaluator; it consumes CAND-004, CAND-005, and CAND-006 evidence plus static
> local policy fixtures and records an envelope artifact. It is an envelope
> evaluator, not a live path, and does not submit orders, call brokers or
> providers, load credentials, or indicate live readiness. The status
> `readiness_envelope_recorded` is evidence-recording status only.
>
> A read-only comparison is **not** live readiness.
>
> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss. Past performance does not guarantee future results. No documentation here recommends any specific security, strategy, broker, or course of action.

## 1. Purpose

This document defines "shadow live" — a future, strictly read-only operating
mode in which Atlas Agent may observe live broker and account state solely to
validate, compare, and improve paper-mode decisions. Shadow live must remain
advisory only. It must not submit orders, mutate broker state, or otherwise act
as execution authority.

Shadow live is a research and validation concept, not a current capability or a
claim that Atlas is ready to trade live money.

## 2. What "shadow live" means

In shadow-live mode, the system may:

- Read and sync broker/account state only through existing read-only paths.
- Compare paper decisions against live market data and live account constraints.
- Log observations, discrepancies, and hypothetical outcomes for later review.
- Surface analysis and suggestions to a human operator.

In shadow-live mode, the system must:

- Remain deterministic, local-first, and credential-aware (no hard-coded secrets).
- Keep provider/LLM output advisory only.
- Route every observation through the existing audit hash-chain.

In shadow-live mode, the system must **not**:

- Submit orders.
- Mutate broker state.
- Hold or move funds.
- Treat provider output as broker execution authority.
- Run without explicit operator opt-in and active oversight.

## 3. Staged readiness ladder

Atlas Agent autonomy is intentionally staged. Each stage adds capability only
inside hard boundaries that remain disabled by default.

| Stage | Name | What Atlas may do | Current status |
|---|---|---|---|
| **1** | Paper autonomy | Run scheduled paper routines, backtests, and dry-runs locally. No broker contact. No orders submitted. | Implemented; default runtime. |
| **2** | Read-only fixture-first comparison (CAND-005) | Compare a stateful paper run against a recorded local broker-like snapshot; produce deterministic read-only artifacts. No broker API calls, no credentials, no live submit. | Implemented as a local read-only comparison only. **Not** live readiness. |
| **3** | Shadow-live read-only | Read live broker/account state, compare paper decisions against live constraints, and surface advisory observations. | **Planning-only.** Not implemented. Not production-ready. Must not submit orders or mutate broker state. |
| **4** | Gated live submit | Submit orders to a live broker only after explicit multi-step opt-in, approval queues, RiskManager validation, kill-switch checks, and audit logging. | Implemented as an approval-gated path; live submit remains disabled by default. See [Live-Submit Safety Contract](live-submit-safety-contract.md). |
| **5** | Bounded autonomous live operation | A tightly bounded research concept requiring per-deployment limits, active oversight, and additional external review. | **Not implemented.** Not a current milestone. Cannot be claimed without independent legal, security, operational, risk, and regulatory review. |

Stage 2 (CAND-005) is the only read-only comparison capability implemented so
far, and it is intentionally narrow: it uses local JSON fixtures, never calls a
real broker API, never loads credentials, and only produces a comparison report.
It is not a step toward autonomous live trading.

CAND-006 is implemented as a simulated-only gated submit conformance rehearsal.
It consumes CAND-004 and CAND-005 evidence plus hypothetical order-intent and
simulated kill-switch, risk-envelope, and approval fixtures, and records a
non-transmittable dry-run submit request. It does not submit orders, call brokers
or providers, load credentials, mutate broker state, or indicate live readiness.

CAND-007 is implemented as a simulated-only runtime readiness envelope evaluator.
It consumes CAND-004, CAND-005, and CAND-006 evidence plus five static local
policy fixtures (runtime envelope, broker capability manifest, operator policy,
kill-switch policy, audit policy), evaluates them in strict fail-closed order,
and records `runtime-readiness-envelope.json` and `runtime-readiness-envelope-report.md`.
It is an envelope evaluator, not a live path. It does not submit orders, call
brokers or providers, load credentials, instantiate runtime trading objects,
mutate state, or indicate live readiness. The status `readiness_envelope_recorded`
is evidence-recording status only.

## 4. Safety boundaries

Shadow live must preserve the same conservative boundaries as the rest of Atlas
Agent:

- **No live submit by default.** Shadow live does not enable order submission; `can_submit` remains `false` in this mode.
- **No broker-state mutation.** All broker interactions are read-only. State-changing endpoints must be unreachable from shadow-live code paths.
- **Provider output remains advisory only.** LLM or provider suggestions cannot directly trigger broker calls, order generation, or configuration changes.
- **RiskManager remains mandatory and deterministic.** Any shadow-live observation that could influence future decisions must still pass deterministic risk checks before any paper or live action is considered.
- **Kill switch remains mandatory and fail-closed.** Shadow-live sync must respect kill-switch state and stop when paused or killed.
- **Audit hash-chain records every read and comparison.** All shadow-live observations, gate failures, and operator opt-in events are tamper-evident and redacted.
- **No credentials, secrets, or private financial data in repo/tests/docs examples.** Broker credentials must be loaded only from explicit user configuration.
- **No profit, risk elimination, or autonomous-trading-readiness claims.** Shadow live is described as a validation aid, not as a guarantee of performance, safety, or readiness.

## 5. Governance relationship

This contract is subordinate to the broader autonomy governance framework. Before
any shadow-live work proceeds, it must remain aligned with [Bounded Live Autonomy
Governance](bounded-live-autonomy-governance.md).

Future shadow-live implementation work, if it happens, must:

- Add no new live-submit capabilities.
- Add no provider-to-broker execution paths.
- Keep all broker interactions behind the existing `Broker` interface and read-only adapters.
- Fail closed when configuration is missing, kill switch is active, or operator opt-in is absent.

## 6. Reviewer checklist

Before accepting changes related to this contract, reviewers should confirm:

- [ ] `docs/shadow-live-readiness-contract.md` exists and states "planning-only."
- [ ] The doc explicitly says shadow live must not submit orders and must not mutate broker state.
- [ ] The doc does not claim Atlas is ready for live, autonomous, or production trading, or that it eliminates risk or guarantees profit.
- [ ] The doc references `docs/bounded-live-autonomy-governance.md`.
- [ ] The static checker `scripts/check_shadow_live_contract.py` passes.
- [ ] The test file `tests/test_shadow_live_contract.py` passes.
- [ ] CAND-005 is described as a local, fixture-first, read-only comparison only.
- [ ] CAND-006 is described as a simulated-only gated submit conformance
      rehearsal that does not submit orders, call brokers/providers, load
      credentials, or indicate live readiness.

Run the verification commands:

```bash
python scripts/check_shadow_live_contract.py
python scripts/check_shadow_live_contract.py --json
pytest tests/test_shadow_live_contract.py -v
```

## 7. Non-goals

- Shadow live is **not** autonomous live trading.
- Shadow live does **not** run without active human supervision.
- Shadow live is **not** intended for real-money production deployment.
- Shadow live does **not** guarantee profits, reduce risk to zero, or validate that any strategy will perform favorably in live markets.
- CAND-005 read-only fixture comparison is **not** live readiness, trading safety, profitability, or permission to submit orders.
- CAND-006 gated submit conformance rehearsal is implemented as simulated-only
  and does not submit orders, call brokers or providers, load credentials, or
  indicate live readiness, trading safety, profitability, or permission to
  submit orders.

---

*This contract was introduced as a planning document (CAND-001). CAND-005
implements only the local fixture-first read-only comparison described here. No
runtime behavior change enables live trading or claims autonomous live-trading
readiness.*
