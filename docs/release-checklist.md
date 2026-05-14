# Release Checklist

Run this before pushing a public GitHub release.

## Required Validation Commands

- `python3.11 -m pytest -q`
- `python3.11 -m pip check`
- `./scripts/demo_paper_workflow.sh`
- `python3.11 -c "import atlas_agent; print(getattr(atlas_agent, '__version__', 'no __version__'))"`

## Validate Contract Checks

- `atlas validate`
Expectation: human-readable readiness report; command remains read-only.
- `atlas validate --json`
Expectation: one parseable JSON envelope on stdout; no mixed human text; non-strict readiness failures still exit `0`.
- `atlas validate --strict`
Expectation: read-only; exits non-zero (`2`) when readiness checks fail.
- `atlas validate --json --strict`
Expectation: same stable JSON envelope shape as non-strict JSON mode; exits non-zero (`2`) when readiness checks fail.
- Serious config/load/internal failures in any validate mode remain non-zero.

## Release Hygiene Assertions

- Positioning remains broker-neutral supervised workspace, not autonomous trading.
- Demo flow is paper-only and reproducible via `./scripts/demo_paper_workflow.sh`.
- Live trading remains disabled by default unless explicitly enabled by the user.
- No release docs include return guarantees, zero-risk language, autonomous income claims, live-readiness overstatements, or broker-preference marketing language.
- Do not reference a demo GIF as present unless `assets/atlas-demo.gif` actually exists.
- Confirm no private values or credential-like strings are committed in docs or scripts.

## Broker Foundation 3.x Release Assertions

- `can_submit=false` for all live brokers (`BrokerResolver` live status never enables submit).
- `resolve_execution_broker("live")` returns `None` (no live execution broker resolved).
- Live `propose_order` creates no `pending_orders/` files and does not invoke `ApprovalManager`.
- `run_once --mode live` performs broker sync and risk evaluation but does not submit orders, create pending orders, or invoke `ApprovalManager`.
- `run_once --mode live` returns `status="live_analysis_only"` when risk passes; never returns `filled` or `pending_approval`.
- `run_once --mode live` does not instantiate `OrderRouter` or call `OrderRouter.route`.
- `run_once --mode live` does not create files in `pending_orders/`.
- `run_once --mode live` does not call `broker.place_order` on any broker.
- `run_once --mode live` does not call `resolve_execution_broker("live")`.
- `run_once --mode live` requires `enable_live_trading=true`; returns controlled rejection without sync if disabled.
- Synced open orders influence `run_once` live risk evaluation via `PortfolioSnapshot`.
- Alpaca read-only sync is GET-only; `AlpacaBrokerAdapter` implements `BrokerProvider`, not `Broker`, and has no order submission methods.
- Non-Alpaca broker sync (Binance, CCXT, IBKR) remains deferred.
- Docs do not claim production-ready live trading or recommend any specific broker.

## Broker Foundation 4.4 Release Assertions

- `submit-approved-order` without `--dry-run` or `--reconcile` runs the gated execution skeleton and fails controlled at `can_submit=false`.
- `--dry-run` never mutates pending files.
- `--dry-run` never persists `client_order_id`.
- `--dry-run` never calls broker GET reconciliation (`get_order_by_client_order_id`).
- `--dry-run` never calls `place_order`.
- `--reconcile` never calls `place_order`.
- `--reconcile` never calls `resolve_execution_broker("live")`.
- `--reconcile` never calls `OrderRouter.route`.
- `--reconcile` requires existing `client_order_id` in the pending file.
- `--reconcile` does not compute `client_order_id` when missing (returns `reconcile_not_available`).
- `--reconcile` requires `enable_live_trading=true` before broker query.
- `--reconcile` uses `AlpacaBrokerAdapter.get_order_by_client_order_id` only (read-only GET).
- `BrokerResolver.can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None`.
- No claims that live trading is ready for unattended deployment or without risk in release docs or README.

## Broker Foundation 4.5 Release Assertions

- `submit-approved-order` no-flag path runs the full execution skeleton (`run_submit_execution`).
- Execution skeleton performs all safety gates in order: path traversal → file integrity → terminal states → approved → expiry → live trading enabled → kill switch normal → `client_order_id` validation → fresh broker sync → sync validation → market order block → risk revalidation → `can_submit=false` block.
- Fresh live sync (`BrokerSyncService.sync()`) happens on every no-flag submit attempt.
- Risk revalidation (`RiskManager.evaluate_order(..., mode="live")`) uses the synced `PortfolioSnapshot`.
- Market orders are blocked with `market_price_unavailable`; no market order reaches `can_submit` or `place_order`.
- No pending file mutation in the execution skeleton.
- Missing `client_order_id` is computed deterministically but never persisted.
- Existing `client_order_id` in pending file is validated but not modified.
- Invalid / path-traversal order ids are masked as `<invalid>` in report output; raw user input never leaks to text, JSON, or diagnostics.
- `BrokerResolver.can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None`.
- No live submit enablement.
- `--dry-run` and `--reconcile` behavior remain unchanged.

## Broker Foundation 4.6 Release Assertions

- `submit_state.py` contains pure helper functions `build_submit_requested_payload()`, `mark_submit_requested()`, and `append_submit_attempt()`.
- `build_submit_requested_payload()` validates `status="approved"`, hash integrity, deterministic `client_order_id`, and existing stored `client_order_id` before constructing the mutation.
- `append_submit_attempt()` enforces exact allowed keys and validates: UUID4 `attempt_id`, Alpaca-compatible `client_order_id`, enum `status`, ISO `created_at`, allowlisted `actor`, bool `risk_revalidated`/`sync_revalidated`, and allowlisted `error_code`.
- `build_submit_requested_payload()` passes its constructed submit attempt through `append_submit_attempt()` so all schema/validation rules are enforced by a single code path.
- `attempt_id` must be a canonical UUID4 string (`uuid.UUID(..., version=4)` check).
- `actor` allowlist is exactly `{"submit:cli", "system"}`.
- `error_code` allowlist is exactly `{"broker_rejected_order", "broker_unavailable", "broker_transport_failed", "malformed_broker_response", "client_order_id_mismatch", "order_not_found", "unknown"}`.
- Existing `client_order_id` in payload is validated against `compute_client_order_id(order_id, order_hash)`. Mismatched values raise `SubmitStateError`; no silent overwrite occurs.
- All validation errors use static safe messages; no raw values (client_order_id, secrets, payload fields) leak in exception text.
- Helpers are **unwired** from runtime submit execution: `run_submit_execution()` does not call `mark_submit_requested()` or any helper.
- No CLI flag exposes the helpers (`--prepare-submit-state` does not exist).
- `submit-approved-order` no-flag continues to block at `can_submit=false` with zero file mutation.
- `BrokerResolver.can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None`.
- No live submit enablement.
- `--dry-run` and `--reconcile` behavior remain unchanged.
- Paper mode remains unchanged.

## Broker Foundation 4.8 Release Assertions

- `submit_state.py` contains unwired post-submit state mutation helpers: `mark_acknowledged()`, `mark_submit_failed()`, `mark_submit_uncertain()`, and `mark_submit_prepare_failed()`.
- `submit_execution.py` is unchanged from the Batch 4.8 perspective (helpers were unwired at that time).
- `cli.py` is unchanged from the Batch 4.8 perspective.
- `BrokerResolver` is unchanged from the Batch 4.8 perspective.
- `can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None` in production.
- `--dry-run` behavior remains unchanged.
- `--reconcile` behavior remains unchanged.
- Paper mode remains unchanged.
- `submitted_at` is set **only** by `mark_acknowledged()` after broker ACK.
- `submitted_at` remains `null` for `failed`, `submit_uncertain`, and `submit_prepare_failed`.
- `broker_order_id` is validated as a safe non-empty string; secret-shaped values are rejected without leaking.
- `broker_status` is validated against a safe allowlist.
- Status transition reasons are static strings; no raw `broker_order_id` or broker error text is interpolated.
- `mark_submit_prepare_failed()` restricts `error_code` to exactly `execution_broker_unavailable`, `execution_broker_invalid`, or `kill_switch_active`.
- All validation errors use static safe messages; no raw values leak in exception text.

## Broker Foundation 4.9 Release Assertions

- `can_submit` remains `false` for all live brokers (`BrokerResolver` live status never enables submit).
- Production `can_submit=false` path blocks before mutation and before any broker contact.
- Production `can_submit=false` path does not call `resolve_execution_broker("live")`.
- Production `can_submit=false` path does not call `broker.place_order`.
- Mocked/test `can_submit=true` path reconstructs the Order from the pending payload before `mark_submit_requested()`.
- `mark_submit_requested()` must succeed before `resolve_execution_broker` or `place_order` is called.
- Final kill-switch check happens immediately before `place_order`.
- Exactly one `place_order` call per mocked submit attempt; no retry on failure or timeout.
- Accepted broker result (`accepted=True` + valid `order_id`) → `mark_acknowledged()` → sets `submitted_at` and `broker_order_id`.
- Rejected broker result (`accepted=False` or `BrokerOperationError("broker rejected order")`) → `mark_submit_failed()` → `submitted_at` remains `null`.
- Uncertain broker outcomes (timeout, transport, malformed response, CID mismatch, unexpected exception) → `mark_submit_uncertain()` → `submitted_at` remains `null`.
- Prepare failures (resolver returns None, invalid broker, kill switch active after `mark_submit_requested`) → `mark_submit_prepare_failed()` → `submitted_at` remains `null`.
- Post-broker local write failure (e.g. `mark_acknowledged` raises) does not retry `place_order`; returns static sanitized report with `reconciliation_required`.
- Report messages are static strings; no raw broker errors, HTTP bodies, headers, exception text, path values, or order payload values leak.
- `failed` status is explicitly blocked at the idempotency gate before sync/risk/mutation.
- Dry-run remains strictly read-only.
- Reconcile remains read-only and never calls `place_order`.
- Paper mode remains unchanged.
- No production live submit is enabled.
- No production-ready live trading claim exists in README or CHANGELOG.

## Broker Foundation 4.7 Release Assertions

- Production `can_submit=false` path does not call `mark_submit_requested()`.
- Production `can_submit=false` path does not mutate pending files.
- Mocked `can_submit=true` path may write `submit_requested` state via `mark_submit_requested()`.
- Mocked `can_submit=true` path immediately blocks with `blocked_reason="broker_submit_not_implemented"` (Batch 4.7 behavior; superseded by Batch 4.9).
- Mocked `can_submit=true` path does not call `resolve_execution_broker("live")` (Batch 4.7 behavior; superseded by Batch 4.9).
- Mocked `can_submit=true` path does not call `broker.place_order` / `AlpacaBroker.place_order` (Batch 4.7 behavior; superseded by Batch 4.9).
- Mocked `can_submit=true` path does not call `OrderRouter.route`.
- `submit_requested` rerun blocks with `reconciliation_required` at the idempotency gate.
- `submit_requested` rerun does not append duplicate `submit_attempts`.
- Reconcile supports `submit_requested` status (found → `duplicate_reconciled`; not found → `reconciliation_required`).
- Dry-run remains read-only and blocks on `submit_requested`.
- `submitted_at` remains `null` after Batch 4.7.
- `broker_order_id` remains `null` after Batch 4.7.
- No production-ready live trading claim exists in README or CHANGELOG.
