#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

cd "$REPO_ROOT"

PYTEST_EXTRA_ARGS=()
if [[ "${ATLAS_CHECK_FAIL_FAST:-}" == "1" ]]; then
    PYTEST_EXTRA_ARGS+=("-x")
fi
if [[ "${ATLAS_CHECK_LAST_FAILED:-}" == "1" ]]; then
    PYTEST_EXTRA_ARGS+=("--lf")
fi
if [[ -n "${ATLAS_CHECK_PYTEST_ARGS:-}" ]]; then
    read -ra USER_ARGS <<< "$ATLAS_CHECK_PYTEST_ARGS"
    PYTEST_EXTRA_ARGS+=("${USER_ARGS[@]}")
fi

TOTAL_ELAPSED=0

echo "========================================"
echo "ci check — local CI parity gate"
echo "========================================"

echo ""
echo "0. release metadata"
SECONDS=0
python scripts/check_release_metadata.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"


echo "1. version consistency"
SECONDS=0
"$PYTHON_BIN" scripts/check_version_consistency.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "2. CLI command compatibility"
SECONDS=0
"$PYTHON_BIN" scripts/check_cli_command_compatibility.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3. forbidden claims scan"
SECONDS=0
"$PYTHON_BIN" scripts/check_forbidden_claims.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3a. bounded autonomy governance check"
SECONDS=0
"$PYTHON_BIN" scripts/check_bounded_autonomy_governance.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3b. bounded autonomy governance tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_bounded_autonomy_governance.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3c. autonomous paper workflow demo check"
SECONDS=0
"$PYTHON_BIN" scripts/check_autonomous_paper_workflow_demo.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3d. autonomous paper workflow demo tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_autonomous_paper_workflow_demo.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3e. paper provider isolation check"
SECONDS=0
"$PYTHON_BIN" scripts/check_paper_provider_isolation.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3f. paper provider isolation tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_paper_provider_isolation.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3g. paper strategy evaluation check"
SECONDS=0
"$PYTHON_BIN" scripts/check_paper_strategy_evaluation.py
"$PYTHON_BIN" scripts/check_paper_strategy_sensitivity.py
"$PYTHON_BIN" scripts/check_paper_strategy_robustness.py
"$PYTHON_BIN" scripts/check_paper_strategy_walk_forward.py
"$PYTHON_BIN" scripts/check_paper_strategy_scorecard.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4l. paper portfolio proposal sandbox check"
SECONDS=0
"$PYTHON_BIN" scripts/check_paper_portfolio_proposal.py
"$PYTHON_BIN" scripts/check_v0613_paper_autonomy_evidence.py
"$PYTHON_BIN" scripts/check_v0613_final_reviewer_index.py
"$PYTHON_BIN" scripts/check_v0613_release_cutover_preflight.py
"$PYTHON_BIN" scripts/check_v0613_final_readiness_audit.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3h. paper strategy evaluation tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_paper_strategy_evaluation.py tests/test_paper_strategy_sensitivity.py tests/test_paper_strategy_robustness.py tests/test_paper_strategy_walk_forward.py tests/test_paper_strategy_scorecard.py tests/test_paper_portfolio_proposal.py tests/test_v0613_paper_autonomy_evidence.py tests/test_v0613_final_reviewer_index.py tests/test_v0613_release_cutover_preflight.py tests/test_v0613_final_readiness_audit.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4. env template checks"
SECONDS=0
"$PYTHON_BIN" scripts/check_env_templates.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4a. packaged template integrity check"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_template_packaging.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "5. feedback intake check"
SECONDS=0
"$PYTHON_BIN" scripts/check_feedback_intake.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "5. feedback taxonomy check"
SECONDS=0
"$PYTHON_BIN" scripts/check_feedback_taxonomy.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "6. reviewer outreach check"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_outreach.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "7. product capability inventory check"
SECONDS=0
"$PYTHON_BIN" scripts/check_product_capability_inventory.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8.9. v0.6.13 post-release hygiene check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0613_post_release_hygiene.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8.10. v0.6.13 post-release hygiene tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_v0613_post_release_hygiene.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8a. product demo and marketplace readiness check"
SECONDS=0
"$PYTHON_BIN" scripts/check_product_demo_pack.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8b. product demo evidence tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_product_demo_evidence.py -m "not slow" -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8c. reviewer trust snapshot check (self-test)"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_trust_snapshot.py --self-test
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8d. reviewer trust snapshot tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_reviewer_trust_snapshot.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8e. reviewer trust snapshot workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_trust_snapshot_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8f. reviewer trust snapshot workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_reviewer_trust_snapshot_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8g. docs archive hygiene check"
SECONDS=0
"$PYTHON_BIN" scripts/check_docs_archive_hygiene.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8h. docs archive hygiene tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_docs_archive_hygiene.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8i. release assurance snapshot integration check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_snapshot_integration.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8j. release assurance snapshot integration tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_snapshot_integration.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8k. release assurance bundle manifest tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_bundle_manifest.py -m "not slow" -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8l. release assurance bundle workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_bundle_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8m. release assurance bundle workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_bundle_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8n. release assurance diagnostics check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_diagnostics.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8o. release assurance diagnostics tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8r. release assurance diagnostics workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_diagnostics_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8s. release assurance diagnostics workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8t. release assurance diagnostics artifact check (deterministic fixture)"
SECONDS=0
"$PYTHON_BIN" - "$REPO_ROOT" <<'PY'
import json, subprocess, sys, tempfile
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
check_script = repo_root / "scripts" / "check_release_assurance_diagnostics_artifact.py"

with tempfile.TemporaryDirectory() as tmp:
    diag_path = Path(tmp) / "release-assurance-diagnostics.json"
    diag_path.write_text(
        json.dumps(
            {
                "schema_version": "atlas-release-assurance-diagnostics/1.0",
                "passed": False,
                "release": "v0.0.0-does-not-exist",
                "failed_phase": "release_assurance",
                "failed_check": "package_version_aligned",
                "command": "internal: read pyproject.toml",
                "exit_code": 0,
                "stdout_excerpt": "",
                "stderr_excerpt": "",
                "remediation": "Verify versions are aligned.",
                "redactions_applied": ["*_TOKEN"],
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    subprocess.run([
        sys.executable, str(check_script), str(diag_path),
        "--expect-release", "v0.0.0-does-not-exist",
        "--expect-failed-check", "package_version_aligned",
    ], check=True)
PY
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8u. release assurance diagnostics artifact tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics_artifact.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8v. release assurance diagnostics artifact workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_diagnostics_artifact_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8w. release assurance diagnostics artifact workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics_artifact_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8x. release assurance artifact retention audit check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_artifact_retention_audit.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8y. release assurance artifact retention audit (deterministic fixture)"
SECONDS=0
"$PYTHON_BIN" - "$REPO_ROOT" <<'PY'
import json, subprocess, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
audit_script = repo_root / "scripts" / "audit_release_assurance_artifact_retention.py"

with tempfile.TemporaryDirectory() as tmp:
    fixture_path = Path(tmp) / "artifacts.json"
    report_dir = Path(tmp) / "report"
    report_dir.mkdir()
    now = datetime.now(timezone.utc)
    fixture_path.write_text(
        json.dumps(
            {
                "total_count": 1,
                "artifacts": [
                    {
                        "name": "release-assurance-diagnostics",
                        "id": 123456,
                        "workflow_run": {"id": 789012},
                        "created_at": (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "expires_at": (now + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "expired": False,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    subprocess.run([
        sys.executable, str(audit_script),
        "--input-json", str(fixture_path),
        "--output-dir", str(report_dir),
        "--json",
    ], check=True)
    json_report = report_dir / "release-assurance-artifact-retention-report.json"
    md_report = report_dir / "release-assurance-artifact-retention-report.md"
    assert json_report.exists(), f"JSON report not found: {json_report}"
    assert md_report.exists(), f"Markdown report not found: {md_report}"
PY
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8z. release assurance artifact retention audit tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_artifact_retention_audit.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8p. release assurance workflow artifact check (deterministic fixture)"
SECONDS=0
"$PYTHON_BIN" - "$REPO_ROOT" <<'PY'
import json, subprocess, sys, tempfile
from pathlib import Path

release = "v0.6.11"
repo_root = Path(sys.argv[1]).resolve()
build_script = repo_root / "scripts" / "build_release_assurance_bundle_manifest.py"
check_script = repo_root / "scripts" / "check_release_assurance_workflow_artifact.py"

with tempfile.TemporaryDirectory() as tmp:
    artifact_dir = Path(tmp) / "release-assurance-bundle-demo"
    baseline_dir = artifact_dir / "baseline"
    snapshot_dir = artifact_dir / "with-reviewer-trust-snapshot"
    baseline_dir.mkdir(parents=True)
    snapshot_dir.mkdir(parents=True)
    for bundle in (baseline_dir, snapshot_dir):
        for name in ("release-assurance-summary.json", "release-assurance-report.md", "sha256sums.txt"):
            (bundle / name).write_text("{}", encoding="utf-8")
    snap_dir = snapshot_dir / "reviewer-trust-snapshot"
    snap_dir.mkdir()
    (snap_dir / "reviewer-trust-snapshot.json").write_text(json.dumps({"schema_version": "atlas-reviewer-trust-snapshot/1.0"}, indent=2), encoding="utf-8")
    (snap_dir / "reviewer-trust-snapshot.md").write_text("# Reviewer trust snapshot\n", encoding="utf-8")

    subprocess.run([
        sys.executable, str(build_script),
        "--baseline-dir", str(baseline_dir),
        "--snapshot-dir", str(snapshot_dir),
        "--release", release,
        "--output-dir", str(artifact_dir),
    ], check=True)

    subprocess.run([
        sys.executable, str(check_script), str(artifact_dir),
    ], check=True)
PY
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8q. release assurance workflow artifact tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_workflow_artifact.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "9. public docs consistency"
SECONDS=0
"$PYTHON_BIN" scripts/check_public_docs_consistency.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "10. trust center check"
SECONDS=0
"$PYTHON_BIN" scripts/check_trust_center.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "11. onboarding docs check"
SECONDS=0
"$PYTHON_BIN" scripts/check_onboarding_docs.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "12. generated artifact hygiene check"
SECONDS=0
"$PYTHON_BIN" scripts/check_generated_artifacts.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13. GitHub Actions version check"
SECONDS=0
"$PYTHON_BIN" scripts/check_github_actions_versions.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "14. README quickstart verification"
SECONDS=0
"$PYTHON_BIN" scripts/verify_readme_quickstart.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "15. RC cutover check"
SECONDS=0
"$PYTHON_BIN" scripts/check_rc1_cutover.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "16. clean install dry-run"
SECONDS=0
"$PYTHON_BIN" scripts/check_clean_install.py --dry-run
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "17. clean install verification"
SECONDS=0
"$PYTHON_BIN" scripts/check_clean_install.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "18. package distribution dry-run"
SECONDS=0
"$PYTHON_BIN" scripts/check_package_distribution.py --dry-run
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "19. package distribution verification"
SECONDS=0
"$PYTHON_BIN" scripts/check_package_distribution.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "20. public launch readiness check"
SECONDS=0
"$PYTHON_BIN" scripts/check_public_launch_readiness.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "21. reviewer onboarding check"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_onboarding.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "22. public launch messaging check"
SECONDS=0
"$PYTHON_BIN" scripts/check_public_launch_messaging.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "23. final RC audit check"
SECONDS=0
"$PYTHON_BIN" scripts/check_final_rc_audit.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "24. stable release decision check"
SECONDS=0
"$PYTHON_BIN" scripts/check_stable_release_decision.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "25. focused pytest subset"
SECONDS=0
"$PYTHON_BIN" -m pytest \
    tests/test_clean_install_check.py \
    tests/test_package_distribution_check.py \
    tests/test_rc1_cutover_consistency.py \
    tests/test_changelog_consistency.py \
    tests/test_public_docs_consistency.py \
    tests/test_generated_artifacts.py \
    tests/test_github_actions_versions.py \
    tests/test_trust_center.py \
    tests/test_onboarding_docs.py \
    tests/test_readme_quickstart_verification.py \
    tests/test_release_check_scripts.py \
    tests/test_ci_workflows.py \
    tests/test_docs_v040.py \
    tests/test_public_launch_readiness.py \
    tests/test_reviewer_onboarding.py \
    tests/test_public_launch_messaging.py \
    tests/test_final_rc_audit.py \
    tests/test_stable_release_decision.py \
    tests/test_check_v0610_release_prep.py \
    tests/test_check_v0611_release_prep.py \
    tests/test_check_v0611_planning.py \
    tests/test_env_templates.py \
    tests/test_product_demo_pack.py \
    tests/test_reviewer_trust_snapshot_workflow.py \
    tests/test_docs_archive_hygiene.py \
    -q \
    "${PYTEST_EXTRA_ARGS[@]+"${PYTEST_EXTRA_ARGS[@]}"}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "26. pip check"
SECONDS=0
"$PYTHON_BIN" -m pip check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "27. git diff --check"
SECONDS=0
git diff --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "28. protected staged files"
SECONDS=0
"$PYTHON_BIN" scripts/check_no_protected_staged.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "All CI checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
