# CAND-017: Post-Release CI Run-ID Recorder

## Summary

Add `scripts/update_release_assurance_ci.py`, a small deterministic helper that
queries GitHub Actions for the workflow runs associated with a release tag and
injects the run IDs and URLs into the post-release assurance dossier
(`docs/releases/v0.6.X-post-release-assurance.md`) and its optional JSON mirror
(`docs/releases/v0.6.X-post-release-assurance.json`).

The script is **dry-run by default**; it only mutates files when passed
`--write`. It shells out to the already-authenticated `gh` CLI, uses only the
Python standard library, performs no network mutation, and does not change any
runtime, safety, broker, provider, or credential-loading code.

## Motivation

The v0.6.22 post-release assurance dossier was committed with a placeholder CI
section because the tag-triggered workflows had not yet completed. Manually
updating the dossier with run IDs is error-prone and easy to forget. CAND-017
automates that final step while keeping the human in control via an explicit
`--write` flag.

## Design

### Script interface

```bash
python3.11 scripts/update_release_assurance_ci.py \
  --tag v0.6.23 \
  --md docs/releases/v0.6.23-post-release-assurance.md \
  --json docs/releases/v0.6.23-post-release-assurance.json \
  --write
```

- `--tag` (required): release tag, e.g. `v0.6.23`.
- `--md` (required): path to the markdown assurance dossier.
- `--json` (required): path to the JSON assurance artifact.
- `--write` (optional): actually mutate the files. Without it, the script prints
the proposed updates to stdout and exits 0.

### Behavior

1. Verify the GitHub Release exists via `gh release view <tag> --json url`.
2. List workflow runs for the tag via
   `gh run list --branch <tag> --limit 100 --json name,displayTitle,headBranch,event,status,conclusion,url,createdAt,databaseId`.
3. Filter to the workflows of interest:
   - `CI`
   - `Release Gate`
   - `Atlas Agent Paper Routines`
4. For each matched workflow, keep the most recent run.
5. Generate:
   - A markdown table under `## GitHub Actions / CI Status` in the `.md` file.
   - A JSON array under `ci_status.runs` in the `.json` file.
6. If `--write`:
   - Replace the placeholder paragraph/table in the markdown file atomically.
   - Update the JSON file atomically (write to temp, fsync, rename).
7. Print a summary of matched runs and whether files were updated.

### Safety and boundaries

- No live trading, live submit, broker/provider execution, order placement,
  pending-order creation, or approval-queue mutation.
- No credential loading beyond what `gh` already manages.
- No runtime or safety-module changes.
- No broadening of the CAND-014 provider-artifact extraction boundary.
- Dry-run by default; `--write` is required for any file mutation.
- Atomic writes for the JSON file; markdown edits are bounded to the
  `## GitHub Actions / CI Status` section.

### Files changed

- New: `scripts/update_release_assurance_ci.py`
- New: `tests/test_update_release_assurance_ci.py`
- Update: `docs/releases/v0.6.23-candidates.md` to accept CAND-017
- Update: `docs/releases/v0.6.23-plan.md` to list CAND-017
- Update: `docs/autonomy-roadmap.md` to record CAND-017 in the v0.6.23 section
- Later: `docs/releases/v0.6.23-post-release-assurance.md` and `.json` will be
  updated by the script after the v0.6.23 release is cut.

### Tests

- Mock `gh` subprocess output and verify the script parses runs correctly.
- Verify dry-run mode does not mutate files.
- Verify `--write` mode updates both `.md` and `.json` as expected.
- Verify the script exits non-zero if the release does not exist.
- Verify only the most recent run per workflow is retained.

### Acceptance criteria

- `scripts/update_release_assurance_ci.py --tag v0.6.22 --md ... --json ...`
  runs without `--write` and prints plausible CI updates for the existing
  v0.6.22 release.
- `pytest tests/test_update_release_assurance_ci.py` passes.
- `check_public_docs_consistency.py`, `check_candidate_chain.py`,
  `check_release_metadata.py`, and `check_version_consistency.py` pass after
  CAND-017 is accepted into the v0.6.23 candidate chain.
- The dossier and JSON updates contain no live-trading, production-readiness,
  or profitability claims.
