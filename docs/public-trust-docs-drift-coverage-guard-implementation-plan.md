# CAND-013: Public/Trust Docs Drift Coverage Guard — Implementation Plan

> **Candidate ID:** CAND-013
> **Title:** Public/Trust Docs Drift Coverage Guard
> **Document type:** Implementation plan (implementation-plan-only; no checker code changes in this task)
> **Design document:** `docs/public-trust-docs-drift-coverage-guard-design.md`
> **Design commit:** `9b59147f7ef9c73fb12645e7e20152f02810bf38`
> **Design fixup commit:** `a5c973c22caeb0df1dcfc88e2da80c56fb0c31cc`
> **Design readiness verdict:** `READY_FOR_IMPLEMENTATION_PLAN`
> **Repository:** `usernotfinded/atlas-agent`
> **Branch:** `main`
> **Plan-authoring HEAD:** `a5c973c22caeb0df1dcfc88e2da80c56fb0c31cc`
> **Baseline public release:** `v0.6.20`
> **Baseline package/source version:** `0.6.20`
> **Next planned release:** `v0.6.21`

## 1. Title and candidate ID

- **Candidate ID:** `CAND-013`
- **Title:** Public/Trust Docs Drift Coverage Guard
- **Subtitle:** Strengthen automated public/trust documentation drift detection so stale current/latest release and candidate-state claims are caught before future release cutovers.
- **Safety classification:** docs/checker/test-only; no runtime, safety, broker, provider, or execution changes.
- **This document:** Breaks the approved design into concrete, reviewable implementation steps. It does **not** implement the checker changes, does **not** add checker tests, and does **not** modify any checker script. The only file created by this task is this plan document.

## 2. Baseline state

Verified locally at plan-authoring time (`python3.11` resolves to a pyenv shim; interpreter used is CPython 3.14):

| Check | Command | Result |
|---|---|---|
| HEAD | `git rev-parse HEAD` | `a5c973c22caeb0df1dcfc88e2da80c56fb0c31cc` ✓ |
| Tag on HEAD | `git tag --points-at HEAD` | none (expected; `v0.6.20` points to the release commit, not HEAD) |
| `v0.6.20` target | `git rev-parse v0.6.20^{}` | `4d908aa8007cf60c3c7d1b410fb59afaa5cf765b` ✓ |
| No `v0.6.21` local tag | `git tag --list 'v0.6.21*'` | empty ✓ |
| No `v0.6.21` remote tag | `git ls-remote --tags origin 'v0.6.21*'` | empty ✓ |
| No `v0.6.21` release | `gh release view v0.6.21` | `release not found` ✓ |
| `v0.6.20` release exists | `gh release view v0.6.20` | present, `draft: false`, `prerelease: false` ✓ |
| Package version | `import atlas_agent; atlas_agent.__version__` | `0.6.20` ✓ |
| Version consistency | `scripts/check_version_consistency.py` | exit 0 — `package=0.6.20 public_tag=v0.6.20` ✓ |
| Release metadata | `scripts/check_release_metadata.py` | exit 0 — PASSED ✓ |
| Public docs consistency | `scripts/check_public_docs_consistency.py` | exit 0 — PASSED ✓ |
| Candidate chain | `scripts/check_candidate_chain.py` | exit 0 — PASSED ✓ |
| Candidate-chain tests | `pytest tests/test_candidate_chain.py -q` | 23 passed ✓ |
| Forbidden claims | `scripts/check_forbidden_claims.py` | exit 0 — clean ✓ |
| Bounded autonomy governance | `scripts/check_bounded_autonomy_governance.py` | exit 0 — next planned `v0.6.21` ✓ |
| Trust center | `scripts/check_trust_center.py` | exit 0 — 0 blocking findings ✓ |
| Onboarding docs | `scripts/check_onboarding_docs.py` | exit 0 ✓ |
| Public launch readiness | `scripts/check_public_launch_readiness.py` | exit 0 ✓ |
| CLI command compatibility | `scripts/check_cli_command_compatibility.py` | exit 0 ✓ |
| Safety atomic write | `scripts/check_safety_atomic_write.py` | exit 0 — PASSED ✓ |
| Kill-switch types | `mypy src/atlas_agent/safety/kill_switch.py` | Success: no issues ✓ |
| Live fail-closed | `atlas run --mode live` | exit `2` (fail-closed) ✓ |
| Whitespace | `git diff --check` | clean ✓ |

**Working-tree deviation (disclosed):** The working tree is **not** clean at plan-authoring time. It carries an unrelated, uncommitted CLI refactor from earlier work in the same session (modified `src/atlas_agent/cli.py`, new `src/atlas_agent/cli_commands/*` modules, one test file). That refactor is orthogonal to CAND-013: it touches no docs, no release metadata, no checker under this candidate, no version files, and no release state. All release-state invariants above were verified directly, and every doc/release checker passes. This plan's only deliverable is a new documentation file, which does not interact with the refactor.

**Heavyweight gate note:** `scripts/dev_check.sh`, `scripts/ci_check.sh`, and `scripts/release_check.sh --quick` (which delegates to `dev_check.sh`) were **not** run to completion. They use `set -euo pipefail` and invoke `tests/test_release_assurance_bundle_manifest.py`, which fails **pre-existing** at HEAD `a5c973c` (confirmed against a clean `git worktree` of HEAD; it is one of ~17 environment/release-hygiene tests that are red on this release commit, none caused by CAND-013 or by the refactor). Running the full gates would halt on that pre-existing failure without adding signal for a docs-only planning task. Every release-state and doc/release checker relevant to CAND-013 was verified directly and passes.

## 3. Design summary

CAND-013 adds automated coverage for two public/trust-doc drift classes that the `v0.6.20` readiness review caught manually but existing checks did not:

1. **Autonomy roadmap candidate-state contradiction** — `docs/autonomy-roadmap.md` claiming "no candidates are currently proposed for `vX.Y.Z`" while that release line's candidate-chain JSON already records accepted/released candidates.
2. **Trust README stale `(current public)` label** — `docs/trust/README.md` labeling an old release (e.g., `v0.6.17`) as `(current public)` when a newer release is current.

The approved design selects **Option A: extend `scripts/check_public_docs_consistency.py`** with two new detection functions plus small metadata/candidate-chain helpers, keeping the change inside a checker already wired into the dev/CI gates. The design's implementation-readiness verdict is `READY_FOR_IMPLEMENTATION_PLAN`.

## 4. Implementation scope

**Files to change during the (separate) implementation task:**

| File | Change |
|---|---|
| `scripts/check_public_docs_consistency.py` | Add two pure per-doc check functions, small metadata/candidate helpers, and wire them into `main()`. |
| `tests/test_public_docs_consistency.py` | Add unit tests (direct function calls via `_load_script_module()`) and keep the existing baseline subprocess test green. |
| `docs/development/checks-reference.md` | Extend the `check_public_docs_consistency.py` bullet to mention the two new coverage areas. |

**Explicitly not in scope (Option A):** `scripts/check_trust_center.py`, `scripts/check_candidate_chain.py`, `scripts/check_release_metadata.py`, `scripts/release_metadata.py`, `scripts/dev_check.sh`, `scripts/ci_check.sh`. Option A requires no dev/CI wiring change because `check_public_docs_consistency.py` already runs in both gates.

## 5. Non-goals

Per design §6, the implementation will **not**:

1. Fix historical `v0.6.20` drift (already fixed during the `v0.6.20` cutover).
2. Modify runtime, broker, provider, safety, risk, approval, kill-switch, deadman, heartbeat, or audit hash-chain code.
3. Modify `check_candidate_chain.py`, `check_trust_center.py`, `check_release_metadata.py`, `release_metadata.py`, `dev_check.sh`, or `ci_check.sh`.
4. Add NLP or heuristic doc understanding; detection stays deterministic and auditable.
5. Require public docs to duplicate every candidate-chain detail (no exhaustive-listing requirement).
6. Change the candidate-chain JSON schema or release-metadata schema.
7. Bump the package version, create a `v0.6.21` tag/GitHub Release, publish to PyPI, or start the `v0.6.21` cutover.
8. Exempt any doc from existing forbidden-claims checks or weaken any existing check.

## 6. Chosen implementation path

**Option A — extend `scripts/check_public_docs_consistency.py`.** Rationale (design §13): the stale claims are public-docs drift; the checker already imports `release_metadata`, already resolves `current_public_release` / `next_planned_release`, already scans both target files (`docs/trust/README.md` and `docs/autonomy-roadmap.md` are already in `PUBLIC_DOC_PATHS`), and already runs in dev/CI. The change is small, reviewable, and rollback is trivial.

### 6.1 Function shape (matches existing checker idioms)

The new detection functions follow the established `_check_xxx(text, rel_path, ...) -> list[str]` pure-function pattern (same as `_check_readme_required_safe`, which gates on `rel_path`). They are pure over their inputs so they can be unit-tested by importing the module and calling them directly (the pattern already used for `_check_readme_current_version` in the test file). All metadata/candidate-chain resolution happens **once** in `main()` and is passed in as plain values, so the per-doc scan stays side-effect-free and deterministic.

Planned additions:

```text
# Metadata / candidate-chain resolution (called once in main()):
_get_next_planned_release(repo_root) -> str
_historical_release_tags(repo_root) -> set[str]
_next_planned_has_accepted_candidates(repo_root, next_planned_release) -> bool

# Pure per-doc scanners (called inside the existing PUBLIC_DOC_PATHS loop):
_check_trust_readme_current_public_labels(
    text, rel_path, current_public_release, next_planned_release, historical_tags
) -> list[str]
_check_autonomy_roadmap_candidate_state(
    text, rel_path, next_planned_release, has_accepted_candidates
) -> list[str]
```

The design's illustrative helper names (`load_release_metadata`, `get_current_previous_next_releases`, `scan_trust_readme_labels`, …) map onto the concrete functions above; the concrete names reuse the checker's existing `_get_*` / `_check_*` conventions instead of introducing a new naming style.

### 6.2 `main()` wiring

In `main()`, alongside the existing `current_version` / `current_public_release` resolution (wrapped in the same `try/except` that returns `1` on metadata error):

1. Resolve `next_planned_release = _get_next_planned_release(REPO_ROOT)`.
2. Resolve `historical_tags = _historical_release_tags(REPO_ROOT)`.
3. Resolve `has_accepted_candidates = _next_planned_has_accepted_candidates(REPO_ROOT, next_planned_release)`.
4. Inside the existing `for path in PUBLIC_DOC_PATHS` loop, append:
   - `all_violations.extend(_check_trust_readme_current_public_labels(text, str(rel), current_public_release, next_planned_release, historical_tags))`
   - `all_violations.extend(_check_autonomy_roadmap_candidate_state(text, str(rel), next_planned_release, has_accepted_candidates))`

Because both new functions gate on `rel_path` and return `[]` for non-target files, adding them to the loop is safe for every other scanned doc.

## 7. Data sources and metadata authority

- **Release identity:** `docs/releases/release-metadata.json`, read through the existing `release_metadata.ReleaseMetadata` wrapper (already imported via `sys.path.insert(0, str(REPO_ROOT / "scripts"))`). Fields used:
  - `.current_public_release` → `v0.6.20` (the only tag allowed a current-public label).
  - `.next_planned_release` → `v0.6.21` (roadmap candidate-state subject; must not be labeled current public).
  - `.releases` → list of records; entries with `status == "historical"` yield `historical_tags` (`v0.6.19 … v0.6.7`). Note the current entry uses `status == "current_public"`.
  - `.pypi_published` → `false`; the checker must never assert PyPI publication.
- **Candidate evidence:** `docs/releases/{next_planned_release}-candidates.json` (i.e., `docs/releases/v0.6.21-candidates.json`). Candidate records expose `id`, `status` (`proposed` / `accepted` / `released` / …), and `accepted` (bool). Accepted/released signal = `status in {"accepted","released"}` **or** `accepted is True`.
- **Baseline reality at plan time:** `docs/releases/v0.6.21-candidates.json` **does not exist yet**, so `_next_planned_has_accepted_candidates` returns `False` (fallback, design §11.4) and the roadmap check is a no-op today. `docs/trust/README.md` already labels only `v0.6.20` as `(current public)` and older releases as `(historical)`, so the trust-label check passes today. **Implementing CAND-013 therefore requires no edits to the target docs to keep the baseline green.**

All reads are stdlib file I/O and `json.loads`. No environment variables, `.env` files, secrets, network, or runtime imports.

## 8. Detection rules

### 8.1 General principles (design §8.1)

- Derive expected labels from `release-metadata.json`; derive candidate state from candidate-chain JSON.
- Prefer contradiction detection over exhaustive prose parsing.
- Allow clearly historical paragraphs/labels.
- Emit one diagnostic per violation with file path and, where available, line number.
- **Exit-code convention (important accuracy point):** the existing `check_public_docs_consistency.py` returns `1` on any violation and `0` on pass (metadata/operational errors also return `1`). The design's generic "exit `2` on validation failure" does **not** match this specific checker. To preserve existing behavior, the new checks must append to `all_violations` and rely on the existing `return 1` path. **Do not introduce a new exit code `2` in this script.**

### 8.2 Covered docs

- Primary: `docs/trust/README.md`, `docs/autonomy-roadmap.md` (both already in `PUBLIC_DOC_PATHS`).
- Secondary current/latest coverage already handled by `_check_stale_public_release_claims` and `_check_stale_release_status_lines`; CAND-013 does not duplicate those. The parenthetical-label extension (design §9.4 / open question §3) is scoped to the trust README function to avoid overlap.

## 9. Trust README validation

Function: `_check_trust_readme_current_public_labels(text, rel_path, current_public_release, next_planned_release, historical_tags)`.

- **Gate:** return `[]` unless `rel_path == "docs/trust/README.md"` (mirrors `_check_readme_required_safe`'s `rel_path` gate).
- **Normalization:** strip markdown emphasis characters (`` ` ``, `*`, `_`) as `_check_stale_release_status_lines` does, so labels inside code spans/links are seen.
- **Current-public label forms to detect (case-insensitive):** parenthetical `(current public)`, `(current public release)`, `(current public — …)`, and inline shorthand pairing a release tag with `current public` in list-item or link text (design §9.1, §9.4). The real file uses both a parenthetical form (`… (current public)`) and an inline form (`Public v0.6.20: current public — …`); both must be recognized.
- **Per-line rule:** for each line, identify the release tag `vX.Y.Z` the current-public label applies to.
  - If that tag `== current_public_release` → allowed (no violation).
  - If that tag is in `historical_tags` (or is any tag `!= current_public_release`) → violation: `"[docs/trust/README.md] Stale (current public) label on line N: 'vX.Y.Z' (expected {current_public_release})"`.
  - If that tag `== next_planned_release` → violation (design §9.3: next planned must not be current public).
- **Historical/next-planned exemptions:** lines whose context includes `historical`, `previous public`, `(historical)`, `(next planned)`, `(planning-only)`, `(planning)` are allowed for their non-current tags. Only a positive current-public label attached to a non-current tag fails (design §18: allow `(historical)` or no label).
- **Recommended scope for first implementation (design open question §21.1):** only *forbid* old/next-planned tags from carrying the current-public label. Do **not** yet require the current release to carry the label (do not fail when the current tag is unlabeled).

## 10. Public release claim validation

- The stale current/latest **sentence** and **status-line** coverage already exists (`_check_stale_public_release_claims`, `_check_stale_release_status_lines`) and is **not** modified.
- CAND-013's only current/latest extension is the **parenthetical/inline `(current public)` label** coverage, implemented inside the trust README function (§9) to prevent overlap with the existing sentence-based checks.
- The checker must never emit language asserting PyPI publication; `pypi_published` stays `false` and is read-only.

## 11. Roadmap validation

Function: `_check_autonomy_roadmap_candidate_state(text, rel_path, next_planned_release, has_accepted_candidates)`.

- **Gate:** return `[]` unless `rel_path == "docs/autonomy-roadmap.md"`.
- **Guard:** if `has_accepted_candidates is False` → return `[]` (covers both "no accepted/released candidates" and "candidate-chain JSON missing", design §11.4).
- **Scope:** only the `next_planned_release` line (design open question §21.2 recommendation). Historical release lines already have fixed candidate prose and are not retroactively edited.
- **Stale "no candidates" phrases (case-insensitive, tolerant of minor whitespace/punctuation), matched against the `next_planned_release` string** (design §10.1):
  - `No candidates are currently proposed for {release_line}`
  - `No candidates proposed for {release_line}`
  - `no active candidates for {release_line}`
  - `no accepted candidates for {release_line}`
  - `no candidates are proposed for {release_line}`
- **Historical-tense exemption (design §10.2):** do not flag a matched phrase when its sentence/paragraph contains a past-tense/historical marker (`was`, `were`, `initially`, `before`, `historical`). Example that must stay passing: the existing line `No additional candidates were proposed for v0.6.20.` (past tense, and not the next-planned line).
- **Diagnostic on violation:** `"[docs/autonomy-roadmap.md] Roadmap contradicts candidate chain: claims no candidates for {next_planned_release} but accepted/released candidates are recorded"` (include line number when a matched phrase is found).
- **No exhaustive-listing requirement (design §11.3):** the roadmap is not required to enumerate candidate IDs.

## 12. Candidate-chain coordination

- Read `docs/releases/{next_planned_release}-candidates.json` in `_next_planned_has_accepted_candidates`.
- Accepted/released signal: any candidate with `status == "accepted"`, `status == "released"`, or `accepted is True`.
- Missing file → `False` (skip roadmap check; no failure).
- No candidate-chain schema change; no new required fields (design §11.3).
- `scripts/check_candidate_chain.py` and `tests/test_candidate_chain.py` remain untouched (only contradiction detection is added, in the public-docs checker, not in the candidate-chain checker).

## 13. Diagnostics policy

- Format matches the existing checker: `"[{rel_path}] <message>"`, one entry per violation appended to `all_violations`.
- Include a 1-based line number when the violation is line-anchored (mirrors `_check_stale_release_status_lines`).
- Deterministic ordering: violations accumulate in document/loop order; no set/dict iteration that would reorder output.
- Exit codes preserved: `0` pass, `1` any violation or metadata/operational error. No `2`.
- Metadata/candidate-chain read failures surface through the existing `main()` `try/except`, printing `Public docs consistency check FAILED` + `Metadata Error: …` and returning `1`.

## 14. False-positive mitigation

- **Trust README:** only a positive current-public label on a non-current tag fails; `(historical)`, `(next planned)`, `(planning-only)`, or no label all pass. The sanctioned `current_public_release` tag is always allowed the label.
- **Roadmap:** require **both** a stale "no candidates" phrase **and** `has_accepted_candidates is True`; exempt historical-tense paragraphs. When `v0.6.21-candidates.json` is absent (current baseline), the check is a no-op.
- **Scope discipline:** both functions gate on exact `rel_path`; no full-repo scan; only the two target files are inspected beyond existing coverage.
- **Label-variant tolerance:** case-insensitive regex matching the core `current public` phrase inside a larger label, so `(current public release)` / `(current public — …)` are handled without flagging benign prose.
- **No duplication:** current/latest sentence detection stays in the existing functions; the trust function only adds parenthetical/inline label detection.
- **Metadata robustness:** use the existing `ReleaseMetadata` accessors; if a required field is missing, fail via the existing metadata `try/except` rather than raising uncaught.

## 15. Test plan

Extend `tests/test_public_docs_consistency.py`. Two testing styles, both already present in the file:

- **Unit (preferred for the new logic):** `mod = _load_script_module()` then call the pure functions directly with a `rel_path` matching the gated filename (the file already uses this for `_check_readme_current_version` / `_check_stale_current_status_in_readme`). This avoids fixture-repo complexity because `_run_script_on_text` rewrites `PUBLIC_DOC_PATHS` to a temp doc whose `rel_path` would **not** match `docs/trust/README.md` or `docs/autonomy-roadmap.md`, so the gated checks would not trigger through that helper.
- **Integration:** the existing `TestScriptPassesOnCurrentDocs` runs the real script and asserts `returncode == 0`; it must stay green (the baseline already satisfies both new rules).
- **Candidate-JSON helper:** for `_next_planned_has_accepted_candidates`, build a `tmp_path` fixture with a minimal `docs/releases/v0.6.21-candidates.json` and assert `True`/`False`/missing-file behavior by calling the helper with that root.

Required cases (design §14.2) mapped to concrete assertions:

| Test | Call | Expectation |
|---|---|---|
| `test_trust_readme_current_public_label_passes` | `_check_trust_readme_current_public_labels(text_only_v0620_current, "docs/trust/README.md", "v0.6.20", "v0.6.21", historical_tags)` | `== []` |
| `test_trust_readme_old_release_current_public_fails` | same fn, `v0.6.17` labeled `(current public)` | non-empty; message mentions `v0.6.17` and `v0.6.20` |
| `test_trust_readme_historical_label_passes` | same fn, `v0.6.19` labeled `(historical)` | `== []` |
| `test_trust_readme_next_planned_not_current_public_passes` | same fn, `v0.6.21` labeled `(next planned)` | `== []` |
| `test_trust_readme_next_planned_current_public_fails` | same fn, `v0.6.21` labeled `(current public)` | non-empty; mentions `v0.6.21` |
| `test_roadmap_no_candidates_contradiction_fails` | `_check_autonomy_roadmap_candidate_state(text_no_candidates_v0621, "docs/autonomy-roadmap.md", "v0.6.21", True)` | non-empty; mentions `v0.6.21` |
| `test_roadmap_no_candidates_when_none_accepted_passes` | same fn with `has_accepted_candidates=False` | `== []` |
| `test_roadmap_historical_no_candidates_paragraph_passes` | same fn, historical-tense paragraph, `has_accepted_candidates=True` | `== []` |
| `test_next_planned_has_accepted_candidates_*` | `_next_planned_has_accepted_candidates(tmp_root, "v0.6.21")` | `True` (accepted/released), `False` (none), `False` (missing file) |
| `test_public_docs_still_pass_on_current_baseline` | run real script | `returncode == 0` |
| `test_no_forbidden_claims_introduced` | `scripts/check_forbidden_claims.py` on the repo | exit 0 |

Test-style constraints (design §14.3): assert exit codes and diagnostic substrings; avoid brittle full-output assertions; keep fixtures minimal and deterministic; no network, no credentials, no subprocess for the pure-function unit tests.

## 16. Dev/CI integration

- **Option A → no gate wiring change.** `scripts/check_public_docs_consistency.py` is already invoked by `scripts/dev_check.sh` and `scripts/ci_check.sh`; the new coverage runs automatically.
- **Docs update (in the implementation task):** extend the `check_public_docs_consistency.py` bullet in `docs/development/checks-reference.md` (currently lines ~18–21) to add: stale trust README `(current public)` labels, and autonomy-roadmap candidate-state contradictions against candidate-chain JSON (design §15.2 gives the exact replacement text).
- No new CI step, no `dev_check.sh`/`ci_check.sh` edits, no ordering changes.

## 17. Verification matrix

To run during the implementation task (all from repo root; `python3.11`):

| Step | Command | Expected |
|---|---|---|
| Whitespace | `git diff --check` | clean |
| Public docs (target checker) | `python3.11 scripts/check_public_docs_consistency.py` | exit 0 — PASSED |
| New/extended tests | `python3.11 -m pytest tests/test_public_docs_consistency.py -q` | all pass |
| Trust center (unchanged) | `python3.11 scripts/check_trust_center.py` | exit 0 |
| Candidate chain (unchanged) | `python3.11 scripts/check_candidate_chain.py` | exit 0 |
| Candidate-chain tests (unchanged) | `python3.11 -m pytest tests/test_candidate_chain.py -q` | 23 passed |
| Release metadata | `python3.11 scripts/check_release_metadata.py` | exit 0 |
| Version consistency | `python3.11 scripts/check_version_consistency.py` | exit 0 |
| Forbidden claims | `python3.11 scripts/check_forbidden_claims.py` | clean |
| Bounded autonomy governance | `python3.11 scripts/check_bounded_autonomy_governance.py` | exit 0 |
| Onboarding docs | `python3.11 scripts/check_onboarding_docs.py` | exit 0 |
| Public launch readiness | `python3.11 scripts/check_public_launch_readiness.py` | exit 0 |
| Kill-switch types | `mypy src/atlas_agent/safety/kill_switch.py` | zero issues |
| Live fail-closed | `atlas run --mode live` | exit `2` |
| Dev gate | `bash scripts/dev_check.sh` | pass (modulo pre-existing red tests unrelated to CAND-013) |
| CI gate | `bash scripts/ci_check.sh` | pass (same caveat) |
| Quick release gate | `bash scripts/release_check.sh --quick` | pass (same caveat) |

Expected invariants after implementation: version stays `0.6.20`; current public release stays `v0.6.20`; no `v0.6.21` tag/release; PyPI unpublished; live mode exits `2`.

## 18. Safety invariants

The implementation preserves every boundary (design §17). The checker is read-only, stdlib-only, no network, no credentials, no runtime imports, and does not mutate any state outside temporary test fixtures:

- no live trading enabled; no live submit enabled; `atlas run --mode live` exits `2` / fail-closed
- no order placement, cancellation, or position flattening; no pending-order creation
- no approval-queue mutation; no broker calls; no provider calls; no credential loading; no network access
- RiskManager not weakened; kill-switch, deadman, and heartbeat not weakened; audit hash-chain not bypassed
- package version remains `0.6.20`; current public release remains `v0.6.20`; next planned remains `v0.6.21`
- PyPI remains unpublished; no `v0.6.21` tag; no `v0.6.21` GitHub Release

## 19. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| False positive on trust README historical labels | Unnecessary doc rewording | Only fail on positive current-public labels attached to non-current tags; allow `(historical)`/`(next planned)`/no label. |
| False positive on roadmap historical paragraphs | Blocks legitimate historical prose | Require both a stale "no candidates" phrase and `has_accepted_candidates`; exempt past-tense markers. |
| Label variant drift (`(current public release)`, `(current public — …)`) | Missed or over-eager matches | Case-insensitive regex matching the core `current public` phrase within a larger label. |
| Exit-code mismatch with design's generic "exit 2" | Broken gate semantics | Preserve the existing `return 1`-on-violation convention; do not add exit `2`. |
| Test helper mismatch (`_run_script_on_text` rewrites `PUBLIC_DOC_PATHS`) | Gated checks silently untested | Unit-test the pure functions directly via `_load_script_module()`; keep one real-script baseline test. |
| Overlap with `check_trust_center.py` | Duplicate diagnostics for one stale label | Keep the new check narrow; accept minor overlap over a coverage gap (design §18). |
| Future release-metadata field changes | Broken label derivation | Use existing `ReleaseMetadata` accessors; fail via the existing metadata `try/except`. |

## 20. Rollback plan

CAND-013 is docs/checker/test-only (design §19):

1. Revert or delete the new functions in `scripts/check_public_docs_consistency.py` and the new tests in `tests/test_public_docs_consistency.py`.
2. Revert the `docs/development/checks-reference.md` bullet update.
3. Re-run the §17 verification matrix to confirm no safety boundary or release state changed.
4. No runtime state, tags, releases, or packages are affected; rollback is a pure revert.

## 21. Acceptance criteria

CAND-013 implementation is accepted when (design §20):

1. `scripts/check_public_docs_consistency.py` gains the two new detection functions plus the metadata/candidate-chain helpers, wired into `main()`, preserving the existing `0`/`1` exit-code behavior.
2. `tests/test_public_docs_consistency.py` covers every case in §15 (trust label pass/fail, next-planned label, roadmap contradiction/exemption, candidate-JSON helper, baseline pass, no forbidden claims) and all pass.
3. `python3.11 scripts/check_public_docs_consistency.py` exits `0` on the current repository.
4. `docs/development/checks-reference.md` documents the new coverage.
5. The §17 verification matrix passes (excluding pre-existing, CAND-013-unrelated red tests), and `atlas run --mode live` still exits `2`.
6. No runtime, safety, broker, provider, risk, approval, kill-switch, deadman, heartbeat, or audit hash-chain code is modified; `check_candidate_chain.py`, `check_trust_center.py`, `check_release_metadata.py`, `release_metadata.py`, `dev_check.sh`, and `ci_check.sh` are untouched.
7. No version bump, tag, GitHub Release, or PyPI publication occurs.

## 22. Implementation-readiness verdict

**Verdict:** `READY_FOR_IMPLEMENTATION`

Rationale:

- The design is approved (`READY_FOR_IMPLEMENTATION_PLAN`) and narrowly scoped to two concrete drift classes.
- The chosen path (Option A) reuses an existing checker that already loads release metadata, already scans both target files, and already runs in the dev/CI gates — no wiring changes required.
- The metadata API (`ReleaseMetadata.current_public_release` / `.next_planned_release` / `.releases` / `.release_by_tag` / `.pypi_published`) already exposes every field the new checks need.
- Detection rules are deterministic, metadata-driven, and have explicit historical-context exemptions; the exit-code convention is pinned to the existing `1`-on-violation behavior.
- The test approach is proven by existing patterns in `tests/test_public_docs_consistency.py`; the baseline already satisfies both new rules, so implementation needs no target-doc edits to stay green.
- No runtime, safety, broker, provider, or execution code is involved.

**Next step:** a separate implementation prompt that applies the §4 changes and §15 tests, then runs the §17 verification matrix.
