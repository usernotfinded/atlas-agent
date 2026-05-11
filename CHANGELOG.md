# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
