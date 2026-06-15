# Broker Foundation Batch 4.0: Approved-Order Live Submission Design (Revised)

## 1. Executive Summary

Batch 4.0 designs the architecture for human-triggered, approved-order live submission. The design preserves the hard invariant that **no AI or automated path may call `broker.place_order` directly**.

**Critical clarification on source of orders:**
- **AgentLoop** (`atlas run`) and **run_once** (`atlas run-once`) in live mode return `live_analysis_only`. They **do not create pending order files**.
- **OrderRouter.route()** in legacy live mode (used by non-agentic paths or older integrations) creates `pending_approval` files.
- Batch 4.0 submit **only handles orders that already have a `pending_approval` file** on disk. Converting a `live_analysis_only` analysis result into a draft order is **deferred** to a future batch.

**Key principle:** Approval and submission are **separate commands**. A user approves an order in one step. A user submits an approved order in a second step. The submit step is where all live-safety gates are enforced.

**Idempotency:** Uses Alpaca `client_order_id` (deterministic, derived from order). Before any retry, the system queries Alpaca by `client_order_id` to reconcile. **No blind retry** after timeout or unknown broker response.

**can_submit semantics:** `BrokerResolver.can_submit` represents **only** broker capability/configuration (feature flag, credentials, adapter available). Per-order gates (approval, expiry, kill switch, fresh sync, risk revalidation, idempotency, tamper check) are enforced **separately** by the submit command.

**Batch 4.0 is design-only.** No runtime code changes. `can_submit` remains `false`. `resolve_execution_broker("live")` remains `None`.

---

## 2. Recommended Architecture

### High-Level Flow

```
┌─────────────────────────┐
│  AgentLoop / run_once   │────▶ live_analysis_only (NO pending file)
│  live mode              │      Analysis only. No execution bridge.
└─────────────────────────┘

┌─────────────────────────┐
│  OrderRouter.route()    │────▶ pending_approval file created
│  legacy live mode       │      Awaiting human approval.
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐     ┌─────────────────────┐
│  atlas approve-order    │────▶│  Approved Pending   │
│  <order_id>             │     │  Order File         │
└─────────────────────────┘     └─────────────────────┘
                                          │
                                          ▼
┌─────────────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│  atlas submit-approved  │────▶│  Fresh Sync + Risk  │────▶│  Broker Submit  │
│  -order <order_id>      │     │  Revalidation       │     │  (idempotent    │
│                         │     │  (all gates)        │     │   via client_   │
│                         │     │                     │     │   order_id)     │
└─────────────────────────┘     └─────────────────────┘     └─────────────────┘
```

### Submit Step Gates (ALL must pass)

1. **Explicit submit command invoked** (`atlas submit-approved-order <order_id>`)
2. **Pending order file exists and is approved**
3. **Approval has not expired**
4. **Kill switch is in `normal` mode**
5. **Live trading is enabled** (`enable_live_trading=true`)
6. **BrokerResolver.can_submit is true** (broker capability gate only)
7. **Fresh live sync succeeds** (account, positions, open_orders — critical ops pass)
8. **Fresh risk revalidation passes** against synced PortfolioSnapshot
9. **Idempotency key not already submitted successfully**
10. **Order file integrity verified** (hash check)
11. **Not already in `submit_uncertain` state without human reconciliation**

---

## 3. Source-of-Order Design

### What Creates Approvable Orders?

| Path | Creates Pending File? | Status | Batch 4.0 Handling |
|------|----------------------|--------|-------------------|
| `AgentLoop.run()` live mode | **No** | `live_analysis_only` | **Not submittable.** Analysis result only. No execution bridge. |
| `run_once()` live mode | **No** | `live_analysis_only` | **Not submittable.** Analysis result only. No execution bridge. |
| `OrderRouter.route()` live mode | **Yes** | `pending_approval` | **Submittable after approval.** This is the legacy live path that creates pending files. |

### Why AgentLoop/run_once Do Not Create Pending Files

Batch 3.x intentionally designed `live_analysis_only` to create **zero execution artifacts**. The analysis result is for human review only. There is no automated bridge from analysis to order submission.

### How Could live_analysis_only Become Submittable in the Future?

**Deferred to Batch 5.x+:** A separate explicit human command such as:
```bash
atlas draft-order --from-analysis <analysis_run_id> --symbol AAPL --side buy --quantity 10
```
This command would create a `pending_approval` file from an analysis result. Batch 4.0 **does not implement this**.

### Batch 4.0 Scope

Batch 4.0 submit **only** reads and processes approved pending order files that already exist on disk. These files may come from:
- The current `ApprovalManager` schema (legacy `OrderRouter.route()` live mode, test fixtures, or manual creation)
- A future explicit human draft command (deferred to Batch 5.x+)

Batch 4.0 does **not** create new pending order files, does **not** bridge `live_analysis_only` to pending orders, and does **not** re-enable any automated pending-order creation path.

---

## 4. Proposed Command Design

### Primary Command

```bash
atlas submit-approved-order <order_id>
```

**Behavior:**
- Reads pending order file from `pending_orders_dir`
- Verifies approval, expiry, integrity
- Evaluates kill switch
- Checks `BrokerResolver.can_submit`
- Performs fresh live sync
- Revalidates risk
- Generates/persists `client_order_id`
- Submits to broker idempotently
- Records audit/events
- Updates pending order file with submission result

**Dry-run variant:**
```bash
atlas submit-approved-order <order_id> --dry-run
```
Performs all gates up to (but not including) the actual broker call. Returns what would happen.

**Reconciliation variant:**
```bash
atlas submit-approved-order <order_id> --reconcile
```
For orders in `submit_uncertain` state. Queries broker by `client_order_id` and updates local state without resubmitting.

### Why Not `atlas orders submit`?

A nested `orders` subcommand would suggest a full CRUD order management system. Batch 4.0 intentionally keeps the surface minimal: one command for one safety-critical action. A future batch can introduce `atlas orders list/status/cancel` if needed.

### Why Separate Approval and Submit?

- **Temporal decoupling:** A trader may approve during market analysis and submit when the market opens.
- **Safety boundary:** Approval is lightweight (file write). Submit is heavy (network, money, risk).
- **Audit clarity:** Two distinct human actions with distinct audit trails.
- **Kill switch integration:** A kill switch can activate between approval and submit, blocking the submit.
- **Fresh sync requirement:** Market conditions change between approval and submit; sync must be fresh at submit time.

---

## 5. State Machine

### States That Exist Today

| State | Where | Description |
|-------|-------|-------------|
| `proposed` | AgentLoop / run_once | Order proposed by strategy/agent |
| `live_analysis_only` | AgentLoop / run_once | Risk passed but live submit deferred; **no file created** |
| `pending_approval` | OrderRouter (live mode) | Pending order file created; awaiting human approval |
| `approved` | ApprovalManager | Pending order file marked `approved=true` |
| `rejected` | OrderRouter / RiskManager | Risk or gates blocked; no file created |
| `filled` | PaperBroker / SpyBroker | Order executed and filled |

### New States for Batch 4.x

| State | Description |
|-------|-------------|
| `submit_requested` | Human invoked `submit-approved-order` |
| `sync_revalidated` | Fresh live sync succeeded |
| `risk_revalidated` | Fresh risk evaluation passed |
| `submitted` | Broker accepted the order (broker_order_id assigned) |
| `partially_filled` | Broker reports partial fill |
| `fill_confirmed` | Broker reports complete fill |
| `submit_failed` | Broker explicitly rejected the order (4xx, definite error response) |
| `submit_uncertain` | Broker response unknown (timeout, connection lost, inconclusive lookup) |
| `reconciliation_required` | Human must run `--reconcile` to resolve uncertain state |
| `duplicate_reconciled` | Reconciliation found existing broker order by client_order_id; no duplicate submitted |
| `post_submit_tracking_failed` | Broker accepted order but subsequent local status tracking or broker lookup failed |
| `blocked_by_kill_switch` | Kill switch active at submit time |
| `blocked_by_sync_failure` | Critical sync op failed at submit time |
| `blocked_by_risk_revalidation` | Risk failed at submit time |
| `blocked_by_expired_approval` | Approval TTL expired |
| `blocked_by_tampering` | Pending order file integrity check failed |
| `blocked_by_can_submit_false` | BrokerResolver.can_submit is false |
| `cancelled` | Human cancelled before submit |

### State Transitions

```
proposed ──▶ live_analysis_only     (run_once/agent live, NOT submittable)
proposed ──▶ pending_approval        (OrderRouter live)
pending_approval ──▶ approved        (atlas approve-order)
approved ──▶ submit_requested       (atlas submit-approved-order)

submit_requested ──▶ sync_revalidated ──▶ risk_revalidated ──▶ submitted
submit_requested ──▶ blocked_by_*      (any gate fails)

submitted ──▶ partially_filled ──▶ fill_confirmed
submitted ──▶ fill_confirmed
submitted ──▶ cancelled
submitted ──▶ post_submit_tracking_failed   (broker accepted but later lookup/tracking failed)

# Definite broker rejection path
submit_requested ──▶ submit_failed          (broker explicitly rejects, 4xx, definite error)

# Uncertainty path (NO blind retry)
submit_requested ──▶ submit_uncertain ──▶ reconciliation_required
reconciliation_required ──▶ duplicate_reconciled   (found by client_order_id)
reconciliation_required ──▶ submitted               (human retry after confirm 404)
reconciliation_required ──▶ submit_failed           (human aborts after confirm 404)
```

---

## 6. Approved-Order File Schema

### Current Schema (Batch 3.x)

```json
{
  "order": { ...Order fields... },
  "approved": false,
  "created_at": "2026-05-14T10:00:00+00:00",
  "expires_at": "2026-05-14T10:30:00+00:00"
}
```

### Proposed Schema v2 (Batch 4.1+)

```json
{
  "schema_version": "2",
  "order": { ...Order fields... },
  "approved": true,
  "created_at": "2026-05-14T10:00:00+00:00",
  "approved_at": "2026-05-14T10:05:00+00:00",
  "expires_at": "2026-05-14T10:30:00+00:00",
  "approval_actor": "cli:user",
  "order_hash": "sha256-of-canonical-order-json",
  "status": "approved",
  "status_transitions": [
    {"status": "pending_approval", "at": "2026-05-14T10:00:00+00:00"},
    {"status": "approved", "at": "2026-05-14T10:05:00+00:00"}
  ],
  "submit_attempts": [],
  "broker_order_id": null,
  "client_order_id": null,
  "fill_quantity": 0.0,
  "fill_price": null,
  "submitted_at": null
}
```

### Required Fields Rationale

| Field | Purpose |
|-------|---------|
| `schema_version` | Migration/validation |
| `order_hash` | Tamper detection: if order fields change after approval, reject submit |
| `status` | Current state in state machine |
| `status_transitions` | Immutable audit trail within the file |
| `submit_attempts` | History of submit tries with timestamps, results, errors |
| `broker_order_id` | Maps local order to broker order for fill tracking |
| `client_order_id` | Alpaca idempotency key; generated at first submit attempt |
| `fill_quantity` / `fill_price` | Tracks partial fills |

### client_order_id Generation

```python
# Generated at FIRST submit attempt, not at approval time
client_order_id = "atlas-" + sha256(f"{order_id}:{order_hash}".encode()).hexdigest()[:32]
```

- Deterministic: same order_id + same order_hash = same client_order_id
- Length-safe: "atlas-" (6) + 32 hex chars = 38 chars total, well under Alpaca's 64-char limit
- Alpaca-compatible: alphanumeric + hyphen only
- **Validated before persistence:** if any broker adapter reports stricter constraints, truncate or hash further
- Written to pending file BEFORE broker.place_order is called
- Reused on all retries and reconciliation queries

### Tamper Detection

- Compute `order_hash = sha256(json.dumps(order_payload_only, sort_keys=True))` at creation time.
- The `order_payload_only` includes only the immutable `Order` fields (symbol, side, quantity, order_type, limit_price, confidence, stop_loss, leverage, id, created_at, source). It **excludes** all mutable file-level fields: `status`, `submit_attempts`, `broker_order_id`, `client_order_id`, `fill_quantity`, `fill_price`, `submitted_at`, `status_transitions`, `approved`, `approved_at`, `approval_actor`, `expires_at`.
- At submit time, recompute from the persisted `order` dict and compare to stored `order_hash`. Mismatch = `blocked_by_tampering`.
- The file itself is not cryptographically signed (filesystem permissions + hash check is sufficient for Batch 4.x).

---

## 7. Idempotency / client_order_id Design

### Strategy

1. **Generate at first submit attempt:** When `atlas submit-approved-order` is first invoked, compute deterministic `client_order_id` from `order_id + order_hash` using the length-safe scheme above.
2. **Persist before broker call:** Write `client_order_id` and `status: submit_requested` to the pending file BEFORE calling `broker.place_order`.
3. **Broker payload:** Pass `client_order_id` in the Alpaca order payload.
4. **On timeout/uncertainty:**
   - Mark status `submit_uncertain`.
   - Do NOT blindly retry.
   - Require human to run `atlas submit-approved-order <order_id> --reconcile`.
5. **On reconciliation:**
   - Query Alpaca GET `/v2/orders:by_client_order_id` with `client_order_id`.
   - If found: update local state with broker order ID and status. Mark `duplicate_reconciled`. No duplicate submitted.
   - If lookup returns 404 (definitely not found): mark `reconciliation_required`. Human can explicitly retry.
   - If lookup is inconclusive (network error, malformed response, auth failure): block. Do not retry. Require human investigation.
6. **On explicit retry:**
   - Reuse same `client_order_id`.
   - Query broker first. If found, reconcile. If not found, submit.
   - If query is inconclusive, block and require human reconciliation.
7. **Audit:** Every idempotency check, reconciliation, pass, and block is auditable.

### Alpaca GET by client_order_id

Alpaca supports:
```
GET /v2/orders:by_client_order_id?client_order_id={client_order_id}
```

This endpoint is used for reconciliation. It returns the order if it exists, or 404 if it does not.

### Crash Recovery

If the process crashes between `broker.place_order` success and local file write:
- On next start, the pending file shows `submit_requested` (or `submit_uncertain` if we managed to write that).
- Human runs `--reconcile`.
- System queries Alpaca by `client_order_id`.
- If found: reconciles. Marks `duplicate_reconciled`.
- If not found (404): human may explicitly retry, which reuses the same `client_order_id` and submits.
- If lookup is inconclusive: block. Require human investigation. Do not retry blindly.
- **No duplicate risk** because reconciliation queries before retry, and the same `client_order_id` is reused on retry.

---

## 8. BrokerResolver / can_submit Semantics

### What can_submit Represents

`BrokerResolver.can_submit` is a **broker capability/configuration gate only**. It answers: "Is the broker infrastructure capable of accepting submit requests?"

`can_submit=true` requires:
1. `enable_live_trading=true`
2. Broker credentials are present and non-empty
3. Broker adapter is implemented and audited
4. Broker submit feature flag is enabled (e.g., `ATLAS_LIVE_SUBMIT_ENABLED=true`)

`can_submit` does **NOT** depend on:
- Whether any specific order is approved
- Whether approval is expired
- Kill switch state
- Fresh sync status
- Risk revalidation result
- Idempotency state
- Order file integrity

### Per-Order Gates (Enforced by Submit Command)

These are checked **independently** by `atlas submit-approved-order`:
1. Pending order file exists
2. Order is approved
3. Approval not expired
4. Kill switch is `normal`
5. Fresh live sync succeeds
6. Fresh risk revalidation passes
7. Order file integrity verified
8. Not already successfully submitted

### resolve_execution_broker("live") Design

Currently returns `None`. In Batch 4.3+, it may return an `AlpacaBroker` instance:

```python
def resolve_execution_broker(self, mode: str) -> BrokerResolution:
    status = self.resolve_status(mode)
    if mode == "paper":
        ...  # existing paper path
    if mode == "live" and status.can_submit:
        from atlas_agent.brokers.alpaca import AlpacaBroker
        return BrokerResolution(
            execution_broker=AlpacaBroker(config=self.config),
            sync_provider=None,
            status=status,
        )
    return BrokerResolution(execution_broker=None, sync_provider=None, status=status)
```

**Key point:** `can_submit` is the broker capability gate. Even if `can_submit=true`, the submit command still enforces all per-order gates. Even if `can_submit=false`, `resolve_execution_broker` returns `None`.

### can_submit Transition Plan

| Batch | can_submit |
|-------|------------|
| 3.x | `false` for all live brokers |
| 4.0-4.2 | `false` (design + dry-run only) |
| 4.3 | `false` (Alpaca submit adapter implemented, but gated off) |
| 4.4 | `false` (risk revalidation + idempotency implemented, gated off) |
| 4.5 | May become `true` for Alpaca after full audit and checklist sign-off |

---

## 9. Fresh Sync + Risk Revalidation Design

### Pre-Submit Sync Flow

```python
def _pre_submit_sync(config, audit, run_id):
    resolver = BrokerResolver(config)
    status = resolver.resolve_status("live")
    if not status.can_sync:
        return SubmitResult(blocked="broker_sync_unavailable")

    resolution = resolver.resolve_sync_provider("live")
    if resolution.sync_provider is None:
        return SubmitResult(blocked="broker_sync_unavailable")

    sync_service = BrokerSyncService(broker=resolution.sync_provider, ...)
    sync_result = sync_service.sync()

    warnings, error = validate_live_sync(sync_result, resolution.status)
    if error:
        return SubmitResult(blocked="sync_critical_failure")

    snapshot = sync_service.get_portfolio_snapshot(sync_result)
    return SubmitResult(ok=True, snapshot=snapshot, warnings=warnings)
```

### Pre-Submit Risk Revalidation Flow

```python
def _pre_submit_risk_revalidation(order, snapshot, config):
    effective_price = order.limit_price  # or market price for market orders
    risk_input = OrderRiskInput(
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        price=effective_price,
        notional=order.quantity * effective_price,
        confidence=order.confidence,
        stop_loss=order.stop_loss,
    )
    risk_limits = RiskLimits(...)  # from config
    risk_manager = RiskManager(limits=risk_limits)
    decision = risk_manager.evaluate_order(risk_input, snapshot, mode="live")
    return decision
```

### What If Risk Passed at Proposal but Fails at Submission?

**Behavior:** Block the submit. Return `status="blocked_by_risk_revalidation"`. Write audit event `live_submit_blocked` with reasons. Do NOT call broker.

### What If Live Sync Fails Right Before Submission?

**Behavior:** Block the submit. Return `status="blocked_by_sync_failure"`. Write audit event `live_submit_sync_failed` with failed operations. Do NOT call broker.

---

## 10. Failure Handling Matrix

| Scenario | Behavior | Audit Event | User Message |
|----------|----------|-------------|--------------|
| Network timeout | Mark `submit_uncertain`. Require `--reconcile`. No blind retry. | `live_submit_uncertain` | "Broker response uncertain. Run --reconcile to verify." |
| Broker 4xx (bad request) | Fail closed, do not retry | `live_submit_failed` | "Broker rejected order: {sanitized_code}" |
| Broker 5xx | Mark `submit_uncertain`. Require `--reconcile`. | `live_submit_uncertain` | "Broker error. Run --reconcile to verify status." |
| Malformed broker response | Mark `submit_uncertain`. Require `--reconcile`. | `live_submit_uncertain` | "Malformed broker response. Run --reconcile." |
| Order already submitted (reconciliation finds it) | Reconcile local state. No duplicate submitted. | `live_submit_duplicate_reconciled` | "Order already submitted. Reconciled with broker." |
| Potential duplicate detected (retry after prior uncertain submit) | Query by client_order_id, reconcile. | `live_submit_duplicate_reconciled` | "Order already accepted by broker. Reconciled." |
| Partial fill | Update file with fill_qty, leave open | `live_partial_fill_confirmed` | "Order partially filled: X/Y" |
| Broker accepts but local write fails | Log error, mark `submitted` (broker accepted), then `post_submit_tracking_failed` on subsequent lookup failure | `live_submit_acknowledged` + error | "Submitted but local state update failed. Run --reconcile." |
| Local status=submitted but broker lookup fails | Mark `post_submit_tracking_failed`, require reconcile | `live_post_submit_tracking_failed` | "Cannot confirm order status. Run --reconcile." |
| Kill switch activates mid-submit | If broker call not yet sent: block. If in-flight: mark uncertain. | `live_submit_blocked` or `live_submit_uncertain` | "Kill switch activated, submission blocked/uncertain." |
| Sync succeeds but risk fails | Block, do not submit | `live_submit_blocked` | "Risk revalidation failed, submission blocked" |
| Stale/expired approval | Block, do not submit | `live_submit_blocked` | "Approval expired, resubmit for approval" |
| Tampered pending order file | Block, do not submit | `live_submit_blocked` | "Order file integrity check failed" |
| can_submit=false | Block, do not submit | `live_submit_blocked` | "Live submit not enabled" |

---

## 11. Required Tests Before can_submit Can Become True

### Negative Guard Tests

1. `test_live_analysis_only_does_not_create_pending_order` — AgentLoop and run_once live return `live_analysis_only` with no pending file.
2. `test_explicit_human_approval_required_before_submit` — Submit without approval returns `blocked`.
3. `test_submit_rejects_analysis_only_result_directly` — Passing an analysis result ID (not a pending file) to submit fails safely.
4. `test_no_submit_without_explicit_submit_command` — AgentLoop and run_once must never trigger submit.
5. `test_no_submit_from_agent_loop` — `propose_order` in AgentLoop returns `live_analysis_only`, never reaches submit.
6. `test_no_submit_from_run_once` — run_once live returns `live_analysis_only`, never reaches submit.
7. `test_no_submit_when_can_submit_false` — Even if all other gates pass, `can_submit=false` blocks submit.
8. `test_can_submit_true_alone_is_insufficient` — can_submit=true but missing approval/sync/risk still blocks.
9. `test_no_submit_if_kill_switch_active` — Kill switch in any non-normal mode blocks submit.
10. `test_no_submit_if_approval_expired` — TTL expiration blocks submit.
11. `test_no_submit_if_live_sync_fails` — Critical sync failure blocks submit.
12. `test_no_submit_if_risk_revalidation_fails` — Fresh risk eval failure blocks submit.
13. `test_no_duplicate_submit_on_retry` — Same client_order_id cannot trigger two broker calls.
14. `test_client_order_id_stable_across_retry` — Retry uses same client_order_id.
15. `test_timeout_does_not_blindly_call_broker_twice` — Timeout marks uncertain, requires reconcile.
16. `test_reconciliation_by_client_order_id_prevents_duplicate` — Query by client_order_id finds existing order.
17. `test_pending_order_tampering_rejected` — Modified order file fails hash check.
18. `test_broker_exception_sanitized` — Raw broker errors never leak to user/output.
19. `test_partial_fill_recorded_safely` — Partial fill updates state without secrets.
20. `test_filled_order_state_transition` — Complete fill transitions state correctly.
21. `test_paper_mode_unchanged` — Paper path is untouched by live submit logic.
22. `test_no_private_values_in_audit_or_events` — All payloads redacted.
23. `test_no_paper_fallback_in_live` — Live sync failure does not fall back to paper.
24. `test_submit_blocked_if_resolve_execution_broker_returns_none` — Even if can_submit is accidentally true but resolver returns None, block.

### Positive Path Tests

25. `test_successful_submit_flow` — All gates pass, broker accepts, state transitions correctly.
26. `test_successful_submit_with_noncritical_sync_warning` — Balances-only failure proceeds with warning.
27. `test_successful_reconciliation_after_timeout` — Reconcile finds broker order, no duplicate.
28. `test_successful_explicit_retry_after_reconcile_not_found` — Reconcile finds nothing, human retries, submits.

---

## 12. Recommended Implementation Batches

### Batch 4.0 (Design Only) — CURRENT
- Produce this design document.
- No code changes.
- `can_submit=false`.

### Batch 4.1: Pending Order Schema Hardening
- Update `ApprovalManager` to write v2 schema.
- Add `order_hash`, `status`, `status_transitions`, `client_order_id` (null at approval), `submit_attempts`.
- Backward compatibility: read v1 files, upgrade on approval.
- Tests: schema migration, hash computation, tamper detection.

### Batch 4.2: Submit Command Dry-Run
- Add `atlas submit-approved-order <order_id> --dry-run` CLI command.
- Implement all gates up to (but not including) broker call.
- Returns JSON/human-readable report of what would happen.
- `can_submit` still `false`.
- Tests: dry-run passes all gates, dry-run blocked by each gate individually.

### Batch 4.3: Alpaca Submit Adapter
- Implement `AlpacaBroker.place_order` production path (already scaffolded).
- Add `client_order_id` to payload.
- Add timeout, exception sanitization.
- Add GET by `client_order_id` reconciliation method.
- Keep `can_submit=false` — tests verify the adapter works but live path remains gated.
- Tests: adapter unit tests with mocked HTTP, exception sanitization, timeout handling, client_order_id passthrough.

### Batch 4.4: Risk Revalidation + Idempotency + Reconciliation
- Implement fresh sync + risk revalidation in submit command.
- Implement `client_order_id` generation, persistence, dedup.
- Implement `--reconcile` command using GET by client_order_id.
- Integrate kill switch check.
- Integrate approval expiry check.
- Integrate order hash integrity check.
- `can_submit=false` still.
- Tests: all 24 negative guard tests + 4 positive path tests.

### Batch 4.5: Audited Live Submit Opt-In
- Full end-to-end integration test with mocked broker.
- Update release checklist with 4.5 assertions.
- Update CHANGELOG.
- **Only after all tests pass and checklist is signed off:** set `can_submit=true` for Alpaca.
- **Even then:** Default remains `can_submit=false`. User must explicitly opt in via env var or config flag.

---

## 13. Safety Invariants (Non-Negotiable)

- [ ] No AI or automated path may call `broker.place_order`.
- [ ] Live submit must be human-triggered via explicit CLI command.
- [ ] `BrokerResolver.can_submit` must remain `false` until full implementation + audit complete.
- [ ] `resolve_execution_broker("live")` must remain `None` until `can_submit` is explicitly enabled.
- [ ] Fresh live sync must succeed before any submit.
- [ ] Fresh risk revalidation must pass before any submit.
- [ ] Kill switch in non-normal mode must block submit.
- [ ] Expired approval must block submit.
- [ ] Tampered pending order file must block submit.
- [ ] No blind retry after timeout or uncertain broker response.
- [ ] Timeout/uncertainty must require human `--reconcile`.
- [ ] `client_order_id` must be deterministic and stable across retry.
- [ ] No paper fallback in live mode.
- [ ] No broker credentials in config.toml.
- [ ] No private values in CLI, JSON, audit, events, diagnostics, or logs.
- [ ] No raw broker exceptions in user-facing output.
- [ ] No claims of production-ready live trading maturity in docs.
- [ ] Paper mode must remain completely unchanged.

---

## 14. Explicitly Deferred Items

- **Analysis-to-order bridge:** Converting `live_analysis_only` results into draft orders is deferred to Batch 5.x+.
- **Real-time fill tracking / WebSocket:** Deferred to Batch 5.x. Batch 4.x uses polling and reconciliation.
- **Cancel after submit:** CLI scaffolded but full cancel-confirm loop deferred.
- **Flatten integration with live submit:** Kill switch `flatten_all` triggers safety executor, not the submit path.
- **Multi-broker submit:** Batch 4.x targets Alpaca only. Binance/CCXT/IBKR submit remains deferred.
- **Cryptographic signature of pending order files:** Hash check is sufficient for Batch 4.x.
- **Automatic re-analysis / re-approval:** If risk fails at submit time, user must manually re-run analysis.
- **Stale sync detection / caching policy:** Fresh sync on every submit is the Batch 4.x policy.
- **2FA/TOTP on submit:** Not required in Batch 4.x. Kill switch disable already requires TOTP.

---

## 15. Final Recommendation: Proceed

**Recommendation: Proceed with Batch 4.0 design as documented above.**

The revised architecture satisfies all hard constraints and user corrections:
- `live_analysis_only` paths do not create pending orders and are not submittable.
- `client_order_id` provides broker-visible idempotency with reconciliation.
- No blind retry after timeout.
- `can_submit` is cleanly separated from per-order gates.
- Idempotency key is generated at submit time, stable across retries.
- New states handle uncertainty and reconciliation explicitly.
- Comprehensive negative guard test plan ensures safety before any live submit is enabled.

The design is conservative, fail-closed, and aligns with the project's safety-first philosophy. No runtime behavior is changed in Batch 4.0.
