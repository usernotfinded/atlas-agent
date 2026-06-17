# CAND-017 — v0.6.12 Release Candidate Consolidation and Cutover Readiness Audit Implementation Plan

> **Status:** historical implementation plan. CAND-017 has been completed. The
> resulting v0.6.12 candidate-readiness docs are now historical planning records;
> the canonical released-state evidence is
> [v0.6.12 Post-Release Evidence](../../releases/v0.6.12-post-release-evidence.md).
> For the v0.6.13 planning line, see
> [v0.6.13 Candidate Selection](../../releases/v0.6.13-candidate-selection.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate CAND-001 through CAND-016 into a v0.6.12 release-candidate readiness layer without creating a tag, release, or PyPI publish, and without bumping the version.

**Architecture:** Mirror the v0.6.11 candidate-completion-audit/cutover-readiness pattern. Add a v0.6.12 candidate readiness doc, a candidate index, a deterministic static checker, and tests. Link the new docs from existing trust/release docs and integrate the checker/tests into local and CI gates.

**Tech Stack:** Markdown, Python 3.11 stdlib, pytest, GitHub Actions YAML.

---

## File map

- Create `docs/releases/v0.6.12-candidate-readiness.md` — readiness audit doc.
- Create `docs/releases/v0.6.12-candidates.md` — candidate index (human-readable table).
- Create `docs/releases/v0.6.12-candidates.json` — machine-readable candidate index.
- Create `scripts/check_v0612_release_candidate_readiness.py` — deterministic static checker.
- Create `tests/test_v0612_release_candidate_readiness.py` — pytest coverage.
- Modify `docs/trust/README.md` — link to readiness doc and confirm v0.6.12 is next planning line.
- Modify `docs/trust/v0.6.11-status.md` — add note that v0.6.12 candidate readiness audit exists.
- Modify `docs/release-candidate-readiness.md` — link to v0.6.12 doc.
- Modify `docs/public-launch-readiness.md` — mention candidate readiness consolidation.
- Modify `docs/reviewer-checklist.md` — add readiness-check item.
- Modify `scripts/dev_check.sh` — run checker and tests.
- Modify `scripts/ci_check.sh` — run checker and tests.
- Modify `.github/workflows/ci.yml` — run checker and tests.
- Modify `scripts/release_check.sh` — run checker and tests if consistent.

---

## Task 1: Candidate inventory

**Files:**
- Read-only inspection of commits, design docs, and existing docs.

**Design:**
- Gather CAND-001 through CAND-016 titles, primary files, checkers/tests, workflow impact, and safety scope.
- CAND-001: Product Demo and Marketplace Readiness Pack — `docs/product-demo-pack.md`, `scripts/check_product_demo_pack.py`, `tests/test_product_demo_pack.py`.
- CAND-002: Product Demo Evidence Bundle — `docs/product-demo-evidence.md`, `scripts/build_product_demo_evidence.py`, `scripts/check_product_demo_evidence.py`, `tests/test_product_demo_evidence.py`.
- CAND-003: Reviewer Trust Snapshot — `docs/trust/reviewer-trust-snapshot.md`, `scripts/build_reviewer_trust_snapshot.py`, `scripts/check_reviewer_trust_snapshot.py`, `tests/test_reviewer_trust_snapshot.py`.
- CAND-004: Reviewer Trust Snapshot Workflow — `.github/workflows/reviewer-trust-snapshot.yml`, `scripts/check_reviewer_trust_snapshot_workflow.py`, `tests/test_reviewer_trust_snapshot_workflow.py`.
- CAND-005: Docs archive hygiene / legacy planning archive — `docs/archive/`, `scripts/check_docs_archive_hygiene.py`, `tests/test_docs_archive_hygiene.py`.
- CAND-006: Release Assurance Snapshot Integration — `scripts/check_release_assurance_snapshot_integration.py`, `scripts/build_release_assurance_bundle_manifest.py`, `.github/workflows/release-assurance.yml` snapshot input, `tests/test_release_assurance_snapshot_integration.py`.
- CAND-007: Release Assurance Bundle Demo and Manifest — `docs/security/release-assurance-bundle-demo.md`, `scripts/build_release_assurance_bundle_manifest.py`, `scripts/check_release_assurance_bundle_manifest.py`, `scripts/check_release_assurance_bundle_workflow.py`, `tests/test_release_assurance_bundle_manifest.py`, `tests/test_release_assurance_bundle_workflow.py`.
- CAND-008: Not separately tracked in commit history; note as gap/folded.
- CAND-009: Release Assurance Workflow Artifact Validation — `scripts/check_release_assurance_workflow_artifact.py`, `tests/test_release_assurance_workflow_artifact.py`.
- CAND-010: Not separately tracked; note as gap/folded.
- CAND-011: Release Assurance Failure Diagnostics — `scripts/release_assurance.py --diagnostics-json`, `scripts/check_release_assurance_diagnostics.py`, `tests/test_release_assurance_diagnostics.py`.
- CAND-012: Release Assurance Diagnostics Artifact — `.github/workflows/release-assurance.yml` diagnostics upload, `scripts/check_release_assurance_diagnostics_workflow.py`, `tests/test_release_assurance_diagnostics_workflow.py`.
- CAND-013: Release Assurance Diagnostics Artifact Validator — `scripts/check_release_assurance_diagnostics_artifact.py`, `tests/test_release_assurance_diagnostics_artifact.py`.
- CAND-014: Release Assurance Diagnostics Artifact Workflow Integration — `.github/workflows/release-assurance.yml` validate step, `scripts/check_release_assurance_diagnostics_artifact_workflow.py`, `tests/test_release_assurance_diagnostics_artifact_workflow.py`.
- CAND-015: Release Assurance Diagnostics Artifact Revalidation Workflow — `.github/workflows/release-assurance-diagnostics-artifact-validate.yml`.
- CAND-016: Release Assurance Artifact Retention Audit — `scripts/audit_release_assurance_artifact_retention.py`, `scripts/check_release_assurance_artifact_retention_audit.py`, `.github/workflows/release-assurance-artifact-retention-audit.yml`, `tests/test_release_assurance_artifact_retention_audit.py`.

**Steps:**
- [ ] Step 1.1: Collect commit SHAs and messages for each CAND.
- [ ] Step 1.2: Collect primary files, checkers, tests, and workflows.
- [ ] Step 1.3: Summarize safety scope per CAND.

---

## Task 2: Readiness doc

**Files:**
- Create: `docs/releases/v0.6.12-candidate-readiness.md`

**Design:**
- Header: not financial advice, audit date, repo, branch, baseline commit, last candidate commit, last candidate CI run.
- Status section: `v0.6.12 is not released yet`; current public release remains `v0.6.11`; next planned release is `v0.6.12`.
- Release state table: current public release, source/package version, next planned, candidate inventory status, selected/implemented CAND-001 through CAND-016, presence of `docs/releases/v0.6.12.md`, `docs/trust/v0.6.12-status.md`, CHANGELOG entry, tag/GitHub Release, PyPI.
- Candidate matrix table: CAND ID, title, implementation evidence, tests/checkers, safety note.
- Candidate tracking evidence section.
- Checks run section.
- Safety invariants table.
- Stale/premature claim scan section.
- Known non-blockers section.
- Blockers section.
- Final decision: `READY_FOR_V0.6.12_RELEASE_PREP` or equivalent.

**Steps:**
- [ ] Step 2.1: Create doc header and status.
- [ ] Step 2.2: Add candidate matrix.
- [ ] Step 2.3: Add safety invariants and claim scan.
- [ ] Step 2.4: Add final decision.

---

## Task 3: Candidate index

**Files:**
- Create: `docs/releases/v0.6.12-candidates.md`
- Create: `docs/releases/v0.6.12-candidates.json`

**Design:**
- Markdown: status, selection criteria, candidate table with id/title/summary/user value/safety boundary/risk/recommendation, accepted list, deferred list (CAND-008/010 if not tracked), rejected/out-of-scope list (live trading, broker execution, provider execution, autonomous trading, PyPI publish, tag/release, version bump, runtime changes), safety boundaries, constraints, release criteria, next steps.
- JSON: schema_version, release_line, current_public_release, next_planned_release, candidates array with id/title/implemented/selected_for_v0612/primary_files/checkers/tests/workflows/safety_scope, deferred array, rejected array.

**Steps:**
- [ ] Step 3.1: Create Markdown index.
- [ ] Step 3.2: Create JSON index.
- [ ] Step 3.3: Validate JSON parses.

---

## Task 4: Checker

**Files:**
- Create: `scripts/check_v0612_release_candidate_readiness.py`

**Design:**
- Validate:
  - `docs/releases/v0.6.12-candidate-readiness.md` exists.
  - `docs/releases/v0.6.12-candidates.md` exists.
  - `docs/releases/v0.6.12-candidates.json` exists and parses.
  - CAND-001 through CAND-016 are mentioned in readiness doc or candidate index.
  - `docs/releases/release-metadata.json` `current_public_release` is `v0.6.11`, not `v0.6.12`.
  - No doc claims v0.6.12 is released/current public.
  - v0.6.12 tag does not need to exist.
  - Package/source version remains `0.6.11` (read pyproject.toml and `src/atlas_agent/__init__.py` if simple; otherwise trust version consistency checker).
  - Required safety phrases present in readiness doc: live trading disabled, broker execution disabled, provider execution disabled, no PyPI publish, no tag/release created.
  - Required workflow/checker docs linked: reviewer trust snapshot, release assurance bundle demo, diagnostics artifact, diagnostics revalidation workflow, artifact retention audit.
  - Forbidden claims absent (use simple phrase scan).
  - No stale wording "current public v0.6.12".
- CLI: `--json`, human-readable PASS/FAIL.
- Exit codes: 0 pass, 1 fail, 2 operational error.

**Steps:**
- [ ] Step 4.1: Create checker scaffold.
- [ ] Step 4.2: Implement doc existence and CAND coverage checks.
- [ ] Step 4.3: Implement release-state and safety-phrase checks.
- [ ] Step 4.4: Implement forbidden/stale-claim checks.
- [ ] Step 4.5: Run checker on real repo; expect PASS.

---

## Task 5: Tests

**Files:**
- Create: `tests/test_v0612_release_candidate_readiness.py`

**Design:**
- Tests:
  - checker passes on real repo;
  - checker JSON output works;
  - checker fails if a CAND entry is missing (temporarily modify parsed JSON or doc);
  - checker fails if docs claim v0.6.12 is released;
  - checker fails if current public release is stated as v0.6.12;
  - checker fails if safety invariant text is missing;
  - checker fails on forbidden claims;
  - checker fails if required workflow/checker links are missing;
  - checker fails if PyPI publish/tag/release wording implies it happened.
- Use temp files and monkeypatch or pass paths to check function.

**Steps:**
- [ ] Step 5.1: Write fixture helpers.
- [ ] Step 5.2: Write positive and negative tests.
- [ ] Step 5.3: Run `pytest tests/test_v0612_release_candidate_readiness.py -q`.

---

## Task 6: Doc updates

**Files:**
- Modify: `docs/trust/README.md`
- Modify: `docs/trust/v0.6.11-status.md`
- Modify: `docs/release-candidate-readiness.md`
- Modify: `docs/public-launch-readiness.md`
- Modify: `docs/reviewer-checklist.md`
- Optional: `README.md`, `docs/security/release-readiness.md`, `docs/security/release-assurance-diagnostics.md`, `docs/security/release-assurance-workflow-dispatch.md`

**Design:**
- Add concise links to the new v0.6.12 readiness doc/index.
- Confirm v0.6.12 is next planning line, not released.
- Do not duplicate large content.

**Steps:**
- [ ] Step 6.1: Update trust docs.
- [ ] Step 6.2: Update release readiness and public launch docs.
- [ ] Step 6.3: Update reviewer checklist.

---

## Task 7: Gate integration

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/release_check.sh` (if consistent)

**Design:**
- Add checker run and pytest run.
- Place in release-assurance/candidate-readiness section.

**Steps:**
- [ ] Step 7.1: Add to dev_check.
- [ ] Step 7.2: Add to ci_check.
- [ ] Step 7.3: Add to ci.yml.
- [ ] Step 7.4: Add to release_check.sh if appropriate.

---

## Task 8: Validation

**Steps:**
- [ ] Step 8.1: Run checker.
- [ ] Step 8.2: Run tests.
- [ ] Step 8.3: Run `scripts/check_docs_archive_hygiene.py`.
- [ ] Step 8.4: Run `scripts/check_forbidden_claims.py`.
- [ ] Step 8.5: Run `scripts/check_public_docs_consistency.py`.
- [ ] Step 8.6: Run `scripts/check_version_consistency.py`.
- [ ] Step 8.7: Run `scripts/check_trust_center.py`.
- [ ] Step 8.8: Run `git diff --check`.
- [ ] Step 8.9: Run `./scripts/dev_check.sh`.
- [ ] Step 8.10: Run `./scripts/ci_check.sh`.
- [ ] Step 8.11: Run `./scripts/release_check.sh --quick`.

---

## Task 9: Commit, push, CI verification

**Steps:**
- [ ] Step 9.1: Stage explicit files.
- [ ] Step 9.2: Commit with `docs: consolidate v0.6.12 release candidate readiness`.
- [ ] Step 9.3: Push to origin/main.
- [ ] Step 9.4: Verify push-CI is green.

---

## Spec coverage self-check

- Readiness doc: Task 2.
- Candidate index: Task 3.
- Checker: Task 4.
- Tests: Task 5.
- Doc updates: Task 6.
- Gate integration: Task 7.
- Validation: Task 8.
