from __future__ import annotations

import sys
import types

import pytest

from atlas_agent.brokers.alpaca import AlpacaBroker
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.brokers.binance import BinanceBroker
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order import Order


def test_live_order_without_enable_live_trading_fails() -> None:
    broker = AlpacaBroker(AtlasConfig(trading_mode="live", live_broker="alpaca"))

    with pytest.raises(BrokerConfigurationError, match="ENABLE_LIVE_TRADING"):
        broker.place_order(Order("TEST-SYMBOL", "buy", 1, limit_price=100))


def test_alpaca_refuses_without_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    broker = AlpacaBroker(
        AtlasConfig(
            trading_mode="live",
            enable_live_trading=True,
            live_broker="alpaca",
        )
    )

    with pytest.raises(BrokerConfigurationError, match="ALPACA_API_KEY"):
        broker.place_order(Order("TEST-SYMBOL", "buy", 1, limit_price=100))


def test_binance_refuses_without_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    monkeypatch.delenv("BINANCE_SECRET_KEY", raising=False)
    broker = BinanceBroker(
        AtlasConfig(
            trading_mode="live",
            enable_live_trading=True,
            live_broker="binance",
        )
    )

    with pytest.raises(BrokerConfigurationError, match="BINANCE_API_KEY"):
        broker.place_order(Order("TEST-SYMBOL", "buy", 1, limit_price=100))


def test_binance_legacy_secret_alias_is_compatibility_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "demo-key")
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    monkeypatch.setenv("BINANCE_SECRET_KEY", "legacy-secret")

    fake_exchange = types.SimpleNamespace(
        create_limit_order=lambda *args, **kwargs: {"status": "closed", "id": "ord-1"},
    )
    fake_ccxt = types.SimpleNamespace(binance=lambda *_args, **_kwargs: fake_exchange)
    monkeypatch.setitem(sys.modules, "ccxt", fake_ccxt)

    broker = BinanceBroker(
        AtlasConfig(
            trading_mode="live",
            enable_live_trading=True,
            live_broker="binance",
        )
    )

    result = broker.place_order(Order("TEST-SYMBOL", "buy", 1, order_type="limit", limit_price=100))
    assert result.accepted is True
    assert result.status == "closed"
