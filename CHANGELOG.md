# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.22] - 2026-07-13

### Added

- Opened the `v0.6.22` planning line: `docs/releases/v0.6.22-plan.md`, `docs/releases/v0.6.22-candidates.json`, `docs/releases/v0.6.22-candidates.md`, and `docs/releases/v0.6.22-candidate-selection.md`.
- Released `CAND-016: Release-Maintenance Drift Hardening` as part of `v0.6.22`. It is documented in `docs/cand-016-release-maintenance-drift-hardening.md` and recorded in the `v0.6.22` candidate chain. Docs/checker/test-only; no runtime, safety, broker, provider, credential, version, or release-metadata behavior changes; the CAND-014 extraction boundary is unchanged.
- Accepted `CAND-016: Release-Maintenance Drift Hardening` into the `v0.6.22` candidate chain on 2026-07-13 with verdict `PASS` (not released). It is documented in `docs/cand-016-release-maintenance-drift-hardening.md` and recorded in the `v0.6.22` candidate chain. Docs/checker/test-only; no runtime, safety, broker, provider, credential, version, or release-metadata behavior changes; the CAND-014 extraction boundary is unchanged.
- Added `docs/releases/v0.6.21-post-release-assurance.md` and `.json` recording the `v0.6.21` release state, tag/GitHub Release verification, GitHub Actions/CI status, re-run local checks, and remaining caveats. GitHub-only record; not a live-trading or production-readiness claim.
- Added `tests/test_next_planned_tag_guard.py` regression coverage proving the next-planned tag guard in `check_bounded_autonomy_governance.py`, `check_autonomous_paper_workflow_demo.py`, and `check_paper_provider_isolation.py` tracks `next_planned_release` from release metadata (offline, `subprocess.run` mocked; no real git tags).
- Added reverse-drift coverage in `tests/test_public_docs_consistency.py` for the new roadmap guard.

### Changed

- Made the next-planned tag guard metadata-driven in `scripts/check_bounded_autonomy_governance.py`, `scripts/check_autonomous_paper_workflow_demo.py`, and `scripts/check_paper_provider_isolation.py`: the `git tag --list` guard now queries `NEXT_PLANNED_TAG` (from release metadata) instead of a hardcoded tag literal, so it can no longer drift from the metadata next-planned line.
- Extended `scripts/check_public_docs_consistency.py` with a metadata-driven reverse-drift roadmap guard (`_released_candidate_ids` and `_check_autonomy_roadmap_released_candidates_not_next_planned`): it flags an already-released candidate listed as a candidate-entry bullet under the next-planned planning-line section of `docs/autonomy-roadmap.md`, mirroring the existing forward-drift check. Prose cross-references are ignored to avoid false positives; exit codes `0`/`1` preserved. (CAND-016)

### Fixed

- Made the release-assurance snapshot demo default (`scripts/demo_release_assurance_snapshot_bundle.sh`) metadata-driven: it derives the assured release from `current_public_release` (with a pinned fallback) instead of a stale hardcoded `v0.6.15`, resolving the post-`v0.6.21` full-suite CI failure in `tests/test_release_assurance_bundle_manifest.py::test_demo_runs_end_to_end`. (CAND-016)

- Corrected post-release documentation drift in `docs/autonomy-roadmap.md`: restored the `v0.6.20` release section (CAND-012), moved CAND-013/CAND-014 Phase 2/CAND-015 under the `v0.6.21` release section (released, not planning), and reset the `v0.6.22` planning line to no accepted candidates. The cutover's blind version increment had mislabeled which candidates belonged to which release.
- Corrected a stale planning-seed reference in `docs/public-launch-readiness.md` that still described `v0.6.21` as seeding the next planning line; `v0.6.22` is now the next planning-seed link and `v0.6.21` is historical.

### Safety

- The `v0.6.22` release is docs/tests/checker-only. No live trading, live submit, broker/provider execution, credential loading, network access, order placement, or approval queue mutation is introduced. `RiskManager`, kill-switch, deadman, heartbeat, audit hash-chain, live-submit opt-in, and `can_submit` are unchanged. `atlas run --mode live` remains fail-closed. The CAND-014 extraction boundary is unchanged. PyPI remains unpublished.

## [0.6.21] - 2026-07-07

### Added

- CAND-013: Public/Trust Docs Drift Coverage Guard. `scripts/check_public_docs_consistency.py` now uses release metadata as the current/next-planned authority and additionally catches stale trust README `(current public)` labels on non-current releases, autonomy-roadmap candidate-state contradictions against next-planned candidate-chain JSON, and related public-docs drift; `tests/test_public_docs_consistency.py` coverage extended and documented in `docs/development/checks-reference.md`. Exit codes `0`/`1` preserved.
- CAND-014 Phase 2: Provider Artifact Engine Deduplication. Phase 2 delivered a one-module pilot extraction that moved shared artifact mechanics for `src/atlas_agent/research/provider_mock_response_final_safety_seal.py` behind a minimal `src/atlas_agent/research/artifact_engine.py` while preserving Phase 1 golden compatibility. No spec module was created and extraction beyond this pilot remains not authorized.
- CAND-015: Bounded Live Autonomy Readiness Gate. Adds `src/atlas_agent/agent/bounded_live_autonomy_readiness.py` engine and `src/atlas_agent/agent/bounded_live_autonomy_readiness_cli.py` configless CLI, registers `atlas agent bounded-live-readiness`, adds `scripts/check_bounded_live_autonomy_readiness_contract.py` static contract checker, tests, and fixtures. Evaluates a 15-gate fail-closed sequence and records artifacts only when all gates pass. Does not submit orders, call brokers/providers, load credentials, mutate runtime state, or claim live readiness. `bounded_live_readiness_recorded` is evidence-recording status only and not permission to trade or authorization to submit orders.

### Changed

- Cut over current public release from `v0.6.20` to `v0.6.21`. Package/source version is now `0.6.21`. `v0.6.20` is the historical previous public release. `v0.6.22` is the next planned release line.
- CAND-015 finalization: added conservative cross-references to `docs/bounded-live-autonomy-governance.md` and `docs/autonomy-roadmap.md`; made `artifact_recording_gate` explicit in the recorded report gate list; added a dedicated regression test proving `provider_output_authoritative=true` blocks readiness.
- Added v0.6.21 release-readiness planning dossier (`docs/releases/v0.6.21-final-readiness-audit.md` and `.json`) and updated `docs/releases/v0.6.21-readiness-plan.md`, `docs/releases/v0.6.21-plan.md`, and `docs/releases/v0.6.21-candidate-selection.md` to reference it.

### Fixed

- Stale public-release test expectations: updated tests that still expected `v0.6.20`-era current/latest release values to `v0.6.21`.

### Safety

- CAND-013 introduces no live trading, live submit, broker/provider execution, credential loading, network access, or order placement, and changes no `RiskManager`, kill-switch, deadman, heartbeat, or audit hash-chain behavior. `atlas run --mode live` remains fail-closed.
- CAND-014 Phase 2 changes only `src/atlas_agent/research/artifact_engine.py` and `src/atlas_agent/research/provider_mock_response_final_safety_seal.py`; introduces no live trading, live submit, broker/provider calls, credential loading, network access, order placement, order cancellation, position flattening, pending-order creation, or approval queue mutation; preserves all public function names, signatures, version constants, schema fields, status values, hash exclusions, `validate_provider_id` behavior, disabled-provider behavior, replay/summarize/doctor structures, and CLI-facing behavior; and does not authorize extraction beyond the pilot module.
- CAND-015 is evidence-only and simulated-only; it does not submit orders, call brokers/providers, load credentials, create or mutate pending orders, mutate approval queues, access the network, or change `RiskManager`, kill-switch, deadman, heartbeat, or audit hash-chain behavior. `atlas run --mode live` remains fail-closed. `bounded_live_readiness_recorded` is evidence-recording status only and not live readiness, trading safety, permission to trade, or authorization to submit orders.
- This is a GitHub-only release; PyPI remains unpublished.

## [0.6.20] - 2026-07-02

### Added

- CAND-012: Candidate-Chain Consistency Guard. Added `scripts/check_candidate_chain.py` static checker and `tests/test_candidate_chain.py` coverage to validate release-metadata, candidate-chain JSON, and candidate-chain Markdown consistency; integrated into `scripts/dev_check.sh` and `scripts/ci_check.sh`; documented in `docs/development/checks-reference.md`.

### Changed

- Cut over current public release from `v0.6.19` to `v0.6.20`. Package/source version is now `0.6.20`. `v0.6.19` is the historical previous public release. `v0.6.21` is the next planned release line.

### Fixed

- Stale public-release docs drift: corrected remaining public docs that still labeled `v0.6.17`/`v0.6.18` as current/latest.
- Stale test expectations: updated tests that still expected `v0.6.17`-era current/latest release values.

### Safety

- No live trading, live submit, broker/provider execution, credential loading, or order placement introduced.
- `atlas run --mode live` remains fail-closed.
- GitHub-only release; PyPI remains unpublished.

## [0.6.19] - 2026-07-01

### Fixed

- CAND-011: Kill-Switch `last_heartbeat()` Type-Safety Cleanup. Narrowed audit payload construction in `src/atlas_agent/safety/kill_switch.py` to eliminate a pre-existing mypy `union-attr` warning; preserved fail-closed behavior and the existing `last_heartbeat` payload shape; added mandatory `heartbeat_expired` audit-payload regression tests.

### Safety

- No live trading, live submit, broker/provider execution, credential loading, or order placement introduced.
- `atlas run --mode live` remains fail-closed.
- GitHub-only release; no PyPI publication.

## [0.6.18] - 2026-07-01

### Added
- CAND-010: Safety-State Persistence Regression Guard. Committed `scripts/check_safety_atomic_write.py` static checker and `tests/test_check_safety_atomic_write.py` coverage to prevent reintroduction of fixed `<target>.tmp` writes in `src/atlas_agent/safety/heartbeat.py`, `src/atlas_agent/safety/deadman.py`, `src/atlas_agent/safety/kill_switch.py`, and `src/atlas_agent/safety/state.py`; integrated into `scripts/dev_check.sh` and `scripts/ci_check.sh`.

### Changed
- Optional non-behavioral lint hygiene in CAND-009 touched test files: removed unused assignments in `tests/safety/test_atomic_write.py` and added missing `Path` imports in `tests/safety/test_deadman.py` and `tests/safety/test_kill_switch_core.py`.

### Fixed
- Escaped literal protected-boundary brace paths in release-assurance remediation text so diagnostic rendering remains reliable when protected-boundary checks fail.

### Safety
- No live trading, live submit, broker/provider execution, credential loading, or order placement introduced.
- `atlas run --mode live` remains fail-closed.
- GitHub-only release; no PyPI publication.

## [0.6.17] - 2026-07-01

### Added
- CAND-009: Safety State Atomic-Write Hardening. `src/atlas_agent/safety/atomic_write.py` stdlib-only helper using unique same-directory temporary files; migrated `src/atlas_agent/safety/heartbeat.py`, `src/atlas_agent/safety/deadman.py`, `src/atlas_agent/safety/kill_switch.py`, and `src/atlas_agent/safety/state.py` from fixed `<target>.tmp` writes; regression and concurrency tests under `tests/safety/`.
- `doctor` top-level command added to `tests/fixtures/cli_command_contract.json`.
- CAND-009 accepted into the `v0.6.17` candidate chain. Acceptance is documentation/governance acceptance only and does not authorize `v0.6.17` release cutover.

### Changed
- Safety-state persistence now uses unique temporary filenames via `tempfile.mkstemp` while preserving atomic `replace` semantics, file formats, public APIs, and best-effort `chmod(0o600)` behavior.

### Safety
- No live trading, live submit, broker/provider execution, credential loading, or order placement introduced.
- `atlas run --mode live` remains fail-closed.
- This is a GitHub-only release; PyPI was not published.

## [0.6.16] - 2026-06-30

### Added
- CAND-001: Paper Autonomous Decision Loop and Shadow-Live Readiness Contract.
- CAND-002: Autonomous Paper Decision Quality Scorecard and Promotion Gate.
- CAND-003: execution-neutral autonomous trading kernel and stateful paper runner with resume, duplicate-prevention, next-bar fills, configurable costs, and honest trading metrics.
- CAND-004: Autonomous Paper Trading Quality Gate for deterministic offline evaluation of stateful paper trading behavior.
- CAND-005: Shadow-Live Read-Only Fixture-First Comparison for deterministic, read-only comparison of a stateful paper run against a recorded local broker-like snapshot.
- `atlas agent shadow-live` command for read-only fixture-first comparison of paper state against a recorded broker snapshot.
- `src/atlas_agent/agent/autonomous_paper_shadow_live.py` shadow-live comparison builder, snapshot loader, comparison engine, status resolver, and artifact writers.
- `scripts/check_shadow_live_readonly_contract.py` static contract checker and `tests/test_shadow_live_readonly.py`, `tests/test_shadow_live_readonly_contract.py` test coverage.
- `docs/shadow-live-readonly-comparison.md` user-facing documentation for the CAND-005 read-only comparison.
- CAND-006: Gated Submit Conformance Rehearsal (Simulated Only) for deterministic, fixture-first rehearsal of the submit gate without submitting orders.
- `atlas agent submit-conformance` command and configless `atlas agent submit-conformance` bootstrap route for simulated-only conformance rehearsal.
- `src/atlas_agent/agent/gated_submit_conformance.py` closed-schema engine, gate sequence, dry-run request builder, fingerprinting, and artifact writers.
- `src/atlas_agent/agent/gated_submit_conformance_cli.py` CLI handler for the CAND-006 rehearsal.
- `src/atlas_agent/cli_bootstrap.py` narrow pre-router that intercepts `atlas agent submit-conformance` before the legacy CLI to avoid loading configuration, credentials, or heavy dependencies.
- `scripts/check_gated_submit_conformance_contract.py` static contract checker and `tests/test_gated_submit_conformance.py`, `tests/test_gated_submit_conformance_cli.py`, `tests/test_gated_submit_conformance_import_trace.py` test coverage.
- `docs/gated-submit-conformance.md` user-facing documentation for the CAND-006 rehearsal.
- CAND-007: Runtime Readiness Envelope Evaluation (Simulated Only) for deterministic, fixture-first evaluation of the runtime readiness envelope without submitting orders.
- `atlas agent readiness-envelope` command and configless `atlas agent readiness-envelope` bootstrap route for simulated-only envelope evaluation.
- `src/atlas_agent/agent/runtime_readiness_envelope.py` closed-schema engine, projection validators, universal rejection scanner, gate sequence, fingerprinting, and artifact writers.
- `src/atlas_agent/agent/runtime_readiness_envelope_cli.py` CLI handler for the CAND-007 envelope evaluator.
- `scripts/check_runtime_readiness_envelope_contract.py` static contract checker and `tests/test_runtime_readiness_envelope.py`, `tests/test_runtime_readiness_envelope_cli.py`, `tests/test_runtime_readiness_envelope_contract.py`, `tests/test_runtime_readiness_envelope_import_trace.py` test coverage.
- `docs/runtime-readiness-envelope.md` user-facing documentation for the CAND-007 envelope evaluator.
- CAND-008: Operator Approval Gate (Simulated Only) for deterministic, fixture-first operator evidence review that consumes CAND-004/CAND-005/CAND-006/CAND-007 artifacts plus CAND-008 static fixtures, evaluates a 13-gate fail-closed sequence, and records `operator-approval-gate.json` plus `operator-approval-gate-report.md` without submitting orders, calling brokers/providers, loading credentials, or claiming live readiness.
- `atlas agent operator-approval-gate` command and configless `atlas agent operator-approval-gate` bootstrap route for simulated-only operator approval gate evaluation.
- `src/atlas_agent/agent/operator_approval_gate.py` closed-schema engine, projection validators, universal rejection scanner, gate sequence, fingerprinting, and artifact writers.
- `src/atlas_agent/agent/operator_approval_gate_cli.py` CLI handler for the CAND-008 operator approval gate.
- `scripts/check_operator_approval_gate_contract.py` static contract checker and `tests/test_operator_approval_gate.py`, `tests/test_operator_approval_gate_cli.py`, `tests/test_operator_approval_gate_contract.py`, `tests/test_operator_approval_gate_import_trace.py` test coverage.
- `docs/operator-approval-gate.md` user-facing documentation for the CAND-008 operator approval gate.
- `atlas agent autonomous-paper` command for deterministic, paper-only autonomous decision loops on local sample/CSV data.
- `atlas agent autonomous-scorecard` command for deterministic offline evaluation of autonomous-paper artifacts.
- `atlas agent autonomous-paper-quality` command for deterministic offline trading-quality gate evaluation.
- `src/atlas_agent/agent/autonomous_paper_quality.py` trading-quality gate builder and Markdown renderer.
- `scripts/check_autonomous_paper_quality_contract.py` static contract checker and `tests/test_autonomous_paper_quality.py`, `tests/test_autonomous_paper_quality_contract.py` test coverage.
- `docs/autonomous-paper-quality-gate.md` user-facing documentation for the CAND-004 gate.
- `src/atlas_agent/agent/autonomous_paper.py` decision loop with `RiskManager` paper-mode gating, local execution simulation, audit events, and manifest generation.
- `src/atlas_agent/agent/autonomous_paper_scorecard.py` scorecard builder and promotion gate.
- `docs/autonomous-paper-loop.md`, `scripts/check_autonomous_paper_loop_contract.py`, and `tests/test_autonomous_paper_loop_contract.py`.
- `docs/autonomous-paper-scorecard.md`, `scripts/check_autonomous_paper_scorecard_contract.py`, `tests/test_autonomous_paper_scorecard.py`, `tests/test_autonomous_paper_scorecard_contract.py`, and `scripts/demo_autonomous_paper_scorecard.sh`.
- `docs/shadow-live-readiness-contract.md`, `scripts/check_shadow_live_contract.py`, and `tests/test_shadow_live_contract.py`.
- `tests/test_autonomous_paper_loop.py` covering happy path, no-trade path, orders blocked by risk controls, malformed-config fail-closed, live-mode rejection, unreachable broker submit, no provider execution, audit artifact creation, and deterministic replay.
- `tests/test_autonomous_paper_scorecard.py` covering valid scorecard generation, missing/malformed artifacts, runs blocked by risk controls, no-trade runs, kill-switch blocked runs, replay mismatch, unsafe live/provider/broker references, redaction, promotion defaults, and CLI smoke.

### Changed
- `docs/bounded-live-autonomy-governance.md` updated to reflect the current v0.6.15 / v0.6.16 posture and CAND-001/CAND-002/CAND-003/CAND-004/CAND-005/CAND-006/CAND-007/CAND-008 paper-only scope, including CAND-005 as a read-only fixture-first comparison stage, CAND-007 as an envelope evaluator stage, and CAND-008 as an operator approval gate stage in the staged autonomy ladder.
- `docs/shadow-live-readiness-contract.md` clarified: CAND-005 implements local fixture-first read-only comparison only; CAND-006 is a simulated-only gated submit conformance rehearsal; CAND-007 is a simulated-only runtime readiness envelope evaluator; CAND-008 is a simulated-only operator approval gate evaluator.
- `docs/autonomy-roadmap.md` marked CAND-005, CAND-006, CAND-007, and CAND-008 implemented in planning.
- `docs/runtime-readiness-envelope-design.md` updated to note that the CAND-007 implementation has landed.
- `docs/operator-approval-gate-design.md` updated to note that the CAND-008 implementation has landed.
- `docs/architecture.md` documented `atlas agent readiness-envelope` as a second bootstrap-only configless route and `atlas agent operator-approval-gate` as a third bootstrap-only configless route.
- `docs/cli-command-compatibility.md` documented the bootstrap-only command exceptions for CAND-007 and CAND-008.
- `docs/gated-submit-conformance.md` added forward reference to CAND-007 as the next envelope stage.
- `docs/runtime-readiness-envelope.md` added forward reference to CAND-008 as the next operator approval gate stage.
- `docs/autonomous-paper-quality-gate.md` added note that `cost_impact_pct` is an approximation/proxy for directional paper-run review, not high-precision production cost analysis.
- `docs/releases/v0.6.16-plan.md`, `v0.6.16-candidates.md`, `v0.6.16-candidates.json`, and `v0.6.16-candidate-selection.md` updated with CAND-001, CAND-002, CAND-003, CAND-004, CAND-005, CAND-006, CAND-007, and CAND-008 as implemented planning candidates.
- `docs/releases/v0.6.16-plan.md`, `v0.6.16-candidates.md`, `v0.6.16-candidates.json`, `v0.6.16-candidate-selection.md`, `docs/autonomy-roadmap.md`, `docs/bounded-live-autonomy-governance.md`, and `docs/operator-approval-gate.md` updated to record CAND-008 as accepted into the `v0.6.16` candidate chain. Acceptance is documentation-only; the candidate remains simulated-only, evidence-only, and non-executing, with no live trading, no live submit, no broker/provider calls, no credentials, and no release cutover.
- `scripts/dev_check.sh` and `scripts/release_check.sh` wired to run the new autonomous paper loop, shadow-live contract, shadow-live read-only contract, autonomous paper scorecard, autonomous paper quality gate, gated submit conformance rehearsal, runtime readiness envelope, and operator approval gate checkers and tests.
- `pyproject.toml` console entry point remains `atlas_agent.cli_bootstrap:main` to enable the configless CAND-006/CAND-007/CAND-008 routes.
- `tests/fixtures/cli_command_contract.json` updated with `agent submit-conformance` and `agent operator-approval-gate`.
- `tests/test_package_distribution_check.py` fake wheels now reflect the `atlas_agent.cli_bootstrap:main` entry point.

### Safety
- PyPI was not published.
- Live trading and live submit remain disabled by default; provider and broker execution defaults are unchanged.
- The autonomous loop and scorecard are paper-only and fail closed on missing configuration, malformed artifacts, or live-mode CLI arguments.
- The scorecard gate defaults to `blocked` and never enables shadow-live execution.
- CAND-003 remains paper-only and does not enable live trading, shadow-live, broker submission, provider execution, or credential loading.
- CAND-004 trading-quality gate is paper-only and does not enable live trading, shadow-live, broker submission, provider execution, or credential loading. It does not claim profitability or live-trading readiness.
- CAND-005 shadow-live read-only comparison is fixture-first, calls no real broker APIs by default, loads no credentials, submits no orders, mutates no broker state, and does not claim live readiness, trading safety, profitability, or permission to submit orders.
- CAND-006 gated submit conformance rehearsal is simulated-only: it submits no orders, calls no broker or provider APIs, loads no credentials, creates no real or pending orders, does not instantiate runtime `Order`/`OrderRouter`/`RiskManager`/`ApprovalManager`/kill-switch objects, and does not claim live readiness or permission to submit orders.
- CAND-007 runtime readiness envelope evaluation is simulated-only: it submits no orders, calls no broker or provider APIs, loads no credentials, creates no real or pending orders, does not instantiate runtime `Order`/`OrderRouter`/`RiskManager`/`ApprovalManager`/kill-switch objects, and does not claim live readiness, trading safety, profitability, or permission to submit orders. The status `readiness_envelope_recorded` is evidence-recording status only.
- No protected runtime safety boundary changed in this planning phase.

## [0.6.15] - 2026-06-22

### Added
- CAND-001 through CAND-006 paper human review pack, ledger, policy simulator, replay, evidence bundle, and final-readiness gates.
- Deterministic, offline paper human review documentation, demos, checkers, tests, and reviewer evidence.
- `docs/releases/v0.6.15.md`, `docs/trust/v0.6.15-status.md`, `docs/releases/v0.6.15-post-release-evidence.md`, and `.json`.
- `scripts/check_v0615_post_release_hygiene.py` and `tests/test_v0615_post_release_hygiene.py` for v0.6.15 post-release state validation.
- `docs/releases/v0.6.16-plan.md`, `docs/releases/v0.6.16-candidates.md`, and `.json` as the next planning seed.

### Changed
- Source/package version advanced from `0.6.14` to `0.6.15` for the owner-authorized GitHub-only release.
- Public release metadata now identifies `v0.6.15` as current, `v0.6.14` as historical, and `v0.6.16` as the next planning line.
- README, public docs, and active checkers updated to the v0.6.15 public / v0.6.16 next posture.
- Archived `scripts/check_v0614_post_release_hygiene.py` to `scripts/historical_release_checkers/` and updated its test to exercise it against fixtures.

### Safety
- PyPI was not published.
- Live trading and live submit remain disabled by default; provider and broker execution defaults are unchanged.
- No real human approval is created or recorded.
- No protected runtime safety boundary changed in this release cutover.

## [0.6.14] - 2026-06-22

### Added
- CAND-001 through CAND-008 paper portfolio proposal, stress, monitoring, recheck, dossier, replay, evidence, and final-readiness gates.
- Deterministic, offline paper portfolio documentation, demos, checkers, tests, and reviewer evidence.

### Changed
- Source/package version advanced to `0.6.14` for the owner-authorized GitHub-only release.
- Public release metadata now identifies `v0.6.14` as current, `v0.6.13` as historical, and `v0.6.15` as the next planning line.

### Safety
- PyPI was not published.
- Live trading and live submit remain disabled by default; provider and broker execution defaults are unchanged.
- No protected runtime safety boundary changed in this release cutover.

## [0.6.13] - 2026-06-18
- Initial release for 0.6.13.

### Added

### Changed

### Fixed

### Safety

## [0.6.12] - 2026-06-17

### Added
- Release preparation and owner approval gate (CAND-018): bumped package/source version to `0.6.12`, created `docs/releases/v0.6.12.md`, `docs/trust/v0.6.12-status.md`, and `docs/releases/v0.6.12-owner-approval.md`.
- Public release cutover (CAND-019): created annotated tag `v0.6.12`, pushed it to origin, and created GitHub Release `v0.6.12` from `docs/releases/v0.6.12.md`.
- Post-release evidence and next-line planning seed (CAND-020): added `docs/releases/v0.6.12-post-release-evidence.md`, `docs/releases/v0.6.12-post-release-evidence.json`, and `docs/releases/v0.6.13-plan.md`.
- `scripts/check_v0612_release_prep.py` and `tests/test_v0612_release_prep.py` for v0.6.12 release-prep and post-release state validation.
- `scripts/check_v0612_release_cutover.py` and `tests/test_v0612_release_cutover.py` for v0.6.12 public-release cutover validation.
- `scripts/check_v0612_post_release_evidence.py` and `tests/test_v0612_post_release_evidence.py` for deterministic v0.6.12 post-release evidence validation.
- `tests/test_v0612_release_candidate_readiness.py` for the updated v0.6.12 release-candidate readiness checker.

### Changed
- Bumped package/source version from `0.6.11` to `0.6.12`.
- Updated release metadata to reflect `v0.6.12` as the current public GitHub release, `v0.6.11` as historical, and `v0.6.13` as the next planned release.
- Updated README, SECURITY.md, `docs/trust/README.md`, `docs/development/main-health.md`, `docs/public-launch-readiness.md`, and `docs/release-checklist.md` to reflect `0.6.12` source / `v0.6.12` public / `v0.6.13` next state.
- Integrated the v0.6.12 release-prep/post-release and cutover checks into `scripts/dev_check.sh`, `scripts/ci_check.sh`, `scripts/release_check.sh`, and the GitHub Actions `quick-gate` workflow.

### Safety
- No live trading, broker execution, provider execution, risk gate, approval gate, kill switch, or audit behavior changes.
- Annotated tag `v0.6.12` was created and pushed; GitHub Release `v0.6.12` was published; **PyPI was not published**.
- Public cutover for `v0.6.12` was performed with explicit owner approval documented in `docs/releases/v0.6.12-owner-approval.md`.

## [0.6.11] - 2026-06-15

### Added
- Post-release hardening and observability cleanup (CAND-001): refreshed stale version references across reviewer-facing docs, public-repo hygiene, and public-feedback checklists; aligned consistency and trust-center checkers with the v0.6.10 public / v0.6.11 planning state.
- Backtest/report dashboard usability follow-up (CAND-002): improved dashboard empty-state messaging, added export timestamp headers, and improved backtest summary table column alignment for Markdown/HTML output.
- Broker/provider preflight diagnostics without enabling execution (CAND-003): added deterministic, redacted `atlas doctor` output for configured-but-not-activated broker/provider settings, credential-presence checks, and connection-readiness hints with no network calls.
- Paper-trading workflow documentation and safe examples (CAND-004): refreshed `docs/paper-trading-guide.md`, `scripts/demo_paper_workflow.sh`, and `examples/paper_trading_demo/config.toml` as canonical offline, paper-only, fail-closed references.
- Release/checker simplification after v0.6.10 (CAND-005): archived historical version-specific release checkers into `scripts/historical_release_checkers/` while preserving active v0.6.10 post-release and v0.6.11 planning validation; added `scripts/check_v0611_release_prep.py` and matching tests.
- Test-suite performance and generated-artifact hygiene (CAND-006): marked subprocess-heavy integration tests for targeted runs, isolated CLI test workspaces, batched focused CI pytest collection, and hardened generated-artifact detection.
- User-facing quickstart and reviewer demo consolidation (CAND-007): merged overlapping quickstart/demo content across README, external-reviewer-walkthrough, and reviewer-golden-path into one canonical flow.
- `docs/releases/v0.6.11.md`, `docs/trust/v0.6.11-status.md`, and `docs/releases/release-metadata.json` prepared-state artifacts.
- `scripts/check_v0611_release_prep.py` and matching tests for v0.6.11 release-prep state validation.

### Changed
- Bumped package/source version from `0.6.10` to `0.6.11`.
- Updated release metadata to reflect `v0.6.11` as the current public GitHub release and `v0.6.10` as historical, with `v0.6.12` as the next planned release.
- Updated README, SECURITY.md, `docs/trust/README.md`, and `docs/development/main-health.md` to reflect `v0.6.11` as current public release, `v0.6.10` as historical, and `v0.6.12` as next planned release.

### Fixed

### Safety
- No live trading, broker execution, provider execution, risk gate, approval gate, kill switch, or audit behavior changes.
- Tag `v0.6.11` created and pushed; GitHub Release `v0.6.11` published; **PyPI was not published**.

## [0.6.10] - 2026-06-13

### Added
- Reviewer validation command guide refresh (CAND-001): updated reviewer walkthroughs, golden path, checklist, FAQ, safety docs, and stale-link repairs.
- Dashboard/report UX polish after v0.6.9 (CAND-002): fixed schema-status badge mapping, added HTML safety banner to Markdown dashboard exports, improved empty/redacted diagnostics, and sorted backtest runs deterministically by `run_id`.
- Backtest report schema checker ergonomics (CAND-003): added `--json`, per-status counts (`valid/invalid/legacy/unreadable`), `--fail-on-legacy`, final summary, and direct unit tests for `scripts/check_backtest_report_schema.py`.
- Template source-of-truth simplification (CAND-004): made `src/atlas_agent/templates/routine-trader/` the canonical packaged copy, removed the root-level duplicate, and updated checkers/tests/docs to reference the packaged copy.
- Code inventory follow-up import/API classification (CAND-005): refreshed `docs/development/code-inventory-followups.md` and `tests/test_code_inventory_imports.py`.
- Release-assurance metadata cleanup (CAND-006): removed stale hardcoded v0.5.x-era copy-paste from `scripts/release_assurance.py`, archived old `artifacts/release_assurance/v0.5.9*` packs, and tightened `.gitignore` for generated local evidence.
- Public docs link/reference hardening after README cleanup (CAND-007): fixed broken CHANGELOG links to v0.5.8 rc notes, refreshed capability-inventory headers, converted backticked doc paths to Markdown links, and extended the public-docs consistency scan list.
- `docs/releases/v0.6.10.md`, `docs/trust/v0.6.10-status.md`, `docs/releases/v0.6.10-candidates.md`, and `docs/releases/v0.6.10-candidates.json`.
- `scripts/check_v0610_release_prep.py` and matching tests for v0.6.10 release-prep state validation.

### Changed
- Bumped package/source version from `0.6.9` to `0.6.10`.
- Updated release metadata to reflect `v0.6.10` as the current public GitHub release and `v0.6.9` as historical.
- Updated README, SECURITY.md, `docs/trust/README.md`, and `docs/development/main-health.md` to reflect `v0.6.10` as current public release, `v0.6.9` as historical, and `v0.6.11` as next planned release.

### Fixed

### Safety
- No live trading, broker execution, provider execution, risk gate, approval gate, kill switch, or audit behavior changes.
- Tag `v0.6.10` created and pushed; GitHub release `v0.6.10` published; **PyPI was not published**.

## [0.6.9] - 2026-06-11

### Added
- Backtest report schema contract (`src/atlas_agent/backtest/report_schema.py`, `docs/backtesting/report-schema.md`, `tests/backtest/test_backtest_report_schema.py`) with `backtest.report.v1`, deterministic validation, and accumulated schema error collection.
- Backtest validation UX: `atlas backtest runs --validate` emits `schema_status`, `schema_valid`, `schema_error`, `schema_errors`, and `schema_version`; unreadable `result.json` files are surfaced instead of silently skipped.
- Dashboard/report schema status surfacing (`latest_schema_version`, `latest_validation_status`).
- Markdown Diagnostics and Fills Summary sections in backtest reports.
- Markdown trade metrics: realized-PnL best/worst/average and percentage best/worst/average (`Best Trade %`, `Worst Trade %`, `Average Trade %`).
- Historical backtest runs CLI (`atlas backtest runs`) with JSON and validate modes.
- Backtest date filtering (`--start-date`, `--end-date`).
- Realized-PnL tracking per sell fill.
- Strategy entry-point dogfooding: built-in backtest strategies declared in `pyproject.toml` with discovery tests.
- `scripts/check_v069_release_prep.py` and `tests/test_check_v069_release_prep.py` for v0.6.9 release-prep state validation.
- `docs/releases/v0.6.9.md`, `docs/trust/v0.6.9-status.md`, `docs/releases/v0.6.9-candidates.md`, and `docs/releases/v0.6.9-candidates.json`.

### Changed
- Bumped package/source version from `0.6.8` to `0.6.9`.
- Updated release metadata to reflect `v0.6.9` as the current public GitHub release and `v0.6.8` as historical.
- Updated `docs/releases/v0.6.9.md`, `docs/trust/v0.6.9-status.md`, README, SECURITY.md, and `docs/trust/README.md` current status lines to `v0.6.9` public / `v0.6.8` historical / `v0.6.10` next planning line.
- Updated `docs/releases/v0.6.8.md` and `docs/trust/v0.6.8-status.md` to historical state.

### Fixed

### Safety
- No live trading, broker execution, provider execution, risk gate, approval gate, kill switch, or audit behavior changes.
- Tag `v0.6.9` created and GitHub release `v0.6.9` published; PyPI was not published.

## [0.6.8] - 2026-06-10

### Added
- Documented v0.6.8 public-demo-proof candidate selection (`docs/releases/v0.6.8-candidates.md`, `docs/releases/v0.6.8-candidates.json`): CAND-001 (Demo Artifact Index), CAND-002 (Demo Proof Checker), CAND-003 (Reviewer Demo Path Consolidation), and CAND-004 (Demo command smoke validation under smoke/local quick tier) accepted.
- Added `docs/demo-artifact-index.md` (CAND-001), a complete indexed view of every paper-demo artifact, its path, content summary, and safety invariant. Cross-referenced from `README.md`, `docs/demo-paper-workflow.md`, and `docs/external-reviewer-walkthrough.md`.
- Added `scripts/check_demo_proof.py` and `tests/test_demo_proof_checker.py` (CAND-002), a deterministic demo proof checker that validates demo documentation, artifact index consistency, safety invariants, and script/doc alignment without running provider, broker, or trading paths.
- Added `scripts/check_demo_command_smoke.py` and `tests/test_demo_command_smoke.py` (CAND-004), a lightweight static smoke checker that validates the demo script exists, is executable, is referenced in docs, contains paper-only wording, and excludes forbidden high-risk patterns. Integrated into `scripts/smoke_check.sh` and `scripts/local_quick_check.sh`.
- Created `docs/releases/v0.6.8.md` release notes and `docs/trust/v0.6.8-status.md` trust status.
- Added `scripts/check_v068_release_prep.py` and `tests/test_check_v068_release_prep.py` for v0.6.8 release-prep state validation.

### Changed
- Consolidated the reviewer demo path for v0.6.8 CAND-003, aligning README, reviewer walkthrough, demo workflow, artifact index, and demo proof checker references. Fixed README quickstart to use `ATLAS-DEMO` consistently with the demo script, corrected stale `0.6.8` source-version-prepared wording in README, removed over-promise v0.6.8 release-notes-prepared claim from trust center, and replaced ambiguous `production-ready` wording in brokers doc with safer phrasing.
- Bumped package/source version from `0.6.7` to `0.6.8`.
- Updated public docs and checker metadata to reflect `v0.6.7` as the current public GitHub release and `0.6.8` as the source version being prepared.
- Updated `scripts/check_version_consistency.py`, `scripts/check_trust_center.py`, `scripts/check_public_launch_readiness.py`, `scripts/check_stable_release_decision.py`, `scripts/check_final_rc_audit.py`, `scripts/check_reviewer_onboarding.py`, `scripts/build_release_evidence_bundle.py`, and `scripts/doctor.py` package version metadata from `0.6.7` to `0.6.8`.
- Updated `scripts/check_onboarding_docs.py` current package version from `0.6.7` to `0.6.8` and next planned release from `v0.6.8` to `v0.6.9`.
- Updated `scripts/main_health.py` expected source version from `0.6.7` to `0.6.8` and next unrequested release tag from `v0.6.8` to `v0.6.9`.
- Updated `scripts/check_generated_artifacts.py` tracked versioned evidence prefixes to include `v0.6.8`.

### Fixed

### Safety

## [0.6.7] - 2026-06-09

### Added
- Documented v0.6.7 public-onboarding candidate selection (`docs/releases/v0.6.7-candidates.md`, `docs/releases/v0.6.7-candidates.json`): CAND-001 (README quickstart front-loading), CAND-002 (demo output expectations and discoverability), and CAND-003 (onboarding docs and checker stale version references) accepted.
- Documented expected output, success criteria, artifact expectations, and common failures for the paper demo (`docs/demo-paper-workflow.md`, `docs/external-reviewer-walkthrough.md`) and reframed the README demo note as a constructive pointer to documented demos (CAND-002).
- Fixed stale onboarding, reviewer, release-readiness, and checker version references across the repository: updated docs to reference the current `v0.6.6` public release, converted `check_onboarding_docs.py` `REQUIRED_FACTS` to use module-level current-release constants, aligned `check_public_launch_messaging.py`, `check_reviewer_outreach.py`, `doctor.py`, and `check_generated_artifacts.py` to current release, and updated corresponding tests (CAND-003).
- Created `docs/releases/v0.6.7.md` release notes and `docs/trust/v0.6.7-status.md` trust status.
- Added `scripts/check_v067_release_prep.py` and `tests/test_check_v067_release_prep.py` for v0.6.7 release-prep state validation.

### Changed
- Front-loaded the README quickstart path for v0.6.7 public onboarding candidate CAND-001: added "Try Atlas in 5 minutes" section immediately after the status banner and compressed the "Review and Feedback" link list.
- Updated public docs and checker metadata to reflect `v0.6.6` as the then-current public GitHub release and `0.6.7` as the source version being prepared.
- Updated `scripts/check_version_consistency.py`, `scripts/check_trust_center.py`, `scripts/check_public_launch_readiness.py`, `scripts/check_stable_release_decision.py`, `scripts/check_final_rc_audit.py`, `scripts/check_reviewer_onboarding.py`, `scripts/build_release_evidence_bundle.py`, and `scripts/doctor.py` package version metadata from `0.6.6` to `0.6.7`.
- Updated `scripts/check_onboarding_docs.py` current package version from `0.6.6` to `0.6.7` and next planned release from `v0.6.7` to `v0.6.8`.
- Updated `scripts/main_health.py` expected source version from `0.6.6` to `0.6.7` and next unrequested release tag from `v0.6.7` to `v0.6.8`.
- Updated `scripts/check_generated_artifacts.py` tracked versioned evidence prefixes to include `v0.6.7`.
- Bumped package/source version from `0.6.6` to `0.6.7`.

### Fixed

### Safety
- The v0.6.7 release-prep updates do not change trading, broker, provider, risk, approval, or kill-switch behavior.
- `v0.6.7` was tagged and released on 2026-06-09.
- `v0.6.7` release cutover was approved and completed.

## [0.6.6] - 2026-06-09

### Added
- Added v0.6.6 maintenance planning notes after the v0.6.5 release (`docs/releases/v0.6.6-plan.md`).
- Documented v0.6.6 patch candidate selection (`docs/releases/v0.6.6-candidates.md`): CAND-001 (v0.6.6 release prep checker skeleton), CAND-002 (checks-reference.md stale wording), and CAND-003 (public docs consistency checker expansion) accepted.
- Added `scripts/check_v066_release_prep.py` and `tests/test_check_v066_release_prep.py` for v0.6.6 release-prep state validation in planning and future release-prep modes (CAND-001).
- Expanded `scripts/check_public_docs_consistency.py` and `tests/test_public_docs_consistency.py` to validate that the README status line matches the current public release and warn on orphaned release notes not referenced in CHANGELOG (CAND-003).
- Aligned `docs/releases/v0.6.6-candidates.md` section headings with the v0.6.6 release-prep checker so the unsafe-candidates scan is genuinely active (`## Accepted Candidates` added, `## Rejected items` renamed to `## Rejected / Out-of-Scope Candidates`).
- Added missing CHANGELOG reference to `docs/releases/v0.5.8.1.md` so the orphan release-note warning clears.
- Created `docs/releases/v0.6.6.md` release notes and `docs/trust/v0.6.6-status.md` trust status.

### Changed
- Bumped package/source version from `0.6.5` to `0.6.6`.
- Updated public docs and checker metadata to reflect `v0.6.5` as the current public GitHub release and `0.6.6` as the prepared source version.
- Updated `SECURITY.md` supported versions table to list `0.6.6` as the current source version on `main` and `0.6.5` as the current public GitHub release.
- Updated `docs/trust/v0.6.6-status.md` from version-prepared wording to prepared-but-not-yet-tagged wording.
- Updated `docs/development/checks-reference.md` to describe v0.6.5 release prep checks as historical and note v0.6.6 as the next planning line (CAND-002).

### Fixed

### Safety
- The v0.6.6 release-prep updates do not change trading, broker, provider, risk, approval, or kill-switch behavior.
- No tag, GitHub release, or PyPI publish was performed in this batch.
- `v0.6.6` is version-prepared; tag and release cutover require separate owner approval.

## [0.6.5] - 2026-06-07

### Added
- Added v0.6.5 maintenance planning notes after the v0.6.4 release-assurance checker fix (`docs/releases/v0.6.5-plan.md`, `docs/releases/v0.6.5-candidates.md`, `docs/releases/v0.6.5-candidates.json`).
- Finalized v0.6.5 candidate selection: CAND-003 (regression test for `security_md_current`), CAND-004 (release checklist version references), CAND-005 (JSON determinism), and CAND-006 (v0.6.5 release prep checker skeleton) accepted.
- Added `scripts/check_v065_release_prep.py` and `tests/test_v065_release_prep.py` for v0.6.5 release-prep state validation in planning and future release-prep modes.
- Added CAND-003 regression test in `tests/test_release_assurance.py` proving `security_md_current` validates against package version, not tag string.
- Created `docs/releases/v0.6.5.md` release notes and `docs/trust/v0.6.5-status.md` trust status.

### Changed
- Bumped package/source version from `0.6.4` to `0.6.5`.
- Updated `docs/release-checklist.md` tag example from stale `v0.6.3` to current `v0.6.4`.
- Hardened deterministic JSON output in `scripts/check_v065_candidates.py` and `scripts/check_v065_release_prep.py` by adding `sort_keys=True` to all `json.dumps` calls.
- Updated public docs and checker metadata to reflect `v0.6.4` as the current public GitHub release and `0.6.5` as the prepared source version.

### Fixed
- Fixed release assurance `SECURITY.md` validation to compare supported versions against the package version without the leading `v` tag prefix.
- Updated public release documentation to consistently describe `v0.6.4` as the current GitHub release (CAND-001).
- Updated version-consistency metadata to use the current public tag `v0.6.4` while preserving package-version checks for `0.6.4` (CAND-002).

### Safety
- The v0.6.5 release-prep updates do not change trading, broker, provider, risk, approval, or kill-switch behavior.
- No tag, GitHub release, or PyPI publish was performed in this batch.
- `v0.6.5` is version-prepared; tag and release cutover require separate owner approval.

## [0.6.4] - 2026-06-07

### Added
- Added post-v0.6.3 planning notes for v0.6.4 maintenance candidate selection (`docs/releases/v0.6.4-plan.md`).
- Added v0.6.4 patch candidate selection documentation (`docs/releases/v0.6.4-candidates.md`) and machine-readable inventory (`docs/releases/v0.6.4-candidates.json`) to separate safe maintenance candidates from deferred or runtime-sensitive work.
- Added `scripts/check_v064_candidates.py` and `tests/test_v064_candidates.py` to verify candidate selection structure, safety boundaries, and absence of premature version bumps or release claims.
- Added `scripts/check_v064_release_prep.py` and `tests/test_v064_release_prep.py` to validate v0.6.4 release prep state in both planning mode (before version bump) and release-prep mode (after version bump).
- Added `docs/releases/v0.6.4.md` release notes and `docs/trust/v0.6.4-status.md` trust status.

### Changed
- Bumped package/source version from `0.6.3` to `0.6.4`.
- Updated public docs (README, SECURITY, trust center, release readiness, public launch readiness, capability inventory, checks reference, main health, release checklist) to reflect `v0.6.3` as the current public GitHub release and remove stale "version-prepared" wording.
- Hardened `scripts/main_health.py` release metadata checks by centralizing constants into a `ReleaseMetadata` dataclass with a `validate()` method that detects drift against local git tags and source version. Tests now verify drift detection.
- Hardened package distribution checker diagnostics: `--dry-run` plan now explicitly documents `--no-deps` behavior; missing `build` and `twine` tooling yields actionable install hints instead of bare messages. Tests verify hints and plan clarity.
- Improved generated-artifact hygiene guidance: `scripts/check_generated_artifacts.py` now emits copy-paste-ready `mv` backup commands for untracked local evidence artifacts, with explicit warnings against `git clean`, `git reset --hard`, and destructive stash operations. Tests verify exact-path guidance and disallowed-command warnings.
- Improved release-assurance artifact hygiene: `scripts/release_assurance.py` now marks outputs as `local_only_evidence` in the summary JSON and includes a "Local Evidence" section in the report with deterministic cleanup instructions. Tests verify local-only metadata and cleanup guidance.
- Standardized PyPI non-publish messaging across README, release notes, trust center, and release readiness docs to consistently use "PyPI was not published". Tests verify consistent negated phrasing and absence of positive publish claims.
- Fixed stale `v0.6.2` current-release references in `docs/public-launch-readiness.md`, `docs/release-checklist.md`, `README.md`, and `docs/development/checks-reference.md` to correctly describe `v0.6.3` as the current stable public GitHub release. Tests verify no stale v0.6.2 claims remain.
- Hardened deterministic ordering in `src/atlas_agent/research/provider_execution_readiness_report.py` by replacing `list(set(...))` with `sorted(set(...))` for artifact lists, preventing nondeterministic JSON output. Added regression tests to enforce no `list(set(...))` patterns in source code and to verify the existing `sorted(_FORBIDDEN_PATTERNS)` fix for pytest-xdist collection stability.

### Fixed

### Safety
- The planning and docs updates do not change trading, broker, provider, risk, approval, or kill-switch behavior.
- The main-health hardening does not change trading, broker, provider, risk, approval, or kill-switch behavior.
- The release-assurance and PyPI messaging updates do not change trading, broker, provider, risk, approval, or kill-switch behavior.
- The release-doc consistency and CI-determinism updates do not change trading, broker, provider, risk, approval, or kill-switch behavior.

## [0.6.3] - 2026-06-06

### Added
- Added `docs/releases/v0.6.3.md` release notes and `docs/trust/v0.6.3-status.md` trust status.
- Added `scripts/check_v063_release_prep.py` and `tests/test_v063_release_prep.py` to verify v0.6.3 release prep state.

### Changed
- Bumped package/source version from `0.6.2` to `0.6.3`.
- Updated version-aware local checks (`check_version_consistency.py`, `check_trust_center.py`, `check_public_docs_consistency.py`, `check_public_launch_readiness.py`, `check_stable_release_decision.py`, `check_reviewer_onboarding.py`, `check_package_distribution.py`, `check_clean_install.py`, `check_final_rc_audit.py`, `check_rc1_cutover.py`, `check_v058_rc1_readiness.py`, `check_v0581_hotfix_cutover.py`, `main_health.py`, `release_assurance.py`, `build_release_evidence_bundle.py`) to recognize `0.6.3`.
- Updated `scripts/check_v061_release_prep.py` to also accept `0.6.3` as a valid post-bump state while still verifying v0.6.1 artifacts exist and rejecting v0.6.4.md.
- Updated `scripts/check_v062_release_prep.py` to accept `0.6.3` as a valid post-bump state, accept `v0.6.3.md` existing, and reject v0.6.4.md while still verifying v0.6.2 artifacts exist.
- Updated public docs (README, SECURITY, trust center, release readiness, public launch readiness, release checklist, checks reference, capability inventory) to reflect `v0.6.3` as the prepared source version and `v0.6.2` as the current public GitHub release.

### Fixed
- Hardened package distribution checker runtime dependency verification, including explicit `pydantic` metadata validation.
- Separated `--no-deps` install checks from wheel-installed `atlas init` so dependency-free installs no longer fail when runtime dependencies are absent.
- Guarded `atlas init` in package distribution checks so it only runs when runtime dependencies are confirmed present.
- Confirmed `twine>=4.0` and `.[dev]` install paths in CI/release gates for package distribution tooling.

### Safety
- No live trading, provider execution, broker execution, risk gate, approval queue, or kill switch changes.
- No new runtime features, broker adapters, or provider integrations.
- No PyPI publish performed.

## [0.6.2] - 2026-06-06

### Added
- Added `docs/releases/v0.6.2.md` release notes and `docs/trust/v0.6.2-status.md` trust status.
- Added `scripts/check_v062_release_prep.py` and `tests/test_v062_release_prep.py` to verify v0.6.2 release prep state.

### Changed
- Bumped package/source version from `0.6.1` to `0.6.2`.
- Updated public release identity docs (README, SECURITY, trust center, release readiness, public launch readiness) to reflect `v0.6.2` as the current public GitHub release after cutover.
- Updated version-aware local checks (`check_version_consistency.py`, `check_trust_center.py`, `check_public_docs_consistency.py`, `check_public_launch_readiness.py`, `check_stable_release_decision.py`) to recognize `0.6.2`.
- Updated `scripts/check_v061_release_prep.py` to accept `0.6.2` as a valid post-bump state while still verifying v0.6.1 artifacts exist.
- Hardened release assurance output ordering so JSON and checksum evidence remains deterministic across local and CI runs.

### Fixed
- Fixed post-release CI failures discovered after v0.6.1 tag/release:
  - `tests/test_discipline_profile.py` pytest-xdist collection mismatch via `sorted(_FORBIDDEN_PATTERNS)`.
  - `tests/test_provider_policy_docs.py` notification urllib allowlist for `notifications/transports.py`.
  - Stale v0.6.1 public docs corrected.
  - v0.6.1 release assurance wording aligned.
  - Package distribution checker artifact discovery and staged `.egg-info` detection hardened.
  - Release assurance updater dry-run no longer uses shell invocation.

### Safety
- No live trading, provider execution, broker execution, risk gate, approval queue, or kill switch changes.
- No new runtime features, broker adapters, or provider integrations.
- No PyPI publish performed.

## [0.6.1] - 2026-06-06

### Added
- Added a v0.6.1 maintenance planning document covering post-release verification, known follow-ups, and patch criteria.
- Added `scripts/check_runtime_diagnostics.py`, a read-only helper that documents expected check runtimes, focused subsets, and timeout triage guidance.
- Added a v0.6.1 patch candidate selection document (`docs/releases/v0.6.1-candidates.md`) and machine-readable inventory (`docs/releases/v0.6.1-candidates.json`) to separate safe maintenance candidates from deferred or runtime-sensitive work.
- Added `scripts/check_v061_candidates.py` and `tests/test_v061_candidates.py` to verify candidate selection structure, safety boundaries, and absence of premature version bumps or release claims.
- Added `scripts/check_v061_release_prep.py` and `tests/test_v061_release_prep.py` to verify v0.6.1 release prep state.
- Added `docs/releases/v0.6.1.md` release notes and `docs/trust/v0.6.1-status.md` trust status.

### Changed
- Bumped package/source version from `0.6.0` to `0.6.1`.
- Implemented selected v0.6.1 maintenance candidates for post-release status docs (CAND-001), capability inventory labeling (CAND-002), post-release readiness CI coverage (CAND-003), and checks-reference cross-links (CAND-005).
- Updated `scripts/check_v060_readiness.py` to treat `gh` authentication failures as warnings instead of errors in post-release mode, preventing CI flakiness while preserving tag and docs checks.
- Added v0.6 post-release readiness check to CI `quick-gate` and matching workflow tests.
- Added post-release mode (`--post-release`) to the v0.6 readiness checker so `v0.6.0` can be validated after tag and GitHub release publication while preserving the default pre-release behavior.
- Added per-step elapsed timing and total elapsed summary to all local gate scripts (`dev_check.sh`, `ci_check.sh`, `research_check.sh`, `release_check.sh`).
- Updated public release identity docs (README, trust center, SECURITY, launch readiness) to reflect `0.6.1` source version while preserving `v0.6.0` as the latest tagged GitHub release.

### Fixed
- Fixed `test_discipline_show_default` and `test_discipline_validate_no_file` to run in isolated temporary directories, preventing failures when a local `.atlas/discipline.md` exists.
- Fixed `tests/test_v060_readiness.py` post-release tests to be deterministic and offline-safe by mocking `_check_v060_tag` and `_check_github_release` instead of relying on real local git tags or GitHub release visibility.

### Safety
- No live trading, provider execution, broker execution, risk gate, approval queue, or kill switch changes.
- No new runtime features, broker adapters, or provider integrations.
- No PyPI publish, tag creation, or GitHub release creation performed in this prep batch.

## [0.6.0] - 2026-06-05

### Added
- Prepared v0.6.0 release identity and release notes.
- Added a broker support inventory (`BrokerSupportEntry`) documenting status for PaperBroker, Alpaca, Binance, CCXT, and IBKR.
- Added fail-closed broker guard helpers (`guard_submit`, `guard_sync`) in `src/atlas_agent/brokers/guards.py`.
- Added `atlas broker status` CLI command for read-only broker support inventory and runtime status output.
- Added `docs/broker-roadmap.md` with broker status table, fail-closed behavior, and CLI usage.
- Added comprehensive broker status, guard, fail-closed, and CLI tests (`tests/brokers/test_broker_status.py`, `tests/brokers/test_broker_guards.py`, `tests/brokers/test_unsupported_brokers_fail_closed.py`, `tests/cli/test_brokers_cli.py`).
- Added a safe notification foundation with disabled, dry-run, and Slack webhook transport modes, redaction, structured delivery results, and local audit storage.
- Added `atlas notifications test/send` CLI commands with `--transport` and `--severity` flags, defaulting to dry-run mode.
- Added `src/atlas_agent/notifications/models.py`, `redaction.py`, `transports.py`, `dispatcher.py`, `storage.py` for safe, testable notification delivery.
- Enhanced the read-only local dashboard UI with structured sections for system health, safety status, reports, backtests, reflections, skills, learning suggestions, audit events, warnings, and missing data.
- Added `docs/dashboard.md` documenting dashboard scope, safety boundaries, CLI usage, missing-data behavior, and no-external-asset constraints.
- Added a real local report generator foundation for daily, weekly, and ad-hoc Markdown/JSON reports using available local data only.
- Added `atlas report generate --type daily|weekly|ad-hoc --format markdown|json` with real portfolio, backtest, research, risk, audit, and system health sections.
- Added `src/atlas_agent/reports/models.py`, `sources.py`, `generator.py`, `renderers.py`, and `adhoc.py` for local-data-only report generation.
- Added `docs/reports.md` documenting report scope, safety, and CLI usage.
- Added unit tests for report generator, renderers, and CLI (`tests/reports/test_report_generator.py`, `tests/reports/test_report_renderers.py`, `tests/cli/test_report_cli.py`).
- Added a local-first reflection artifact foundation with structured artifacts, dry-run/static generation, provenance metadata, and approval/rejection state handling.
- Added `atlas reflection create/list/show/submit/approve/reject/archive` CLI commands.
- Added `src/atlas_agent/reflection/models.py`, `storage.py`, `generator.py`, `approval.py`, `renderers.py` for offline reflection generation.
- Added `docs/reflection.md` documenting reflection scope, safety, status lifecycle, and CLI usage.
- Added unit tests for reflection models, storage, generator, approval, and CLI (`tests/reflection/`, `tests/cli/test_reflection_cli.py`).
- Added a local-first skill candidate foundation with structured candidate artifacts, provenance metadata, approval/rejection workflows, and manual-only promotion into a local skill library.
- Added `atlas skills create-candidate/list-candidates/show-candidate/submit-candidate/approve-candidate/reject-candidate/archive-candidate/promote-candidate/list-library/show-library` CLI commands.
- Added `src/atlas_agent/skills/models.py`, `storage.py`, `generator.py`, `approval.py`, `library.py`, `renderers.py` for offline skill candidate generation.
- Added `docs/skills.md` documenting skill candidate scope, safety, status lifecycle, and CLI usage.
- Added unit tests for skill candidate models, storage, generator, approval, library, and CLI (`tests/skills/`, `tests/cli/test_skills_cli.py`).
- Added a local-first learning suggestion foundation with structured suggestion artifacts, reflection/skill/file provenance, review workflows, and advisory-only execution policy.
- Added `atlas learning suggest/list-suggestions/show-suggestion/submit-suggestion/accept-suggestion/reject-suggestion/archive-suggestion` CLI commands.
- Added `src/atlas_agent/learning/models.py`, `storage.py`, `generator.py`, `approval.py`, `renderers.py` for offline learning suggestion generation.
- Added `docs/learning-loop.md` documenting learning suggestion scope, safety, status lifecycle, and CLI usage.
- Added unit tests for learning suggestion models, storage, generator, approval, renderers, and CLI (`tests/learning/`, `tests/cli/test_learning_cli.py`).
- Added the v0.6.1 backtesting strategy pack with `moving_average_cross`, `rsi_mean_reversion`, and registered `buy_and_hold`.
- Added typed strategy parameter specs, parameter coercion, and fail-closed parameter validation.
- Added CLI strategy parameter overrides for `atlas backtest run` and `atlas backtest validate`.
- Added backtest run configuration fields for strategy parameters and benchmark selection.
- Added a local-only SPY benchmark abstraction requiring explicit local benchmark CSV data.
- Added full strategy-pack tests for registry, validation, signal generation, benchmarks, config defaults, and CLI behavior.

### Changed
- Updated strategy example configs to use the v0.6.1 strategy IDs and parameters.
- Kept the existing deterministic buy-and-hold order ID format while adding strategy-pack order IDs for new strategies.

### Safety
- Broker support inventory formalizes PaperBroker as `default_paper`, Alpaca as `supported_opt_in`, Binance as `partial`, CCXT as `disabled`, and IBKR as `placeholder`. No status enables live submit by default.
- Fail-closed broker guards (`guard_submit`, `guard_sync`) block unsupported, disabled, and placeholder broker execution paths with clear `BrokerConfigurationError` messages.
- `atlas broker status` is read-only and local; it does not call broker APIs, read credentials, or submit orders.
- No live trading default changes. No live submit default changes. No broker execution default changes. No provider execution default changes. Risk gates, approval queue, and kill-switch remain unchanged.
- No real broker API calls are made in broker status/guard tests. No real credentials are required.
- Notifications remain disabled/dry-run by default, redact webhook secrets, avoid network calls in tests, and never alter trading, provider, broker, skill, or learning execution state.
- Dashboard UI remains static, local, read-only, research-only, and does not expose trading, provider, broker, skill activation, or learning execution controls.
- Dashboard rendering shows missing data and warnings explicitly without fake content, provider calls, broker calls, external scripts, or CDN dependencies.
- No live trading default changes.
- No provider execution default changes.
- No broker execution default changes.
- No approval gate changes.
- No kill-switch changes.
- No audit hash-chain or manifest bypass.
- No network benchmark data fetch was added.
- No strategy performance claims added.
- Added backtest report rendering (JSON and Markdown research summaries) with research-only disclaimer.
- Added `atlas backtest run --report json|markdown` for direct report output.
- Added `atlas report generate` subcommand with `--format json|markdown|text` and `--output` support.
- Added empty-data and missing-benchmark report fallback renderers.
- Added e2e tier1 tests for backtest report and `atlas report generate` CLI flows.
- Added unit tests for backtest report module (28 tests).
- Reports remain local, offline, research-only, and do not call providers, brokers, or external services.
- Missing data is shown explicitly; no fake content, no financial advice, no profit guarantees.
- Reflection artifacts remain offline, research-only, provider-disabled by default, broker-disabled by default, and require operator review before downstream use.
- Reflection static fallback clearly marks `provider_execution_disabled` and does not generate fake insights.
- Skill candidates remain offline, research-only, manually reviewed, and never auto-activated. Provider execution, broker execution, and live trading remain disabled by default.
- Skill candidate static fallback clearly marks `provider_execution_disabled` and preserves the marker from source reflection artifacts.
- Skill library entries inherit `manual_only` activation policy and cannot be auto-activated.

## [0.5.9.5] - 2026-06-04

### Fixed
- Kept release assurance updater dry-run checks local by running them in an isolated temporary workspace.

### Changed
- Updated source package metadata from `0.5.9.4` to `0.5.9.5`.
- Updated public release identity from `v0.5.9.4` to `v0.5.9.5`.

### Safety
- No live trading default changes.
- No provider execution default changes.
- No broker execution default changes.
- No runtime trading behavior changes.
- PyPI publish was not performed.

## [0.5.9.4] - 2026-06-04

### Changed
- Modernized GitHub Actions workflow dependencies to Node 24-compatible action majors.
- Updated `actions/checkout` usage to `@v6`.
- Updated `actions/setup-python` usage to `@v6`.
- Updated `actions/upload-artifact` usage to `@v6` where artifact upload is used.
- Updated source package metadata from `0.5.9.3` to `0.5.9.4`.
- Runtime trading behavior did not change.

### Added
- Added workflow action version guard coverage to prevent regression to deprecated action majors.
- Added GitHub Actions maintenance guidance covering Node 24 runner compatibility and workflow safety boundaries.

### Safety
- No live trading default changes.
- No provider execution default changes.
- No broker execution default changes.
- No runtime trading behavior changes.
- Public GitHub release cutover is authorized for `v0.5.9.4`.
- PyPI publish was not performed.

## [0.5.9.3] - 2026-06-04

### Added
- Added a post-push main health reporting script and guide for verifying local `main`, pushed commits, CI visibility, artifact hygiene, protected-boundary status, and release/tag safety after direct-main maintenance updates.

### Changed
- Updated source package metadata from `0.5.9.2` to `0.5.9.3`.
- Clarified post-push direct-main verification guidance for maintainers.
- Runtime trading behavior did not change.

### Safety
- No live trading default changes.
- No provider execution default changes.
- No broker execution default changes.
- No runtime trading behavior changes.
- No tag, GitHub release, or PyPI publish was performed.

## [0.5.9.2] - 2026-06-04

### Added
- Added generated artifact hygiene guidance and checking for local evidence outputs.

### Changed
- Updated source package metadata from `0.5.9.1` to `0.5.9.2`.
- Clarified which generated artifact outputs are local-only and should not be staged unless explicitly requested.
- Runtime trading behavior did not change.

### Safety
- No live trading default changes.
- No provider execution default changes.
- No broker execution default changes.
- No runtime trading behavior changes.

## [0.5.9.1] - 2026-06-04

### Changed
- Bumped package/source metadata from `0.5.9` to `0.5.9.1` for direct-main maintenance work.
- Updated version-aware local checks and public current-status references to recognize `0.5.9.1` as the current source package version while keeping `v0.5.9` as the latest actual public release.
- Runtime behavior did not change.

### Safety
- No live trading default changes.
- No provider execution default changes.
- No broker execution default changes.

## [0.5.9] - 2026-06-03

### Security
Security hardening:
- redaction refresh after secret load/set
- short/low-entropy secret redaction regression coverage
- secret key-name validation
- Alpaca live/paper endpoint consistency hardening
- timeout reconciliation guidance
- dashboard/read-only surface documentation
- approval path safety documentation/tests
- config store safety tests
- Telegram/remote-control status clarification

### Audit
Provider audit evidence:
- provider preflight call-plan
- validation
- evidence bundle
- bundle verifier
- smoke chain
- capability inventory/readiness gate
- evidence index
- evidence report/export
- audit pack
- audit pack verifier
- manual CI audit-pack artifact workflow

### Safety
- This release does not enable live trading by default.
- This release does not enable provider execution by default.
- This release does not authorize autonomous trading.
- This release is not financial advice.

## [0.5.8.1] - 2026-06-01

> See [release notes](docs/releases/v0.5.8.1.md) for full details.

### Fixed
- Fixed runtime template packaging so `atlas init --template routine-trader` works from clean wheel/sdist installs outside the source checkout.

### Tests
- Added/updated artifact install checks covering packaged templates.

### Safety
- No live trading, provider execution, broker execution, credential loading, package publishing, or GitHub Release creation was performed.
- No protected runtime boundaries were changed.

## [0.5.8] - 2026-06-01

### Added
- Stable v0.5.8 release notes and final public-release metadata.

### Fixed
- Promoted the final green `v0.5.8rc5` release candidate to stable `v0.5.8`.

### Safety
- No live trading, provider execution, broker execution, credential loading, package publishing, or GitHub release creation was performed.
- No protected runtime boundaries were changed.
- Stable status does not imply profitability, live-trading readiness, or financial advice.

## [0.5.8rc5] - 2026-06-01

> **Release candidate.** Not a stable final release. See [release notes](docs/releases/v0.5.8-rc5.md) for full details.

### Fixed
- Fixed reviewer golden-path smoke diagnostics so the optional `release_check.sh --quick` step preserves captured stdout/stderr.
- Fixed reviewer-facing README and walkthrough documentation inconsistencies.

### Documentation
- Updated README current RC status and release-notes link.
- Documented local safe diagnostic commands used by the reviewer golden path.

### Safety
- No live trading, provider execution, broker execution, credential loading, tag publishing, package publishing, or GitHub release creation was performed.
- No protected runtime boundaries were changed.
- No network calls were added.

## [0.5.8rc4] - 2026-06-01

> **Release candidate.** Not a stable final release. See [release notes](docs/releases/v0.5.8-rc4.md) for full details.

### Fixed
- Superseded the already-consumed `v0.5.8rc3` tag by preparing `v0.5.8rc4` as the active release candidate.
- Updated RC cutover checks and docs so historical RC tags do not block the active RC line.

### Safety
- No live trading, provider execution, broker execution, credential loading, tag publishing, package publishing, or GitHub release creation was performed.
- No protected boundaries were changed.
- No network calls were added.

## [0.5.8rc2] - 2026-05-29

> **Release candidate.** Not a stable final release. See [release notes](docs/releases/v0.5.8-rc2.md) for full details.

### Fixed
- Fixed RC cutover verification so an existing RC tag is accepted only when it resolves to the current HEAD. Historical RC tags (e.g., `v0.5.8rc1`) are allowed without requiring them to match current HEAD.

### Safety
- No live trading, provider execution, broker execution, credential loading, tag publishing, package publishing, or GitHub release creation was performed.
- No protected boundaries were changed.
- No network calls were added.

## [0.5.8rc1] - 2026-05-29

> **Release candidate.** Not a stable final release. See [release notes](docs/releases/v0.5.8-rc1.md) for full details.

### Added
- Added CLI command compatibility contract and local check to guard public command families.
- Added deterministic reviewer golden-path smoke test for safe local onboarding.
- Added local release evidence bundle generator.
- Added public feedback intake templates, taxonomy, and triage checker.
- Added controlled reviewer outreach pack with safe copy-paste review requests.
- Added product capability inventory and local gap-audit check.
- Added v0.5.8 gap prioritization plan.
- Added v0.5.8 RC1 readiness dry-run gate and documentation.
- Added v0.5.8 RC1 cutover checker and documentation.

### Changed
- Refactored CLI command structure to reduce the size of the main CLI module while preserving research command compatibility.
- Enhanced reviewer golden-path smoke test with per-step diagnostic categories and suggested fixes on failure.
- Improved product capability inventory docs with "How to read this document" section and gap-prioritization link.

### Fixed
- Updated legacy RC cutover check to accept post-v0.5.7 development and RC versions while the historical `v0.5.7` tag remains verified.
- Hardened tests against local environment PermissionError failures via test environment isolation.
- Addressed v0.5.8 must-fix release-readiness gaps:
  - Clarified provider execution boundary in README (governed by artifact-based safety policy and risk manager, not a runtime network block).
  - Audited public docs for overclaim; confirmed no production-ready or live-trading-readiness overstatements.
  - Enhanced capability inventory checker to verify `safe_to_claim` capabilities have corresponding CLI commands or files.

### Safety
- No intentional live trading enablement.
- No intentional provider execution unlock.
- No intentional broker execution unlock.
- Safety-critical boundaries remain conservative and require review before release.
- The CLI compatibility check, golden-path smoke test, release evidence bundle, and historical release record check are all local-only and do not call providers, brokers, load credentials, submit orders, or enable live trading.
- Feedback intake docs and templates explicitly reject credential sharing, safety-bypass requests, real-money broker setup, and profitability/trading-signal evaluation.
- Feedback taxonomy docs classify live-trading, broker, provider, credential, and safety-bypass requests as safety-sensitive or out-of-scope by default.
- Reviewer outreach drafts explicitly avoid profitability claims, live-trading readiness claims, broker setup requests, credential sharing, and safety-bypass requests.
- Capability inventory marks live trading, provider execution, broker execution, credentials, and profitability-related areas as disabled, safety-sensitive, or not safe to claim unless explicitly verified.
- The v0.5.8 prioritization explicitly defers or rejects live trading, broker execution, provider execution, autonomous real-money operation, credential sharing, and profitability/trading-signal claims.

## [0.5.7] - 2026-05-26

### Release Engineering
- Stable v0.5.7 release decision from RC9.
- Added stable release decision doc (`docs/stable-release-decision.md`) documenting the decision to prepare stable v0.5.7.
- Added stable release checklist (`docs/stable-release-checklist.md`) for pre-tag verification.
- Added `scripts/check_stable_release_decision.py` for local static verification of stable release readiness.
- Added `tests/test_stable_release_decision.py` with safety and structure tests for stable release decision.
- Updated final RC audit docs to reference stable release decision materials.
- Updated README current status to stable v0.5.7.
- Updated public docs version references to stable v0.5.7.
- Updated `docs/release-checklist.md` with stable release decision gate.
- Updated CI quick gate to include stable release decision check.
- Package version cutover to `0.5.7` (package) / `v0.5.7` (public tag).
- No runtime behavior changes in this batch.
- No broker/execution/risk/config/safety boundary changes.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the stable release workflow.
- No credentials loaded by the stable release workflow.
- No network enabled by Atlas runtime in CI.
- No publish, upload, tag, or push performed by CI.
- Not financial advice. Does not imply profitability or trading correctness.
- Does not imply real-money readiness.

## [0.5.7rc9] - 2026-05-26

### Release Engineering
- Ninth release candidate for the v0.5.7 line.
- Added final RC audit doc (`docs/final-rc-audit.md`) with release-manager style audit of the RC series.
- Added final release candidate checklist (`docs/final-release-candidate-checklist.md`) to decide whether to move toward v0.5.7 final.
- Added `scripts/check_final_rc_audit.py` for local static verification of final RC audit materials.
- Added `tests/test_final_rc_audit.py` with safety and structure tests for final RC audit.
- Linked final RC audit and checklist from README and public launch docs.
- Updated `docs/release-checklist.md` with final RC audit gate.
- Updated CI quick gate to include final RC audit check.
- Package version bumped to `0.5.7rc9` (package) / `v0.5.7-rc9` (public tag).
- No runtime behavior changes in this batch.
- No broker/execution/risk/config/safety boundary changes.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the final RC audit workflow.
- No credentials loaded by the final RC audit workflow.
- No network enabled by Atlas runtime in CI.
- No publish, upload, tag, or push performed by CI.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7rc8] - 2026-05-26

### Release Engineering
- Eighth release candidate for the v0.5.7 line.
- Added public launch messaging doc (`docs/public-launch-messaging.md`) with safe draft messaging for feedback requests.
- Added feedback request guide (`docs/feedback-request-guide.md`) explaining how to ask for feedback safely.
- Added public FAQ (`docs/public-faq.md`) answering common visitor questions conservatively.
- Added `scripts/check_public_launch_messaging.py` for local static verification of launch messaging safety.
- Added `tests/test_public_launch_messaging.py` with safety and structure tests for launch messaging.
- Linked launch/reviewer/feedback materials from README and public launch docs.
- Updated `docs/release-checklist.md` with public launch messaging gate.
- Updated CI quick gate to include public launch messaging check.
- Package version bumped to `0.5.7rc8` (package) / `v0.5.7-rc8` (public tag).
- No runtime behavior changes in this batch.
- No broker/execution/risk/config/safety boundary changes.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the public launch messaging workflow.
- No credentials loaded by the public launch messaging workflow.
- No network enabled by Atlas runtime in CI.
- No publish, upload, tag, or push performed by CI.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7rc7] - 2026-05-26

### Release Engineering
- Seventh release candidate for the v0.5.7 line.
- Added external reviewer walkthrough (`docs/external-reviewer-walkthrough.md`).
- Added reviewer checklist (`docs/reviewer-checklist.md`).
- Added `scripts/check_reviewer_onboarding.py` for local static verification of reviewer onboarding materials.
- Added `tests/test_reviewer_onboarding.py` with safety and structure tests for reviewer onboarding.
- Linked reviewer path from README and public launch docs.
- Updated `docs/release-checklist.md` with reviewer onboarding gate.
- Updated CI quick gate to include reviewer onboarding check.
- Package version bumped to `0.5.7rc7` (package) / `v0.5.7-rc7` (public tag).
- No runtime behavior changes in this batch.
- No broker/execution/risk/config/safety boundary changes.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the reviewer onboarding workflow.
- No credentials loaded by the reviewer onboarding workflow.
- No network enabled by Atlas runtime in CI.
- No publish, upload, tag, or push performed by CI.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7rc6] - 2026-05-26

### Release Engineering
- Sixth release candidate for the v0.5.7 line.
- Added public launch readiness docs and checks.
- Added `docs/public-launch-readiness.md` explaining public launch status, verified checks, and known limitations.
- Added `docs/github-repo-settings.md` with recommended repository settings for public review.
- Added `scripts/check_public_launch_readiness.py` for local static verification of launch materials.
- Added `tests/test_public_launch_readiness.py` with safety and structure tests for launch readiness.
- Hardened README for public review with explicit "What this is" and "What this is not" sections.
- Updated `docs/release-checklist.md` with public launch readiness gate.
- Updated CI quick gate to include public launch readiness check.
- Package version bumped to `0.5.7rc6` (package) / `v0.5.7-rc6` (public tag).
- No runtime behavior changes in this batch.
- No broker/execution/risk/config/safety boundary changes.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the public launch workflow.
- No credentials loaded by the public launch workflow.
- No network enabled by Atlas runtime in CI.
- No publish, upload, tag, or push performed by CI.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7rc5] - 2026-05-26

### Release Engineering
- Fifth release candidate for the v0.5.7 line.
- Added public repository hygiene pack.
- Added `SECURITY.md` and `CONTRIBUTING.md`.
- Added GitHub issue templates (bug report, docs issue, safety concern, feature request) and PR template.
- Added `docs/public-repo-hygiene.md` explaining the public contribution and safety model.
- Added `tests/test_public_repo_hygiene.py` with safety and structure tests for repo hygiene files.
- Updated `docs/release-checklist.md` with public repo hygiene gate.
- Package version bumped to `0.5.7rc5` (package) / `v0.5.7-rc5` (public tag).
- No runtime behavior changes in this batch.
- No broker/execution/risk/config/safety boundary changes.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the repo hygiene workflow.
- No credentials loaded by the repo hygiene workflow.
- No network enabled by Atlas runtime in CI.
- No publish, upload, tag, or push performed by CI.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7rc4] - 2026-05-26

### Release Engineering
- Fourth release candidate for the v0.5.7 line.
- CI release gate parity: aligned GitHub Actions with local RC verification stack.
- Added clean install verification and package distribution dry-run to CI quick gate.
- Added public docs consistency, README quickstart verification, and RC cutover check to CI.
- Restructured CI into fast PR gate and manual heavy release gate.
- Added `docs/ci-release-gates.md` documenting CI structure.
- Package version bumped to `0.5.7rc4` (package) / `v0.5.7-rc4` (public tag).
- No runtime behavior changes in this batch.
- No broker/execution/risk/config/safety boundary changes.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the CI workflow.
- No credentials loaded by the CI workflow.
- No network enabled by Atlas runtime in CI.
- No publish, upload, tag, or push performed by CI.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7rc3] - 2026-05-26

### Release Engineering
- Third release candidate for the v0.5.7 line.
- Added `scripts/check_package_distribution.py` for local packaging/distribution dry-run verification.
- Added `tests/test_package_distribution_check.py` with safety and structure tests.
- Added `docs/package-distribution-verification.md`.
- Updated `docs/release-checklist.md` with package distribution dry-run as RC gate.
- Package version bumped to `0.5.7rc3` (package) / `v0.5.7-rc3` (public tag).
- No runtime behavior changes in this batch.
- No broker/execution/risk/config/safety boundary changes.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the package distribution workflow.
- No credentials loaded by the package distribution workflow.
- No network enabled by the package distribution workflow.
- No publish, upload, tag, or push performed by the package distribution workflow.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7rc2] - 2026-05-25

### Release Engineering
- Second release candidate for the v0.5.7 line.
- Added `scripts/check_clean_install.py` for local clean-install verification.
- Added `tests/test_clean_install_check.py` with 18+ safety tests.
- Added `docs/clean-install-verification.md`.
- Updated `docs/release-checklist.md` with clean-install verification as RC gate.
- No runtime behavior changes.
- Sandbox/paper/preflight positioning.
- Clean-install verification confirms no credentials, no network, no broker/provider contact, no live trading enablement.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the clean-install workflow.
- No credentials loaded by the clean-install workflow.
- No network enabled by the clean-install workflow.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7rc1] - 2026-05-25

### Release Engineering
- First release candidate for the v0.5.7 line.
- Cutover from `0.5.7.dev50` to `0.5.7rc1` (package) / `v0.5.7-rc1` (public tag).
- No runtime behavior changes.
- Documentation and release-engineering maturity only.
- Sandbox/paper/preflight positioning.
- Release candidate readiness and cutover dry-run checks completed before RC.

### Safety
- Provider execution remains locked.
- Trust remains blocked.
- Live trading disabled by default.
- No broker/order path in the provider safety workflow.
- No credentials loaded by the provider safety workflow.
- No network enabled by the provider safety workflow.
- Not financial advice. Does not imply profitability or trading correctness.

## [0.5.7.dev50] - 2026-05-25

### Documentation
- Synchronized `CHANGELOG.md` with recent dev release notes (dev38–dev49).
- Added release-history hygiene for the future RC path.
- Cross-checked release notes against tags, git history, and version files.

### Release hygiene
- No runtime behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev49] - 2026-05-25

### Added
- Batch 10.2 — Release Candidate Cutover Dry Run.
  - `src/atlas_agent/research/release_candidate_cutover.py`: local, deterministic dry-run report for dev-to-RC transition planning.
  - Validates target RC version shape (e.g. `v0.5.7-rc1`) without tagging, pushing, or publishing.
  - Checks local docs, verification scripts, forbidden claims, protected boundaries, and release checklist entries.
  - Recomputes derived fields during validation so recalculated-hash tampering is rejected.
  - CLI commands: `release-candidate-cutover-dry-run`, `release-candidate-cutover-dry-run-list`, `release-candidate-cutover-dry-run-validate`, `release-candidate-cutover-dry-run-summary`, `release-candidate-cutover-dry-run-doctor`.
  - Fixed summary/list tamper exposure: `validate`, `summarize`, and `iter` now agree on tampered artifact status.

### Safety / Compatibility
- No execution behavior changes.
- No broker adapter changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev48] - 2026-05-24

### Added
- Batch 10.1 — Release Candidate Readiness Report.
  - `src/atlas_agent/research/release_candidate_readiness.py`: local, read-only readiness report for sandbox/paper/preflight release candidate evaluation.
  - Checks version consistency, README quickstart verification, public docs consistency, forbidden claims scan, protected boundaries, and hard-false safety invariants.
  - Produces `readiness_status` and `readiness_score` — never claims live-trading readiness or profitability.
  - CLI commands: `release-candidate-readiness`, `release-candidate-readiness-list`, `release-candidate-readiness-show`, `release-candidate-readiness-validate`, `release-candidate-readiness-summary`, `release-candidate-readiness-doctor`.

### Safety / Compatibility
- No execution behavior changes.
- No broker adapter changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev47] - 2026-05-24

### Added
- Batch 9.10 — Pre-Release Hardening Sweep.
  - `scripts/verify_readme_quickstart.py`: hardened forbidden-claim detection using `re.finditer` and improved secret detection in bash blocks.
  - `scripts/check_public_docs_consistency.py`: new deterministic local script scanning README and public docs for unsafe claims, forbidden fragments, secret-like patterns, and stale version references.
  - `tests/test_public_docs_consistency.py`: 16 tests covering pass-on-current-docs, rejection of unsafe claims, forbidden fragments, and absolute paths.
  - `docs/releases/v0.5.7-dev40-to-dev47-summary.md`: cumulative release map.

### Changed
- README: fixed duplicate heading, stale release-notes link, current-status version references.
- `docs/release-checklist.md`: added `verify_readme_quickstart.py` and `check_public_docs_consistency.py` to required validation commands; added explicit staging reminders.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev46] - 2026-05-23

### Added
- Batch 9.9 — README Quickstart Verification Pack.
  - `scripts/verify_readme_quickstart.py`: programmatically verifies README quickstart commands are safe, consistent, and free of forbidden claims/fragments.
  - `tests/test_readme_quickstart_verification.py`: 21 tests covering README structure, safety wording, forbidden claims, forbidden fragments, and command path safety.

### Changed
- README quickstart reorganized into clear install → create → validate → backtest → inspect steps.
- Added explicit "What is intentionally disabled" subsection.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev45] - 2026-05-23

### Added
- Batch 9.8 — Public Safety Proof Pack.
  - `docs/provider-safety-dossier.md`: public-facing documentation explaining the mock/offline safety chain.
  - `docs/examples/provider-safety-dossier-workflow.md`: safe copy-paste workflow for discovering and exporting dossiers.
  - `tests/test_provider_safety_dossier_docs.py`: docs-truth tests guarding against unsafe claims and forbidden fragments in public docs.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev44] - 2026-05-23

### Added
- Batch 9.7 — Provider Safety Dossier Discovery UX.
  - `atlas research provider-safety-dossier-latest`: returns the latest valid dossier metadata with safe sentinels only.
  - `atlas research provider-safety-dossier-list --status <status>`: filters dossiers by safe status without exposing raw tampered fields.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev43] - 2026-05-23

### Added
- Batch 9.6 — Provider Safety Dossier Markdown Export.
  - `export_provider_safety_dossier_markdown()`: generates safe local Markdown reports from validated dossiers.
  - Scans output for forbidden fragments before writing; fails closed on validation failure.
  - CLI command: `atlas research provider-safety-dossier-export <id> --format markdown --output <path>`.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev42] - 2026-05-23

### Added
- Batch 9.5 — Provider Safety Dossier.
  - `src/atlas_agent/research/provider_safety_dossier.py`: read-only, offline safety report summarizing the completed mock provider safety chain.
  - Traverses the 6-node chain of custody from mock simulation through final safety seal.
  - Reports `chain_complete` / `chain_incomplete` health and `safety_verdict`.
  - Enforces 16 hard-false boolean invariants.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev41] - 2026-05-23

### Added
- Batch 9.4 — Mock Response Final Safety Seal.
  - `src/atlas_agent/research/provider_mock_response_final_safety_seal.py`: terminal artifact in the mock response pipeline.
  - Derived from trust decision blocker artifacts; stores source hash for lineage verification.
  - All dangerous booleans hard-false (~40 flags); safety booleans hard-true (~8 flags).
  - Seal is explicitly non-authorizing.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev40] - 2026-05-22

### Added
- Batch 9.3 — Mock Response Trust Decision Blocker.
  - `src/atlas_agent/research/provider_mock_response_trust_decision_blocker.py`: blocks all trust decisions, trust upgrades, and trading authorization.
  - Derived from mock response review sandbox artifacts.
  - Hardcodes `provider_id="mock"`; all execution/network/credential/broker booleans are `False`.
  - 12 policy sub-dicts document the absence of trust at every boundary.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev39] - 2026-05-22

### Added
- Batch 9.2 — Mock Response Review Sandbox.
  - `src/atlas_agent/research/provider_mock_response_review_sandbox.py`: sandboxed, non-authorizing review layer for mock response import candidates.
  - Hardcodes `provider_id="mock"`; all execution/network/credential/broker booleans are `False`.
  - Deterministic hash, source hash validation, semantic positive-claim validation, forbidden fragment scan.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev38] - 2026-05-22

### Added
- Batch 9.1 — Mock Response Import Candidate.
  - `src/atlas_agent/research/provider_mock_response_import_candidate.py`: local schema-validation sandbox deriving import candidates from existing mock response simulations.
  - Hardcodes `provider_id="mock"`; validates mock-source lineage and structural compatibility.
  - Source hash validation against upstream artifacts; semantic positive-claim scanning.

### Safety / Compatibility
- No execution behavior changes.
- No broker/execution/risk/config/safety changes.
- Live trading remains disabled by default.
- Provider execution remains locked.
- Trust remains blocked.

## [0.5.7.dev37] - 2026-05-21

### Added
- Batch 9.0 — Mock Provider Adapter / Simulated Response.
  - `src/atlas_agent/research/provider_mock_response_simulation.py`: offline mock response artifact lifecycle.
  - `src/atlas_agent/research/provider_adapter_interface.py`: mock-only adapter classes with safe defaults.
  - `MockProviderAdapterCapability`: static descriptor with `supports_mock_response=True` and all real flags false.
  - `MockProviderRequestPreview`: metadata-only preview with `mock_generation_allowed=True` and `real_provider_request_sent=False`.
  - `MockProviderResponseSimulation`: safe placeholder with `manual_review_required=True`.
  - `MockProviderAdapter`: `capabilities()`, `build_request_preview()`, `simulate_response()`, `send()` raises `ProviderAdapterDisabledError`.
  - `create_provider_mock_response_simulation()`: safe creation from adapter contract with validation, lineage, hash, and positive-claim scanning.
  - `safe_validate_provider_mock_response_simulation_data()`: strict validation with hash, lineage, forbidden fragments, impossible boolean checks, and recursive unsafe positive claim detection.
  - `validate_provider_mock_response_simulation_artifact()`: detailed per-check validation.
  - `replay_provider_mock_response_simulation()`: deterministic hash replay.
  - `iter_provider_mock_response_simulation_artifacts()`: safe listing with invalid sentinels.
  - `summarize_provider_mock_response_simulation()`: read-only summary.
  - `doctor_provider_mock_response_simulation()`: read-only chain diagnostic.
  - `validate_provider_id()`: accepts `"mock"` alongside disabled provider IDs.
  - 7 new CLI commands under `atlas research`.
  - Session integration: `check_research_artifacts`, `build_research_timeline`, `build_dossier`.
  - Demo script extended with mock response flow after disabled-smoke and before import-provider-response.
  - Comprehensive test suite: 45 tests.

## [0.5.7.dev36] - 2026-05-21

### Added
- Batch 8.9 — Provider Adapter Interface Contract.
  - `src/atlas_agent/research/provider_adapter_interface_contract.py`: future adapter interface definition with disabled adapter harness.
  - `ProviderAdapterCapability`: static descriptor with all execution flags false.
  - `ProviderAdapterRequestPreview`: metadata-only preview with `payload_body_present=false` and `provider_call_allowed=false`.
  - `ProviderAdapterResponsePlaceholder`: safe placeholder with only `manual_review_required=true`.
  - `ProviderAdapterDisabledError`: custom exception with static safe message.
  - `ProviderAdapterProtocol`: typing Protocol for future adapter implementations.
  - `DisabledProviderAdapter`: concrete harness where `send()` always raises `ProviderAdapterDisabledError`.
  - `build_provider_adapter_interface_contract_dict()`: deterministic contract artifact with 12 policy substructures.
  - `create_provider_adapter_interface_contract()`: safe creation from unlock state with validation, lineage, hash, and denylist scanning.
  - `safe_validate_provider_adapter_interface_contract_data()`: strict validation with hash, lineage, forbidden fragments, and impossible boolean checks.
  - `validate_provider_adapter_interface_contract_artifact()`: detailed per-check validation.
  - `replay_provider_adapter_interface_contract()`: deterministic hash replay from source unlock state.
  - `iter_provider_adapter_interface_contract_artifacts()`: safe listing with invalid sentinels for tampered items.
  - `summarize_provider_adapter_interface_contract()`: read-only summary without writing artifacts.
  - `doctor_provider_adapter_interface_contract()`: read-only chain diagnostic.
  - `run_disabled_adapter_smoke_test()`: exercises disabled harness and confirms fail-closed behavior.
  - 12 policy substructures: `adapter_capability_summary`, `disabled_adapter_policy`, `request_preview_contract`, `response_placeholder_contract`, `send_method_policy`, `credential_access_policy`, `network_access_policy`, `provider_sdk_policy`, `error_handling_policy`, `side_effect_policy`, `broker_separation_policy`, `future_adapter_requirements`.
  - 40+ boolean safety flags; only `adapter_interface_recorded=True` and `disabled_adapter_available=True` are ever True.
  - 8 new CLI commands under `atlas research`.
  - Session integration: `check_research_artifacts`, `build_research_timeline`, `build_dossier`.
  - Demo script extended with adapter interface flow.
  - Comprehensive test suite: 51 tests.

## [0.5.7.dev35] - 2026-05-21

### Added
- Batch 8.8 — Provider Execution Unlock State Machine.
  - `src/atlas_agent/research/provider_execution_unlock_state.py`: local provider execution unlock state artifacts.
  - `build_provider_execution_unlock_state_dict()`: deterministic unlock state artifact construction from review result.
  - `create_provider_execution_unlock_state()`: safe creation with validation, lineage, hash, and denylist scanning.
  - `safe_validate_provider_execution_unlock_state_data()`: strict validation with invalid sentinel returns.
  - `validate_provider_execution_unlock_state_artifact()`: detailed per-check validation.
  - `replay_provider_execution_unlock_state()`: deterministic hash replay from source review result.
  - `iter_provider_execution_unlock_state_artifacts()`: safe listing with invalid sentinels for tampered items.
  - `summarize_provider_execution_unlock_state_state()`: read-only summary without writing artifacts.
  - `doctor_provider_execution_unlock_state()`: read-only chain diagnostic.
  - `provider_execution_unlock_state_sha256()`: deterministic canonical hash excluding volatile fields.
  - 11 policy substructures: `unlock_transition_policy`, `manual_unlock_policy`, `credential_unlock_policy`, `provider_adapter_unlock_policy`, `network_unlock_policy`, `request_send_unlock_policy`, `response_import_unlock_policy`, `trust_upgrade_policy`, `trading_separation_policy`, `broker_separation_policy`, `rollback_policy`.
  - 40+ boolean safety flags; only `unlock_state_recorded=True` and `manual_unlock_required=True` are ever True.
  - 7 new CLI commands: `provider-execution-unlock-state`, `provider-execution-unlock-state-list`, `provider-execution-unlock-state-show`, `provider-execution-unlock-state-validate`, `provider-execution-unlock-state-replay`, `provider-execution-unlock-state-summary`, `provider-execution-unlock-state-doctor`.
  - Integration into `check-artifacts`, `timeline`, and `dossier`.
  - Tests in `tests/research/test_research_provider_execution_unlock_state.py`.
  - Demo workflow extended with unlock state creation, list, show, validate, replay, summary, doctor, timeline lineage checks, and check-artifacts count validation.

## [0.5.7.dev34] - 2026-05-21

### Added
- Batch 8.6 — Provider Response Schema Contract & Manual Review Gate.
  - `src/atlas_agent/research/provider_response_schema_contract.py`: local provider response schema contract artifacts.
  - `build_provider_response_schema_contract_dict()`: deterministic schema contract artifact construction from pairing.
  - `create_provider_response_schema_contract()`: safe creation with validation, lineage, hash, and denylist scanning.
  - `safe_validate_provider_response_schema_contract_data()`: strict validation with invalid sentinel returns.
  - `validate_provider_response_schema_contract_artifact()`: detailed per-check validation.
  - `replay_provider_response_schema_contract()`: deterministic hash replay from source pairing.
  - `iter_provider_response_schema_contract_artifacts()`: safe listing with invalid sentinels for tampered items.
  - `summarize_provider_response_schema_contract_state()`: read-only summary without writing artifacts.
  - `doctor_provider_response_schema_contract()`: read-only chain diagnostic.
  - `provider_response_schema_contract_sha256()`: deterministic canonical hash excluding volatile fields.
  - 12 policy substructures: `expected_response_shape`, `allowed_response_fields`, `rejected_response_fields`, `schema_validation_policy`, `unsafe_content_policy`, `manual_review_gate_policy`, `trust_boundary_policy`, `trading_separation_policy`, `broker_separation_policy`, `response_storage_policy`, `response_hash_policy`, `review_result_policy`, `future_response_artifact_requirements`.
  - 40 boolean safety flags including `schema_contract_enabled`, `manual_review_gate_open`, `automatic_review_allowed`, `future_response_artifact_present`, `future_response_schema_validated`, `provider_response_received`, `provider_response_trusted`, `provider_response_can_create_orders`, `response_schema_allows_trading_signal`, `response_schema_allows_broker_call`, `raw_response_body_stored`, `raw_prompt_body_stored`.
  - 7 new CLI commands: `provider-response-schema-contract`, `provider-response-schema-contract-list`, `provider-response-schema-contract-show`, `provider-response-schema-contract-validate`, `provider-response-schema-contract-replay`, `provider-response-schema-contract-summary`, `provider-response-schema-contract-doctor`.
  - Integration into `check-artifacts`, `timeline`, and `dossier`.
  - Tests in `tests/research/test_research_provider_response_schema_contract.py`.
  - Demo workflow extended with schema contract creation, list, show, validate, replay, summary, doctor, timeline lineage checks, and check-artifacts count validation.

## [0.5.7.dev32] - 2026-05-20

### Added
- Batch 8.5 — Provider Request/Response Pairing Contract Artifact.
  - `src/atlas_agent/research/provider_request_response_pairing.py`: local provider request/response pairing contract artifacts.
  - `build_provider_request_response_pairing_dict()`: deterministic pairing contract artifact construction from intake policy.
  - `create_provider_request_response_pairing()`: safe creation with validation, lineage, hash, and denylist scanning.
  - `safe_validate_provider_request_response_pairing_data()`: strict validation with invalid sentinel returns.
  - `validate_provider_request_response_pairing_artifact()`: detailed per-check validation.
  - `replay_provider_request_response_pairing()`: deterministic hash replay from source intake policy.
  - `iter_provider_request_response_pairing_artifacts()`: safe listing with invalid sentinels for tampered items.
  - `summarize_provider_request_response_pairing_state()`: read-only summary without writing artifacts.
  - `doctor_provider_request_response_pairing_state()`: read-only chain diagnostic.
  - `provider_request_response_pairing_sha256()`: deterministic canonical hash excluding volatile fields.
  - 12 policy substructures: `request_side`, `response_side`, `correlation_policy`, `provider_trace_policy`, `request_hash_policy`, `response_hash_policy`, `pairing_validation_policy`, `pairing_replay_policy`, `mismatch_policy`, `trust_boundary_policy`, `manual_review_policy`, `future_response_requirements`.
  - 30 boolean safety flags including `request_response_pair_completed`, `future_response_artifact_present`, `future_response_hash_present`, `provider_trace_id_present`, `external_correlation_id_present`, `raw_request_body_stored`, `raw_response_body_stored`.
  - 7 new CLI commands: `provider-request-response-pairing`, `provider-request-response-pairing-list`, `provider-request-response-pairing-show`, `provider-request-response-pairing-validate`, `provider-request-response-pairing-replay`, `provider-request-response-pairing-summary`, `provider-request-response-pairing-doctor`.
  - Integration into `check-artifacts`, `timeline`, and `dossier`.
  - Tests in `tests/research/test_research_provider_request_response_pairing.py`.
  - Demo workflow extended with pairing creation, list, show, validate, replay, summary, doctor, and timeline lineage checks.

## [0.5.7.dev31] - 2026-05-20

### Added
- Batch 8.4 — Provider Response Intake Policy Artifact.
  - `src/atlas_agent/research/provider_response_intake_policy.py`: local provider response intake policy artifacts.
  - `build_provider_response_intake_policy_dict()`: deterministic response intake policy artifact construction from payload preview.
  - `create_provider_response_intake_policy()`: safe creation with validation, lineage, hash, and denylist scanning.
  - `safe_validate_provider_response_intake_policy_data()`: strict validation with invalid sentinel returns.
  - `validate_provider_response_intake_policy_artifact()`: detailed per-check validation.
  - `replay_provider_response_intake_policy()`: deterministic hash replay from source payload preview.
  - `iter_provider_response_intake_policy_artifacts()`: safe listing with invalid sentinels for tampered items.
  - `summarize_provider_response_intake_policy_state()`: read-only summary without writing artifacts.
  - `provider_response_intake_policy_sha256()`: deterministic canonical hash excluding volatile fields.
  - 8 policy substructures: `response_storage_policy`, `response_redaction_policy`, `response_validation_policy`, `response_review_policy`, `unsafe_response_policy`, `trading_separation_policy`, `response_hash_policy`, `manual_review_policy`.
  - 23 boolean safety flags including `provider_response_received`, `provider_response_trusted`, `provider_response_imported`, `provider_response_reviewed`, `provider_response_can_create_orders`, `provider_response_can_approve_orders`, `provider_response_can_call_broker`.
  - 6 new CLI commands: `provider-response-intake-policy`, `provider-response-intake-policy-list`, `provider-response-intake-policy-show`, `provider-response-intake-policy-validate`, `provider-response-intake-policy-replay`, `provider-response-intake-policy-summary`.
  - Integration into `check-artifacts`, `timeline`, and `dossier`.
  - Tests in `tests/research/test_research_provider_response_intake_policy.py`.
  - Demo workflow extended with response intake policy creation, validation, replay, summary, and timeline lineage checks.

## [0.5.7.dev30] - 2026-05-20

### Added
- Batch 8.3 — Provider Outbound Payload Preview Artifact.
  - `src/atlas_agent/research/provider_outbound_payload_preview.py`: local provider outbound payload preview artifacts.
  - `build_provider_outbound_payload_preview_dict()`: deterministic payload preview artifact construction.
  - `create_provider_outbound_payload_preview()`: safe creation with validation, lineage, and hash.
  - `safe_validate_provider_outbound_payload_preview_data()`: strict validation with invalid sentinel returns.
  - `validate_provider_outbound_payload_preview_artifact()`: detailed per-check validation.
  - `replay_provider_outbound_payload_preview()`: deterministic hash replay from source boundary.
  - `iter_provider_outbound_payload_preview_artifacts()`: safe listing with invalid sentinels.
  - `summarize_provider_outbound_payload_preview_state()`: read-only summary without writing artifacts.
  - Payload shape metadata, minimization summary, redaction summary, blocked fields, and safe category labels.
  - 25 boolean safety flags including `provider_enabled`, `network_enabled`, `credentials_loaded`, `outbound_request_sent`, `payload_body_stored`.
  - Impossible boolean detection: `provider_outbound_payload_preview_impossible_boolean`.
  - denylist-clean manifest: stores only safe metadata; never stores raw forbidden fragments.
- CLI commands (all configless, local-only):
  - `atlas research provider-payload-preview PROVIDER_CREDENTIAL_BOUNDARY_ID`
  - `atlas research provider-payload-preview-list`
  - `atlas research provider-payload-preview-show PREVIEW_ID`
  - `atlas research provider-payload-preview-validate PREVIEW_ID`
  - `atlas research provider-payload-preview-replay PREVIEW_ID`
  - `atlas research provider-payload-preview-summary RUN_ID`
- Session integration: `check-artifacts`, `timeline`, and `dossier` now support provider outbound payload preview artifacts.
- Timeline nesting: payload preview artifacts indexed by `source_provider_credential_boundary_id` under credential boundary entries.
- Demo workflow extended with payload preview creation, validation, replay, summary, and timeline lineage checks.

### Safety / Compatibility
- No real provider execution added. No network calls. No API keys. No provider SDKs.
- No credential loading. No `.env.atlas` loading. No `os.environ` lookup.
- No broker execution changes. No trading signals. No approvals or pending orders.
- Boundary diff clean under `src/atlas_agent/config`, `brokers`, `execution`, `safety`, `risk`.
- Provider execution remains disabled.
- All configless invariants preserved.

## [0.5.7.dev29] - 2026-05-20

### Added
- Batch 8.2 — Provider Credential Boundary Record & Secret-Handling Contract.
  - `src/atlas_agent/research/provider_credential_boundary.py`: local provider credential boundary artifacts.
  - `build_provider_credential_boundary_dict()`: deterministic boundary artifact construction.
  - `create_provider_credential_boundary()`: safe creation with validation, lineage, and hash.
  - `safe_validate_provider_credential_boundary_data()`: strict validation with invalid sentinel returns.
  - `validate_provider_credential_boundary_artifact()`: detailed per-check validation.
  - `replay_provider_credential_boundary()`: deterministic hash replay.
  - `iter_provider_credential_boundary_artifacts()`: safe listing with invalid sentinels.
  - `summarize_provider_credential_boundary_for_run()`: read-only summary without writing artifacts.
  - Secret policy sections: `secret_storage_policy`, `secret_input_policy`, `secret_output_policy`, `secret_logging_policy`, `secret_redaction_policy`, `secret_rotation_policy`, `secret_revocation_policy`, `ci_secret_policy`.
  - 14 boolean safety flags including `credential_value_present`, `credential_lookup_attempted`, `env_read_attempted`, `dotenv_loaded`.
  - Impossible boolean detection: `provider_credential_boundary_impossible_boolean`.
  - denylist-clean manifest: stores only safe metadata; never stores raw forbidden fragments.
- CLI commands (all configless, local-only):
  - `atlas research provider-credential-boundary PROVIDER_OPT_IN_POLICY_ID`
  - `atlas research provider-credential-boundary-list`
  - `atlas research provider-credential-boundary-show BOUNDARY_ID`
  - `atlas research provider-credential-boundary-validate BOUNDARY_ID`
  - `atlas research provider-credential-boundary-replay BOUNDARY_ID`
  - `atlas research provider-credential-boundary-summary RUN_ID`
- Session integration: `check-artifacts`, `timeline`, and `dossier` now support provider credential boundary artifacts.
- Timeline nesting: boundary artifacts indexed by `source_provider_opt_in_policy_id` under policy entries.
- Demo workflow extended with credential boundary creation, validation, replay, summary, and timeline lineage checks.

### Safety / Compatibility
- No real provider execution added. No network calls. No API keys. No provider SDKs.
- No credential loading. No `.env.atlas` loading. No `os.environ` lookup.
- No broker execution changes. No trading signals. No approvals or pending orders.
- Boundary diff clean under `src/atlas_agent/config`, `brokers`, `execution`, `safety`, `risk`.
- Provider execution remains disabled.
- All configless invariants preserved.

## [0.5.7.dev28] - 2026-05-20

### Added
- Batch 8.1 — Provider Opt-In Policy Artifact.
  - `src/atlas_agent/research/provider_opt_in_policy.py`: local provider opt-in policy artifacts.
  - `build_provider_opt_in_policy_dict()`: deterministic policy artifact construction.
  - `create_provider_opt_in_policy()`: safe creation with validation, lineage, and hash.
  - `safe_validate_provider_opt_in_policy_data()`: strict validation with invalid sentinel returns.
  - `validate_provider_opt_in_policy_artifact()`: detailed per-check validation.
  - `replay_provider_opt_in_policy()`: deterministic hash replay.
  - `iter_provider_opt_in_policy_artifacts()`: safe listing with invalid sentinels.
  - `summarize_provider_opt_in_policy_for_run()`: read-only summary without writing artifacts.
  - Impossible boolean detection: `provider_opt_in_policy_impossible_boolean` for tampered flags.
  - denylist-clean manifest: stores only safe metadata; never stores raw forbidden fragments.
- CLI commands (all configless, local-only):
  - `atlas research provider-opt-in-policy READINESS_REPORT_ID`
  - `atlas research provider-opt-in-policy-list`
  - `atlas research provider-opt-in-policy-show POLICY_ID`
  - `atlas research provider-opt-in-policy-validate POLICY_ID`
  - `atlas research provider-opt-in-policy-replay POLICY_ID`
  - `atlas research provider-opt-in-policy-summary RUN_ID`
- Session integration: `check-artifacts`, `timeline`, and `dossier` now support provider opt-in policy artifacts.
- Timeline nesting: policy artifacts indexed by `source_provider_execution_readiness_report_id` under readiness report entries.
- Demo workflow extended with provider opt-in policy creation, validation, replay, summary, and timeline lineage checks.

### Safety / Compatibility
- No real provider execution added. No network calls. No API keys. No provider SDKs.
- No broker execution changes. No trading signals. No approvals or pending orders.
- Boundary diff clean under `src/atlas_agent/config`, `brokers`, `execution`, `safety`, `risk`.
- Provider execution remains disabled.
- All configless invariants preserved.

## [0.5.7.dev27] - 2026-05-20

### Added
- Batch 8.0 — Real Provider Integration Threat Model & Policy Draft.
  - `docs/security/provider-integration-threat-model.md`: formal threat model for future provider execution.
  - `docs/security/provider-execution-policy.md`: policy draft covering default deny, human opt-in, credential isolation, outbound payload, response handling, trading separation, audit, failure, allowlist, and release gate policies.
  - `docs/security/provider-integration-requirements.md`: checkbox checklist for future provider integration phases.
  - `docs/adr/ADR-0001-provider-execution-boundary.md`: architecture decision record isolating provider execution from trading execution.
  - `docs/releases/v0.5.7.dev27.md`: release notes for Batch 8.0.

### Changed
- `docs/audits/provider-preflight-freeze-v0.5.7.dev26.md`: fixed stale wording about configless invariant tests.
- `README.md`: updated current status to v0.5.7.dev27; added note that real provider execution is not implemented.
- `docs/research-workflow.md`: added cross-reference to new security documentation.

### Safety / Compatibility
- No real provider execution added. No network calls. No API keys. No provider SDKs.
- No broker execution changes. No trading signals. No approvals or pending orders.
- Boundary diff clean under `src/atlas_agent/config`, `brokers`, `execution`, `safety`, `risk`.
- This batch is documentation, policy, and tests only.

## [0.5.7.dev26] - 2026-05-20

### Added
- Provider Preflight Freeze Audit & Evidence Pack (`src/atlas_agent/research/provider_preflight_freeze.py`).
  - Deterministic freeze artifact consolidating the full 9-artifact provider-preflight chain into a single auditable envelope.
  - `build_provider_preflight_freeze_dict()` creates freeze artifacts from readiness reports with hash, validation, command surface, boundary, and denylist manifests.
  - `safe_validate_provider_preflight_freeze_data()` performs strict validation with invalid sentinel returns.
  - `validate_provider_preflight_freeze_artifact()` performs detailed check-by-check validation including denylist manifest safety.
  - `replay_provider_preflight_freeze()` rebuilds from source readiness report and compares hashes.
  - `iter_provider_preflight_freeze_artifacts()` safely lists freeze artifacts with invalid sentinels.
  - `summarize_provider_preflight_freeze_for_run()` provides read-only summary without writing artifacts.
  - 10 boolean safety flags + 9 `no_action_attestations` all enforced as `False`.
  - denylist_manifest stores only safe metadata (profile name, count, safety flags); never stores raw forbidden fragment strings.
- CLI commands (all configless, local-only, read-only):
  - `atlas research provider-preflight-freeze READINESS_REPORT_ID`
  - `atlas research provider-preflight-freeze-list`
  - `atlas research provider-preflight-freeze-show FREEZE_ID`
  - `atlas research provider-preflight-freeze-validate FREEZE_ID`
  - `atlas research provider-preflight-freeze-replay FREEZE_ID`
  - `atlas research provider-preflight-freeze-summary RUN_ID`
- Session integration: `check-artifacts`, `timeline`, and `dossier` now support provider preflight freeze artifacts.
- Timeline nesting: freeze artifacts indexed by `source_provider_execution_readiness_report_id` under readiness report entries.
- Demo workflow extended with provider preflight freeze creation, validation, replay, summary, and timeline lineage checks.

### Fixed
- denylist_manifest no longer stores raw forbidden fragment strings (`<users-path>`, `<authorization-header>`, `<bearer-token>`, `<apca-fragment>`, `<secret-fragment>`, `<token-fragment>`, `<password-fragment>`, `<api-key-fragment>`, `<api-key-prefix>`, `<broker-example-host>`) inside freeze artifacts.
- Forbidden fragment leak fixed: freeze artifacts are now denylist-clean in the happy path.
- Validation updated to explicitly check `denylist_manifest.forbidden_fragments_raw_stored` is `False` and `denylist_profile` is known.

### Safety / Compatibility
- No real provider execution. No API/network calls. No API key loading. No provider SDK usage.
- No trading signals generated. No approvals or pending orders created. No broker touched.
- Freeze artifact is development-scope only; provider execution remains disabled.
- Future opt-in required for any real provider call.
- All configless invariants preserved.

## [0.5.7.dev25] - 2026-05-19

### Added
- Provider Execution Readiness Report & Chain Doctor (`src/atlas_agent/research/provider_execution_readiness_report.py`).
  - Deterministic readiness scoring (0–100) based on chain completeness, hash integrity, and mandatory-false boolean safety flags.
  - `_build_safety_gate_summary()` covers all 10 mandatory flags: `provider_enabled`, `network_enabled`, `credentials_loaded`, `provider_call_allowed`, `actual_provider_call_made`, `future_provider_execution_possible`, `trading_signal_generated`, `approval_created`, `pending_order_created`, `broker_touched`.
  - Read-only Chain Doctor (`provider-execution-chain-doctor`) diagnoses the full provider-preflight chain without creating artifacts or calling providers.
  - Safe validation with invalid sentinels, forbidden-fragment scanning, and impossible-boolean detection.
  - Nested `no_action_attestations` dict with 9 False-by-design flags.
- CLI commands (all configless, local-only):
  - `atlas research provider-execution-readiness AUDIT_PACKET_ID`
  - `atlas research provider-execution-readiness-list`
  - `atlas research provider-execution-readiness-show ID`
  - `atlas research provider-execution-readiness-validate ID [--strict]`
  - `atlas research provider-execution-readiness-replay ID [--strict]`
  - `atlas research provider-execution-chain-doctor RUN_ID`
- Session integration: `check-artifacts`, `timeline`, and `dossier` now support provider execution readiness report artifacts.
- Timeline nesting: readiness reports are indexed by `source_provider_execution_audit_packet_id` and nested under each audit packet entry.
- Demo workflow extended with readiness report creation, validation, replay, chain doctor, and timeline lineage checks.

### Fixed
- `_build_safety_gate_summary()` now sources all 10 mandatory boolean flags directly from the source audit packet top-level fields, fixing a bug where missing flags caused valid chains to score 0 and report `chain_invalid`.
- `_compute_readiness_score()` safety gate check now correctly evaluates all 10 flags against the safety gate summary.

### Safety / Compatibility
- No real provider execution. No API/network calls. No API key loading. No provider SDK usage.
- No trading signals generated. No approvals or pending orders created. No broker touched.
- Readiness score reflects local chain integrity/completeness only; it is NOT trading confidence.
- Even `readiness_score=100` does NOT imply provider execution is allowed.
- All configless invariants preserved.

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
- Demo research workflow script stdout/stderr sanitized to prevent absolute temp path leaks (`<users-path>`, `<private-var-path>`, etc.).

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
