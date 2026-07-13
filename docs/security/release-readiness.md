# Release Readiness

## Security hardening release readiness

The v0.6.25 public GitHub release is the current stable version. v0.6.24 and earlier releases are historical.

Release was performed after:
- all security hardening PRs were merged;
- version consistency checks passed;
- forbidden claims scan passed;
- generated artifact hygiene checks passed;
- dev/CI/research/release checks passed;
- no live trading/provider execution defaults changed;
- no secrets were present;
- changelog/release notes were updated;
- tag/release steps were explicitly approved.

## Auto-updater delivery verification

After a security release, maintainers must verify that the auto-updater can detect the new GitHub release/tag.

For v0.6.25, the public GitHub release is `v0.6.25`. v0.6.24 is historical.

PyPI was not published. A separate approval process is required for any future PyPI publish.

The updater verification must not install packages, modify files, enable live trading, call providers, or require credentials.

## Release assurance

After publishing a security release, maintainers can generate a local release assurance pack:

```bash
python scripts/release_assurance.py --version v0.6.25 --output artifacts/release_assurance/v0.6.25-local-check
```

The pack verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims.

It does not create tags, publish packages, call providers, enable trading, or modify runtime behavior.

If a check fails, `release_assurance.py` emits a redacted diagnostic block to `stderr` and can write a machine-readable `release-assurance-diagnostics.json` via `--diagnostics-json`. See [Release Assurance Diagnostics](release-assurance-diagnostics.md) for details on redaction, usage, and debugging workflow failures.

### End-to-end bundle demo

A fully local, offline demo generates a baseline release-assurance bundle, an opt-in bundle with a reviewer trust snapshot, and a manifest describing both:

```bash
bash scripts/demo_release_assurance_snapshot_bundle.sh \
  --version v0.6.12 \
  --output-dir artifacts/release_assurance/v0.6.12-bundle-demo \
  --deterministic
```

See [Release Assurance Bundle Demo](release-assurance-bundle-demo.md) for details.

### Optional reviewer trust snapshot

You can include a deterministic reviewer trust snapshot in the assurance output:

```bash
python scripts/release_assurance.py \
  --version v0.6.12 \
  --output artifacts/release_assurance/v0.6.12-local \
  --include-reviewer-trust-snapshot
```

This is opt-in only. The snapshot is written to
`<output>/reviewer-trust-snapshot/` and validated before the pack is finalized.
It remains local-only and does not tag, release, publish, call providers/brokers,
or enable live trading.

## CI release assurance

`.github/workflows/release-assurance.yml` can be run manually with `workflow_dispatch` to generate a fresh release assurance pack in GitHub Actions.

The workflow verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims, then uploads the generated assurance pack as an artifact.

It is read-only and non-publishing. It does not create tags, create GitHub releases, publish to PyPI, use secrets, call providers, touch brokers, or enable trading.

### Optional release assurance bundle demo

The workflow has an additional opt-in input, `run_bundle_demo` (default `false`). When set to `true`, the workflow also runs `scripts/demo_release_assurance_snapshot_bundle.sh`, validates the resulting manifest with `scripts/check_release_assurance_bundle_manifest.py`, and uploads the baseline bundle, opt-in snapshot bundle, and manifest as the `release-assurance-bundle-demo` artifact.

This optional path is disabled by default so that normal workflow dispatches behave exactly as before. It uses no secrets, creates no tags or releases, publishes no packages, and does not enable live trading, provider execution, broker execution, or order submission.

#### Optional diagnostics artifact

The workflow also has opt-in inputs:

- `upload_diagnostics_json` (default `false`)
- `validate_diagnostics_artifact` (default `false`)

When `upload_diagnostics_json=true`, a failed `release_assurance.py` run writes a redacted
`release-assurance-diagnostics.json`. If `validate_diagnostics_artifact=true`, the workflow
validates that JSON with `scripts/check_release_assurance_diagnostics_artifact.py` before
uploading it. The artifact is uploaded only if validation succeeds, and the workflow still
concludes failure after the upload.

After downloading the diagnostics artifact, validate it locally with:

```bash
python3.11 scripts/check_release_assurance_diagnostics_artifact.py <path> \
  --expect-release <release>
```

This checker accepts a JSON file, a directory containing `release-assurance-diagnostics.json`, or a downloaded `.zip`. It verifies the schema, failure semantics, release identity, redaction metadata, and scans all string values for unredacted secrets, credentials, account IDs, and unsafe publishing commands. See [Release Assurance Workflow Dispatch](release-assurance-workflow-dispatch.md) for the full dispatch and validation guide.

A separate manual workflow, [Release Assurance Diagnostics Artifact Validate](../../.github/workflows/release-assurance-diagnostics-artifact-validate.yml), can re-download and re-validate a previously uploaded diagnostics artifact from a known run ID. It is `workflow_dispatch` only, uses `contents: read` and `actions: read` permissions, and relies only on `GH_TOKEN: ${{ github.token }}`. It uploads a `release-assurance-diagnostics-validation` report artifact and fails if validation fails. It does not create tags, releases, or packages, and does not call providers, brokers, or enable live trading.

### Artifact retention visibility

A separate manual workflow, [Release Assurance Artifact Retention Audit](../../.github/workflows/release-assurance-artifact-retention-audit.yml),
provides a visibility-only check of whether release-assurance artifacts are available,
near expiry, or expired. It queries artifact metadata only; it does not download or delete
artifacts, create tags or releases, publish to PyPI, or enable trading. See
[Release Assurance Diagnostics](release-assurance-diagnostics.md) for the report format and
[Release Assurance Workflow Dispatch](release-assurance-workflow-dispatch.md) for dispatch
instructions.

Generated release assurance and provider evidence outputs should stay local or
be uploaded as CI artifacts unless a task explicitly requires a versioned
evidence pack. See [Generated Artifacts](../development/generated-artifacts.md)
and run `python3.11 scripts/check_generated_artifacts.py` before staging.

GitHub Actions workflow action versions are covered by
[GitHub Actions Maintenance](../development/github-actions.md). Run
`python3.11 scripts/check_github_actions_versions.py` after workflow edits to
confirm `actions/checkout@v6`, `actions/setup-python@v6`, and
`actions/upload-artifact@v6` are still in place without changing workflow
permissions, secrets, or publishing behavior.

After direct-main maintenance pushes, maintainers can run
`python3.11 scripts/main_health.py` for local post-push verification of
`main`, `origin/main`, source version identity, artifact hygiene,
release/tag safety, and protected runtime boundaries. Optional GitHub CLI
visibility is available with `python3.11 scripts/main_health.py --include-github`;
missing GitHub CLI should be treated as a visibility limitation, not a local
release-readiness failure.

The trust center is checked by `scripts/check_trust_center.py` to prevent stale public release/security messaging.

Contributor onboarding docs are checked by `scripts/check_onboarding_docs.py`
to keep local setup, safe-check, and release-sensitive command guidance current.

Current release-state gates use:

```bash
python3.11 scripts/check_v0612_release_cutover.py
python3.11 scripts/check_v0612_release_prep.py --post-release
python3.11 -m pytest tests/test_v0612_release_cutover.py -q
python3.11 -m pytest tests/test_v0612_release_prep.py -q
```

The version-specific commands below are retained in
`scripts/historical_release_checkers/` for audit and regression use only.

## v0.6.6 readiness

For v0.6.6 release readiness and post-cutover verification, run the v0.6.6 release prep checker:

```bash
python3.11 scripts/historical_release_checkers/check_v066_release_prep.py --release-prep
python3.11 scripts/historical_release_checkers/check_v066_release_prep.py --release-prep --json
```

## v0.6.4 readiness

For v0.6.4 release readiness and post-cutover verification, run the v0.6.4 release prep checker:

```bash
python3.11 scripts/historical_release_checkers/check_v064_release_prep.py --release-prep
python3.11 scripts/historical_release_checkers/check_v064_release_prep.py --release-prep --json
```

The checker verifies required docs, source modules, test files, CLI contract
entries, CHANGELOG `[0.6.4]` section, version identity, absence of a premature
v0.6.4 tag, forbidden claims, and generated artifact hygiene.

## v0.6.3 readiness

For v0.6.3 release readiness and post-cutover verification, run the v0.6.3 release prep checker:

```bash
python3.11 scripts/historical_release_checkers/check_v063_release_prep.py
python3.11 scripts/historical_release_checkers/check_v063_release_prep.py --json
```

The checker verifies required docs, source modules, test files, CLI contract
entries, CHANGELOG unreleased section, version identity, absence of a premature
v0.6.3 tag, forbidden claims, and generated artifact hygiene.

See [v0.6.0 Readiness Audit](../releases/v0.6.0-readiness.md) for the full
capability summary, safety boundaries, test coverage, docs coverage, deferred
items, non-goals, release blockers, and release recommendation.

## v0.6.15 post-release evidence

After the historical v0.6.15 public GitHub-only cutover, deterministic post-release evidence became the
canonical historical record for the v0.6.15 released state. The v0.6.16 planning line was seeded and has since been released.

- [v0.6.15 Post-Release Evidence](../releases/v0.6.15-post-release-evidence.md) — canonical deterministic cutover evidence
- [v0.6.16 Planning Seed](../releases/v0.6.16-plan.md) — next-line planning notes
- [v0.6.15 Candidate Selection](../releases/v0.6.15-candidate-selection.md) — historical pre-cutover candidate-selection gate

## v0.6.14 post-release evidence

The v0.6.14 public GitHub-only cutover evidence is now a historical record.

- [v0.6.14 Post-Release Evidence](../releases/v0.6.14-post-release-evidence.md) — historical deterministic cutover evidence
- [v0.6.14 Candidate Selection](../releases/v0.6.14-candidate-selection.md) — historical pre-cutover candidate-selection gate

## v0.6.12 candidate readiness

The v0.6.12 planning-line candidate readiness consolidation is now a historical
planning record:

- [docs/releases/v0.6.12-candidate-readiness.md](../releases/v0.6.12-candidate-readiness.md) (historical)
- `python3.11 scripts/check_v0612_release_candidate_readiness.py` still validates the historical record.

For the historical v0.6.15 release evidence, use
[docs/releases/v0.6.15-post-release-evidence.md](../releases/v0.6.15-post-release-evidence.md)
and run `python3.11 scripts/check_v0615_post_release_hygiene.py`.
