#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

BACKTEST_SYMBOL="${BACKTEST_SYMBOL:-DEMO-SYMBOL}"
SAMPLE_DATA_REL="data/sample/ohlcv.csv"
STRATEGIES="${STRATEGIES:-buy_and_hold,moving_average_cross,rsi_mean_reversion}"

unset OPENAI_API_KEY
unset OPENROUTER_API_KEY
unset ANTHROPIC_API_KEY
unset GEMINI_API_KEY
unset GOOGLE_API_KEY
unset MOONSHOT_API_KEY
unset KIMI_API_KEY
unset XAI_API_KEY
unset GROK_API_KEY

cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -f "$SAMPLE_DATA_REL" ]; then
  printf 'Missing prerequisite: sample data not found at %s\n' "$SAMPLE_DATA_REL" >&2
  exit 1
fi

if [ -n "${DEMO_OUTPUT_DIR:-}" ]; then
  OUTPUT_DIR="$DEMO_OUTPUT_DIR"
  if [ -e "$OUTPUT_DIR" ]; then
    printf 'Refusing to reuse existing DEMO_OUTPUT_DIR: %s\n' "$OUTPUT_DIR" >&2
    exit 1
  fi
  CLEANUP_OUTPUT=0
else
  OUTPUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/atlas-paper-strategy-evaluation.XXXXXX")"
  CLEANUP_OUTPUT=1
fi

cleanup() {
  if [ "$CLEANUP_OUTPUT" = "1" ] && [ -e "$OUTPUT_DIR" ]; then
    rm -rf "$OUTPUT_DIR"
  fi
}
trap cleanup EXIT

atlas() {
  "$PYTHON_BIN" -m atlas_agent.cli "$@"
}

printf 'Atlas Agent paper strategy evaluation demo\n'
printf 'Output directory: %s\n' "$OUTPUT_DIR"
printf 'Symbol: %s\n' "$BACKTEST_SYMBOL"
printf 'Strategies: %s\n' "$STRATEGIES"
printf 'This demo is paper-only, offline, and requires no credentials.\n'
printf 'Guide: docs/paper-strategy-evaluation.md\n'

atlas backtest compare \
  --data "$SAMPLE_DATA_REL" \
  --symbol "$BACKTEST_SYMBOL" \
  --strategies "$STRATEGIES" \
  --output-dir "$OUTPUT_DIR"

REPORT_JSON="$OUTPUT_DIR/strategy-evaluation.json"
REPORT_MD="$OUTPUT_DIR/strategy-evaluation.md"

if [ ! -f "$REPORT_JSON" ]; then
  printf 'Expected JSON report missing: %s\n' "$REPORT_JSON" >&2
  exit 1
fi

if [ ! -f "$REPORT_MD" ]; then
  printf 'Expected Markdown report missing: %s\n' "$REPORT_MD" >&2
  exit 1
fi

EXPECTED_SYMBOL="$BACKTEST_SYMBOL" REPORT_JSON="$REPORT_JSON" REPORT_MD="$REPORT_MD" "$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

report_json = Path(os.environ["REPORT_JSON"])
report_md = Path(os.environ["REPORT_MD"])
payload = json.loads(report_json.read_text(encoding="utf-8"))

allowed = {"paper_candidate", "needs_more_testing", "rejected"}
for key in (
    "provider_required",
    "broker_required",
    "network_required",
    "live_readiness",
):
    if payload.get(key) is not False:
        raise SystemExit(f"{key} must be false")

if payload.get("artifact_type") != "paper_strategy_evaluation":
    raise SystemExit("unexpected artifact_type")
if payload.get("schema_version") != 1:
    raise SystemExit("unexpected schema_version")
if payload.get("mode") != "paper":
    raise SystemExit("mode must be paper")
if payload.get("not_financial_advice") is not True:
    raise SystemExit("not_financial_advice must be true")
if payload.get("symbol") != os.environ["EXPECTED_SYMBOL"]:
    raise SystemExit("unexpected symbol")
if payload.get("data_source") != "data/sample/ohlcv.csv":
    raise SystemExit("unexpected data_source")
if not payload.get("strategies"):
    raise SystemExit("at least one strategy is required")
if not payload.get("ranking"):
    raise SystemExit("ranking is required")

for item in payload["strategies"]:
    if item.get("live_ready") is not False:
        raise SystemExit("strategy live_ready must be false")
    decision = item.get("paper_gate", {}).get("decision")
    if decision not in allowed:
        raise SystemExit(f"unexpected paper gate decision: {decision}")

if not report_md.read_text(encoding="utf-8").strip():
    raise SystemExit("markdown report is empty")
PY

printf '\n=== Paper strategy evaluation demo PASS ===\n'
printf 'Generated strategy-evaluation.json and strategy-evaluation.md.\n'
printf 'No live trading, broker calls, provider calls, network calls, or credentials.\n'
