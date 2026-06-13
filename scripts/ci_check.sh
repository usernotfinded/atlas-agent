#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

cd "$REPO_ROOT"

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
echo "8. v0.5.8 gap prioritization check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v058_gap_prioritization.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8a. v0.5.8 RC1 readiness dry run"
SECONDS=0
"$PYTHON_BIN" scripts/check_v058_rc1_readiness.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8b. v0.5.8.1 hotfix cutover check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0581_hotfix_cutover.py
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
"$PYTHON_BIN" -m pytest tests/test_clean_install_check.py -q
"$PYTHON_BIN" -m pytest tests/test_package_distribution_check.py -q
"$PYTHON_BIN" -m pytest tests/test_rc1_cutover_consistency.py -q
"$PYTHON_BIN" -m pytest tests/test_changelog_consistency.py -q
"$PYTHON_BIN" -m pytest tests/test_public_docs_consistency.py -q
"$PYTHON_BIN" -m pytest tests/test_generated_artifacts.py -q
"$PYTHON_BIN" -m pytest tests/test_github_actions_versions.py -q
"$PYTHON_BIN" -m pytest tests/test_trust_center.py -q
"$PYTHON_BIN" -m pytest tests/test_onboarding_docs.py -q
"$PYTHON_BIN" -m pytest tests/test_readme_quickstart_verification.py -q
"$PYTHON_BIN" -m pytest tests/test_release_check_scripts.py -q
"$PYTHON_BIN" -m pytest tests/test_ci_workflows.py -q
"$PYTHON_BIN" -m pytest tests/test_docs_v040.py -q
"$PYTHON_BIN" -m pytest tests/test_public_launch_readiness.py -q
"$PYTHON_BIN" -m pytest tests/test_reviewer_onboarding.py -q
"$PYTHON_BIN" -m pytest tests/test_public_launch_messaging.py -q
"$PYTHON_BIN" -m pytest tests/test_final_rc_audit.py -q
"$PYTHON_BIN" -m pytest tests/test_stable_release_decision.py -q
"$PYTHON_BIN" -m pytest tests/test_v0581_hotfix_cutover.py -q
"$PYTHON_BIN" -m pytest tests/test_env_templates.py -q
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
