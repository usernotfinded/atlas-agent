# Stable Release Checklist — v0.5.8

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

Use this checklist to verify the repo is ready before committing/tagging stable **v0.5.8**.

Stable v0.5.8 means documentation/release/process stability, not trading profitability or real-money safety.

---

## Version Cutover

- [ ] `pyproject.toml` version is `0.5.8`
- [ ] `src/atlas_agent/__init__.py` `__version__` is `0.5.8`
- [ ] README current status references `v0.5.8`
- [ ] CHANGELOG has `[0.5.8]` entry
- [ ] Release note `docs/releases/v0.5.8.md` exists

**Command:**
```bash
python3.11 scripts/check_version_consistency.py
```

---

## README Status

- [ ] "What this is" section present
- [ ] "What this is not" section present
- [ ] Links to SECURITY.md, CONTRIBUTING.md, changelog, release notes
- [ ] No forbidden claims (live trading readiness, profitability, autonomous trading, etc.)

**Command:**
```bash
python3.11 scripts/verify_readme_quickstart.py
```

---

## Changelog

- [ ] `[0.5.8]` entry present
- [ ] Mentions stable release decision docs/checks
- [ ] Mentions no runtime behavior changes
- [ ] Historical rc1-rc5 entries preserved

---

## Release Note

- [ ] `docs/releases/v0.5.8.md` exists
- [ ] Contains safe wording
- [ ] No forbidden claims

---

## Public Docs Consistency

- [ ] All public docs exist and are safe
- [ ] No stale current-version references
- [ ] `docs/stable-release-decision.md` exists
- [ ] `docs/stable-release-checklist.md` exists
- [ ] `docs/final-rc-audit.md` exists
- [ ] `docs/final-release-candidate-checklist.md` exists

**Command:**
```bash
python3.11 scripts/check_public_docs_consistency.py
```

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

## Security/Contributing/Templates

- [ ] `SECURITY.md` present
- [ ] `CONTRIBUTING.md` present
- [ ] Issue templates present
- [ ] PR template present
- [ ] No secrets in templates

---

## Reviewer Onboarding

- [ ] Walkthrough and checklist exist
- [ ] README links to reviewer materials
- [ ] Script and tests pass

**Commands:**
```bash
python3.11 scripts/check_reviewer_onboarding.py
python3.11 -m pytest tests/test_reviewer_onboarding.py -q
```

---

## Launch Messaging

- [ ] Launch messaging doc exists
- [ ] Feedback guide exists
- [ ] Public FAQ exists
- [ ] Script and tests pass

**Commands:**
```bash
python3.11 scripts/check_public_launch_messaging.py
python3.11 -m pytest tests/test_public_launch_messaging.py -q
```

---

## Clean Install

- [ ] `check_clean_install.py` passes
- [ ] No credentials required
- [ ] No network enabled by default

**Commands:**
```bash
python3.11 scripts/check_clean_install.py --dry-run
python3.11 scripts/check_clean_install.py
```

---

## Package Distribution

- [ ] `check_package_distribution.py` passes
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

## Research Tests

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

## Artifact Hygiene

- [ ] `dist/` not staged
- [ ] `build/` not staged
- [ ] `*.egg-info/` not staged

**Commands:**
```bash
git diff --cached --name-status
find . -maxdepth 2 \( -name "dist" -o -name "build" -o -name "*.egg-info" \) -print
```

---

## Final Tag Readiness

- [ ] All checklist items above pass
- [ ] No blockers remain
- [ ] Release manager approves

If all items pass, the repo is ready to tag `v0.5.8` as a stable public repository release.

**Remember:** Stable v0.5.8 means documentation/release/process stability. It does not imply trading profitability, real-money safety, or production trading readiness.
