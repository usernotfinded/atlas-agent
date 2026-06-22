#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

cd "$REPO_ROOT"

MODE="full"

if [[ "$#" -gt 0 ]]; then
    case "$1" in
        --quick)
            MODE="quick"
            shift
            ;;
        --research)
            MODE="research"
            shift
            ;;
        --full)
            MODE="full"
            shift
            ;;
        --help|-h)
            cat <<'EOF'
Usage: release_check.sh [OPTION]

Run release checks with tiered modes for local developer convenience.

Options:
  --quick     Delegates to ./scripts/dev_check.sh (full local development gate).
              Historically described as a minimal subset; in practice it runs
              all dev checks for safety. For a faster smoke loop, use
              ./scripts/smoke_check.sh. For a balanced pre-commit gate, use
              ./scripts/local_quick_check.sh.
  --research  Research/sandbox gate (medium cost).
              Runs: version, claims, full research tests, research demo,
                    git diff checks, protected-staged check.
  --full      Full release gate (default). Required before push/tag.
              Runs: everything in --research plus full pytest, pip check,
                    paper demo, research demo.
  --help, -h  Show this help message.

Environment:
  PYTHON_BIN                    Python interpreter to use (default: python3.11, then python).
  ATLAS_CHECK_FAIL_FAST=1       Pass -x to pytest invocations.
  ATLAS_CHECK_LAST_FAILED=1     Pass --lf to pytest invocations.
  ATLAS_CHECK_PYTEST_ARGS       Extra arguments appended to pytest invocations.

Quick/research modes are developer convenience checks only.
Full mode remains required before push/tag.
EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Run 'release_check.sh --help' for usage." >&2
            exit 1
            ;;
    esac
fi

if [[ "$#" -gt 0 ]]; then
    echo "Unknown trailing arguments: $*" >&2
    exit 1
fi

TOTAL_ELAPSED=0

echo "========================================"
echo "release check — mode: $MODE"
echo "========================================"

if [[ "$MODE" == "quick" ]]; then
    ./scripts/dev_check.sh
    exit 0
fi

if [[ "$MODE" == "research" ]]; then
    ./scripts/research_check.sh
    exit 0
fi

# Full mode — run everything directly
echo ""
echo "========================================"
echo "1. pytest"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" -m pytest -q
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "2. pip check"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" -m pip check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "3. reviewer golden-path smoke"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/smoke_reviewer_golden_path.py --skip-release-check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "4. demo paper workflow"
echo "========================================"
SECONDS=0
./scripts/demo_paper_workflow.sh
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "5. demo research workflow"
echo "========================================"
SECONDS=0
./scripts/demo_research_workflow.sh
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "5a. paper provider isolation check"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_paper_provider_isolation.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "5b. paper provider isolation tests"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_paper_provider_isolation.py -q
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "5c. paper strategy evaluation check"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_paper_strategy_evaluation.py
"$PYTHON_BIN" scripts/check_paper_strategy_sensitivity.py
"$PYTHON_BIN" scripts/check_paper_strategy_robustness.py
"$PYTHON_BIN" scripts/check_paper_strategy_walk_forward.py
"$PYTHON_BIN" scripts/check_paper_strategy_scorecard.py
"$PYTHON_BIN" scripts/check_paper_portfolio_proposal.py
"$PYTHON_BIN" scripts/check_paper_portfolio_stress.py
"$PYTHON_BIN" scripts/check_paper_portfolio_monitoring.py
"$PYTHON_BIN" scripts/check_paper_portfolio_recheck.py
"$PYTHON_BIN" scripts/check_paper_portfolio_dossier.py
"$PYTHON_BIN" scripts/check_paper_portfolio_replay.py
"$PYTHON_BIN" scripts/check_v0614_paper_portfolio_evidence.py
"$PYTHON_BIN" scripts/check_v0614_final_readiness_audit.py
"$PYTHON_BIN" scripts/check_v0613_paper_autonomy_evidence.py
"$PYTHON_BIN" scripts/check_v0613_final_reviewer_index.py
"$PYTHON_BIN" scripts/check_v0613_release_cutover_preflight.py
"$PYTHON_BIN" scripts/check_v0613_final_readiness_audit.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "4h. paper strategy evaluation tests"
SECONDS=0
if [[ "${QUICK_MODE:-0}" == "1" ]]; then
    echo "Skipping tests in quick mode."
else
    "$PYTHON_BIN" -m pytest tests/test_paper_strategy_evaluation.py tests/test_paper_strategy_sensitivity.py tests/test_paper_strategy_robustness.py tests/test_paper_strategy_walk_forward.py tests/test_paper_strategy_scorecard.py tests/test_paper_portfolio_proposal.py tests/test_paper_portfolio_stress.py tests/test_paper_portfolio_monitoring.py tests/test_paper_portfolio_recheck.py tests/test_paper_portfolio_dossier.py tests/test_paper_portfolio_replay.py tests/test_v0614_paper_portfolio_evidence.py tests/test_v0614_final_readiness_audit.py tests/test_v0613_paper_autonomy_evidence.py tests/test_v0613_final_reviewer_index.py tests/test_v0613_release_cutover_preflight.py tests/test_v0613_final_readiness_audit.py -q
fi
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "5d. paper strategy evaluation tests"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_paper_strategy_evaluation.py tests/test_paper_strategy_sensitivity.py tests/test_paper_strategy_robustness.py tests/test_paper_strategy_walk_forward.py tests/test_paper_strategy_scorecard.py tests/test_paper_portfolio_proposal.py tests/test_paper_portfolio_stress.py tests/test_paper_portfolio_monitoring.py tests/test_paper_portfolio_recheck.py tests/test_paper_portfolio_dossier.py tests/test_paper_portfolio_replay.py tests/test_v0614_paper_portfolio_evidence.py tests/test_v0614_final_readiness_audit.py tests/test_v0613_paper_autonomy_evidence.py tests/test_v0613_final_reviewer_index.py -q
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "6. git diff --check"
echo "========================================"
SECONDS=0
git diff --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "7. git diff --cached --check"
echo "========================================"
SECONDS=0
git diff --cached --check
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "8. protected staged files"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_no_protected_staged.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "8a. release metadata"
SECONDS=0
python scripts/check_release_metadata.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"


echo "9. version consistency"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_version_consistency.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "9i. v0.6.14 post-release hygiene check"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_v0614_post_release_hygiene.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "9j. v0.6.14 post-release hygiene tests"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_v0614_post_release_hygiene.py -q
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "10. forbidden claims scan"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_forbidden_claims.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "10a. bounded autonomy governance check"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_bounded_autonomy_governance.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "10b. bounded autonomy governance tests"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" -m pytest tests/test_bounded_autonomy_governance.py -q
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "11. product demo and marketplace readiness check"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_product_demo_pack.py
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "12. product demo walkthrough with evidence bundle"
echo "========================================"
SECONDS=0
PRODUCT_DEMO_EVIDENCE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/atlas-agent-release-evidence.XXXXXX")"
./scripts/demo_product_walkthrough.sh --output-dir "$PRODUCT_DEMO_EVIDENCE_DIR" --deterministic
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "13. product demo evidence check"
echo "========================================"
SECONDS=0
"$PYTHON_BIN" scripts/check_product_demo_evidence.py "$PRODUCT_DEMO_EVIDENCE_DIR"
TOTAL_ELAPSED=$((TOTAL_ELAPSED + SECONDS))
echo "  → elapsed: ${SECONDS}s"

echo ""
echo "========================================"
echo "All release checks passed."
echo "Total elapsed: ${TOTAL_ELAPSED}s"
echo "========================================"
