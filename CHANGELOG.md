# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Added read-only research timeline command: `atlas research timeline`.
- Added lineage view linking research artifacts to plans, verifications, and evaluations.
- Added tests for filters, broken lineage, unsafe artifacts, and no execution path.
- Updated research workflow demo to include lineage/timeline validation.
- Added tests for timeline demo integration, unsafe timeline output, timeline failure behavior, missing lineage, and pending-order guard.

### Fixed
- Fixed stale v0.5.7.dev7 current-version references after v0.5.7.dev8.
- Sanitized research CLI invalid-symbol and unsupported-provider error output.
- Added regression tests for path/secret-like research CLI error leaks.

### Documentation
- Added post-research-system audit documentation (`docs/audits/post-research-system-audit.md`).
- Recorded validation results, safety boundaries, non-blocking findings, and follow-up areas.

### Safety / Compatibility
- No live-trading behavior changes.

## [0.5.7.dev8] - 2026-05-16

### Added
- Research artifact schema versioning with `schema_version`.
- Legacy artifact compatibility for artifacts without `schema_version`.
- Fail-closed handling for unsupported future research artifact schema versions.
- Read-only research artifact health check command: `atlas research check-artifacts`.
- Health checks for malformed JSON, unsupported schema versions, legacy artifacts, duplicate IDs, symbol mismatches, missing required fields, and unsafe paths.
- End-to-end research demo integration with `check-artifacts`.

### Changed
- Research workflow artifacts are now explicitly versioned.
- Research demo now validates artifact health after run/list/show/plan/verify/evaluate/summary.
- Research command reference now documents schema versioning and artifact health checks.

### Safety / Compatibility
- No live-submit default enablement.
- No broker submit behavior expansion.
- Research workflow remains paper-only and analysis-only.
- `check-artifacts` is read-only and does not migrate, rewrite, delete, or repair artifacts.
- Legacy artifacts are read where safe; unsupported future schema versions fail closed.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in latest validation.
- `pip check` passed.
- `./scripts/demo_paper_workflow.sh` passed.
- `./scripts/demo_research_workflow.sh` passed.
- `./scripts/release_check.sh` passed.
- Protected-staged check passed.

## [0.5.7.dev7] - 2026-05-16

### Added
- Paper-only research evaluation command: `atlas research evaluate PLAN_ID --data PATH`.
- Deterministic evaluation artifacts with local CSV checks and objective metrics.
- Research workflow demo integration covering: run -> list/show -> plan -> verify -> evaluate -> summary.
- Dedicated research workflow command reference: `docs/research-workflow.md`.
- Docs-truth tests for the full paper-only research workflow boundary.

### Changed
- Research workflow documentation now describes the complete local artifact chain: run -> list/show -> plan -> verify -> evaluate -> summary.
- Demo workflow now validates the evaluation step and artifact existence.
- README/architecture docs now link to the dedicated research command reference.

### Safety / Compatibility
- No live-submit default enablement.
- No broker submit behavior expansion.
- Research workflow remains paper-only and analysis-only.
- Research commands do not create approvals or pending orders.
- Evaluation does not generate trading signals, buy/sell recommendations, profit estimates, or live-trading authorization.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in latest validation.
- `pip check` passed.
- `./scripts/demo_paper_workflow.sh` passed.
- `./scripts/demo_research_workflow.sh` passed.
- `./scripts/release_check.sh` passed.
- `scripts/check_no_protected_staged.py` passed.

## [0.5.7.dev6] - 2026-05-16

### Added
- End-to-end research workflow demo script: `scripts/demo_research_workflow.sh`.
- Tests for the research demo script with fake-atlas fixtures (`tests/test_demo_research_workflow_script.py`).
- README and docs mention of the research workflow demo.

### Changed
- Research workflow demo script now creates temp workspace and cleans up safely.

### Safety / Compatibility
- Research workflow remains paper-only and analysis-only.
- Demo script enforces no pending orders, no absolute paths, no secrets in outputs.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Full pytest passed.
- `pip check` passed.
- `./scripts/demo_paper_workflow.sh` passed.
- `./scripts/demo_research_workflow.sh` passed.
- `./scripts/release_check.sh` passed.
- `scripts/check_no_protected_staged.py` passed.

## [0.5.7.dev5] - 2026-05-16

### Added
- Paper plan verification command: `atlas research verify PLAN_ID`.
- Verification artifacts with deterministic local checks.
- Docs-truth coverage requiring verify in the paper-only research workflow.
- Final research workflow docs/index polish.

### Changed
- Research workflow now documents the complete chain: run -> list/show -> plan -> verify -> summary.
- Research docs now describe research artifacts, paper plan artifacts, verification artifacts, and local summary output.

### Safety / Compatibility
- No live-submit default enablement.
- No broker submit behavior expansion.
- Research workflow remains paper-only and analysis-only.
- Research commands do not create approvals or pending orders.
- Verification does not authorize live trading.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Full pytest passed in latest validation.
- `pip check` passed.
- `./scripts/demo_paper_workflow.sh` passed.
- `./scripts/release_check.sh` passed.
- `scripts/check_no_protected_staged.py` passed.

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
