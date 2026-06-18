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

echo "Atlas Agent paper strategy robustness demo"

TEMP_DIR=$(mktemp -d -t atlas-paper-strategy-robustness.XXXXXX)
if [ ! -d "$TEMP_DIR" ]; then
    TEMP_DIR=$(mktemp -d /tmp/atlas-paper-strategy-robustness.XXXXXX)
fi

REGIME_FIXTURES="data/sample/regimes/ohlcv_uptrend.csv,data/sample/regimes/ohlcv_downtrend.csv,data/sample/regimes/ohlcv_flat.csv,data/sample/regimes/ohlcv_volatile.csv"

python3.11 -m atlas_agent.cli backtest robustness \
    --symbol "DEMO-SYMBOL" \
    --fixtures "$REGIME_FIXTURES" \
    --strategies "buy_and_hold,moving_average_cross,rsi_mean_reversion" \
    --output-dir "$TEMP_DIR"

if [ ! -f "$TEMP_DIR/strategy-robustness.json" ]; then
    echo "ERROR: strategy-robustness.json not generated"
    exit 1
fi

if [ ! -f "$TEMP_DIR/strategy-robustness.md" ]; then
    echo "ERROR: strategy-robustness.md not generated"
    exit 1
fi

python3.11 -c "
import json

with open('$TEMP_DIR/strategy-robustness.json', encoding='utf-8') as f:
    data = json.load(f)

allowed = {
    'robust_paper_follow_up',
    'regime_sensitive_needs_more_testing',
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

assert data['artifact_type'] == 'paper_strategy_robustness', 'Invalid artifact type'
assert data['mode'] == 'paper', 'Invalid mode'
assert data['provider_required'] is False, 'Provider should not be required'
assert data['broker_required'] is False, 'Broker should not be required'
assert data['network_required'] is False, 'Network should not be required'
assert data['live_readiness'] is False, 'Report must not claim live readiness'
assert data['safety']['no_live_trading'] is True, 'Safety violation'
assert data['safety']['no_provider_calls'] is True, 'Safety violation'
assert data['safety']['no_broker_calls'] is True, 'Safety violation'
assert len(data['regimes']) == 4, 'Expected four regimes'
assert len(data['strategies']) == 3, 'Expected three strategies'

for regime in data['regimes']:
    assert regime['row_count'] >= 10, 'Regime fixture is too small'
for strategy in data['strategies']:
    status = strategy['robustness_summary']['paper_follow_up_status']
    assert status in allowed, f'Unexpected robustness status: {status}'
    assert status not in forbidden, f'Forbidden status used: {status}'
    assert strategy['regime_results'], 'Missing regime results'
    for item in strategy['regime_results']:
        assert item['live_ready'] is False, 'Regime result must not be live-ready'
" || {
    echo "ERROR: JSON report validation failed"
    exit 1
}

echo ""
echo "=== Paper strategy robustness demo PASS ==="
echo "Generated strategy-robustness.json and strategy-robustness.md."
echo "No live trading, broker calls, provider calls, network calls, or credentials."
