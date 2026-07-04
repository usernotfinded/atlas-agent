# CAND-014 — Provider Artifact Engine Deduplication (Design)

> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss. This document is a
> design-only proposal. It changes no runtime behavior, enables no live trading
> or live submit, authorizes no order placement, loads no credentials, makes no
> broker or provider calls, and adds no network access.

## 1. Title and candidate ID

- **Candidate:** CAND-014 — Provider Artifact Engine Deduplication.
- **Type:** Design-only. Refactor/deduplication of the
  `src/atlas_agent/research/provider_*` artifact module family.
- **Release line:** `v0.6.21` (planning-only; not released).
- **Scope of this document:** verify the duplication claims, inventory the
  provider artifact modules, catalogue the repeated lifecycle patterns and the
  contract-sensitive surfaces, and propose a safe incremental extraction
  strategy. It does **not** implement the engine.

## 2. Baseline state

- HEAD `0ea6c922ffca7d5d62d5c3f982057618e6177d7a` (`Remove obsolete atlas agent
  code`), `origin/main` in sync, working tree otherwise clean.
- Package/source version `0.6.20`; current public release `v0.6.20`; next planned
  release `v0.6.21`; PyPI unpublished; no `v0.6.21` tag or GitHub Release.
- CAND-013 remains accepted in the `v0.6.21` candidate chain
  (`PASS_WITH_WARNINGS`).
- Baseline checkers pass: `check_version_consistency`, `check_release_metadata`,
  `check_candidate_chain` (historical warnings only), `check_public_docs_consistency`,
  `check_forbidden_claims`; `mypy src/atlas_agent/safety/kill_switch.py` clean;
  `atlas run --mode live` fail-closed (exit `2`, verified in a safe isolated
  offline paper workspace — see §20).
- The immediately preceding commit `0ea6c92` performed an unrelated CLI refactor
  (moved research CLI dispatch into `src/atlas_agent/cli_commands/research/`). It
  did not touch `release-metadata.json`, version files, or the CAND-013
  acceptance docs. It is orthogonal to this candidate.

## 3. Audit claim verification

The external audit was treated as hypotheses and checked against the repository:

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | `research/provider_*` has ~20 near-duplicate modules | **Confirmed (higher)** | **22** `provider_*.py` modules |
| 2 | Family ~25,000 lines | **Confirmed (higher)** | **28,908** source lines in `provider_*.py` (plus ~48,222 lines across 84 `test_*provider_*` files and ~11,040 lines of research CLI) |
| 3 | Repeated create/load/list/show/validate/replay/summarize/doctor | **Confirmed** | `create` 21, `load` 21, `validate` 22, `replay` 21, `summarize` 16, `doctor` 12, list-via-`iter_*`/CLI 13 modules |
| 4 | `validate_provider_id` in many near-identical copies | **Confirmed, with nuance** | **21** copies; one dominant byte-identical form (~8 copies) plus ~13 minor variants — they are **not** all identical |
| 5 | CLI subcommands and tests reflect the same duplication | **Confirmed** | 16 CLI modules (`cli_commands/research/`, ~11k lines) with one `handle_provider_*` per lifecycle op; 84 provider test files (~48k lines) |
| 6 | String-matching contract checkers require byte-identical CLI strings and error codes | **Confirmed** | `tests/fixtures/cli_command_contract.json` pins commands; CLI handlers dispatch on literal `args.research_command == "provider-...-<op>"`; tests assert artifact-name-specific status/error codes byte-for-byte |

**Net:** the duplication is real and slightly larger than reported. Claim 4 is
refined: the validator is *mostly* duplicated but has real per-module variants,
so unification must preserve or explicitly re-baseline each error string (see
§11, §14).

## 4. Provider artifact inventory

22 modules, 28,908 source lines, grouped by prefix:

| Family | Modules | Lines |
|---|---|---|
| `provider_adapter_interface*` | `provider_adapter_interface` (363), `provider_adapter_interface_contract` (1869) | 2,232 |
| `provider_execution_*` | `audit_packet` (1222), `dry_run` (1015), `readiness_report` (1539), `state` (1214), `unlock_state` (1660) | 6,650 |
| `provider_mock_response_*` | `final_safety_seal` (1103), `import_candidate` (1844), `review_sandbox` (1965), `simulation` (1828), `trust_decision_blocker` (1589) | 8,329 |
| `provider_response_*` | `intake_policy` (944), `review_result` (1403), `schema_contract` (1357) | 3,704 |
| Singletons | `call_plan` (975), `credential_boundary` (1318), `opt_in_policy` (1324), `outbound_payload_preview` (839), `preflight_freeze` (1575), `request_response_pairing` (1210), `safety_dossier` (752) | 7,993 |

Largest modules: `review_sandbox` (1965), `adapter_interface_contract` (1869),
`import_candidate` (1844), `simulation` (1828), `unlock_state` (1660).

Common intra-module structure (exemplar `provider_mock_response_simulation.py`):

- Constants: `PROVIDER_..._VERSION = "research_provider_..._v1"`;
  `_..._HASH_EXCLUDED_FIELDS = {"artifact_hash", "created_at"}`;
  `_VALID_..._STATUSES` / `_SCOPES` / `_STATES`;
  `_BOOLEAN_SAFETY_FLAGS_MUST_BE_FALSE` / `_MUST_BE_TRUE`;
  `_UNSAFE_POSITIVE_CLAIM_PHRASES`.
- Validators: `validate_provider_id`, `validate_model_id`,
  `validate_..._status/scope/state`, `sanitize_adapter_text`,
  `_get_disabled_provider_ids`.
- Hash: `provider_..._sha256(data)`.
- Policy builders: `_build_..._hash_policy`, `_storage_policy`, `_trust_policy`,
  `_review_policy`, `_build_real_provider_boundary_policy`,
  `_build_network_boundary_policy`, `_build_credential_boundary_policy`,
  `_build_broker_separation_policy`, `_build_side_effect_policy`,
  `_build_denylist_metadata`.
- Lifecycle: `build_provider_..._dict`, `create_provider_..._`,
  `safe_validate_provider_..._data`, `validate_provider_..._artifact`,
  `load_provider_..._`, `load_and_validate_provider_..._`,
  `find_provider_..._by_id`, `replay_provider_..._`,
  `iter_provider_..._artifacts`, `summarize_provider_..._`,
  `doctor_provider_..._`.

Already-shared foundations (do **not** re-extract; reuse):

- `canonical_json_dumps` — `src/atlas_agent/research/sandbox_contracts.py:79`,
  imported by 21 modules. The canonicalization primitive is already centralized.
- `ResearchSessionError` — shared error type (21 modules).
- `MAX_CONTRACT_TEXT_CHARS` — shared bound (20 modules).

Duplicated (extraction targets): `_get_disabled_provider_ids` (16 per-module
copies of what should be one function), `validate_provider_id` (21), the entire
lifecycle above, per-module constants, `*_sha256`, and the policy builders.

## 5. Duplication taxonomy

1. **Boilerplate-identical** (safe to unify first): `_get_disabled_provider_ids`;
   the `*_sha256` body (drop excluded fields → `canonical_json_dumps` → sha256);
   the dominant `validate_provider_id` form; `_check_name`; storage/path
   resolution; deterministic JSON emission; list/iter sort ordering.
2. **Structurally-identical, data-different** (unify via declarative spec): status
   enums, hash-excluded field sets, required/optional field lists, boolean safety
   flags, unsafe-claim phrase lists, artifact version strings, error-code
   templates.
3. **Shape-identical, behavior-tuned** (unify carefully, per-spec hooks): the
   lifecycle functions (build/create/validate/load/replay/summarize/doctor) — same
   skeleton, per-artifact field wiring and diagnostics.
4. **Genuinely divergent** (do not force-unify without golden re-baselining): the
   ~13 `validate_provider_id` variants and per-artifact policy/summary content.

## 6. Contract-sensitive surfaces

Surfaces that must remain byte-identical under any future extraction:

- **CLI command names** — pinned in `tests/fixtures/cli_command_contract.json`
  and dispatched on literal `args.research_command == "provider-...-<op>"` in
  `cli_commands/research/*`. Enforced by `scripts/check_cli_command_compatibility.py`
  (parser-only introspection).
- **CLI status/result codes** — e.g. `provider_mock_response_simulations_listed`,
  `research_provider_mock_response_simulation_validated` /
  `..._validation_failed`; asserted in tests.
- **Artifact-name-specific error codes** — e.g.
  `invalid_provider_mock_response_simulation_provider`,
  `missing_provider_mock_response_simulation`, `invalid_provider_id`; raised as
  `ResearchSessionError(...)` and asserted byte-for-byte in tests.
- **Artifact `*_VERSION` strings** (`research_provider_..._v1`) — embedded in
  artifacts and hashed; changing them changes stored hashes.
- **Hash output** — `artifact_hash` values produced by `*_sha256`; the excluded
  fields (`{"artifact_hash", "created_at"}`) and `canonical_json_dumps` ordering
  must not change.
- **JSON schema field names** and **exit codes** for each CLI op.
- **Existing contract-artifact modules** (`provider_adapter_interface_contract`,
  `provider_response_schema_contract`) whose own outputs are consumed elsewhere.

A first extraction must not alter any of these.

## 7. Artifact lifecycle model

Every provider artifact follows the same lifecycle, which the engine will model:

`build_dict` (assemble canonical artifact + policies) → `create` (validate, hash,
persist deterministically) → `load` / `load_and_validate` (read + re-validate) →
`find_by_id` / `iter` (locate, stable-sorted listing) → `validate_artifact` /
`safe_validate` (schema + safety-flag + provider-id checks, structured
diagnostics) → `replay` (recompute hash from stored inputs, compare, emit
match/mismatch envelope) → `summarize` (roll up by run) → `doctor` (health/
consistency checks). Hashing excludes `{"artifact_hash", "created_at"}` and uses
`canonical_json_dumps`.

## 8. Proposed `ArtifactSpec` design

A declarative, immutable spec per artifact type, consumed by a shared engine.
(Illustrative shape — **not** to be implemented in this candidate.)

```
ArtifactSpec(
  name: str,                       # "provider_mock_response_simulation"
  version: str,                    # "research_provider_..._v1"
  storage: ArtifactStoragePolicy,  # subdir, filename pattern, extension
  fields: list[ArtifactFieldSpec], # name, type, required?, default, validator
  status: ArtifactStatusSpec,      # enum values, optional transitions
  hash: ArtifactHashPolicy,        # excluded_fields, canonicalizer
  validation: ArtifactValidationPolicy,  # validators + error-code templates
  cli: ArtifactCliPolicy,          # command names, labels, status codes
  replay: ArtifactReplayPolicy,    # inputs to recompute, envelope shape
  summary: ArtifactSummaryPolicy,  # rolled-up fields
  doctor: ArtifactDoctorPolicy,    # health checks
)
```

Supporting declarative types:

- `ArtifactFieldSpec(name, kind, required, default, validator, max_chars)`
- `ArtifactStatusSpec(values: frozenset, transitions: mapping | None)`
- `ArtifactHashPolicy(excluded_fields: frozenset, canonicalize=canonical_json_dumps)`
- `ArtifactValidationPolicy(provider_id_validator, timestamp_validator, boolean_safety_flags_true/false, unsafe_claim_phrases, error_code_prefix)`
- `ArtifactStoragePolicy(subdir, filename_template, extension=".json")`
- `ArtifactCliPolicy(command_prefix, op_names, display_labels, status_codes)`
- `ArtifactReplayPolicy(recompute_inputs, failure_envelope_builder)`
- `ArtifactSummaryPolicy(group_key, summary_fields)`
- `ArtifactDoctorPolicy(checks)`

**What is declarative per artifact type:** name, version, storage path/extension,
field schema (+required/optional), status enum (+transitions if any), validators,
provider-id validation, timestamp validation, hash-exclusion fields, canonical
form, CLI labels/command names, replay behaviour, summary fields, doctor checks,
error-message templates.

## 9. Shared engine responsibilities

One engine implements the mechanics once, parameterised by `ArtifactSpec`:
`load`, `save`, `list`/`iter` (stable sort), `show`, `validate` (+structured
diagnostics), `replay`, `summarize`, `doctor`, `hash`/canonicalize, diagnostics
formatting, deterministic JSON output, path resolution, `_get_disabled_provider_ids`,
and fixture helpers. It reuses the existing `canonical_json_dumps` and
`ResearchSessionError` rather than reintroducing them.

## 10. Per-artifact spec responsibilities

Each artifact provides only its `ArtifactSpec` instance (data + a small number of
artifact-specific validation/policy hooks). No artifact re-implements load/save/
hash/list/replay/summarize/doctor mechanics. Divergent `validate_provider_id`
variants are captured either by the shared validator (for the identical majority)
or by an explicit per-spec validator hook (for documented variants), never by
silent normalisation.

## 11. Compatibility requirements

- Public function names currently imported elsewhere (CLI, tests, other provider
  modules — note the cross-module imports: `provider_call_plan` imported by 17
  modules, `provider_response_intake_policy`/`_request_response_pairing`/
  `_outbound_payload_preview` by 7 each) must remain importable, at minimum as
  thin shims delegating to the engine.
- Byte-identical CLI command names, status codes, error codes, JSON field names,
  exit codes, and artifact hashes (see §6).
- The ~13 `validate_provider_id` variants must be inventoried and either mapped to
  the shared validator (only if byte-identical error strings) or preserved via a
  per-spec hook; **document every difference before unifying**.

## 12. Hash / canonicalization preservation

- Keep `canonical_json_dumps` as the single canonicaliser (already shared).
- Keep excluded-field sets exactly (`{"artifact_hash", "created_at"}`; a few
  modules exclude additional fields — capture these per spec verbatim).
- Keep each `*_VERSION` string unchanged (it participates in the hashed payload).
- Golden-freeze the sha256 of representative artifacts before and after; the
  extraction is only valid if hashes are identical.

## 13. CLI contract preservation

- No command renames, no new/removed subcommands in the first extraction.
- Keep `args.research_command == "..."` literals and `handle_provider_*` entry
  points; if handlers are thinned, keep the same dispatch strings.
- Re-run `scripts/check_cli_command_compatibility.py` against
  `tests/fixtures/cli_command_contract.json` unchanged.

## 14. Test / golden fixture strategy

Before touching any module, add characterization ("golden") tests that freeze
current behaviour (they should pass on today's code unchanged):

- create/load/validate-success/validate-failure diagnostics; hash + excluded
  fields; list/show/summarize/replay/doctor outputs; CLI JSON and text output;
  exit codes; error strings; stable sorting; missing/invalid file handling;
  invalid provider-id handling.
- **`validate_provider_id`**: capture each module's current error message and
  accepted/rejected inputs. Preserve exact strings where existing tests/checkers
  require them; where variants differ, record the differences explicitly and do
  not normalise silently.

These goldens become the regression gate for every later extraction PR.

## 15. Extraction strategy options

| Option | Churn | Contract risk | Test burden | CLI/docs impact | Safety risk | Reversibility | Byte-identical outputs | Review ease | Est. line reduction |
|---|---|---|---|---|---|---|---|---|---|
| **A. Big-bang engine across all 22** | Very high | Very high | Very high | High | Low* | Poor | Hard to guarantee | Very hard | Largest (~15–20k) but risky |
| **B. One pilot module + full compat guarantees** | Low | Low–med | Medium | None | Low | Good | Provable for pilot | Easy | Small first (~0.5–1k), scales later |
| **C. Inventory + golden tests first, no engine** | Minimal | Minimal | Medium | None | Minimal | Trivial | N/A (no change) | Easy | 0 now (enables later) |
| **D. Compatibility adapter layer wrapping existing modules** | Medium | Medium | Medium | None | Low | Medium | Preserved by indirection | Medium | Low initially |

*Safety risk stays low because these modules are pure local artifact builders
(no network/broker/credential/order paths — verified), but **contract** risk from
byte-identical strings/hashes is the dominant hazard, and Option A maximises it.

## 16. Recommended strategy

**Option C first, then Option B.** Land inventory + golden characterization tests
(Option C) as a standalone, zero-churn step; then extract exactly one pilot module
onto the new engine (Option B) with the goldens proving byte-identical outputs.
Only after the pilot is accepted should further modules migrate one family at a
time. Avoid Option A (big-bang). Option D may be used tactically if a family
cannot be cleanly extracted, but is not the default.

Rationale: goldens de-risk before any structural change; a single pilot validates
the `ArtifactSpec`/engine design against a real contract surface; incremental
family-by-family migration keeps each PR small and reviewable and preserves the
byte-identical CLI/hash contracts.

## 17. Pilot module recommendation

**`src/atlas_agent/research/provider_mock_response_final_safety_seal.py`** (1103
lines — the smallest module in the `provider_mock_response_*` family that still
implements the full lifecycle: `create`/`load`/`safe_validate`/`replay`/
`summarize`/`doctor`).

- **Why:** small enough to review; representative of the highest-duplication
  family (5 near-identical mock_response modules ⇒ engine payoff); artifact-only
  and local (no live/broker/provider/network/credential behaviour); dedicated
  test file `tests/research/test_research_provider_mock_response_final_safety_seal.py`;
  simple JSON schema; testable replay/hash.
- **Current public API:** `create_*`, `build_*_dict`, `load_*`,
  `load_and_validate_*`, `find_*_by_id`, `validate_*_artifact`, `safe_validate_*_data`,
  `iter_*_artifacts`, `replay_*`, `summarize_*`, `doctor_*`, `*_sha256`,
  `validate_provider_id`, plus its constants (`*_VERSION`,
  `_*_HASH_EXCLUDED_FIELDS`, `_VALID_*_STATUSES`).
- **CLI commands:** the `research provider-mock-response-*` seal ops routed via
  `cli_commands/research/mock_response.py` (`handle_provider_mock_response_*`).
- **Golden outputs to freeze:** a created seal artifact's JSON + `artifact_hash`;
  validate success/failure diagnostics; replay match/mismatch envelope; list/
  summary/doctor JSON; CLI JSON+text and exit codes; `validate_provider_id`
  accepted/rejected strings.
- **Compatibility invariants:** identical module public API (shim if needed),
  identical CLI strings/codes, identical artifact hash, identical error codes.
- **Expected extracted spec:** an `ArtifactSpec` naming the seal artifact, its
  version, status enum, hash-excluded fields, field schema, CLI policy, replay/
  summary/doctor hooks.

(An alternative low-risk pilot is a `provider_preflight_*`/dry-run module if a
read-only-only surface is preferred; the mock_response seal is favoured for its
family-wide payoff.)

## 18. Migration phases

1. **Phase C0 (this candidate):** design only (this document).
2. **Phase C1:** inventory doc + golden characterization tests for the pilot
   family (no source change; goldens pass on current code).
3. **Phase C2:** introduce the engine + `ArtifactSpec` types *unused* (pure
   addition; no behaviour change), with unit tests.
4. **Phase C3:** migrate the pilot module to the engine behind unchanged public
   API + CLI; goldens must pass byte-for-byte.
5. **Phase C4+:** migrate remaining modules one family at a time (mock_response →
   response → execution → singletons), each gated by its goldens.
6. Each phase is a separate candidate/PR with its own review and acceptance.

## 19. Verification matrix

| Concern | Gate |
|---|---|
| Artifact hash unchanged | golden sha256 equality (pilot artifacts) |
| CLI commands unchanged | `check_cli_command_compatibility.py` + `cli_command_contract.json` |
| CLI output/exit codes | golden CLI JSON/text + exit-code tests |
| Error strings | golden error-code assertions incl. `validate_provider_id` |
| Import compatibility | existing test suite + cross-module import smoke |
| Determinism | repeated-run JSON equality |
| Safety boundaries | §20 checks; `mypy` on kill_switch; no runtime diff |
| Release invariants | `check_version_consistency`, `check_release_metadata`, `check_candidate_chain`, `check_public_docs_consistency`, `check_forbidden_claims` |

## 20. Safety and release invariants

Future implementation must **not** change: live-trading behaviour; broker/provider
call behaviour; credential loading; network access; approval-queue behaviour; risk
gates; kill-switch; deadman; heartbeat; audit hash-chain; release metadata;
package version; public-release docs; CLI command names; CLI exit codes;
user-facing error strings (unless explicitly covered by a golden update);
artifact hash output (unless intentionally versioned). The provider modules make
**no** real network/broker/credential/order calls today (verified), so the
extraction is a pure-refactor concern; the dominant hazard is contract drift, not
runtime safety. This design preserves: no live trading, no live submit, no order
placement/cancellation/flattening, no pending-order creation, no approval-queue
mutation, no broker/provider calls, no credential loading, no network access, no
weakening of RiskManager/kill-switch/deadman/heartbeat, no audit hash-chain
bypass. `atlas run --mode live` remains fail-closed (exit `2`, verified in a safe
isolated offline paper workspace because the local config carries live
credentials). Version stays `0.6.20`; current public stays `v0.6.20`; next
planned stays `v0.6.21`; PyPI unpublished; no `v0.6.21` tag or GitHub Release.

## 21. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Byte-identical CLI/error/hash drift | High | Goldens first (Option C); pilot-only (Option B); no command renames in first extraction |
| `validate_provider_id` variant flattening | Medium | Inventory all 21 forms; per-spec validator hooks; document differences before unifying |
| Hidden cross-module imports break | Medium | Keep public API via shims; import smoke tests; migrate one family at a time |
| Hash payload changes via `*_VERSION` edits | Medium | Freeze version strings; golden sha256 equality |
| Reviewer overload | Medium | Small per-family PRs; each gated by goldens |
| Candidate-ID collision (see §24) | Low | Confirm CAND-014 numbering with maintainer before acceptance |
| Under-estimated line reduction | Low | Treat reduction as a secondary goal; correctness/contract first |

## 22. Non-goals

- Implementing the engine, `ArtifactSpec`, or migrating any module (future
  candidates).
- Changing any CLI command, status code, error string, or artifact hash.
- Changing provider/broker/network/credential behaviour or any safety module.
- Touching release metadata, version files, tags, GitHub Releases, or PyPI.
- Starting the `v0.6.21` release cutover.
- Altering CAND-013's accepted status.

## 23. Acceptance criteria

- Inventory and duplication taxonomy verified against the repository (done here).
- Contract-sensitive surfaces enumerated with the exact artifacts that enforce
  them (done here).
- A declarative `ArtifactSpec`/engine concept defined with a clear split between
  shared mechanics and per-artifact data.
- A staged, reversible extraction strategy with a named low-risk pilot and a
  golden-test gating plan.
- Design introduces no forbidden claims; all release/safety checkers pass; no
  runtime/test/version/release files changed by this design commit.

## 24. Open questions

1. **Candidate-ID collision:** `CAND-014` was previously used for a v0.6.12-era
   candidate (`docs/releases/v0.6.12-candidates.*`, release-assurance diagnostics).
   The candidate-chain checker only enforces uniqueness *within* a single JSON
   file, so this does not fail any check today, but the reuse should be confirmed
   with the maintainer before CAND-014 is added to `v0.6.21-candidates.json` at
   acceptance time.
2. Should `provider_*_contract` artifact modules (whose outputs are themselves
   contracts) be migrated in the same family pass, or deferred to last?
3. Are the additional per-module hash-excluded fields (beyond
   `{"artifact_hash", "created_at"}`) intentional per artifact, or accidental?
   Inventory them before unifying.
4. Preferred pilot: mock_response seal (family payoff) vs a preflight/dry-run
   module (strictly read-only surface)? Recommendation: the seal, unless a
   read-only-only pilot is required.
5. Target for the CLI dispatch layer (`cli_commands/research/`, ~11k lines): is
   its deduplication in scope for this engine, or a separate follow-up candidate?

## 25. Design-readiness verdict

**READY_FOR_IMPLEMENTATION_PLAN.** The duplication claims are verified (and are
somewhat larger than reported), the contract-sensitive surfaces are enumerated, a
declarative engine concept is defined, and a safe, staged, reversible extraction
plan with a named pilot and golden-test gates is specified. The recommended next
step is a separate CAND-014 implementation-plan prompt that begins with Option C
(inventory + goldens) before any extraction.
