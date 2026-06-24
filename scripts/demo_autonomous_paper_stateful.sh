#!/usr/bin/env bash
# CAND-003 stateful autonomous paper demo
#
# Demonstrates stateful resume, a simulated fill, a risk rejection, hold
# decisions, honest cost/equity metrics, and redacted artifacts. The demo is
# paper-only, offline, and requires no credentials.
#
# Usage:
#   bash scripts/demo_autonomous_paper_stateful.sh
#   DEMO_WORKSPACE=/path/to/empty/dir bash scripts/demo_autonomous_paper_stateful.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

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
  WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-agent-cand003-demo.XXXXXX")"
fi

cleanup() {
  if [ -z "${DEMO_WORKSPACE:-}" ] && [ -e "$WORKSPACE" ]; then
    rm -rf "$WORKSPACE"
  fi
}
trap cleanup EXIT

# Build a minimal, self-contained Atlas workspace so the demo does not touch
# the user's default workspace or home-directory config.
mkdir -p "$WORKSPACE/.atlas" "$WORKSPACE/memory"

cat > "$WORKSPACE/.atlas/discipline.md" <<'EOF'
# Atlas User Discipline Profile

## Decision temperament

Cautious and evidence-seeking.

## Reasoning style

Step-by-step and transparent.

## Communication style

Concise, structured, and respectful.

## Risk posture

Conservative.

## Uncertainty handling

Explicitly state confidence levels.

## No-trade bias

Default to no action unless the case is compelling.

## Forbidden overrides

User discipline cannot override Atlas risk gates, approval queues, kill switch, audit logging, broker sync checks, reference price requirements, or live-trading safeguards.
EOF

# Use a small max_order_notional so that later buy orders are rejected while the
# opening buy is allowed. initial_cash and position_pct are set so the first
# order is just under the limit and later orders exceed it.
cat > "$WORKSPACE/.atlas/config.toml" <<'EOF'
[market]
symbol = "DEMO"

[risk]
max_order_notional = 10250
max_position_notional = 20000

[backtest]
initial_cash = 50000
EOF

# Copy sample data into the workspace and rewrite the symbol to DEMO so the
# demo can use a concise ticker while still exercising the real sample OHLCV.
awk -F, 'NR==1 {print; next} {gsub(/DEMO-SYMBOL/, "DEMO"); print}' "$SAMPLE_DATA" \
  > "$WORKSPACE/data.csv"

mkdir -p "$WORKSPACE/state" "$WORKSPACE/output"

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

atlas() {
  "$PYTHON_BIN" -m atlas_agent.cli --workspace "$WORKSPACE" "$@"
}

run_step() {
  printf '\n$ atlas %s\n' "$*"
  atlas "$@"
}

printf 'Atlas Agent CAND-003 stateful autonomous paper demo\n'
printf 'Workspace: %s\n' "$WORKSPACE"
printf 'Symbol: DEMO\n'
printf 'Strategy: demo_stateful_paper (deterministic demo strategy)\n'
printf 'This demo is paper-only, offline, and requires no credentials.\n'

# First run: initialise state, process the first five bars, and record a fill.
run_step agent autonomous-paper \
  --symbol DEMO \
  --strategy demo_stateful_paper \
  --strategy-param position_pct=0.2 \
  --data-path data.csv \
  --max-cycles 5 \
  --state-dir state \
  --evidence-dir output \
  --commission-bps 2 \
  --slippage-bps 2 \
  --fill-timing next_bar \
  --json

# Resume: continue from the next unprocessed bar. The deterministic demo
# strategy exits the opening position and then attempts additional entries that
# are blocked by the small max_order_notional limit.
run_step agent autonomous-paper \
  --symbol DEMO \
  --strategy demo_stateful_paper \
  --strategy-param position_pct=0.2 \
  --data-path data.csv \
  --max-cycles 0 \
  --state-dir state \
  --resume \
  --evidence-dir output \
  --commission-bps 2 \
  --slippage-bps 2 \
  --fill-timing next_bar \
  --json

METRICS_FILE="$(find "$WORKSPACE/output" -name '*-metrics.json' | head -n 1)"
DECISIONS_FILE="$(find "$WORKSPACE/output" -name '*-decisions.jsonl' | head -n 1)"

if [ -z "$METRICS_FILE" ] || [ -z "$DECISIONS_FILE" ]; then
  printf 'Missing expected output artifacts.\n' >&2
  exit 1
fi

printf '\n=== Verifying artifacts ===\n'

"$PYTHON_BIN" - "$WORKSPACE" "$METRICS_FILE" "$DECISIONS_FILE" <<'PY'
import json
import os
import pathlib
import sys

workspace = pathlib.Path(sys.argv[1])
metrics_path = pathlib.Path(sys.argv[2])
decisions_path = pathlib.Path(sys.argv[3])

metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
decisions = [
    json.loads(line)
    for line in decisions_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

assert metrics["number_of_fills"] >= 1, "expected at least one fill"
assert metrics["number_of_rejections"] >= 1, "expected at least one risk rejection"
assert metrics["total_commission"] > 0, "expected positive total commission"
assert metrics["total_slippage"] >= 0, "expected non-negative total slippage"
assert "total_return_pct" in metrics, "expected total_return_pct in metrics"
assert any(d.get("decision_state") == "no_trade" for d in decisions), \
    "expected at least one hold (no_trade) decision"

# Ensure persisted artifacts do not leak home-directory paths.
for subdir in ("output", "state"):
    root = workspace / subdir
    if not root.exists():
        continue
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "/Users/" in text:
            print(f"FAIL: home directory path leaked in {path}", file=sys.stderr)
            sys.exit(1)

print("fills:", metrics["number_of_fills"])
print("rejections:", metrics["number_of_rejections"])
print("commission:", metrics["total_commission"])
print("slippage:", metrics["total_slippage"])
print("total_return_pct:", metrics["total_return_pct"])
print("bars_processed:", metrics["bars_processed"])
print("no_trade_decisions:", sum(1 for d in decisions if d.get("decision_state") == "no_trade"))
PY

printf '\n=== CAND-003 stateful autonomous paper demo PASS ===\n'
printf 'Stateful resume worked, produced fills, holds, risk rejections,\n'
printf 'cost/equity metrics, and redacted artifacts.\n'
