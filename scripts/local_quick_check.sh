#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/local_quick_check.sh
# PURPOSE: Runs the local quick check validation workflow.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


# Atlas Agent — Local Quick Check
# Medium-cost local gate intended to run before committing.
#
# Target runtime: ~20–35 seconds with pytest-xdist on four cores; roughly
# two to three times that serially. Each run prints its own total.
# Skips historical release checkers, subprocess-heavy packaging checks,
# and slow integration tests while preserving all safety boundaries.
#
# This is a developer convenience check. It does NOT replace release_check.sh --quick
# or ci_check.sh. Full release_check.sh --full remains required before push/tag.
#
# Usage:
#   ./scripts/local_quick_check.sh
#
# Environment:
#   PYTHON_BIN                    Python interpreter to use (default: python3.11, then python).
#   ATLAS_CHECK_FAIL_FAST=1       Pass -x to pytest invocations.
#   ATLAS_CHECK_LAST_FAILED=1     Pass --lf to pytest invocations.
#   ATLAS_CHECK_PYTEST_ARGS       Extra arguments appended to pytest invocations.
#   ATLAS_CHECK_SERIAL=1          Do not distribute the test step across cores.

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
if [[ "${ATLAS_CHECK_LAST_FAILED:-}" == "1" ]]; then
    PYTEST_EXTRA_ARGS+=("--lf")
fi
if [[ -n "${ATLAS_CHECK_PYTEST_ARGS:-}" ]]; then
    read -ra USER_ARGS <<< "$ATLAS_CHECK_PYTEST_ARGS"
    PYTEST_EXTRA_ARGS+=("${USER_ARGS[@]}")
fi

# The quick test tier is this gate: every checker step around it costs 0-1 s and
# the tests cost the rest, so it is the only step worth distributing.
# pytest-xdist ships in the dev extra but the gate must still run without it, so
# an absent plugin degrades to the serial behaviour rather than failing.
# ATLAS_CHECK_SERIAL=1 forces serial on a machine where the heat matters more
# than the wall clock.
PYTEST_PARALLEL_ARGS=()
if [[ "${ATLAS_CHECK_SERIAL:-}" != "1" ]] && "$PYTHON_BIN" -c "import xdist" >/dev/null 2>&1; then
    PYTEST_PARALLEL_ARGS+=("-n" "auto")
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
echo "local quick check — pre-commit gate"
echo "========================================"

# --- Tier 1: smoke checks (non-negotiable safety) ---
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

# --- Tier 2: additional fast checks ---
_run "8. trust center check" \
    "$PYTHON_BIN" scripts/check_trust_center.py

_run "9. onboarding docs check" \
    "$PYTHON_BIN" scripts/check_onboarding_docs.py

_run "10. generated artifact hygiene check" \
    "$PYTHON_BIN" scripts/check_generated_artifacts.py

_run "11. GitHub Actions version check" \
    "$PYTHON_BIN" scripts/check_github_actions_versions.py

_run "12. README quickstart verification" \
    "$PYTHON_BIN" scripts/verify_readme_quickstart.py

_run "13. feedback intake check" \
    "$PYTHON_BIN" scripts/check_feedback_intake.py

_run "14. feedback taxonomy check" \
    "$PYTHON_BIN" scripts/check_feedback_taxonomy.py

_run "15. reviewer outreach check" \
    "$PYTHON_BIN" scripts/check_reviewer_outreach.py

_run "16. product capability inventory check" \
    "$PYTHON_BIN" scripts/check_product_capability_inventory.py

_run "17. demo command smoke validation" \
    "$PYTHON_BIN" scripts/check_demo_command_smoke.py

_run "18. git diff --cached --check" \
    git diff --cached --check

# --- Tier 3: automatically classified quick tests ---
# Tests in domain directories join this tier automatically. Legacy root-level
# coverage is classified centrally, and exceptional tests can declare `quick`.
_run "19. automatically classified quick tests" \
    "$PYTHON_BIN" -m pytest tests -m "quick" -q \
        "${PYTEST_PARALLEL_ARGS[@]+"${PYTEST_PARALLEL_ARGS[@]}"}" \
        "${PYTEST_EXTRA_ARGS[@]+"${PYTEST_EXTRA_ARGS[@]}"}"

echo ""
echo "========================================"
echo "All local quick checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
echo ""
echo "Reminder: local quick check is a convenience gate only."
echo "Run ./scripts/release_check.sh --full before push/tag."
