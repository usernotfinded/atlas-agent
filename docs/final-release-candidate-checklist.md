# Final Release Candidate Checklist

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

Use this checklist to decide whether the repo should move from `rc9` toward a stable `v0.5.7` final release. If the stable release has already been decided, see `docs/stable-release-checklist.md` for the pre-tag checklist and `docs/stable-release-decision.md` for the decision rationale.

A stable `v0.5.7` release means documentation/release/process stability, not trading profitability or real-money safety.

---

## Version Consistency

- [ ] `pyproject.toml` version is `0.5.7`
- [ ] `src/atlas_agent/__init__.py` `__version__` is `0.5.7`
- [ ] README current status references `v0.5.7`
- [ ] CHANGELOG has `[0.5.7rc9]` entry
- [ ] Release note `docs/releases/v0.5.7-rc9.md` exists

**Command:**
```bash
python3.11 scripts/check_version_consistency.py
```

---

## README Clarity

- [ ] "What this is" section present
- [ ] "What this is not" section present
- [ ] Links to SECURITY.md, CONTRIBUTING.md, changelog, release notes
- [ ] No forbidden claims (live trading readiness, profitability, autonomous trading, etc.)

**Command:**
```bash
python3.11 scripts/verify_readme_quickstart.py
```

---

## Documentation Navigation

- [ ] Final RC audit doc (`docs/final-rc-audit.md`) exists
- [ ] Final release candidate checklist (`docs/final-release-candidate-checklist.md`) exists
- [ ] Public launch readiness doc exists
- [ ] External reviewer walkthrough exists
- [ ] Reviewer checklist exists
- [ ] Public launch messaging doc exists
- [ ] Feedback request guide exists
- [ ] Public FAQ exists
- [ ] All docs cross-linked where appropriate

---

## Security Policy

- [ ] `SECURITY.md` exists and contains safe wording
- [ ] GitHub Security Advisories link present

---

## Contribution Guide

- [ ] `CONTRIBUTING.md` exists and contains safe-by-default design rules
- [ ] No forbidden claims in contribution guide

---

## Issue/PR Templates

- [ ] `.github/ISSUE_TEMPLATE/bug_report.yml` exists
- [ ] `.github/ISSUE_TEMPLATE/docs_issue.yml` exists
- [ ] `.github/ISSUE_TEMPLATE/safety_concern.yml` exists
- [ ] `.github/ISSUE_TEMPLATE/feature_request.yml` exists
- [ ] `.github/ISSUE_TEMPLATE/config.yml` exists
- [ ] `.github/pull_request_template.md` exists
- [ ] No secrets or credential examples in templates

---

## Reviewer Onboarding

- [ ] `docs/external-reviewer-walkthrough.md` exists
- [ ] `docs/reviewer-checklist.md` exists
- [ ] README links to reviewer materials
- [ ] `scripts/check_reviewer_onboarding.py` passes
- [ ] `tests/test_reviewer_onboarding.py` passes

**Commands:**
```bash
python3.11 scripts/check_reviewer_onboarding.py
python3.11 -m pytest tests/test_reviewer_onboarding.py -q
```

---

## Public Launch Messaging

- [ ] `docs/public-launch-messaging.md` exists
- [ ] `docs/feedback-request-guide.md` exists
- [ ] `docs/public-faq.md` exists
- [ ] `scripts/check_public_launch_messaging.py` passes
- [ ] `tests/test_public_launch_messaging.py` passes

**Commands:**
```bash
python3.11 scripts/check_public_launch_messaging.py
python3.11 -m pytest tests/test_public_launch_messaging.py -q
```

---

## Public FAQ

- [ ] `docs/public-faq.md` exists
- [ ] Answers common questions conservatively
- [ ] Required safety phrases present (live trading disabled by default, not financial advice, etc.)

---

## Clean Install

- [ ] `scripts/check_clean_install.py --dry-run` passes
- [ ] `scripts/check_clean_install.py` passes
- [ ] No credentials required
- [ ] No network enabled by default

**Commands:**
```bash
python3.11 scripts/check_clean_install.py --dry-run
python3.11 scripts/check_clean_install.py
```

---

## Package Distribution Dry-Run

- [ ] `scripts/check_package_distribution.py --dry-run` passes
- [ ] `scripts/check_package_distribution.py` passes
- [ ] Wheel and sdist metadata correct
- [ ] No forbidden claims in metadata
- [ ] No package artifacts staged

**Commands:**
```bash
python3.11 scripts/check_package_distribution.py --dry-run
python3.11 scripts/check_package_distribution.py
```

---

## CI Quick Gate

- [ ] `scripts/ci_check.sh` passes locally
- [ ] `.github/workflows/ci.yml` includes all required checks
- [ ] No secrets required in CI
- [ ] No publish/upload/tag/push in CI

**Commands:**
```bash
./scripts/ci_check.sh
python3.11 -m pytest tests/test_ci_workflows.py -q
```

---

## Manual Heavy Release Gate

- [ ] `./scripts/release_check.sh --quick` passes
- [ ] `./scripts/release_check.sh --research` passes
- [ ] `./scripts/release_check.sh --full` passes

**Commands:**
```bash
./scripts/release_check.sh --quick
./scripts/release_check.sh --research
./scripts/release_check.sh --full
```

---

## Research Safety Gates

- [ ] Research tests pass
- [ ] Demo research workflow passes
- [ ] No real provider calls made

**Commands:**
```bash
python3.11 -m pytest tests/research -q
python3.11 -m pytest tests/test_demo_research_workflow_script.py -q
./scripts/demo_research_workflow.sh
```

---

## Protected Boundaries

- [ ] No changes to `src/atlas_agent/config`
- [ ] No changes to `src/atlas_agent/brokers`
- [ ] No changes to `src/atlas_agent/execution`
- [ ] No changes to `src/atlas_agent/safety`
- [ ] No changes to `src/atlas_agent/risk`

**Commands:**
```bash
git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
git diff --cached -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
```

Expected: no output.

---

## Forbidden Claims

- [ ] No live trading readiness claims
- [ ] No profitability claims
- [ ] No autonomous trading readiness claims
- [ ] No production trading readiness claims

**Command:**
```bash
python3.11 scripts/check_forbidden_claims.py
```

---

## Secret/Path Leaks

- [ ] No user home paths in public docs
- [ ] No system temp paths in public docs
- [ ] No secret-like fragments (sk-, Bearer, APCA, etc.) in public docs

**Command:**
```bash
python3.11 scripts/check_public_docs_consistency.py
```

---

## Package Artifacts

- [ ] `dist/` not staged
- [ ] `build/` not staged
- [ ] `*.egg-info/` not staged

**Commands:**
```bash
git diff --cached --name-status
find . -maxdepth 2 \( -name "dist" -o -name "build" -o -name "*.egg-info" \) -print
```

---

## Final RC Audit

- [ ] `docs/final-rc-audit.md` exists
- [ ] `docs/final-release-candidate-checklist.md` exists
- [ ] `scripts/check_final_rc_audit.py` passes
- [ ] `tests/test_final_rc_audit.py` passes

**Commands:**
```bash
python3.11 scripts/check_final_rc_audit.py
python3.11 scripts/check_final_rc_audit.py --json
python3.11 -m pytest tests/test_final_rc_audit.py -q
```

---

## Known Limitations

- [ ] Known limitations documented in final RC audit
- [ ] What remains disabled documented clearly
- [ ] No claim that stable release implies live trading readiness

---

## Final Go/No-Go Decision

- [ ] All checklist items above pass
- [ ] No blockers remain
- [ ] Release manager approves

If all items pass, the repo may be ready to prepare a stable `v0.5.7` release plan. If any item fails, document the blocker and decide whether an `rc10` is needed.

**Remember:** A stable `v0.5.7` release means documentation/release/process stability. It does not imply trading profitability, real-money safety, or production trading readiness.
