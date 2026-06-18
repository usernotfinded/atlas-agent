#!/usr/bin/env bash
set -euo pipefail

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

echo "Atlas Agent paper strategy scorecard demo"

TEMP_DIR=$(mktemp -d -t atlas-paper-strategy-scorecard.XXXXXX)
if [ ! -d "$TEMP_DIR" ]; then
    TEMP_DIR=$(mktemp -d /tmp/atlas-paper-strategy-scorecard.XXXXXX)
fi

REGIME_FIXTURES="data/sample/regimes/ohlcv_uptrend.csv,data/sample/regimes/ohlcv_downtrend.csv,data/sample/regimes/ohlcv_flat.csv,data/sample/regimes/ohlcv_volatile.csv"

python3.11 -m atlas_agent.cli backtest scorecard \
    --data "data/sample/ohlcv_extended.csv" \
    --symbol "DEMO-SYMBOL" \
    --fixtures "$REGIME_FIXTURES" \
    --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
    --output-dir "$TEMP_DIR"

if [ ! -f "$TEMP_DIR/strategy-scorecard.json" ]; then
    echo "ERROR: strategy-scorecard.json not generated"
    exit 1
fi

if [ ! -f "$TEMP_DIR/strategy-scorecard.md" ]; then
    echo "ERROR: strategy-scorecard.md not generated"
    exit 1
fi

python3.11 -c "
import json

with open('$TEMP_DIR/strategy-scorecard.json', encoding='utf-8') as f:
    data = json.load(f)

allowed = {
    'paper_follow_up_candidate',
    'paper_watchlist',
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

assert data['artifact_type'] == 'paper_strategy_scorecard', 'Invalid artifact type'
assert data['mode'] == 'paper', 'Invalid mode'
assert data['provider_required'] is False, 'Provider should not be required'
assert data['broker_required'] is False, 'Broker should not be required'
assert data['network_required'] is False, 'Network should not be required'
assert data['live_readiness'] is False, 'Report must not claim live readiness'
assert data['safety']['no_live_trading'] is True, 'Safety violation'
assert data['safety']['no_provider_calls'] is True, 'Safety violation'
assert data['safety']['no_broker_calls'] is True, 'Safety violation'

assert data['evidence_streams']['evaluation'] is True
assert data['evidence_streams']['sensitivity'] is True
assert data['evidence_streams']['walk_forward'] is True
assert data['evidence_streams']['robustness'] is True

assert len(data['strategies']) == 3, 'Expected three strategies'
for strategy in data['strategies']:
    decision = strategy['scorecard']['decision']
    assert decision in allowed, f'Unexpected scorecard decision: {decision}'
    assert decision not in forbidden, f'Forbidden status used: {decision}'
    assert strategy['scorecard']['live_ready'] is False, 'Strategy scorecard must not be live-ready'

assert len(data['ranking']) == 3, 'Expected three ranked strategies'
" || {
    echo "ERROR: JSON report validation failed"
    exit 1
}

echo ""
echo "=== Paper strategy scorecard demo PASS ==="
echo "Generated strategy-scorecard.json and strategy-scorecard.md."
echo "No live trading, broker calls, provider calls, network calls, or credentials."
