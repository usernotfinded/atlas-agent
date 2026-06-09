# Reviewer Outreach Checklist

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.
>
> Atlas is **not a live trading product** by default. **Live trading is disabled by default.** **Provider execution remains locked.** **Broker execution remains blocked** unless explicit opt-in gates pass. Atlas is **not production ready** for unattended or real-money trading. Atlas does not guarantee profitability or trading correctness.

Use this checklist before starting controlled reviewer outreach.

## Repository state

- [ ] `main` source version is `0.6.6` and the public GitHub release is `v0.6.6`.
- [ ] Historical tags remain untouched (no tag recreation or force-push).
- [ ] Working tree is clean or only contains intentional changes.
- [ ] No protected boundary changes staged (`git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk`).

## Deterministic checks

- [ ] `./scripts/release_check.sh --quick` passes.
- [ ] `python3.11 scripts/smoke_reviewer_golden_path.py --json --skip-release-check` passes.
- [ ] `python3.11 scripts/build_release_evidence_bundle.py --skip-slow` passes.
- [ ] `python3.11 scripts/check_feedback_intake.py` passes.
- [ ] `python3.11 scripts/check_feedback_taxonomy.py` passes.
- [ ] `python3.11 scripts/check_reviewer_outreach.py` passes.

## Safety scans

- [ ] `python3.11 scripts/check_forbidden_claims.py` passes (no unsafe claims in docs).
- [ ] `python3.11 scripts/check_public_docs_consistency.py` passes.
- [ ] `python3.11 scripts/check_public_launch_readiness.py` passes.
- [ ] `python3.11 scripts/check_stable_release_decision.py` passes.
- [ ] No secrets or credential-like strings in outreach docs or templates.
- [ ] No absolute user paths in outreach docs or templates.

## Feedback infrastructure

- [ ] Issue templates present in `.github/ISSUE_TEMPLATE/`.
- [ ] Label taxonomy present in `.github/labels.yml`.
- [ ] Triage docs present (`docs/feedback-triage-taxonomy.md`).
- [ ] Intake docs present (`docs/feedback-intake-process.md`).
- [ ] Outreach docs present (`docs/controlled-reviewer-outreach.md`).

## README and messaging

- [ ] README current status is clear (`v0.6.6` latest stable; `v0.6.5` is historical).
- [ ] README links to reviewer walkthrough, checklist, and outreach docs.
- [ ] Outreach message drafts do not claim profitability, live readiness, or production safety.
- [ ] Outreach message drafts do not invite broker setup, credential sharing, or live trading.

## Evidence artifacts

- [ ] No generated evidence artifacts are staged (`artifacts/release_evidence/`, `build/`, `dist/`, `*.egg-info/`).
- [ ] No runtime files staged (`memory/`, `.atlas/`, `.env`, `.env.atlas`).
- [ ] `python3.11 scripts/check_no_protected_staged.py` passes.

## Outreach plan

- [ ] Target reviewer count is 5–10 (controlled, small-scale).
- [ ] `docs/reviewer-targets-template.md` is updated with planned reviewers (no real personal data).
- [ ] Each reviewer is sent the safe review path and the external reviewer walkthrough.
- [ ] Reviewers understand that live trading, broker setup, and credential sharing are out of scope.

## Rollback plan

- [ ] If a safety concern is reported, outreach is paused immediately.
- [ ] The concern is triaged using the safety-sensitive path.
- [ ] Outreach resumes only after the concern is fixed and the release check passes.

## Final sign-off

- [ ] All checks above pass.
- [ ] Outreach pack is committed to `main`.
- [ ] No tag, release, or publish actions are performed.
