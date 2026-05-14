# Broker Foundation Batch 4.6: Submit State Mutation Boundary (Plan)

**Status:** Planning only — no runtime wiring.  
**Goal:** Define and implement the safe local state transition that happens immediately before `broker.place_order`, while keeping real live submit disabled.  
**Constraint:** Must NOT call `broker.place_order`, must NOT enable `can_submit`, must NOT expose `resolve_execution_broker("live")`.

---

## 1. Executive Summary

Batch 4.5 built the execution skeleton: all gates (valid pending order, hash integrity, status==approved, non-expired approval, live trading enabled, kill switch normal, client_order_id computed, fresh live sync, risk revalidation) pass, and then execution blocks at `can_submit=false` with **zero file mutation**.

Batch 4.6 answers: *"What exact mutation would we perform if `can_submit` were true, and how do we make that mutation safe, atomic, testable, and recoverable?"*

The answer is to implement **pure helper functions** that construct and perform the mutation, but keep them **unwired from the CLI execution path** until a future batch actually enables broker submission. This gives us:
- A tested, auditable state-transition primitive ready for Batch 4.7/4.8.
- No risk of accidental live submit because the helpers are not invoked by `run_submit_execution`.
- A clear crash-recovery contract documented before any broker call exists.

---

## 2. Core Recommendation

**Do NOT persist `submit_requested` while `can_submit=false`.**

Persisting a submit-state transition when no submit can actually occur would create a lying local state ("I requested a submit" when nothing was requested). Instead:

1. Implement **pure, test-only mutation helpers** in `submit_state.py`.
2. Add **unit tests** that exercise these helpers against temporary files.
3. Leave `run_submit_execution` **unchanged** — it continues to block at `can_submit=false` with zero mutation.
4. Do **not** add a `--prepare-submit-state` CLI flag yet. Defer until Batch 4.7 when there is an actual broker call to prepare for.

---

## 3. State Mutation Boundary Design

### 3.1 Gate Sequence (unchanged from 4.5)

```
1. valid pending order id          -> path traversal check
2. pending file exists             -> file system check
3. valid schema + hash             -> load_pending_order (integrity)
4. status == "approved"            -> explicit check
5. idempotency / terminal state    -> is_submit_blocked_by_state
6. not expired                     -> _check_expiry
7. live_trading_enabled=true       -> config check
8. kill_switch normal              -> _check_kill_switch
9. client_order_id valid/computed  -> _validate_client_order_id / compute_client_order_id
10. live sync passes               -> BrokerSyncService.sync + validate_live_sync
11. risk revalidation passes       -> RiskManager.evaluate_order (mode="live")
12. can_submit check               -> broker_status.can_submit
```

### 3.2 When Mutation Should Happen (in a future batch)

In Batch 4.7+, the mutation must happen **between gate 11 (risk revalidation passes) and gate 12 (can_submit)** — or more precisely, **immediately after gate 12 passes and immediately before the broker call**.

The exact sequence in a future wired batch will be:

```
... gates 1-11 pass ...
gate 12: can_submit == true   -> continue
MUTATION A: persist client_order_id (if not already persisted)
MUTATION B: append submit_attempt with status="submit_requested"
MUTATION C: atomically write status="submit_requested" + submit_requested_at (submitted_at remains null)
BROKER CALL: broker.place_order (with client_order_id)
POST-CALL:   update submit_attempt → "acknowledged" or "failed"
```

**Why mutate BEFORE the broker call?**
- Crash recovery: if the process dies after the broker call is sent but before local acknowledgment, the pending file already contains `client_order_id` and `submit_attempts`, enabling `--reconcile` to query the broker by idempotency key.
- Idempotency: the broker receives the same `client_order_id` that is already persisted, preventing duplicate orders on retry.

**Why NOT mutate in Batch 4.6?**
- `can_submit` is false. There is no broker call. Mutating would create a `submit_requested` state with no corresponding broker action.
- Reconciliation logic would be confused: "I see `submit_requested`, let me query the broker" → broker returns 404 → user thinks something went wrong when in fact nothing was ever sent.

### 3.3 Pure Helper Approach for 4.6

Instead of wiring mutation into the CLI, implement these as standalone functions with full test coverage:

| Helper | Purpose |
|--------|---------|
| `build_submit_requested_payload(payload, order_id, client_order_id, now, actor, attempt_id)` | Returns a **new dict** representing the mutated payload, without modifying input. |
| `mark_submit_requested(path, order_id, client_order_id, actor="submit:cli", attempt_id=None)` | Atomically reads, validates, mutates, and writes the pending file. |
| `append_submit_attempt(payload, attempt)` | Returns a **new dict** with the attempt appended to `submit_attempts`. |

These helpers are "shovel-ready" for 4.7 but inert in production today.

---

## 4. Submit Attempts Schema

### 4.1 Entry Structure

```json
{
  "attempt_id": "uuid4-string",
  "client_order_id": "atlas-abc123-deadbeef",
  "status": "prepared",
  "created_at": "2026-05-14T16:39:14+00:00",
  "actor": "submit:cli",
  "risk_revalidated": true,
  "sync_revalidated": true,
  "broker_order_id": null,
  "error_code": null
}
```

### 4.2 Status Enum

| Status | Meaning |
|--------|---------|
| `prepared` | Mutation helper built the payload; not yet persisted (test-only) |
| `submit_requested` | Local state transitioned to submit_requested; broker call not yet sent |
| `acknowledged` | Broker accepted the order; `broker_order_id` populated |
| `failed` | Broker explicitly rejected (4xx, definite error); `error_code` populated |
| `submit_uncertain` | Broker response unknown (timeout, network loss, inconclusive) |

### 4.3 Safety Rules

- `attempt_id` must be a UUID4 (random but not secret; used only for local tracing).
- `actor` must be allowlisted: `submit:cli` or `system`.
- `error_code` must be an explicit allowlisted enum value, never a raw HTTP status, never a broker error body, never a stack trace.
- Allowed `error_code` values: `null`, `broker_rejected_order`, `broker_unavailable`, `broker_transport_failed`, `malformed_broker_response`, `client_order_id_mismatch`, `order_not_found`, `unknown`.
- No secrets, no raw broker responses, no HTTP bodies.

---

## 5. Crash Recovery Model

Since Batch 4.6 has no broker call, we focus on the **pre-broker crash points** and define how future batches should handle post-broker crashes.

### 5.1 Crash Points and Recovery

| # | Crash Point | Local State on Disk | Recovery Behavior |
|---|-------------|---------------------|-------------------|
| 1 | After `client_order_id` persisted but before `submit_attempt` appended | `client_order_id` set, no attempt record | Reconcile queries broker by `client_order_id`. If found → reconcile. If 404 → human may retry (reuses same cid). |
| 2 | After `submit_attempt` appended with `submit_requested` but before broker call | `status=submit_requested`, attempt present | Same as #1. The `submit_requested` state signals "intended to submit but uncertain if broker received it." Reconcile is required. |
| 3 | After broker call sent but before local acknowledged write | `status=submit_requested` (or possibly `submit_uncertain` if partial write occurred) | **Future batch:** Reconcile by `client_order_id`. If broker has it → update to `submitted`. If 404 → depends on idempotency window; safest is `submit_uncertain` until human confirms. |
| 4 | After broker accepted but local write failed | Broker has order; local file may be stale or unchanged | **Future batch:** Reconcile finds broker order → update local state, populate `broker_order_id`, mark `submitted`. |
| 5 | After timeout/unknown broker response | `submit_attempt` may have `status=submit_uncertain` | Human must run `--reconcile`. Query by `client_order_id`. If found → reconcile. If 404 → human may explicitly retry. If inconclusive → block, require human investigation. No blind retry. |

### 5.2 Recovery Invariant

> **No state is unrecoverable.** Every persisted `client_order_id` can be queried via broker GET by client_order_id. Every `submit_attempt` entry records enough metadata to reconstruct the human decision context. No blind retry is ever performed automatically.

---

## 6. Idempotency Semantics

### 6.1 `client_order_id` Requirements (already satisfied by 4.5)

- **Deterministic:** `compute_client_order_id(order_id, order_hash)` always returns the same value for the same inputs.
- **Stable across retries:** Once persisted, the same `client_order_id` is reused on all retries and reconciliation queries.
- **Alpaca-compatible:** Alpaca allows `A-Za-z0-9_-` up to 64 chars. Current format `atlas-{safe_prefix}-{hash_prefix}` = max 38 chars.
- **Never random:** No UUIDs, no timestamps, no nonces.
- **Never based on symbol/qty/side:** Changing the order quantity or side (which would change `order_hash`) changes the id, but the id does not embed human-readable trade parameters.

### 6.2 Existing `client_order_id` Handling

| Scenario | Behavior |
|----------|----------|
| `client_order_id` is `null` | Compute from `order_id` + `order_hash`. Persist on mutation. |
| `client_order_id` already set, valid | Reuse as-is. Do not recompute. |
| `client_order_id` already set, invalid | Block immediately with `blocked_reason="invalid_client_order_id"`. Do not mutate. Require human fix or recreation. |
| `client_order_id` set but does NOT match `compute_client_order_id(order_id, order_hash)` | **Block.** This indicates tampering or a bug. The stored cid must be either null or exactly equal to the deterministic computation. |

### 6.3 Validation Rule to Add in 4.6 Helper

```python
def _validate_existing_client_order_id(payload: dict, order_id: str) -> None:
    existing = payload.get("client_order_id")
    expected = compute_client_order_id(order_id, payload["order_hash"])
    if existing is not None and existing != expected:
        raise SubmitStateError("client_order_id mismatch")
```

This prevents a class of tampering where an attacker injects a different `client_order_id` to collide with another order.

---

## 7. Atomic Mutation Helpers (Implementation Plan)

### 7.1 Proposed APIs in `submit_state.py`

```python
def build_submit_requested_payload(
    payload: dict[str, Any],
    client_order_id: str,
    now: datetime,
    actor: str = "submit:cli",
) -> dict[str, Any]:
    """Return a NEW dict representing the pending order after a submit-requested transition.

    Does NOT modify the input payload. Pure function suitable for testing.
    """


def append_submit_attempt(
    payload: dict[str, Any],
    attempt: dict[str, Any],
) -> dict[str, Any]:
    """Return a NEW dict with the attempt appended to submit_attempts.

    Does NOT modify the input payload. Pure function.
    """


def mark_submit_requested(
    path: Path,
    client_order_id: str,
    actor: str = "submit:cli",
) -> Path:
    """Atomically transition the pending order to submit_requested state.

    Preconditions (fail-closed):
      - File must exist and be valid v2 schema.
      - status must be "approved".
      - Hash must match.
      - client_order_id must be valid and match deterministic computation.

    Side effects:
      - Sets payload["status"] = "submit_requested"
      - Sets payload["client_order_id"] = client_order_id
      - Sets payload["submit_requested_at"] = now.isoformat()
      - Keeps payload["submitted_at"] unchanged/null
      - Appends status_transition entry
      - Appends submit_attempt entry with status="submit_requested"

    Returns the path to the updated file.
    """
```

### 7.2 Implementation Details

**`build_submit_requested_payload`:**
1. Deep-copy input payload (or construct new dict from it).
2. Validate `client_order_id` with `_validate_client_order_id`.
3. Set `status = "submit_requested"`.
4. Set `client_order_id`.
5. Set `submit_requested_at = now.isoformat()`.
6. Keep `submitted_at` unchanged/null.
6. Append to `status_transitions`: `{"status": "submit_requested", "at": now.isoformat(), "actor": actor}`.
7. Build submit_attempt entry and append to `submit_attempts`.
8. Return the new dict.

**`append_submit_attempt`:**
1. Deep-copy input payload.
2. Append attempt to `submit_attempts` list.
3. Return new dict.

**`mark_submit_requested`:**
1. `load_pending_order(path)` — validates schema + hash.
2. Check `payload["status"] == "approved"`. If not, raise `SubmitStateError("status must be approved")`.
3. Validate `client_order_id` matches deterministic computation for the stored `order_id` and `order_hash`.
4. Call `build_submit_requested_payload`.
5. Call `_atomic_write_json(path, new_payload)`.
6. Return path.

### 7.3 Why `submit_requested_at` Instead of `submitted_at`

Batch 4.6 does not set `submitted_at`. The helper sets `submit_requested_at` to record the local state boundary, while `submitted_at` remains `null` until broker acknowledgment in a future batch. This preserves semantic clarity: `submitted_at` should mean "broker accepted the order," not "local system decided to submit."

---

## 8. CLI Behavior

### 8.1 No Changes to `run_submit_execution`

The execution skeleton in `submit_execution.py` must remain **unchanged** for Batch 4.6. Specifically:

- It still blocks at `can_submit=false`.
- It still returns `blocked_reason="can_submit_false"`.
- It still does **not** call `mark_submit_requested` or any mutation helper.
- It still does **not** persist `client_order_id`.
- It still does **not** append to `submit_attempts`.

### 8.2 No New CLI Flags

Do **not** add `--prepare-submit-state` or any user-facing flag in this batch. The helpers are dev/test-only primitives. A future batch (4.7) will wire them when `can_submit` is enabled.

### 8.3 Dry-Run and Reconcile Unchanged

- `submit-approved-order --dry-run` continues to compute `client_order_id_preview` without persisting.
- `submit-approved-order --reconcile` continues to require an existing persisted `client_order_id` (which currently only exists if manually injected or created by a future batch).

---

## 9. Safety Invariants (Must Hold After 4.6)

| # | Invariant | Verification |
|---|-----------|------------|
| 1 | `BrokerResolver.can_submit` remains `False` for all live brokers | Static code review of `resolver.py` |
| 2 | `resolve_execution_broker("live")` returns `None` | Static code review of `resolver.py` |
| 3 | `broker.place_order` is never called from CLI/runtime | Existing tests in `test_submit_execution.py` |
| 4 | `OrderRouter.route` is never called from submit path | Existing tests in `test_submit_execution.py` |
| 5 | No production live submit claim exists in docs/messages | Code review of strings |
| 6 | `dry-run` behavior unchanged | Existing dry-run tests pass |
| 7 | `reconcile` behavior unchanged | Existing reconcile tests pass |
| 8 | Paper mode completely untouched | Paper broker tests pass |
| 9 | No secrets/raw values in any output | Existing leak tests pass |
| 10 | `run_submit_execution` performs zero file mutation | Existing mutation tests pass |
| 11 | `AUDIT_ENHANCEMENTS_2026-05-13.md` untouched | Git diff check |
| 12 | `BATCH2_PLAN.md` untouched | Git diff check |
| 13 | `memory/kill_switch_state.json.lock` untouched | Git diff check |

---

## 10. Test Plan

### 10.1 New Tests in `tests/execution/test_submit_state.py`

```
test_build_submit_requested_payload_sets_client_order_id
  - Input: valid v2 payload, deterministic client_order_id from order_id + order_hash
  - Assert: output["client_order_id"] equals deterministic client_order_id
  - Assert: output["status"] == "submit_requested"
  - Assert: output["submit_requested_at"] is not None
  - Assert: output.get("submitted_at") is None

test_build_submit_requested_payload_appends_submit_attempt
  - Assert: len(output["submit_attempts"]) == 1
  - Assert: output["submit_attempts"][0]["status"] == "submit_requested"
  - Assert: output["submit_attempts"][0]["client_order_id"] == cid
  - Assert: output["submit_attempts"][0]["risk_revalidated"] is True
  - Assert: output["submit_attempts"][0]["sync_revalidated"] is True

test_build_submit_requested_payload_does_not_mutate_input
  - Assert: input payload remains "approved" with no submit_attempts

test_build_submit_requested_payload_reuses_existing_client_order_id
  - Input payload already has matching client_order_id
  - Assert: output preserves it, does not overwrite with different value

test_build_submit_requested_payload_rejects_mismatched_existing_cid
  - Input payload has client_order_id that does not match deterministic computation
  - Assert: raises SubmitStateError

test_append_submit_attempt_returns_new_dict
  - Assert: input dict is unchanged
  - Assert: output has one more attempt

test_mark_submit_requested_atomic_write
  - Write valid approved payload to tmp file
  - Call mark_submit_requested
  - Assert: file now has status="submit_requested", client_order_id set, one attempt

test_mark_submit_requested_preserves_original_on_write_failure
  - Patch Path.write_text to raise OSError after temp creation
  - Assert: original file unchanged (atomic write invariant)

test_mark_submit_requested_rejects_invalid_status
  - File has status="submitted"
  - Assert: raises SubmitStateError

test_mark_submit_requested_rejects_tampered_hash
  - File has tampered order_hash
  - Assert: raises InvalidPendingOrderError (via load_pending_order)

test_mark_submit_requested_rejects_invalid_existing_client_order_id
  - File has client_order_id="../../etc/passwd"
  - Assert: raises SubmitStateError
```

### 10.2 New Tests in `tests/execution/test_submit_execution.py`

```
test_no_cli_submit_execution_mutation_while_can_submit_false
  - Run run_submit_execution with all gates mocked to pass
  - Assert: file on disk is unchanged (status still "approved", no submit_attempts)

test_no_place_order_called
  - Already exists; keep passing.

test_no_resolve_execution_broker_called
  - Already exists; keep passing.

test_execution_skeleton_returns_correct_cid_preview_when_computed
  - When client_order_id is null, report.client_order_id equals deterministic value
  - File remains null
```

### 10.3 Test Infrastructure Helpers

Add a shared helper in `test_submit_state.py`:

```python
def _make_submit_attempt(
    client_order_id: str,
    status: str = "submit_requested",
    risk_revalidated: bool = True,
    sync_revalidated: bool = True,
) -> dict[str, Any]:
    return {
        "attempt_id": str(uuid.uuid4()),
        "client_order_id": client_order_id,
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": risk_revalidated,
        "sync_revalidated": sync_revalidated,
        "broker_order_id": None,
        "error_code": None,
    }
```

---

## 11. Files to Change

| File | Change Type | Description |
|------|-------------|-------------|
| `src/atlas_agent/execution/submit_state.py` | Add functions | `build_submit_requested_payload`, `append_submit_attempt`, `mark_submit_requested`, `_validate_existing_client_order_id` |
| `tests/execution/test_submit_state.py` | Add tests | All tests listed in §10.1 |
| `tests/execution/test_submit_execution.py` | Add tests | Tests listed in §10.2 |
| `docs/batch-4.6-plan.md` | Create | This document |

**Files that must NOT change:**
- `src/atlas_agent/execution/submit_execution.py` (no wiring)
- `src/atlas_agent/cli.py` (no new flags)
- `src/atlas_agent/brokers/resolver.py` (can_submit stays false)
- `src/atlas_agent/brokers/alpaca.py` (no place_order exposure)
- `AUDIT_ENHANCEMENTS_2026-05-13.md`
- `BATCH2_PLAN.md`
- `memory/kill_switch_state.json.lock`

---

## 12. Exact Helper API Signatures

```python
# In src/atlas_agent/execution/submit_state.py

def build_submit_requested_payload(
    payload: dict[str, Any],
    *,
    order_id: str,
    client_order_id: str,
    now: datetime,
    actor: str = "submit:cli",
    attempt_id: str | None = None,
) -> dict[str, Any]:
    ...


def append_submit_attempt(
    payload: dict[str, Any],
    attempt: dict[str, Any],
) -> dict[str, Any]:
    ...


def mark_submit_requested(
    path: Path,
    *,
    order_id: str,
    client_order_id: str,
    actor: str = "submit:cli",
    now: datetime | None = None,
    attempt_id: str | None = None,
) -> Path:
    ...
```

### 12.1 `build_submit_requested_payload` Implementation Sketch

```python
def build_submit_requested_payload(
    payload: dict[str, Any],
    *,
    order_id: str,
    client_order_id: str,
    now: datetime,
    actor: str = "submit:cli",
    attempt_id: str | None = None,
) -> dict[str, Any]:
    _validate_client_order_id(client_order_id)
    _validate_submit_actor(actor)
    expected_cid = compute_client_order_id(order_id, payload["order_hash"])
    if client_order_id != expected_cid:
        raise SubmitStateError("client_order_id does not match deterministic computation")

    new_payload = copy.deepcopy(payload)
    new_payload["status"] = "submit_requested"
    new_payload["client_order_id"] = client_order_id
    new_payload["submit_requested_at"] = now.isoformat()
    # submitted_at remains unchanged/null in Batch 4.6

    transition = {
        "status": "submit_requested",
        "at": now.isoformat(),
        "actor": actor,
    }
    new_payload["status_transitions"] = list(new_payload.get("status_transitions", []))
    new_payload["status_transitions"].append(transition)

    attempt = {
        "attempt_id": attempt_id or str(uuid.uuid4()),
        "client_order_id": client_order_id,
        "status": "submit_requested",
        "created_at": now.isoformat(),
        "actor": actor,
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }
    return append_submit_attempt(new_payload, attempt)
```

*Note:* `build_submit_requested_payload` must pass the constructed attempt through `append_submit_attempt` so the submit-attempt schema, UUID4 validation, actor allowlist, and error-code allowlist are enforced by one path.

### 12.2 `mark_submit_requested` Implementation Sketch

```python
def mark_submit_requested(
    path: Path,
    client_order_id: str,
    actor: str = "submit:cli",
) -> Path:
    payload = load_pending_order(path)

    if payload.get("status") != "approved":
        raise SubmitStateError("status must be approved")

    # Validate stored cid matches deterministic computation
    order_id = payload["order"]["id"]
    expected_cid = compute_client_order_id(order_id, payload["order_hash"])
    existing_cid = payload.get("client_order_id")
    if existing_cid is not None and existing_cid != expected_cid:
        raise SubmitStateError("client_order_id mismatch")

    # If null, use the provided one; if set, it must equal the provided one
    if existing_cid is not None and existing_cid != client_order_id:
        raise SubmitStateError("client_order_id mismatch")

    now = datetime.now(UTC)
    new_payload = build_submit_requested_payload(
        payload,
        order_id=order_id,
        client_order_id=client_order_id,
        now=now,
        actor=actor,
    )
    _atomic_write_json(path, new_payload)
    return path
```

---

## 13. Rollback Risk

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Helper accidentally called from production path | Low | No wiring in `submit_execution.py` or `cli.py`. Code review enforces this. |
| Test helper leaks into runtime via import chain | Very Low | Helpers are in `submit_state.py` which is already imported; no new imports needed. Static analysis confirms no new call sites. |
| `build_submit_requested_payload` mutates input due to shallow copy bug | Medium | Test `test_build_submit_requested_payload_does_not_mutate_input` catches this. |
| Schema drift if v3 pending order introduced later | Low | Helpers operate on dicts; future schema migration can wrap these functions. |
| Developer confusion about whether mutation is live | Low | This plan document and comments explicitly state "unwired, test-only." |

**Rollback procedure:** If anything goes wrong, revert the two changed files (`submit_state.py` and test files). No runtime behavior changes, so rollback is trivial.

---

## 14. Final Recommendation

**Proceed with the helper-only implementation.**

Batch 4.6 should:
1. Implement `build_submit_requested_payload`, `append_submit_attempt`, and `mark_submit_requested` in `submit_state.py`.
2. Add the full test suite (§10) to lock in behavior.
3. Leave `run_submit_execution`, `cli.py`, and `BrokerResolver` completely untouched.
4. Produce this plan document as the design artifact.

This creates a **tested, atomic, recoverable state-transition primitive** that is ready to be wired in Batch 4.7 (the actual broker call batch) without any redesign or surprise. The boundary between "safe to mutate local state" and "safe to call broker" is now explicitly defined, tested, and documented.

**Sign-off checklist before merging:**
- [ ] All new tests pass (`pytest tests/execution/test_submit_state.py tests/execution/test_submit_execution.py`)
- [ ] Full suite passes (`pytest`)
- [ ] `atlas validate` passes
- [ ] `atlas config set market.symbol AAPL && atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL` passes
- [ ] `atlas run --mode paper` unchanged
- [ ] `atlas run --mode live` fails safely (as before)
- [ ] No changes to `resolver.py` (can_submit still false)
- [ ] No changes to `submit_execution.py` (no wired mutation)
- [ ] No changes to `cli.py` (no new flags)
- [ ] Git diff shows only expected files changed
