#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/demo_paper_portfolio_dossier.sh
# PURPOSE: Demonstrates the paper portfolio dossier workflow using safe local
#         defaults.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


echo "Atlas Agent paper portfolio reviewer dossier demo"

DEMO_DIR=$(mktemp -d -t atlas-paper-portfolio-dossier.XXXXXX)

python3.11 -m atlas_agent.cli backtest portfolio-dossier \
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

if [[ ! -f "${DEMO_DIR}/paper-portfolio-dossier.json" ]]; then
  echo "Error: json dossier report not found"
  exit 1
fi

if [[ ! -f "${DEMO_DIR}/paper-portfolio-dossier.md" ]]; then
  echo "Error: markdown dossier report not found"
  exit 1
fi

if [[ ! -f "${DEMO_DIR}/paper-portfolio-evidence-manifest.json" ]]; then
  echo "Error: evidence manifest not found"
  exit 1
fi

python3.11 - "${DEMO_DIR}/paper-portfolio-dossier.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
allowed_status = {
    "paper_dossier_complete",
    "paper_dossier_watchlist",
    "paper_dossier_recheck_required",
    "paper_dossier_rejected",
}

assert data["artifact_type"] == "paper_portfolio_dossier"
assert data["mode"] == "paper"
assert data["provider_required"] is False
assert data["broker_required"] is False
assert data["network_required"] is False
assert data["live_readiness"] is False
assert data["not_financial_advice"] is True
assert data["safety"]["no_live_trading"] is True
assert data["safety"]["no_broker_calls"] is True
assert data["safety"]["no_provider_calls"] is True
assert data["safety"]["no_notifications_sent"] is True
assert data["safety"]["no_orders_generated"] is True
assert data["overall_dossier_status"] in allowed_status
assert len(data["artifacts"]) == 4

for chk in data["human_review_checklist"]:
    assert "item" in chk
    assert chk["required"] is True

PY

echo "=== Paper portfolio reviewer dossier demo PASS ==="
echo "Generated paper-portfolio-dossier.json, paper-portfolio-dossier.md, and paper-portfolio-evidence-manifest.json."
echo "No live trading, broker calls, provider calls, network calls, notifications, or credentials."
