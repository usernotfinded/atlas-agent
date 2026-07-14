# Atlas Agent Trust Center

This page is the public trust/readiness entry point for Atlas Agent reviewers,
users, contributors, auditors, and potential adopters.

## Current Public Release

- Current public release: `v0.6.26` (tagged)
- Previous public release: `v0.6.25`
- Source package version on `main`: `0.6.26`
- GitHub release: `v0.6.26` (current public)
- Next planning line: `v0.6.27`
- Public v0.6.26: current public — [v0.6.26 Trust and Release Status](v0.6.26-status.md)
- Public v0.6.25: historical — [v0.6.25 Trust and Release Status](v0.6.25-status.md)
- Public v0.6.24: historical — [v0.6.24 Trust and Release Status](v0.6.24-status.md)
- Public v0.6.23: historical — [v0.6.23 Trust and Release Status](v0.6.23-status.md)
- Public v0.6.22: historical — [v0.6.22 Trust and Release Status](v0.6.22-status.md)
- Public v0.6.21: historical — [v0.6.21 Trust and Release Status](v0.6.21-status.md)
- Public v0.6.20: historical — [v0.6.20 Trust and Release Status](v0.6.20-status.md)
- Public v0.6.19: historical — [v0.6.19 Trust and Release Status](v0.6.19-status.md)
- Public v0.6.18: historical — [v0.6.18 Trust and Release Status](v0.6.18-status.md)
- Public v0.6.17: historical — [v0.6.17 Trust and Release Status](v0.6.17-status.md)
- Public v0.6.16: historical — [v0.6.16 Trust and Release Status](v0.6.16-status.md)
- Public v0.6.15: historical — [v0.6.15 Trust and Release Status](v0.6.15-status.md)
- Public v0.6.14: historical — [v0.6.14 Trust and Release Status](v0.6.14-status.md)
- Public v0.6.13: historical — [v0.6.13 Trust and Release Status](v0.6.13-status.md)
- Public v0.6.12: historical — [v0.6.12 Trust and Release Status](v0.6.12-status.md)
- Public v0.6.11: historical — [v0.6.11 Trust and Release Status](v0.6.11-status.md) (historical)
- PyPI was not published
- Current public release status: [v0.6.26 Trust and Release Status](v0.6.26-status.md) (current public)
- Previous release status: [v0.6.25 Trust and Release Status](v0.6.25-status.md) (historical)
- Previous previous release status: [v0.6.24 Trust and Release Status](v0.6.24-status.md) (historical)
- Previous previous release status: [v0.6.23 Trust and Release Status](v0.6.23-status.md) (historical)
- Previous previous previous release status: [v0.6.22 Trust and Release Status](v0.6.22-status.md) (historical)
- Previous previous previous previous release status: [v0.6.18 Trust and Release Status](v0.6.18-status.md) (historical)
- Previous previous previous previous previous release status: [v0.6.17 Trust and Release Status](v0.6.17-status.md) (historical)
- Previous previous previous previous previous previous release status: [v0.6.15 Trust and Release Status](v0.6.15-status.md) (historical)
- Previous previous previous previous previous previous previous release status: [v0.6.11 Trust and Release Status](v0.6.11-status.md) (historical)
- Current public release notes: [docs/releases/v0.6.26.md](../releases/v0.6.26.md) (current public)
- Previous release notes: [docs/releases/v0.6.25.md](../releases/v0.6.25.md) (historical)
- v0.6.11 release notes: [docs/releases/v0.6.11.md](../releases/v0.6.11.md) (historical)
- Previous previous release notes: [docs/releases/v0.6.10.md](../releases/v0.6.10.md) (historical)
- Previous previous previous release notes: [docs/releases/v0.6.9.md](../releases/v0.6.9.md) (historical)
- Previous previous previous previous release notes: [docs/releases/v0.6.8.md](../releases/v0.6.8.md) (historical)
- Previous previous previous previous previous release notes: [docs/releases/v0.6.7.md](../releases/v0.6.7.md) (historical)
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

## v0.6.15 Post-Release Evidence

The `v0.6.15` GitHub-only release cutover evidence is captured in deterministic,
reviewer-verifiable records. The `v0.6.18` release is historical and the next
planning line is seeded in `v0.6.19-plan.md`. PyPI remains unpublished, live
trading remains disabled by default, and provider/broker execution remains locked
behind the existing safety gates.

- [v0.6.15 Post-Release Evidence](../releases/v0.6.15-post-release-evidence.md) — deterministic GitHub-only cutover record (historical)
- [v0.6.15 Paper Human Review Evidence](../releases/v0.6.15-paper-human-review-evidence.md) — historical pre-cutover CAND-001 through CAND-005 evidence
- [v0.6.15 Final Human Review Release-Readiness Audit](../releases/v0.6.15-final-readiness-audit.md) — historical pre-cutover CAND-006 decision dossier
- [v0.6.18 Planning Seed](../releases/v0.6.18-plan.md) — historical planning notes
- [v0.6.19 Planning Seed](../releases/v0.6.19-plan.md) — next-line planning notes

## v0.6.14 Post-Release Evidence

The historical `v0.6.14` release cutover evidence is captured in deterministic,
reviewer-verifiable records. That line is now historical after the `v0.6.15`
public GitHub release cutover.

- [v0.6.14 Post-Release Evidence](../releases/v0.6.14-post-release-evidence.md) — deterministic GitHub-only cutover record (historical)
- [v0.6.14 Paper Portfolio Evidence](../releases/v0.6.14-paper-portfolio-evidence.md) — historical pre-cutover CAND-001 through CAND-007 evidence
- [v0.6.14 Final Paper Portfolio Readiness Audit](../releases/v0.6.14-final-readiness-audit.md) — historical pre-cutover CAND-008 decision dossier

## v0.6.12 Post-Release Evidence

The historical `v0.6.12` release cutover evidence is captured in a deterministic,
reviewer-verifiable pack. That line is now historical after the `v0.6.13`
public GitHub release cutover.

Paper-mode provider isolation is documented in [docs/paper-provider-isolation.md](../paper-provider-isolation.md).
Paper strategy evaluation is documented in [docs/paper-strategy-evaluation.md](../paper-strategy-evaluation.md)
Paper strategy sensitivity is documented in [docs/paper-strategy-sensitivity.md](../paper-strategy-sensitivity.md)
Paper strategy robustness is documented in [docs/paper-strategy-robustness.md](../paper-strategy-robustness.md)
Paper strategy walk-forward stability is documented in [docs/paper-strategy-walk-forward.md](../paper-strategy-walk-forward.md)
Paper strategy scorecard evidence is documented in [docs/paper-strategy-scorecard.md](../paper-strategy-scorecard.md)
Paper portfolio stress constraints are documented in [docs/paper-portfolio-stress.md](../paper-portfolio-stress.md)
The v0.6.13 paper-autonomy closure evidence is documented in
[docs/releases/v0.6.13-paper-autonomy-evidence.md](../releases/v0.6.13-paper-autonomy-evidence.md).

- [v0.6.12 Post-Release Evidence](../releases/v0.6.12-post-release-evidence.md) — deterministic cutover evidence and canonical public record
- [v0.6.13 Planning Seed](../releases/v0.6.13-plan.md) — historical planning notes
- [v0.6.13 Candidate Selection](../releases/v0.6.13-candidate-selection.md) — historical candidate-selection gate
- [v0.6.13 Paper Autonomy Evidence](../releases/v0.6.13-paper-autonomy-evidence.md) — CAND-021 through CAND-029 evidence bundle

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

Auto-updater delivery for `v0.6.26` is verified against the GitHub release/tag.
Auto-updater delivery for `v0.6.25` and earlier remains verified.
The updater verification does not install packages, call providers, touch
brokers, enable trading, or require credentials.

## Distribution Status

- GitHub release: `v0.6.26` (current public)
- GitHub release: `v0.6.25` (historical)
- GitHub release: `v0.6.24` (historical)
- GitHub release: `v0.6.23` (historical)
- GitHub release: `v0.6.22` (historical)
- GitHub release: `v0.6.21` (historical)
- GitHub release: `v0.6.20` (historical)
- GitHub release: `v0.6.18` (historical)
- GitHub release: `v0.6.17` (historical)
- GitHub release: `v0.6.16` (historical)
- GitHub release: `v0.6.15` (historical)
- GitHub release: `v0.6.14` (historical)
- GitHub release: `v0.6.13` (historical)
- GitHub release: `v0.6.11` (historical)
- Tag: `v0.6.26` (current public)
- Tag: `v0.6.25` (historical)
- Tag: `v0.6.24` (historical)
- Tag: `v0.6.23` (historical)
- Tag: `v0.6.22` (historical)
- Tag: `v0.6.21` (historical)
- Tag: `v0.6.20` (historical)
- Tag: `v0.6.18` (historical)
- Tag: `v0.6.17` (historical)
- Tag: `v0.6.16` (historical)
- Tag: `v0.6.15` (historical)
- Tag: `v0.6.14` (historical)
- Tag: `v0.6.13` (historical)
- Tag: `v0.6.11` (historical)
- PyPI was not published
- Package version in source metadata: `0.6.26`
- Auto-updater delivery: verified for `v0.6.26`; verified for `v0.6.25`; verified for `v0.6.23`; verified for `v0.6.22`; verified for `v0.6.21`; verified for `v0.6.20`; verified for `v0.6.19`; verified for `v0.6.18`; verified for `v0.6.17`; verified for `v0.6.16`; verified for `v0.6.15`; verified for `v0.6.14`; verified for `v0.6.13`

## What Is Ready

- Public v0.6.26 release notes and release status documentation (current public).
- Public v0.6.25 release notes and release status documentation (historical).
- Public v0.6.24 release notes and release status documentation (historical).
- Public v0.6.23 release notes and release status documentation (historical).
- Public v0.6.22 release notes and release status documentation (historical).
- Public v0.6.21 release notes and release status documentation (historical).
- Public v0.6.20 release notes and release status documentation (historical).
- Public v0.6.18 release notes and release status documentation (historical).
- Public v0.6.17 release notes and release status documentation (historical).
- Public v0.6.15 release notes and release status documentation (historical).
- Public v0.6.14 release notes and release status documentation (historical).
- Public v0.6.13 release notes and release status documentation (historical).
- Public v0.6.11 release notes and release status documentation (historical).
- Public v0.6.10 release notes and release status documentation (historical).
- Public v0.6.9 release notes and release status documentation (historical).
- Local and CI release assurance generation.
- Local and CI provider audit pack generation and verification.
- Deterministic local backtesting and paper-first workflows.
- Read-only dashboard security documentation.
- Approval safety documentation and tests.
- Bounded autonomy governance documentation (`docs/bounded-live-autonomy-governance.md`)
  and aligned long-term autonomy roadmap (`docs/autonomy-roadmap.md`).
- L1 autonomous paper workflow demo documentation (`docs/autonomous-paper-workflow.md`)
  and evidence gate script (`scripts/demo_autonomous_paper_workflow.sh`) — paper-only, offline, no credentials.
- Paper strategy evaluation documentation (`docs/paper-strategy-evaluation.md`),
  demo script (`scripts/demo_paper_strategy_evaluation.sh`), and checker
  (`scripts/check_paper_strategy_evaluation.py`) — paper-only, offline, no credentials.
- Paper-autonomy evidence bundle (`docs/releases/v0.6.13-paper-autonomy-evidence.md`
  and `.json`) plus `scripts/check_v0613_paper_autonomy_evidence.py` — planning-only,
  local, and no release side effects.
- Paper human review evidence bundle (`docs/releases/v0.6.15-paper-human-review-evidence.md`
  and `.json`) plus `scripts/check_v0615_paper_human_review_evidence.py` — historical
  pre-cutover evidence, local, and paper-only.
- Final human review release-readiness audit (`docs/releases/v0.6.15-final-readiness-audit.md`
  and `.json`) plus `scripts/check_v0615_final_readiness_audit.py` — historical
  pre-cutover decision evidence.
- Paper portfolio evidence bundle (`docs/releases/v0.6.14-paper-portfolio-evidence.md`
  and `.json`) plus `scripts/check_v0614_paper_portfolio_evidence.py` — historical
  pre-cutover evidence, local, and paper-only.
- Final paper portfolio readiness audit (`docs/releases/v0.6.14-final-readiness-audit.md`
  and `.json`) plus `scripts/check_v0614_final_readiness_audit.py` — historical
  pre-cutover decision evidence.

## What Is Not Ready

- PyPI was not published for `v0.6.1` through `v0.6.26`.
- `v0.6.27` is the next planning line; no candidates are selected.
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
- [v0.6.26 Release Notes](../releases/v0.6.26.md) (current public)
- [v0.6.26 Trust and Release Status](v0.6.26-status.md) (current public)
- [v0.6.25 Release Notes](../releases/v0.6.25.md) (historical)
- [v0.6.25 Trust and Release Status](v0.6.25-status.md) (historical)
- [v0.6.24 Release Notes](../releases/v0.6.24.md) (historical)
- [v0.6.24 Trust and Release Status](v0.6.24-status.md) (historical)
- [v0.6.23 Release Notes](../releases/v0.6.23.md) (historical)
- [v0.6.23 Trust and Release Status](v0.6.23-status.md) (historical)
- [v0.6.22 Release Notes](../releases/v0.6.22.md) (historical)
- [v0.6.22 Trust and Release Status](v0.6.22-status.md) (historical)
- [v0.6.21 Release Notes](../releases/v0.6.21.md) (historical)
- [v0.6.21 Trust and Release Status](v0.6.21-status.md) (historical)
- [v0.6.20 Release Notes](../releases/v0.6.20.md) (historical)
- [v0.6.20 Trust and Release Status](v0.6.20-status.md) (historical)
- [v0.6.17 Release Notes](../releases/v0.6.17.md) (historical)
- [v0.6.17 Trust and Release Status](v0.6.17-status.md) (historical)
- [v0.6.16 Release Notes](../releases/v0.6.16.md) (historical)
- [v0.6.16 Trust and Release Status](v0.6.16-status.md) (historical)
- [v0.6.15 Release Notes](../releases/v0.6.15.md) (historical)
- [v0.6.15 Trust and Release Status](v0.6.15-status.md) (historical)
- [v0.6.14 Release Notes](../releases/v0.6.14.md) (historical)
- [v0.6.14 Trust and Release Status](v0.6.14-status.md) (historical)
- [v0.6.13 Release Notes](../releases/v0.6.13.md) (historical)
- [v0.6.13 Trust and Release Status](v0.6.13-status.md) (historical)
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
