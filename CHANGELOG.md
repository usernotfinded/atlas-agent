# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.7.dev4] - 2026-05-16

### Added
- Workspace hygiene guard for protected staged artifacts.
- Safe quote source boundary for market-order live-submit risk revalidation.
- Quote gate docs-truth tests.
- Paper-only research workflow.
- Research CLI polish and safe JSON/text output.
- Research artifact list/show commands.
- Paper-only research plan command.
- Research workflow docs-truth tests.
- Research summary/index command (`atlas research summary`).
- Paper-only research plan verification command (`atlas research verify PLAN_ID`).
- Verification artifacts with deterministic checks: plan_schema_complete, paper_only_mode, no_live_authorization_language, has_risk_notes, has_invalidation_checks, has_verification_steps, has_paper_only_constraints, source_path_contained.
- Verification event type `research_verification_created` with bounded safe payload.
- Tests for safe output, failed checks, dangerous-language detection, no broker calls, no approvals, and no pending orders.

### Changed
- Market orders remain blocked by default unless a fresh validated quote is explicitly supplied for risk revalidation.
- Research workflow now supports run, list, show, plan, verify, and summary.
- Release workflow now blocks protected staged artifacts.

### Safety / Compatibility
- No live-submit default enablement.
- No broker submit behavior expansion.
- Reconcile remains read-only.
- Research workflow remains paper-only and analysis-only.
- Research commands do not create approvals or pending orders.
- Research verify command does not create approvals, pending orders, or authorize live trading.
- Quote gate is execution-time only, not part of BrokerResolver.can_submit.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Full pytest passed in latest validation.
- `pip check` passed.
- `./scripts/demo_paper_workflow.sh` passed.
- `./scripts/release_check.sh` passed.
- `scripts/check_no_protected_staged.py` passed.

## [0.5.7.dev3] - 2026-05-16

### Added
- Clean-clone release tag smoke script (`scripts/smoke_release_tag.sh`) and tests (`tests/test_smoke_release_tag_script.py`).
- Wheel/sdist package smoke script (`scripts/smoke_package_build.sh`) and tests (`tests/test_smoke_package_build_script.py`).
- Offline package smoke support (`--offline` / `--skip-build-deps-install`) for no-network environments.
- Release candidate audit document (`docs/release-candidate-audit-v0.5.7.dev2.md`) with release gate results, smoke status, safety contracts, and known limitations.
- Release candidate audit document validation tests (`tests/test_release_candidate_audit_docs.py`).
- Architecture/performance hardening:
  - CLI command extraction and shared JSONL helpers.
  - Shared redaction engine (`src/atlas_agent/redaction.py`).
  - Optional SQLite memory index (Markdown remains source of truth).
  - Broker sync parallelization and CSV cache invalidation.
  - Tool contract/runtime split and schema caching.
- Redaction constant single-source cleanup (`src/atlas_agent/audit/redaction.py` imports `SECRET_MARKERS` from shared module).
- **Batch 5.18 — Workspace Hygiene / Generated-Artifact Ignore Guard**:
  - Added `scripts/check_no_protected_staged.py` to fail if protected local/runtime artifacts are staged.
  - Wired protected-staged check into `scripts/release_check.sh`.
  - Added `tests/test_worktree_hygiene.py` covering protected path detection, allowed path pass-through, CLI exit codes, and git-failure handling.

### Changed
- Reconcile remains broker-neutral by lookup capability rather than a concrete Alpaca adapter type.
- Release workflow now includes tag smoke and package smoke scripts.
- `AtlasConfig` uses Pydantic V2 `ConfigDict` instead of class-based `Config`.
- Redaction compatibility wrapper now imports shared `SECRET_MARKERS` from `atlas_agent.redaction`.
- Atlas internals are more modular while preserving the existing CLI entrypoint.
- Hardened `.gitignore` for build, dist, wheel, sdist, Python cache, virtual environment, and local private-note patterns.

### Safety / Compatibility
- No live-submit behavior enabled by default.
- No broker submit behavior changed.
- Reconcile remains read-only.
- No kill-switch, risk, or live-trading gate weakening.
- Markdown memory remains the source of truth; SQLite remains an optional index.
- AuditWriter remains separate for hash-chain/manifest safety.
- No runtime trading behavior changes.
- No broker, submit, reconcile, safety, risk, or config behavior changes.
- **Batch 5.19 — Safe Quote Source for Market-Order Live-Submit Gating**:
  - Added `MarketQuote` dataclass and `QuoteProvider` protocol in `src/atlas_agent/execution/quotes.py`.
  - Added quote validation helper with conservative pricing (ask for buy, bid for sell) and freshness checking.
  - Integrated optional `quote_provider` parameter into `run_submit_execution()`.
  - Market orders remain blocked by default when no `quote_provider` is supplied.
  - Added tests for stale/malformed/mismatched quotes, conservative bid/ask pricing, output safety, and hard-limit interaction.
  - Updated `docs/live-submit-safety-contract.md` with market-order quote validation rules.
- **Batch 5.20 — Quote Gate Docs-Truth Tests**:
  - Added docs-truth tests in `tests/test_live_submit_safety_contract_docs.py` for the market-order safe quote gate.
  - Tests ensure quote validation remains documented as an execution-time gate, not a `can_submit` resolver condition.
  - Tightened safety contract wording for failure modes and default-blocked behavior.
- **Batch 5.21 — Paper-Only Research Workflow**:
  - Added `atlas research run --symbol SYMBOL` command for paper-only, analysis-only research sessions.
  - Creates structured local artifacts at `.atlas/research/<SYMBOL>/<run_id>.json`.
  - Integrates optional memory index lookup with safe output redaction.
  - Emits `research_run_created` events with bounded, safe payloads.
  - Blocks path traversal in symbol arguments.
- **Batch 5.22 — Research Workflow CLI/Docs Polish**:
  - Polished CLI help text and output for `atlas research run`.
  - Added `--provider` flag (default `deterministic`, unsupported providers fail closed).
  - Added `--no-memory` flag to skip memory index lookup.
  - Standardized JSON output envelope with `ok`, `status`, `symbol`, `run_id`, `artifact_path`, `warnings`.
  - Standardized text output with workspace-relative artifact paths and warning counts.
  - Expanded artifact schema with `thesis`, `market_context`, `risks`, `invalidation_conditions`, `paper_only_plan`, `metadata`.
  - Added deterministic research provider (`DeterministicResearchProvider`) that is network-free.
  - Added CLI regression tests for help, JSON/text output, unsupported provider, symbol validation, event safety, artifact schema, and no-execution-path guarantees.
  - Updated `README.md` and `docs/architecture.md` with research workflow documentation.
- **Batch 5.23 — Research Artifact Index/List/Show Commands**:
  - Added `atlas research list` to discover local research artifacts with `--symbol`, `--limit`, and `--json` options.
  - Added `atlas research show RUN_ID` to inspect a single artifact with `--json` option.
  - Added read-only helpers: `iter_research_artifacts`, `load_research_artifact`, `find_research_artifact_by_run_id`, `validate_run_id`.
  - Safe run_id validation (`[A-Za-z0-9_-]{1,80}`) with static errors for unsafe input.
  - Path containment checks: symlinks outside workspace are ignored; absolute paths are never emitted.
  - Malformed JSON artifacts are handled gracefully (skipped in list, safe error in show).
  - Ambiguous run_id detection fails closed.
  - Added 23 CLI regression tests for list/show covering empty state, filtering, limits, malformed files, not-found, invalid run_id, ambiguity, symlink safety, read-only behavior, and no-execution-path guarantees.
  - Fixed a `UnboundLocalError` in `cli.py` where a local variable shadowed the `warnings` module.
- **Batch 5.24 — Research-to-Paper-Plan Workflow**:
  - Added `atlas research plan RUN_ID` to create a deterministic paper-only plan from an existing research artifact.
  - Plan artifacts saved under `.atlas/research/<SYMBOL>/plans/<plan_id>.json` with stable schema.
  - Plan fields: `plan_id`, `source_run_id`, `symbol`, `mode`, `provider`, `source_artifact_path`, `thesis_recap`, `constraints`, `risk_notes`, `invalidation_checks`, `paper_only_actions`, `verification_steps`, `warnings`, `metadata`.
  - Constraints explicitly state: paper-only, does not authorize live trading, does not create pending orders.
  - Emits `research_plan_created` event with bounded safe payload (no full plan body, no research body, no secrets).
  - Unsupported providers fail closed with `unsupported_research_provider`.
  - Added 21 CLI regression tests covering plan creation, JSON/text output, not-found, invalid run_id, ambiguous run_id, malformed source, unsupported provider, event safety, no-execution-path, no pending orders, no broker credentials required, and symlink containment.
- **Batch 5.25 — Research Workflow Docs-Truth Tests**:
  - Added `tests/test_research_workflow_docs.py` with 32 docs-truth tests protecting README.md and docs/architecture.md.
  - Tests verify research command mentions, paper-only wording, forbidden claim absence, workflow progression, execution boundaries, artifact schemas, path/output safety, read-only list/show, and plan paper-only constraints.
  - Expanded docs/architecture.md Research Workflow section with commands, safety boundaries, artifact schemas, and event safety.
  - No runtime behavior changes.

### Validation
- Full pytest passed in the latest validation run.
- `pip check` passed.
- `./scripts/demo_paper_workflow.sh` passed.
- `./scripts/release_check.sh` passed.
- Offline package smoke requires a Python where `python -m build` works.

## [0.5.7.dev2] - 2026-05-15

### Added
- Release-check automation:
  - `scripts/release_check.sh`
  - `scripts/check_version_consistency.py`
  - `scripts/check_forbidden_claims.py`
  - Tests for the release gate.
- Live-submit safety contract documentation (`docs/live-submit-safety-contract.md`).
- Docs-truth tests for the live-submit safety contract (`tests/test_live_submit_safety_contract_docs.py`).
- Audit/output safety regression tests for CLI/JSON/report/audit payloads (`tests/test_output_safety.py`).
- Broker-neutral reconcile capability based on `get_order_by_client_order_id`.
- Pydantic V2 ConfigDict cleanup tests (`tests/config/test_schema.py`).
- Clean-clone release tag smoke script (`scripts/smoke_release_tag.sh`) and tests (`tests/test_smoke_release_tag_script.py`).
- Wheel/sdist package smoke script (`scripts/smoke_package_build.sh`) and tests (`tests/test_smoke_package_build_script.py`).
- Offline package smoke mode (`--offline` / `--skip-build-deps-install`) for no-network environments.
  - Uses an existing build-capable Python (`ATLAS_PACKAGE_SMOKE_BUILD_PYTHON`) instead of installing build dependencies into a fresh build venv.
  - Skips pip upgrade in the install venv.
  - Fails with a clear static message if `python -m build` is unavailable.
- Offline package smoke tests proving no PyPI dependency installation, no pip upgrade, and strict wheel verification.
- Release-candidate audit document (`docs/release-candidate-audit-v0.5.7.dev2.md`) with release gate results, smoke status, safety contracts, and known limitations.
- Release-candidate audit document validation tests (`tests/test_release_candidate_audit_docs.py`).

### Changed
- Reconcile now depends on a read-only lookup capability rather than a concrete Alpaca adapter type.
- `AtlasConfig` now uses Pydantic V2 `ConfigDict` instead of class-based `Config`.

### Safety
- No live-submit behavior enabled by default.
- No broker submit behavior changed.
- No kill-switch, risk, or live-trading gate weakening.
- Reconcile remains read-only and does not call `place_order` or `resolve_execution_broker("live")`.
- Output/audit tests cover unsafe paths, headers, broker bodies, secrets, and raw exception text.

### Tests
- Full pytest suite: 1753 passed.
- `pip check`: passed (release environment).
- `./scripts/demo_paper_workflow.sh`: passed.
- `./scripts/release_check.sh`: all checks passed.
- No Pydantic V2 deprecation warnings emitted.
- `./scripts/smoke_release_tag.sh v0.5.7.dev2`: added for post-tag clean-clone verification. Tested with mocked/no-network tests. Real remote tag smoke is a post-tag verification command.

## [0.5.7.dev1] - 2026-05-14

### Added
- **Batch 5.0 — Production Live-Submit Opt-In Layer**:
  - `broker.enable_live_submit: bool = False` — separate opt-in flag for actual order placement, independent from `broker.enable_live_trading` (which controls sync/read-only).
  - `BrokerResolver._resolve_can_submit()` — multi-factor opt-in gate. `can_submit` becomes `true` ONLY when ALL conditions are satisfied:
    1. `broker.enable_live_submit=true`
    2. `broker.enable_live_trading=true`
    3. Kill switch is normal (not soft_pause/cancel_all/flatten_all/locked_down)
    4. `trading_mode == "live"`
    5. `order_approval_mode != "disabled_live"`
    6. `allow_leverage == false`
    7. Live broker credentials are configured
    8. Valid opt-in audit record exists (`audit/live_submit_opt_in.jsonl`)
  - Deterministic opt-in record validation (`_live_submit_opt_in_status`):
    - Parses `audit/live_submit_opt_in.jsonl` for `event_type="live_submit_opt_in_enabled"`
    - Validates `broker_id` match, `config_fingerprint` match (SHA-256 of provider + limits), parseable `created_at`, no subsequent `opt_out`, and 24-hour expiry.
  - `resolve_execution_broker("live")` now returns a real `AlpacaBroker` **only** when `status.can_submit` is `true`. When `can_submit` is `false`, it returns `execution_broker=None` and never instantiates `AlpacaBroker`.
  - Live-submit hard limits in `run_submit_execution()` (gate 16, evaluated **before** `mark_submit_requested()`):
    - `risk.live_submit_max_order_notional` — notional cap (falls back to `risk.max_order_notional`)
    - `risk.live_submit_allowed_symbols` — symbol allowlist (falls back to `risk.symbol_allowlist`)
    - `risk.live_submit_allowed_sides` — side restriction (e.g. `{"buy"}`)
    - If any limit fails, the pending file remains completely unchanged. No `mark_submit_requested()`, no `resolve_execution_broker()`, no `place_order()`.
  - New audit event types registered: `live_submit_opt_in_enabled`, `live_submit_opt_in_disabled`, `live_submit_opt_in_config_changed`, `live_submit_blocked`, `live_submit_attempted`.
    - `live_submit_opt_in_enabled` and `live_submit_opt_in_disabled` are emitted by the opt-in / opt-out CLI commands.
    - `live_submit_blocked` and `live_submit_attempted` runtime emission from `run_submit_execution()` implemented in Batch 5.1.
- **Batch 5.1 — Live Submit Audit Hardening**:
  - `run_submit_execution()` now accepts an optional `audit_writer` parameter (default `None`).
  - `live_submit_blocked` is emitted when any live-submit safety gate blocks the order, including: `live_trading_disabled`, `kill_switch_active`, `broker_sync_unavailable`, `live_sync_failed`, `market_price_unavailable`, `risk_revalidation_failed`, `live_submit_max_notional_exceeded`, `live_submit_symbol_not_allowed`, `live_submit_side_not_allowed`, `can_submit_false`, `invalid_pending_order`, `submit_state_mutation_failed`, `execution_broker_unavailable`, `execution_broker_invalid`.
  - `live_submit_attempted` is emitted exactly once, immediately before `execution_broker.place_order()`, only when all gates pass.
  - `live_submit_attempted` is **not** emitted when `can_submit=false`, hard limits fail, state mutation fails, broker resolution fails, or the final kill-switch check fails.
  - Audit emission is best-effort: failures are caught silently and never change `SubmitExecutionReport` outcome.
  - Audit payloads contain only safe structured fields (`order_id`, `client_order_id`, `broker_id`, `reason_code`, `gate`, `status`, `mode`). No raw order data, broker responses, exceptions, paths, or secrets.
  - CLI `submit-approved-order` (no flags) now creates an `AuditWriter` and passes it to `run_submit_execution`.
- **Batch 5.2 — Live-Submit Audit and Opt-In Hardening**:
  - `live_submit_blocked` coverage expanded to all previously missed branches:
    - `invalid_pending_order` from initial load/integrity failure (`load_pending_order` raises `InvalidPendingOrderError` or `json.JSONDecodeError`) — gate `integrity`.
    - `invalid_pending_order` from `order_reconstruction` failure (`_reconstruct_order` raises after all earlier gates pass) — gate `order_reconstruction`.
    - `invalid_client_order_id` with `client_order_id=None` in audit payload — gate `client_order_id`.
  - `live_submit_attempted` is emitted exactly once and immediately before `execution_broker.place_order()`; zero `live_submit_attempted` events on all blocked paths.
  - Audit write failure safety: `RuntimeError` during `write_event` does not change `SubmitExecutionReport` outcome.
  - Payload safety tests strengthened to prove audit events never contain: raw order payload, broker response bodies, exception text, stack traces, API keys, APCA headers, file paths, or raw pending payload values.
  - Payload key-set test proves `live_submit_blocked` payloads contain exactly the allowed structured fields (`mode`, `broker_id`, `order_id`, `client_order_id`, `reason_code`, `gate`, `status`).
  - Opt-in CLI output safety: kill-switch unreadable errors print a static sanitized message (`"Kill switch state is unreadable."`) — no exception text, paths, or secrets leak to stdout.
  - Opt-in credential check: `atlas broker opt-in` verifies live broker credentials are configured before writing the opt-in record.
  - Opt-in typed confirmation remains mandatory; `--yes` is rejected and cannot bypass typed confirmation.
  - Missing-credentials test clears `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` from the environment to avoid false negatives from ambient variables.
  - New CLI commands:
    - `atlas broker opt-in` — requires typed confirmation, writes opt-in record to `audit/live_submit_opt_in.jsonl` and audit log.
    - `atlas broker opt-out` — writes opt-out record to invalidate prior opt-in.
  - Config schema additions:
    - `BrokerConfig.enable_live_submit: bool = False`
    - `RiskConfig.live_submit_max_order_notional: float = 0.0`
    - `RiskConfig.live_submit_allowed_symbols: Optional[Set[str]] = None`
    - `RiskConfig.live_submit_allowed_sides: Optional[Set[str]] = None`
    - Legacy field mappings for all new keys.
    - Compatibility properties on `AtlasConfig`.
  - Updated `configs/brokers.example.yaml` and `configs/risk.example.yaml` with new fields.

### Security / Safety
- Default behavior is identical to Batch 4.9: `can_submit=false`, no mutation, no broker contact.
- No production live submit enabled by default. Explicit multi-factor opt-in required.
- Only `run_submit_execution()` is permitted to call `resolve_execution_broker("live")` for live submissions.
- Kill switch still blocks live submit when active.
- No prohibited trading-safety or profit-promise claims added.
- Paper mode untouched.

### Tests
- 12 new resolver tests covering all can_submit conditions and opt-in record validation.
- 8 new submit execution tests for live-submit hard limits (notional, symbol, side), zero-mutation guarantees, and skipped-evaluation when `can_submit=false`.
- 8 new config schema tests for new fields, defaults, legacy mapping, and isolation.
- 7 new CLI tests for opt-in/opt-out commands (prerequisite checks, record writing, confirmation prompts).

### Documentation
- **Batch 5.5 — Live Submit Safety Contract**:
  - Added `docs/live-submit-safety-contract.md`: authoritative documentation covering scope, definitions, default behavior, live-submit conditions, commands, state machine, reconciliation contract, audit contract, output safety contract, forbidden claims, and non-goals.
  - Updated `README.md` to link to the safety contract in the Safety Model section.
  - Updated `docs/release-checklist.md` to require review of the safety contract when broker, submit, reconcile, approval, audit, risk, or kill-switch behavior changes.
  - No runtime behavior changes.

### Tests
- **Batch 5.6 — Docs Truth Tests for Live-Submit Safety Contract**:
  - Added `tests/test_live_submit_safety_contract_docs.py`: automated tests that keep `docs/live-submit-safety-contract.md` aligned with the live-submit safety model.
  - Tests cover: file existence, required sections, can_submit separation from execution-time gates, can_submit overclaim prevention, execution-time gate documentation, reconciliation contract, output safety bounded language, forbidden claims absence, README link presence, and release-checklist mention.
  - No runtime behavior changes.

### Safety
- **Batch 5.7 — Audit/Output Safety Sweep**:
  - Added `tests/test_output_safety.py`: output/audit safety regression tests for CLI, JSON reports, submit/reconcile reports, and live-submit audit payloads.
  - Hardened `_emit_config_error` and `atlas config check --json` to use static messages instead of printing raw exception text.
  - Added broad exception catches to CLI `submit-approved-order` paths (`--reconcile`, `--dry-run`, no flags) with static safe messages to prevent unexpected exception text leakage.
  - No live-trading behavior changes.
- **Batch 5.8 — Broker-Neutral Reconcile Capability**:
  - Replaced `isinstance(sync_provider, AlpacaBrokerAdapter)` in `run_reconcile()` with a capability check (`callable(getattr(provider, "get_order_by_client_order_id", None))`).
  - Reconcile now requires a read-only broker lookup capability, not a specific broker adapter class.
  - Added `tests/execution/test_submit_reconcile.py` tests proving reconcile remains read-only, does not submit, does not resolve execution brokers, and works with non-Alpaca capability providers.
  - No live-submit behavior changes.
- **Batch 5.9 — Pydantic V2 Config Cleanup**:
  - Replaced class-based Pydantic `Config` with `ConfigDict` in `AtlasConfig` to remove `PydanticDeprecatedSince20` warning.
  - Added `tests/config/test_schema.py` tests to verify no deprecation warning, default values, legacy field mappings, and compatibility properties remain intact.
  - No runtime behavior changes.

## [0.5.6.dev7] - 2026-05-14

### Added
- **Batch 4.9 — Wire Broker Submit Boundary Behind Mocked can_submit=true**:
  - `run_submit_execution()` now wires the full broker submission boundary after `can_submit=true`:
    - Reconstructs `Order` from pending payload **before** `mark_submit_requested()` to prevent crash-recovery ambiguity.
    - `mark_submit_requested()` is wrapped in try/except; failure returns `blocked_reason="submit_state_mutation_failed"` with no broker calls.
    - `resolve_execution_broker("live")` → validates execution broker and `place_order` callable.
    - Re-checks kill switch immediately before `place_order`.
    - `broker.place_order(order, client_order_id=...)` called exactly once; never retried.
    - Response mapping:
      - `accepted=True` + valid `order_id` → `mark_acknowledged()` → `ok=True, status="acknowledged"`.
      - `accepted=True` + missing `order_id` → `mark_submit_uncertain("malformed_broker_response")`.
      - `accepted=False` → `mark_submit_failed("broker_rejected_order")` → `blocked_reason="broker_rejected_order"`.
      - `BrokerOperationError("broker rejected order")` → `mark_submit_failed("broker_rejected_order")`.
      - `BrokerOperationError` (timeout/transport/malformed/CID mismatch/unknown) → `mark_submit_uncertain()` → `blocked_reason="reconciliation_required"`.
      - Unexpected exception → `mark_submit_uncertain("unknown")`.
    - All post-broker local state mutations are failure-safe: if `mark_acknowledged`, `mark_submit_failed`, or `mark_submit_uncertain` raises, the code falls back to a static sanitized report with `blocked_reason="reconciliation_required"`. No retry of `place_order`.
  - `_reconstruct_order()` — helper that parses `created_at` ISO string back to datetime before constructing `Order`.
  - `_broker_error_code()` — maps `BrokerOperationError` static messages to safe internal error codes using **exact string matching only** (no substring routing).
  - Report helpers: `_broker_rejected_report()`, `_reconciliation_required_report()`, `_ack_local_write_failed_report()`, `_uncertain_report()` — all return static safe messages.
  - Idempotency gate expanded: `acknowledged` and `submit_prepare_failed` are now blocked before sync/risk.
  - `mark_submit_prepare_failed()` allowlist restricted to pre-broker failures only: `execution_broker_unavailable`, `execution_broker_invalid`, `kill_switch_active`.
  - Added `kill_switch_active` to `_SUBMIT_ATTEMPT_ERROR_CODES` and `_PREPARE_FAILED_ERROR_CODES`.

### Security / Safety
- Production remains completely blocked: `BrokerResolver.can_submit` is still `false` for live Alpaca.
- `resolve_execution_broker("live")` still returns `None` in production.
- `broker.place_order` is only reachable when tests mock `can_submit=True` AND mock `resolve_execution_broker` to return a valid execution broker.
- All report messages are static strings. No `ks_reason` interpolation, no raw broker errors, no HTTP bodies/headers, no exception text, no path values, no order payload values.
- No `enable_live_submit` config added.
- No `resolver.py` production behavior changes.
- Dry-run remains strictly read-only.
- Paper mode untouched.

### Tests
- 38+ new unit tests in `test_submit_execution.py` covering: production safety barriers, mocked acceptance/rejection/uncertainty paths, resolver/kill-switch failure paths, local write failure fallbacks, exact-match broker error codes, missing order_id handling, idempotency gates, leak checks.
- 3 new state tests in `test_submit_state.py` for `mark_submit_prepare_failed` allowlist behavior.
- 6 new CLI tests in `test_cli.py` for production blocking, mocked acceptance/rejection/uncertainty text and JSON output, and leak verification.

## [0.5.6.dev6] - 2026-05-14

### Added
- **Batch 4.8 — Unwired Post-Submit State Mutation Helpers**:
  - `mark_acknowledged()` — atomically transitions a pending order from `submit_requested` to `acknowledged` after broker confirmation. Sets `submitted_at`, `broker_order_id`, and `broker_status`. Updates the last `submit_attempt` entry in-place. Validates `broker_order_id` as a safe non-empty string and `broker_status` against an allowlist. Status transition reason is static (`"broker_acknowledged"`); no raw `broker_order_id` interpolation.
  - `mark_submit_failed()` — atomically transitions from `submit_requested` to `failed` after explicit broker rejection. Keeps `submitted_at=null`. Updates last `submit_attempt` with `status="failed"` and an allowlisted `error_code`.
  - `mark_submit_uncertain()` — atomically transitions from `submit_requested` to `submit_uncertain` for post-broker uncertainty (timeout, 5xx, transport, malformed response, CID mismatch). Keeps `submitted_at=null`. Updates last `submit_attempt` with `status="submit_uncertain"` and an allowlisted `error_code`.
  - `mark_submit_prepare_failed()` — atomically transitions from `submit_requested` to `submit_prepare_failed` for pre-broker local failure (resolver returns None, execution broker invalid). Keeps `submitted_at=null`. Restricts `error_code` to exactly `execution_broker_unavailable` or `execution_broker_invalid`.
  - `_validate_broker_order_id()` — rejects empty/none values and secret-shaped strings (containing `API_KEY`, `SECRET`, `TOKEN`, `PASSWORD`).
  - `_validate_broker_status()` — rejects unknown broker statuses against a safe allowlist.
  - `_update_last_attempt_status()` — shared helper that updates the last `submit_attempt` entry in-place without creating duplicates.
  - Expanded `_SUBMIT_ATTEMPT_STATUSES` to include `"submit_prepare_failed"`.
  - Expanded `_SUBMIT_ATTEMPT_ERROR_CODES` to include `"execution_broker_unavailable"` and `"execution_broker_invalid"`.

### Security / Safety
- Helpers are **unwired** from runtime submit execution. `run_submit_execution()` does not import or call any new helper.
- `BrokerResolver.can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None`.
- No `broker.place_order` path was added.
- `submitted_at` is only set after broker ACK (`acknowledged`). Remains `null` for `failed`, `submit_uncertain`, and `submit_prepare_failed`.
- All validation errors use static safe messages; no raw value leakage.
- No live submit enablement.

## [0.5.6.dev5] - 2026-05-14

### Added
- **Batch 4.7 — Pre-Submit Mutation Wiring Behind Hard-Disabled Gate**:
  - `run_submit_execution()` wires `mark_submit_requested()` into the execution skeleton **only after** the `can_submit=true` gate, then immediately hard-blocks with `broker_submit_not_implemented` before any broker submission.
  - `submit_requested` idempotency gate: reruns on `submit_requested` status block at the idempotency check with `reconciliation_required`, preventing duplicate `submit_attempts` and repeated sync/risk work.
  - Mocked/test `can_submit=true` path atomically writes `submit_requested` state (`status`, `client_order_id`, `submit_requested_at`, status transition, submit attempt) then returns `blocked_reason="broker_submit_not_implemented"`.
  - Production `can_submit=false` path is unchanged: all gates run, then block with `can_submit_false` and zero file mutation.
  - `submit_reconcile.py` accepts `submit_requested` as a valid reconcile status. Broker found → `duplicate_reconciled`; broker not found → `reconciliation_required`.
  - `submit_dry_run.py` blocks on `submit_requested` like `submit_uncertain`/`reconciliation_required`, remaining strictly read-only.

### Security / Safety
- `BrokerResolver.can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None`.
- `broker.place_order` is never called, even in mocked `can_submit=true` tests.
- `OrderRouter.route` is never called from submit execution.
- `submitted_at` and `broker_order_id` remain `null` in Batch 4.7.
- No live submit enablement.
- Dry-run and reconcile behavior remain unchanged for existing statuses.

## [0.5.6.dev4] - 2026-05-14

### Added
- **Batch 4.6 — Submit State Mutation Boundary Helpers**:
  - `build_submit_requested_payload()` — pure helper that returns a deep-copied payload transitioned to `submit_requested` state. Validates `status="approved"`, hash integrity, deterministic `client_order_id`, and existing stored `client_order_id`. Sets `submit_requested_at` while keeping `submitted_at` unchanged/null.
  - `mark_submit_requested()` — atomic file mutation (temp-file + rename) that transitions a pending order to `submit_requested` state with full validation.
  - `append_submit_attempt()` — pure helper that enforces exact allowed keys on submit attempts and validates all fields: UUID4 `attempt_id`, Alpaca-compatible `client_order_id`, enum `status`, ISO `created_at`, allowlisted `actor`, bool `risk_revalidated`/`sync_revalidated`, and allowlisted `error_code`.
  - UUID4 validation for `attempt_id`: canonical UUID4 string check via `uuid.UUID(..., version=4)`.
  - Actor allowlist: `{"submit:cli", "system"}`.
  - Error code allowlist: `{"broker_rejected_order", "broker_unavailable", "broker_transport_failed", "malformed_broker_response", "client_order_id_mismatch", "order_not_found", "unknown"}`.
  - `build_submit_requested_payload` passes its constructed submit attempt through `append_submit_attempt` so all schema/validation rules are enforced by a single code path.
  - Deterministic `client_order_id` validation in `build_submit_requested_payload`: if payload already contains `client_order_id`, it must match `compute_client_order_id(order_id, order_hash)` and the provided `client_order_id`; mismatches raise `SubmitStateError` without silent overwrite.

### Security / Safety
- Helpers are **unwired** from runtime submit execution. `run_submit_execution()` continues to block at `can_submit=false` with zero file mutation.
- `BrokerResolver.can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None`.
- No live submit enablement.
- No raw value leakage: all validation errors use static safe messages.

## [0.5.6.dev3] - 2026-05-14

### Added
- **Batch 4.5 — Gated Submit Execution Skeleton**:
  - `submit-approved-order` no-flag path runs a full execution skeleton through all safety gates before failing closed at `can_submit=false`.
  - Gate order: path traversal guard → pending file validation → terminal-state / idempotency blocks → approved status → expiry check → live-trading enabled → kill-switch normal → `client_order_id` validation → fresh broker sync → sync validation → market-order block → risk revalidation (`mode="live"`) → `can_submit=false` block.
  - Fresh live sync via `BrokerSyncService.sync()` and `validate_live_sync()` on every submit attempt.
  - Risk revalidation via `RiskManager.evaluate_order(..., mode="live")` using the synced `PortfolioSnapshot`.
  - Market orders are blocked with `market_price_unavailable` until a safe quote source is integrated.
  - Missing `client_order_id` is computed deterministically (`compute_client_order_id`) but never persisted to the pending file.
  - No pending file mutation; no `place_order` call; no `resolve_execution_broker("live")` call; no `OrderRouter.route` call.
- **Batch 4.5 Output Safety**: Invalid / path-traversal order ids are masked as `<invalid>` in `SubmitExecutionReport.order_id`, preventing raw user input from leaking to CLI text/JSON output.

### Security / Safety
- `BrokerResolver.can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None`.
- No live submit enablement.

## [0.5.6.dev2] - 2026-05-14

### Added
- **Batch 4.4 — Approved-Order Reconciliation + Idempotency State Machine**:
  - `submit-approved-order --dry-run` extended with deterministic `client_order_id_preview` and idempotency gates. Blocks `submit_uncertain` and `reconciliation_required` states; blocks orders with existing `client_order_id`.
  - `submit-approved-order --reconcile` queries the broker read-only via `AlpacaBrokerAdapter.get_order_by_client_order_id`. Found orders update local state to `duplicate_reconciled`; not-found orders return controlled results without submitting.
  - `src/atlas_agent/execution/submit_state.py` — deterministic `client_order_id` generator, atomic file writes, and state-machine helpers (`mark_reconciliation_required`, `mark_duplicate_reconciled`).
  - `src/atlas_agent/execution/submit_reconcile.py` — `run_reconcile()` with full error sanitization, no raw value leakage, and short-circuit for already-reconciled orders.
- **Alpaca Submit Adapter Hardening (Batch 4.3)**: `AlpacaBroker.place_order` requires `client_order_id`, validates input, sanitizes HTTP errors, and validates status against an allowlist. `AlpacaBrokerAdapter.get_order_by_client_order_id` performs read-only broker queries with full malformed-response sanitization.
- **Dry-Run + Reconcile CLI Coverage**: End-to-end CLI tests prove `--dry-run` never mutates files or persists `client_order_id`; `--reconcile` never calls `place_order`, `resolve_execution_broker("live")`, or `OrderRouter.route`.

### Security / Safety
- **No live submit enabled**: `BrokerResolver.can_submit` remains `false` for all live brokers. `resolve_execution_broker("live")` returns `None`.
- **Reconcile is read-only**: Uses `GET` only. Does not compute `client_order_id` when missing. Requires `enable_live_trading=true` before broker contact.
- **Atomic file writes**: All pending order mutations use temp-file + rename for crash safety.

## [0.5.6.dev1] - 2026-05-14

### Added
- **Execution/Approval Bypass Guard Tests**: Regression tests prove `run_once --mode live` analysis-only path never reaches `_broker_for_mode`, `OrderRouter.route`, `ApprovalManager`, `resolve_execution_broker("live")`, or `broker.place_order`. No pending order files are created.
- **Open Orders in Live Risk Evaluation**: Tests verify `RiskManager.evaluate_order` receives a `PortfolioSnapshot` containing synced `open_orders` (as `PendingOrder` list) so projected exposure includes pending baseline.

### Fixed
- `RiskManager.evaluate_order` audit writer compatibility in `run_once` live path: passes `audit_writer=None` to avoid `AuditLogger`/`AuditWriter` interface mismatch.

## [0.5.6.dev0] - 2026-05-14

### Added
- **Alpaca Read-Only Live Sync**: `AlpacaBrokerAdapter` provides HTTP GET-only synchronization for account state, positions, open orders, and balances. Requires `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`.
- **Live Agent Analysis-Only Mode**: When `TRADING_MODE=live` and `ENABLE_LIVE_TRADING=true`, the agent consumes live Alpaca portfolio snapshots for risk-aware analysis without order submission.
- **`live_analysis_only` Deferred Execution**: Live `propose_order` tool calls that pass risk checks return `live_analysis_only` and do not create pending orders, approval requests, or broker submissions.
- **`run_once --mode live` Analysis-Only Path**: `run_once` now supports live analysis with real broker sync, risk evaluation against synced portfolio (including open orders), and returns `live_analysis_only` without order submission, pending orders, or approval artifacts.
- **Shared Live Sync Validation Helper**: `validate_live_sync()` in `brokers/live_sync_validation.py` extracts the live sync critical-check logic used by both `AgentLoop` and `run_once`, preventing duplication.
- **Structured `broker_errors` Diagnostics**: `BrokerSyncResult` carries typed `broker_errors` with strict fail-closed validation. Malformed diagnostics reject the sync.
- **Noncritical Sync Warning Surfacing**: Balances-only sync failure proceeds with safe diagnostic warnings; critical failures (account, positions, open_orders) fail closed.
- **Auto-Mode `effective_mode` Consistency**: `mode="auto"` resolves to `"live"` or `"paper"` and propagates correctly through AgentLoop, risk manager, and model prompts.

### Changed
- `BrokerResolver` live Alpaca: `can_sync=true` when credentials are present; `can_submit=false` for all live brokers.
- `resolve_execution_broker("live")` returns `None`.
- Docs truth alignment: `live-trading.md`, `brokers.md`, `pending-orders.md`, `architecture.md`, `safety.md` updated to distinguish Alpaca read-only sync (available) from live submit and other broker sync (deferred).

### Documentation
- Added docs-truth tests enforcing accurate live-sync state descriptions.
- Clarified that live analysis-only mode does not create pending order files.

## [0.5.5] - 2026-05-13

### Fixed
- Hardened credential handling and audit safety paths used during setup and runtime checks.
- Corrected runtime provider/config consistency paths used by diagnostics and dashboard summaries.
- Enforced fail-closed behavior for invalid Atlas config loading and schema validation in normal runtime/CLI paths.
- Strengthened approval and input validation paths, including approval ID checks and private `.env` value handling.
- Ensured agent runtime system prompts include the configured discipline profile after discipline gating succeeds.
- Corrected readiness audit flag lookup to use `config.audit` fields for raw prompt/provider text logging checks.
- Fixed backtest portfolio snapshot position-model wiring so snapshots with existing positions do not crash.
- Stabilized `atlas validate --json` and `atlas config check --json` envelope behavior and strict/non-strict exit-code contracts.

### Changed
- Dashboard provider summary now reflects configured/resolved Atlas provider metadata instead of `AI_PROVIDER` environment fallback.
- Demo/proof layer now uses a reproducible paper workflow script (`scripts/demo_paper_workflow.sh`) and updated docs aligned with paper-only safety posture.

### Documentation
- Updated demo and release-facing docs to keep broker-neutral supervised-workspace positioning, paper workflow emphasis, and live-trading-disabled-by-default guidance.
- Clarified that no demo GIF is currently checked in (`assets/atlas-demo.gif` is not present).

## [0.5.4] - 2026-05-12

### Fixed
- Fixed setup model-selection state so stale models from a previous provider cannot appear under a newly selected provider.
- Enforced provider-scoped text model catalogs for hosted providers.
- Rejected invalid hosted provider/model pairs such as OpenAI with Claude models or Anthropic with GPT models.
- Ensured setup, CLI model listing, and selected-state rendering display exact raw model IDs without prettified labels.

### Changed
- Hosted providers now use curated text-only model catalogs.
- Freeform-compatible providers such as OpenRouter, LM Studio, local/self-hosted, OpenAI-compatible, custom endpoints, and NVIDIA local continue to allow exact custom model IDs.

## [0.5.3] - 2026-05-12

### Added
- Added `atlas setup` guided workspace setup flow.
- Added end-to-end setup path for provider, model, auth, discipline profile, symbol, and readiness validation.
- Added guided setup handling for LM Studio, OpenAI-compatible endpoints, and unified Google Gemini modes.

### Changed
- First-run setup now guides users toward a ready paper-mode workspace instead of requiring multiple disconnected commands.
- Google Gemini setup now remains a single provider with mode/auth sub-selection.
- Setup now forces safe defaults: paper mode and live trading disabled.

### Fixed
- Reduced onboarding failure loops caused by missing discipline profile, missing symbol, or incomplete provider configuration.
- Preserved read-only `atlas validate` behavior while reusing diagnostics at the end of guided setup.

## [0.5.2] - 2026-05-12

### Fixed
- Restored tracked readiness diagnostics package used by `atlas validate`.
- Kept `atlas validate` and `atlas validate --json` strictly read-only.
- Reconciled provider catalog/runtime schema for LM Studio, OpenAI-compatible endpoints, OpenRouter metadata headers, Anthropic, Gemini, and hidden legacy/internal providers.
- Ensured setup wizard hides `local_command` and `null` while keeping LM Studio and OpenAI-compatible providers user-facing.

## [0.5.1] - 2026-05-11

### Fixed
- Removed normal runtime fallback to `NullProvider`; agentic workflows now fail closed when no AI provider is configured.
- Kept `NullProvider` available only for explicit internal/test usage.
- Kept `local_command` hidden from normal provider selection as a legacy compatibility option.
- Aligned LM Studio and OpenAI-compatible endpoints as first-class local/custom provider choices.


## [0.5.0] - 2026-05-11

### Added
- **Mandatory Discipline Profile**: Agentic workflows now require an explicit user discipline profile. `atlas discipline setup` must be completed before paper or live trading routines can run.
- **Explicit Symbol Configuration**: Trading symbol is now strictly user-configured. No runtime default symbol is assumed; users must set `market.symbol` via `atlas config set market.symbol <SYMBOL>`.
- **Provider-Specific API Key Handling**: Improved per-provider credential management with clearer `.env.atlas` variable names and validation.
- **Reference Price Requirement**: Risk-gated market orders now require a reference price to pass deterministic checks.
- **Raw Prompt / Provider Audit Logging**: Optional opt-in logging of raw prompts and provider responses for debugging, disabled by default to protect privacy.
- **Demo Documentation**: Added reproducible walkthroughs for paper workflow, risk rejection, and audit verification.

### Changed
- **Workspace Positioning**: Repositioned Atlas Agent as a broker-neutral supervised trading workspace, emphasizing user choice of model, broker, and risk limits.
- **Configuration Architecture**: Consolidated on TOML + `.env.atlas` dual-layer configuration for non-secret and secret settings respectively.

### Security / Safety
- Hardened live trading gates: live mode fails safely unless explicit configuration, credentials, risk checks, and approval are all present.
- Strengthened kill-switch and approval queue integration.
- Removed all hardcoded BTC-USD assumptions from runtime logic.

### CI / Docs
- Fixed GitHub Actions workflow generator to include `atlas init`, `atlas discipline setup`, and `atlas config set market.symbol DEMO-SYMBOL` before every generated paper routine.
- Updated all documentation to v0.5.0 current-status references while preserving historical changelog entries.

## [0.4.0] - 2026-05-10

### Added
- **Backtesting Foundation**: Implemented a deterministic, local-first backtesting engine with historical CSV data loading, execution simulation, and full integration with RiskManager and Audit logs.
- **Backtest CLI**: Added `atlas backtest run --data path/to/data.csv --symbol SYMBOL` command.
- **Documentation Audit**: Repository-wide documentation update for v0.4.0 consistency, including new safety and architecture details.
- **Runtime Hygiene**: Hardened `.gitignore` to ensure runtime artifacts in `.atlas/backtests/` and `.atlas/config.json` are not tracked.

### Changed
- **CLI Contract**: Standardized backtest and broker commands for consistency and safety.
- **Audit Hash-Chain**: Expanded audit event types to include backtesting lifecycle events.

## [0.3.0] - 2026-05-09

### Added
- **Tool-Driven Agent Loop**: Transitioned from routine-centric execution to a fully autonomous tool-driven reasoning cycle.
- **Audit Hardening V2**: Added run-level audit manifests and root hash verification to prevent tail deletion and ensure tamper-evident logs.
- **Portfolio Risk Manager**: Introduced deterministic risk gates evaluating position size, single trade limits, daily loss limits, and symbol policies before any execution.
- **Pending Orders Risk V3**: Upgraded exposure projection to automatically calculate the "worst reasonable" outcome of all open and pending orders combined.
- **Advanced Kill Switch**: Integrated an emergency state machine (normal, soft_pause, cancel_all, flatten_all, locked_down) with dead-man heartbeat protection.
- **Safety Action Planner & Executor**: Automated generation and protected execution of emergency cancellation and flattening action plans, fully integrated with audit and risk gates.
- **Broker Sync Layer**: Added provider-neutral normalization of account state, positions, and open orders directly into the risk engine.
- **Local Dashboard**: Created a minimal, read-only HTML dashboard for safe, zero-secret visibility into system status, audit health, and risk metrics.
- **Backtesting Foundation**: Implemented a deterministic, local-first backtesting engine with historical CSV data loading, execution simulation, and full integration with RiskManager and Audit logs.
- **CLI Smoke Tests**: Extensive validation of new commands.

### Changed
- **Provider Neutrality**: Completed removal of hardcoded vendor positioning, ensuring complete neutrality for models and research APIs.

### Security
- Strengthened redaction logic across all audit events, logs, and dashboard outputs to prevent API key leaks.
