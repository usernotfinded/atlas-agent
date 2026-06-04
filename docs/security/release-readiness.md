# Release Readiness

## Security hardening release readiness

The security hardening changes have been delivered through the `v0.5.9` versioned release so auto-updater users can receive them.

Release was performed after:
- all security hardening PRs were merged;
- version consistency checks passed;
- forbidden claims scan passed;
- dev/CI/research/release checks passed;
- no live trading/provider execution defaults changed;
- no secrets were present;
- changelog/release notes were updated;
- tag/release steps were explicitly approved.

## Auto-updater delivery verification

After a security release, maintainers must verify that the auto-updater can detect the new GitHub release/tag.

For v0.5.9, the expected public release is `v0.5.9`.

PyPI publishing was intentionally skipped unless explicitly approved separately.

The updater verification must not install packages, modify files, enable live trading, call providers, or require credentials.

## Release assurance

After publishing a security release, maintainers can generate a local release assurance pack:

```bash
python scripts/release_assurance.py --version v0.5.9 --output artifacts/release_assurance/v0.5.9
```

The pack verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims.

It does not create tags, publish packages, call providers, enable trading, or modify runtime behavior.

## CI release assurance

`.github/workflows/release-assurance.yml` can be run manually with `workflow_dispatch` to generate a fresh release assurance pack in GitHub Actions.

The workflow verifies release identity, public metadata, updater delivery, provider audit evidence, and safety non-claims, then uploads the generated assurance pack as an artifact.

It is read-only and non-publishing. It does not create tags, create GitHub releases, publish to PyPI, use secrets, call providers, touch brokers, or enable trading.

The trust center is checked by `scripts/check_trust_center.py` to prevent stale public release/security messaging.
