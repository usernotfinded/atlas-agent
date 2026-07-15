#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/demo_autonomous_paper_quality.sh
# PURPOSE: Demonstrates the autonomous paper quality workflow using safe local
#         defaults.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---

# CAND-004 deterministic autonomous paper trading-quality gate demo
#
# Runs the stateful autonomous-paper loop offline to generate artifacts, then
# evaluates them with the trading-quality gate. The demo is paper-only,
# deterministic, requires no credentials, and exits non-zero if the quality
# state is `not_evaluated` or `blocked`.
#
# Usage:
#   bash scripts/demo_autonomous_paper_quality.sh
#   DEMO_WORKSPACE=/path/to/empty/dir bash scripts/demo_autonomous_paper_quality.sh

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
  WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-agent-cand004-demo.XXXXXX")"
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

mkdir -p "$WORKSPACE/state" "$WORKSPACE/output" "$WORKSPACE/quality"

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

atlas() {
  "$PYTHON_BIN" -m atlas_agent.cli --workspace "$WORKSPACE" "$@"
}

printf 'Atlas Agent CAND-004 autonomous paper trading-quality gate demo\n'
printf 'Workspace: %s\n' "$WORKSPACE"
printf 'Symbol: DEMO\n'
printf 'Strategy: demo_stateful_paper (deterministic demo strategy)\n'
printf 'This demo is paper-only, offline, and requires no credentials.\n'

# Step 1: run the stateful autonomous paper loop if fresh artifacts are absent.
if [ ! -f "$WORKSPACE/output/"*-metrics.json ] || \
   [ ! -f "$WORKSPACE/output/"*-decisions.jsonl ] || \
   [ ! -f "$WORKSPACE/output/"*-fills.jsonl ] || \
   [ ! -f "$WORKSPACE/state/"*-state.json ]; then
  printf '\n=== Generating stateful autonomous paper artifacts ===\n'

  atlas agent autonomous-paper \
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

  # Resume to process the remaining bars and produce additional rejections.
  atlas agent autonomous-paper \
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
else
  printf '\n=== Reusing existing artifacts ===\n'
fi

METRICS_FILE="$(find "$WORKSPACE/output" -name '*-metrics.json' | head -n 1)"
DECISIONS_FILE="$(find "$WORKSPACE/output" -name '*-decisions.jsonl' | head -n 1)"
FILLS_FILE="$(find "$WORKSPACE/output" -name '*-fills.jsonl' | head -n 1)"
STATE_FILE="$(find "$WORKSPACE/state" -name '*-state.json' | head -n 1)"

if [ -z "$METRICS_FILE" ] || [ -z "$DECISIONS_FILE" ] || [ -z "$FILLS_FILE" ] || [ -z "$STATE_FILE" ]; then
  printf 'Missing expected autonomous-paper artifacts.\n' >&2
  exit 1
fi

printf '\n=== Artifact paths ===\n'
printf 'metrics:   %s\n' "$METRICS_FILE"
printf 'decisions: %s\n' "$DECISIONS_FILE"
printf 'fills:     %s\n' "$FILLS_FILE"
printf 'state:     %s\n' "$STATE_FILE"

# Step 2: evaluate artifacts with the trading-quality gate.
printf '\n=== Evaluating trading quality gate ===\n'
QUALITY_EXIT=0
atlas agent autonomous-paper-quality \
  --metrics "$METRICS_FILE" \
  --decisions "$DECISIONS_FILE" \
  --fills "$FILLS_FILE" \
  --state "$STATE_FILE" \
  --data-path data.csv \
  --output-dir quality || QUALITY_EXIT=$?

QUALITY_JSON="$WORKSPACE/quality/trading-quality-gate.json"
if [ ! -f "$QUALITY_JSON" ]; then
  printf 'Missing expected trading-quality-gate.json output.\n' >&2
  exit 1
fi

QUALITY_STATE="$("$PYTHON_BIN" -c "import json,sys; print(json.load(open('${QUALITY_JSON}', encoding='utf-8'))['quality_state'])")"

printf '\n=== Quality gate result ===\n'
printf 'Quality state: %s\n' "$QUALITY_STATE"

# Step 3: print summary metrics from the quality gate report.
"$PYTHON_BIN" - "$QUALITY_JSON" <<'PY'
import json
import sys

report = json.loads(open(sys.argv[1], encoding="utf-8").read())
metrics = report.get("metrics", {})
dimensions = {d["name"]: d for d in report.get("dimensions", [])}

def p(label, value):
    print(f"{label}: {value}")

def dim_reason(name):
    return dimensions.get(name, {}).get("reason", "n/a")

p("fills", metrics.get("number_of_fills", "n/a"))
p("no-trades", dim_reason("no_trade_coverage"))
p("risk_rejections", metrics.get("number_of_rejections", "n/a"))
p("total_commission", metrics.get("total_commission", "n/a"))
p("total_slippage", metrics.get("total_slippage", "n/a"))
p("total_return_pct", metrics.get("total_return_pct", "n/a"))
p("drawdown", dim_reason("drawdown_bounds"))
p("exposure", dim_reason("exposure_bounds"))
p("turnover", dim_reason("turnover_bounds"))
if report.get("benchmark"):
    benchmark = report["benchmark"]
    if benchmark.get("available"):
        p("benchmark", benchmark)
PY

printf '\n=== Artifact output paths ===\n'
printf 'quality JSON: %s\n' "$QUALITY_JSON"
printf 'quality MD:   %s\n' "$WORKSPACE/quality/trading-quality-report.md"

# Step 4: fail the demo if the gate did not pass.
if [ "$QUALITY_STATE" = "not_evaluated" ] || [ "$QUALITY_STATE" = "blocked" ]; then
  printf '\nDemo failed quality gate (%s).\n' "$QUALITY_STATE" >&2
  exit 1
fi

printf '\n=== CAND-004 autonomous paper trading-quality gate demo PASS ===\n'
printf 'Quality state "%s" is acceptable. Review artifacts in %s.\n' "$QUALITY_STATE" "$WORKSPACE/quality"
