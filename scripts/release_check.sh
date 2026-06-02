#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"

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
  --quick     Fast dev check (cheap loop for active development).
              Runs: version, claims, sandbox CLI tests, release script tests,
                    git diff checks, protected-staged check.
  --research  Research/sandbox gate (medium cost).
              Runs: version, claims, full research tests, research demo,
                    git diff checks, protected-staged check.
  --full      Full release gate (default). Required before push/tag.
              Runs: everything in --research plus full pytest, pip check,
                    paper demo, research demo.
  --help, -h  Show this help message.

Environment:
  PYTHON_BIN                    Python interpreter to use (default: python3.11).
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
$PYTHON_BIN -m pytest -q

echo ""
echo "========================================"
echo "2. pip check"
echo "========================================"
$PYTHON_BIN -m pip check

echo ""
echo "========================================"
echo "3. reviewer golden-path smoke"
echo "========================================"
$PYTHON_BIN scripts/smoke_reviewer_golden_path.py --skip-release-check

echo ""
echo "========================================"
echo "4. demo paper workflow"
echo "========================================"
./scripts/demo_paper_workflow.sh

echo ""
echo "========================================"
echo "5. demo research workflow"
echo "========================================"
./scripts/demo_research_workflow.sh

echo ""
echo "========================================"
echo "6. git diff --check"
echo "========================================"
git diff --check

echo ""
echo "========================================"
echo "7. git diff --cached --check"
echo "========================================"
git diff --cached --check

echo ""
echo "========================================"
echo "8. protected staged files"
echo "========================================"
$PYTHON_BIN scripts/check_no_protected_staged.py

echo ""
echo "========================================"
echo "9. version consistency"
echo "========================================"
$PYTHON_BIN scripts/check_version_consistency.py

echo ""
echo "========================================"
echo "10. forbidden claims scan"
echo "========================================"
$PYTHON_BIN scripts/check_forbidden_claims.py

echo ""
echo "========================================"
echo "All release checks passed."
echo "========================================"
