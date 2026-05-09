# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- **CLI Smoke Tests**: Extensive validation of new commands.

### Changed
- **Provider Neutrality**: Completed removal of hardcoded vendor positioning, ensuring complete neutrality for models and research APIs.

### Security
- Strengthened redaction logic across all audit events, logs, and dashboard outputs to prevent API key leaks.
