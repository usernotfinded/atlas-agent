# CAND-016 — Release Assurance Artifact Retention Audit Design

## Goal
Add a read-only artifact retention audit so maintainers can see whether release-assurance diagnostics artifacts are still available, nearing expiration, or already expired.

## Scope
- Manual workflow only (`workflow_dispatch`).
- No scheduled trigger.
- No artifact download or deletion.
- No tag/release/PyPI creation.
- No trading runtime changes.

## Components

### 1. Audit script
`scripts/audit_release_assurance_artifact_retention.py`
- Read-only metadata audit.
- Live mode: `gh api` metadata queries only.
- Fixture mode: `--input-json <path>` for deterministic tests.
- CLI options:
  - `--repo <owner/name>` (default `GITHUB_REPOSITORY` or `usernotfinded/atlas-agent`)
  - `--artifact-name <name>` repeatable or comma-separated
  - default names: `release-assurance-diagnostics`, `release-assurance-diagnostics-validation`, `release-assurance-bundle-demo`, `reviewer-trust-snapshot`
  - `--older-than-days <n>` default `7`
  - `--near-expiry-days <n>` default `3`
  - `--output-dir <path>`
  - `--json`
- Outputs:
  - `release-assurance-artifact-retention-report.json`
  - `release-assurance-artifact-retention-report.md`
- Report fields per artifact:
  - name, id, source workflow run id
  - created_at, expires_at
  - expired, age_days, days_until_expiry
  - matches_watched_names, retention_status (`available`/`near_expiry`/`expired`/`unknown`)
- Exit codes:
  - `0` audit completed
  - `1` validation/config error
  - `2` operational error

### 2. Manual workflow
`.github/workflows/release-assurance-artifact-retention-audit.yml`
- Trigger: `workflow_dispatch` only.
- Permissions: `contents: read`, `actions: read`.
- Token: `GH_TOKEN: ${{ github.token }}`.
- Inputs:
  - `older_than_days` default `7`
  - `near_expiry_days` default `3`
  - `artifact_names` default comma-separated watched names
- Steps:
  - checkout
  - setup-python 3.11
  - run audit script
  - upload `release-assurance-artifact-retention-audit` artifact
- No download, no delete, no tag/release/PyPI.

### 3. Static checker
`scripts/check_release_assurance_artifact_retention_audit.py`
- Validates audit script and workflow exist.
- Ensures workflow is `workflow_dispatch` only.
- Ensures read-only permissions.
- Ensures safe token pattern only.
- Rejects arbitrary `secrets.*`.
- Rejects artifact download commands (`gh run download`, `download-artifact`).
- Rejects artifact delete commands (`DELETE`, `gh api -X DELETE`).
- Rejects `git push`, `git tag`, `gh release create/upload`, twine/PyPI.
- Rejects broker/provider/live execution commands.
- Supports `--json` and clear PASS/FAIL.

### 4. Tests
`tests/test_release_assurance_artifact_retention_audit.py`
- Fixture input produces JSON and Markdown reports.
- Watched names filtered correctly.
- age/days_until_expiry deterministic.
- expired/near_expiry/available statuses.
- No matching artifacts produces valid report.
- CLI `--json` and `--help`.
- Bad input JSON fails.
- Checker passes on real repo.
- Checker JSON output works.
- Checker rejects unsafe patterns (download, delete, write, secrets, tag/release/PyPI).

### 5. Docs updates
- `docs/security/release-assurance-diagnostics.md`
- `docs/security/release-assurance-workflow-dispatch.md`
- `docs/security/release-readiness.md`
- `docs/reviewer-checklist.md`
- `docs/public-launch-readiness.md`

### 6. Gate integration
- `scripts/dev_check.sh`
- `scripts/ci_check.sh`
- `.github/workflows/ci.yml`

## Safety invariants
- `workflow_dispatch` only.
- `contents: read`, `actions: read` only.
- Safe token pattern only.
- No arbitrary secrets.
- No artifact download or deletion.
- No tag/release/PyPI.
- No runtime behavior changes.
