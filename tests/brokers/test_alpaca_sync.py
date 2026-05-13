from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from atlas_agent.brokers.alpaca import (
    AlpacaBrokerAdapter,
    _require_finite,
    _require_finite_non_negative,
    _require_finite_positive,
)
from atlas_agent.brokers.base import BrokerConfigurationError
from atlas_agent.config import AtlasConfig


# ---------------------------------------------------------------------------
# Numeric validation helpers
# ---------------------------------------------------------------------------

def test_require_finite_accepts_float() -> None:
    assert _require_finite(3.14, "x") == 3.14


def test_require_finite_rejects_nan() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite(float("nan"), "x")


def test_require_finite_rejects_inf() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite(float("inf"), "x")


def test_require_finite_rejects_true() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite(True, "x")


def test_require_finite_rejects_false() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite(False, "x")


def test_require_finite_non_negative_accepts_zero() -> None:
    assert _require_finite_non_negative(0, "cash") == 0.0


def test_require_finite_non_negative_rejects_negative() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite_non_negative(-1, "cash")


def test_require_finite_non_negative_rejects_true() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite_non_negative(True, "cash")


def test_require_finite_non_negative_rejects_false() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite_non_negative(False, "cash")


def test_require_finite_positive_rejects_zero() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite_positive(0, "qty")


def test_require_finite_positive_rejects_bool() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite_positive(True, "qty")


def test_require_finite_positive_rejects_negative() -> None:
    with pytest.raises(ValueError, match="invalid numeric value"):
        _require_finite_positive(-5, "qty")


# ---------------------------------------------------------------------------
# Adapter helpers
# ---------------------------------------------------------------------------

def _adapter() -> AlpacaBrokerAdapter:
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
    )
    return AlpacaBrokerAdapter(config)


def _with_env():
    return patch.dict(
        os.environ,
        {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"},
        clear=False,
    )


# ---------------------------------------------------------------------------
# Adapter: get_account_state
# ---------------------------------------------------------------------------

def test_get_account_state_maps_fields() -> None:
    adapter = _adapter()
    raw = {
        "cash": "1234.56",
        "portfolio_value": "5678.90",
        "buying_power": "9999.99",
    }
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            state = adapter.get_account_state()
    assert state.account_id == "alpaca_paper"
    assert state.currency == "USD"
    assert state.cash == 1234.56
    assert state.equity == 5678.90
    assert state.buying_power == 9999.99
    assert state.is_live is True


def test_get_account_state_live_mode() -> None:
    adapter = _adapter()
    raw = {"cash": "100", "portfolio_value": "200", "buying_power": "300"}
    with _with_env():
        with patch.dict(os.environ, {"ALPACA_ENDPOINT_MODE": "live"}, clear=False):
            with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
                state = adapter.get_account_state()
    assert state.account_id == "alpaca_live"


def test_get_account_state_rejects_negative_cash() -> None:
    adapter = _adapter()
    raw = {"cash": "-1", "portfolio_value": "100", "buying_power": "100"}
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value"):
                adapter.get_account_state()


def test_get_account_state_rejects_nan_equity() -> None:
    adapter = _adapter()
    raw = {"cash": "100", "portfolio_value": "nan", "buying_power": "100"}
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value"):
                adapter.get_account_state()


def test_get_account_state_rejects_bool_cash() -> None:
    adapter = _adapter()
    raw = {"cash": True, "portfolio_value": "100", "buying_power": "100"}
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value") as exc_info:
                adapter.get_account_state()
    assert "True" not in str(exc_info.value)


def test_get_account_state_rejects_bool_portfolio_value() -> None:
    adapter = _adapter()
    raw = {"cash": "100", "portfolio_value": False, "buying_power": "100"}
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value") as exc_info:
                adapter.get_account_state()
    assert "False" not in str(exc_info.value)


def test_get_account_state_rejects_bool_buying_power() -> None:
    adapter = _adapter()
    raw = {"cash": "100", "portfolio_value": "100", "buying_power": True}
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value") as exc_info:
                adapter.get_account_state()
    assert "True" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Adapter: get_positions
# ---------------------------------------------------------------------------

def test_get_positions_long_and_short() -> None:
    adapter = _adapter()
    raw = [
        {
            "symbol": "AAPL",
            "qty": "10",
            "avg_entry_price": "150.0",
            "current_price": "155.0",
        },
        {
            "symbol": "TSLA",
            "qty": "-5",
            "avg_entry_price": "200.0",
            "current_price": "195.0",
        },
    ]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            positions = adapter.get_positions()
    assert len(positions) == 2
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == 10.0
    assert positions[0].side == "long"
    assert positions[1].symbol == "TSLA"
    assert positions[1].quantity == -5.0
    assert positions[1].side == "short"


def test_get_positions_rejects_non_list() -> None:
    adapter = _adapter()
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value={"foo": "bar"}):
            with pytest.raises(ValueError, match="not a list"):
                adapter.get_positions()


def test_get_positions_rejects_zero_avg_entry() -> None:
    adapter = _adapter()
    raw = [
        {
            "symbol": "AAPL",
            "qty": "10",
            "avg_entry_price": "0",
            "current_price": "155.0",
        },
    ]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value"):
                adapter.get_positions()


def test_get_positions_rejects_bool_qty() -> None:
    adapter = _adapter()
    raw = [
        {
            "symbol": "AAPL",
            "qty": True,
            "avg_entry_price": "150.0",
            "current_price": "155.0",
        },
    ]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value") as exc_info:
                adapter.get_positions()
    assert "True" not in str(exc_info.value)


def test_get_positions_negative_qty_still_allowed() -> None:
    adapter = _adapter()
    raw = [
        {
            "symbol": "TSLA",
            "qty": "-5",
            "avg_entry_price": "200.0",
            "current_price": "195.0",
        },
    ]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            positions = adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == -5.0
    assert positions[0].side == "short"


# ---------------------------------------------------------------------------
# Adapter: get_open_orders
# ---------------------------------------------------------------------------

def test_get_open_orders_maps_fields() -> None:
    adapter = _adapter()
    raw = [
        {
            "id": "ord-1",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "10",
            "filled_qty": "3",
            "limit_price": "150.0",
        },
    ]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            orders = adapter.get_open_orders()
    assert len(orders) == 1
    assert orders[0].order_id == "ord-1"
    assert orders[0].symbol == "AAPL"
    assert orders[0].side == "buy"
    assert orders[0].quantity == 10.0
    assert orders[0].filled_quantity == 3.0
    assert orders[0].limit_price == 150.0
    assert orders[0].status == "open"


def test_get_open_orders_none_limit_price() -> None:
    adapter = _adapter()
    raw = [
        {
            "id": "ord-2",
            "symbol": "TSLA",
            "side": "sell",
            "qty": "5",
            "filled_qty": "0",
        },
    ]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            orders = adapter.get_open_orders()
    assert orders[0].limit_price is None


def test_get_open_orders_rejects_non_list() -> None:
    adapter = _adapter()
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value={"foo": "bar"}):
            with pytest.raises(ValueError, match="not a list"):
                adapter.get_open_orders()


def test_get_open_orders_rejects_zero_qty() -> None:
    adapter = _adapter()
    raw = [{"id": "x", "symbol": "X", "side": "buy", "qty": "0"}]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value"):
                adapter.get_open_orders()


def test_get_open_orders_rejects_bool_filled_qty() -> None:
    adapter = _adapter()
    raw = [
        {
            "id": "ord-3",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "10",
            "filled_qty": True,
        },
    ]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            with pytest.raises(ValueError, match="invalid numeric value") as exc_info:
                adapter.get_open_orders()
    assert "True" not in str(exc_info.value)


def test_get_open_orders_zero_filled_qty_still_allowed() -> None:
    adapter = _adapter()
    raw = [
        {
            "id": "ord-4",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "10",
            "filled_qty": "0",
        },
    ]
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            orders = adapter.get_open_orders()
    assert len(orders) == 1
    assert orders[0].filled_quantity == 0.0


# ---------------------------------------------------------------------------
# Adapter: get_balances
# ---------------------------------------------------------------------------

def test_get_balances_derives_from_account() -> None:
    adapter = _adapter()
    raw = {"cash": "1234.56", "portfolio_value": "5678.90", "buying_power": "9999.99"}
    with _with_env():
        with patch.object(AlpacaBrokerAdapter, "_request", return_value=raw):
            balances = adapter.get_balances()
    assert len(balances) == 1
    assert balances[0].asset == "USD"
    assert balances[0].free == 1234.56
    assert balances[0].locked == 0.0
    assert balances[0].total == 1234.56


# ---------------------------------------------------------------------------
# Adapter: configuration validation
# ---------------------------------------------------------------------------

def test_adapter_validate_config_missing_key() -> None:
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
    )
    adapter = AlpacaBrokerAdapter(config)
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(BrokerConfigurationError):
            adapter.get_account_state()


def test_adapter_uses_paper_endpoint_by_default() -> None:
    adapter = _adapter()
    with patch.dict(os.environ, {"ALPACA_ENDPOINT_MODE": "paper"}, clear=False):
        assert adapter._endpoint == "https://paper-api.alpaca.markets"


def test_adapter_uses_live_endpoint_when_configured() -> None:
    adapter = _adapter()
    with patch.dict(os.environ, {"ALPACA_ENDPOINT_MODE": "live"}, clear=False):
        assert adapter._endpoint == "https://api.alpaca.markets"
