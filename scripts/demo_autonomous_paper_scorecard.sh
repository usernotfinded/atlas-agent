#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/demo_autonomous_paper_scorecard.sh
# PURPOSE: Demonstrates the autonomous paper scorecard workflow using safe local
#         defaults.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

DEMO_SYMBOL="${DEMO_SYMBOL:-ATLAS-DEMO}"
BACKTEST_SYMBOL="${BACKTEST_SYMBOL:-DEMO-SYMBOL}"
SAMPLE_DATA="$REPO_ROOT/data/sample/ohlcv.csv"

if [ ! -f "$SAMPLE_DATA" ]; then
  printf 'Missing prerequisite: sample data not found at %s\n' "$SAMPLE_DATA" >&2
  exit 1
fi

if [ -n "${DEMO_WORKSPACE:-}" ]; then
  WORKSPACE="$DEMO_WORKSPACE"
  if [ -e "$WORKSPACE" ]; then
    printf 'Refusing to reuse existing DEMO_WORKSPACE: %s\n' "$WORKSPACE" >&2
    exit 1
  fi
else
  WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-agent-autonomous-paper-scorecard.XXXXXX")"
fi

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

cleanup() {
  if [ -z "${DEMO_WORKSPACE:-}" ] && [ -e "$WORKSPACE" ]; then
    rm -rf "$WORKSPACE"
  fi
}
trap cleanup EXIT

atlas() {
  "$PYTHON_BIN" -m atlas_agent.cli "$@"
}

run_step() {
  printf '\n$ atlas %s\n' "$*"
  atlas "$@"
}

printf 'Atlas Agent autonomous paper scorecard demo\n'
printf 'Workspace: %s\n' "$WORKSPACE"
printf 'Agent symbol: %s\n' "$DEMO_SYMBOL"
printf 'Backtest symbol: %s\n' "$BACKTEST_SYMBOL"
printf 'This demo is paper-only, offline, and requires no credentials.\n'
printf 'Guide: docs/autonomous-paper-scorecard.md\n'

cd "$REPO_ROOT"
run_step init "$WORKSPACE" --template routine-trader

cd "$WORKSPACE"
run_step discipline setup --manual --yes
run_step config set market.symbol "$DEMO_SYMBOL"
run_step validate

EVIDENCE_DIR="$WORKSPACE/evidence"
SCORECARD_DIR="$WORKSPACE/scorecard"

run_step agent autonomous-paper \
  --symbol "$BACKTEST_SYMBOL" \
  --strategy moving_average_cross \
  --data-path "$SAMPLE_DATA" \
  --max-cycles 5 \
  --evidence-dir "$EVIDENCE_DIR" \
  --json

RUN_ID="$(ls "$EVIDENCE_DIR")"
run_step agent autonomous-scorecard \
  --decisions "$EVIDENCE_DIR/$RUN_ID/decisions.jsonl" \
  --manifest "$EVIDENCE_DIR/$RUN_ID/manifest.json" \
  --output-dir "$SCORECARD_DIR" \
  --json

printf '\n=== Autonomous paper scorecard demo PASS ===\n'
printf 'Scorecard reports written to: %s\n' "$SCORECARD_DIR"
printf 'No live trading, no broker contact, no provider calls.\n'
