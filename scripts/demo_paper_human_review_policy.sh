#!/usr/bin/env bash
set -euo pipefail

# Safety: this demo performs no real human approval and no live trading.

echo "Atlas Agent paper human review policy simulation demo"

DEMO_DIR=$(mktemp -d -t atlas-paper-human-review-policy.XXXXXX)

python3.11 -m atlas_agent.cli backtest portfolio-review-policy \
  --symbol "DEMO-SYMBOL" \
  --data "data/sample/ohlcv_extended.csv" \
  --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
  --max-strategy-weight 0.40 \
  --min-cash-weight 0.10 \
  --max-stressed-drawdown 0.25 \
  --max-single-scenario-loss 0.20 \
  --monitor-window 20 \
  --recheck-threshold 0.05 \
  --output-dir "${DEMO_DIR}"

if [[ ! -f "${DEMO_DIR}/paper-human-review-policy.json" ]]; then
  echo "Error: JSON review policy report not found"
  exit 1
fi

if [[ ! -f "${DEMO_DIR}/paper-human-review-policy.md" ]]; then
  echo "Error: Markdown review policy report not found"
  exit 1
fi

python3.11 - "${DEMO_DIR}/paper-human-review-policy.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
allowed_status = {
    "paper_policy_passed_with_live_blocked",
    "paper_policy_needs_more_evidence",
    "paper_policy_manual_review_required",
    "paper_policy_blocked",
}

assert data["artifact_type"] == "paper_human_review_policy"
assert data["schema_version"] == 1
assert data["release"] == "v0.6.15-planning"
assert data["source_release"] == "v0.6.14"
assert data["mode"] == "paper"
assert data["non_executable"] is True
assert data["paper_only"] is True
assert data["provider_required"] is False
assert data["broker_required"] is False
assert data["network_required"] is False
assert data["live_submit_enabled"] is False
assert data["orders_generated"] is False
assert data["notifications_sent"] is False
assert data["real_human_approval"] is False
assert data["not_financial_advice"] is True
assert data["not_live_ready"] is True
assert data["gate_summary"]["live_path_blocked"] is True
assert data["gate_summary"]["broker_submission_allowed"] is False
assert data["gate_summary"]["provider_execution_allowed"] is False
assert data["gate_summary"]["notification_sending_allowed"] is False
assert data["gate_summary"]["real_order_generation_allowed"] is False
assert data["gate_summary"]["paper_follow_up_allowed"] is True
assert data["overall_policy_status"] in allowed_status
assert len(data["policy_results"]) >= 10

PY

echo "=== Paper human review policy simulation demo PASS ==="
echo "Generated paper-human-review-policy.json and paper-human-review-policy.md."
echo "Output is non-executable. No live trading, broker calls, provider calls, network calls, notifications, real human approval, or credentials."
