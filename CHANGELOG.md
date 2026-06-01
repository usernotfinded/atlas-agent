# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Opened the `0.5.9.dev0` development cycle after the public `v0.5.8` GitHub Release.

### Safety
- No live trading, provider execution, broker execution, credential loading, tag publishing, package publishing, or GitHub Release creation was performed.

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

> **Release candidate.** Not a stable final release. See [release notes](docs/releases/v0.5.8rc2.md) for full details.

### Fixed
- Fixed RC cutover verification so an existing RC tag is accepted only when it resolves to the current HEAD. Historical RC tags (e.g., `v0.5.8rc1`) are allowed without requiring them to match current HEAD.

### Safety
- No live trading, provider execution, broker execution, credential loading, tag publishing, package publishing, or GitHub release creation was performed.
- No protected boundaries were changed.
- No network calls were added.

## [0.5.8rc1] - 2026-05-29

> **Release candidate.** Not a stable final release. See [release notes](docs/releases/v0.5.8rc1.md) for full details.

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
