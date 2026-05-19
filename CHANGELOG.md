# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.7.dev24] - 2026-05-18

### Added
- Provider Execution Audit Packet (`src/atlas_agent/research/provider_execution_audit_packet.py`).
  - Consolidates the full research/provider-preflight chain into a single auditable artifact.
  - 10 mandatory-false boolean flags: 6 from state + `trading_signal_generated`, `approval_created`, `pending_order_created`, `broker_touched`.
  - SHA-256 hashing with excluded fields, lineage validation, forbidden-fragment scanning.
  - `build_provider_execution_audit_packet_dict()`, `create_provider_execution_audit_packet()`, `safe_validate_provider_execution_audit_packet_data()`, `validate_provider_execution_audit_packet_artifact()`, `replay_provider_execution_audit_packet()`, `iter_provider_execution_audit_packet_artifacts()`.
- CLI commands:
  - `atlas research provider-execution-audit STATE_ID`
  - `atlas research provider-execution-audit-list`
  - `atlas research provider-execution-audit-show ID`
  - `atlas research provider-execution-audit-validate ID [--strict]`
  - `atlas research provider-execution-audit-replay ID [--strict]`
- Session integration: `check-artifacts`, `timeline`, and `dossier` now support provider execution audit packet artifacts.
- Timeline nesting: audit packets are indexed by `source_provider_execution_state_id` and nested under each state entry.
- Demo workflow extended with audit packet creation, validation, replay, and timeline lineage checks.

### Fixed
- Demo script `provider-execution-audit-validate` and `provider-execution-audit-replay` checks now correctly compare against `"True"` (Python boolean string) instead of `"true"`.

## [0.5.7.dev23] - 2026-05-19

### Added
- Provider Execution Opt-In State Machine Skeleton (`src/atlas_agent/research/provider_execution_state.py`).
  - Four states: `disabled`, `dry_run_only`, `manual_unlock_required`, `provider_call_allowed_but_not_implemented`.
  - Deterministic local-only transition evaluator (`evaluate_provider_execution_state_transition`).
  - All 6 safety booleans hardcoded to `False` in every state, including `provider_call_allowed_but_not_implemented`.
  - SHA-256 hashing, lineage validation, forbidden-fragment scanning, impossible-boolean detection.
- CLI commands:
  - `atlas research provider-execution-state DRY_RUN_ID --to STATE`
  - `atlas research provider-execution-state-list`
  - `atlas research provider-execution-state-show ID`
  - `atlas research provider-execution-state-validate ID [--strict]`
  - `atlas research provider-execution-state-replay ID [--strict]`
- Session integration: `check-artifacts`, `timeline`, and `dossier` now support provider execution state artifacts.
- Demo workflow extended with state transition chain and timeline lineage validation.

### Fixed
- Removed `choices=...` from `--to` argument in `provider-execution-state` to prevent argparse from leaking raw invalid values.
- Invalid state names now fail safely with static `invalid_provider_execution_state_name` envelope; no forbidden fragments leaked.

### Safety / Compatibility
- No provider calls, no API keys, no network requests, no provider SDK imports.
- No trading signals generated. No live trading authorization created.
- Even `provider_call_allowed_but_not_implemented` does not allow real provider calls.
- All configless invariants preserved.

## [0.5.7.dev22] - 2026-05-18

### Fixed
- `atlas research provider-execution-replay` now returns a consistent replay envelope when the source provider call plan has drifted.
  - Non-strict mode: exit code 0, `ok=true`, `match=false`.
  - Strict mode: exit code 2, `ok=true`, `match=false`.
  - Previously returned a generic error envelope (`ok=false`) with `provider_execution_dry_run_source_hash_mismatch`.
- `replay_provider_execution_dry_run()` skips source hash validation during load so it can detect drift and report it as a replay result.
- Replay JSON output now includes `warnings` array.

### Safety / Compatibility
- No provider calls, no API keys, no network requests.
- All configless invariants preserved.
- Tampered artifacts (impossible booleans, forbidden fragments, unsafe lineage) still fail safely with generic error envelopes.

## [0.5.7.dev21] - 2026-05-18

### Added
- `src/atlas_agent/research/provider_execution_dry_run.py`: local, auditable provider execution dry-run artifacts.
- `provider_execution_dry_run_sha256()` with centralized `PROVIDER_EXECUTION_DRY_RUN_HASH_EXCLUDED_FIELDS`.
- 6 boolean safety flags: `provider_enabled=false`, `network_enabled=false`, `credentials_loaded=false`, `provider_call_allowed=false`, `would_call_provider=false`, `actual_provider_call_made=false`.
- Impossible boolean combination detection (e.g. `actual_provider_call_made=true` when `provider_call_allowed=false`).
- `atlas research provider-execution-dry-run PLAN_ID`: create dry-run artifact from provider call plan.
- `atlas research provider-execution-list`: list dry-run artifacts with safe sentinels for tampered items.
- `atlas research provider-execution-show ID`: show one dry-run artifact (fail-closed on tamper).
- `atlas research provider-execution-validate ID`: validate dry-run artifact with 15+ checks.
- `atlas research provider-execution-replay ID`: replay and compare deterministic hashes.
- Provider execution dry-run lineage linked in timeline (nested under provider_call_plans) and dossier.
- `check-artifacts` now counts and validates provider execution dry-run artifacts (hash, lineage, impossible booleans).
- Demo workflow extended with provider execution dry-run chain.
- Comprehensive tamper tests: boolean flag tests, artifact path test, raw-dict serialization test, actual_call_made=true detection across all read paths.

### Safety / Compatibility
- Provider execution dry-runs are dry-run-only: all 6 boolean flags are False by design.
- No real provider calls, no API keys read, no network requests.
- All new commands remain configless.
- No changes to broker behavior, live trading gates, order routing, approval manager, risk manager, or config secret loading.

## [0.5.7.dev20] - 2026-05-18

### Added
- `src/atlas_agent/research/provider_call_plan.py`: local, auditable provider call-plan artifacts.
- `list_disabled_provider_call_targets()`: metadata for disabled future provider targets.
- `atlas research provider-targets`: list disabled provider targets.
- `atlas research provider-plan SANDBOX_ID --provider ID --model ID`: create provider call-plan artifact.
- `atlas research provider-plan-list`: list provider call-plan artifacts.
- `atlas research provider-plan-show ID`: show one call-plan artifact.
- `atlas research provider-plan-validate ID`: validate call-plan artifact with hash and lineage checks.
- `atlas research provider-plan-replay ID`: replay and compare deterministic hashes.
- Provider call-plan lineage linked in timeline and dossier.
- `check-artifacts` now counts and validates provider call-plan artifacts.
- Demo workflow extended with provider call-plan chain.

### Safety / Compatibility
- Provider call plans are plan-only: `provider_enabled=false`, `network_enabled=false`, `credentials_loaded=false`, `provider_call_allowed=false`.
- No real provider calls, no API keys read, no network requests.
- All new commands remain configless.
- No changes to broker behavior, live trading gates, order routing, approval manager, risk manager, or config secret loading.

## [0.5.7.dev19] - 2026-05-18

### Added
- `.github/workflows/ci.yml`: full safety/test gate on push/PR to main, including pytest, pip check, demo workflows, version/claims checks.
- `.github/workflows/research-ci.yml`: research/sandbox gate on path-filtered push/PR, running `./scripts/release_check.sh --research`.
- `scripts/ci_check.sh`: local CI parity helper that mirrors the CI command sequence (no `git diff --cached --check`).
- CI status badge in README.
- Static tests verifying workflow contents, safety constraints, and absence of secrets.

### Changed
- `.github/workflows/ci.yml` updated to run the full release-equivalent gate remotely.
- README updated with CI workflow documentation and recommended check loops.

### Safety / Compatibility
- CI does not require secrets, broker credentials, or `.env.atlas`.
- CI does not call real LLM/API/network providers.
- No changes to broker behavior, live trading gates, order routing, approval manager, risk manager, or config secret loading.

## [0.5.7.dev18] - 2026-05-18

### Added
- `scripts/dev_check.sh`: fast local development gate (no full pytest, no demos, no pip check).
- `scripts/research_check.sh`: medium-cost research/sandbox gate (research tests + research demo).
- `scripts/release_check.sh` now supports `--quick`, `--research`, and `--full` modes.
- Optional thermal-friendly environment variables: `ATLAS_CHECK_FAIL_FAST=1`, `ATLAS_CHECK_LAST_FAILED=1`, `ATLAS_CHECK_PYTEST_ARGS`.
- Tests verifying tiered mode dispatch, static mutation guards, and script existence.

### Changed
- `scripts/release_check.sh` default behavior remains the full gate; `--quick` and `--research` are developer convenience only.
- README updated with recommended local check loops.

### Safety / Compatibility
- No changes to broker behavior, live trading gates, order routing, approval manager, risk manager, or config secret loading.
- Quick and research modes are not release gates; full mode remains required before push/tag.

## [0.5.7.dev17] - 2026-05-18

### Added
- `src/atlas_agent/research/sandbox_contracts.py`: deterministic canonical JSON hashing, artifact validation, and safe lineage/symbol validators.
- `atlas research sandbox-list`, `sandbox-show`, `sandbox-validate`, `sandbox-replay`, and `import-provider-response` configless research subcommands.
- `import-provider-response` validates local JSON fixtures against the sandbox contract before creating artifacts.
- Sandbox request artifacts now include `artifact_type`, `content_hash` (SHA-256), and `contract_version` for deterministic replay.
- `sandbox-replay` recomputes the artifact hash and verifies it matches the stored `content_hash`.
- Timeline lineage now links `run_id -> prompt -> imported provider response` for full auditability.
- Demo research workflow extended with sandbox inspection and import steps.

### Changed
- `build_llm_sandbox_request_from_prompt_packet` now uses `_build_sandbox_request_dict()` for deterministic artifact construction.
- CLI error mapping expanded with sandbox-specific static error codes.

### Fixed
- Circular import between `sandbox_contracts.py` and `session.py` resolved.
- JSON shadowing bug in `import-provider-response` handler fixed.
- Demo script test fixtures updated to handle all new sandbox commands.

### Safety / Compatibility
- All new commands remain configless and do not load `AtlasConfig.from_env` or `.env.atlas` secrets.
- No network calls, no API keys read, no orders submitted.

## [0.5.7.dev16] - 2026-05-18

### Added
- `atlas research sandbox PROMPT_PACKET_ID` command: builds a local, bounded, replayable LLM sandbox request artifact from an existing prompt packet.
- LLM sandbox request artifact with explicit system boundaries, safety checks, and redaction.
- Sandbox request lineage validation: copied `source_run_id`, `prompt_packet_id`, and `symbol` are validated before artifact construction.
- Regression tests proving tampered prompt packet lineage fails closed without leaking forbidden fragments.
- Configless invariant tests proving sandbox command does not load `AtlasConfig.from_env` or `.env.atlas` secrets.
- Documentation updates for sandbox step in research workflow chain.

### Changed
- `build_llm_sandbox_request_from_prompt_packet` now validates all copied lineage fields before writing artifacts or events.
- CLI sandbox error output maps `ResearchSessionError` to static safe JSON/text with no leaked user-controlled values.
- `scripts/release_check.sh` now includes `./scripts/demo_research_workflow.sh`.
- `docs/research-workflow.md` and `README.md` updated to include `sandbox` in the research command chain.

### Fixed
- Tampered prompt packet `source_run_id` no longer leaks unsafe values into sandbox CLI output or artifacts.
- Sandbox command now fails closed on invalid lineage with no partial artifact or event written.

### Safety / Compatibility
- No runtime broker submit behavior expansion.
- No live-submit default enablement.
- No LLM/API/network provider enablement.
- Sandbox remains local-only: no API calls, no network, no secrets read.
- Frozen research scope remains paper-only and analysis-only.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed.
- pip check passed.
- Demo paper workflow passed.
- Demo research workflow passed.
- release_check.sh passed.
- Protected-staged check passed.

## [0.5.7.dev15] - 2026-05-16

### Added
- Research system freeze audit documentation:
  `docs/audits/research-system-freeze-v0.5.7.dev14.md`
- Regression tests proving local research commands do not call `AtlasConfig.from_env` or load `.env.atlas`.

### Changed
- Release metadata now records the research system as frozen for development scope.
- README/release checklist current-version references updated where applicable.
- Updated `research timeline` help text to reflect the current full lineage including dossiers.

### Fixed
- Made all local research CLI commands bypass global config/secret loading.
- Removed handler-level `AtlasConfig.from_env` and `get_config` calls from `research run`, `plan`, `verify`, `evaluate`, `prompt`, `simulate-provider`, and `review-response`.
- Demo research workflow script stdout/stderr sanitized to prevent absolute temp path leaks (`/Users/`, `/private/var/`, etc.).

### Safety / Compatibility
- This is a documentation/release-prep tag.
- No runtime research behavior changes beyond the already-reviewed freeze fixes.
- No broker submit behavior expansion.
- No live-submit default enablement.
- No LLM/API/network provider enablement.
- Frozen research scope remains paper-only and analysis-only.
- Frozen local research commands remain configless and do not load `.env.atlas` or config secrets.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in latest validation.
- pip check passed.
- Demo paper workflow passed.
- Demo research workflow passed.
- release_check.sh passed.
- Protected-staged check passed.

## [0.5.7.dev14] - 2026-05-16

### Added
- Local research dossier command: `atlas research dossier RUN_ID`.
- Dossier artifacts with bounded summaries of the local paper-only research chain.
- Health-check coverage for dossier artifacts.
- Timeline support for run -> dossier lineage.
- End-to-end demo integration for dossier creation and post-dossier timeline validation.
- Regression tests proving dossier does not load config secrets or `.env.atlas`.

### Changed
- Research demo now validates the extended local chain through dossier creation.
- Artifact health checks now include dossier artifacts.
- Timeline now includes dossier lineage.
- Dossier command uses workspace-only dispatch instead of loading AtlasConfig or config secrets.

### Fixed
- Dossier generation no longer loads AtlasConfig.from_env or `.env.atlas`.
- Dossier output/artifacts omit path-like and secret-like unsafe fragments.
- Dossier command avoids broker/config secret loading while preserving workspace validation.

### Safety / Compatibility
- No LLM/API/network behavior was enabled.
- `dossier` uses local deterministic consolidation only.
- No API keys are read by `dossier`.
- Research workflow remains paper-only and analysis-only.
- Research commands do not create approvals or pending orders.
- No live-submit default enablement.
- No broker submit behavior expansion.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in latest validation.
- pip check passed.
- Demo paper workflow passed.
- Demo research workflow passed.
- release_check.sh passed.
- Protected-staged check passed.

## [0.5.7.dev13] - 2026-05-16

### Added
- Local provider response review command: `atlas research review-response PROVIDER_RESPONSE_ID`.
- Response review artifacts with deterministic safety/completeness checks.
- Timeline support for provider response review lineage.
- Health-check coverage for response review artifacts.
- End-to-end demo integration for response review.
- Duplicate response review ID detection in artifact health checks.

### Changed
- Research demo now validates the extended local chain: run → list/show → plan → verify → evaluate → summary → check-artifacts → timeline → providers → prompt → simulate-provider → review-response → post-review timeline validation.
- Timeline now includes provider_response -> response_review lineage.
- Artifact health checks now include response review artifacts.
- Response review output is bounded and redacted.

### Fixed
- Response review generation now revalidates copied provider-response lineage fields before artifact/event/output construction.
- Unsafe `source_run_id` and `source_prompt_packet_id` values in tampered provider-response artifacts fail closed or are sanitized before output.
- Response review artifacts omit path-like and secret-like unsafe fragments.

### Safety / Compatibility
- No LLM/API/network behavior was enabled.
- `review-response` uses local deterministic review only.
- Response reviews do not call external providers.
- No API keys are read by `review-response`.
- Research workflow remains paper-only and analysis-only.
- Research commands do not create approvals or pending orders.
- No live-submit default enablement.
- No broker submit behavior expansion.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in latest validation.
- pip check passed.
- Demo paper workflow passed.
- Demo research workflow passed.
- release_check.sh passed.
- Protected-staged check passed.

## [0.5.7.dev12] - 2026-05-16

### Added
- Local research prompt packet command (`atlas research prompt RUN_ID`).
- Prompt packet artifacts for bounded, sanitized future-provider context.
- Local simulated provider response command (`atlas research simulate-provider PROMPT_PACKET_ID`).
- Deterministic-mock provider response artifacts.
- Provider response safety checks and recommendations.
- Health-check and timeline coverage for prompt/provider-response artifacts.
- End-to-end demo integration for prompt packets and simulated provider responses.

### Changed
- Research demo now validates the extended local chain: run → list/show → plan → verify → evaluate → summary → check-artifacts → timeline → providers → prompt → simulate-provider → post-simulate-provider timeline validation.
- Timeline now includes prompt → provider_response lineage.
- Artifact health checks now include prompt/provider-response artifacts.
- Prompt/provider-response outputs are bounded and redacted.

### Fixed
- Prompt packet generation now revalidates source artifact symbols before output/path construction.
- Simulated provider response generation now revalidates prompt metadata before artifact/event output.
- Prompt/provider-response artifacts omit path-like and secret-like unsafe fragments.

### Safety / Compatibility
- No LLM/API/network behavior was enabled.
- `simulate-provider` uses local deterministic simulation only.
- Prompt packets do not call providers.
- Simulated provider responses do not call external providers.
- No API keys are read by prompt/simulate-provider commands.
- Research workflow remains paper-only and analysis-only.
- Research commands do not create approvals or pending orders.
- No live-submit default enablement.
- No broker submit behavior expansion.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in latest validation.
- pip check passed.
- Demo paper workflow passed.
- Demo research workflow passed.
- release_check.sh passed.
- Protected-staged check passed.

## [0.5.7.dev11] - 2026-05-16

### Added
- Read-only research provider discovery command (`atlas research providers`).
- Provider metadata model (`ResearchProviderInfo`) for deterministic and disabled LLM placeholder providers.
- CLI tests proving no API key reads, no network imports, no broker path usage, and safe output.
- Demo workflow now validates provider discovery (`deterministic.local=true`, disabled `llm` placeholder).
- Failure tests for unsafe provider discovery output.

### Changed
- Research workflow documentation now documents the `providers` discovery command.
- Architecture docs now mention provider-discovery as a read-only boundary.

### Safety / Compatibility
- Deterministic/local remains the default provider.
- External/LLM providers remain disabled.
- No API keys are read by the provider discovery command.
- No network/API calls were added.
- No live-submit default enablement.
- No broker submit behavior expansion.
- Research workflow remains paper-only and analysis-only.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in the latest validation.
- pip check passed.
- Demo paper workflow passed.
- Demo research workflow passed.
- release_check.sh passed.
- Protected-staged check passed.

## [0.5.7.dev10] - 2026-05-16

### Added
- Research provider interface.
- Deterministic/local research provider abstraction.
- Disabled/fail-closed LLM provider stub.
- Provider docs-truth tests.
- Release notes for v0.5.7.dev10.

### Changed
- Research workflow documentation now describes the provider boundary.
- Architecture docs now separate research provider selection from broker/live-submit execution.

### Safety / Compatibility
- Deterministic/local remains the default provider.
- External/LLM providers are not enabled.
- Unsupported providers fail closed.
- No API keys are read by the research provider layer.
- No network/API calls were added.
- No live-submit default enablement.
- No broker submit behavior expansion.
- Research workflow remains paper-only and analysis-only.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in latest validation.
- pip check passed.
- Demo paper workflow passed.
- Demo research workflow passed.
- release_check.sh passed.
- Protected-staged check passed.

## [0.5.7.dev9] - 2026-05-16

### Added
- Post-research-system audit documentation.
- Read-only research timeline command and lineage tests.
- Timeline integration in the end-to-end research demo.
- Research artifact health-check demo integration.
- Memory runtime artifact ignore/protection tests.

### Changed
- Research demo now validates the complete local chain:
  run -> list/show -> plan -> verify -> evaluate -> summary -> check-artifacts -> timeline.
- Demo lineage validation now verifies:
  run_id -> plan_id -> verification_id -> evaluation_id.
- Workspace hygiene now ignores and protects memory runtime lock/cache artifacts.

### Fixed
- Sanitized generic research CLI error fallback output.
- Fixed invalid-symbol and unsupported-provider CLI error leaks for path-like and secret-like input.
- Fixed stale current-version references after v0.5.7.dev8.

### Safety / Compatibility
- No live-submit default enablement.
- No broker submit behavior expansion.
- Research workflow remains paper-only and analysis-only.
- Research commands do not create approvals or pending orders.
- Health checks and timeline commands are read-only.
- Artifact health checks do not migrate, rewrite, repair, or delete artifacts.
- No kill-switch, risk, config, broker, submit, or live-trading gate weakening.

### Validation
- Version consistency passed.
- Forbidden-claim scan passed.
- Full pytest passed in latest validation.
- pip check passed.
- Demo paper workflow passed.
- Demo research workflow passed.
- release_check.sh passed.
- Protected-staged check passed.

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
