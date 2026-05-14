# Broker Foundation Batch 4.7 Plan

**Pre-Submit Mutation Wiring Behind Hard-Disabled Gate**

**Date:** 2026-05-14  
**Status:** Planning (not yet implemented)  
**Target Version:** 0.5.6.dev5

---

## 1. Context

Batch 4.6 added three strict helper-only submit state mutation primitives in `submit_state.py`:

- `append_submit_attempt()`
- `build_submit_requested_payload()`
- `mark_submit_requested()`

These helpers enforce:
- deterministic `client_order_id`
- UUID4 `attempt_id`
- actor allowlist (`submit:cli`, `system`)
- error_code allowlist
- `submit_requested_at` (not `submitted_at`)
- atomic file writes
- no raw secret-shaped values

**Batch 4.6 did NOT wire these helpers into runtime submit execution.**

The current `run_submit_execution()` skeleton performs all safety gates and blocks at `can_submit=false` with **no file mutation**, **no `client_order_id` persistence**, and **no broker interaction**.

---

## 2. Recommended Option: C

### Decision

**Adopt Option C:** Wire `mark_submit_requested()` **only if `can_submit=true`**, then immediately block before any broker submit.

### Rationale

| Option | Production Behavior | Testability | Risk |
|--------|--------------------|-------------|------|
| A — Keep unwired | Identical to today | No new test surface | Zero progress |
| B — Internal env flag | User can create `submit_requested` without broker capability | High | Risk of orphaned submit state |
| **C — Wire after can_submit=true** | **Identical to today** (`can_submit=false`) | **Mocked tests prove boundary** | **Lowest risk with measurable progress** |

Option C is the only choice that:
1. **Leaves production behavior completely unchanged** (Alpaca `can_submit=False` in `BrokerResolver`).
2. **Allows unit tests to prove the mutation boundary works** under mocked `can_submit=True`.
3. **Prevents any broker submission** (`resolve_execution_broker` and `place_order` remain unreachable).
4. **Produces auditable state** (`submit_attempts`, `status_transitions`) when the gate hypothetically opens in a future batch.

### Rejected Options

- **Option A rejected:** No progress toward runtime state boundary validation.
- **Option B rejected:** An env flag that bypasses the hard `BrokerResolver` gate creates a divergence between "production says no" and "code says maybe." This contradicts the AGENTS.md rule that `can_submit` is the single source of truth for submit capability.

---

## 3. State Boundary Placement

### Exact Gate Order

The execution skeleton `run_submit_execution()` must preserve this exact order. All gates 1–14 must pass before gate 15 decides whether mutation occurs.

```
 1. pending id / path validation
 2. pending file schema + hash validation
 3. terminal / idempotency state gate (NEW: include submit_requested)
 4. status == "approved"
 5. non-expired approval
 6. enable_live_trading == true
 7. kill switch normal
 8. client_order_id computed / validated
 9. live sync provider available (can_sync)
10. fresh live sync passes
11. validate_live_sync passes
12. PortfolioSnapshot built
13. limit-order price available; market orders still block
14. risk revalidation passes
15. can_submit check
    ├── can_submit == false  →  block with NO mutation (production path)
    └── can_submit == true   →  proceed to mutation
16. mark_submit_requested() atomically writes submit_requested state
17. immediately block before broker submit
18. no resolve_execution_broker("live")
19. no broker.place_order
20. no OrderRouter.route
```

### Why This Order

- **Gates 1–14 are identical to Batch 4.6.** No behavioral change.
- **Gate 3 (idempotency) is expanded** to include `submit_requested` so reruns cannot pass through again.
- **Gate 15 is the decision point.** `can_submit=false` → zero mutation. `can_submit=true` → exactly one atomic mutation, then hard stop.
- **Gate 16 is the only new side effect** and it occurs after ALL validation passes.
- **Gates 17–20 are negative invariants:** code paths that must remain unreachable in Batch 4.7.

---

## 4. New Report Statuses and Blocked Reasons

### Two Distinct Outcomes After Gate 14

#### A. `can_submit = false` (Production Path)

```python
SubmitExecutionReport(
    ok=False,
    status="blocked",
    order_id=order_id,
    gates={..., "can_submit": "fail"},
    blocked_reason="can_submit_false",
    message="All safety gates passed, but live submit remains disabled.",
    client_order_id=cid,
    risk=risk_dict,
    sync={...},
    warnings=warnings,
)
```

- **No file mutation.**
- **Message unchanged from Batch 4.6** (production compatibility).

#### B. `can_submit = true` (Mocked / Future Path)

```python
# Step 1: mutate
mark_submit_requested(
    path,
    order_id=order_id,
    client_order_id=cid,
    actor="submit:cli",
)

# Step 2: block
SubmitExecutionReport(
    ok=False,
    status="blocked",
    order_id=order_id,
    gates={..., "can_submit": "pass", "broker_submit": "not_implemented"},
    blocked_reason="broker_submit_not_implemented",
    message="Submit state prepared, but broker submission is not implemented in this release.",
    client_order_id=cid,
    risk=risk_dict,
    sync={...},
    warnings=warnings,
)
```

- **File IS mutated** to `submit_requested`.
- **`submitted_at` remains `null`.**
- **No broker call.**
- **Clear messaging** tells the operator that local state is prepared but the broker was never contacted.

### Idempotency Block for `submit_requested` Rerun

When `run_submit_execution()` encounters a file already in `submit_requested`:

```python
SubmitExecutionReport(
    ok=False,
    status="blocked",
    order_id=order_id,
    gates={..., "idempotency": "fail"},
    blocked_reason="reconciliation_required",
    message="Order is in submit_requested state. Run --reconcile first.",
)
```

- **No mutation.**
- **No duplicate `submit_attempt`.**
- **Blocked before sync/risk gates** (at the idempotency gate).

### Blocked Reason Catalog (Batch 4.7)

| `blocked_reason` | When | Mutation? |
|-----------------|------|-----------|
| `invalid_pending_order_id` | path traversal | No |
| `pending_order_not_found` | file missing | No |
| `invalid_pending_order` | JSON/hash invalid | No |
| `already_submitted` | status == submitted | No |
| `already_reconciled` | status == duplicate_reconciled | No |
| `reconciliation_required` | status in (submit_uncertain, reconciliation_required, **submit_requested**) | No |
| `terminal_state` | status in (cancelled, rejected, expired) | No |
| `not_approved` | approved=false or status != approved | No |
| `approval_expired` | expires_at in past | No |
| `live_trading_disabled` | enable_live_trading=false | No |
| `kill_switch_active` | kill switch not normal | No |
| `invalid_client_order_id` | stored cid malformed | No |
| `broker_sync_unavailable` | can_sync=false | No |
| `live_sync_failed` | validate_live_sync failed | No |
| `market_price_unavailable` | order_type == market | No |
| `risk_revalidation_failed` | RiskManager rejected | No |
| `can_submit_false` | can_submit=false (gate 15) | **No** |
| `broker_submit_not_implemented` | can_submit=true, mutation done, then blocked (gate 17) | **Yes** |

---

## 5. File Mutation Policy

When `can_submit=true` and all gates pass:

### What `mark_submit_requested()` Does (Already Implemented in Batch 4.6)

1. **Preconditions (fail-closed):**
   - File exists and is valid v2 schema.
   - `status == "approved"`.
   - Hash matches recomputed hash.
   - `client_order_id` matches deterministic computation.
   - If payload already has `client_order_id`, it must match the provided one.

2. **Atomic mutation via `_atomic_write_json`:**
   - `status = "submit_requested"`
   - `client_order_id = <computed_cid>`
   - `submit_requested_at = now.isoformat()`
   - `submitted_at` **stays unchanged / null**
   - `broker_order_id` **stays null**
   - Appends `status_transitions` entry: `{"status": "submit_requested", "at": <now>, "actor": "submit:cli"}`
   - Appends `submit_attempts` entry:
     ```json
     {
       "attempt_id": "<uuid4>",
       "client_order_id": "<cid>",
       "status": "submit_requested",
       "created_at": "<now>",
       "actor": "submit:cli",
       "risk_revalidated": true,
       "sync_revalidated": true,
       "broker_order_id": null,
       "error_code": null
     }
     ```

### What Must NOT Happen

- `submitted_at` must NOT be set.
- `broker_order_id` must NOT be set.
- No second `submit_attempt` on rerun.
- No `status = "submitted"`, `"acknowledged"`, or `"failed"`.
- No call to `resolve_execution_broker("live")`.
- No call to `broker.place_order(...)`.
- No call to `OrderRouter.route(...)`.

---

## 6. Re-Running Behavior After `submit_requested`

### Scenario: User reruns `atlas submit-approved-order <id>` on a `submit_requested` file

1. **Idempotency gate catches it** (step 3 in gate order).
2. **Blocked reason:** `reconciliation_required`.
3. **Message:** `"Order is in submit_requested state. Run --reconcile first."`
4. **No file mutation.**
5. **No new `submit_attempt`.**
6. **No `client_order_id` recomputation.**
7. **No sync, no risk, no can_submit check reached.**

### Why Not Auto-Revert to `approved`?

Because:
- In a future batch, `submit_requested` may mean "broker was contacted but result is uncertain."
- Auto-reverting would destroy the audit trail of the submit attempt.
- Human reconciliation is the safe default for any state that implies a broker interaction may have occurred.

---

## 7. Reconcile Interaction

### Current Reconcile Allowed Statuses

```python
_is_allowed_reconcile_status = (
    "approved", "submit_uncertain", "reconciliation_required", "duplicate_reconciled"
)
```

**Batch 4.7 change:** Add `"submit_requested"` to this tuple.

### Reconcile Flow for `submit_requested`

```
run_reconcile(order_id)
  → loads file
  → sees status == "submit_requested"
  → passes _is_allowed_reconcile_status check
  → skips expiry check (same as submit_uncertain / reconciliation_required)
  → requires existing client_order_id (will exist)
  → queries broker via AlpacaBrokerAdapter.get_order_by_client_order_id
      ├── broker order FOUND
      │     → mark_duplicate_reconciled(broker_order_id, broker_status)
      │     → return ReconcileReport(ok=True, status="duplicate_reconciled")
      └── broker order NOT FOUND
            → mark_reconciliation_required(path, "broker order not found during reconcile")
            → return ReconcileReport(
                  ok=False,
                  status="reconcile_not_found",
                  message="No broker order found. Manual review required before retry.",
              )
```

### Why Mark `reconciliation_required` on Not Found?

- Local state says a submit was requested (via `submit_attempt` entry).
- Broker has no record.
- In Batch 4.7, we **know** the broker was never called, but from the state machine's perspective the intent is recorded.
- Marking `reconciliation_required` forces human review and preserves the audit trail.
- This is consistent with how `submit_uncertain` is handled today.

### Future Batch Consideration

When Batch 4.x eventually calls `broker.place_order()`, a `submit_requested` + broker not found may indicate a network failure between local state write and broker ACK. In that future world, `reconciliation_required` is still the correct outcome. Batch 4.7's behavior is forward-compatible.

---

## 8. Dry-Run Behavior

`run_submit_dry_run()` must remain **strictly read-only**.

### Dry-Run Idempotency Check Expansion

Current dry-run checks:
- `submit_uncertain`, `reconciliation_required` → block

**Batch 4.7 addition:** Also block on `submit_requested`.

```python
if current_status in ("submit_uncertain", "reconciliation_required", "submit_requested"):
    return DryRunReport(
        ok=False,
        status="blocked",
        blocked_reason="reconciliation_required",
        message="Order is in submit_requested state. Run --reconcile first.",
    )
```

### Dry-Run Invariants (Unchanged)

- No `mark_submit_requested()` call.
- No `client_order_id` persistence.
- No status change.
- No `submit_attempts` append.
- Still shows `client_order_id_preview` when applicable (but not for `submit_requested`, since idempotency blocks earlier).

---

## 9. Tests to Plan

### 9.1 Unit Tests — `tests/execution/test_submit_execution.py`

| # | Test Name | Asserts |
|---|-----------|---------|
| 1 | `test_submit_execution_can_submit_false_no_mutation` | `can_submit=false` → no `mark_submit_requested` call, file unchanged, `blocked_reason="can_submit_false"` |
| 2 | `test_submit_execution_mocked_can_submit_true_calls_mark_submit_requested` | Patched `can_submit=True` → `mark_submit_requested` called exactly once with correct args |
| 3 | `test_submit_execution_mocked_can_submit_true_file_moves_to_submit_requested` | File on disk has `status="submit_requested"`, `submit_requested_at` set, `submitted_at=null` |
| 4 | `test_submit_execution_mocked_can_submit_true_appends_status_transition` | Last transition is `{"status": "submit_requested", ...}` |
| 5 | `test_submit_execution_mocked_can_submit_true_appends_submit_attempt` | `submit_attempts[-1]["status"] == "submit_requested"`, UUID4 `attempt_id`, `risk_revalidated=true`, `sync_revalidated=true` |
| 6 | `test_submit_execution_mocked_can_submit_true_submitted_at_remains_null` | `submitted_at` not present or null after mutation |
| 7 | `test_submit_execution_mocked_can_submit_true_broker_place_order_not_called` | `broker.place_order` not called (patch `resolve_execution_broker` or `AlpacaBroker.place_order`) |
| 8 | `test_submit_execution_mocked_can_submit_true_resolve_execution_broker_not_called` | `BrokerResolver.resolve_execution_broker` not called |
| 9 | `test_submit_execution_mocked_can_submit_true_order_router_not_called` | `OrderRouter.route` not called |
| 10 | `test_submit_execution_mocked_can_submit_true_returns_broker_submit_not_implemented` | `blocked_reason="broker_submit_not_implemented"`, message contains "not implemented" |
| 11 | `test_submit_execution_rerun_on_submit_requested_blocks_before_sync` | Pre-seed file to `submit_requested` → blocked at idempotency, no sync, no risk, no mutation |
| 12 | `test_submit_execution_rerun_on_submit_requested_no_second_attempt` | `submit_attempts` length == 1 (from first run) |
| 13 | `test_submit_execution_rerun_on_submit_requested_returns_reconciliation_required` | `blocked_reason="reconciliation_required"`, message mentions `--reconcile` |
| 14 | `test_submit_execution_risk_failure_still_blocks_before_mutation` | Mock risk rejection → `blocked_reason="risk_revalidation_failed"`, `mark_submit_requested` not called |
| 15 | `test_submit_execution_sync_failure_still_blocks_before_mutation` | Mock sync failure → `blocked_reason="live_sync_failed"`, `mark_submit_requested` not called |
| 16 | `test_submit_execution_kill_switch_active_blocks_before_mutation` | Kill switch active → `blocked_reason="kill_switch_active"`, `mark_submit_requested` not called |
| 17 | `test_submit_execution_market_order_blocks_before_mutation` | Market order → `blocked_reason="market_price_unavailable"`, `mark_submit_requested` not called |
| 18 | `test_submit_execution_approval_expired_blocks_before_mutation` | Expired approval → `blocked_reason="approval_expired"`, `mark_submit_requested` not called |
| 19 | `test_submit_execution_live_trading_disabled_blocks_before_mutation` | `enable_live_trading=false` → `blocked_reason="live_trading_disabled"`, `mark_submit_requested` not called |

### 9.2 Unit Tests — `tests/execution/test_submit_reconcile.py`

| # | Test Name | Asserts |
|---|-----------|---------|
| 20 | `test_reconcile_submit_requested_allowed_status` | `run_reconcile` accepts `submit_requested` status (does not return `reconcile_invalid_status`) |
| 21 | `test_reconcile_submit_requested_with_cid_queries_broker` | Uses persisted `client_order_id` in `get_order_by_client_order_id` call |
| 22 | `test_reconcile_submit_requested_broker_found_becomes_duplicate_reconciled` | `mark_duplicate_reconciled` called, returns `ok=True, status="duplicate_reconciled"` |
| 23 | `test_reconcile_submit_requested_broker_not_found_becomes_reconciliation_required` | `mark_reconciliation_required` called, returns `ok=False, status="reconcile_not_found"` |
| 24 | `test_reconcile_submit_requested_no_place_order` | `broker.place_order` not called |
| 25 | `test_reconcile_submit_requested_no_resolve_execution_broker` | `BrokerResolver.resolve_execution_broker` not called |

### 9.3 Unit Tests — `tests/execution/test_submit_dry_run.py` (or inline in test_submit_execution.py)

| # | Test Name | Asserts |
|---|-----------|---------|
| 26 | `test_dry_run_submit_requested_blocks` | `run_submit_dry_run` on `submit_requested` file → `blocked`, `blocked_reason="reconciliation_required"` |
| 27 | `test_dry_run_submit_requested_no_mutation` | File unchanged after dry-run |

### 9.4 CLI Tests — `tests/test_cli.py`

| # | Test Name | Asserts |
|---|-----------|---------|
| 28 | `test_cli_submit_approved_order_can_submit_false_no_mutation` | Default production path → text output shows "can_submit_false", file unchanged |
| 29 | `test_cli_submit_approved_order_mocked_can_submit_true_mutates_file` | Mock `BrokerResolver.resolve_status` to return `can_submit=True` → file on disk shows `submit_requested` |
| 30 | `test_cli_submit_approved_order_mocked_can_submit_true_no_place_order` | `AlpacaBroker.place_order` not called |
| 31 | `test_cli_submit_approved_order_mocked_can_submit_true_output_sanitized` | No API keys, no raw errors in stdout/stderr |
| 32 | `test_cli_submit_approved_order_mocked_can_submit_true_json_parseable` | `--json` output is valid JSON, contains `blocked_reason="broker_submit_not_implemented"` |
| 33 | `test_cli_submit_approved_order_dry_run_unchanged` | `--dry-run` on approved file → same behavior as Batch 4.6 |
| 34 | `test_cli_submit_approved_order_reconcile_unchanged` | `--reconcile` on approved file → same behavior as Batch 4.6 |
| 35 | `test_cli_submit_approved_order_rerun_submit_requested_blocks` | First run (mocked can_submit=true) → submit_requested. Second run → blocks, mentions `--reconcile` |

---

## 10. Files Likely to Change

### Primary Changes

| File | Change |
|------|--------|
| `src/atlas_agent/execution/submit_execution.py` | Add `submit_requested` to idempotency gate; import `mark_submit_requested`; wire mutation after `can_submit=true` check; add `broker_submit_not_implemented` block |
| `src/atlas_agent/execution/submit_reconcile.py` | Add `"submit_requested"` to `_is_allowed_reconcile_status`; ensure broker-not-found path handles `submit_requested` same as `submit_uncertain` |
| `src/atlas_agent/execution/submit_dry_run.py` | Add `"submit_requested"` to idempotency check |
| `tests/execution/test_submit_execution.py` | 19+ new tests (see §9.1) |
| `tests/execution/test_submit_reconcile.py` | 6 new tests (see §9.2) |
| `tests/test_cli.py` | 8 new tests (see §9.4) |

### Optional / Deferred

| File | When |
|------|------|
| `docs/release-checklist.md` | During release hygiene |
| `CHANGELOG.md` | During release hygiene |
| `README.md` | During release hygiene |
| `pyproject.toml` / `__init__.py` | During release hygiene (version bump to 0.5.6.dev5) |

---

## 11. Hard Safety Invariants

After Batch 4.7 implementation and tests pass, the following must remain true:

### Production Runtime Invariants

1. **`BrokerResolver.can_submit` remains `False` for live Alpaca.** No code change to `resolver.py`.
2. **`resolve_execution_broker("live")` returns `execution_broker=None`.** No code change.
3. **No production live submit is possible.** The `can_submit=false` gate blocks before mutation in all real Alpaca configurations.
4. **`broker.place_order` is never called** — not in production, not in mocked tests, not in any code path reachable from `run_submit_execution()`.
5. **`OrderRouter.route` is never called** from submit execution.
6. **`resolve_execution_broker("live")` is never called** from submit execution.

### State Machine Invariants

7. **`submitted_at` stays `null`** in Batch 4.7. Only `submit_requested_at` is set.
8. **`broker_order_id` stays `null`** in Batch 4.7.
9. **No `status = "submitted"`, `"acknowledged"`, or `"failed"`** is ever written by Batch 4.7.
10. **Exactly one `submit_attempt` entry** per successful `mark_submit_requested()` call.
11. **Reruns on `submit_requested` do not create duplicate `submit_attempts`.**

### Data Safety Invariants

12. **No raw secrets or raw broker errors in `SubmitExecutionReport` output.** Messages are static strings.
13. **No live submit docs claim** in README/CHANGELOG (no "live orders now supported" language).
14. **Dry-run remains strictly read-only.**
15. **Paper mode is completely untouched.** No changes to paper broker, paper adapter, or paper execution paths.

### File Protection Invariants

16. **Protected / unwanted untracked files remain untouched:**
    - `AUDIT_ENHANCEMENTS_2026-05-13.md`
    - `BATCH2_PLAN.md`
    - `memory/kill_switch_state.json.lock`

---

## 12. Implementation Sketch

### `run_submit_execution()` — Pseudocode Diff

```python
# --- Idempotency gate (BEFORE approved check) ---
# Add submit_requested to the existing terminal-state checks:
if current_status == "submit_requested":
    return SubmitExecutionReport(
        ok=False, status="blocked", order_id=order_id,
        gates={**gates, "idempotency": "fail"},
        blocked_reason="reconciliation_required",
        message="Order is in submit_requested state. Run --reconcile first.",
    )

# ... existing gates 4–14 unchanged ...

# --- Gate 15: can_submit ---
if not broker_status.can_submit:
    return SubmitExecutionReport(
        ok=False, status="blocked", order_id=order_id,
        gates={**gates, "can_submit": "fail"},
        blocked_reason="can_submit_false",
        message="All safety gates passed, but live submit remains disabled.",
        client_order_id=cid, risk=risk_dict, sync={...}, warnings=warnings,
    )
gates["can_submit"] = "pass"

# --- Gate 16: Mutate to submit_requested (NEW) ---
from atlas_agent.execution.submit_state import mark_submit_requested
mark_submit_requested(
    path,
    order_id=order_id,
    client_order_id=cid,
    actor="submit:cli",
)

# --- Gate 17: Hard block before broker submit (NEW) ---
return SubmitExecutionReport(
    ok=False,
    status="blocked",
    order_id=order_id,
    gates={**gates, "broker_submit": "not_implemented"},
    blocked_reason="broker_submit_not_implemented",
    message="Submit state prepared, but broker submission is not implemented in this release.",
    client_order_id=cid,
    risk=risk_dict,
    sync={"status": "success", "warnings": sync_warnings},
    warnings=warnings,
)
```

### `_is_allowed_reconcile_status()` — One-Line Change

```python
def _is_allowed_reconcile_status(status: str) -> bool:
    return status in (
        "approved", "submit_uncertain", "reconciliation_required",
        "duplicate_reconciled", "submit_requested",  # <-- ADD
    )
```

### `run_submit_dry_run()` — Idempotency Expansion

```python
if current_status in ("submit_uncertain", "reconciliation_required", "submit_requested"):
    # ... existing block ...
```

---

## 13. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Production behavior changes | **None** | High | `can_submit=false` in Alpaca blocks before mutation. No resolver changes. |
| Test mocks leak into production | Low | High | Tests patch `BrokerResolver.resolve_status` return value; production uses real resolver. |
| Orphaned `submit_requested` files in tests | Medium | Low | Tests use `tmp_path`; no persistent state pollution. Reconcile handles `submit_requested`. |
| Reconcile incorrectly treats `submit_requested` as uncertain | Low | Medium | Correct by design: local intent exists, broker status unknown → `reconciliation_required` is the safe default. |
| Secret leak in new error messages | Low | High | All new messages are static strings. No raw values interpolated. |
| Duplicate `submit_attempt` on rerun | Low | High | Idempotency gate blocks reruns before mutation. Tested explicitly. |

---

## 14. Final Recommendation

**Implement Option C.**

Batch 4.7 wires `mark_submit_requested()` into `run_submit_execution()` **only after** the `can_submit=true` check, then immediately blocks with `broker_submit_not_implemented`. This design:

- **Preserves zero production behavior change** (Alpaca `can_submit=False`).
- **Validates the mutation boundary under test** (mocked `can_submit=True`).
- **Prepares the state machine for future broker submission** (`submit_requested` is a real, audited state).
- **Maintains all Batch 4.6 invariants** (no `place_order`, no `submitted_at`, no secrets, dry-run read-only).
- **Adds reconcile support for `submit_requested`** so operators can recover from test- or future-batch-created states.

**Proceed to implementation when approved.**
