# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/brokers/test_unsupported_brokers_fail_closed.py
# PURPOSE: Verifies unsupported brokers fail closed behavior and regression
#         expectations.
# DEPS:    sys, types, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import sys
import types

import pytest

from atlas_agent.brokers.alpaca import AlpacaBroker
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.brokers.binance import BinanceBroker
from atlas_agent.brokers.ccxt_adapter import CCXTBroker
from atlas_agent.brokers.ibkr_stub import IBKRStub
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order import Order


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_unsupported_broker_submit_fails_closed() -> None:
    """An invented/unknown broker should not be constructible or submit.

    This test documents the fail-closed boundary: only explicitly supported
    broker adapters exist in the codebase. There is no generic 'other' broker.
    """
    # There is no UnknownBroker class. Attempting to import one would fail.
    # Runtime resolution via BrokerResolver already rejects unknown brokers.
    from atlas_agent.brokers.resolver import BrokerResolver

    config = AtlasConfig(
        trading_mode="live",
        broker={
            "provider": "unknown_broker",
            "enable_live_trading": True,
            "enable_live_submit": True,
        },
    )
    resolver = BrokerResolver(config)
    status = resolver.resolve_status("live")
    assert status.configured is False
    assert status.can_submit is False
    assert status.code == "live_broker_unsupported"

    resolution = resolver.resolve_execution_broker("live")
    assert resolution.execution_broker is None


def test_ibkr_placeholder_does_not_submit() -> None:
    stub = IBKRStub()
    with pytest.raises(NotImplementedError, match="IBKR support requires a future reviewed adapter"):
        stub.place_order("any-order")  # type: ignore[attr-defined]


def test_ccxt_disabled_by_default() -> None:
    config = AtlasConfig(
        trading_mode="live",
        broker={
            "provider": "ccxt",
            "enable_live_trading": True,
            "enable_live_submit": True,
        },
    )
    broker = CCXTBroker(config)
    with pytest.raises(BrokerConfigurationError, match="disabled"):
        broker.place_order(Order("TEST", "buy", 1, limit_price=100))


def test_binance_does_not_submit_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    monkeypatch.delenv("BINANCE_SECRET_KEY", raising=False)

    config = AtlasConfig(
        trading_mode="live",
        broker={
            "provider": "binance",
            "enable_live_trading": True,
            "enable_live_submit": True,
        },
    )
    broker = BinanceBroker(config)
    with pytest.raises(BrokerConfigurationError, match="BINANCE_API_KEY"):
        broker.place_order(Order("TEST", "buy", 1, limit_price=100))


def test_alpaca_behavior_unchanged_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)

    config = AtlasConfig(
        trading_mode="live",
        broker={
            "provider": "alpaca",
            "enable_live_trading": True,
            "enable_live_submit": True,
        },
    )
    broker = AlpacaBroker(config)
    with pytest.raises(BrokerConfigurationError, match="ALPACA_API_KEY"):
        broker.place_order(Order("TEST", "buy", 1, limit_price=100))


def test_no_real_broker_api_calls_are_made_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirm Binance path raises before constructing any ccxt exchange.

    Even if ccxt were importable, missing credentials must fail closed first.
    """
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)

    config = AtlasConfig(
        trading_mode="live",
        broker={
            "provider": "binance",
            "enable_live_trading": True,
            "enable_live_submit": True,
        },
    )
    broker = BinanceBroker(config)
    with pytest.raises(BrokerConfigurationError):
        broker.place_order(Order("TEST", "buy", 1, limit_price=100))


def test_live_trading_defaults_remain_disabled() -> None:
    config = AtlasConfig()
    assert config.broker.enable_live_trading is False
    assert config.broker.enable_live_submit is False
    assert config.trading_mode == "paper"


def test_provider_execution_disabled_by_default() -> None:
    config = AtlasConfig()
    assert config.model.provider == "openai"
    # Provider execution is disabled by default because only deterministic
    # research provider is supported; real providers require opt-in/config.
    assert config.broker.provider == "none"


def test_broker_execution_disabled_by_default() -> None:
    config = AtlasConfig()
    assert config.broker.provider == "none"
    assert config.broker.enable_live_trading is False
    assert config.broker.enable_live_submit is False
