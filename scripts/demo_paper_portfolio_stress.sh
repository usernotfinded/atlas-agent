#!/usr/bin/env bash
set -euo pipefail

echo "Atlas Agent paper portfolio stress demo"

DEMO_DIR=$(mktemp -d -t atlas-paper-portfolio-stress.XXXXXX)

python3.11 -m atlas_agent.cli backtest portfolio-stress \
  --symbol "DEMO-SYMBOL" \
  --data "data/sample/ohlcv_extended.csv" \
  --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
  --max-strategy-weight 0.40 \
  --min-cash-weight 0.10 \
  --max-stressed-drawdown 0.25 \
  --max-single-scenario-loss 0.20 \
  --output-dir "${DEMO_DIR}"

if [[ ! -f "${DEMO_DIR}/paper-portfolio-stress.json" ]]; then
  echo "Error: json stress report not found"
  exit 1
fi

if [[ ! -f "${DEMO_DIR}/paper-portfolio-stress.md" ]]; then
  echo "Error: markdown stress report not found"
  exit 1
fi

python3.11 - "${DEMO_DIR}/paper-portfolio-stress.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
allowed = {
    "paper_stress_pass",
    "paper_stress_watchlist",
    "needs_more_testing",
    "rejected",
}

assert data["artifact_type"] == "paper_portfolio_stress"
assert data["mode"] == "paper"
assert data["provider_required"] is False
assert data["broker_required"] is False
assert data["network_required"] is False
assert data["live_readiness"] is False
assert data["safety"]["no_live_trading"] is True
assert data["safety"]["no_broker_calls"] is True
assert data["safety"]["no_provider_calls"] is True
assert data["overall_stress_status"] in allowed
assert data["stress_constraints"]["max_stressed_drawdown"] == 0.25
assert data["stress_constraints"]["max_single_scenario_loss"] == 0.20
assert data["stress_constraints"]["max_strategy_weight"] == 0.40
assert data["stress_constraints"]["min_cash_weight"] == 0.10
assert {item["scenario"] for item in data["stress_results"]} == {
    "flash_crash",
    "volatility_spike",
    "liquidity_gap",
    "sideways_chop",
    "slow_drawdown",
}
for item in data["stress_results"]:
    assert item["status"] in allowed
PY

echo "=== Paper portfolio stress demo PASS ==="
echo "Generated paper-portfolio-stress.json and paper-portfolio-stress.md."
echo "No live trading, broker calls, provider calls, network calls, or credentials."
