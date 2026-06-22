#!/usr/bin/env bash
set -euo pipefail

echo "Atlas Agent paper human review pack demo"

DEMO_DIR=$(mktemp -d -t atlas-paper-human-review-pack.XXXXXX)

python3.11 -m atlas_agent.cli backtest portfolio-review-pack \
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

if [[ ! -f "${DEMO_DIR}/paper-human-review-pack.json" ]]; then
  echo "Error: JSON review pack report not found"
  exit 1
fi

if [[ ! -f "${DEMO_DIR}/paper-human-review-pack.md" ]]; then
  echo "Error: Markdown review pack report not found"
  exit 1
fi

python3.11 - "${DEMO_DIR}/paper-human-review-pack.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
allowed_status = {
    "paper_review_pack_open",
    "paper_review_pack_follow_up",
    "paper_review_pack_rejected",
}
allowed_item_status = {
    "needs_human_review",
    "needs_more_paper_testing",
    "rejected_from_review",
    "paper_only_follow_up",
}

assert data["artifact_type"] == "paper_human_review_pack"
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
assert data["not_financial_advice"] is True
assert data["not_live_ready"] is True
assert data["overall_review_pack_status"] in allowed_status
assert len(data["review_items"]) >= 1

for item in data["review_items"]:
    assert item["type"] == "paper_review_item"
    assert item["status"] in allowed_item_status
    assert item["non_executable_action"] == "paper_only_follow_up"

assert data["safety"]["no_live_trading"] is True
assert data["safety"]["no_broker_calls"] is True
assert data["safety"]["no_provider_calls"] is True
assert data["safety"]["no_notifications_sent"] is True
assert data["safety"]["no_orders_generated"] is True
assert data["safety"]["non_executable"] is True
assert data["safety"]["paper_only"] is True

PY

echo "=== Paper human review pack demo PASS ==="
echo "Generated paper-human-review-pack.json and paper-human-review-pack.md."
echo "Output is non-executable. No live trading, broker calls, provider calls, network calls, notifications, or credentials."

