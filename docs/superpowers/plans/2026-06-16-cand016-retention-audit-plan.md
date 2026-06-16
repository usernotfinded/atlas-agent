# CAND-016 — Release Assurance Artifact Retention Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only artifact retention audit (script, manual workflow, static checker, tests, docs) so maintainers can see whether release-assurance artifacts are available, near expiry, or expired.

**Architecture:** A Python audit script queries GitHub artifact metadata via `gh api` (live) or reads a JSON fixture (`--input-json`) for deterministic tests. A manual `workflow_dispatch` workflow runs the script with read-only permissions and uploads the JSON/Markdown report. A static checker validates the script/workflow safety invariants. Tests exercise fixture mode and the checker. Docs and CI/dev gates are updated to include the new checks.

**Tech Stack:** Python 3.11, `gh` CLI metadata commands, GitHub Actions YAML, pytest.

---

## File map

- Create `scripts/audit_release_assurance_artifact_retention.py` — read-only audit script.
- Create `.github/workflows/release-assurance-artifact-retention-audit.yml` — manual workflow.
- Create `scripts/check_release_assurance_artifact_retention_audit.py` — static checker.
- Create `tests/test_release_assurance_artifact_retention_audit.py` — pytest tests.
- Modify `docs/security/release-assurance-diagnostics.md` — add retention audit section.
- Modify `docs/security/release-assurance-workflow-dispatch.md` — document manual dispatch.
- Modify `docs/security/release-readiness.md` — mention retention audit visibility.
- Modify `docs/reviewer-checklist.md` — add retention audit item.
- Modify `docs/public-launch-readiness.md` — mention artifact retention visibility.
- Modify `scripts/dev_check.sh` — add checker + fixture + tests.
- Modify `scripts/ci_check.sh` — add checker + fixture + tests.
- Modify `.github/workflows/ci.yml` — add checker + fixture + tests steps.

---

## Task 1: Audit script

**Files:**
- Create: `scripts/audit_release_assurance_artifact_retention.py`

**Design:**
- Default watched artifact names:
  - `release-assurance-diagnostics`
  - `release-assurance-diagnostics-validation`
  - `release-assurance-bundle-demo`
  - `reviewer-trust-snapshot`
- CLI flags:
  - `--repo` (default from `GITHUB_REPOSITORY` env or `usernotfinded/atlas-agent`)
  - `--artifact-name` repeatable or comma-separated
  - `--older-than-days` default 7
  - `--near-expiry-days` default 3
  - `--output-dir` default current directory
  - `--input-json` fixture path (optional)
  - `--json` machine-readable output
- Live mode runs `gh api repos/{owner}/{repo}/actions/artifacts?per_page=100` (and paginates) to list artifact metadata. No `gh run download`, no delete, no `DELETE`.
- Fixture mode reads a JSON file matching the `gh api` artifacts list shape (`{"artifacts": [...], "total_count": N}`).
- Each artifact record in report includes:
  - `name`, `id`, `source_run_id` (from `workflow_run.id` if present)
  - `created_at`, `expires_at`
  - `expired` (bool), `age_days` (int), `days_until_expiry` (int)
  - `matches_watched_names` (bool)
  - `retention_status` — `available`, `near_expiry`, `expired`, or `unknown`
- Status logic:
  - If `expired` true → `expired`
  - Else if `days_until_expiry <= near_expiry_days` → `near_expiry`
  - Else → `available`
  - If dates missing → `unknown`
- Outputs `release-assurance-artifact-retention-report.json` and `release-assurance-artifact-retention-report.md` to output dir.
- Exit 0 on success, 1 for validation/config errors, 2 for operational errors.
- Human-readable summary printed unless `--json`.

**Steps:**
- [ ] Step 1.1: Create script with argparse, default constants, and helper to parse artifact names.
- [ ] Step 1.2: Implement fixture loading and validation.
- [ ] Step 1.3: Implement live `gh api` listing with pagination.
- [ ] Step 1.4: Implement report building with age/expiry calculations.
- [ ] Step 1.5: Implement JSON and Markdown report writers.
- [ ] Step 1.6: Run `python3.11 scripts/audit_release_assurance_artifact_retention.py --help`.
- [ ] Step 1.7: Run fixture-mode smoke test with synthetic input.

---

## Task 2: Manual workflow

**Files:**
- Create: `.github/workflows/release-assurance-artifact-retention-audit.yml`

**Design:**
- Trigger: `workflow_dispatch` only.
- Permissions:
  - `contents: read`
  - `actions: read`
- Env:
  - `GH_TOKEN: ${{ github.token }}`
  - `ENABLE_LIVE_TRADING: "false"`
  - `PROVIDER_EXECUTION_ENABLED: "false"`
  - `BROKER_EXECUTION_ENABLED: "false"`
- Inputs:
  - `older_than_days` type string default `7`
  - `near_expiry_days` type string default `3`
  - `artifact_names` type string default `release-assurance-diagnostics,release-assurance-diagnostics-validation,release-assurance-bundle-demo,reviewer-trust-snapshot`
- Steps:
  1. checkout
  2. setup-python 3.11
  3. run audit script with inputs
  4. upload artifact `release-assurance-artifact-retention-audit` from report dir
- No download, delete, tag, release, PyPI.

**Steps:**
- [ ] Step 2.1: Create workflow file matching existing style.
- [ ] Step 2.2: Validate YAML with `python3.11 -c "import yaml; yaml.safe_load(...)"`.

---

## Task 3: Static checker

**Files:**
- Create: `scripts/check_release_assurance_artifact_retention_audit.py`

**Design:**
- Validates:
  - audit script exists
  - workflow exists
  - workflow is `workflow_dispatch` only
  - permissions are `contents: read` and `actions: read` only; no write scopes
  - token uses `GH_TOKEN: ${{ github.token }}` only
  - no arbitrary `secrets.*`
  - no `gh run download`, `download-artifact`, `DELETE`, `gh api -X DELETE`
  - no `git push`, `git tag`, `gh release create`, `gh release upload`, `twine upload/publish`
  - no live/broker/provider execution enablement
  - workflow uploads only `release-assurance-artifact-retention-audit` artifact
- Output: human-readable PASS/FAIL or `--json`.
- Exit 0 pass, 1 fail, 2 operational error.

**Steps:**
- [ ] Step 3.1: Create checker scaffold with argparse and workflow text loaders.
- [ ] Step 3.2: Implement trigger/permission/token/secret checks.
- [ ] Step 3.3: Implement forbidden command checks.
- [ ] Step 3.4: Implement upload artifact name check.
- [ ] Step 3.5: Run checker on real repo; expect PASS.

---

## Task 4: Tests

**Files:**
- Create: `tests/test_release_assurance_artifact_retention_audit.py`

**Design:**
- Tests for audit script fixture mode:
  - JSON + Markdown report generation
  - watched names filtering
  - age/days_until_expiry determinism
  - expired / near_expiry / available statuses
  - no matches still produces valid report
  - `--json` CLI output
  - `--help` CLI output
  - bad input JSON fails
- Tests for checker:
  - passes on real repo
  - JSON output works
  - rejects `gh run download`
  - rejects `download-artifact`
  - rejects `DELETE`
  - rejects `contents: write`
  - rejects arbitrary secrets
  - rejects release/tag/PyPI commands

**Steps:**
- [ ] Step 4.1: Write fixture factory helper.
- [ ] Step 4.2: Write audit script fixture-mode tests.
- [ ] Step 4.3: Write checker tests including unsafe variant fixtures.
- [ ] Step 4.4: Run `pytest tests/test_release_assurance_artifact_retention_audit.py -q`.

---

## Task 5: Docs updates

**Files:**
- Modify: `docs/security/release-assurance-diagnostics.md`
- Modify: `docs/security/release-assurance-workflow-dispatch.md`
- Modify: `docs/security/release-readiness.md`
- Modify: `docs/reviewer-checklist.md`
- Modify: `docs/public-launch-readiness.md`

**Design:**
- Explain what retention audit does (read-only metadata visibility).
- Explain what it does NOT do (no download, no delete, no cleanup, no tag/release/PyPI).
- Show local fixture mode command.
- Show manual workflow dispatch command.
- Explain JSON/Markdown report fields.
- Clarify expiry is visibility only, not cleanup.

**Steps:**
- [ ] Step 5.1: Update `release-assurance-diagnostics.md` with retention audit section.
- [ ] Step 5.2: Update `release-assurance-workflow-dispatch.md` with dispatch instructions.
- [ ] Step 5.3: Update `release-readiness.md`.
- [ ] Step 5.4: Update `reviewer-checklist.md`.
- [ ] Step 5.5: Update `public-launch-readiness.md`.

---

## Task 6: Gate integration

**Files:**
- Modify: `scripts/dev_check.sh`
- Modify: `scripts/ci_check.sh`
- Modify: `.github/workflows/ci.yml`

**Design:**
- Add static checker invocation.
- Add deterministic fixture-mode audit invocation.
- Add pytest invocation for `tests/test_release_assurance_artifact_retention_audit.py`.
- No live GitHub API calls in normal gates.

**Steps:**
- [ ] Step 6.1: Add entries to `scripts/dev_check.sh` in the release-assurance section.
- [ ] Step 6.2: Add entries to `scripts/ci_check.sh` in the release-assurance section.
- [ ] Step 6.3: Add steps to `.github/workflows/ci.yml` quick-gate job.

---

## Task 7: Validation

**Steps:**
- [ ] Step 7.1: Run audit script `--help`.
- [ ] Step 7.2: Run static checker.
- [ ] Step 7.3: Run new pytest tests.
- [ ] Step 7.4: Run existing release-assurance checks to ensure no regression.
- [ ] Step 7.5: Run `git diff --check`.
- [ ] Step 7.6: Run `./scripts/dev_check.sh` (or focused subset if full run is too slow).
- [ ] Step 7.7: Run `./scripts/ci_check.sh` (or focused subset).

---

## Task 8: Commit, push, and verify CI

**Steps:**
- [ ] Step 8.1: Stage explicit files only (no `git add .`).
- [ ] Step 8.2: Commit with message `ci: add release assurance artifact retention audit`.
- [ ] Step 8.3: Push to `origin/main`.
- [ ] Step 8.4: Find push-CI run via `gh run list --repo usernotfinded/atlas-agent --branch main --limit 5`.
- [ ] Step 8.5: Wait for CI conclusion; if failure, inspect logs, fix, commit, push.

---

## Task 9: Optional real retention audit dispatch

**Steps:**
- [ ] Step 9.1: If authenticated and CI is green, dispatch workflow with default inputs.
- [ ] Step 9.2: Verify run conclusion success.
- [ ] Step 9.3: Verify report artifact `release-assurance-artifact-retention-audit` uploaded.
- [ ] Step 9.4: Optionally download and inspect report JSON/Markdown.
- [ ] Step 9.5: If dispatch blocked, report exact blocker.

---

## Spec coverage self-check

- Read-only metadata audit: Task 1.
- No download/delete: Tasks 1, 2, 3.
- Fixture-based deterministic tests: Tasks 1, 4.
- Manual workflow: Task 2.
- Static checker: Task 3.
- Docs: Task 5.
- Gate integration: Task 6.
- Safety invariants: Tasks 2, 3, 7.
