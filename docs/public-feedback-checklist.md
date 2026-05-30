# Public Feedback Checklist

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

Use this checklist before opening the repo for broader public feedback or outreach.

## Repository state

- [ ] `README.md` current development status is clear (post-v0.5.7 development, `0.5.8rc2`).
- [ ] `CHANGELOG.md` has an `[Unreleased]` section.
- [ ] `v0.5.7` tag exists and is untouched.
- [ ] No forbidden claims in public docs.

## Deterministic checks

- [ ] `python3.11 scripts/smoke_reviewer_golden_path.py` passes.
- [ ] `python3.11 scripts/build_release_evidence_bundle.py --skip-slow` passes.
- [ ] `python3.11 scripts/check_cli_command_compatibility.py` passes.
- [ ] `python3.11 scripts/check_forbidden_claims.py` passes.
- [ ] `python3.11 scripts/check_public_docs_consistency.py` passes.

## Issue templates

- [ ] `.github/ISSUE_TEMPLATE/reviewer_feedback.yml` exists.
- [ ] `.github/ISSUE_TEMPLATE/bug_report.yml` exists.
- [ ] `.github/ISSUE_TEMPLATE/docs_issue.yml` exists.
- [ ] `.github/ISSUE_TEMPLATE/safety_concern.yml` exists.
- [ ] `.github/ISSUE_TEMPLATE/feature_request.yml` exists.
- [ ] `.github/ISSUE_TEMPLATE/config.yml` exists and points to Security Advisories.

## Safety warnings in templates

- [ ] Reviewer feedback template says "do not paste credentials."
- [ ] Reviewer feedback template says "do not ask for real-money broker setup."
- [ ] Reviewer feedback template says "do not ask to bypass safety gates."
- [ ] Reviewer feedback template says "do not request profit/trading signal evaluation."
- [ ] Reviewer feedback template says "do not request live trading enablement by default."
- [ ] All templates include a "not financial advice" disclaimer.

## Generated artifacts

- [ ] No `artifacts/release_evidence/` files are staged.
- [ ] No `build/`, `dist/`, or `*.egg-info/` directories are staged.
- [ ] No `.env` or `.env.atlas` files are staged.

## Secrets and paths

- [ ] No secrets or credential-like strings in public docs or templates.
- [ ] No absolute user paths (`/Users/`, `/private/var/`) in public docs or templates.

## Live trading and profitability claims

- [ ] No docs claim live trading is ready for unattended deployment.
- [ ] No docs understate trading risk or imply profitability.
- [ ] No docs claim provider execution is unlocked by default.
- [ ] No docs claim broker execution is enabled by default.

## Protected boundaries

```bash
git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
git diff --cached -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
```

- [ ] No unprotected boundary changes, or changes are explicitly justified.

## Final sign-off

- [ ] `git diff --check` passes.
- [ ] `./scripts/release_check.sh --quick` passes.
