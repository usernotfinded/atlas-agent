# Release Checklist

Run this before pushing a public GitHub release.

## Required Validation Commands

- `./scripts/release_check.sh` (preferred: runs pytest, pip check, demo workflow, version consistency, and forbidden-claims scan)
- `python3.11 -m pytest -q`
- `python3.11 -m pip check`
- `./scripts/demo_paper_workflow.sh`
- `./scripts/demo_research_workflow.sh` (optional: validates the complete paper-only research chain including evaluation)
- `python3.11 scripts/check_version_consistency.py`
- `python3.11 scripts/check_forbidden_claims.py`
- `python3.11 scripts/check_no_protected_staged.py`
- `python3.11 -c "import atlas_agent; print(getattr(atlas_agent, '__version__', 'no __version__'))"`
- `python3.11 -m pytest tests/research -q`
- `python3.11 -m pytest tests/test_research_workflow_docs.py -q`

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
- No release docs include return guarantees, prohibited safety claims, autonomous income claims, live-readiness overstatements, or broker-preference marketing language.
- Do not reference a demo GIF as present unless `assets/atlas-demo.gif` actually exists.
- Confirm no private values or credential-like strings are committed in docs or scripts.
- Verify `pyproject.toml` `project.version` matches `src/atlas_agent/__init__.py` `__version__`.
- Verify `git status` does not include runtime files like `memory/`.
- Verify `./scripts/check_no_protected_staged.py` passes (no protected local artifacts staged):
  - `AUDIT_ENHANCEMENTS_2026-05-13.md`
  - `BATCH2_PLAN.md`
  - `memory/`
  - `build/`
  - `dist/`
  - `*.egg-info/`
- Verify `./scripts/check_forbidden_claims.py` passes.
- If broker, submit, reconcile, approval, audit, risk, or kill-switch behavior changed, review `docs/live-submit-safety-contract.md` for accuracy and update it if necessary.

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
- `--reconcile` uses the sync provider's `get_order_by_client_order_id` capability (read-only GET), not a concrete adapter type.
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

## Broker Foundation 5.0 Release Assertions

- `broker.enable_live_submit` defaults to `False` and is independent from `broker.enable_live_trading`.
- With default settings (`enable_live_submit=false`), behavior is identical to Batch 4.9: `can_submit=false`, no mutation, no broker contact.
- `can_submit` becomes `true` only when ALL required conditions are satisfied: `enable_live_submit=true`, `enable_live_trading=true`, kill switch normal, `trading_mode=live`, approval not disabled, leverage off, credentials present, valid opt-in audit record.
- `resolve_execution_broker("live")` returns a real `AlpacaBroker` **only** when `status.can_submit` is `true`.
- `resolve_execution_broker("live")` returns `execution_broker=None` when `can_submit` is `false`, and never instantiates `AlpacaBroker`.
- Live-submit hard limits (`live_submit_max_order_notional`, `live_submit_allowed_symbols`, `live_submit_allowed_sides`) are evaluated **before** `mark_submit_requested()`.
- If any live-submit hard limit fails, the pending file remains completely unchanged. No `mark_submit_requested()`, no `resolve_execution_broker()`, no `place_order()`.
- When `can_submit=false`, live-submit hard limits are skipped entirely; the function blocks at `can_submit=false` with zero mutation.
- Only `run_submit_execution()` is permitted to call `resolve_execution_broker("live")` for live submissions.
- Opt-in record is stored in `audit/live_submit_opt_in.jsonl` with deterministic validation: event type match, broker ID match, config fingerprint match, parseable timestamp, no subsequent opt-out, and 24-hour expiry.
- `atlas broker opt-in` requires typed confirmation, valid prerequisites, and writes the opt-in record.
- `atlas broker opt-out` writes an opt-out record that invalidates prior opt-ins.
- Dry-run remains strictly read-only.
- Reconcile remains read-only and never calls `place_order`.
- Paper mode remains unchanged.
- No profit claims, prohibited safety claims, or live-readiness overstatements exist in README or CHANGELOG.

## Broker Foundation 5.1 Release Assertions

- `run_submit_execution()` accepts an optional `audit_writer` parameter defaulting to `None`.
- `live_submit_blocked` is emitted for every live-submit gate failure: `live_trading_disabled`, `kill_switch_active` (both checks), `broker_sync_unavailable`, `live_sync_failed`, `market_price_unavailable`, `risk_revalidation_failed`, `live_submit_max_notional_exceeded`, `live_submit_symbol_not_allowed`, `live_submit_side_not_allowed`, `can_submit_false`, `invalid_pending_order`, `invalid_client_order_id`, `submit_state_mutation_failed`, `execution_broker_unavailable`, `execution_broker_invalid`.
- `live_submit_attempted` is emitted exactly once, immediately before `execution_broker.place_order()`, only when all gates pass.
- `live_submit_attempted` is **not** emitted when `can_submit=false`, hard limits fail, state mutation fails, broker resolution fails, or the final kill-switch check fails.
- Audit emission is best-effort: write failures are caught silently and never change `SubmitExecutionReport` outcome.
- Audit payloads contain only safe structured fields (`order_id`, `client_order_id`, `broker_id`, `reason_code`, `gate`, `status`, `mode`). No raw order data, broker responses, exceptions, paths, or secrets.
- CLI `submit-approved-order` (no flags) passes an `AuditWriter` to `run_submit_execution`.
- Existing callers of `run_submit_execution()` without `audit_writer` continue to work unchanged.
- Dry-run does not emit `live_submit_attempted`.
- Reconcile does not emit `live_submit_attempted`.
- Paper mode remains unchanged.

## Broker Foundation 5.2 Release Assertions

- `live_submit_blocked` is emitted for `invalid_pending_order` from initial load/integrity failure (gate `integrity`).
- `live_submit_blocked` is emitted for `invalid_pending_order` from `order_reconstruction` failure (gate `order_reconstruction`).
- `live_submit_blocked` is emitted for `invalid_client_order_id` with `client_order_id=None` in the audit payload (gate `client_order_id`).
- `live_submit_attempted` is emitted exactly once and immediately before `execution_broker.place_order()`.
- Zero `live_submit_attempted` events are emitted on any blocked path.
- Audit writer failure does not alter `SubmitExecutionReport` outcome.
- `atlas broker opt-in` typed confirmation cannot be bypassed by `--yes`.
- Kill-switch unreadable opt-in output is a static sanitized message; no exception text, paths, or secrets leak to CLI output.
- Missing live broker credentials block opt-in before any opt-in record is written.
- Protected untracked files (`AUDIT_ENHANCEMENTS_2026-05-13.md`, `BATCH2_PLAN.md`, `memory/kill_switch_state.json.lock`) must not be staged.

## Package Artifact Verification

Before publishing artifacts or tagging a release candidate, verify the package builds and installs from wheel in a clean environment:

```bash
./scripts/smoke_package_build.sh
```

This installs from the built wheel (not editable source) and runs a paper-only workspace smoke.

Optional flags:
- `--skip-sdist` to skip the source distribution check
- `--keep-artifacts` to preserve the temporary build directory
- `--offline` (or `--skip-build-deps-install`) to skip installing build dependencies from PyPI. Use this in offline/no-network environments where `python -m build` already works. Offline mode skips pip/build dependency installation and does not upgrade pip, but still builds the wheel with the selected build Python and installs the locally built wheel into a fresh venv.

## Post-Tag Verification

After pushing a tag, verify it from a clean clone:

```bash
./scripts/smoke_release_tag.sh v0.5.7.dev5
```

Optional full mode (also runs `release_check.sh` inside the clean clone):

```bash
./scripts/smoke_release_tag.sh v0.5.7.dev5 --full
```

## Tagging

After all validations pass and the commit is ready:

```bash
git add pyproject.toml src/atlas_agent/__init__.py CHANGELOG.md README.md docs/
git commit -m "Bump version to v0.5.7.dev5"
git push origin main
git tag -a v0.5.7.dev5 -m "Atlas Agent v0.5.7.dev5"
git push origin v0.5.7.dev5
```

Only create the tag after:
- tests pass
- `./scripts/release_check.sh` passes
- the version-bump commit is created
- `main` is pushed or ready to push

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
