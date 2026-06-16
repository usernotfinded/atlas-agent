# CAND-014 Design: Release Assurance Diagnostics Artifact Validator Workflow Integration

## Context

CAND-012 made release-assurance diagnostics JSON downloadable from the manual `release-assurance.yml` workflow.
CAND-013 added a local validator (`scripts/check_release_assurance_diagnostics_artifact.py`) for downloaded diagnostics artifacts.

CAND-014 wires that validator into `.github/workflows/release-assurance.yml` as an optional workflow validation step so the same workflow that produces the diagnostics artifact can validate it before upload.

## Goals

- Keep all new behavior opt-in and default-off.
- Validate the diagnostics JSON before uploading it, but only when explicitly requested.
- Preserve the workflow's existing failure semantics: if release assurance failed, the workflow still fails after validation/upload.
- Keep the workflow manual-only, read-only, secret-free, and non-publishing.

## Non-goals

- Do not make diagnostics JSON generation default.
- Do not make diagnostics artifact validation default.
- Do not change any runtime trading, broker, provider, or risk behavior.
- Do not create tags, releases, or PyPI publishes.

## Design

### 1. Workflow input

Add a new optional boolean input to `.github/workflows/release-assurance.yml`:

```yaml
validate_diagnostics_artifact:
  description: Validate the diagnostics JSON before uploading it
  type: boolean
  required: false
  default: false
```

### 2. Validator step

After the `Generate release assurance pack` step captures `exit_code`, add a step that runs only when:

- `inputs.upload_diagnostics_json` is true,
- `inputs.validate_diagnostics_artifact` is true,
- the captured `exit_code` is non-zero (release assurance failed),
- the diagnostics JSON file exists.

Command:

```bash
python3.11 scripts/check_release_assurance_diagnostics_artifact.py \
  artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json
```

If validation fails, the step exits non-zero and the workflow stops before uploading the artifact.

### 3. Upload ordering

The existing diagnostics artifact upload step is moved (or remains) after the validator step. Its condition remains:

```yaml
if: ${{ inputs.upload_diagnostics_json && steps.release_assurance.outputs.exit_code != '0' }}
```

Because the validator step fails fast, the upload step only runs when validation succeeds.

### 4. Failure preservation

The final `Fail if release assurance failed` step re-emits the captured `exit_code`. It runs regardless of validation success because its condition is based on the captured exit code, not on the validator step outcome.

### 5. Checker update

Update `scripts/check_release_assurance_diagnostics_workflow.py` to assert:

- `validate_diagnostics_artifact` input exists, is boolean, and defaults to `false`.
- A validator step exists and calls `scripts/check_release_assurance_diagnostics_artifact.py`.
- The validator step is conditional on `upload_diagnostics_json`, `validate_diagnostics_artifact`, and failure.
- The validator step runs before the diagnostics artifact upload step.
- Upload remains conditional and the final failure step remains present.
- Existing safety invariants are preserved.

### 6. Tests

Update `tests/test_release_assurance_diagnostics_workflow.py` to cover the new input, step, ordering, and negative cases (default true, unconditional validator, upload before validation, missing validator command, secrets, `contents: write`, release/tag/PyPI commands).

### 7. Docs

Update:

- `docs/security/release-assurance-diagnostics.md`
- `docs/security/release-assurance-workflow-dispatch.md`
- `docs/security/release-readiness.md`
- `docs/reviewer-checklist.md`
- `docs/public-launch-readiness.md`

Document the new input, the recommended controlled-failure dispatch command, validation-before-upload behavior, and the preserved failure semantics.

### 8. Gate integration

Add/update the checker and focused tests in:

- `scripts/dev_check.sh`
- `scripts/ci_check.sh`
- `.github/workflows/ci.yml`

## Safety invariants

- Workflow remains `workflow_dispatch` only.
- Permissions remain `contents: read`.
- Only safe token pattern `GH_TOKEN: ${{ github.token }}` is used.
- No arbitrary `secrets.*` references.
- No `contents: write`, `id-token: write`, or other elevated permissions.
- No `git push`, `git tag`, `gh release create/upload`, or PyPI/twine publish commands.
- No live trading, broker order submission, or real provider/LLM execution.
- No credentials, account IDs, or private financial data.
- No unsafe marketing claims about risk, profitability, or live trading readiness.

## Success criteria

- `python3.11 scripts/check_release_assurance_diagnostics_workflow.py` passes on the real workflow.
- `pytest tests/test_release_assurance_diagnostics_workflow.py` passes.
- `scripts/dev_check.sh`, `scripts/ci_check.sh`, and `scripts/release_check.sh --quick` pass locally.
- Commit pushed to `origin/main` and push-CI run succeeds.
- Optional controlled failure dispatch demonstrates validator-before-upload behavior.
