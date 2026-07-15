#!/usr/bin/env bash
set -euo pipefail
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/demo_paper_strategy_walk_forward.sh
# PURPOSE: Demonstrates the paper strategy walk forward workflow using safe
#         local defaults.
# DEPS:    Bash, local Atlas Agent commands and scripts.
# ==============================================================================

# ==============================================================================
# SCRIPT WORKFLOW
# ==============================================================================

# --- ENVIRONMENT, SAFETY, AND EXECUTION ---


export ATLAS_LIVE_TRADING_ENABLED="false"
export ATLAS_PAPER_MODE="true"
export ATLAS_KILL_SWITCH_ACTIVE="true"

export OPENAI_API_KEY=""
export OPENROUTER_API_KEY=""
export ANTHROPIC_API_KEY=""
export GEMINI_API_KEY=""
export GOOGLE_API_KEY=""
export MOONSHOT_API_KEY=""
export KIMI_API_KEY=""
export XAI_API_KEY=""
export GROK_API_KEY=""

echo "Atlas Agent paper strategy walk-forward demo"

TEMP_DIR=$(mktemp -d -t atlas-paper-strategy-walk-forward.XXXXXX)
if [ ! -d "$TEMP_DIR" ]; then
    TEMP_DIR=$(mktemp -d /tmp/atlas-paper-strategy-walk-forward.XXXXXX)
fi

FIXTURE="data/sample/ohlcv_extended.csv"

python3.11 -m atlas_agent.cli backtest walk-forward \
    --symbol "DEMO-SYMBOL" \
    --data "$FIXTURE" \
    --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
    --window-size 60 \
    --step-size 30 \
    --output-dir "$TEMP_DIR"

if [ ! -f "$TEMP_DIR/strategy-walk-forward.json" ]; then
    echo "ERROR: strategy-walk-forward.json not generated"
    exit 1
fi

if [ ! -f "$TEMP_DIR/strategy-walk-forward.md" ]; then
    echo "ERROR: strategy-walk-forward.md not generated"
    exit 1
fi

python3.11 -c "
import json

with open('$TEMP_DIR/strategy-walk-forward.json', encoding='utf-8') as f:
    data = json.load(f)

allowed = {
    'robust_paper_follow_up',
    'window_sensitive_needs_more_testing',
    'needs_more_testing',
    'rejected',
}
forbidden = {
    'live_ready',
    'production_ready',
    'safe_to_trade_live',
    'approved_for_live',
    'guaranteed_profit',
    'outperforms_market',
}

assert data['artifact_type'] == 'paper_strategy_walk_forward', 'Invalid artifact type'
assert data['mode'] == 'paper', 'Invalid mode'
assert data['provider_required'] is False, 'Provider should not be required'
assert data['broker_required'] is False, 'Broker should not be required'
assert data['network_required'] is False, 'Network should not be required'
assert data['live_readiness'] is False, 'Report must not claim live readiness'
assert data['safety']['no_live_trading'] is True, 'Safety violation'
assert data['safety']['no_provider_calls'] is True, 'Safety violation'
assert data['safety']['no_broker_calls'] is True, 'Safety violation'
assert data['windowing']['windows_evaluated'] >= 1, 'Expected at least one window'
assert len(data['strategies']) == 3, 'Expected three strategies'

for strategy in data['strategies']:
    status = strategy['walk_forward_summary']['paper_follow_up_status']
    assert status in allowed, f'Unexpected walk-forward status: {status}'
    assert status not in forbidden, f'Forbidden status used: {status}'
    assert strategy['window_results'], 'Missing window results'
    for item in strategy['window_results']:
        assert item['live_ready'] is False, 'Window result must not be live-ready'
" || {
    echo "ERROR: JSON report validation failed"
    exit 1
}

echo ""
echo "=== Paper strategy walk-forward demo PASS ==="
echo "Generated strategy-walk-forward.json and strategy-walk-forward.md."
echo "No live trading, broker calls, provider calls, network calls, or credentials."
