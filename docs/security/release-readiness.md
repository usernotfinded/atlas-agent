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
