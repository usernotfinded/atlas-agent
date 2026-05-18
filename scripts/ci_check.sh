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
echo "2. forbidden claims scan"
"$PYTHON_BIN" scripts/check_forbidden_claims.py

echo ""
echo "3. pytest"
"$PYTHON_BIN" -m pytest -q

echo ""
echo "4. pip check"
"$PYTHON_BIN" -m pip check

echo ""
echo "5. demo paper workflow"
./scripts/demo_paper_workflow.sh

echo ""
echo "6. demo research workflow"
./scripts/demo_research_workflow.sh

echo ""
echo "7. git diff --check"
git diff --check

echo ""
echo "8. protected staged files"
"$PYTHON_BIN" scripts/check_no_protected_staged.py

echo ""
echo "========================================"
echo "All CI checks passed."
echo "========================================"
