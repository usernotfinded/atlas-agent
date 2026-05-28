#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

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
echo "4. public docs consistency"
"$PYTHON_BIN" scripts/check_public_docs_consistency.py

echo ""
echo "5. README quickstart verification"
"$PYTHON_BIN" scripts/verify_readme_quickstart.py

echo ""
echo "6. RC cutover check"
"$PYTHON_BIN" scripts/check_rc1_cutover.py

echo ""
echo "7. clean install dry-run"
"$PYTHON_BIN" scripts/check_clean_install.py --dry-run

echo ""
echo "8. clean install verification"
"$PYTHON_BIN" scripts/check_clean_install.py

echo ""
echo "9. package distribution dry-run"
"$PYTHON_BIN" scripts/check_package_distribution.py --dry-run

echo ""
echo "10. package distribution verification"
"$PYTHON_BIN" scripts/check_package_distribution.py

echo ""
echo "11. public launch readiness check"
"$PYTHON_BIN" scripts/check_public_launch_readiness.py

echo ""
echo "12. reviewer onboarding check"
"$PYTHON_BIN" scripts/check_reviewer_onboarding.py

echo ""
echo "13. public launch messaging check"
"$PYTHON_BIN" scripts/check_public_launch_messaging.py

echo ""
echo "14. final RC audit check"
"$PYTHON_BIN" scripts/check_final_rc_audit.py

echo ""
echo "15. stable release decision check"
"$PYTHON_BIN" scripts/check_stable_release_decision.py

echo ""
echo "16. focused pytest subset"
"$PYTHON_BIN" -m pytest tests/test_clean_install_check.py -q
"$PYTHON_BIN" -m pytest tests/test_package_distribution_check.py -q
"$PYTHON_BIN" -m pytest tests/test_rc1_cutover_consistency.py -q
"$PYTHON_BIN" -m pytest tests/test_changelog_consistency.py -q
"$PYTHON_BIN" -m pytest tests/test_public_docs_consistency.py -q
"$PYTHON_BIN" -m pytest tests/test_readme_quickstart_verification.py -q
"$PYTHON_BIN" -m pytest tests/test_release_check_scripts.py -q
"$PYTHON_BIN" -m pytest tests/test_ci_workflows.py -q
"$PYTHON_BIN" -m pytest tests/test_docs_v040.py -q
"$PYTHON_BIN" -m pytest tests/test_public_launch_readiness.py -q
"$PYTHON_BIN" -m pytest tests/test_reviewer_onboarding.py -q
"$PYTHON_BIN" -m pytest tests/test_public_launch_messaging.py -q
"$PYTHON_BIN" -m pytest tests/test_final_rc_audit.py -q
"$PYTHON_BIN" -m pytest tests/test_stable_release_decision.py -q

echo ""
echo "17. pip check"
"$PYTHON_BIN" -m pip check

echo ""
echo "18. git diff --check"
git diff --check

echo ""
echo "19. protected staged files"
"$PYTHON_BIN" scripts/check_no_protected_staged.py

echo ""
echo "========================================"
echo "All CI checks passed."
echo "========================================"
