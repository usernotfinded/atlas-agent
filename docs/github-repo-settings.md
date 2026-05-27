# GitHub Repository Settings Recommendations

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

This document describes recommended GitHub repository settings for Atlas Agent. These are recommendations only — they must be applied manually. Do not use GitHub API or automation to change repository settings.

## Repository description

**Suggested:**

> Local-first sandbox/paper trading research workbench with deterministic safety gates, audit logs, and release-engineering checks.

## Suggested topics

- python
- cli
- trading
- paper-trading
- research
- safety
- audit-logs
- release-engineering
- local-first
- risk-management

Do not include "algorithmic-trading" unless framed carefully so the repo does not appear live-trading ready.
Do not include "live-trading", "profit", or "alpha".

## About/sidebar settings

- **Website:** Leave blank or link to the repository itself.
- **Topics:** Use the suggested topics above.
- **Releases:** Not yet enabled for public distribution (no GitHub releases created).
- **Packages:** Not yet published to PyPI.
- **Suggested sidebar links:**
  - [External Reviewer Walkthrough](../docs/external-reviewer-walkthrough.md)
  - [Reviewer Checklist](../docs/reviewer-checklist.md)
  - [Public Launch Readiness](../docs/public-launch-readiness.md)

## Branch protection recommendations

For `main`:

- Require pull request reviews before merging (at least 1).
- Require status checks to pass before merging:
  - CI quick gate (`quick-gate`)
- Require no protected-boundary diffs unless justified.
- Require forbidden-claims scan to pass.
- Require clean install and package distribution checks for release branches.
- Require manual heavy release gate (`release-gate.yml`) before public release tags.

## Required status checks

- `quick-gate` — fast PR checks (version, claims, docs, focused pytest, pip check)
- Optional/manual: `release-gate.yml` — heavy gate for tags and manual dispatch

## Issue/PR template status

- Bug report template: present
- Docs issue template: present
- Safety concern template: present
- Feature request template: present
- Issue template config: present
- Pull request template: present

All templates warn against pasting secrets and remind contributors to check protected boundaries.

## Security policy status

- `SECURITY.md` is present.
- GitHub Security Advisories are enabled for private reporting.

## Release/tag policy

- Tags are created manually after all checks pass.
- No automated tagging from CI.
- No GitHub releases are created automatically.
- PyPI publication is not enabled.

## What not to enable yet

- Do not enable GitHub Actions to push tags or create releases.
- Do not enable PyPI publishing from CI.
- Do not enable merge without review.
- Do not enable live-trading-related marketing language in the repository description.
