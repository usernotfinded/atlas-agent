# Release Evidence Bundle

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Summary

- **Overall status:** PASSED
- **Generated at:** 2026-06-05T06:15:34.667858+00:00
- **Package version:** 0.5.9.5
- **Public stable tag:** v0.5.8.1
- **Current branch:** main
- **Current commit:** `25d3a127e7a17a60b45be1658ca0431d404dfa70`
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

## Changed Files Since v0.5.8

```
A	.antigravitycli/e5a2f704-d460-434f-829e-9bd713ffb828.json
A	.atlas_update_state.json
M	.env.example
M	.github/workflows/atlas-routines.yml
M	.github/workflows/ci.yml
A	.github/workflows/full-test.yml
A	.github/workflows/provider-audit-pack.yml
A	.github/workflows/release-assurance.yml
M	.github/workflows/release-gate.yml
M	.github/workflows/research-ci.yml
M	.gitignore
M	CHANGELOG.md
M	CONTRIBUTING.md
M	README.md
M	SECURITY.md
A	artifacts/release_assurance/v0.5.9-local-check/provider-audit-pack-checks.json
A	artifacts/release_assurance/v0.5.9-local-check/public-metadata-checks.json
A	artifacts/release_assurance/v0.5.9-local-check/release-assurance-report.md
A	artifacts/release_assurance/v0.5.9-local-check/release-assurance-summary.json
A	artifacts/release_assurance/v0.5.9-local-check/release-checks.json
A	artifacts/release_assurance/v0.5.9-local-check/sha256sums.txt
A	artifacts/release_assurance/v0.5.9-local-check/updater-delivery-checks.json
A	artifacts/release_assurance/v0.5.9.5-local-check/provider-audit-pack-checks.json
A	artifacts/release_assurance/v0.5.9.5-local-check/public-metadata-checks.json
A	artifacts/release_assurance/v0.5.9.5-local-check/release-assurance-report.md
A	artifacts/release_assurance/v0.5.9.5-local-check/release-assurance-summary.json
A	artifacts/release_assurance/v0.5.9.5-local-check/release-checks.json
A	artifacts/release_assurance/v0.5.9.5-local-check/sha256sums.txt
A	artifacts/release_assurance/v0.5.9.5-local-check/updater-delivery-checks.json
A	artifacts/release_assurance/v0.5.9/provider-audit-pack-checks.json
A	artifacts/release_assurance/v0.5.9/public-metadata-checks.json
A	artifacts/release_assurance/v0.5.9/release-assurance-report.md
A	artifacts/release_assurance/v0.5.9/release-assurance-summary.json
A	artifacts/release_assurance/v0.5.9/release-checks.json
A	artifacts/release_assurance/v0.5.9/sha256sums.txt
A	artifacts/release_assurance/v0.5.9/updater-delivery-checks.json
M	artifacts/release_evidence/evidence.json
M	artifacts/release_evidence/evidence.md
A	bump.py
A	docs/audits/batch-7-post-incident-audit.md
M	docs/cli-command-compatibility.md
A	docs/demo/provider-preflight-demo.md
A	docs/development/checks-reference.md
A	docs/development/generated-artifacts.md
A	docs/development/github-actions.md
A	docs/development/main-health.md
A	docs/development/onboarding.md
A	docs/development/safe-local-workflows.md
M	docs/kill-switch.md
M	docs/live-submit-safety-contract.md
M	docs/product-capability-inventory.md
M	docs/public-launch-readiness.md
M	docs/release-checklist.md
A	docs/releases/v0.5.9.4.md
A	docs/releases/v0.5.9.5.md
A	docs/releases/v0.5.9.md
M	docs/reviewer-outreach-checklist.md
A	docs/security/approval-safety.md
A	docs/security/broker-safety.md
A	docs/security/dashboard-security.md
A	docs/security/live-trading.md
A	docs/security/provider-audit-pack.md
A	docs/security/provider-evidence-index.md
M	docs/security/provider-execution-policy.md
M	docs/security/provider-integration-requirements.md
A	docs/security/provider-preflight.md
A	docs/security/provider-readiness.md
A	docs/security/release-readiness.md
A	docs/trust/README.md
A	docs/trust/v0.5.9-status.md
A	docs/trust/v0.5.9.4-status.md
A	docs/trust/v0.5.9.5-status.md
A	patch_sources.py
M	pyproject.toml
M	scripts/build_release_evidence_bundle.py
M	scripts/check_clean_install.py
M	scripts/check_final_rc_audit.py
A	scripts/check_generated_artifacts.py
A	scripts/check_github_actions_versions.py
A	scripts/check_onboarding_docs.py
M	scripts/check_package_distribution.py
M	scripts/check_public_docs_consistency.py
M	scripts/check_public_launch_messaging.py
M	scripts/check_public_launch_readiness.py
M	scripts/check_rc1_cutover.py
M	scripts/check_reviewer_onboarding.py
M	scripts/check_stable_release_decision.py
A	scripts/check_submit_execution_safety.py
A	scripts/check_trust_center.py
M	scripts/check_v0581_hotfix_cutover.py
M	scripts/check_v058_rc1_readiness.py
M	scripts/check_version_consistency.py
M	scripts/ci_check.sh
M	scripts/demo_paper_workflow.sh
M	scripts/demo_research_workflow.sh
M	scripts/dev_check.sh
A	scripts/doctor.py
A	scripts/main_health.py
A	scripts/python_env.sh
A	scripts/release_assurance.py
M	scripts/release_check.sh
M	scripts/research_check.sh
M	src/atlas_agent/__init__.py
M	src/atlas_agent/brokers/alpaca.py
M	src/atlas_agent/cli.py
M	src/atlas_agent/config/schema.py
M	src/atlas_agent/config/secrets.py
M	src/atlas_agent/execution/approval.py
M	src/atlas_agent/providers/openrouter.py
A	src/atlas_agent/providers/provider_audit_pack.py
A	src/atlas_agent/providers/provider_evidence_index.py
A	src/atlas_agent/providers/provider_preflight.py
A	src/atlas_agent/providers/provider_readiness.py
M	src/atlas_agent/research/release_candidate_cutover.py
M	src/atlas_agent/research/release_candidate_readiness.py
M	src/atlas_agent/risk/limits.py
M	src/atlas_agent/templates/routine-trader/configs/risk.example.yaml
M	src/atlas_agent/update/sources.py
M	tests/brokers/test_alpaca_submit.py
M	tests/brokers/test_alpaca_sync.py
A	tests/config/test_config_store.py
A	tests/execution/test_approval_safety.py
M	tests/execution/test_pending_order_schema.py
M	tests/execution/test_submit_approved_order_dry_run.py
M	tests/execution/test_submit_execution.py
M	tests/execution/test_submit_reconcile.py
M	tests/execution/test_submit_state.py
M	tests/fixtures/cli_command_contract.json
M	tests/fixtures/product_capability_inventory.json
M	tests/research/test_release_candidate_cutover_dry_run.py
M	tests/research/test_research_output_safety.py
A	tests/test_approval_integrity.py
A	tests/test_broker_alpaca.py
M	tests/test_ci_workflows.py
M	tests/test_cli.py
M	tests/test_cli_command_compatibility.py
A	tests/test_doctor.py
M	tests/test_final_rc_audit.py
A	tests/test_generated_artifacts.py
A	tests/test_github_actions_versions.py
A	tests/test_kill_switch_drift.py
A	tests/test_live_path_safety_assertions.py
A	tests/test_main_health.py
A	tests/test_onboarding_docs.py
M	tests/test_output_safety.py
M	tests/test_package_distribution_check.py
M	tests/test_permission_hardening.py
M	tests/test_product_capability_inventory.py
M	tests/test_provider_adapters.py
A	tests/test_provider_audit_pack.py
A	tests/test_provider_audit_pack_verifier.py
A	tests/test_provider_evidence_index.py
A	tests/test_provider_evidence_report.py
A	tests/test_provider_preflight.py
A	tests/test_provider_readiness.py
M	tests/test_public_launch_messaging.py
M	tests/test_public_launch_readiness.py
M	tests/test_rc1_cutover_consistency.py
A	tests/test_redaction.py
A	tests/test_release_assurance.py
M	tests/test_release_check_scripts.py
M	tests/test_reviewer_onboarding.py
M	tests/test_reviewer_outreach.py
A	tests/test_risk_defaults.py
A	tests/test_secrets.py
M	tests/test_stable_release_decision.py
A	tests/test_submit_execution_safety_check.py
A	tests/test_trust_center.py
M	tests/test_v0581_hotfix_cutover.py
M	tests/test_v058_dev_version_regression.py
M	tests/test_v058_rc1_readiness.py
M	tests/test_v058_rc5_cutover.py
A	tests/update/test_update_sources.py
```

## Protected Boundary Status

- **src/atlas_agent/config**: ✗
  - `M	src/atlas_agent/config/schema.py`
  - `M	src/atlas_agent/config/secrets.py`
- **src/atlas_agent/brokers**: ✗
  - `M	src/atlas_agent/brokers/alpaca.py`
- **src/atlas_agent/execution**: ✗
  - `M	src/atlas_agent/execution/approval.py`
- **src/atlas_agent/safety**: ✓
- **src/atlas_agent/risk**: ✗
  - `M	src/atlas_agent/risk/limits.py`

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
