# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
