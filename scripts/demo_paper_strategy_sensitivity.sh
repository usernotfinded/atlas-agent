#!/usr/bin/env bash
set -euo pipefail

export ATLAS_LIVE_TRADING_ENABLED="false"
export ATLAS_PAPER_MODE="true"
export ATLAS_KILL_SWITCH_ACTIVE="true"

# Wipe keys to prove no-provider requirement
export OPENAI_API_KEY=""
export OPENROUTER_API_KEY=""
export ANTHROPIC_API_KEY=""
export GEMINI_API_KEY=""
export GOOGLE_API_KEY=""
export MOONSHOT_API_KEY=""
export KIMI_API_KEY=""
export XAI_API_KEY=""
export GROK_API_KEY=""

echo "Atlas Agent paper strategy sensitivity demo"

TEMP_DIR=$(mktemp -d -t atlas-paper-strategy-sensitivity.XXXXXX)
# Fallback for systems where mktemp doesn't like -t with XXXXXX
if [ ! -d "$TEMP_DIR" ]; then
    TEMP_DIR=$(mktemp -d /tmp/atlas-paper-strategy-sensitivity.XXXXXX)
fi

python3.11 -m atlas_agent.cli backtest sensitivity \
    --symbol "DEMO-SYMBOL" \
    --data "data/sample/ohlcv_extended.csv" \
    --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
    --output-dir "$TEMP_DIR"

if [ ! -f "$TEMP_DIR/strategy-sensitivity.json" ]; then
    echo "ERROR: strategy-sensitivity.json not generated"
    exit 1
fi

if [ ! -f "$TEMP_DIR/strategy-sensitivity.md" ]; then
    echo "ERROR: strategy-sensitivity.md not generated"
    exit 1
fi

python3.11 -c "
import json
import sys

with open('$TEMP_DIR/strategy-sensitivity.json') as f:
    data = json.load(f)

assert data['artifact_type'] == 'paper_strategy_sensitivity', 'Invalid artifact type'
assert data['mode'] == 'paper', 'Invalid mode'
assert data['safety']['no_live_trading'] is True, 'Safety violation'
assert data['safety']['no_provider_calls'] is True, 'Safety violation'

strategies = data['strategies']
assert len(strategies) == 3, f'Expected 3 strategies, got {len(strategies)}'

for strat in strategies:
    if strat['name'] == 'moving_average_cross':
        assert len(strat['variants']) >= 3, 'Expected multiple variants for moving_average_cross'
" || {
    echo "ERROR: JSON report validation failed"
    exit 1
}

echo ""
echo "=== Paper strategy sensitivity demo PASS ==="
echo "Generated strategy-sensitivity.json and strategy-sensitivity.md."
echo "No live trading, broker calls, provider calls, network calls, or credentials."
