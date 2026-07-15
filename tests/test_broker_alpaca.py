# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_broker_alpaca.py
# PURPOSE: Verifies broker alpaca behavior and regression expectations.
# DEPS:    os, pytest, unittest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import os
import pytest
from unittest.mock import patch
from atlas_agent.brokers.alpaca import AlpacaBroker, AlpacaBrokerAdapter
from atlas_agent.config import AtlasConfig
from atlas_agent.brokers.base import BrokerConfigurationError, BrokerOperationError
from atlas_agent.execution.order import Order

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def base_config():
    return AtlasConfig()

@pytest.fixture
def live_config_no_submit():
    """Config where _validate_config passes but enable_live_submit is False."""
    return AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True, "enable_live_submit": False},
    )

def test_alpaca_default_paper(monkeypatch, base_config):
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    
    adapter = AlpacaBrokerAdapter(config=base_config)
    assert adapter._endpoint == adapter.paper_endpoint

def test_alpaca_paper_mode_explicit(monkeypatch, base_config):
    """ALPACA_ENDPOINT_MODE=paper explicitly selects paper endpoint."""
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    monkeypatch.setenv("ALPACA_ENDPOINT_MODE", "paper")
    
    adapter = AlpacaBrokerAdapter(config=base_config)
    assert adapter._endpoint == adapter.paper_endpoint

def test_alpaca_live_mode_fails_closed_without_gates(monkeypatch, live_config_no_submit):
    """Live endpoint mode fails closed when enable_live_submit is False."""
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    monkeypatch.setenv("ALPACA_ENDPOINT_MODE", "live")

    # Adapter: _endpoint property should fail
    adapter = AlpacaBrokerAdapter(config=live_config_no_submit)
    with pytest.raises(BrokerConfigurationError, match="Live endpoint requested but live trading/submit gates are not enabled"):
        _ = adapter._endpoint

    # Broker: place_order should fail at endpoint check
    broker = AlpacaBroker(config=live_config_no_submit)
    order = Order(symbol="AAPL", quantity=1, side="buy", order_type="market")
    with pytest.raises(BrokerConfigurationError, match="Live endpoint requested but live trading/submit gates are not enabled"):
        broker.place_order(order, client_order_id="test_id_123")

def test_alpaca_invalid_mode_fails(monkeypatch, base_config):
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    monkeypatch.setenv("ALPACA_ENDPOINT_MODE", "garbage")
    
    adapter = AlpacaBrokerAdapter(config=base_config)
    with pytest.raises(BrokerConfigurationError):
        _ = adapter._endpoint

def test_alpaca_live_env_alone_cannot_select_live(monkeypatch, base_config):
    """Env var ALPACA_ENDPOINT_MODE=live alone cannot select the live endpoint.
    
    Default config has enable_live_trading=False and enable_live_submit=False,
    so even if the env var says 'live', the adapter must refuse.
    """
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    monkeypatch.setenv("ALPACA_ENDPOINT_MODE", "live")

    adapter = AlpacaBrokerAdapter(config=base_config)
    with pytest.raises(BrokerConfigurationError):
        _ = adapter._endpoint

def test_alpaca_timeout_surfaces_reconciliation_message(monkeypatch, live_config_no_submit):
    """Timeout during place_order surfaces a message requiring reconciliation by client_order_id."""
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True, "enable_live_submit": True},
    )
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    monkeypatch.setenv("ALPACA_ENDPOINT_MODE", "paper")

    broker = AlpacaBroker(config=config)
    order = Order(symbol="AAPL", quantity=1, side="buy", order_type="market")

    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        with pytest.raises(BrokerOperationError, match="reconcile by client_order_id"):
            broker.place_order(order, client_order_id="test-timeout-001")

def test_alpaca_no_auto_resubmit_on_timeout(monkeypatch):
    """Verify that place_order does not contain retry/resubmit logic after timeout.
    
    This is a structural assertion: after a TimeoutError, the method must raise
    immediately without any loop or retry mechanism.
    """
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True, "enable_live_submit": True},
    )
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    monkeypatch.setenv("ALPACA_ENDPOINT_MODE", "paper")

    broker = AlpacaBroker(config=config)
    order = Order(symbol="AAPL", quantity=1, side="buy", order_type="market")

    call_count = 0
    original_side_effect = TimeoutError("timed out")

    def counting_urlopen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise original_side_effect

    with patch("urllib.request.urlopen", side_effect=counting_urlopen):
        with pytest.raises(BrokerOperationError):
            broker.place_order(order, client_order_id="test-no-retry-001")

    # urlopen should have been called exactly once — no retry
    assert call_count == 1, f"Expected exactly 1 call to urlopen, got {call_count}"
