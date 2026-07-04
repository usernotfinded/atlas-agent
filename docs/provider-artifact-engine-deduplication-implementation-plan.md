# CAND-014 — Provider Artifact Engine Deduplication (Implementation Plan)

> **Not financial advice.** Atlas Agent is a software tool, not a financial
> advisor. Trading involves significant risk of loss. This document is an
> implementation-plan proposal only. It changes no runtime behavior, enables no
> live trading or live submit, authorizes no order placement, loads no
> credentials, makes no broker or provider calls, and adds no network access.

## 1. Title and candidate ID

- **Candidate:** CAND-014 — Provider Artifact Engine Deduplication.
- **Type:** Implementation-plan only. It does **not** implement the artifact
  engine, add golden tests, or modify provider/CLI/checker/runtime/safety code.
- **Release line:** `v0.6.21` (planning-only; not released).
- **Design source:** `docs/provider-artifact-engine-deduplication-design.md`
  (verdict `READY_FOR_IMPLEMENTATION_PLAN`).
- **CAND-ID note:** `CAND-014` is the correct next ID in the current global
  numbering epoch (see §5). It is unused by any current-epoch candidate doc.

## 2. Baseline state

- HEAD `d610dfcdd98bae31916d9914450543607b7e69ac`
  (`docs(cand-014): design provider artifact engine dedupe`), `origin/main` in
  sync, working tree otherwise clean.
- Package/source version `0.6.20`; current public `v0.6.20`; next planned
  `v0.6.21`; PyPI unpublished; no `v0.6.21` tag or GitHub Release.
- CAND-013 remains accepted in the `v0.6.21` candidate chain
  (`PASS_WITH_WARNINGS`).
- Baseline checkers pass: `check_version_consistency`, `check_release_metadata`,
  `check_candidate_chain` (historical warnings only), `check_public_docs_consistency`,
  `check_forbidden_claims`, `check_bounded_autonomy_governance`,
  `check_trust_center`, `check_onboarding_docs`, `check_public_launch_readiness`;
  `mypy src/atlas_agent/safety/kill_switch.py` clean; `atlas run --mode live`
  fail-closed (exit `2`, verified in a safe isolated offline paper workspace —
  see §19).

## 3. Design summary

The design verified (and slightly increased) the audit's duplication claims and
recommended a staged extraction:

- **22** `provider_*.py` modules, **28,908** source lines, grouped into families
  (`adapter_interface` ×2, `execution_*` ×5, `mock_response_*` ×5, `response_*`
  ×3, and 7 singletons), plus ~48k lines of provider tests and ~11k lines of
  research CLI.
- Each module re-implements the same lifecycle (`build_dict` → `create` →
  `load`/`load_and_validate` → `find_by_id`/`iter` → `validate`/`safe_validate` →
  `replay` → `summarize` → `doctor`) plus per-module constants, validators,
  `*_sha256`, and policy builders.
- Already shared (reuse, do not re-extract): `canonical_json_dumps`
  (`src/atlas_agent/research/sandbox_contracts.py`), `ResearchSessionError`,
  `MAX_CONTRACT_TEXT_CHARS`.
- Recommended strategy: **Option C first** (inventory + golden characterization
  tests, zero refactor), **then Option B** (one pilot module extraction with full
  compatibility guarantees), then family-by-family. Avoid Option A (big-bang).
- Pilot: `src/atlas_agent/research/provider_mock_response_final_safety_seal.py`.
- Contract-sensitive surfaces that must stay byte-identical: CLI command names
  (`tests/fixtures/cli_command_contract.json`), CLI status/result codes,
  artifact-name error codes, `*_VERSION` strings, artifact hashes, excluded-hash
  fields, canonical JSON ordering, JSON field names, exit codes.

This plan follows that recommendation exactly: **Phase 1 is inventory + golden
characterization tests only. No extraction.**

## 4. Current inventory verification

Re-verified at HEAD `d610dfc` (after the `0ea6c92` CLI refactor is on main):

| Metric | Design report | Current HEAD | Status |
|---|---|---|---|
| `provider_*.py` modules | 22 | **22** | unchanged |
| provider source lines | 28,908 | **28,908** | unchanged |
| `validate_provider_id` defs | 21 | **21** | unchanged |
| `_get_disabled_provider_ids` defs | 16 | **16** | unchanged |
| provider test files | 84 (`test_*provider_*`) | **87** (`*provider*`) | consistent (glob breadth differs) |
| pilot module lines | 1103 | **1103** | unchanged |

The `0ea6c92` CLI refactor moved research CLI dispatch into
`src/atlas_agent/cli_commands/research/` but did **not** change the
`src/atlas_agent/research/provider_*` module inventory or the duplication
assumptions. All design numbers still hold.

## 5. CAND-ID reuse analysis

Candidate IDs were mapped across every `docs/releases/v*-candidates.json`:

- **Legacy epoch (v0.6.1 – v0.6.16):** release-**local** numbering. `CAND-001`…
  `CAND-010` appear in ~10 different release lines; `v0.6.12` reached `CAND-016`;
  `v0.6.13` used an outlier `CAND-021`…`CAND-031`. Cross-release-line ID reuse was
  routine in this epoch. The historical `CAND-014` lives here (`v0.6.12` —
  "Release Assurance Diagnostics Artifact Workflow Integration").
- **Current epoch (v0.6.17+):** **globally monotonic**, exactly one candidate per
  release line: `v0.6.17`=CAND-009, `v0.6.18`=CAND-010, `v0.6.19`=CAND-011,
  `v0.6.20`=CAND-012, `v0.6.21`=CAND-013. The natural next ID is **CAND-014**.
- **Checker behavior:** `scripts/check_candidate_chain.py` `validate_candidate_ids`
  enforces uniqueness only **within a single JSON file** (per-file `seen` set); it
  does **not** enforce global uniqueness. No current-epoch candidate doc uses
  `CAND-014`.

**Classification: PASS (non-blocking WARNING).** Using `CAND-014` for `v0.6.21` is
the correct next ID in the current global sequence and is unused by any
current-epoch doc. The only overlap is the abandoned legacy `v0.6.12` `CAND-014`,
which is consistent with the legacy epoch's pervasive release-local reuse and is
permitted by the checker. This is a cosmetic collision, not a blocker. It does not
affect Phase 1 (goldens), which are ID-independent. Per repository convention it
should nonetheless be **confirmed by the maintainer before** `CAND-014` is written
into `v0.6.21-candidates.json` at the future acceptance step (this plan does not
create acceptance docs).

## 6. Implementation scope

This plan authorizes a future **Phase 1** implementation only:

**CAND-014 Phase 1 — Provider Artifact Inventory and Golden Characterization
Tests.** Phase 1 explicitly does **not** extract the artifact engine. It captures
current behavior so later extraction can be proven byte-identical.

Later phases (Phase 2+: engine introduction, pilot migration, family migration)
are described as constraints only (§17) and require their own separate
plan/candidate and review.

## 7. Non-goals

- Implementing the artifact engine, `ArtifactSpec` types, or migrating any module.
- Adding golden tests in this task (they are Phase 1 work, not this plan).
- Changing any CLI command, status code, error string, JSON field, exit code, or
  artifact hash.
- Changing provider/broker/network/credential behavior or any safety module.
- Touching release metadata, version files, tags, GitHub Releases, or PyPI.
- Creating or updating `v0.6.21` candidate-chain acceptance docs.
- Starting the `v0.6.21` release cutover; altering CAND-013's accepted status.

## 8. Phase 1 plan: inventory + golden characterization tests

**Objective:** freeze the current, observable behavior of the pilot module and
produce a machine-checkable inventory, with zero behavior change.

**Expected files (future Phase 1 implementation — not created here):**

- `tests/test_provider_artifact_golden_contracts.py` — golden characterization
  tests for the pilot module (see §10, §16).
- `tests/fixtures/provider_artifacts/` — deterministic golden fixtures (canonical
  JSON artifacts, expected hashes, expected CLI JSON/text, expected diagnostics).
- `docs/provider-artifact-engine-deduplication-inventory.md` — the enumerated
  per-module lifecycle/validator/constant/hash inventory (docs-backed).
- Optional (only if the repo prefers scripts): `scripts/inventory_provider_artifacts.py`
  — a deterministic, stdlib-only, read-only inventory generator.

**Constraints for Phase 1:** no engine extraction; no behavior change; no CLI
output change; no hash change; no schema change; no error-string normalization; no
provider/network/credential behavior change; no changes to provider modules
themselves. Golden tests must pass against **today's** code unchanged.

## 9. Pilot module

`src/atlas_agent/research/provider_mock_response_final_safety_seal.py` (1103 lines)
— smallest full-lifecycle module in the highest-duplication family
(`provider_mock_response_*`, 5 modules), artifact-only and local (no live/broker/
provider/network/credential behavior), with a dedicated test file
`tests/research/test_research_provider_mock_response_final_safety_seal.py`.

Public API to freeze (import compatibility): `create_*`, `build_*_dict`, `load_*`,
`load_and_validate_*`, `find_*_by_id`, `validate_*_artifact`, `safe_validate_*_data`,
`iter_*_artifacts`, `replay_*`, `summarize_*`, `doctor_*`, `*_sha256`,
`validate_provider_id`, and its constants (`*_VERSION`, `_*_HASH_EXCLUDED_FIELDS`,
`_VALID_*_STATUSES`). CLI ops: the `research provider-mock-response-*` seal
commands routed via `cli_commands/research/mock_response.py`.

## 10. Golden fixture strategy

- Generate golden outputs from **current** behavior and store them under a
  deterministic path (`tests/fixtures/provider_artifacts/final_safety_seal/`).
- Normalize non-deterministic inputs in tests (e.g., inject a fixed `created_at`
  or exclude it — it is already a hash-excluded field — and use a fixed workspace
  temp dir) so fixtures are reproducible.
- For **hash-relevant** surfaces, store the exact canonical JSON bytes and the
  exact `artifact_hash`; assert byte-identical.
- For **display** surfaces (CLI text), assert byte-identical where stable; where a
  field is inherently variable, assert on the stable subset while still freezing
  the canonical JSON used for hashing.
- Never silently normalize `validate_provider_id` error strings; capture them
  verbatim per §13.

## 11. Compatibility invariants

Any later extraction must preserve, and Phase 1 goldens must lock:

- Public Python function/constant names (kept importable, at minimum via shims).
- CLI command names and literal `args.research_command == "..."` dispatch strings.
- CLI text labels and JSON field names.
- Exit codes for each op.
- Error strings where tests/checkers depend on them.
- Artifact schema fields and `*_VERSION` strings.
- `artifact_hash` values; excluded-hash fields (`{"artifact_hash", "created_at"}`
  plus any per-module extras); canonical JSON ordering (`canonical_json_dumps`).
- Replay semantics, doctor diagnostics, summary output, path resolution, disabled-
  provider handling.

## 12. Contract-sensitive surfaces

- **CLI commands:** `tests/fixtures/cli_command_contract.json` +
  `scripts/check_cli_command_compatibility.py` (parser-only). No renames.
- **CLI status/result codes:** e.g.
  `research_provider_mock_response_..._validated` / `..._validation_failed`,
  `provider_mock_response_..._listed`.
- **Error codes:** `invalid_provider_..._provider`, `missing_provider_...`,
  `invalid_provider_id` (raised via `ResearchSessionError`).
- **Hash surface:** `*_sha256` output; excluded fields; canonical ordering.
- **Existing contract-artifact modules** (`provider_adapter_interface_contract`,
  `provider_response_schema_contract`) whose outputs are consumed elsewhere.

## 13. `validate_provider_id` preservation plan

- Inventory all **21** current definitions: one dominant byte-identical form
  (~8 copies: fail-closed against `_get_disabled_provider_ids()`, raising
  `ResearchSessionError("invalid_provider_id")`) plus ~13 minor variants.
- For the pilot, capture the exact current message and accepted/rejected inputs in
  goldens.
- In later extraction: map only byte-identical validators to the shared engine
  validator; keep documented variants behind explicit per-spec validator hooks.
- **Forbid** silent normalization of any `validate_provider_id` error string; every
  difference must be recorded in the inventory doc before any unification.

## 14. Hash / canonicalization preservation plan

- Keep `canonical_json_dumps` as the single canonicalizer (already shared).
- Freeze each module's `*_HASH_EXCLUDED_FIELDS` verbatim (base
  `{"artifact_hash", "created_at"}` plus any per-module extras — inventory them).
- Freeze `*_VERSION` strings (they participate in the hashed payload).
- Golden-assert the sha256 of representative artifacts; extraction is valid only if
  hashes are identical. Any intentional hash change must be a **versioned**
  migration (new `*_v2` version string), never an in-place change.

## 15. CLI contract preservation plan

- No command renames, no added/removed subcommands in Phase 1 or the first
  extraction.
- Keep `handle_provider_*` entry points and dispatch literals.
- Re-run `scripts/check_cli_command_compatibility.py` against an unchanged
  `tests/fixtures/cli_command_contract.json`.
- Golden-freeze CLI JSON and text output plus exit codes for each pilot op.

## 16. Test implementation plan

Phase 1 golden test file (`tests/test_provider_artifact_golden_contracts.py`) must
cover, for the pilot: module import side effects (none); create/build determinism;
load; validate success; validate failure diagnostics; invalid provider-id
diagnostics; missing-file handling; JSON canonicalization; artifact hash output;
hash-excluded fields; stable sorting; replay output; summarize output; doctor
output; CLI JSON output; CLI text output; exit codes; error strings; version
field; status fields; disabled-provider handling. Tests must be deterministic,
local, stdlib/pytest-only, load no credentials, make no network/broker/provider
calls, and pass on current code unchanged.

## 17. Future Phase 2 extraction constraints

Phase 2+ (separate candidate/plan) will introduce the engine and migrate the pilot,
then families one at a time. It must preserve everything in §11–§15, and it is
**explicitly forbidden** to: perform a big-bang extraction across all modules;
unify all `validate_provider_id` variants in one PR; change artifact hashes without
a versioned migration; change CLI contract strings before the contract
checker/fixture are updated; or touch live provider execution behavior. Each phase
is gated by the Phase 1 goldens.

## 18. Verification matrix

| Concern | Gate (Phase 1) |
|---|---|
| Behavior frozen, unchanged | goldens pass on current code; `git diff` shows only new test/fixture/doc files |
| Artifact hash captured | golden sha256 fixtures |
| CLI commands unchanged | `check_cli_command_compatibility.py` + `cli_command_contract.json` |
| Error strings captured | golden assertions incl. `validate_provider_id` |
| Determinism | repeated-run equality |
| Safety boundaries | §19 checks; `mypy` on kill_switch; no runtime diff |
| Release invariants | `check_version_consistency`, `check_release_metadata`, `check_candidate_chain`, `check_public_docs_consistency`, `check_forbidden_claims` |

## 19. Safety and release invariants

This plan and the future Phase 1 preserve: no live trading; no live submit; no
order placement/cancellation/flattening; no pending-order creation; no
approval-queue mutation; no broker/provider calls; no credential loading; no
network access; no weakening of RiskManager/kill-switch/deadman/heartbeat; no audit
hash-chain bypass. The provider modules make no real side-effecting calls today, so
this is a pure-refactor concern; the dominant hazard is contract drift, mitigated
by goldens. `atlas run --mode live` remains fail-closed (exit `2`, verified in a
safe isolated offline paper workspace because the local config carries live
credentials). Version stays `0.6.20`; current public stays `v0.6.20`; next planned
stays `v0.6.21`; PyPI unpublished; no `v0.6.21` tag or GitHub Release.

## 20. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Goldens accidentally encode non-determinism | Medium | fixed `created_at`/workspace; canonical JSON; repeated-run equality |
| Byte-identical CLI/error/hash drift in later phases | High | goldens first; pilot-only; no renames; versioned hash migration only |
| `validate_provider_id` variant flattening | Medium | inventory all 21 forms; per-spec hooks; no silent normalization |
| Hidden cross-module imports break later | Medium | keep public API via shims; import smoke tests |
| Reviewer overload | Medium | small per-family PRs, each gated by goldens |
| CAND-ID cosmetic collision (legacy v0.6.12) | Low | non-blocking; confirm with maintainer before acceptance docs (§5) |

## 21. Rollback plan

Phase 1 is purely additive (new test/fixture/doc files; no edits to provider/CLI/
runtime code), so rollback is a single `git revert` of the Phase 1 commit with no
behavioral impact. No migration, no data format change, no version bump — nothing
to un-migrate. Later extraction phases are individually revertible because each is
gated by the goldens and preserves public API via shims.

## 22. Acceptance criteria

For this implementation-plan candidate to be considered complete:

- Design recommendation (Option C then Option B) is translated into a concrete,
  staged, plan (done here).
- Current inventory re-verified against the design at HEAD `d610dfc` (done, §4).
- CAND-ID reuse analyzed and classified (done, §5).
- Phase 1 scope, pilot, golden strategy, compatibility invariants, contract
  surfaces, `validate_provider_id`/hash/CLI preservation, and test plan defined.
- Design introduces no forbidden claims; all release/safety checkers pass; no
  source/test/runtime/version/release files changed by this plan commit.

For the future Phase 1 implementation: goldens pass on current code; only new
test/fixture/doc files added; all §18 gates green.

## 23. Open questions

1. **CAND-ID (non-blocking):** confirm `CAND-014` for `v0.6.21` with the maintainer
   before it is written into `v0.6.21-candidates.json` at acceptance time (§5). It
   does not block Phase 1.
2. Fixture location: `tests/fixtures/provider_artifacts/` vs a per-module
   subdirectory — confirm preferred layout with existing fixture conventions.
3. Inventory as docs-only vs a `scripts/inventory_provider_artifacts.py` generator —
   confirm the repository's preference.
4. Should the CLI dispatch layer (`cli_commands/research/`, ~11k lines) dedup be a
   later phase of CAND-014 or a separate candidate?
5. Per-module extra hash-excluded fields (beyond `{"artifact_hash","created_at"}`):
   intentional per artifact, or accidental? Inventory before unifying.

## 24. Implementation-readiness verdict

**READY_FOR_PHASE_1_IMPLEMENTATION_WITH_ID_REUSE_WARNING.**

Definition: the plan is ready for a separate **Phase 1** implementation prompt
(inventory + golden characterization tests only, no extraction), which is fully
unblocked and ID-independent. The single caveat is the cosmetic `CAND-014` reuse
versus the abandoned legacy `v0.6.12` candidate (§5): it is permitted by the
checkers and consistent with the repository's historical release-local numbering,
and it must be explicitly confirmed by the maintainer **only** before `CAND-014` is
recorded in `v0.6.21` candidate-chain **acceptance** docs — not before Phase 1
goldens. No blockers exist for Phase 1.
