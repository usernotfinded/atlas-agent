# Atlas Agent Trust Center

This page is the public trust/readiness entry point for Atlas Agent reviewers,
users, contributors, auditors, and potential adopters.

## Current Public Release

- Current public release: `v0.6.12` (tagged)
- Previous public release: `v0.6.11`
- Source package version on `main`: `0.6.12`
- GitHub release: `v0.6.12` (current public)
- Next planning line: `v0.6.13` (planning line; candidate docs will be created when the v0.6.13 cycle begins)
- Public v0.6.12: current public — [v0.6.12 Trust and Release Status](v0.6.12-status.md)
- Public v0.6.11: historical — [v0.6.11 Trust and Release Status](v0.6.11-status.md)
- Previous public v0.6.10 — [v0.6.10 Trust and Release Status](v0.6.10-status.md) (historical)
- PyPI was not published
- Current public release status: [v0.6.12 Trust and Release Status](v0.6.12-status.md) (current public)
- Previous release status: [v0.6.11 Trust and Release Status](v0.6.11-status.md) (historical)
- Previous previous release status: [v0.6.10 Trust and Release Status](v0.6.10-status.md) (historical)
- Previous previous previous release status: [v0.6.9 Trust and Release Status](v0.6.9-status.md) (historical)
- Previous previous previous previous release status: [v0.6.8 Trust and Release Status](v0.6.8-status.md) (historical)
- Current public release notes: [docs/releases/v0.6.12.md](../releases/v0.6.12.md) (current public)
- v0.6.11 release notes: [docs/releases/v0.6.11.md](../releases/v0.6.11.md) (historical)
- Previous release notes: [docs/releases/v0.6.10.md](../releases/v0.6.10.md) (historical)
- Previous previous release notes: [docs/releases/v0.6.9.md](../releases/v0.6.9.md) (historical)
- Previous previous previous release notes: [docs/releases/v0.6.8.md](../releases/v0.6.8.md) (historical)
- Previous previous previous previous release notes: [docs/releases/v0.6.7.md](../releases/v0.6.7.md) (historical)
- Historical release notes: [docs/releases/v0.6.6.md](../releases/v0.6.6.md), [docs/releases/v0.6.5.md](../releases/v0.6.5.md), [docs/releases/v0.6.3.md](../releases/v0.6.3.md), [docs/releases/v0.6.2.md](../releases/v0.6.2.md), [docs/releases/v0.6.1.md](../releases/v0.6.1.md), [docs/releases/v0.6.0.md](../releases/v0.6.0.md)

## Security Posture

Atlas Agent is safety-first, paper-first, and local-first by default. Public
security posture and release readiness are documented in:

- [SECURITY.md](../../SECURITY.md)
- [Release Readiness](../security/release-readiness.md)
- [Broker Safety](../security/broker-safety.md)
- [Dashboard Security](../security/dashboard-security.md)
- [Approval Safety](../security/approval-safety.md)

## Runtime Safety Defaults

- Live trading is disabled by default.
- Live submit is disabled by default.
- Provider execution is disabled by default.
- Broker execution is disabled by default.
- Human approval is required for live order flow.
- Passing deterministic risk gates does not mean automatic live execution.
- Telegram/remote control is disabled by default and operator-gated.

## Provider Audit Evidence

Provider evidence is local, non-authorizing audit material. It does not unlock
provider execution, broker execution, live trading, or order approval.

- [Provider Preflight](../security/provider-preflight.md)
- [Provider Evidence Index](../security/provider-evidence-index.md)
- [Provider Audit Pack](../security/provider-audit-pack.md)
- [Provider Audit Pack CI Workflow](../../.github/workflows/provider-audit-pack.yml)

## v0.6.12 Post-Release Evidence

The `v0.6.12` public release cutover evidence is captured in a deterministic,
reviewer-verifiable pack. The next planning line is seeded in `v0.6.13-plan.md`;
it is not released or version-bumped. Candidate selection for `v0.6.13` is
governed by `v0.6.13-candidate-selection.md`.

- [v0.6.12 Post-Release Evidence](../releases/v0.6.12-post-release-evidence.md) — deterministic cutover evidence and canonical public record
- [v0.6.13 Planning Seed](../releases/v0.6.13-plan.md) — non-committal next-line planning notes
- [v0.6.13 Candidate Selection](../releases/v0.6.13-candidate-selection.md) — planning-only candidate-selection gate

## Release Assurance

Release assurance is available locally and through a manual CI workflow. It
checks release identity, updater delivery, provider evidence, checksums, and
safety non-claims without publishing packages or changing runtime behavior.
Generated assurance and audit packs are local evidence unless a task explicitly
requires a versioned evidence pack.

- [Release Readiness](../security/release-readiness.md)
- [Release Assurance Bundle Demo](../security/release-assurance-bundle-demo.md)
- [Release Assurance Workflow Dispatch](../security/release-assurance-workflow-dispatch.md) — how to dispatch, download, and validate the optional `run_bundle_demo` artifact
- [Release Assurance CI Workflow](../../.github/workflows/release-assurance.yml)
- [Generated Artifacts](../development/generated-artifacts.md)
- [GitHub Actions Maintenance](../development/github-actions.md)
- [Main Health Report](../development/main-health.md)

## Auto-Updater Delivery

Auto-updater delivery for `v0.6.12` is verified against the GitHub release/tag.
Auto-updater delivery for `v0.6.11` remains verified.
The updater verification does not install packages, call providers, touch
brokers, enable trading, or require credentials.

## Distribution Status

- GitHub release: `v0.6.12` (current public)
- GitHub release: `v0.6.11` (historical)
- Tag: `v0.6.12` (created and pushed)
- Tag: `v0.6.11` (historical)
- PyPI was not published
- Package version in source metadata: `0.6.12`
- Auto-updater delivery: verified for `v0.6.12`; verified for `v0.6.11`

## What Is Ready

- Public v0.6.12 release notes and release status documentation (current public).
- Public v0.6.11 release notes and release status documentation (historical).
- Public v0.6.10 release notes and release status documentation (historical).
- Public v0.6.9 release notes and release status documentation (historical).
- Local and CI release assurance generation.
- Local and CI provider audit pack generation and verification.
- Deterministic local backtesting and paper-first workflows.
- Read-only dashboard security documentation.
- Approval safety documentation and tests.

## What Is Not Ready

- PyPI was not published for `v0.6.1`, `v0.6.2`, `v0.6.3`, `v0.6.4`, `v0.6.5`, `v0.6.6`, `v0.6.7`, `v0.6.8`, `v0.6.9`, `v0.6.10`, `v0.6.11`, or `v0.6.12`.
- `v0.6.13` is the next planning line and is not yet implemented or released.
- Live trading is not enabled by default and requires explicit local operator
  configuration.
- Live submit is not enabled by default.
- Provider execution is not enabled by default.
- Broker execution is not enabled by default.
- Telegram/remote approval is not enabled by default.
- External security review is still recommended before funded use.

## Reviewer Entry Points

- [Contributor Onboarding](../development/onboarding.md)
- [Safe Local Workflows](../development/safe-local-workflows.md)
- [Generated Artifacts](../development/generated-artifacts.md)
- [Main Health Report](../development/main-health.md)
- [Checks Reference](../development/checks-reference.md)
- [v0.6.12 Release Notes](../releases/v0.6.12.md) (current public)
- [v0.6.12 Trust and Release Status](v0.6.12-status.md) (current public)
- [v0.6.11 Release Notes](../releases/v0.6.11.md) (historical)
- [v0.6.11 Trust and Release Status](v0.6.11-status.md) (historical)
- [v0.6.10 Release Notes](../releases/v0.6.10.md) (historical)
- [v0.6.10 Trust and Release Status](v0.6.10-status.md) (historical)
- [v0.6.9 Release Notes](../releases/v0.6.9.md) (historical)
- [v0.6.9 Trust and Release Status](v0.6.9-status.md) (historical)
- [v0.6.8 Release Notes](../releases/v0.6.8.md) (historical)
- [v0.6.8 Trust and Release Status](v0.6.8-status.md) (historical)
- [v0.6.7 Release Notes](../releases/v0.6.7.md) (historical)
- [v0.6.7 Trust and Release Status](v0.6.7-status.md) (historical)
- [v0.6.5 Release Notes](../releases/v0.6.5.md) (historical)
- [v0.6.5 Trust and Release Status](v0.6.5-status.md) (historical)
- [v0.6.4 Release Notes](../releases/v0.6.4.md) (historical)
- [v0.6.4 Trust and Release Status](v0.6.4-status.md) (historical)
- [v0.6.3 Release Notes](../releases/v0.6.3.md) (historical)
- [v0.6.3 Trust and Release Status](v0.6.3-status.md) (historical)
- [v0.6.2 Trust and Release Status](v0.6.2-status.md) (historical)
- [v0.6.1 Trust and Release Status (historical)](v0.6.1-status.md)
- [v0.6.0 Trust and Release Status (historical)](v0.6.0-status.md)
- [Reviewer Trust Snapshot](reviewer-trust-snapshot.md) — compact release-identity and safety-posture summary
- [Reviewer Trust Snapshot GitHub Actions Workflow](../../.github/workflows/reviewer-trust-snapshot.yml) — manual, read-only snapshot artifact workflow
- [Release Assurance CI Workflow](../../.github/workflows/release-assurance.yml) — manual release assurance workflow with optional reviewer trust snapshot integration and optional `run_bundle_demo` artifact upload
- [SECURITY.md](../../SECURITY.md)
- [Release Readiness](../security/release-readiness.md)
- [Provider Audit Pack](../security/provider-audit-pack.md)
- [Provider Evidence Index](../security/provider-evidence-index.md)
- [Provider Preflight](../security/provider-preflight.md)
- [Broker Safety](../security/broker-safety.md)
- [Dashboard Security](../security/dashboard-security.md)
- [Approval Safety](../security/approval-safety.md)
- [Provider Audit Pack CI Workflow](../../.github/workflows/provider-audit-pack.yml)
- [Release Assurance CI Workflow](../../.github/workflows/release-assurance.yml)

## Non-Claims

- Autonomous trading is not claimed.
- Financial advice is not claimed; Atlas Agent is not financial advice.
- Live trading readiness is not claimed.
- Production trading readiness is not claimed.
- Profitability, trading correctness, and funded-use suitability are not claimed.
- Provider audit evidence does not authorize provider or broker execution.
