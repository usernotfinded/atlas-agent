# Live-Submit Safety Contract

This document describes Atlas Agent's live-submit safety contract. It defines the controls, gating, and constraints that apply when Atlas interacts with a live broker.

**This document is not financial advice. It does not guarantee safety, profits, or loss prevention. Trading involves risk, and no automated system can eliminate it.**

---

## 1. Scope

This document specifies the default behaviors, conditions, state machines, and audit rules that govern how Atlas Agent may submit orders to a live broker. It applies to the live-submit execution path only and does not alter the behavior of paper mode, backtesting, or live analysis-only workflows.

This document is not financial advice. Atlas Agent does not guarantee safety, profits, or the prevention of losses. The controls described here are designed to reduce certain categories of risk, but they cannot remove all risk.

---

## 2. Definitions

| Term | Definition |
|------|------------|
| **paper mode** | A simulated trading workflow in which orders are recorded and tracked locally but are never sent to a broker. |
| **live sync** | A read-only operation that fetches account balances, positions, and open orders from a live broker without submitting new orders. |
| **live analysis-only** | A workflow that performs market analysis and may generate signals or recommendations while remaining fully read-only with respect to order submission. |
| **live submit** | The act of sending a new order to a live broker for execution. |
| **can_submit** | The combined runtime gate that evaluates whether all required conditions are satisfied before a live submit may proceed. |
| **opt-in record** | An auditable record indicating that the user has explicitly enabled live submit through the required multi-step opt-in process. |
| **pending order** | An order that has been generated, approved, and is awaiting submission or has been submitted and is awaiting final resolution. |
| **submit attempt** | A recorded attempt to submit an order to a broker, including timestamp, identifiers, and outcome. |
| **reconciliation** | The process of comparing local order state against broker-reported state to resolve discrepancies without submitting new orders. |
| **manual review state** | A pending order state that signals the order requires human review before any further action is taken. |

---

## 3. Default Behavior

- Live submit is **disabled by default**.
- The default workflow is **paper mode**, in which all orders are simulated locally and no broker submission occurs.
- Live sync and live analysis-only are **separate capabilities** from live submit. Enabling live sync or running live analysis does not enable order submission.
- Live submit requires **explicit multi-factor opt-in**, including configuration changes and a recorded opt-in event.
- Documentation and system messages avoid absolute wording such as "impossible," "assured outcomes," "absence of risk," or "zero exposure." Controls are described as mechanisms designed to reduce risk, not as assurances of safety.

---

## 4. Conditions Required for Live Submit

### A. Resolver Readiness Gate: `can_submit`

The `can_submit` flag evaluates resolver-level readiness and opt-in checks. It requires that **all** of the following conditions are satisfied:

1. `broker.enable_live_submit=true`
2. `broker.enable_live_trading=true`
3. `trading_mode="live"`
4. A supported live broker is configured
5. Broker credentials are configured
6. The kill switch is in a normal/readable state
7. The order approval mode is not configured to disable live submit
8. Leverage is disabled
9. A valid opt-in audit record exists

Failure of any single condition causes `can_submit` to evaluate to `false`, which means `resolve_execution_broker("live")` returns `None` and the live submit path is blocked at the resolver level.

### B. Submit Execution Gates

`can_submit=true` only means Atlas has passed the resolver-level live-submit readiness and opt-in checks. It does **not** mean an order will be submitted. `submit-approved-order` still performs additional execution-time gates inside `run_submit_execution()`, including:

- Fresh live sync
- Sync validation
- Market-order handling
- Live risk revalidation
- Live-submit hard limits (notional, symbol, side)
- Submit-state mutation validation
- Final kill-switch check
- Broker boundary checks

These gates are evaluated **after** `can_submit` is already `true`. Failure at any execution-time gate blocks the order without calling `place_order`.

---

## 5. Commands and Capabilities

| Command / Capability | Behavior |
|----------------------|----------|
| `atlas run --mode live` | Analysis-only. There is no live submit path in this command. |
| `atlas submit-approved-order --dry-run` | Read-only. Simulates validation and gate checks without sending an order to the broker. |
| `atlas submit-approved-order --reconcile` | Read-only broker lookup. Retrieves broker state for comparison. It must never call `place_order` or any order-submission method. |
| `atlas submit-approved-order` (without flags) | The only intended live submit boundary. This path may attempt to submit an order **only after** all gates pass and all conditions in Section 4 are satisfied. |

---

## 6. State Machine

Pending orders may be in the following states:

| State | Description | Requires Manual Review |
|-------|-------------|------------------------|
| `approved` | Order has passed all local approvals and is awaiting submission. | No |
| `submit_requested` | A submit attempt has been initiated. | No |
| `acknowledged` | Broker has acknowledged the order. | No |
| `failed` | Submit attempt failed with a clear error. | Yes |
| `submit_uncertain` | Submit response was ambiguous or timed out; broker state is unclear. | Yes |
| `reconciliation_required` | Local and broker state are inconsistent and must be reconciled. | Yes |
| `submit_prepare_failed` | Pre-submit preparation failed (e.g., gate check failure, risk rejection). | Yes |
| `duplicate_reconciled` | Legacy state indicating the order was previously resolved as a duplicate. | No (legacy, no further action) |

States marked as requiring manual review must not proceed to submission automatically.

---

## 7. Reconciliation Contract

Reconciliation is a read-only comparison process. It must adhere to the following rules:

- Reconciliation **must not submit orders**.
- Reconciliation **must not call** `resolve_execution_broker("live")` or any equivalent method that could trigger live execution.
- Broker-found reconciliation may transition a pending order to `acknowledged` **only if** valid local submit evidence exists.
- Submit evidence means a valid `submit_attempt` entry matching the order's `client_order_id`.
- Malformed, missing, or unverifiable `submit_attempt` entries do not count as submit evidence.
- A broker-found order with an `approved` origin (no matching local submit evidence) is considered suspicious and must be placed into a **manual review state**, not `acknowledged`.

---

## 8. Audit Contract

Atlas Agent records the following live-submit-related audit event types:

| Event Type | Description |
|------------|-------------|
| `live_submit_blocked` | A live submit was blocked because one or more gates failed. |
| `live_submit_attempted` | A live submit was attempted after all gates passed. |
| `live_submit_opt_in_enabled` | The user explicitly enabled live submit via the opt-in flow. |
| `live_submit_opt_in_disabled` | The user explicitly disabled live submit. |

### Payload Safety

Audit payloads use safe structured fields only. The following must **not** appear in audit events:

- Raw broker request or response bodies
- HTTP headers
- Secrets, API keys, or credentials
- Exception stack traces or raw error text
- File system paths
- Raw pending order payloads

Only sanitized, structured fields (such as order IDs, timestamps, gate names, and outcome flags) are logged.

---

## 9. Output Safety Contract

CLI and JSON output for safety-critical failures should use **bounded, sanitized, non-secret-bearing messages**. Safety-critical paths should avoid emitting the following untrusted raw values:

- Unsafe `broker_order_id` values in error or status messages
- File paths
- Secrets, headers, or credentials
- Raw broker request or response bodies
- Raw exception text
- Raw pending payload values

Some messages may include bounded internal reason codes or constrained state labels, but they must not include untrusted raw values such as exception text, file paths, headers, broker response bodies, secrets, or raw pending payload values.

---

## 10. Forbidden Claims

Documentation, UI text, and system messages must avoid language that implies safety guarantees or profit assurances. The following categories of claims are prohibited:

- Claims that trading lacks risk entirely, that all risk has been removed, or that exposure is nonexistent.
- Claims that a strategy or tool guarantees profit, assured returns, or positive outcomes.
- Claims that live trading is safe to run without supervision or oversight.
- Claims that losses are impossible or cannot occur.

Instead, use wording that describes controls and requirements without promising outcomes. For example:

- "Designed to block" rather than "prevents"
- "Helps reduce" rather than "eliminates"
- "Requires explicit" rather than "guarantees"
- "May fail safely" rather than "impossible to fail"

---

## 11. Non-Goals

Atlas Agent is not a financial advisor and does not provide investment advice.

Atlas Agent does not guarantee profitable trades, positive returns, or the avoidance of losses.

Atlas Agent does not remove user responsibility. The user remains responsible for configuration, risk settings, broker selection, and monitoring.

Atlas Agent does not custody funds. All funds remain with the user's chosen broker or exchange.

Atlas Agent does not recommend or endorse a specific broker. Broker selection and due diligence are the user's responsibility.

---

*Last updated: 2026-05-14*
