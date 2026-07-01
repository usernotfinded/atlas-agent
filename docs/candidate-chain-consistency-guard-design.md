# CAND-012: Candidate-Chain Consistency Guard — Design

> **Candidate ID:** CAND-012  
> **Proposed title:** Candidate-Chain Consistency Guard  
> **Proposed subtitle:** Deterministic validation that release-metadata, candidate-chain Markdown, and candidate-chain JSON remain aligned, coherent, and free of premature release or live-trading claims.  
> **Design status:** design-only  
> **Target implementation phase:** after independent design review  
> **Repository:** `usernotfinded/atlas-agent`  
> **Branch:** `main`  
> **Baseline HEAD:** `01a4958fdbec516cd797516917391cd1236ab5ea`  
> **Baseline public release:** `v0.6.19`  
> **Baseline package version:** `0.6.19`  
> **Baseline next planned release:** `v0.6.20`  

## 1. Title and candidate ID

- **Candidate ID:** `CAND-012`
- **Title:** Candidate-Chain Consistency Guard
- **Subtitle:** Deterministic validation that release-metadata, candidate-chain Markdown, and candidate-chain JSON remain aligned, coherent, and free of premature release or live-trading claims.
- **Safety classification:** docs/checker/test-only; no runtime changes.

## 2. Baseline state

At the time of this design, the repository is in the following state:

- `git status --short`: clean.
- `git rev-parse HEAD`: `01a4958fdbec516cd797516917391cd1236ab5ea`.
- `git tag --points-at HEAD`: `v0.6.19`.
- `git rev-parse v0.6.19^{}`: `01a4958fdbec516cd797516917391cd1236ab5ea`.
- `gh release view v0.6.19`: exists, GitHub-only.
- `git tag --list 'v0.6.20*'`: empty.
- `git ls-remote --tags origin 'v0.6.20*'`: empty.
- `gh release view v0.6.20`: not found.
- `atlas_agent.__version__`: `0.6.19`.
- `pyproject.toml` version: `0.6.19`.
- `docs/releases/release-metadata.json`: `source_version` `0.6.19`, `current_public_release` `v0.6.19`, `next_planned_release` `v0.6.20`, `pypi_published` `false`, `release_type` `github_only`.
- `atlas run --mode live`: exits `2` / fail-closed.
- `mypy src/atlas_agent/safety/kill_switch.py`: zero issues.
- All baseline verification commands (`check_version_consistency.py`, `check_release_metadata.py`, `check_forbidden_claims.py`, `check_bounded_autonomy_governance.py`, `check_cli_command_compatibility.py`, `check_safety_atomic_write.py`, `check_trust_center.py`, `check_onboarding_docs.py`, `check_public_launch_readiness.py`) pass.

## 3. Problem statement

The `v0.6.19` release introduced machine-readable candidate-chain files (`docs/releases/v0.6.19-candidates.json`) alongside the existing Markdown candidate-chain files (`docs/releases/v0.6.19-candidates.md`, `docs/releases/v0.6.19-candidate-selection.md`, `docs/releases/v0.6.19-plan.md`). The release metadata in `docs/releases/release-metadata.json` is the authoritative source for:

- current public release,
- next planned release,
- source/package version,
- PyPI publication status,
- release type,
- historical releases.

These three sources (release metadata, candidate-chain Markdown, candidate-chain JSON) can drift. Drift is dangerous because:

- A future `v0.6.20` candidate-chain doc could accidentally claim `released` status before the release cutover.
- A doc could claim `pypi_published: true` while release metadata says `pypi_published: false`.
- A candidate-chain file could reference a stale `current_public_release` or `next_planned_release`.
- A candidate doc could make forbidden live-trading, profit, or order-submission claims that escape the existing forbidden-claims scan because the scan targets do not include `docs/releases/*-candidates.md` by default.

A deterministic, local, read-only checker is needed to catch these inconsistencies before they are accepted into the candidate chain or released.

## 4. Current gap

The existing checkers cover related but distinct concerns:

- `scripts/check_release_metadata.py` validates the shape and referential integrity of `docs/releases/release-metadata.json`.
- `scripts/check_version_consistency.py` validates that `pyproject.toml`, `src/atlas_agent/__init__.py`, README, CHANGELOG, release notes, and release checklist agree on the current public release.
- `scripts/check_forbidden_claims.py` scans `README.md`, `CHANGELOG.md`, `docs/`, and `.github/pull_request_template.md` for prohibited safety/profit wording, but does not explicitly include `docs/releases/*-candidates.md`.
- `scripts/check_bounded_autonomy_governance.py` checks for forbidden autonomous-live-trading claims and version/tag consistency.
- `scripts/check_trust_center.py` validates trust-center docs against release metadata.

None of these checkers validate that:

1. The Markdown and JSON candidate-chain files for a release line agree with each other.
2. The candidate-chain files agree with `release-metadata.json` on current public release, next planned release, PyPI status, and release-created flags.
3. Candidate IDs are unique within a release line.
4. Candidate statuses and acceptance verdicts use allowed values.
5. Released candidates only appear in current or historical releases.
6. Next-planned-release docs do not claim released/tag-created/GitHub-release-created status.
7. Candidate-chain docs do not contain forbidden live-trading, profit, order-submission, or PyPI-publication claims.

This gap is the target of CAND-012.

## 5. Proposed checker

### 5.1 Identity

- **Script:** `scripts/check_candidate_chain.py`
- **Tests:** `tests/test_candidate_chain.py`
- **Type:** static, deterministic, local, read-only, no network, no credentials.

### 5.2 Invocation

```bash
python3.11 scripts/check_candidate_chain.py              # default repo root
python3.11 scripts/check_candidate_chain.py /path/to/repo # positional repo root
python3.11 scripts/check_candidate_chain.py --repo-root /path/to/repo
python3.11 scripts/check_candidate_chain.py --json
```

### 5.3 Exit codes

| Exit code | Meaning |
|---|---|
| `0` | Candidate-chain consistency check passed. |
| `1` | Operational error (bad arguments, missing metadata file, unreadable file, malformed JSON). |
| `2` | Validation failure (alignment mismatch, forbidden claim, duplicate ID, unknown status/verdict, premature release claim). |

The exit-code convention matches the existing `scripts/check_safety_atomic_write.py` and `scripts/check_forbidden_claims.py` checkers.

### 5.4 Output style

Default text output prints one finding per line, prefixed with the file path and line number when available, followed by a summary line:

```text
docs/releases/v0.6.20-candidates.json:7: pypi_published mismatch: metadata says false, candidate doc says true
docs/releases/v0.6.20-candidates.md:3: status mismatch with JSON: md says 'released', json says 'planning'
Candidate-chain consistency check FAILED
  Checks: 42
  Blocking findings: 2
```

JSON output (`--json`) emits a deterministic, sorted JSON object with the same shape as `scripts/check_trust_center.py`:

```json
{
  "checks": [
    {"id": "metadata:source_version", "status": "pass", "detail": "..."}
  ],
  "errors": [],
  "exit_code": 2,
  "findings": [
    "docs/releases/v0.6.20-candidates.json:7: pypi_published mismatch: ..."
  ],
  "repo_root": "/path/to/repo",
  "status": "failed"
}
```

### 5.5 Dependencies

- Python 3.11 standard library only (`json`, `pathlib`, `re`, `sys`, `argparse`, `dataclasses`).
- Existing helper `scripts/release_metadata.py` for `load_metadata` and `ReleaseMetadata`.
- No imports from `atlas_agent` runtime code.
- No third-party packages.
- No network calls.
- No credential loading.

### 5.6 High-level algorithm

1. Resolve repository root.
2. Load `docs/releases/release-metadata.json` via `release_metadata.load_metadata`.
3. Build the authoritative release map from metadata:
   - `source_version`
   - `current_public_release`
   - `next_planned_release`
   - `pypi_published`
   - `release_type`
   - set of historical release tags
   - set of release tags with `github_release: true`
4. Discover candidate-chain files under `docs/releases/`:
   - `vX.Y.Z-candidates.md`
   - `vX.Y.Z-candidates.json`
   - `vX.Y.Z-candidate-selection.md`
   - `vX.Y.Z-plan.md`
5. Group files by release line `vX.Y.Z`.
6. For each release line with at least one candidate-chain file, run the rules in Section 6.
7. Scan all candidate-chain Markdown files for forbidden claims using the same phrase list as `scripts/check_forbidden_claims.py` plus candidate-chain-specific phrases (Section 7).
8. Emit findings and exit with the appropriate code.

## 6. Metadata and candidate-chain rules

### 6.1 Release-line identification

- The release line `vX.Y.Z` is derived from the filename (`docs/releases/vX.Y.Z-candidates.md` → `vX.Y.Z`).
- The Markdown file and JSON file for the same release line must both exist for full cross-validation. If only one exists, the checker validates the existing file against metadata but skips Markdown/JSON agreement checks.
- `vX.Y.Z-candidate-selection.md` and `vX.Y.Z-plan.md` are optional per release line. If they exist, they are validated; if absent, no failure is raised.

### 6.2 Metadata alignment rules

For every release line with candidate-chain files:

| Check | Failure detail |
|---|---|
| `release_line` field in JSON matches filename release line. | `release_line mismatch: filename vX.Y.Z, json says vA.B.C` |
| `source_version` in JSON (if present) matches metadata `source_version`. | `source_version mismatch: metadata says M, json says N` |
| `current_public_release` in JSON (if present) matches metadata `current_public_release`. | `current_public_release mismatch: metadata says M, json says N` |
| `next_planned_release` in JSON (if present) matches metadata `next_planned_release`. | `next_planned_release mismatch: metadata says M, json says N` |
| `pypi_published` in JSON (if present) matches metadata `pypi_published`. | `pypi_published mismatch: metadata says false, json says true` |
| Markdown first paragraph mentions the same current public release as metadata. | `md current_public_release mismatch: metadata says M, md says N` |
| Markdown first paragraph mentions the same next planned release as metadata. | `md next_planned_release mismatch: metadata says M, md says N` |

The Markdown release references are detected with lightweight regular expressions (e.g., `` `vX.Y.Z` is the current public GitHub release `` or `` current public release: `vX.Y.Z` ``). The checker does not enforce exact wording; it only checks that the version strings match metadata.

### 6.3 Markdown/JSON agreement rules

When both `vX.Y.Z-candidates.md` and `vX.Y.Z-candidates.json` exist:

| Check | Failure detail |
|---|---|
| Both agree on `release_line`. | `md/json release_line mismatch` |
| Both agree on `status` if the JSON `status` field exists and the Markdown contains a clear status statement. | `md/json status mismatch: md 'released', json 'planning'` |
| Both agree on `current_public_release`. | `md/json current_public_release mismatch` |
| Both agree on `next_planned_release`. | `md/json next_planned_release mismatch` |
| Both agree on `pypi_published`. | `md/json pypi_published mismatch` |

JSON is authoritative for machine-readable fields. Markdown is allowed to use prose equivalents (e.g., "PyPI was not published" equals `pypi_published: false`). The checker uses normalized lowercase substring matching for Markdown booleans.

### 6.4 Candidate identity and status rules

When parsing `vX.Y.Z-candidates.json`:

| Check | Failure detail |
|---|---|
| Candidate IDs within a release line are unique. | `duplicate candidate id CAND-NNN in vX.Y.Z-candidates.json` |
| Each candidate `status` is in the allowed set: `proposed`, `accepted`, `released`, `deferred`, `rejected`. | `unknown candidate status 'X' for CAND-NNN` |
| Each `acceptance_verdict` (if present) is in the allowed set: `PASS`, `FAIL`, `PENDING`, `WITHDRAWN`. | `unknown acceptance verdict 'X' for CAND-NNN` |
| A candidate with `status: released` has `accepted: true` and `acceptance_verdict: PASS`. | `released candidate CAND-NNN must be accepted with PASS verdict` |
| A candidate with `accepted: true` has a non-empty `title`. | `accepted candidate CAND-NNN missing title` |

Allowed status values are intentionally conservative. If a future candidate needs a new status, the checker must be updated explicitly; this prevents typos from slipping through.

### 6.5 Release-status lifecycle rules

| Check | Failure detail |
|---|---|
| If release line is `metadata.next_planned_release`, JSON `status` must not be `released`. | `next planned release vX.Y.Z claims status 'released' before cutover` |
| If release line is `metadata.next_planned_release`, Markdown must not claim the release is the current public release. | `next planned release vX.Y.Z claims current public release status` |
| If release line is `metadata.next_planned_release`, `tag_created` must not be `true`. | `next planned release vX.Y.Z claims tag_created=true` |
| If release line is `metadata.next_planned_release`, `github_release_created` must not be `true`. | `next planned release vX.Y.Z claims github_release_created=true` |
| If release line is `metadata.current_public_release` or a historical release, `status` may be `released`. | — |
| If release line is not in metadata releases and not `next_planned_release`, the checker warns but does not fail (permissive for planning seeds). | `note: vX.Y.Z candidate-chain files not referenced in release-metadata.json` |
| `pypi_published` must not be `true` anywhere if metadata `pypi_published` is `false`. | `candidate doc claims pypi_published=true while metadata says false` |
| `github_release_created` must not be `true` for a release line not marked `github_release: true` in metadata. | `candidate doc claims github_release_created=true without metadata release record` |

### 6.6 Stale-reference rules

| Check | Failure detail |
|---|---|
| Candidate-chain docs for `metadata.current_public_release` must not reference a different release as the current public release. | `vX.Y.Z-candidates.md references stale current_public_release` |
| Candidate-chain docs for `metadata.next_planned_release` must not reference a different release as the next planned release. | `vX.Y.Z-candidates.md references stale next_planned_release` |
| Historical candidate-chain docs should reference the correct predecessor/successor releases for their line. This is checked as a warning, not a failure, to avoid breaking historical records. | `warning: vX.Y.Z-candidates.md may reference stale next_planned_release` |

### 6.7 Markdown candidate-section rules

For `vX.Y.Z-candidates.md`:

| Check | Failure detail |
|---|---|
| If `status` is `released`, the doc must contain an "Included" or "Implemented" section listing the released candidates. | `released candidate doc vX.Y.Z-candidates.md missing implemented section` |
| If `status` is `planning`, the doc must contain a "Proposed" section. | `planning candidate doc vX.Y.Z-candidates.md missing proposed section` |
| Candidate IDs mentioned in Markdown must be a subset of candidate IDs in JSON (if JSON exists). | `md references candidate CAND-NNN not present in json` |

These checks are advisory warnings by default for historical docs that predate the current schema. They become blocking for the current public release and next planned release.

## 7. Forbidden-claim rules

### 7.1 Reuse policy

The checker must not duplicate the existing forbidden-claims scan logic. It should either:

1. **Preferred:** import and call `scripts/check_forbidden_claims.py` as a module, reusing `_FORBIDDEN_PHRASES` and `_collect_paths` restricted to candidate-chain Markdown files, or
2. **Acceptable:** import the phrase list via a shared constant if one is extracted during implementation.

The design prefers option 1 to avoid drift between the two scanners.

### 7.2 Candidate-chain-specific forbidden phrases

In addition to the shared list, the checker scans candidate-chain Markdown files for:

| Phrase category | Example phrases |
|---|---|
| Live-trading readiness | `"live trading ready"`, `"live-ready"`, `"safe to run live"`, `"ready for live trading"` |
| Autonomous live trading | Phrase combining `"autonomous"`, `"live trading"`, and `"is implemented"`, or `"unattended"` + `"live trading"`, or `"direct AI-to-broker execution"` |
| Profitability | `"guaranteed" + "profit"`, `"expected profit"`, `"profitable strategy"` (when not in disclaimer context) |
| Broker endorsement | `"broker endorsed"`, `"recommended broker"` |
| Order submission permission | `"submit orders without approval"`, `"live submit enabled"`, `"can_submit=true"` |
| PyPI publication | `"pypi published"`, `"published to pypi"` when metadata says unpublished |

Negative/disclaimer contexts are allowed, matching the logic in `scripts/check_bounded_autonomy_governance.py` (`_NEGATIVE_INDICATORS`). For example, "PyPI was not published" is allowed; "PyPI published" is not.

### 7.3 Scope of scan

- Scan targets: `docs/releases/vX.Y.Z-candidates.md`, `docs/releases/vX.Y.Z-candidate-selection.md`, `docs/releases/vX.Y.Z-plan.md`.
- Do not scan `docs/releases/release-metadata.json` (JSON is authoritative and already validated by `check_release_metadata.py`).
- Do not scan `docs/releases/vX.Y.Z.md` release notes (covered by `check_forbidden_claims.py` through the `docs` directory scan).

## 8. Permissiveness / false-positive policy

The checker is intentionally strict about contradictions but permissive about missing or historical material:

### 8.1 Allowed without failure

- A `proposed` or `accepted` candidate in the next planned release.
- A planning-only candidate-chain file with no candidates yet.
- A historical release candidate-chain file that uses an older schema (e.g., `v0.6.13-candidates.json`, `v0.6.1-candidates.json`).
- Missing `vX.Y.Z-candidate-selection.md` or `vX.Y.Z-plan.md` for any release line.
- Markdown wording differences when JSON is authoritative.
- Extra keys in JSON that the checker does not understand.
- Release lines not yet present in `release-metadata.json` (warning only).
- Historical docs with stale successor references (warning only).

### 8.2 Rejected (blocking)

- Any contradiction between JSON and metadata.
- Any contradiction between Markdown and JSON for the same release line.
- `released` status for the next planned release before cutover.
- `pypi_published: true` anywhere while metadata says `false`.
- `tag_created: true` or `github_release_created: true` for the next planned release.
- Duplicate candidate IDs within a release line.
- Unknown candidate status or acceptance verdict.
- Forbidden live-trading, profit, broker-endorsement, order-submission, or PyPI-publication claims in candidate-chain Markdown.

### 8.3 Unknown-schema handling

- If a `vX.Y.Z-candidates.json` file does not contain a `release_line` field or uses an `artifact_type` field (e.g., `v0.6.1-candidates.json`, `v0.6.13-candidates.json`), the checker performs only lightweight checks:
  - Filename-derived release line is sane.
  - No forbidden claims in the Markdown counterpart.
  - No `pypi_published: true` if the field exists and metadata says unpublished.
  - No `released` claim if the release line is the next planned release.
- Full structural validation is applied only to files following the current schema (`release_line`, `status`, `candidates` array with `id`/`status`/`accepted`/`acceptance_verdict`).

## 9. Expected files

### 9.1 Files to create during implementation

| File | Responsibility |
|---|---|
| `scripts/check_candidate_chain.py` | The deterministic candidate-chain consistency checker. |
| `tests/test_candidate_chain.py` | Pytest coverage using temporary fixture repositories. |

### 9.2 Files to modify during integration

| File | Change |
|---|---|
| `scripts/dev_check.sh` | Add a step that runs `scripts/check_candidate_chain.py` after `check_release_metadata.py` and `check_version_consistency.py`. |
| `scripts/ci_check.sh` | Same as `dev_check.sh`. |
| `docs/development/checks-reference.md` | Document the new checker, its invocation, exit codes, and where it runs in the check tiers. |

### 9.3 Files that must not change

No runtime code, safety module, broker adapter, provider adapter, risk configuration, approval logic, kill-switch logic, deadman logic, heartbeat logic, or audit hash-chain code is touched by this candidate.

## 10. Test plan

### 10.1 Test file

`tests/test_candidate_chain.py`

### 10.2 Test style

- Use `tmp_path` fixtures to build isolated temporary repositories.
- Copy a minimal valid `release-metadata.json` and `pyproject.toml` into each fixture.
- Write candidate-chain files into the temporary repo.
- Run the checker via `subprocess.run([sys.executable, str(CHECKER_SCRIPT), str(tmp_repo)])`.
- Assert exit codes and substring presence in stdout/stderr.
- Never mutate real repository files.

### 10.3 Required test cases

| Test | Expected result |
|---|---|
| `test_checker_passes_on_current_repo` | Exit `0`, summary contains `PASSED`. |
| `test_valid_planning_chain_passes` | A `v0.6.20-candidates.json` with status `planning` and one `proposed` candidate passes. |
| `test_valid_released_chain_passes` | A `v0.6.19-candidates.json` with status `released` and one `released` candidate passes. |
| `test_mismatched_md_json_release_line_fails` | Markdown says `v0.6.20`, JSON says `v0.6.21` → exit `2`, finding mentions release-line mismatch. |
| `test_duplicate_candidate_id_fails` | Two candidates with the same ID in one JSON → exit `2`, finding mentions duplicate ID. |
| `test_unknown_candidate_status_fails` | Candidate status `accepted_released` → exit `2`, finding mentions unknown status. |
| `test_unknown_acceptance_verdict_fails` | Verdict `MAYBE` → exit `2`, finding mentions unknown verdict. |
| `test_next_planned_release_claiming_released_fails` | `v0.6.20-candidates.json` with status `released` while metadata says `v0.6.20` is next planned → exit `2`. |
| `test_pypi_mismatch_fails` | JSON `pypi_published: true` while metadata says `false` → exit `2`. |
| `test_github_release_created_mismatch_fails` | Next planned release JSON claims `github_release_created: true` → exit `2`. |
| `test_forbidden_live_trading_claim_fails` | Markdown contains `"live trading ready"` → exit `2`. |
| `test_forbidden_profit_claim_fails` | Markdown contains the phrase composed of `"guaranteed"` and `"profit"` → exit `2`. |
| `test_forbidden_order_submission_claim_fails` | Markdown contains `"submit orders without approval"` → exit `2`. |
| `test_historical_released_candidate_passes` | `v0.6.18-candidates.json` with status `released` passes. |
| `test_accepted_candidate_in_next_release_passes` | `v0.6.20-candidates.json` with one `accepted` candidate passes. |
| `test_missing_optional_selection_doc_passes` | No `v0.6.20-candidate-selection.md` or `v0.6.20-plan.md` → pass. |
| `test_unknown_schema_gracefully_warns` | A `v0.6.1-candidates.json` with `artifact_type` field passes with warnings, not failures. |
| `test_exit_1_for_missing_metadata` | Checker run in a repo without `docs/releases/release-metadata.json` → exit `1`. |
| `test_no_network_calls_in_checker` | Source inspection: no `requests`, `urllib`, `httpx`, `socket` imports. |
| `test_no_credential_loading_in_checker` | Source inspection: no `load_dotenv`, `os.environ`, `getenv` usage. |

### 10.4 Test runtime target

The full `tests/test_candidate_chain.py` file should complete in under 5 seconds on typical hardware.

## 11. Dev/CI integration plan

### 11.1 Placement

Add the new checker to `scripts/dev_check.sh` and `scripts/ci_check.sh` immediately after the existing release metadata and version consistency checks and before the trust-center and onboarding checks:

```bash
echo "1b. candidate-chain consistency"
SECONDS=0
"$PYTHON_BIN" scripts/check_candidate_chain.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"
```

Rationale:

- Candidate-chain consistency is a release-governance gate, not a runtime gate.
- It depends on release metadata and version consistency already being valid.
- It should run early so that release-governance errors surface before slower test suites.
- It is fast (< 1 s) and has no network or credential dependencies.

### 11.2 Tier assignment

| Tier | Includes CAND-012 checker? |
|---|---|
| `scripts/smoke_check.sh` | Optional; maintainer discretion. |
| `scripts/local_quick_check.sh` | Yes. |
| `scripts/dev_check.sh` | Yes. |
| `scripts/ci_check.sh` | Yes. |
| `scripts/release_check.sh --quick` | Yes (via `dev_check.sh`). |
| `scripts/release_check.sh --full` | Yes (via `ci_check.sh`). |

### 11.3 Documentation update

Add a section to `docs/development/checks-reference.md` under "Core Checks":

```markdown
- `scripts/check_candidate_chain.py` validates that release-metadata,
  candidate-chain Markdown, and candidate-chain JSON agree on release identity,
  candidate status, acceptance verdicts, PyPI status, and release-created flags.
  It also scans candidate-chain docs for forbidden live-trading, profit,
  broker-endorsement, order-submission, and PyPI-publication claims.
```

## 12. Safety and release invariants

CAND-012 preserves every safety and release boundary required by the project:

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
- **Package version remains `0.6.19`:** The checker does not bump version.
- **Current public release remains `v0.6.19`:** The checker validates but does not alter release claims.
- **Next planned release remains `v0.6.20`:** The checker enforces this metadata value.
- **PyPI remains unpublished:** The checker rejects any claim that PyPI is published while metadata says otherwise.
- **No `v0.6.20` tag or GitHub Release:** The checker rejects premature tag/release-created claims for the next planned release.

## 13. Non-goals

CAND-012 explicitly does **not**:

1. Create the `v0.6.20` candidate-chain files (`v0.6.20-candidates.md`, `v0.6.20-candidates.json`, etc.). Those are created only when a `v0.6.20` candidate is formally proposed.
2. Implement the checker. This document is design-only.
3. Modify `scripts/dev_check.sh`, `scripts/ci_check.sh`, or `docs/development/checks-reference.md`. Integration happens after implementation.
4. Bump the package version or start the `v0.6.20` release cutover.
5. Create a `v0.6.20` tag or GitHub Release.
6. Publish to PyPI.
7. Validate runtime correctness, test coverage percentages, or code style beyond the candidate-chain scope.
8. Replace `scripts/check_release_metadata.py`, `scripts/check_version_consistency.py`, `scripts/check_forbidden_claims.py`, or `scripts/check_bounded_autonomy_governance.py`. It complements them.
9. Enforce a single universal candidate-chain schema across all historical releases. Historical schemas are handled permissively.
10. Add new live-trading, broker, provider, credential, network, or execution capabilities.

## 14. Verification matrix

| Verification step | Command | Expected result |
|---|---|---|
| Baseline git clean | `git status --short` | empty |
| Baseline HEAD | `git rev-parse HEAD` | `01a4958fdbec516cd797516917391cd1236ab5ea` |
| Baseline version | `python3.11 -c 'import atlas_agent; print(atlas_agent.__version__)'` | `0.6.19` |
| Version consistency | `python3.11 scripts/check_version_consistency.py` | PASSED |
| Release metadata | `python3.11 scripts/check_release_metadata.py` | PASSED |
| Forbidden claims | `python3.11 scripts/check_forbidden_claims.py` | clean |
| Bounded autonomy | `python3.11 scripts/check_bounded_autonomy_governance.py` | PASSED |
| Trust center | `python3.11 scripts/check_trust_center.py` | PASSED |
| Onboarding docs | `python3.11 scripts/check_onboarding_docs.py` | PASSED |
| Public launch readiness | `python3.11 scripts/check_public_launch_readiness.py` | PASSED |
| Kill-switch mypy | `mypy src/atlas_agent/safety/kill_switch.py` | zero issues |
| Live mode fail-closed | `atlas run --mode live` | exits `2` |
| Design doc diff | `git diff --check` | clean |

After implementation, the following additional verifications will apply:

| Verification step | Command | Expected result |
|---|---|---|
| Checker passes on repo | `python3.11 scripts/check_candidate_chain.py` | PASSED |
| Checker tests pass | `python3.11 -m pytest tests/test_candidate_chain.py -q` | PASSED |
| Dev check includes checker | `grep -n check_candidate_chain scripts/dev_check.sh` | present |
| CI check includes checker | `grep -n check_candidate_chain scripts/ci_check.sh` | present |

## 15. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| False positives on historical candidate-chain schemas | Could break existing historical docs. | Handle pre-current schemas permissively; only validate fields that exist; use warnings, not failures, for historical inconsistencies. |
| Duplication of forbidden-claims logic | Two scanners could drift. | Reuse `scripts/check_forbidden_claims.py` as a module or extract a shared phrase list. |
| Overly strict Markdown parsing | Legitimate prose could be flagged. | Use normalized substring matching; allow negative/disclaimer contexts; make JSON authoritative for machine fields. |
| Checker becomes slow as candidate-chain files accumulate | Could exceed the < 1 s target. | Only scan files under `docs/releases/`; skip deep content parsing; cache file reads. |
| Coupling to release-metadata.json schema changes | Future metadata schema changes could break the checker. | Use `ReleaseMetadata` helper from `scripts/release_metadata.py`; validate schema version and fail gracefully. |
| Accidental runtime import | Could pull in `atlas_agent` and slow down or side-effect. | Code review + test `test_no_runtime_imports` asserts no `import atlas_agent` in the checker source. |

## 16. Rollback plan

Because CAND-012 is docs/checker/test-only, rollback is straightforward:

1. Revert or delete `scripts/check_candidate_chain.py` and `tests/test_candidate_chain.py`.
2. Revert the additions to `scripts/dev_check.sh`, `scripts/ci_check.sh`, and `docs/development/checks-reference.md`.
3. Run the baseline verification matrix to confirm no safety boundary or release state changed.
4. No runtime state, tags, releases, or packages are affected.

## 17. Acceptance criteria

CAND-012 is accepted when:

1. This design document is reviewed and approved.
2. `scripts/check_candidate_chain.py` is implemented according to this design.
3. `tests/test_candidate_chain.py` covers all required test cases and passes.
4. The checker runs successfully on the current repository with exit code `0`.
5. The checker is integrated into `scripts/dev_check.sh` and `scripts/ci_check.sh`.
6. `docs/development/checks-reference.md` documents the checker.
7. All baseline verification commands in Section 14 continue to pass.
8. `atlas run --mode live` continues to exit `2`.
9. No runtime, safety, broker, provider, risk, approval, kill-switch, deadman, heartbeat, or audit hash-chain code is modified.
10. No version bump, tag, GitHub Release, or PyPI publication occurs as part of this candidate.

## 18. Implementation-readiness recommendation

**Recommendation:** `READY_FOR_IMPLEMENTATION_PLAN`

Rationale:

- The checker scope is bounded and well-defined.
- Existing patterns (`scripts/check_release_metadata.py`, `scripts/check_safety_atomic_write.py`, `scripts/check_forbidden_claims.py`, `scripts/check_trust_center.py`) provide clear conventions to follow.
- The permissiveness/false-positive policy is explicit and conservative.
- No runtime changes are required.
- The next step should be an implementation-plan prompt that breaks the design into small, reviewable implementation tasks.
