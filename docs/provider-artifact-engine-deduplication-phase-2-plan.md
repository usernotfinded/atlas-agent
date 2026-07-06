# CAND-014 Phase 2 Provider Artifact Pilot Extraction Plan

> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss. This is a planning-only
> implementation-plan document. It changes no runtime behavior, enables no live
> trading or live submit, authorizes no order placement, loads no credentials,
> makes no broker or provider calls, adds no network access, and does not
> implement artifact-engine extraction.

## 1. Title And Candidate Phase

- **Candidate:** CAND-014 - Provider Artifact Engine Deduplication.
- **Phase:** Phase 2 planning only - pilot extraction plan.
- **Accepted prior phase:** Phase 1 - Provider Artifact Inventory + Golden
  Characterization Tests.
- **Pilot module:** `src/atlas_agent/research/provider_mock_response_final_safety_seal.py`.
- **Compatibility gate:** `tests/test_provider_artifact_golden_contracts.py` and
  existing final-safety-seal/upstream mock-response chain tests.
- **Document created:** 2026-07-06.
- **Scope:** Design a future one-module pilot extraction. Do not implement it in
  this task.

## 2. Baseline State

- Baseline HEAD and `origin/main`:
  `d02e88dcd42b552d48abf3a2b9f36a63254ac7fe`
  (`docs(cand-014): accept provider artifact goldens`).
- Package/source version: `0.6.20`.
- Current public release: `v0.6.20`.
- Next planned release: `v0.6.21`.
- Local `v0.6.21*` tag: none.
- Remote `v0.6.21*` tag: none.
- GitHub Release `v0.6.21`: not found.
- PyPI: unpublished for `atlas-agent`.
- CAND-014 Phase 1 is accepted into the `v0.6.21` candidate chain with
  acceptance verdict `PASS_WITH_WARNINGS`.
- `atlas run --mode live` fail-closed with exit `2` in an isolated temporary
  home/config workspace during baseline verification.

Baseline checks run before this planning edit:

- `python3.11 scripts/check_version_consistency.py`: passed
  (`package=0.6.20 public_tag=v0.6.20`).
- `python3.11 scripts/check_release_metadata.py`: passed.
- `python3.11 scripts/check_candidate_chain.py`: passed with existing historical
  warnings.
- `python3.11 scripts/check_public_docs_consistency.py`: passed.
- `python3.11 scripts/check_forbidden_claims.py`: passed.
- `python3.11 -m pytest tests/test_provider_artifact_golden_contracts.py -q`:
  13 passed.
- `mypy src/atlas_agent/safety/kill_switch.py`: passed.
- `atlas validate`: exited 0 and reported live trading disabled by default.
- `git diff --check`: passed.

## 3. Phase 1 Acceptance Summary

Phase 1 delivered:

- `docs/provider-artifact-engine-deduplication-inventory.md`.
- `tests/test_provider_artifact_golden_contracts.py`.
- Golden fixtures under
  `tests/fixtures/provider_artifacts/final_safety_seal/`.

Acceptance state:

- Acceptance verdict: `PASS_WITH_WARNINGS`.
- Independent implementation-review verdict: `PASS_WITH_WARNINGS`.
- New golden tests: 13 passed.
- Existing final-safety-seal and upstream mock-response chain tests: 299 passed.
- Artifact-engine extraction status: not authorized / not started.

Warnings to carry into Phase 2:

1. Inventory-count warning: the Phase 1 inventory doc records 87 provider-related
   test files from the required broad command, while later live filesystem
   counting returned 120 because it included ignored `__pycache__` entries plus
   current Phase 1 files. The source inventory remains correct: 22
   `provider_*.py` modules and 28,908 provider source lines.
2. Heavy-gate review warning: independent review did not run `dev_check.sh`,
   `ci_check.sh`, or `release_check.sh --quick`. This is non-blocking because
   targeted Phase 1 checks, the 13 golden tests, and 299 existing pilot/upstream
   tests passed.
3. CAND-ID legacy warning: `CAND-014` is the correct current-epoch next ID for
   `v0.6.21` after CAND-013. The older v0.6.12 `CAND-014` belongs to the legacy
   release-local epoch and is a non-blocking naming collision.

## 4. Phase 2 Objective

Phase 2 may authorize a future implementation prompt for exactly one pilot
extraction:

`provider_mock_response_final_safety_seal.py` becomes a compatibility wrapper
around a small pilot artifact engine/spec while preserving every public function,
constant, schema field, hash, diagnostic string, CLI output, and exit code
already frozen by Phase 1.

The future implementation must be limited to this pilot module. It must not
extract all provider modules, migrate the mock-response family, unify all
validators, change CLI strings, change artifact hashes, change schemas, change
replay/summary/doctor behavior, alter provider/broker/network/credential
behavior, or weaken safety boundaries.

## 5. Pilot Module Surface Inventory

### Constants

- `PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_VERSION`:
  `research_provider_mock_response_final_safety_seal_v1`.
- `_PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_HASH_EXCLUDED_FIELDS`:
  `{"artifact_hash", "created_at"}`.
- `_MAX_MODEL_ID_CHARS`: `120`.
- `_MAX_STATUS_CHARS`: `120` (defined, currently not part of the golden surface).
- `_VALID_FINAL_SAFETY_SEAL_STATUSES`:
  `final_safety_seal_recorded`, `final_safety_seal_invalid`.
- `_VALID_FINAL_SAFETY_SEAL_SCOPES`:
  `offline_mock_response_final_safety_seal_only`.
- `_VALID_FINAL_SAFETY_SEAL_STATES`:
  `mock_pipeline_sealed`, `trust_blocked_and_sealed`,
  `sandbox_only_seal_valid`, `non_authorizing_seal_active`.
- `_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE`: 50 safety flags.
- `_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE`: 11 safety flags.
- `_UNSAFE_POSITIVE_CLAIM_PHRASES`: denylist phrase tuple.

### Version Fields

- Artifact `contract_version` must remain
  `research_provider_mock_response_final_safety_seal_v1`.
- Artifact `schema_version` must remain `RESEARCH_ARTIFACT_SCHEMA_VERSION`
  (`"1"` in the Phase 1 fixture).
- Changing either value is hash-affecting and outside Phase 2 pilot scope unless
  a later versioned migration is explicitly authorized.

### Artifact Schema Fields

The Phase 1 valid fixture has 94 top-level fields. Future extraction must
preserve all names, values, default booleans, policy object shapes, and JSON
sorting:

```text
actual_provider_call_made, approval_created, artifact_hash, artifact_path,
artifact_type, broker_order_path_enabled, broker_separation_policy,
broker_touched, contract_version, created_at, credential_boundary_policy,
credential_lookup_attempted, credential_value_present, credentials_loaded,
dotenv_loaded, env_read_attempted, final_safety_seal_created,
final_safety_seal_scope, final_safety_seal_state, final_safety_seal_status,
future_response_schema_validated, http_client_imported,
live_trading_path_enabled, manual_review_completed, manual_review_gate_open,
manual_review_policy, manual_unlock_granted, metadata, mock_only,
mock_pipeline_complete, mock_response_trust_policy, mock_response_trusted, mode,
model_id, network_boundary_policy, network_call_attempted, network_enabled,
outbound_request_sent, pending_order_created, provider_call_allowed,
provider_execution_unlocked, provider_id,
provider_mock_response_final_safety_seal_id, provider_response_imported,
provider_response_received, provider_response_reviewed,
provider_response_trusted, provider_sdk_imported, raw_prompt_body_stored,
raw_request_body_stored, raw_response_body_stored, raw_review_notes_stored,
real_provider_response_imported, real_provider_response_received,
real_provider_response_reviewed, real_provider_trust_boundary_policy,
review_decision_allows_broker_call, review_decision_allows_order_approval,
review_decision_allows_order_creation,
review_decision_allows_trading_interpretation,
review_decision_allows_trust_upgrade, review_decision_allows_use,
review_result_present, sandbox_only, schema_version, seal_allows_execution,
seal_allows_trading, seal_authorizing, seal_decision_policy,
seal_non_authorizing, seal_source_summary, seal_summary, seal_type,
seal_upgrade_policy, seal_valid, side_effect_policy, source_provider_id,
source_run_id, source_trust_decision_blocker_hash,
source_trust_decision_blocker_id, symbol, trading_authorization_policy,
trading_signal_generated, trust_blocker_active,
trust_decision_blocker_recorded, trust_decision_denied,
trust_decision_explicitly_blocked, trust_decision_granted,
trust_decision_present, trust_decision_required, trust_source_verified,
trust_upgrade_available, trust_upgrade_performed, warnings
```

### Status Values

- Artifact status: `final_safety_seal_recorded`.
- Other allowed status: `final_safety_seal_invalid`.
- Scope: `offline_mock_response_final_safety_seal_only`.
- State in standard artifacts: `mock_pipeline_sealed`.
- Other allowed states:
  `trust_blocked_and_sealed`, `sandbox_only_seal_valid`,
  `non_authorizing_seal_active`.
- Create result status: `research_provider_mock_response_final_safety_seal_created`.
- Replay result status: `research_provider_mock_response_final_safety_seal_replayed`.
- Summary result status: `research_provider_mock_response_final_safety_seal_summary`.
- Missing summary status: `missing_provider_mock_response_final_safety_seal`.
- Doctor result status: `research_provider_mock_response_final_safety_seal_doctor`.
- CLI list status: `provider_mock_response_final_safety_seals_listed`.
- Missing show/validate CLI status: `seal_not_found`.

### Validators

- `validate_provider_id`.
- `validate_model_id`.
- `validate_final_safety_seal_status`.
- `validate_final_safety_seal_scope`.
- `validate_final_safety_seal_state`.
- `safe_validate_provider_mock_response_final_safety_seal_data`.
- `validate_provider_mock_response_final_safety_seal_artifact`.
- Shared validators used by the module:
  `validate_contract_lineage_id`, `validate_contract_symbol`, `validate_run_id`,
  `_is_inside_workspace`, `_has_forbidden_fragments`.

### `validate_provider_id` Behavior

The pilot accepts only `mock`. Empty values, `openai`, and disabled provider IDs
such as `custom-openai-compatible` all fail with the exact diagnostic
`invalid_provider_mock_response_final_safety_seal_provider`.

The pilot does not use `_get_disabled_provider_ids`. Future extraction must not
replace this validator with a broader shared disabled-provider helper unless the
diagnostic and accepted/rejected inputs remain exactly identical.

### Disabled-Provider Behavior

Disabled provider handling is effectively fail-closed through the pilot's
`provider_id == "mock"` requirement. A disabled provider ID is rejected with the
same diagnostic as any non-mock provider. Phase 2 must preserve that behavior
instead of introducing cross-module disabled-provider normalization.

### Hash And Canonicalization Logic

- `provider_mock_response_final_safety_seal_sha256(data)` removes only
  `artifact_hash` and `created_at`, serializes with `canonical_json_dumps`, and
  hashes with SHA-256.
- Phase 1 reference hash:
  `9bcc626839a4616ed7be19ceb376e849b26736042a65da86eec8f05efb97ea0a`.
- Changing `artifact_hash` and `created_at` leaves the hash unchanged.
- Changing `broker_touched` changes the hash to
  `eb9a3267f3459365af156d8f203721ad23dfe2b0d8d958cf190c2936fd50c4aa`.
- `canonical_json_dumps` is already shared in `sandbox_contracts.py`; Phase 2
  must reuse it rather than introducing a new canonicalizer.

### Excluded Hash Fields

Exactly these fields are excluded:

```text
artifact_hash
created_at
```

No additional pilot exclusions may be added in Phase 2.

### Create/Build Functions

- `build_provider_mock_response_final_safety_seal_dict`.
- `create_provider_mock_response_final_safety_seal`.
- Policy builders currently private to the module:
  `_build_seal_source_summary`, `_build_seal_summary`,
  `_build_seal_decision_policy`, `_build_seal_upgrade_policy`,
  `_build_manual_review_policy`, `_build_mock_response_trust_policy`,
  `_build_real_provider_trust_boundary_policy`,
  `_build_trading_authorization_policy`, `_build_broker_separation_policy`,
  `_build_network_boundary_policy`, `_build_credential_boundary_policy`,
  `_build_side_effect_policy`.

### Load Functions

- `load_provider_mock_response_final_safety_seal`.
- It reads UTF-8 JSON, calls
  `safe_validate_provider_mock_response_final_safety_seal_data`, and raises
  `ResearchSessionError(err)` on validation failure.

### Validate Functions

- `safe_validate_provider_mock_response_final_safety_seal_data`.
- `validate_provider_mock_response_final_safety_seal_artifact`.
- Validation dataclass:
  `ProviderMockResponseFinalSafetySealValidationResult`.
- Important diagnostics include:
  `provider_mock_response_final_safety_seal_malformed`,
  `unsupported_provider_mock_response_final_safety_seal_schema`,
  `invalid_provider_mock_response_final_safety_seal_id`,
  `invalid_provider_mock_response_final_safety_seal_lineage`,
  `invalid_provider_mock_response_final_safety_seal_provider`,
  `invalid_provider_mock_response_final_safety_seal_model`,
  `invalid_provider_mock_response_final_safety_seal_status`,
  `provider_mock_response_final_safety_seal_impossible_boolean`,
  `provider_mock_response_final_safety_seal_hash_mismatch`,
  `provider_mock_response_final_safety_seal_forbidden_trust_claim`,
  `provider_mock_response_final_safety_seal_source_trust_decision_blocker_missing`,
  `provider_mock_response_final_safety_seal_source_trust_decision_blocker_hash_mismatch`,
  and
  `provider_mock_response_final_safety_seal_source_trust_decision_blocker_provider_not_mock`.

### Replay Functions

- `replay_provider_mock_response_final_safety_seal`.
- Replay validates the seal ID, finds and loads the stored seal, loads the source
  trust-decision-blocker, rebuilds the seal with the original seal ID and
  original `created_at`, recomputes the hash, and returns a match envelope.
- Missing seal raises `provider_mock_response_final_safety_seal_not_found`.

### Iter/List Functions

- `iter_provider_mock_response_final_safety_seal_artifacts`.
- `find_provider_mock_response_final_safety_seal_by_id`.
- Iteration searches under `.atlas/research`, supports optional symbol filtering,
  skips symlinks outside the workspace, returns valid items sorted descending by
  `created_at`, and appends invalid items with `_invalid` and `error_code`.

### Summarize Functions

- `_find_latest_provider_mock_response_final_safety_seal_for_run`.
- `summarize_provider_mock_response_final_safety_seal`.
- Summary returns a missing-status envelope when no seal exists and otherwise
  returns a compact seal summary for the latest valid seal for the run.

### Doctor Functions

- `doctor_provider_mock_response_final_safety_seal`.
- Doctor reports `seal_missing` when no seal exists and `seal_valid` for a valid
  seal. It records fixed missing prerequisites and blocking reasons for the
  current non-authorizing mock pipeline.

### CLI-Facing Labels And Errors

Pinned command names:

- `provider-mock-response-final-safety-seal`
- `provider-mock-response-final-safety-seal-list`
- `provider-mock-response-final-safety-seal-show`
- `provider-mock-response-final-safety-seal-validate`
- `provider-mock-response-final-safety-seal-replay`
- `provider-mock-response-final-safety-seal-summary`
- `provider-mock-response-final-safety-seal-doctor`

Pinned compatibility alias in `atlas research mock-response-final-safety-seal`:
`create`, `list`, `show`, `validate`, `replay`.

CLI text headings/labels such as `Provider mock response final safety seal
created`, `Provider mock response final safety seal <id>:`, `Replay: MATCH`,
and `Provider mock response final safety seal doctor for run <id>:` must not
change in the pilot extraction. JSON outputs must continue to use
`json.dumps(..., indent=2, sort_keys=True)`.

### Exceptions And Result Codes

- Public functions raise `ResearchSessionError` for invalid IDs, missing source
  artifacts, missing seals, validation failures, and unsafe/tampered artifacts.
- CLI handlers return `0` for success.
- CLI handlers return `1` for missing workspace, missing artifact, validation
  exception, and generic research command failure.
- CLI validate returns `2` only when `--strict` is supplied and the validation
  result is invalid.
- CLI replay returns `2` only when `--strict` is supplied and replay hash match
  is false.

### Public Python Function Names

The future wrapper must preserve these importable names:

- `ProviderMockResponseFinalSafetySealValidationResult`.
- `validate_provider_id`.
- `validate_model_id`.
- `validate_final_safety_seal_status`.
- `validate_final_safety_seal_scope`.
- `validate_final_safety_seal_state`.
- `provider_mock_response_final_safety_seal_sha256`.
- `build_provider_mock_response_final_safety_seal_dict`.
- `create_provider_mock_response_final_safety_seal`.
- `load_provider_mock_response_final_safety_seal`.
- `safe_validate_provider_mock_response_final_safety_seal_data`.
- `validate_provider_mock_response_final_safety_seal_artifact`.
- `replay_provider_mock_response_final_safety_seal`.
- `summarize_provider_mock_response_final_safety_seal`.
- `doctor_provider_mock_response_final_safety_seal`.
- `iter_provider_mock_response_final_safety_seal_artifacts`.
- `find_provider_mock_response_final_safety_seal_by_id`.

Private helpers may move only if behavior and any tests importing them remain
unchanged. Existing upstream tests import `_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE`,
`_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE`, `_UNSAFE_POSITIVE_CLAIM_PHRASES`, and
`_has_unsafe_positive_claims`, so these names are contract-sensitive for the
pilot even though they are private by naming convention.

### Tests Currently Covering Each Surface

- Phase 1 goldens cover import side effects, build output, validation success
  and failure diagnostics, invalid/disabled provider IDs, missing file handling,
  hash/canonicalization, excluded hash fields, version/status fields, iter/list,
  CLI show JSON/text, replay, summary, doctor, and exit codes.
- `tests/research/test_research_provider_mock_response_final_safety_seal.py`
  covers configless CLI create/list/show/validate/replay/summary/doctor,
  artifact creation, policy field contents, boolean safety flags, validation
  tamper cases, replay tamper detection, summary, doctor, listing/loading,
  timeline/dossier integration, schema version, provider-ID invariant,
  non-authorizing semantics, unsafe claim detection, creation error handling,
  multiple seals, and CLI integration.
- Upstream chain tests cover the mock-response path through simulation, import
  candidate, review sandbox, trust decision blocker, and final safety seal.
- `tests/research/test_research_provider_safety_dossier.py` imports
  `create_provider_mock_response_final_safety_seal`; Phase 2 must keep that
  import stable.

## 6. Golden Coverage Map

| Surface | Phase 1 fixture/test coverage |
| --- | --- |
| Import side effects | `test_pilot_module_imports_without_filesystem_side_effects` |
| Required build fields | `artifact_valid.json`, `test_build_artifact_matches_valid_golden_required_fields` |
| Validation success | `test_validate_success_passes_for_valid_golden` |
| Validation failure diagnostics | `artifact_invalid_provider_id.json`, `artifact_missing_required_field.json`, `test_validate_failure_diagnostics_are_stable` |
| Invalid/disabled provider ID | `test_invalid_and_disabled_provider_diagnostics_are_stable` |
| Missing seal behavior | `test_missing_file_handling_and_exit_codes_are_stable` |
| Canonical JSON/hash | `artifact_hash_reference.json`, `test_canonical_json_and_artifact_hash_are_stable` |
| Hash-excluded fields | `test_excluded_hash_fields_are_excluded_and_core_fields_are_included` |
| Version/status/state | `test_version_and_status_fields_are_stable` |
| Iter/list projection | `iter_list_json.golden`, `test_iter_output_is_stable_against_golden` |
| CLI show JSON/text | `cli_show_json.golden`, `cli_show_text.golden` |
| Replay JSON | `cli_replay_json.golden` |
| Summary JSON | `cli_summarize_json.golden` |
| Doctor text | `doctor_output.golden` |
| Configless CLI no credential/config loading | `_run_cli` patches config/secrets loaders to fail if called |

The golden test file has 12 test functions and 13 collected test cases because
one validation-failure test is parameterized over two negative fixtures.

## 7. Future Minimal Artifact Engine Skeleton

A future Phase 2 implementation may introduce a small internal pilot engine:

```text
src/atlas_agent/research/artifact_engine.py
```

The engine must be minimal and pilot-driven. It should include only primitives
needed by `provider_mock_response_final_safety_seal.py`:

- An immutable spec structure, for example a frozen dataclass or named tuple.
- A canonical hash helper that delegates to `canonical_json_dumps`.
- A JSON load helper with UTF-8 parsing and delegated validation.
- A JSON save helper if the pilot wrapper needs it.
- A validation result helper compatible with the current dataclass shape.
- A list/iter helper if it can preserve the current sort, symlink, invalid-item,
  and symbol-filter behavior.
- Adapter hooks for summary, replay, and doctor output.
- No global registry.
- No CLI registry migration.
- No migration of other provider modules.
- No replacement of all validator variants.

The future engine must stay behind the pilot wrapper until the Phase 1 goldens
prove byte-identical behavior.

## 8. Future Pilot Spec/Wrapper Design

A future implementation may add:

```text
src/atlas_agent/research/artifact_engine.py
src/atlas_agent/research/provider_mock_response_final_safety_seal_spec.py
```

or equivalent minimal names if an independent review approves them.

Proposed split:

- `provider_mock_response_final_safety_seal.py` remains the public compatibility
  wrapper. All current public names continue to exist in this module.
- `provider_mock_response_final_safety_seal_spec.py` holds pilot-only declarative
  data: artifact type, version, storage subdirectory, ID field, required schema
  fields, status/scope/state sets, hash-excluded fields, safety flag lists,
  denylist phrases, and error-code strings.
- `artifact_engine.py` implements only common mechanics extracted from this one
  pilot: hash, load JSON, save JSON, validation result assembly, stable list
  projection, and optional replay/summary/doctor adapter dispatch.
- Policy builders can remain in the wrapper or move to the pilot spec module
  only if the resulting artifacts are byte-identical.
- CLI modules must continue importing and calling the same wrapper functions.

The initial extraction should be intentionally small: move hash/load/save/list
mechanics only if the move can be proven by unchanged goldens. Leave complex
policy construction and final replay/summary/doctor envelope construction in the
wrapper if extracting them would increase risk.

## 9. Public API Preservation Requirements

Future implementation must preserve:

- All public wrapper function and constant names listed in Section 5.
- Private names currently imported by tests:
  `_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE`, `_BOOLEAN_SAFETY_FLAGS_MUST_BE_TRUE`,
  `_UNSAFE_POSITIVE_CLAIM_PHRASES`, `_has_unsafe_positive_claims`.
- Return dictionaries and their keys.
- Dataclass name and fields:
  `valid`, `passed_checks`, `failed_checks`, `checks`, `recommendation`,
  `warnings`.
- Exception type: `ResearchSessionError`.
- Error strings and status strings.
- Workspace-relative artifact path format:
  `.atlas/research/<symbol>/provider_mock_response_final_safety_seals/<seal_id>.json`.
- JSON serialization style for stored artifacts:
  `json.dumps(artifact, indent=2, sort_keys=True)`.

## 10. Hash/Canonicalization Preservation Requirements

Future implementation must preserve:

- `PROVIDER_MOCK_RESPONSE_FINAL_SAFETY_SEAL_VERSION`.
- `RESEARCH_ARTIFACT_SCHEMA_VERSION` handling.
- Hash exclusion set exactly equal to `{"artifact_hash", "created_at"}`.
- SHA-256 over `canonical_json_dumps` of the payload after excluding those
  fields.
- Current Phase 1 fixture hash:
  `9bcc626839a4616ed7be19ceb376e849b26736042a65da86eec8f05efb97ea0a`.
- The fact that `broker_touched` and other core fields remain hash-included.

Any intentional hash-affecting change must be treated as a separate versioned
migration with a new contract version. That is not part of Phase 2.

## 11. `validate_provider_id` Preservation Requirements

Future implementation must preserve:

- Accepted input: exactly `"mock"`.
- Rejected inputs include `""`, `"openai"`, and
  `"custom-openai-compatible"`.
- Rejection diagnostic:
  `invalid_provider_mock_response_final_safety_seal_provider`.
- No use of `_get_disabled_provider_ids` in this pilot unless behavior and
  diagnostics are proven identical.
- No global provider-ID validator unification in the pilot extraction.

## 12. CLI Contract Preservation Requirements

Future implementation must preserve:

- Parser command names in `src/atlas_agent/cli.py`.
- Handler dispatch strings in
  `src/atlas_agent/cli_commands/research/mock_response.py`.
- Command-contract fixture entries in
  `tests/fixtures/cli_command_contract.json`.
- JSON output sorting/indentation.
- Text output headings and labels currently covered by goldens.
- Exit codes `0`, `1`, and strict-mode `2` behavior.
- Missing-artifact JSON payloads such as `{"ok": false, "status": "seal_not_found"}`.
- Configless command behavior, including no config/secret loader calls in the
  Phase 1 golden CLI tests.

Phase 2 implementation must not edit CLI files unless a later independent review
explicitly authorizes that scope. The expected pilot extraction should not need
CLI file changes.

## 13. Compatibility Gate

Before and after a future pilot extraction, run:

```bash
python3.11 -m pytest tests/test_provider_artifact_golden_contracts.py -q
```

Expected result: `13 passed`.

Also run the existing pilot/upstream mock-response chain tests discovered in
Phase 1:

```bash
python3.11 -m pytest \
  tests/research/test_research_provider_mock_response_final_safety_seal.py \
  tests/research/test_research_provider_mock_response_trust_decision_blocker.py \
  tests/research/test_research_provider_mock_response_review_sandbox.py \
  tests/research/test_research_provider_mock_response_import_candidate.py \
  tests/research/test_research_provider_mock_response_simulation.py -q
```

Expected Phase 1 reference result: 299 passed.

The future extraction is not acceptable unless these tests pass unchanged.
Goldens may be updated only with explicit review. A changed golden fixture is a
contract decision, not a refactor detail.

## 14. Future Implementation File Scope

Allowed future implementation files, if the independent Phase 2 planning review
passes:

- `src/atlas_agent/research/artifact_engine.py`
- `src/atlas_agent/research/provider_mock_response_final_safety_seal_spec.py`
- `src/atlas_agent/research/provider_mock_response_final_safety_seal.py`

Optional future docs-only update:

- `docs/provider-artifact-engine-deduplication-phase-2-plan.md`

Expected not to change during the future pilot implementation:

- Other `src/atlas_agent/research/provider_*.py` modules.
- CLI modules.
- Checker scripts.
- Tests or fixtures, unless an explicit compatibility-review decision approves
  a golden refresh.
- Runtime trading, broker, provider execution, or safety modules.
- Version files, release metadata, changelog, tags, GitHub Releases, or PyPI
  state.

## 15. Non-Goals

Phase 2 planning and the future pilot implementation do not authorize:

- Extracting all provider modules.
- Migrating the entire mock-response family.
- Introducing a general provider-artifact framework for all 22 modules.
- Creating or changing CLI command names.
- Editing CLI output.
- Changing artifact schemas, hash fields, or stored JSON format.
- Changing replay, summary, doctor, or validate diagnostics.
- Unifying all provider-ID validators.
- Changing disabled-provider behavior.
- Changing provider, broker, network, credential, runtime trading, or safety
  behavior.
- Updating package version, release metadata, tags, GitHub Releases, or PyPI.
- Starting the `v0.6.21` release cutover.

## 16. Rollback Plan

If the future pilot extraction fails compatibility review:

1. Remove `src/atlas_agent/research/artifact_engine.py`.
2. Remove `src/atlas_agent/research/provider_mock_response_final_safety_seal_spec.py`.
3. Restore the pre-extraction `provider_mock_response_final_safety_seal.py`.
4. Keep Phase 1 goldens unchanged.
5. Re-run the Phase 1 golden tests and the existing pilot/upstream mock-response
   chain tests.
6. No data migration is needed.
7. No release-state change is needed.
8. No tag, GitHub Release, or PyPI action is needed.

Rollback is expected to be a normal file revert because Phase 2 must not change
artifact schemas or persisted data formats.

## 17. Verification Matrix

Planning-doc verification for this task:

```bash
git diff --check
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_public_docs_consistency.py
python3.11 scripts/check_candidate_chain.py
python3.11 scripts/check_release_metadata.py
python3.11 scripts/check_version_consistency.py
python3.11 -m pytest tests/test_provider_artifact_golden_contracts.py -q
mypy src/atlas_agent/safety/kill_switch.py
atlas run --mode live
```

Future pilot implementation verification must include all of the above plus:

```bash
python3.11 -m pytest \
  tests/research/test_research_provider_mock_response_final_safety_seal.py \
  tests/research/test_research_provider_mock_response_trust_decision_blocker.py \
  tests/research/test_research_provider_mock_response_review_sandbox.py \
  tests/research/test_research_provider_mock_response_import_candidate.py \
  tests/research/test_research_provider_mock_response_simulation.py -q
atlas validate
python3.11 -m compileall src/atlas_agent/research tests
```

If practical, future implementation review should also run:

```bash
bash scripts/dev_check.sh
bash scripts/ci_check.sh
bash scripts/release_check.sh --quick
```

If local live credentials exist, `atlas run --mode live` must be run only in a
safe isolated offline home/config workspace and must fail closed with exit `2`.

## 18. Safety And Release Invariants

Phase 2 planning and any future pilot extraction must preserve:

- No live trading enabled.
- No live submit enabled.
- No order placement.
- No order cancellation.
- No position flattening.
- No pending-order creation.
- No approval queue mutation.
- No broker calls.
- No provider calls.
- No credential loading.
- No network access.
- No `RiskManager` weakening.
- No kill-switch weakening.
- No deadman weakening.
- No heartbeat weakening.
- No audit hash-chain bypass.
- `atlas run --mode live` fail-closed with exit `2` or isolated offline
  verification if local live credentials exist.
- Package/source version remains `0.6.20`.
- Current public release remains `v0.6.20`.
- Next planned release remains `v0.6.21`.
- PyPI remains unpublished.
- No `v0.6.21` tag.
- No `v0.6.21` GitHub Release.

## 19. Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Hash drift | Keep `canonical_json_dumps`, excluded fields, version string, and Phase 1 hash fixtures unchanged. Treat any hash change as a separate versioned migration. |
| CLI output drift | Do not edit CLI files in the pilot. Require CLI JSON/text goldens to pass unchanged. |
| Error-string drift | Preserve every `ResearchSessionError` string and safe-validation diagnostic exactly. Prefer adapter wrappers over rewritten diagnostics. |
| Timestamp/path nondeterminism | Keep `created_at` hash-excluded, use deterministic test workspaces, and preserve workspace-relative `artifact_path`. |
| Over-generalized engine | Implement only pilot-required primitives. Do not design for all 22 modules in this phase. |
| Accidental changes to other provider modules | Restrict future implementation file scope to the pilot wrapper plus new engine/spec files. Audit diff by path before commit. |
| Future mismatch between goldens and real use | Run both Phase 1 goldens and existing upstream chain tests. Do not rely on fixtures alone. |
| Hidden contract-checker literal matching | Re-run candidate-chain/public-docs/forbidden-claims checks and avoid CLI command/status literal changes. |
| CAND-ID legacy warning | Keep warning recorded. Treat it as non-blocking unless repository convention changes to require global uniqueness. |
| Heavy gates not always run in review | Run heavy gates if practical; otherwise record as non-blocking only when targeted Phase 2 checks and pilot/upstream tests pass. |

## 20. Open Questions

1. Should the first future implementation move only hash/load/save mechanics, or
   also move list/iter mechanics? Recommendation: move hash/load/save first if
   that produces a small reviewable diff; move list/iter only if the goldens
   remain unchanged and the code reduction is meaningful.
2. Should the pilot spec module include private safety flag lists, or should
   those remain in the wrapper because existing tests import them? Recommendation:
   keep wrapper-level aliases even if the source data moves.
3. Should `validate_provider_id` remain a wrapper-local function permanently for
   this pilot? Recommendation: yes for Phase 2, because this module intentionally
   accepts only `mock` and does not use `_get_disabled_provider_ids`.
4. Should future golden refreshes be allowed during extraction? Recommendation:
   no. A refresh requires a separate explicit compatibility decision.
5. Should heavy gates be mandatory for Phase 2 implementation acceptance?
   Recommendation: run them if practical, but do not treat them as a substitute
   for the pilot-specific golden and upstream-chain gates.

## 21. Phase 2 Readiness Verdict

**READY_FOR_PHASE_2_IMPLEMENTATION_WITH_WARNINGS.**

Phase 2 is ready for a separate independent planning review. If that review
passes, the next implementation prompt may authorize only one pilot extraction:
`provider_mock_response_final_safety_seal.py` as a compatibility wrapper around
minimal pilot engine/spec code, guarded by unchanged Phase 1 goldens.

Warnings:

- CAND-ID legacy reuse remains documented as non-blocking.
- Optional heavy gates should be run if practical during future implementation
  review.
- Pilot extraction must stay limited to one module and the Phase 1 goldens must
  remain unchanged.
- Artifact-engine extraction is still not authorized by this planning document;
  it requires the separate independent Phase 2 planning review to pass first.
