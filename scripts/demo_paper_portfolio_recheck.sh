#!/usr/bin/env bash
set -euo pipefail

echo "Atlas Agent paper portfolio recheck ledger demo"

DEMO_DIR=$(mktemp -d -t atlas-paper-portfolio-recheck.XXXXXX)

python3.11 -m atlas_agent.cli backtest portfolio-recheck \
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

if [[ ! -f "${DEMO_DIR}/paper-portfolio-recheck-ledger.json" ]]; then
  echo "Error: json recheck report not found"
  exit 1
fi

if [[ ! -f "${DEMO_DIR}/paper-portfolio-review-queue.md" ]]; then
  echo "Error: markdown recheck report not found"
  exit 1
fi

python3.11 - "${DEMO_DIR}/paper-portfolio-recheck-ledger.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
allowed_status = {
    "paper_review_clear",
    "paper_review_watchlist",
    "paper_recheck_required",
    "paper_rejected",
}

assert data["artifact_type"] == "paper_portfolio_recheck_ledger"
assert data["mode"] == "paper"
assert data["provider_required"] is False
assert data["broker_required"] is False
assert data["network_required"] is False
assert data["live_readiness"] is False
assert data["safety"]["no_live_trading"] is True
assert data["safety"]["no_broker_calls"] is True
assert data["safety"]["no_provider_calls"] is True
assert data["safety"]["no_notifications_sent"] is True
assert data["overall_review_status"] in allowed_status

for item in data["review_items"]:
    assert item["status"] in allowed_status

for item in data["review_queue"]:
    assert "human_review_required" in item
    assert "paper_action" in item
PY

echo "=== Paper portfolio recheck ledger demo PASS ==="
echo "Generated paper-portfolio-recheck-ledger.json and paper-portfolio-review-queue.md."
echo "No live trading, broker calls, provider calls, network calls, notifications, or credentials."
