#!/usr/bin/env bash
set -euo pipefail

# Atlas Agent — Local Quick Check
# Medium-cost local gate intended to run before committing.
#
# Target runtime: ~30–45 seconds on a modern Mac.
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

# --- Tier 3: focused pytest subset ---
# Includes core unit tests and fast script tests.
# Subprocess-heavy tests marked "slow" remain in full pytest and CI.
# Excludes:
#   - slow subprocess-heavy integration tests (demo workflow, clean install, package build)
#   - historical release checker tests (v0.5.8, v0.6.0–v0.6.6)
#   - slow research sandbox/dossier tests
_run "18. focused pytest subset" \
    "$PYTHON_BIN" -m pytest \
        tests/agent/ \
        tests/architecture/ \
        tests/audit/ \
        tests/backtest/ \
        tests/brokers/ \
        tests/cli/ \
        tests/config/ \
        tests/dashboard/ \
        tests/execution/ \
        tests/e2e/ \
        tests/gateway/ \
        tests/learning/ \
        tests/notifications/ \
        tests/reflection/ \
        tests/reports/ \
        tests/risk/ \
        tests/safety/ \
        tests/skills/ \
        tests/tools/ \
        tests/update/ \
        tests/research/test_research_cli.py \
        tests/research/test_research_configless_cli.py \
        tests/research/test_research_schema_version.py \
        tests/research/test_research_session.py \
        tests/research/test_research_providers.py \
        tests/research/test_research_check_artifacts_cli.py \
        tests/research/test_research_plan_cli.py \
        tests/research/test_research_prompt_cli.py \
        tests/test_generated_artifacts.py \
        tests/test_github_actions_versions.py \
        tests/test_trust_center.py \
        tests/test_onboarding_docs.py \
        tests/test_public_docs_consistency.py \
        tests/test_public_launch_readiness.py \
        tests/test_main_health.py \
        tests/test_release_check_scripts.py \
        tests/test_readme_quickstart_verification.py \
        tests/test_changelog_consistency.py \
        tests/test_ci_workflows.py \
        tests/test_check_v0610_release_prep.py \
        tests/test_check_v0611_planning.py \
        tests/test_submit_execution_safety_check.py \
        tests/test_cli_smoke.py \
        tests/test_feedback_intake.py \
        tests/test_feedback_taxonomy.py \
        tests/test_reviewer_outreach.py \
        tests/test_product_capability_inventory.py \
        tests/test_demo_command_smoke.py \
        -m "not slow" \
        -q \
        "${PYTEST_EXTRA_ARGS[@]+"${PYTEST_EXTRA_ARGS[@]}"}"

echo ""
echo "========================================"
echo "All local quick checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
echo ""
echo "Reminder: local quick check is a convenience gate only."
echo "Run ./scripts/release_check.sh --full before push/tag."
