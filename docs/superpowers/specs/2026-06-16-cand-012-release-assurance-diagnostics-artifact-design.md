# CAND-012 — Release Assurance Workflow Diagnostics Artifact

## Purpose

CAND-011 added `--diagnostics-json <path>` to `scripts/release_assurance.py` so
that maintainers can capture a redacted, machine-readable diagnostic record when
a release assurance check fails. CAND-012 wires that optional output into the
manual GitHub Actions workflow so the diagnostics JSON can be downloaded as a
workflow artifact without changing default workflow behavior, permissions, or
safety boundaries.

## Scope

This candidate only changes `.github/workflows/release-assurance.yml`, adds a
workflow-focused static checker and tests, updates documentation, and integrates
the new checker/tests into local gates. It does not modify
`scripts/release_assurance.py` defaults, protected runtime boundaries, or any
live/provider/broker execution path.

## Components

### 1. `.github/workflows/release-assurance.yml`

Add an optional workflow input:

```yaml
upload_diagnostics_json:
  description: "Upload a redacted release-assurance diagnostics JSON artifact on failure"
  type: boolean
  required: false
  default: false
```

Change the `Generate release assurance pack` step so it:

- runs with an explicit `id: release_assurance`;
- creates `artifacts/release_assurance_diagnostics/`;
- passes `--diagnostics-json artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json`
  only when `inputs.upload_diagnostics_json` is `true`;
- captures the script exit code and writes it to `GITHUB_OUTPUT`;
- exits `0` so later upload steps can run.

Make the existing `Upload release assurance artifact` step conditional on
`steps.release_assurance.outputs.exit_code == '0'` so it still behaves like a
success-only upload.

Add a new `Upload release assurance diagnostics artifact` step:

```yaml
if: always() && inputs.upload_diagnostics_json && steps.release_assurance.outputs.exit_code != '0'
uses: actions/upload-artifact@v6
with:
  name: release-assurance-diagnostics
  path: artifacts/release_assurance_diagnostics/release-assurance-diagnostics.json
  if-no-files-found: ignore
  retention-days: 14
```

Make the bundle demo and manifest validation steps conditional on both
`inputs.run_bundle_demo` and `steps.release_assurance.outputs.exit_code == '0'`
so they do not run after a release-assurance failure.

Add a final `Fail if release assurance failed` step that exits with the
captured exit code when it is non-zero. This preserves the workflow's failure
conclusion while still allowing the diagnostics artifact to upload.

Keep `permissions: contents: read` and the safe job-level
`GH_TOKEN: ${{ github.token }}`. Do not add arbitrary `secrets.*` references,
write permissions, tag/release/PyPI commands, or live/provider/broker execution.

### 2. `scripts/check_release_assurance_diagnostics_workflow.py`

A static, local-only, read-only checker that validates:

- the workflow is `workflow_dispatch` only;
- `upload_diagnostics_json` input exists, is type boolean, and defaults to `false`;
- `--diagnostics-json` is passed only inside a conditional branch tied to the input;
- a diagnostics artifact upload step exists and is conditional on the input plus
  a failure outcome;
- a step re-emits the captured release-assurance exit code on failure;
- `permissions: contents: read` is preserved;
- only safe token patterns (`github.token`, `secrets.GITHUB_TOKEN`) are used;
- no arbitrary `secrets.*` references;
- no `contents: write` or other broad write permission;
- no forbidden commands (`git push`, `git tag`, `gh release create/upload`,
  `twine upload/publish`);
- no live/provider/broker execution commands or enabled flags;
- supports `--json` output and clear PASS/FAIL messages.

### 3. `tests/test_release_assurance_diagnostics_workflow.py`

Covers:

- real workflow passes the new checker;
- checker JSON output works;
- checker fails if `upload_diagnostics_json` defaults to `true`;
- checker fails if `--diagnostics-json` is passed unconditionally;
- checker fails if the diagnostics upload step is unconditional;
- checker fails if arbitrary `secrets.*` references are introduced;
- checker fails if `contents: write` is introduced;
- checker fails if release/tag/PyPI publish commands are introduced.

### 4. Documentation updates

- `docs/security/release-assurance-diagnostics.md` — document the workflow input,
  when the artifact is created, and how to download it.
- `docs/security/release-assurance-workflow-dispatch.md` — add input to dispatch
  examples and `gh run download` command for the diagnostics artifact.
- `docs/security/release-readiness.md` — add an optional diagnostics artifact
  section under CI release assurance.
- `docs/reviewer-checklist.md` and `docs/public-launch-readiness.md` — minimal
  cross-links.

### 5. Gate integration

Add fast invocations to:

- `scripts/dev_check.sh` (after existing diagnostics tests);
- `scripts/ci_check.sh` (after existing diagnostics tests);
- `.github/workflows/ci.yml` (after existing release-assurance diagnostics steps).

## Safety invariants

- Workflow remains `workflow_dispatch` only.
- `permissions: contents: read` is unchanged.
- Only the repository-provided read-only GitHub token is used.
- Diagnostics artifact generation remains opt-in and defaults to `false`.
- `run_bundle_demo` and `include_reviewer_trust_snapshot` defaults remain `false`.
- Workflow failure still results in a failed workflow conclusion after diagnostics upload.
- No tag/release/PyPI creation, no live/provider/broker execution, no credentials.
- No protected runtime boundary modifications.

## Success criteria

- `python3.11 scripts/check_release_assurance_diagnostics_workflow.py` passes on the real workflow.
- `python3.11 -m pytest tests/test_release_assurance_diagnostics_workflow.py -q` passes.
- Existing release-assurance diagnostics checker/tests still pass.
- `scripts/dev_check.sh`, `scripts/ci_check.sh`, and `scripts/release_check.sh --quick` pass.
- Push to `origin/main` triggers a green CI run.
- A controlled manual failure dispatch with `upload_diagnostics_json=true` and a
  fake release produces a downloadable `release-assurance-diagnostics` artifact
  containing redacted JSON and ends with workflow failure.
