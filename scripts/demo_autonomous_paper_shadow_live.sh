#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/demo_autonomous_paper_shadow_live.sh
# PURPOSE: Demonstrates the autonomous paper shadow live workflow using safe
#         local defaults.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---

# CAND-005 deterministic shadow-live read-only comparison demo
#
# Runs the stateful autonomous-paper loop offline, evaluates it with the
# CAND-004 trading-quality gate, constructs a local broker snapshot fixture,
# and performs a read-only shadow-live comparison. The demo is paper-only,
# deterministic, requires no credentials, no network, and no broker API.
#
# The broker snapshot deliberately matches paper cash and deliberately diverges
# on equity so the comparison produces a visible (but non-blocking)
# minor_divergence result.
#
# Usage:
#   bash scripts/demo_autonomous_paper_shadow_live.sh
#   DEMO_WORKSPACE=/path/to/empty/dir bash scripts/demo_autonomous_paper_shadow_live.sh

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
  WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-agent-cand005-demo.XXXXXX")"
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

mkdir -p "$WORKSPACE/state" "$WORKSPACE/output" "$WORKSPACE/quality" "$WORKSPACE/shadow_live"

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

atlas() {
  "$PYTHON_BIN" -m atlas_agent.cli --workspace "$WORKSPACE" "$@"
}

printf 'Atlas Agent CAND-005 shadow-live read-only comparison demo\n'
printf 'Workspace: %s\n' "$WORKSPACE"
printf 'Symbol: DEMO\n'
printf 'Strategy: demo_stateful_paper (deterministic demo strategy)\n'
printf 'This demo is paper-only, offline, and requires no credentials or broker API.\n'

# Step 1: run the stateful autonomous paper loop to generate artifacts.
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

# Step 2: evaluate artifacts with the CAND-004 trading-quality gate.
printf '\n=== Evaluating trading quality gate ===\n'
atlas agent autonomous-paper-quality \
  --metrics "$METRICS_FILE" \
  --decisions "$DECISIONS_FILE" \
  --fills "$FILLS_FILE" \
  --state "$STATE_FILE" \
  --data-path data.csv \
  --output-dir quality \
  --json

QUALITY_JSON="$WORKSPACE/quality/trading-quality-gate.json"
if [ ! -f "$QUALITY_JSON" ]; then
  printf 'Missing expected trading-quality-gate.json output.\n' >&2
  exit 1
fi

QUALITY_STATE="$("$PYTHON_BIN" -c "import json,sys; print(json.load(open('${QUALITY_JSON}', encoding='utf-8'))['quality_state'])")"
if [ "$QUALITY_STATE" != "eligible_for_shadow_live_quality_review" ]; then
  printf 'Quality gate state is "%s", expected "eligible_for_shadow_live_quality_review".\n' "$QUALITY_STATE" >&2
  exit 1
fi

printf 'Quality state: %s\n' "$QUALITY_STATE"

# Step 3: write a local broker snapshot fixture.
printf '\n=== Writing local broker snapshot fixture ===\n'
BROKER_SNAPSHOT="$WORKSPACE/broker-snapshot.json"
"$PYTHON_BIN" - "$METRICS_FILE" "$BROKER_SNAPSHOT" <<'PY'
import datetime
import json
import sys

metrics_path = sys.argv[1]
snapshot_path = sys.argv[2]
metrics = json.loads(open(metrics_path, encoding="utf-8").read())

paper_cash = metrics["ending_cash"]
paper_equity = metrics["ending_equity"]

# Match paper cash exactly; diverge equity by ~2% so the demo shows a minor
# divergence without blocking.
snapshot = {
    "schema_version": "shadow-live-snapshot.v1",
    "account_label": "paper-shadow-001",
    "broker_source": "local-fixture",
    "currency": "USD",
    "cash": paper_cash,
    "equity": paper_equity * 1.02,
    "buying_power": paper_cash,
    "market_timestamp": None,
    "snapshot_freshness_timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "positions": [],
    "open_orders": [],
    "recent_fills": [],
    "completeness_flags": {
        "account": True,
        "positions": True,
        "open_orders": True,
        "recent_fills": True,
        "market_prices": True,
    },
}
open(snapshot_path, "w", encoding="utf-8").write(json.dumps(snapshot, indent=2) + "\n")
print(f"paper cash: {paper_cash:.4f}")
print(f"paper equity: {paper_equity:.4f}")
print(f"broker equity (diverged): {snapshot['equity']:.4f}")
PY

# Step 4: run the CAND-005 shadow-live read-only comparison.
printf '\n=== Running shadow-live comparison ===\n'
SHADOW_EXIT=0
atlas agent shadow-live \
  --quality-gate "$QUALITY_JSON" \
  --broker-snapshot "$BROKER_SNAPSHOT" \
  --output-dir shadow_live \
  --state "$STATE_FILE" \
  --metrics "$METRICS_FILE" \
  --decisions "$DECISIONS_FILE" \
  --fills "$FILLS_FILE" || SHADOW_EXIT=$?

SHADOW_JSON="$WORKSPACE/shadow_live/shadow-live-comparison.json"
SHADOW_MD="$WORKSPACE/shadow_live/shadow-live-report.md"

if [ ! -f "$SHADOW_JSON" ] || [ ! -f "$SHADOW_MD" ]; then
  printf 'Missing expected shadow-live artifacts.\n' >&2
  exit 1
fi

SHADOW_STATUS="$("$PYTHON_BIN" -c "import json,sys; print(json.load(open('${SHADOW_JSON}', encoding='utf-8'))['status'])")"

printf '\n=== Shadow-live result ===\n'
printf 'Status: %s\n' "$SHADOW_STATUS"
printf 'Comparison JSON: %s\n' "$SHADOW_JSON"
printf 'Report MD:       %s\n' "$SHADOW_MD"

# Step 5: fail closed if the comparison could not run or reported a blocking state.
if [ "$SHADOW_STATUS" != "matched" ] && [ "$SHADOW_STATUS" != "minor_divergence" ]; then
  printf '\nDemo failed: shadow-live status is "%s" (exit %s).\n' "$SHADOW_STATUS" "$SHADOW_EXIT" >&2
  exit 1
fi

printf '\n=== CAND-005 shadow-live read-only comparison demo PASS ===\n'
printf 'Status "%s" is acceptable. Review the report at %s.\n' "$SHADOW_STATUS" "$SHADOW_MD"
