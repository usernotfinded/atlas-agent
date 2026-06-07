# Release Readiness

## Security hardening release readiness

The v0.6.3 hotfix has been delivered through the `v0.6.3` versioned GitHub release. The v0.6.2, v0.6.1, and v0.6.0 releases are historical. v0.6.4 is prepared but not yet tagged.

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

For v0.6.3, the public GitHub release is `v0.6.3`. For v0.6.4, release prep is complete but no tag or release has been created yet.

PyPI was not published. A separate approval process is required for any future PyPI publish.

The updater verification must not install packages, modify files, enable live trading, call providers, or require credentials.

## Release assurance

After publishing a security release, maintainers can generate a local release assurance pack:

```bash
python scripts/release_assurance.py --version v0.6.3 --output artifacts/release_assurance/v0.6.3-local-check
python scripts/release_assurance.py --version v0.6.4 --output artifacts/release_assurance/v0.6.4-local-check
```

The pack verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims.

It does not create tags, publish packages, call providers, enable trading, or modify runtime behavior.

## CI release assurance

`.github/workflows/release-assurance.yml` can be run manually with `workflow_dispatch` to generate a fresh release assurance pack in GitHub Actions.

The workflow verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims, then uploads the generated assurance pack as an artifact.

It is read-only and non-publishing. It does not create tags, create GitHub releases, publish to PyPI, use secrets, call providers, touch brokers, or enable trading.

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

## v0.6.4 readiness

For v0.6.4 release readiness and post-cutover verification, run the v0.6.4 release prep checker:

```bash
python3.11 scripts/check_v064_release_prep.py --release-prep
python3.11 scripts/check_v064_release_prep.py --release-prep --json
```

The checker verifies required docs, source modules, test files, CLI contract
entries, CHANGELOG `[0.6.4]` section, version identity, absence of a premature
v0.6.4 tag, forbidden claims, and generated artifact hygiene.

## v0.6.3 readiness

For v0.6.3 release readiness and post-cutover verification, run the v0.6.3 release prep checker:

```bash
python3.11 scripts/check_v063_release_prep.py
python3.11 scripts/check_v063_release_prep.py --json
```

The checker verifies required docs, source modules, test files, CLI contract
entries, CHANGELOG unreleased section, version identity, absence of a premature
v0.6.3 tag, forbidden claims, and generated artifact hygiene.

See [v0.6.0 Readiness Audit](../releases/v0.6.0-readiness.md) for the full
capability summary, safety boundaries, test coverage, docs coverage, deferred
items, non-goals, release blockers, and release recommendation.
