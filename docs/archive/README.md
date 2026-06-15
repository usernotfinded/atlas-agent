# Atlas Agent Historical Docs Archive

> **Warning:** Documents in this directory are historical. They may describe old batches, release candidates, demos, or design plans that no longer reflect the current codebase or public messaging. For current guidance, see the docs listed under [What remains current](#what-remains-current).

## What was archived

The following historical documents were moved here as part of the CAND-005 historical-docs hygiene pass. They are preserved for auditability and release history but are no longer maintained as active public docs.

### Legacy planning documents

| Original path | Archived path | Reason |
|---|---|---|
| `docs/batch-4.4-reconciliation.md` | `archive/legacy-plans/batch-4.4-reconciliation.md` | Old batch reconciliation plan; no active references. |
| `docs/batch-4.6-plan.md` | `archive/legacy-plans/batch-4.6-plan.md` | Old batch plan; only self-referenced. |
| `docs/batch-4.7-plan.md` | `archive/legacy-plans/batch-4.7-plan.md` | Old batch plan; no active references. |
| `docs/design-batch-4.0-live-submit.md` | `archive/legacy-plans/design-batch-4.0-live-submit.md` | Old design doc for a batch that is no longer active. |
| `docs/v0.5.8-gap-prioritization.md` | `archive/legacy-plans/v0.5.8-gap-prioritization.md` | Historical v0.5.8 gap plan; still referenced by release notes and historical checkers, so archived instead of deleted. |

### Legacy release-candidate documents

| Original path | Archived path | Reason |
|---|---|---|
| `docs/release-candidate-audit-v0.5.7.dev2.md` | `archive/release-candidates/release-candidate-audit-v0.5.7.dev2.md` | Historical release-candidate audit; preserved for release evidence. |
| `docs/v0.5.8-rc1-cutover.md` | `archive/release-candidates/v0.5.8-rc1-cutover.md` | Historical RC cutover doc; no active references. |
| `docs/v0.5.8-rc1-readiness.md` | `archive/release-candidates/v0.5.8-rc1-readiness.md` | Historical RC readiness doc; referenced only by historical checkers. |

### Legacy demo documents

| Original path | Archived path | Reason |
|---|---|---|
| `docs/demo-recording-guide.md` | `archive/legacy-demos/demo-recording-guide.md` | Old demo recording guide; no active references outside historical tests. |

## What remains current

These documents remain actively maintained and are the canonical sources for reviewers and contributors:

- [Atlas Agent Trust Center](../trust/README.md)
- [Public Launch Readiness](../public-launch-readiness.md)
- [Reviewer Checklist](../reviewer-checklist.md)
- [Product Demo and Marketplace Readiness Pack](../product-demo-pack.md)
- [Product Demo Evidence Bundle](../product-demo-evidence.md)
- [Reviewer Trust Snapshot](../trust/reviewer-trust-snapshot.md)
- [Stable Release Decision](../stable-release-decision.md)
- [Stable Release Checklist](../stable-release-checklist.md)
- [SECURITY.md](../../SECURITY.md)
- [CHANGELOG.md](../../CHANGELOG.md)

## Why archive instead of delete

Many of these files describe release-candidate state, gap prioritization, or design rationale for versions that are now historical. Deleting them would break release notes, historical checkers, and the ability to audit past decisions. Archiving keeps the history intact while signaling that the content is not current.

## Safety notes

- Archived docs are **not** updated to reflect new releases.
- Do not point new contributors or public messaging to archived docs without clear historical context.
- Live trading, provider execution, broker execution, and order submission remain disabled by default in the current codebase regardless of what any archived doc describes.
