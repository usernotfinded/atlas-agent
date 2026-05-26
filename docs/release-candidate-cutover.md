# Release Candidate Cutover Dry Run

> **Not financial advice.** This document describes a local release-engineering dry run, not trading recommendations.

## What this is

The Release Candidate Cutover Dry Run is a **dry-run only** local report for checking whether the current repository can move from the `v0.5.7` development series toward a **sandbox release candidate** such as `v0.5.7-rc1`.

It is a paper-first release-engineering preflight. It checks version shape, documentation readiness, public safety wording, required local verification commands, protected boundary cleanliness, and hard-false safety invariants.

## What this is not

- Not the RC release itself.
- Not a live-trading release.
- Not a production trading milestone.
- Not a provider execution unlock.
- Not a broker integration milestone.
- Not a trust grant.
- Not a profitability or trading-correctness claim.

## Target RC Version Format

Accepted target versions use the repository tag convention:

```bash
atlas research release-candidate-cutover-dry-run --target-version v0.5.7-rc1 --json
```

Valid examples include `v0.5.7-rc1`, `v0.5.7-rc2`, and `v1.2.3-rc1`.

Rejected examples include missing `v` prefixes, development tags, final stable tags, malformed RC tags, strings with spaces or shell metacharacters, absolute local paths, and secret-like fragments.

## Dry-Run Checks

The dry run checks:

- Current package version is `0.5.7rc3`.
- Target version is an RC tag, not a dev tag or final stable tag.
- The dev-to-RC transition is coherent.
- `docs/releases/v0.5.7-rc3.md` exists.
- README quickstart verification passes.
- Public docs consistency passes.
- Provider safety docs and release candidate readiness code are present.
- Release checklist includes quick, research, and full release checks.
- Forbidden claims scan passes.
- Protected boundaries are clean.

## Safety Guarantees

- Dry-run only: no tag is created.
- Dry-run only: no push is performed.
- Dry-run only: no publish step is performed.
- Provider execution remains locked.
- Trust remains blocked.
- No broker/order path is enabled.
- No credentials loaded by the provider safety workflow.
- No network enabled by the provider safety workflow.
- Live trading disabled by default.
- Safety validation does not imply profitability.
- Safety validation does not imply trading correctness.

## Manual Release Steps After Review

After all local checks and external review pass, a human may decide whether to run release commands manually. The dry-run command does not run those commands and does not output a release artifact path.

Manual release work remains outside this command and should only happen after explicit review.

## Limitations

- The dry run inspects local repository state only.
- It does not run a clean network clone.
- It does not build or publish packages.
- It does not create GitHub releases.
- It does not validate broker credentials or provider API keys.
- It does not measure trading performance.
