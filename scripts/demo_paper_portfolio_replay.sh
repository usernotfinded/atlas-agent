#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/demo_paper_portfolio_replay.sh
# PURPOSE: Demonstrates the paper portfolio replay workflow using safe local
#         defaults.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


# Demo Script: Paper Portfolio Evidence Replay and Regression Gate
# This script demonstrates the deterministic replay of portfolio evidence artifacts.
# No provider, broker, network, live trading, notification, or order path is used.

if [[ "${1:-}" == "--mode" && "${2:-}" == "live" ]]; then
    echo "ERROR: Live mode is strictly forbidden in this paper-only demo."
    exit 1
fi

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "${TEMP_DIR}"' EXIT

echo "============================================================"
echo "Running Paper Portfolio Evidence Replay (CAND-006)"
echo "============================================================"
echo "Output Directory: ${TEMP_DIR}"
echo "Repeat Count: 2"
echo ""

python3.11 -m atlas_agent.cli backtest portfolio-replay \
    --data data/sample/ohlcv_extended.csv \
    --symbol DEMO-SYMBOL \
    --strategies buy_and_hold \
    --repeat 2 \
    --output-dir "${TEMP_DIR}" \
    --json > "${TEMP_DIR}/replay_output.json"

if [ ! -f "${TEMP_DIR}/paper-portfolio-replay.json" ]; then
    echo "ERROR: paper-portfolio-replay.json missing."
    exit 1
fi

if [ ! -f "${TEMP_DIR}/paper-portfolio-replay.md" ]; then
    echo "ERROR: paper-portfolio-replay.md missing."
    exit 1
fi

if [ ! -f "${TEMP_DIR}/paper-portfolio-regression-manifest.json" ]; then
    echo "ERROR: paper-portfolio-regression-manifest.json missing."
    exit 1
fi

# Verify key JSON fields
cat << 'EOF' > "${TEMP_DIR}/verify.py"
import json
import sys

with open(sys.argv[1]) as f:
    data = json.load(f)

assert data.get("artifact_type") == "paper_portfolio_replay"
assert data.get("schema_version") == 1
assert data.get("mode") == "paper"
assert data.get("provider_required") is False
assert data.get("broker_required") is False
assert data.get("network_required") is False
assert data.get("live_readiness") is False
assert data.get("overall_replay_status") in ["paper_replay_pass", "paper_replay_drift_detected", "paper_replay_schema_mismatch", "needs_recheck", "rejected"]

safety = data.get("safety", {})
assert safety.get("no_notifications_sent") is True
assert safety.get("no_orders_generated") is True
assert safety.get("no_live_trading") is True

# Verify at least one comparison is match
comparisons = data.get("comparisons", [])
assert any(c.get("status") == "match" for c in comparisons), "No matching comparisons found."

print("JSON schema and safety boundaries verified successfully.")
EOF

python3.11 "${TEMP_DIR}/verify.py" "${TEMP_DIR}/paper-portfolio-replay.json"

echo "============================================================"
echo "PASS: Paper Portfolio Evidence Replay completed successfully."
echo "============================================================"
