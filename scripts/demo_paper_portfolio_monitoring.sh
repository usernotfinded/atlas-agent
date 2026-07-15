#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/demo_paper_portfolio_monitoring.sh
# PURPOSE: Demonstrates the paper portfolio monitoring workflow using safe local
#         defaults.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


echo "Atlas Agent paper portfolio monitoring demo"

DEMO_DIR=$(mktemp -d -t atlas-paper-portfolio-monitoring.XXXXXX)

python3.11 -m atlas_agent.cli backtest portfolio-monitor \
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

if [[ ! -f "${DEMO_DIR}/paper-portfolio-monitoring.json" ]]; then
  echo "Error: json monitoring report not found"
  exit 1
fi

if [[ ! -f "${DEMO_DIR}/paper-portfolio-monitoring.md" ]]; then
  echo "Error: markdown monitoring report not found"
  exit 1
fi

python3.11 - "${DEMO_DIR}/paper-portfolio-monitoring.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
allowed = {
    "paper_monitor_ok",
    "paper_monitor_watchlist",
    "needs_recheck",
    "rejected",
}

assert data["artifact_type"] == "paper_portfolio_monitoring"
assert data["mode"] == "paper"
assert data["provider_required"] is False
assert data["broker_required"] is False
assert data["network_required"] is False
assert data["live_readiness"] is False
assert data["safety"]["no_live_trading"] is True
assert data["safety"]["no_broker_calls"] is True
assert data["safety"]["no_provider_calls"] is True
assert data["safety"]["no_notifications_sent"] is True
assert data["overall_monitoring_status"] in allowed
assert data["monitoring_rules"]["monitor_window"] == 20
assert data["monitoring_rules"]["recheck_threshold"] == 0.05
assert data["monitoring_rules"]["max_strategy_weight"] == 0.40
assert data["monitoring_rules"]["min_cash_weight"] == 0.10
for event in data["monitoring_events"]:
    assert event["status"] in allowed
PY

echo "=== Paper portfolio monitoring demo PASS ==="
echo "Generated paper-portfolio-monitoring.json and paper-portfolio-monitoring.md."
echo "No live trading, broker calls, provider calls, network calls, notifications, or credentials."
