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
echo "research check — research/sandbox gate"
echo "========================================"

echo ""
echo "1. version consistency"
SECONDS=0
"$PYTHON_BIN" scripts/check_version_consistency.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "2. forbidden claims scan"
SECONDS=0
"$PYTHON_BIN" scripts/check_forbidden_claims.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3. research tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/research -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4. demo research workflow script tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_demo_research_workflow_script.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "5. demo research workflow"
SECONDS=0
./scripts/demo_research_workflow.sh
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "6. git diff --check"
SECONDS=0
git diff --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "7. git diff --cached --check"
SECONDS=0
git diff --cached --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8. protected staged files"
SECONDS=0
"$PYTHON_BIN" scripts/check_no_protected_staged.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "All research checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
