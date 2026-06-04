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

echo "========================================"
echo "dev check — fast local development gate"
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
echo "4. trust center check"
"$PYTHON_BIN" scripts/check_trust_center.py

echo ""
echo "5. feedback intake check"
"$PYTHON_BIN" scripts/check_feedback_intake.py

echo ""
echo "6. feedback taxonomy check"
"$PYTHON_BIN" scripts/check_feedback_taxonomy.py

echo ""
echo "7. reviewer outreach check"
"$PYTHON_BIN" scripts/check_reviewer_outreach.py

echo ""
echo "8. product capability inventory check"
"$PYTHON_BIN" scripts/check_product_capability_inventory.py

echo ""
echo "9. v0.5.8 gap prioritization check"
"$PYTHON_BIN" scripts/check_v058_gap_prioritization.py

echo ""
echo "9a. v0.5.8 RC1 readiness dry run"
"$PYTHON_BIN" scripts/check_v058_rc1_readiness.py

echo ""
echo "9b. v0.5.8.1 hotfix cutover check"
"$PYTHON_BIN" scripts/check_v0581_hotfix_cutover.py

echo ""
echo "10. research sandbox CLI tests"
"$PYTHON_BIN" -m pytest tests/research/test_research_sandbox_cli.py -q "${PYTEST_EXTRA_ARGS[@]}"

echo ""
echo "11. reviewer golden-path smoke tests"
"$PYTHON_BIN" -m pytest tests/test_reviewer_golden_path_smoke.py -q "${PYTEST_EXTRA_ARGS[@]}"

echo ""
echo "12. release check script tests"
"$PYTHON_BIN" -m pytest tests/test_release_check_scripts.py -q "${PYTEST_EXTRA_ARGS[@]}"

echo ""
echo "13. git diff --check"
git diff --check

echo ""
echo "14. git diff --cached --check"
git diff --cached --check

echo ""
echo "15. protected staged files"
"$PYTHON_BIN" scripts/check_no_protected_staged.py

echo ""
echo "========================================"
echo "All dev checks passed."
echo "========================================"
