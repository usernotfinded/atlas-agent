#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

cd "$REPO_ROOT"

echo "========================================"
echo "ci check — local CI parity gate"
echo "========================================"

echo ""
echo "1. version consistency"
"$PYTHON_BIN" scripts/check_version_consistency.py

echo ""
echo "2. CLI command compatibility"
"$PYTHON_BIN" scripts/check_cli_command_compatibility.py

echo ""
echo "3. forbidden claims scan"
"$PYTHON_BIN" scripts/check_forbidden_claims.py

echo ""
echo "4. feedback intake check"
"$PYTHON_BIN" scripts/check_feedback_intake.py

echo ""
echo "5. feedback taxonomy check"
"$PYTHON_BIN" scripts/check_feedback_taxonomy.py

echo ""
echo "6. reviewer outreach check"
"$PYTHON_BIN" scripts/check_reviewer_outreach.py

echo ""
echo "7. product capability inventory check"
"$PYTHON_BIN" scripts/check_product_capability_inventory.py

echo ""
echo "8. v0.5.8 gap prioritization check"
"$PYTHON_BIN" scripts/check_v058_gap_prioritization.py

echo ""
echo "8a. v0.5.8 RC1 readiness dry run"
"$PYTHON_BIN" scripts/check_v058_rc1_readiness.py

echo ""
echo "8b. v0.5.8.1 hotfix cutover check"
"$PYTHON_BIN" scripts/check_v0581_hotfix_cutover.py

echo ""
echo "9. public docs consistency"
"$PYTHON_BIN" scripts/check_public_docs_consistency.py

echo ""
echo "10. trust center check"
"$PYTHON_BIN" scripts/check_trust_center.py

echo ""
echo "11. onboarding docs check"
"$PYTHON_BIN" scripts/check_onboarding_docs.py

echo ""
echo "12. README quickstart verification"
"$PYTHON_BIN" scripts/verify_readme_quickstart.py

echo ""
echo "13. RC cutover check"
"$PYTHON_BIN" scripts/check_rc1_cutover.py

echo ""
echo "14. clean install dry-run"
"$PYTHON_BIN" scripts/check_clean_install.py --dry-run

echo ""
echo "15. clean install verification"
"$PYTHON_BIN" scripts/check_clean_install.py

echo ""
echo "16. package distribution dry-run"
"$PYTHON_BIN" scripts/check_package_distribution.py --dry-run

echo ""
echo "17. package distribution verification"
"$PYTHON_BIN" scripts/check_package_distribution.py

echo ""
echo "18. public launch readiness check"
"$PYTHON_BIN" scripts/check_public_launch_readiness.py

echo ""
echo "19. reviewer onboarding check"
"$PYTHON_BIN" scripts/check_reviewer_onboarding.py

echo ""
echo "20. public launch messaging check"
"$PYTHON_BIN" scripts/check_public_launch_messaging.py

echo ""
echo "21. final RC audit check"
"$PYTHON_BIN" scripts/check_final_rc_audit.py

echo ""
echo "22. stable release decision check"
"$PYTHON_BIN" scripts/check_stable_release_decision.py

echo ""
echo "23. focused pytest subset"
"$PYTHON_BIN" -m pytest tests/test_clean_install_check.py -q
"$PYTHON_BIN" -m pytest tests/test_package_distribution_check.py -q
"$PYTHON_BIN" -m pytest tests/test_rc1_cutover_consistency.py -q
"$PYTHON_BIN" -m pytest tests/test_changelog_consistency.py -q
"$PYTHON_BIN" -m pytest tests/test_public_docs_consistency.py -q
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

echo ""
echo "24. pip check"
"$PYTHON_BIN" -m pip check

echo ""
echo "25. git diff --check"
git diff --check

echo ""
echo "26. protected staged files"
"$PYTHON_BIN" scripts/check_no_protected_staged.py

echo ""
echo "========================================"
echo "All CI checks passed."
echo "========================================"
