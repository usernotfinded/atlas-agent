#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/demo_paper_portfolio_proposal.sh
# PURPOSE: Demonstrates the paper portfolio proposal workflow using safe local
#         defaults.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


echo "Atlas Agent paper portfolio proposal demo"

DEMO_DIR=$(mktemp -d -t atlas-paper-portfolio-proposal.XXXXXX)

python3.11 -m atlas_agent.cli backtest portfolio-proposal \
  --symbol "DEMO-SYMBOL" \
  --data "data/sample/ohlcv_extended.csv" \
  --strategies "moving_average_cross,rsi_mean_reversion,buy_and_hold" \
  --output-dir "${DEMO_DIR}"

if [[ ! -f "${DEMO_DIR}/paper-portfolio-proposal.json" ]]; then
  echo "Error: json proposal not found"
  exit 1
fi

if [[ ! -f "${DEMO_DIR}/paper-portfolio-proposal.md" ]]; then
  echo "Error: markdown proposal not found"
  exit 1
fi

python3.11 -c "
import json, sys
data = json.load(open('${DEMO_DIR}/paper-portfolio-proposal.json'))
if data['safety']['no_live_trading'] is not True:
    sys.exit('Safety flag missing')
weights = sum(a['paper_weight'] for a in data['allocations'])
if not (0.999 < weights < 1.001):
    sys.exit(f'Weights do not sum to 1.0: {weights}')
"

echo "=== Paper portfolio proposal demo PASS ==="
echo "Generated paper-portfolio-proposal.json and paper-portfolio-proposal.md."
echo "No live trading, broker calls, provider calls, network calls, or credentials."
