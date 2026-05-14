# Batch 4.4 — Approved-Order Reconciliation + Idempotency State Machine

**Status:** Implemented  
**Scope:** Gated off — no live submit enabled  
**Date:** 2026-05-14

## What Changed

### New Modules

- **`src/atlas_agent/execution/submit_state.py`**  
  State-machine helpers for pending order files:
  - `compute_client_order_id()` — deterministic, normalized, max 64 chars
  - `load_pending_order()` — load + validate v2 schema + verify hash
  - `is_submit_blocked_by_state()` — idempotency guard
  - `append_status_transition()`, `mark_reconciliation_required()`, `mark_duplicate_reconciled()` — atomic file mutations
  - `_atomic_write_json()` — temp-file + rename for crash safety

- **`src/atlas_agent/execution/submit_reconcile.py`**  
  Reconcile command implementation:
  - `run_reconcile()` — queries broker read-only, updates local state
  - `ReconcileReport` — structured reconcile result

### Modified Modules

- **`src/atlas_agent/execution/submit_dry_run.py`**  
  - Extended `DryRunReport` with `client_order_id_preview`
  - Added idempotency gates:
    - Blocks `submit_uncertain` and `reconciliation_required` states
    - Blocks orders that already have `client_order_id`
  - Computes `client_order_id_preview` deterministically without persisting it

- **`src/atlas_agent/cli.py`**  
  - Added `--reconcile` flag to `submit-approved-order`
  - `--reconcile` and `--dry-run` are mutually exclusive
  - Non-dry-run, non-reconcile still returns "not implemented"

### New Tests

- `tests/execution/test_submit_state.py` — 23 tests
- `tests/execution/test_submit_reconcile.py` — 16 tests
- Extended `tests/execution/test_submit_approved_order_dry_run.py` — 5 new tests
- Extended `tests/test_cli.py` — 3 new tests

**Total test delta:** +47 tests (1283 → 1330)

## CLI Usage

### Dry-run (unchanged behavior + preview)

```bash
atlas submit-approved-order <order_id> --dry-run
```

Output now includes `client_order_id_preview` when all gates pass.  
Dry-run never mutates pending files, never persists `client_order_id`, never calls the broker.

### Reconcile (new)

```bash
atlas submit-approved-order <order_id> --reconcile
```

Queries the live broker (Alpaca only) via read-only `GET` to check whether an order with the persisted `client_order_id` already exists.

**Requirements before broker query:**
- Pending file must be valid v2 with matching hash
- Status must be `approved`, `submit_uncertain`, or `reconciliation_required`
- `client_order_id` must already be present in the file
- `enable_live_trading` must be `true`
- Alpaca sync provider must be available

**Outcomes:**
- **Found** → updates local file to `duplicate_reconciled`, stores `broker_order_id`
- **Not found** → reports controlled not-found; does not submit; does not mark submitted
- **Transport error** → marks `reconciliation_required` (if eligible); sanitized message
- **Tampered file** → fails closed before any broker contact

## Safety Invariants

| Invariant | Status |
|-----------|--------|
| `BrokerResolver.can_submit = False` for all live brokers | ✅ Preserved |
| `resolve_execution_broker("live").execution_broker = None` | ✅ Preserved |
| No `AlpacaBroker.place_order` from CLI/runtime | ✅ Preserved |
| No `OrderRouter.route` from reconcile or dry-run | ✅ Preserved |
| Dry-run never mutates pending files | ✅ Preserved |
| Reconcile only performs broker-side `GET` | ✅ Enforced |
| Paper mode unchanged | ✅ Preserved |

## Deferred to Future Batches

- Real `broker.place_order` execution
- `can_submit = True` enablement
- Persisting `client_order_id` in real submit path
- Multi-broker reconcile (Binance/CCXT/IBKR)
- Event logging for reconcile
