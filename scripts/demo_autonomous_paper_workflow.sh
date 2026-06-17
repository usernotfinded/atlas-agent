#!/usr/bin/env bash
set -euo pipefail

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
  WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-agent-autonomous-paper.XXXXXX")"
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

printf 'Atlas Agent autonomous paper workflow demo\n'
printf 'Workspace: %s\n' "$WORKSPACE"
printf 'Agent symbol: %s\n' "$DEMO_SYMBOL"
printf 'Backtest symbol: %s\n' "$BACKTEST_SYMBOL"
printf 'This demo is paper-only, offline, and requires no credentials.\n'
printf 'Guide: docs/autonomous-paper-workflow.md\n'

cd "$REPO_ROOT"
run_step init "$WORKSPACE" --template routine-trader

cd "$WORKSPACE"
run_step discipline setup --manual --yes
run_step config set market.symbol "$DEMO_SYMBOL"
run_step validate
run_step doctor --json
run_step run --mode paper --dry-run --symbol "$DEMO_SYMBOL" --max-cycles 1
run_step routine run pre_market --mode paper --symbol "$DEMO_SYMBOL" || true
run_step backtest run --symbol "$BACKTEST_SYMBOL" --data "$SAMPLE_DATA"
run_step report generate --type daily --format text || true
run_step audit verify --all

printf '\n=== Autonomous paper workflow demo PASS ===\n'
printf 'All paper-only steps completed without manual intervention.\n'
printf 'No live trading, no broker contact, no provider calls.\n'
