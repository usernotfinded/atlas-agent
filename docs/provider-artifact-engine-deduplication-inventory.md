# CAND-014 Phase 1 Provider Artifact Inventory

## 1. Scope

This document records CAND-014 Phase 1 only: provider artifact inventory plus
golden characterization coverage for the pilot module
`src/atlas_agent/research/provider_mock_response_final_safety_seal.py`.

Phase 1 is additive and ID-independent. It does not extract an artifact engine,
does not introduce `ArtifactSpec`, does not refactor provider modules, and does
not modify runtime, CLI, checker, safety, broker, version, release, changelog, or
candidate-chain acceptance files.

The implementation-readiness verdict is
`READY_FOR_PHASE_1_IMPLEMENTATION_WITH_ID_REUSE_WARNING`. The warning does not
block this phase because no acceptance docs are added here. Maintainer
confirmation on `CAND-014` ID reuse is needed only before future candidate-chain
acceptance docs.

## 2. Baseline Commit

- Baseline local HEAD: `bc07ac1758215ca41075a0eac6dada95e5a1390d`
- Baseline `origin/main`: `bc07ac1758215ca41075a0eac6dada95e5a1390d`
- Baseline latest commit: `bc07ac1 docs(cand-014): plan provider artifact engine dedupe`
- Current package/source version at baseline: `0.6.20`
- Current public release at baseline: `v0.6.20`
- Next planned release at baseline: `v0.6.21`
- Local `v0.6.21*` tag at baseline: none
- Remote `v0.6.21*` tag at baseline: none
- GitHub Release `v0.6.21` at baseline: not found

## 3. Provider Artifact Module Inventory

Generated from current repository state with `Path("src/atlas_agent/research").glob("provider_*.py")`.

| Module | Lines | Family |
| --- | ---: | --- |
| `provider_adapter_interface.py` | 363 | adapter/interface |
| `provider_adapter_interface_contract.py` | 1869 | adapter/interface |
| `provider_call_plan.py` | 975 | execution planning |
| `provider_credential_boundary.py` | 1318 | execution boundary |
| `provider_execution_audit_packet.py` | 1222 | execution readiness |
| `provider_execution_dry_run.py` | 1015 | execution readiness |
| `provider_execution_readiness_report.py` | 1539 | execution readiness |
| `provider_execution_state.py` | 1214 | execution readiness |
| `provider_execution_unlock_state.py` | 1660 | execution readiness |
| `provider_mock_response_final_safety_seal.py` | 1103 | mock response |
| `provider_mock_response_import_candidate.py` | 1844 | mock response |
| `provider_mock_response_review_sandbox.py` | 1965 | mock response |
| `provider_mock_response_simulation.py` | 1828 | mock response |
| `provider_mock_response_trust_decision_blocker.py` | 1589 | mock response |
| `provider_opt_in_policy.py` | 1324 | execution boundary |
| `provider_outbound_payload_preview.py` | 839 | execution boundary |
| `provider_preflight_freeze.py` | 1575 | execution readiness |
| `provider_request_response_pairing.py` | 1210 | response handling |
| `provider_response_intake_policy.py` | 944 | response handling |
| `provider_response_review_result.py` | 1403 | response handling |
| `provider_response_schema_contract.py` | 1357 | response handling |
| `provider_safety_dossier.py` | 752 | safety dossier |

## 4. Total Count And Line Count

- Provider artifact module count: 22
- Provider artifact total line count: 28,908
- Pilot module line count: 1,103
- Required provider-related test file command returned: 87 files
  - Note: this count includes existing `__pycache__` bytecode files that match
    `*provider*`; no bytecode files are added by this phase.

## 5. Largest Modules

| Rank | Module | Lines |
| ---: | --- | ---: |
| 1 | `provider_mock_response_review_sandbox.py` | 1965 |
| 2 | `provider_adapter_interface_contract.py` | 1869 |
| 3 | `provider_mock_response_import_candidate.py` | 1844 |
| 4 | `provider_mock_response_simulation.py` | 1828 |
| 5 | `provider_execution_unlock_state.py` | 1660 |
| 6 | `provider_mock_response_trust_decision_blocker.py` | 1589 |
| 7 | `provider_preflight_freeze.py` | 1575 |
| 8 | `provider_execution_readiness_report.py` | 1539 |
| 9 | `provider_response_review_result.py` | 1403 |
| 10 | `provider_response_schema_contract.py` | 1357 |

## 6. Repeated Lifecycle Operations

The provider artifact modules repeatedly implement these lifecycle operations:

- `build_*_dict` or direct artifact construction
- `create_*` artifact creation and JSON write
- `load_*` with JSON parse plus validation
- `safe_validate_*_data`
- `validate_*_artifact`
- `replay_*`
- `_find_latest_*_for_run`
- `summarize_*`
- `doctor_*`
- `iter_*_artifacts`
- `find_*_by_id`
- CLI wrappers for create, list, show, validate, replay, summary, and doctor

Phase 1 freezes the pilot behavior before any future extraction attempts.

## 7. Repeated Validators And Helpers

Current repeated helper search results:

- `def validate_provider_id`: 21 definitions under `src/atlas_agent/research/provider_*.py`.
- `_get_disabled_provider_ids`: 16 definitions under provider modules plus one use in `research/session.py`.

Pilot-specific validator behavior:

- `provider_mock_response_final_safety_seal.validate_provider_id("mock")` passes.
- Any other provider ID, including disabled provider IDs such as
  `custom-openai-compatible`, fails with
  `invalid_provider_mock_response_final_safety_seal_provider`.
- The pilot does not use `_get_disabled_provider_ids`; this is recorded rather
  than changed.

## 8. Artifact Family Grouping

- Adapter/interface: `provider_adapter_interface.py`, `provider_adapter_interface_contract.py`
- Execution planning: `provider_call_plan.py`
- Execution readiness: dry-run, state, audit packet, readiness report, preflight freeze, unlock state
- Execution boundary: opt-in policy, credential boundary, outbound payload preview
- Response handling: intake policy, request/response pairing, schema contract, review result
- Mock response pipeline: simulation, import candidate, review sandbox, trust decision blocker, final safety seal
- Safety dossier: `provider_safety_dossier.py`

## 9. Pilot Module Rationale

The pilot is `provider_mock_response_final_safety_seal.py` because it is a
terminal mock-response artifact with broad contract-sensitive behavior but no
provider, broker, credential, or network calls. It exercises the repeated
artifact lifecycle without requiring runtime behavior changes.

The pilot depends on a valid upstream trust-decision-blocker artifact for replay
and workspace-aware validation. The new tests use deterministic direct-build
fixtures for byte-stable artifact/hash checks and a temporary local mock chain
for replay, summary, doctor, and CLI characterization.

## 10. Contract-Sensitive Surfaces

These surfaces are now covered by Phase 1 goldens or explicit assertions:

- Module import side effects
- Required artifact fields
- `contract_version`, `schema_version`, status, and state fields
- Provider ID validation and diagnostics
- Validation success and negative diagnostic codes
- Missing artifact handling
- Canonical JSON hash payload
- Exclusion of `artifact_hash` and `created_at` from the artifact hash
- Inclusion of core fields in the artifact hash
- Iterator/list item shape
- Replay JSON output shape
- Summary JSON output shape
- Doctor text output shape
- CLI show JSON output shape
- CLI show text output shape
- CLI success and missing-artifact exit codes
- Configless CLI behavior with config and secret loaders patched to fail if called

## 11. Golden Fixture Inventory

Fixtures live under `tests/fixtures/provider_artifacts/final_safety_seal/`.

| Fixture | Purpose |
| --- | --- |
| `artifact_valid.json` | Full deterministic direct-build pilot artifact with pinned timestamp. |
| `artifact_invalid_provider_id.json` | Negative validation mutation spec and expected provider diagnostic. |
| `artifact_missing_required_field.json` | Negative validation mutation spec and expected lineage diagnostic. |
| `artifact_hash_reference.json` | Expected hash, version, status, state, and hash-exclusion behavior. |
| `iter_list_json.golden` | Normalized iterator/list item shape. |
| `cli_show_json.golden` | Normalized CLI show JSON projection. |
| `cli_show_text.golden` | Normalized CLI show text output. |
| `cli_summarize_json.golden` | Normalized CLI summary JSON projection. |
| `cli_replay_json.golden` | Normalized CLI replay JSON projection. |
| `doctor_output.golden` | Normalized CLI doctor text output. |

Golden refresh rule:

- Goldens are generated from current committed behavior.
- Future refactors must update goldens only with explicit review.
- Hash-affecting changes require versioned migration rationale.
- Error-string changes require an explicit compatibility decision.
- CLI output changes require an explicit contract update.

## 12. Non-Goals

This phase does not:

- Extract or introduce a provider artifact engine.
- Add `ArtifactSpec` or a shared artifact schema DSL.
- Refactor any provider module.
- Modify `provider_mock_response_final_safety_seal.py`.
- Modify any `provider_*.py` module.
- Modify CLI command names, CLI output, JSON schemas, error strings, or exit codes.
- Modify check scripts.
- Modify runtime trading, broker, provider execution, safety, or audit behavior.
- Modify version metadata, release metadata, changelog, tags, PyPI publishing, or GitHub Releases.
- Modify candidate-chain acceptance docs.

## 13. Safety And Release Invariants

Preserved boundaries:

- No live trading enabled.
- No live submit enabled.
- No order placement, cancellation, flattening, or pending-order creation.
- No approval queue mutation.
- No broker calls.
- No provider calls.
- No credential loading in golden CLI tests.
- No network access in tests.
- No `RiskManager`, kill-switch, deadman, heartbeat, audit hash-chain, or manifest weakening.
- Dashboard behavior is untouched.
- Package/source version remains `0.6.20`.
- Current public release remains `v0.6.20`.
- Next planned release remains `v0.6.21`.
- No `v0.6.21` tag, GitHub Release, or PyPI publication is part of this phase.

## 14. Verification Summary

Baseline verification before edits:

- `git status --short`: clean
- `git rev-parse HEAD`: `bc07ac1758215ca41075a0eac6dada95e5a1390d`
- `git rev-parse origin/main`: `bc07ac1758215ca41075a0eac6dada95e5a1390d`
- `python3.11 -c 'import atlas_agent; print(atlas_agent.__version__)'`: `0.6.20`
- `python3.11 scripts/check_version_consistency.py`: passed
- `python3.11 scripts/check_release_metadata.py`: passed
- `python3.11 scripts/check_candidate_chain.py`: passed with existing historical warnings
- `python3.11 scripts/check_public_docs_consistency.py`: passed
- `python3.11 scripts/check_forbidden_claims.py`: passed
- `python3.11 scripts/check_bounded_autonomy_governance.py`: passed
- `python3.11 scripts/check_trust_center.py`: passed
- `python3.11 scripts/check_onboarding_docs.py`: passed
- `python3.11 scripts/check_public_launch_readiness.py`: passed
- `mypy src/atlas_agent/safety/kill_switch.py`: passed
- `atlas validate`: exited 0 and reported live trading disabled by default
- `atlas run --mode live`: exited 2 in an isolated temporary home/config
- `git diff --check`: passed

Focused Phase 1 verification after adding fixtures/tests:

- `python3.11 -m pytest tests/test_provider_artifact_golden_contracts.py -q`: 13 passed
- Existing pilot-related tests:
  - `tests/research/test_research_provider_mock_response_final_safety_seal.py`
  - `tests/research/test_research_provider_mock_response_trust_decision_blocker.py`
  - `tests/research/test_research_provider_mock_response_review_sandbox.py`
  - `tests/research/test_research_provider_mock_response_import_candidate.py`
  - `tests/research/test_research_provider_mock_response_simulation.py`
  - Result: 299 passed
- Phase 7 verification matrix:
  - `git diff --check`: passed
  - `python3.11 scripts/check_forbidden_claims.py`: passed
  - `python3.11 scripts/check_public_docs_consistency.py`: passed
  - `python3.11 scripts/check_candidate_chain.py`: passed with existing historical warnings
  - `python3.11 scripts/check_release_metadata.py`: passed
  - `python3.11 scripts/check_version_consistency.py`: passed
  - `python3.11 scripts/check_bounded_autonomy_governance.py`: passed
  - `python3.11 scripts/check_trust_center.py`: passed
  - `python3.11 scripts/check_onboarding_docs.py`: passed
  - `python3.11 scripts/check_public_launch_readiness.py`: passed
  - `mypy src/atlas_agent/safety/kill_switch.py`: passed
  - `atlas validate`: exited 0 and reported live trading disabled by default
  - `atlas run --mode live`: exited 2 in an isolated temporary home/config
  - `python3.11 -m compileall tests`: passed
