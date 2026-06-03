# Release Readiness

## Security hardening release readiness

The security hardening changes must be delivered through a future versioned release so auto-updater users can receive them.

Release must be performed only after:
- all security hardening PRs are merged;
- version consistency checks pass;
- forbidden claims scan passes;
- dev/CI/research/release checks pass;
- no live trading/provider execution defaults changed;
- no secrets are present;
- changelog/release notes are updated;
- tag/release/PyPI publish steps are explicitly approved.
