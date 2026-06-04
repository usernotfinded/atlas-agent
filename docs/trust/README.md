# Atlas Agent Trust Center

This page is the public trust/readiness entry point for Atlas Agent reviewers,
users, contributors, auditors, and potential adopters.

## Current Public Release

- Current public release: `v0.5.9`
- Source package version on `main`: `0.5.9.3`
- GitHub release: `v0.5.9`
- PyPI publish: not performed
- Maintenance label `v0.5.9.3`: not tagged or released
- Release status detail: [v0.5.9 Trust and Release Status](v0.5.9-status.md)
- Release notes: [docs/releases/v0.5.9.md](../releases/v0.5.9.md)

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

## Release Assurance

Release assurance is available locally and through a manual CI workflow. It
checks release identity, updater delivery, provider evidence, checksums, and
safety non-claims without publishing packages or changing runtime behavior.
Generated assurance and audit packs are local evidence unless a task explicitly
requires a versioned evidence pack.

- [Release Readiness](../security/release-readiness.md)
- [Release Assurance CI Workflow](../../.github/workflows/release-assurance.yml)
- [Generated Artifacts](../development/generated-artifacts.md)
- [Main Health Report](../development/main-health.md)

## Auto-Updater Delivery

Auto-updater delivery for `v0.5.9` is verified against the GitHub release/tag.
The updater verification does not install packages, call providers, touch
brokers, enable trading, or require credentials.

## Distribution Status

- GitHub release: `v0.5.9`
- PyPI publish: not performed
- Package version in source metadata: `0.5.9.3`
- Auto-updater delivery: verified

## What Is Ready

- Public v0.5.9 release notes and release status documentation.
- Local and CI release assurance generation.
- Local and CI provider audit pack generation and verification.
- Deterministic local backtesting and paper-first workflows.
- Read-only dashboard security documentation.
- Approval safety documentation and tests.

## What Is Not Ready

- PyPI was not published for `v0.5.9`.
- No `v0.5.9.3` tag or GitHub release has been created.
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
- [v0.5.9 Release Notes](../releases/v0.5.9.md)
- [v0.5.9 Trust and Release Status](v0.5.9-status.md)
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
