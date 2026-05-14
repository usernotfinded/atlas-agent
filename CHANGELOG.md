# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
