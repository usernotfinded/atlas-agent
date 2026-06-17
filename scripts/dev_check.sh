#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

cd "$REPO_ROOT"

# Optional thermal-friendly pytest args
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
echo "dev check — fast local development gate"
echo "========================================"

echo ""
echo "0. release metadata"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_metadata.py
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
echo "3. env template checks"
SECONDS=0
"$PYTHON_BIN" scripts/check_env_templates.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3a. packaged template integrity check"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_template_packaging.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4. forbidden claims scan"
SECONDS=0
"$PYTHON_BIN" scripts/check_forbidden_claims.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4a. bounded autonomy governance check"
SECONDS=0
"$PYTHON_BIN" scripts/check_bounded_autonomy_governance.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4b. bounded autonomy governance tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_bounded_autonomy_governance.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4c. autonomous paper workflow demo check"
SECONDS=0
"$PYTHON_BIN" scripts/check_autonomous_paper_workflow_demo.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4d. autonomous paper workflow demo tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_autonomous_paper_workflow_demo.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4e. paper provider isolation check"
SECONDS=0
"$PYTHON_BIN" scripts/check_paper_provider_isolation.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4f. paper provider isolation tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_paper_provider_isolation.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4g. paper strategy evaluation check"
SECONDS=0
"$PYTHON_BIN" scripts/check_paper_strategy_evaluation.py
"$PYTHON_BIN" scripts/check_paper_strategy_sensitivity.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4h. paper strategy evaluation tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_paper_strategy_evaluation.py tests/test_paper_strategy_sensitivity.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "5. trust center check"
SECONDS=0
"$PYTHON_BIN" scripts/check_trust_center.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "6. onboarding docs check"
SECONDS=0
"$PYTHON_BIN" scripts/check_onboarding_docs.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "7. generated artifact hygiene check"
SECONDS=0
"$PYTHON_BIN" scripts/check_generated_artifacts.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8. GitHub Actions version check"
SECONDS=0
"$PYTHON_BIN" scripts/check_github_actions_versions.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "9. feedback intake check"
SECONDS=0
"$PYTHON_BIN" scripts/check_feedback_intake.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "10. feedback taxonomy check"
SECONDS=0
"$PYTHON_BIN" scripts/check_feedback_taxonomy.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "11. reviewer outreach check"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_outreach.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "12. product capability inventory check"
SECONDS=0
"$PYTHON_BIN" scripts/check_product_capability_inventory.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.1. v0.6.12 release candidate readiness check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0612_release_candidate_readiness.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.2. v0.6.12 release candidate readiness tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_v0612_release_candidate_readiness.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.3. v0.6.12 release cutover check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0612_release_cutover.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.4. v0.6.12 release cutover tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_v0612_release_cutover.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.5. v0.6.12 release prep check (post-release)"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0612_release_prep.py --post-release
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.6. v0.6.12 release prep tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_v0612_release_prep.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.7. v0.6.12 post-release evidence check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0612_post_release_evidence.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.8. v0.6.12 post-release evidence tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_v0612_post_release_evidence.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.9. v0.6.13 post-release hygiene check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0613_post_release_hygiene.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13.10. v0.6.13 post-release hygiene tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_v0613_post_release_hygiene.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13a. product demo and marketplace readiness check"
SECONDS=0
"$PYTHON_BIN" scripts/check_product_demo_pack.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13b. product demo and marketplace readiness tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_product_demo_pack.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13c. product demo evidence tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_product_demo_evidence.py -m "not slow" -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13d. reviewer trust snapshot check (self-test)"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_trust_snapshot.py --self-test
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13e. reviewer trust snapshot tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_reviewer_trust_snapshot.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13f. reviewer trust snapshot workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_trust_snapshot_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13g. reviewer trust snapshot workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_reviewer_trust_snapshot_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13h. docs archive hygiene check"
SECONDS=0
"$PYTHON_BIN" scripts/check_docs_archive_hygiene.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13i. docs archive hygiene tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_docs_archive_hygiene.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13j. release assurance snapshot integration check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_snapshot_integration.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13k. release assurance snapshot integration tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_snapshot_integration.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13l. release assurance bundle manifest tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_bundle_manifest.py -m "not slow" -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13m. release assurance bundle workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_bundle_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13n. release assurance bundle workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_bundle_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13q. release assurance diagnostics check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_diagnostics.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13r. release assurance diagnostics tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13s. release assurance diagnostics workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_diagnostics_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13t. release assurance diagnostics workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13u. release assurance diagnostics artifact check (deterministic fixture)"
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
echo "13v. release assurance diagnostics artifact tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics_artifact.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13w. release assurance diagnostics artifact workflow check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_diagnostics_artifact_workflow.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13x. release assurance diagnostics artifact workflow tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_diagnostics_artifact_workflow.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13y. release assurance artifact retention audit check"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_assurance_artifact_retention_audit.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13z. release assurance artifact retention audit (deterministic fixture)"
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
echo "13za. release assurance artifact retention audit tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_artifact_retention_audit.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13o. release assurance workflow artifact check (deterministic fixture)"
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
echo "13p. release assurance workflow artifact tests (fast)"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_assurance_workflow_artifact.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "14. generated artifact hygiene tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_generated_artifacts.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "15. GitHub Actions version tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_github_actions_versions.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "16. research sandbox CLI tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/research/test_research_sandbox_cli.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "17. reviewer golden-path smoke tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_reviewer_golden_path_smoke.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "18. env template tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_env_templates.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "19. release check script tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_check_scripts.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "20. git diff --check"
SECONDS=0
git diff --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "21. git diff --cached --check"
SECONDS=0
git diff --cached --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "22. protected staged files"
SECONDS=0
"$PYTHON_BIN" scripts/check_no_protected_staged.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "All dev checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
