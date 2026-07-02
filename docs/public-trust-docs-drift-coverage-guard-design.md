# CAND-013: Public/Trust Docs Drift Coverage Guard — Design

> **Candidate ID:** CAND-013
> **Proposed title:** Public/Trust Docs Drift Coverage Guard
> **Proposed subtitle:** Strengthen automated public/trust documentation drift detection so stale current/latest release and candidate-state claims are caught before future release cutovers.
> **Design status:** design-only
> **Target implementation phase:** after independent design review
> **Repository:** `usernotfinded/atlas-agent`
> **Branch:** `main`
> **Baseline HEAD:** `4d908aa8007cf60c3c7d1b410fb59afaa5cf765b`
> **Baseline public release:** `v0.6.20`
> **Baseline package version:** `0.6.20`
> **Baseline next planned release:** `v0.6.21`

## 1. Title and candidate ID

- **Candidate ID:** `CAND-013`
- **Title:** Public/Trust Docs Drift Coverage Guard
- **Subtitle:** Strengthen automated public/trust documentation drift detection so stale current/latest release and candidate-state claims are caught before future release cutovers.
- **Safety classification:** docs/checker/test-only; no runtime changes.

## 2. Baseline state

At the time of this design, the repository is in the following state:

- `git status --short`: clean.
- `git rev-parse HEAD`: `4d908aa8007cf60c3c7d1b410fb59afaa5cf765b`.
- `git tag --points-at HEAD`: `v0.6.20`.
- `git rev-parse v0.6.20^{}`: `4d908aa8007cf60c3c7d1b410fb59afaa5cf765b`.
- `gh release view v0.6.20`: exists, GitHub-only.
- `git tag --list 'v0.6.21*'`: empty.
- `git ls-remote --tags origin 'v0.6.21*'`: empty.
- `gh release view v0.6.21`: not found.
- `atlas_agent.__version__`: `0.6.20`.
- `pyproject.toml` version: `0.6.20`.
- `src/atlas_agent/__init__.py` version: `0.6.20`.
- `docs/releases/release-metadata.json`: `source_version` `0.6.20`, `current_public_release` `v0.6.20`, `next_planned_release` `v0.6.21`, `pypi_published` `false`, `release_type` `github_only`.
- `atlas run --mode live`: exits `2` / fail-closed.
- `mypy src/atlas_agent/safety/kill_switch.py`: zero issues.
- All baseline verification commands pass.

## 3. Problem statement

Atlas Agent maintains public-facing docs (`docs/public-*.md`, `docs/autonomy-roadmap.md`) and trust docs (`docs/trust/README.md`, `docs/trust/vX.Y.Z-status.md`) that describe the current public release, historical releases, and the next planned release line. These docs are expected to stay aligned with `docs/releases/release-metadata.json`, which is the authoritative source for:

- current public release,
- previous public releases,
- next planned release,
- source/package version,
- PyPI publication status,
- release type.

During the `v0.6.20` release-readiness review, two stale public/trust doc claims were found manually that existing automated checks did not catch:

1. `docs/autonomy-roadmap.md` still said `No candidates are currently proposed for v0.6.20` after **CAND-012** had already been accepted into the `v0.6.20` candidate chain.
2. `docs/trust/README.md` still labeled `v0.6.17` Release Notes and Trust Status links as `(current public)` even though `v0.6.20` was the current public release and `v0.6.17` was historical.

These drifts are public-docs/trust problems, not runtime safety problems, but they erode reviewer confidence and can make a release-readiness review harder than it needs to be. They should be caught automatically before future release cutovers.

## 4. v0.6.20 missed findings

### 4.1 Autonomy roadmap stale candidate-state claim

**File:** `docs/autonomy-roadmap.md`
**Observed stale text (paraphrased from pre-cutover state):**

```markdown
### Candidate status in the `v0.6.20` release

`v0.6.20` is the current public GitHub release. ...

- **CAND-012** is accepted into the `v0.6.20` candidate chain ...
- No additional candidates are currently proposed for `v0.6.20`.
```

**What was wrong:** The first paragraph already stated CAND-012 was accepted, but a nearby line used a stale template phrase implying no candidates existed for `v0.6.20`. This contradiction passed all automated checks.

**Why existing checks missed it:**

- `scripts/check_public_docs_consistency.py` scans for stale version *numbers* and forbidden positive claims, but it does not compare `docs/autonomy-roadmap.md` prose against candidate-chain JSON to detect contradictions.
- `scripts/check_candidate_chain.py` validates candidate-chain files under `docs/releases/`, but it does not read `docs/autonomy-roadmap.md`.
- `scripts/check_trust_center.py` focuses on `docs/trust/README.md` and the current trust status file.

### 4.2 Trust README stale `(current public)` label on an old release

**File:** `docs/trust/README.md`
**Observed stale text (pre-cutover state):**

```text
- `v0.6.17 Release Notes` (`../releases/v0.6.17.md`) (current public)
- `v0.6.17 Trust and Release Status` (`v0.6.17-status.md`) (current public)
```

**What was wrong:** `v0.6.17` was historical; only `v0.6.20` should have been labeled `(current public)`.

**Why existing checks missed it:**

- `scripts/check_public_docs_consistency.py` flags stale public-release *sentences* like "`v0.6.17` is the latest stable public release", but it did not flag the shorter parenthetical label `(current public)` attached to a markdown link.
- `scripts/check_trust_center.py` checks that the current release is mentioned and that stale dev versions are absent, but it did not enforce that only the current public release row may carry the `(current public)` label.

## 5. Goals

CAND-013 adds automated coverage for the two missed drift classes, without weakening any existing gate:

1. **Trust README label coverage:** Only the release line matching `metadata.current_public_release` may be labeled `(current public)` in `docs/trust/README.md`. Historical releases must be labeled `(historical)` or equivalent.
2. **Autonomy roadmap candidate-state coverage:** If a release line has accepted/released candidates in its candidate-chain JSON, `docs/autonomy-roadmap.md` must not claim that no candidates are proposed/accepted for that release line.
3. **Current/latest release claim coverage:** Strengthen detection of stale "current public"/"latest release" claims in public docs by covering parenthetical link labels, not just full sentences.
4. **Deterministic local checking:** The new coverage must remain read-only, stdlib-only, no network, no credentials, no runtime imports.
5. **Fail-closed on contradiction:** A stale current-public label or a candidate-state contradiction must fail the relevant checker with a clear diagnostic.

## 6. Non-goals

CAND-013 explicitly does **not**:

1. Fix the historical `v0.6.20` drift; that was done during the `v0.6.20` cutover.
2. Implement the checker changes. This document is design-only.
3. Modify runtime code, broker adapters, provider adapters, safety modules, risk configuration, approval logic, kill-switch logic, deadman logic, heartbeat logic, or audit hash-chain code.
4. Modify `scripts/check_candidate_chain.py`, `tests/test_candidate_chain.py`, `scripts/dev_check.sh`, or `scripts/ci_check.sh` unless the chosen implementation option requires extending one of them.
5. Bump the package version, create a `v0.6.21` tag or GitHub Release, or publish to PyPI.
6. Start the `v0.6.21` release cutover.
7. Add broad NLP or heuristic doc understanding. Detection must be deterministic and auditable.
8. Exempt any doc from existing forbidden-claims checks.
9. Require public docs to duplicate every candidate-chain detail.
10. Change candidate-chain schema unless strictly necessary.

## 7. Metadata authority

The authoritative source of release identity is `docs/releases/release-metadata.json`:

| Field | Meaning for CAND-013 |
|---|---|
| `source_version` | Current source/package version (e.g., `0.6.20`). Used to derive `v{source_version}` when needed. |
| `current_public_release` | The only release line that may be labeled `(current public)` in trust docs. |
| `next_planned_release` | The release line that may be labeled `next planned` / `planning-only`; must not be labeled `(current public)`. |
| `releases[].tag` | Historical release tags. Any release tag in this list with `status: historical` must not be labeled `(current public)`. |
| `pypi_published` | Must remain `false`. The checker must not claim PyPI publication. |

The candidate-chain evidence source is `docs/releases/vX.Y.Z-candidates.json`:

| Field | Meaning for CAND-013 |
|---|---|
| `release_line` | The release line the file describes. |
| `candidates[].id` | Candidate ID. |
| `candidates[].status` | `proposed`, `accepted`, `released`, etc. |
| `candidates[].accepted` | Boolean acceptance flag. |

## 8. Detection rule design

### 8.1 General principles

- Use `docs/releases/release-metadata.json` to compute the expected current/previous/next release labels.
- Use `docs/releases/vX.Y.Z-candidates.json` to decide whether a release line has accepted/released candidates.
- Prefer contradiction detection over exhaustive prose parsing.
- Allow clearly historical paragraphs to mention old "no candidates" states if they are not labeled as current.
- Emit one diagnostic per violation with file path and line number when available.
- Exit code `0` on pass, `2` on validation failure, `1` on operational error (consistent with existing checkers).

### 8.2 Covered docs

Primary:

- `docs/trust/README.md`
- `docs/autonomy-roadmap.md`

Secondary (already partially covered; CAND-013 extends coverage):

- `docs/public-repo-hygiene.md`
- `docs/public-launch-messaging.md`
- `docs/public-faq.md`
- `docs/public-launch-readiness.md`

## 9. Trust README label rules

### 9.1 Current public release label

In `docs/trust/README.md`:

- Exactly one release line may be labeled `(current public)`: the value of `metadata.current_public_release`.
- The label may appear on the release-notes link, trust-status link, or both.
- Acceptable variants (case-insensitive): `(current public)`, `(current public release)`, `(current public — ...)`.

### 9.2 Historical release labels

- Any release line in `metadata.releases` with `status: historical` must not be labeled `(current public)`.
- Historical release links should be labeled `(historical)` or equivalent (e.g., `(historical)`, `(historical — ...)`) or have no parenthetical label at all if the surrounding prose makes the historical status clear.
- Labels like `(current public)` on `v0.6.17`, `v0.6.18`, or `v0.6.19` when `v0.6.20` is current must fail.

### 9.3 Next planned release label

- The release line matching `metadata.next_planned_release` may be labeled `(next planned)`, `(planning-only)`, `(planning)`, or left unlabeled.
- It must not be labeled `(current public)` or `(released)`.

### 9.4 Stale current-public shorthand detection

Also detect stale labels outside explicit parentheses:

- Markdown link text that pairs an old release tag with `current public` (e.g., a link titled `v0.6.17 Trust and Release Status (current public)`).
- List items that call an old release the `current public release` or `latest release`.

## 10. Autonomy roadmap candidate-state rules

### 10.1 Contradiction detection

For `docs/autonomy-roadmap.md`:

1. Load `metadata.next_planned_release`.
2. Load the corresponding candidate-chain JSON (`docs/releases/{next_planned_release}-candidates.json`).
3. Determine whether the candidate-chain JSON contains any candidate with:
   - `status` in (`accepted`, `released`), or
   - `accepted: true`.
4. If accepted/released candidates exist, scan `docs/autonomy-roadmap.md` for stale "no candidates" phrases that refer to that release line.

Stale "no candidates" phrases (matched against the release line string):

- `No candidates are currently proposed for {release_line}`
- `No candidates proposed for {release_line}`
- `no active candidates for {release_line}`
- `no accepted candidates for {release_line}`
- `no candidates are currently proposed for {release_line}`
- `no candidates are proposed for {release_line}`

These phrases are case-insensitive and tolerate minor whitespace/punctuation differences.

### 10.2 Historical paragraph exemption

A paragraph that explicitly discusses a past planning state is allowed to say "At the start of the cycle, no candidates were proposed for `v0.6.21`" if:

- the paragraph is clearly marked as historical (contains words like `was`, `were`, `historical`, `initially`, `before`), or
- the candidate-chain JSON for that release line has no accepted/released candidates.

The checker must not flag historical explanations as failures.

### 10.3 No exhaustive listing requirement

The checker does not require the roadmap to list every candidate ID. It only checks that the roadmap does not contradict the candidate-chain JSON by claiming no candidates exist when accepted/released candidates are recorded.

## 11. Candidate-chain coordination

### 11.1 Evidence file

For the next planned release line, read `docs/releases/{next_planned_release}-candidates.json`.

### 11.2 Accepted/released signal

A candidate is considered accepted/released if any of the following hold:

- `status` == `"accepted"`
- `status` == `"released"`
- `accepted` == `true`

### 11.3 No candidate-chain schema change

CAND-013 uses the existing candidate-chain JSON schema. It does not add new required fields.

### 11.4 Fallback if candidate-chain JSON is missing

If `docs/releases/{next_planned_release}-candidates.json` does not exist, the roadmap candidate-state check is skipped (no failure). The trust README label check still runs.

## 12. Implementation options

### Option A: Extend `scripts/check_public_docs_consistency.py`

**Approach:** Add two new check functions to the existing public-docs checker:

- `_check_trust_readme_current_public_labels(...)`
- `_check_autonomy_roadmap_candidate_state(...)`

Both functions read `docs/releases/release-metadata.json` (already imported by the script) and, for the roadmap check, the next planned candidate-chain JSON.

**Files touched:**

- `scripts/check_public_docs_consistency.py` (new functions)
- `tests/test_public_docs_consistency.py` (new test classes)
- `docs/development/checks-reference.md` (one-line mention of new coverage)

**Complexity:** Low. The script already loads metadata and scans public docs.

**False-positive risk:** Low to medium. Must carefully exempt historical paragraphs.

**Overlap:** Minimal. Extends an existing public-docs checker rather than creating a new one.

**Testability:** High. Existing test style uses `tmp_path` and subprocess wrappers.

**Dev/CI integration:** None required; `scripts/dev_check.sh` and `scripts/ci_check.sh` already call `check_public_docs_consistency.py`.

**Recommendation:** Preferred, unless trust-specific checks are judged to belong more naturally in `check_trust_center.py`.

### Option B: Split trust labels to `check_trust_center.py`, roadmap to `check_public_docs_consistency.py`

**Approach:** Add trust README label checks to `scripts/check_trust_center.py` and keep the autonomy roadmap candidate-state check in `scripts/check_public_docs_consistency.py`.

**Files touched:**

- `scripts/check_trust_center.py`
- `scripts/check_public_docs_consistency.py`
- `tests/test_trust_center.py`
- `tests/test_public_docs_consistency.py`
- `docs/development/checks-reference.md`

**Complexity:** Medium. Two files change instead of one.

**False-positive risk:** Low for trust labels; low to medium for roadmap.

**Overlap:** Slightly more surface area; trust center already reads metadata and trust docs.

**Testability:** High, but tests are split across two files.

**Dev/CI integration:** None required; both scripts already run in dev/CI.

**Recommendation:** Reasonable if reviewers prefer trust-label logic to live with other trust-center checks.

### Option C: Create `scripts/check_public_trust_docs_drift.py`

**Approach:** A new narrow checker dedicated to public/trust docs drift.

**Files touched:**

- `scripts/check_public_trust_docs_drift.py` (new)
- `tests/test_public_trust_docs_drift.py` (new)
- `scripts/dev_check.sh` (add step)
- `scripts/ci_check.sh` (add step)
- `docs/development/checks-reference.md` (new section)

**Complexity:** Medium. New file, new tests, new dev/CI wiring.

**False-positive risk:** Low to medium.

**Overlap:** Avoids changing existing checkers, but adds another script to maintain and run.

**Testability:** High, but more boilerplate.

**Dev/CI integration:** Required; must add the new script to gate scripts.

**Recommendation:** Not preferred unless the existing checkers are too large or the new coverage is expected to grow substantially.

## 13. Preferred implementation path

**Option A: Extend `scripts/check_public_docs_consistency.py`.**

Rationale:

- The stale claims are public-docs drift; the existing public-docs consistency checker is the natural home.
- The script already imports `release_metadata` and knows how to read `current_public_release` and `next_planned_release`.
- No dev/CI wiring changes are required because the script is already in the gates.
- Keeps the change small and reviewable.
- If trust-label logic grows in the future, it can be refactored into `check_trust_center.py` at that time.

## 14. Test plan

### 14.1 Test file

Extend `tests/test_public_docs_consistency.py` with new test classes.

### 14.2 Required tests

| Test | Expected result |
|---|---|
| `test_trust_readme_current_public_label_passes` | A trust README with only `v0.6.20` labeled `(current public)` passes. |
| `test_trust_readme_old_release_current_public_fails` | A trust README with `v0.6.17` labeled `(current public)` fails (exit != 0) and mentions the stale tag. |
| `test_trust_readme_historical_label_passes` | A trust README with `v0.6.19` labeled `(historical)` passes. |
| `test_trust_readme_next_planned_not_current_public_passes` | A trust README with `v0.6.21` labeled `(next planned)` passes. |
| `test_trust_readme_next_planned_current_public_fails` | A trust README with `v0.6.21` labeled `(current public)` fails. |
| `test_roadmap_no_candidates_contradiction_fails` | A roadmap saying "No candidates are currently proposed for v0.6.21" fails when `v0.6.21-candidates.json` contains an accepted candidate. |
| `test_roadmap_no_candidates_when_none_accepted_passes` | A roadmap saying "No candidates are currently proposed for v0.6.21" passes when the candidate-chain JSON has no accepted/released candidates. |
| `test_roadmap_historical_no_candidates_paragraph_passes` | A roadmap historical paragraph mentioning an old "no candidates proposed" state passes if not labeled as current. |
| `test_public_docs_still_pass_on_current_baseline` | Running the full `check_public_docs_consistency.py` on the real repo passes. |
| `test_no_forbidden_claims_introduced` | The design doc and any implementation doc pass `check_forbidden_claims.py`. |

### 14.3 Test style

Follow the existing `tests/test_public_docs_consistency.py` style:

- Use `_run_script_on_text(...)` for single-doc checks where possible.
- For checks that need both trust README and candidate-chain JSON, build a `tmp_path` fixture repository and run the script via subprocess with `repo_root` argument.
- Assert exit code and diagnostic substring.
- Avoid brittle full-output assertions.

### 14.4 Fixture example

```python
def _make_repo_with_trust_readme(tmp_path: Path, readme_text: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.6.20"\n')
    src = repo / "src" / "atlas_agent"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('__version__ = "0.6.20"\n')
    meta_dir = repo / "docs" / "releases"
    meta_dir.mkdir(parents=True)
    (meta_dir / "release-metadata.json").write_text(
        (REPO_ROOT / "docs" / "releases" / "release-metadata.json").read_text()
    )
    trust_dir = repo / "docs" / "trust"
    trust_dir.mkdir(parents=True)
    (trust_dir / "README.md").write_text(readme_text)
    # Trust status file required by check_trust_center is not needed for public-docs tests
    return repo
```

## 15. Dev/CI integration plan

### 15.1 Option A integration

If Option A is chosen, no changes to `scripts/dev_check.sh` or `scripts/ci_check.sh` are required because `scripts/check_public_docs_consistency.py` is already invoked in both gates.

### 15.2 Checks-reference update

Update `docs/development/checks-reference.md` in the "Core Checks" section to mention the new coverage:

```markdown
- `scripts/check_public_docs_consistency.py` scans public docs for unsafe claims,
  stale version references, stale RC status claims, missing safety wording,
  forbidden commands in bash blocks, secret-like patterns, release-note reference
  consistency, stale trust README `(current public)` labels, and autonomy-roadmap
  candidate-state contradictions against candidate-chain JSON.
```

## 16. Verification matrix

| Verification step | Command | Expected result |
|---|---|---|
| Baseline git clean | `git status --short` | empty |
| Baseline HEAD | `git rev-parse HEAD` | `4d908aa8007cf60c3c7d1b410fb59afaa5cf765b` |
| Baseline version | `python3.11 -c 'import atlas_agent; print(atlas_agent.__version__)'` | `0.6.20` |
| Version consistency | `python3.11 scripts/check_version_consistency.py` | PASSED |
| Release metadata | `python3.11 scripts/check_release_metadata.py` | PASSED |
| Public docs consistency | `python3.11 scripts/check_public_docs_consistency.py` | PASSED |
| Candidate chain | `python3.11 scripts/check_candidate_chain.py` | PASSED (with expected historical warnings) |
| Candidate chain tests | `python3.11 -m pytest tests/test_candidate_chain.py -q` | 23 passed |
| Forbidden claims | `python3.11 scripts/check_forbidden_claims.py` | clean |
| Trust center | `python3.11 scripts/check_trust_center.py` | PASSED |
| Onboarding docs | `python3.11 scripts/check_onboarding_docs.py` | PASSED |
| Public launch readiness | `python3.11 scripts/check_public_launch_readiness.py` | PASSED |
| Kill-switch mypy | `mypy src/atlas_agent/safety/kill_switch.py` | zero issues |
| Live mode fail-closed | `atlas run --mode live` | exits `2` |
| Dev check | `bash scripts/dev_check.sh` | PASSED |
| CI check | `bash scripts/ci_check.sh` | PASSED |
| Quick release check | `bash scripts/release_check.sh --quick` | PASSED |
| Design doc diff | `git diff --check` | clean |

After implementation, the following additional verifications will apply:

| Verification step | Command | Expected result |
|---|---|---|
| New public-docs tests pass | `python3.11 -m pytest tests/test_public_docs_consistency.py -q` | PASSED |
| Public docs consistency still passes on real repo | `python3.11 scripts/check_public_docs_consistency.py` | PASSED |

## 17. Safety and release invariants

CAND-013 preserves every safety and release boundary required by the project:

- **No live trading enabled:** The checker is read-only; it does not change defaults or configuration.
- **No live submit enabled:** No execution path is touched.
- **No order placement, cancellation, or flattening:** The checker does not interact with orders.
- **No pending-order creation:** The checker does not create files outside temporary test fixtures.
- **No approval queue mutation:** No runtime state is mutated.
- **No broker calls:** No broker modules are imported or executed.
- **No provider calls:** No provider modules are imported or executed.
- **No credential loading:** The checker does not read environment variables, `.env` files, or secrets.
- **No network access:** Standard-library file I/O only.
- **RiskManager is not weakened:** Risk code is untouched.
- **No kill-switch, deadman, or heartbeat weakening:** Safety modules are untouched.
- **No audit hash-chain bypass:** Audit code is untouched.
- **`atlas run --mode live` exits `2`:** No runtime change affects this.
- **Package version remains `0.6.20`:** The checker does not bump version.
- **Current public release remains `v0.6.20`:** The checker validates but does not alter release claims.
- **Next planned release remains `v0.6.21`:** The checker enforces this metadata value.
- **PyPI remains unpublished:** The checker does not claim PyPI publication.
- **No `v0.6.21` tag or GitHub Release:** The checker does not create tags or releases.

## 18. Risks and false-positive mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| False positive on trust README historical labels | Could force unnecessary doc rewording. | Only fail on explicit `(current public)` or equivalent positive current-public labels attached to old releases; allow `(historical)` or no label. |
| False positive on roadmap historical paragraphs | Could block legitimate historical explanation. | Require both a stale "no candidates" phrase and a candidate-chain JSON with accepted/released candidates; exempt paragraphs with historical tense markers. |
| Parenthetical label variants | Different authors may write `(current public release)` or `(current public — ...)` | Use case-insensitive regex that matches the core `(current public)` phrase anywhere in the label. |
| Future schema changes in release metadata | Could break expected label derivation. | Use existing `release_metadata.ReleaseMetadata` helper; fail gracefully if fields are missing. |
| Checker becomes slow as docs grow | Could exceed the fast gate target. | Only scan the targeted files; avoid full-repo scans. |
| Overlap with `check_trust_center.py` | Two checkers could flag the same stale label. | Keep the new check narrow and specific; accept that some overlap is better than a gap. |

## 19. Rollback plan

Because CAND-013 is docs/checker/test-only, rollback is straightforward:

1. Revert or delete the new functions/tests in `scripts/check_public_docs_consistency.py` and `tests/test_public_docs_consistency.py` (or the new script/tests if Option B/C is chosen).
2. Revert any checks-reference update.
3. Run the baseline verification matrix to confirm no safety boundary or release state changed.
4. No runtime state, tags, releases, or packages are affected.

## 20. Acceptance criteria

CAND-013 is accepted when:

1. This design document is reviewed and approved.
2. The chosen implementation option is implemented according to this design.
3. Tests cover all required test cases and pass.
4. The relevant checker runs successfully on the current repository with exit code `0`.
5. `docs/development/checks-reference.md` documents the new coverage.
6. All baseline verification commands in Section 16 continue to pass.
7. `atlas run --mode live` continues to exit `2`.
8. No runtime, safety, broker, provider, risk, approval, kill-switch, deadman, heartbeat, or audit hash-chain code is modified.
9. No version bump, tag, GitHub Release, or PyPI publication occurs as part of this candidate.

## 21. Open questions

1. Should the trust README label check also enforce that the current public release row is explicitly labeled `(current public)` (i.e., make the label mandatory), or only forbid old releases from carrying it?
   *Recommendation:* For the first implementation, only forbid old releases from carrying `(current public)`. Making the label mandatory could be added later if project convention requires it.
2. Should the roadmap check apply only to `metadata.next_planned_release`, or to all release lines with candidate-chain JSONs?
   *Recommendation:* Apply to `metadata.next_planned_release` first; historical release lines already have fixed candidate-state prose and should not be edited retroactively.
3. Should CAND-013 also detect stale "current public" claims in `docs/public-launch-readiness.md` and `docs/public-repo-hygiene.md` that are not already caught by existing sentence-based checks?
   *Recommendation:* Yes, as a secondary coverage extension, but only if the new check does not duplicate the existing `_check_stale_release_status_lines` logic.

## 22. Implementation-readiness verdict

**Verdict:** `READY_FOR_IMPLEMENTATION_PLAN`

Rationale:

- The problem is narrowly scoped to two missed drift classes from the `v0.6.20` readiness review.
- The detection rules are deterministic and metadata-driven.
- The preferred implementation path (Option A) reuses an existing checker and requires no dev/CI wiring changes.
- False-positive risks are mitigated by explicit exemptions for historical paragraphs and historical labels.
- No runtime, safety, broker, provider, or execution code is involved.
- The next step should be a separate implementation-plan prompt that breaks the design into small, reviewable implementation tasks.
