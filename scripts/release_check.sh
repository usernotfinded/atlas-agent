#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

cd "$REPO_ROOT"

echo "========================================"
echo "1. pytest"
echo "========================================"
$PYTHON_BIN -m pytest -q

echo ""
echo "========================================"
echo "2. pip check"
echo "========================================"
$PYTHON_BIN -m pip check

echo ""
echo "========================================"
echo "3. demo paper workflow"
echo "========================================"
./scripts/demo_paper_workflow.sh

echo ""
echo "========================================"
echo "4. git diff --check"
echo "========================================"
git diff --check

echo ""
echo "========================================"
echo "5. protected staged files"
echo "========================================"
$PYTHON_BIN scripts/check_no_protected_staged.py

echo ""
echo "========================================"
echo "6. version consistency"
echo "========================================"
$PYTHON_BIN scripts/check_version_consistency.py

echo ""
echo "========================================"
echo "7. forbidden claims scan"
echo "========================================"
$PYTHON_BIN scripts/check_forbidden_claims.py

echo ""
echo "========================================"
echo "All release checks passed."
echo "========================================"
