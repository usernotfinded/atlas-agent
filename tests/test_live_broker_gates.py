from __future__ import annotations

import pytest

from omni_trade_ai.brokers.alpaca import AlpacaBroker
from omni_trade_ai.brokers.base import BrokerConfigurationError
from omni_trade_ai.brokers.binance import BinanceBroker
from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.execution.order import Order


def test_live_order_without_enable_live_trading_fails() -> None:
    broker = AlpacaBroker(OmniTradeConfig(trading_mode="live", live_broker="alpaca"))

    with pytest.raises(BrokerConfigurationError, match="ENABLE_LIVE_TRADING"):
        broker.place_order(Order("BTC-USD", "buy", 1, limit_price=100))


def test_alpaca_refuses_without_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    broker = AlpacaBroker(
        OmniTradeConfig(
            trading_mode="live",
            enable_live_trading=True,
            live_broker="alpaca",
        )
    )

    with pytest.raises(BrokerConfigurationError, match="ALPACA_API_KEY"):
        broker.place_order(Order("BTC-USD", "buy", 1, limit_price=100))


def test_binance_refuses_without_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    broker = BinanceBroker(
        OmniTradeConfig(
            trading_mode="live",
            enable_live_trading=True,
            live_broker="binance",
        )
    )

    with pytest.raises(BrokerConfigurationError, match="BINANCE_API_KEY"):
        broker.place_order(Order("BTC-USD", "buy", 1, limit_price=100))
