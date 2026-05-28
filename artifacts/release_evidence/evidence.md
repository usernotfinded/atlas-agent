# Release Evidence Bundle

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Summary

- **Overall status:** PASSED
- **Generated at:** 2026-05-28T18:41:29.714317+00:00
- **Package version:** 0.5.8.dev0
- **Public stable tag:** v0.5.7
- **Current branch:** main
- **Current commit:** `1377744fb196bef2ae5e85b2fbff9f5572cd5ceb`
- **Working tree clean:** False
- **Diff check clean:** True
- **Protected boundaries clean:** False

## Evidence Checks

| Check | Exit Code | Passed |
|-------|-----------|--------|
| check_version_consistency | 0 | ✓ |
| check_forbidden_claims | 0 | ✓ |
| check_public_docs_consistency | 0 | ✓ |
| check_public_launch_readiness | 0 | ✓ |
| check_stable_release_decision | 0 | ✓ |
| check_cli_command_compatibility | 0 | ✓ |
| smoke_reviewer_golden_path | 0 | ✓ |
| release_check_quick | 0 | ✓ |

## Changed Files Since v0.5.7

```
M	.github/workflows/ci.yml
M	CHANGELOG.md
M	README.md
A	docs/cli-command-compatibility.md
M	docs/feedback-request-guide.md
M	docs/final-rc-audit.md
M	docs/package-distribution-verification.md
M	docs/public-faq.md
M	docs/public-launch-messaging.md
M	docs/public-launch-readiness.md
M	docs/release-checklist.md
A	docs/release-evidence-bundle.md
A	docs/reviewer-golden-path.md
M	pyproject.toml
A	scripts/build_release_evidence_bundle.py
A	scripts/check_cli_command_compatibility.py
M	scripts/check_public_docs_consistency.py
M	scripts/check_public_launch_messaging.py
M	scripts/check_public_launch_readiness.py
M	scripts/check_stable_release_decision.py
M	scripts/check_version_consistency.py
M	scripts/ci_check.sh
M	scripts/dev_check.sh
M	scripts/release_check.sh
A	scripts/smoke_reviewer_golden_path.py
M	src/atlas_agent/__init__.py
M	src/atlas_agent/cli.py
M	src/atlas_agent/cli_commands/__init__.py
A	src/atlas_agent/cli_commands/demo.py
A	src/atlas_agent/cli_commands/deploy.py
A	src/atlas_agent/cli_commands/events.py
M	src/atlas_agent/cli_commands/memory.py
A	src/atlas_agent/cli_commands/risk.py
A	src/atlas_agent/cli_commands/update.py
A	src/atlas_agent/cli_commands/workspace.py
A	src/atlas_agent/cli_io.py
A	src/atlas_agent/cli_safety.py
M	src/atlas_agent/config/schema.py
M	src/atlas_agent/events/log.py
M	src/atlas_agent/execution/audit.py
A	src/atlas_agent/research/artifact_store.py
A	src/atlas_agent/research/command_specs.py
A	src/atlas_agent/research/errors.py
M	src/atlas_agent/research/session.py
A	tests/fixtures/cli_command_contract.json
M	tests/research/test_research_sandbox_cli.py
A	tests/test_cli_command_compatibility.py
M	tests/test_output_safety.py
M	tests/test_public_launch_messaging.py
M	tests/test_public_launch_readiness.py
A	tests/test_release_evidence_bundle.py
A	tests/test_reviewer_golden_path_smoke.py
M	tests/test_stable_release_decision.py
```

## Protected Boundary Status

- **src/atlas_agent/config**: ✗
  - `M	src/atlas_agent/config/schema.py`
- **src/atlas_agent/brokers**: ✓
- **src/atlas_agent/execution**: ✗
  - `M	src/atlas_agent/execution/audit.py`
- **src/atlas_agent/safety**: ✓
- **src/atlas_agent/risk**: ✓

## Safety Summary

- Provider execution enabled: False
- Broker execution enabled: False
- Live trading enabled by default: False
- Credentials loaded: False
- Network calls required: False

## Reviewer Notes

- This bundle is a local-only snapshot. It does not prove trading safety, profitability, or readiness for unattended deployment.
- Live trading remains disabled by default.
- Provider execution remains locked unless explicit manual unlock steps are completed.
- Broker execution remains blocked unless explicit opt-in gates pass.

## Non-Goals

- This bundle does not replace the full release checklist (`docs/release-checklist.md`).
- It does not execute provider calls, broker sync, or order submission.
- It does not load API keys or secrets.
