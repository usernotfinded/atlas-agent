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
echo "4. feedback intake check"
"$PYTHON_BIN" scripts/check_feedback_intake.py

echo ""
echo "5. feedback taxonomy check"
"$PYTHON_BIN" scripts/check_feedback_taxonomy.py

echo ""
echo "5. research sandbox CLI tests"
"$PYTHON_BIN" -m pytest tests/research/test_research_sandbox_cli.py -q "${PYTEST_EXTRA_ARGS[@]}"

echo ""
echo "6. reviewer golden-path smoke tests"
"$PYTHON_BIN" -m pytest tests/test_reviewer_golden_path_smoke.py -q "${PYTEST_EXTRA_ARGS[@]}"

echo ""
echo "7. release check script tests"
"$PYTHON_BIN" -m pytest tests/test_release_check_scripts.py -q "${PYTEST_EXTRA_ARGS[@]}"

echo ""
echo "8. git diff --check"
git diff --check

echo ""
echo "9. git diff --cached --check"
git diff --cached --check

echo ""
echo "10. protected staged files"
"$PYTHON_BIN" scripts/check_no_protected_staged.py

echo ""
echo "========================================"
echo "All dev checks passed."
echo "========================================"
