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
echo "dev check — fast local development gate"
echo "========================================"

echo ""
echo "1. version consistency"
SECONDS=0
"$PYTHON_BIN" scripts/check_version_consistency.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "2. CLI command compatibility"
SECONDS=0
"$PYTHON_BIN" scripts/check_cli_command_compatibility.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3. forbidden claims scan"
SECONDS=0
"$PYTHON_BIN" scripts/check_forbidden_claims.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4. trust center check"
SECONDS=0
"$PYTHON_BIN" scripts/check_trust_center.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "5. onboarding docs check"
SECONDS=0
"$PYTHON_BIN" scripts/check_onboarding_docs.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "6. generated artifact hygiene check"
SECONDS=0
"$PYTHON_BIN" scripts/check_generated_artifacts.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "7. GitHub Actions version check"
SECONDS=0
"$PYTHON_BIN" scripts/check_github_actions_versions.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8. feedback intake check"
SECONDS=0
"$PYTHON_BIN" scripts/check_feedback_intake.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "9. feedback taxonomy check"
SECONDS=0
"$PYTHON_BIN" scripts/check_feedback_taxonomy.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "10. reviewer outreach check"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_outreach.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "11. product capability inventory check"
SECONDS=0
"$PYTHON_BIN" scripts/check_product_capability_inventory.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "12. v0.5.8 gap prioritization check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v058_gap_prioritization.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "12a. v0.5.8 RC1 readiness dry run"
SECONDS=0
"$PYTHON_BIN" scripts/check_v058_rc1_readiness.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "12b. v0.5.8.1 hotfix cutover check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0581_hotfix_cutover.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13. generated artifact hygiene tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_generated_artifacts.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "14. GitHub Actions version tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_github_actions_versions.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "15. research sandbox CLI tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/research/test_research_sandbox_cli.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "16. reviewer golden-path smoke tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_reviewer_golden_path_smoke.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "17. release check script tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_check_scripts.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "18. git diff --check"
SECONDS=0
git diff --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "19. git diff --cached --check"
SECONDS=0
git diff --cached --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "20. protected staged files"
SECONDS=0
"$PYTHON_BIN" scripts/check_no_protected_staged.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "All dev checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
