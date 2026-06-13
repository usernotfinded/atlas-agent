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
echo "0. release metadata"
SECONDS=0
"$PYTHON_BIN" scripts/check_release_metadata.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"


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
echo "3. env template checks"
SECONDS=0
"$PYTHON_BIN" scripts/check_env_templates.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "3a. packaged template integrity check"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_template_packaging.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4. forbidden claims scan"
SECONDS=0
"$PYTHON_BIN" scripts/check_forbidden_claims.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "5. trust center check"
SECONDS=0
"$PYTHON_BIN" scripts/check_trust_center.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "6. onboarding docs check"
SECONDS=0
"$PYTHON_BIN" scripts/check_onboarding_docs.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "7. generated artifact hygiene check"
SECONDS=0
"$PYTHON_BIN" scripts/check_generated_artifacts.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "8. GitHub Actions version check"
SECONDS=0
"$PYTHON_BIN" scripts/check_github_actions_versions.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "9. feedback intake check"
SECONDS=0
"$PYTHON_BIN" scripts/check_feedback_intake.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "10. feedback taxonomy check"
SECONDS=0
"$PYTHON_BIN" scripts/check_feedback_taxonomy.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "11. reviewer outreach check"
SECONDS=0
"$PYTHON_BIN" scripts/check_reviewer_outreach.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "12. product capability inventory check"
SECONDS=0
"$PYTHON_BIN" scripts/check_product_capability_inventory.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13. v0.5.8 gap prioritization check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v058_gap_prioritization.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13a. v0.5.8 RC1 readiness dry run"
SECONDS=0
"$PYTHON_BIN" scripts/check_v058_rc1_readiness.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "13b. v0.5.8.1 hotfix cutover check"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0581_hotfix_cutover.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "14. generated artifact hygiene tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_generated_artifacts.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "15. GitHub Actions version tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_github_actions_versions.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "16. research sandbox CLI tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/research/test_research_sandbox_cli.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "17. reviewer golden-path smoke tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_reviewer_golden_path_smoke.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "18. env template tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_env_templates.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "19. release check script tests"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_release_check_scripts.py -q "${PYTEST_EXTRA_ARGS[@]}"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "20. git diff --check"
SECONDS=0
git diff --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "21. git diff --cached --check"
SECONDS=0
git diff --cached --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "22. protected staged files"
SECONDS=0
"$PYTHON_BIN" scripts/check_no_protected_staged.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "All dev checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
