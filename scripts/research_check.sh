#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

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
echo "research check — research/sandbox gate"
echo "========================================"

echo ""
echo "1. version consistency"
"$PYTHON_BIN" scripts/check_version_consistency.py

echo ""
echo "2. forbidden claims scan"
"$PYTHON_BIN" scripts/check_forbidden_claims.py

echo ""
echo "3. research tests"
"$PYTHON_BIN" -m pytest tests/research -q "${PYTEST_EXTRA_ARGS[@]}"

echo ""
echo "4. demo research workflow script tests"
"$PYTHON_BIN" -m pytest tests/test_demo_research_workflow_script.py -q "${PYTEST_EXTRA_ARGS[@]}"

echo ""
echo "5. demo research workflow"
./scripts/demo_research_workflow.sh

echo ""
echo "6. git diff --check"
git diff --check

echo ""
echo "7. git diff --cached --check"
git diff --cached --check

echo ""
echo "8. protected staged files"
"$PYTHON_BIN" scripts/check_no_protected_staged.py

echo ""
echo "========================================"
echo "All research checks passed."
echo "========================================"
