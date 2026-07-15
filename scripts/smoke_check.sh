#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/smoke_check.sh
# PURPOSE: Runs the smoke check validation workflow.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


# Atlas Agent — Smoke Check
# Fastest local gate for edit-loop feedback after small docs/checker changes.
#
# Target runtime: < 10 seconds.
# This is a developer convenience check. It does NOT replace release_check.sh --quick
# or ci_check.sh. Full release_check.sh --full remains required before push/tag.
#
# Usage:
#   ./scripts/smoke_check.sh
#
# Environment:
#   PYTHON_BIN              Python interpreter to use (default: python3.11, then python).
#   ATLAS_CHECK_FAIL_FAST=1 Pass -x to pytest invocations.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

cd "$REPO_ROOT"

PYTEST_EXTRA_ARGS=()
if [[ "${ATLAS_CHECK_FAIL_FAST:-}" == "1" ]]; then
    PYTEST_EXTRA_ARGS+=("-x")
fi

TOTAL_ELAPSED=0

_run() {
    local label="$1"
    shift
    echo ""
    echo "$label"
    SECONDS=0
    "$@"
    TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
    echo "  → elapsed: ${SECONDS}s"
}

echo "========================================"
echo "smoke check — fastest local gate"
echo "========================================"

_run "1. version consistency" \
    "$PYTHON_BIN" scripts/check_version_consistency.py

_run "2. forbidden claims scan" \
    "$PYTHON_BIN" scripts/check_forbidden_claims.py

_run "3. CLI command compatibility" \
    "$PYTHON_BIN" scripts/check_cli_command_compatibility.py

_run "4. submit execution safety" \
    "$PYTHON_BIN" scripts/check_submit_execution_safety.py

_run "5. git diff --check" \
    git diff --check

_run "6. protected staged files" \
    "$PYTHON_BIN" scripts/check_no_protected_staged.py

_run "7. pip check" \
    "$PYTHON_BIN" -m pip check

_run "8. demo command smoke validation" \
    "$PYTHON_BIN" scripts/check_demo_command_smoke.py

_run "9. focused pytest smoke" \
    "$PYTHON_BIN" -m pytest tests/test_cli_smoke.py tests/test_submit_execution_safety_check.py -q "${PYTEST_EXTRA_ARGS[@]+"${PYTEST_EXTRA_ARGS[@]}"}"

echo ""
echo "========================================"
echo "All smoke checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
echo ""
echo "Reminder: smoke check is a convenience gate only."
echo "Run ./scripts/local_quick_check.sh before commit,"
echo "and ./scripts/release_check.sh --full before push/tag."
