# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/brokers/test_broker_guards.py
# PURPOSE: Verifies broker guards behavior and regression expectations.
# DEPS:    pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import pytest

from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.brokers.guards import guard_submit, guard_sync
from atlas_agent.config import AtlasConfig


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _live_config(
    *,
    broker_id: str = "alpaca",
    enable_live_trading: bool = True,
    enable_live_submit: bool = True,
) -> AtlasConfig:
    return AtlasConfig(
        trading_mode="live",
        broker={
            "provider": broker_id,
            "enable_live_trading": enable_live_trading,
            "enable_live_submit": enable_live_submit,
        },
    )


def test_guard_submit_allows_alpaca_with_all_gates() -> None:
    config = _live_config(broker_id="alpaca")
    entry = guard_submit(broker_id="alpaca", config=config)
    assert entry.broker_id == "alpaca"


def test_guard_submit_rejects_unknown_broker() -> None:
    config = _live_config(broker_id="alpaca")
    with pytest.raises(BrokerConfigurationError, match="unsupported broker"):
        guard_submit(broker_id="unknown_broker", config=config)


def test_guard_submit_rejects_disabled_ccxt() -> None:
    config = _live_config(broker_id="ccxt")
    with pytest.raises(BrokerConfigurationError, match="disabled"):
        guard_submit(broker_id="ccxt", config=config)


def test_guard_submit_rejects_placeholder_ibkr() -> None:
    config = _live_config(broker_id="ibkr")
    with pytest.raises(BrokerConfigurationError, match="placeholder"):
        guard_submit(broker_id="ibkr", config=config)


def test_guard_submit_rejects_partial_binance() -> None:
    config = _live_config(broker_id="binance")
    with pytest.raises(BrokerConfigurationError, match="partial"):
        guard_submit(broker_id="binance", config=config)


def test_guard_submit_rejects_missing_live_trading() -> None:
    config = _live_config(broker_id="alpaca", enable_live_trading=False)
    with pytest.raises(BrokerConfigurationError, match="enable_live_trading"):
        guard_submit(broker_id="alpaca", config=config)


def test_guard_submit_rejects_missing_live_submit() -> None:
    config = _live_config(broker_id="alpaca", enable_live_submit=False)
    with pytest.raises(BrokerConfigurationError, match="enable_live_submit"):
        guard_submit(broker_id="alpaca", config=config)


def test_guard_submit_rejects_non_live_trading_mode() -> None:
    config = AtlasConfig(
        trading_mode="paper",
        broker={
            "provider": "alpaca",
            "enable_live_trading": True,
            "enable_live_submit": True,
        },
    )
    with pytest.raises(BrokerConfigurationError, match="trading_mode"):
        guard_submit(broker_id="alpaca", config=config)


def test_guard_sync_allows_alpaca_read_only_sync() -> None:
    config = _live_config(broker_id="alpaca")
    entry = guard_sync(broker_id="alpaca", config=config)
    assert entry.broker_id == "alpaca"


def test_guard_sync_rejects_unknown_broker() -> None:
    config = _live_config(broker_id="alpaca")
    with pytest.raises(BrokerConfigurationError, match="unsupported broker"):
        guard_sync(broker_id="unknown_broker", config=config)


def test_guard_sync_rejects_placeholder_ibkr() -> None:
    config = _live_config(broker_id="ibkr")
    with pytest.raises(BrokerConfigurationError, match="placeholder"):
        guard_sync(broker_id="ibkr", config=config)


def test_guard_sync_rejects_disabled_ccxt() -> None:
    config = _live_config(broker_id="ccxt")
    with pytest.raises(BrokerConfigurationError, match="disabled"):
        guard_sync(broker_id="ccxt", config=config)


def test_guard_sync_rejects_binance_because_read_only_not_supported() -> None:
    config = _live_config(broker_id="binance")
    with pytest.raises(BrokerConfigurationError, match="read-only sync is not supported"):
        guard_sync(broker_id="binance", config=config)


def test_guard_sync_rejects_missing_live_trading() -> None:
    config = _live_config(broker_id="alpaca", enable_live_trading=False)
    with pytest.raises(BrokerConfigurationError, match="enable_live_trading"):
        guard_sync(broker_id="alpaca", config=config)
