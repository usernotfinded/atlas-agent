# Stable Release Decision — Atlas Agent v0.5.7

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Decision Summary

The Atlas Agent repository is ready to prepare a **stable v0.5.7** release.

This decision is based on the RC series (rc1–rc9) verification and the final RC audit. All release gates pass. No blockers remain. The repository has stable documentation, CI, release process, and public-facing materials.

## What "Stable" Means for v0.5.7

A stable v0.5.7 release means:

- **Documentation stability** — public docs, README, changelogs, and release notes are consistent and complete.
- **Release process stability** — version consistency, CI gates, check scripts, and checklists are aligned and passing.
- **Package stability** — the package builds cleanly, installs without credentials, and passes distribution dry-runs.
- **Public repo readiness** — SECURITY.md, CONTRIBUTING.md, issue templates, PR templates, and reviewer materials are present.
- **Conservative safety posture** — all safety claims remain disabled by default; no live trading enablement; no provider execution unlock.

Stable v0.5.7 refers to **release/documentation/process stability**, not trading performance or market safety.

## What "Stable" Does Not Mean

Stable v0.5.7 **does not** mean:

- Live trading readiness.
- Production trading readiness.
- Real-money safety.
- Profitability or trading correctness.
- Autonomous trading readiness.
- Broker execution approval.
- Provider execution unlock.

Atlas Agent remains a **sandbox/paper/preflight-first** research workbench. Live trading is disabled by default. Provider execution remains locked. Trust remains blocked.

## Evidence from RC Series

The following were verified across rc1–rc9:

- Version consistency maintained across all release candidates.
- README clarity improved with "What this is" and "What this is not" sections.
- Public documentation expanded: launch readiness, reviewer onboarding, launch messaging, feedback guide, public FAQ, final RC audit, and final RC checklist.
- Security policy (`SECURITY.md`) and contribution guide (`CONTRIBUTING.md`) established.
- Issue and PR templates added.
- CI quick gate and release gates aligned between local and GitHub Actions.
- Clean install verification confirmed — no credentials, no network, no broker contact.
- Package distribution dry-run confirmed — wheel and sdist metadata verified.
- Forbidden claims scans clean across all public docs.
- Protected boundaries (config, brokers, execution, safety, risk) unchanged throughout the RC series.
- No runtime behavior changes introduced in any RC batch.

## Release Gates Status

| Gate | Status |
|---|---|
| Version consistency | Pass |
| Forbidden claims scan | Pass |
| Public docs consistency | Pass |
| README quickstart verification | Pass |
| RC cutover check | Pass |
| Clean install dry-run | Pass |
| Package distribution dry-run | Pass |
| Public launch readiness | Pass |
| Reviewer onboarding | Pass |
| Public launch messaging | Pass |
| Final RC audit | Pass |
| Stable release decision | Pass |
| Protected boundaries clean | Pass |
| No staged artifacts | Pass |

## CI Status

- CI quick gate passes on `push` and `pull_request` to `main`.
- Research CI passes on research-path changes.
- Release gate available for manual `workflow_dispatch` and tags.
- No secrets required. No broker/provider credentials. No PyPI upload or GitHub release creation. No git push or tag from CI.

## Clean Install Status

- `check_clean_install.py` passes.
- Installs with `--no-index --no-build-isolation` by default.
- No credentials required. No network enabled by default. No broker contact.

## Package Distribution Status

- Package builds locally.
- Wheel and sdist metadata verified.
- No forbidden claims in metadata.
- `pip check` passes.
- Distribution checks are dry-run only; they do not publish or upload.

## Public Documentation Status

All public docs exist, are cross-linked, and contain safe wording:

- `README.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `docs/public-launch-readiness.md`
- `docs/external-reviewer-walkthrough.md`
- `docs/reviewer-checklist.md`
- `docs/public-launch-messaging.md`
- `docs/feedback-request-guide.md`
- `docs/public-faq.md`
- `docs/final-rc-audit.md`
- `docs/final-release-candidate-checklist.md`
- `docs/stable-release-decision.md`
- `docs/stable-release-checklist.md`
- `docs/release-checklist.md`
- `docs/ci-release-gates.md`

## Security/Contribution Hygiene Status

- `SECURITY.md` present with safe wording.
- `CONTRIBUTING.md` present with safe-by-default design rules.
- Issue templates present (bug, docs, safety, feature).
- PR template present.
- No secrets in templates or hygiene docs.

## Reviewer Onboarding Status

- External reviewer walkthrough and checklist are present.
- README and public launch docs link to reviewer materials.
- Reviewer onboarding script and tests pass.

## Public Launch Messaging Status

- Safe draft messaging exists for GitHub, Reddit, Hacker News, Discord, and direct outreach.
- No invitation to real-money trading.
- No request for credentials.
- Required safety phrases present in all launch docs.

## Known Limitations

- Live trading is disabled by default and requires explicit multi-factor opt-in.
- Provider execution remains locked — no real LLM/provider calls are made by default.
- Research uses deterministic local mock workflows; external providers are not enabled.
- Alpaca is the only live sync adapter; other broker integrations remain beta/deferred.
- The dashboard is read-only and basic.
- Self-improvement is early-stage.
- No third-party security audit has been performed.
- This is a sandbox/paper/preflight release, not a production trading system.

## What Remains Disabled

- Live trading by default.
- Provider execution (real API calls).
- Trust upgrades for provider responses.
- Autonomous order submission.
- Credential auto-loading without explicit configuration.

## Go/No-Go Checklist

- [x] All release gates pass.
- [x] No blockers remain.
- [x] Version cutover to `0.5.7` / `v0.5.7` complete.
- [x] CHANGELOG has stable v0.5.7 entry.
- [x] Release note `docs/releases/v0.5.7.md` exists.
- [x] Stable release decision doc exists.
- [x] Stable release checklist exists.
- [x] Public docs contain no forbidden claims.
- [x] Public docs contain no secret-like fragments.
- [x] Public docs contain no absolute paths.
- [x] Protected boundaries are clean.
- [x] CI quick gate passes.
- [x] Package distribution dry-run passes.

## Recommendation

**Go.** Tag v0.5.7 as a stable public repository release.

This stable release documents the state of the codebase, the release process, and the public-facing materials. It does not claim live trading readiness, profitability, trading correctness, or real-money safety.

Atlas Agent remains a sandbox/paper/preflight-first research workbench. Users should continue to treat it as such.

---

**This document does not claim that v0.5.7 has already been published externally.** It is a decision record to inform the tagging action.
