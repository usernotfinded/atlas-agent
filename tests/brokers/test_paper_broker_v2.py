from __future__ import annotations

import pytest
from pathlib import Path
from atlas_agent.brokers.paper import PaperBroker, PaperBrokerAdapter
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.portfolio.positions import Position
from atlas_agent.brokers.models import BrokerOrder


def test_paper_adapter_returns_positions_and_orders():
    state = PortfolioState(cash=10000)
    state.positions["AAPL"] = Position(symbol="AAPL", quantity=10, average_price=150.0)
    
    broker = PaperBroker(state=state)
    broker.open_orders_list = [
        BrokerOrder(order_id="o1", symbol="MSFT", side="buy", quantity=5, status="open")
    ]
    
    adapter = PaperBrokerAdapter(broker=broker)
    
    positions = adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == 10
    assert positions[0].side == "long"
    
    orders = adapter.get_open_orders()
    assert len(orders) == 1
    assert orders[0].order_id == "o1"
    assert orders[0].symbol == "MSFT"


def test_paper_adapter_get_account_state():
    state = PortfolioState(cash=10000)
    broker = PaperBroker(state=state)
    adapter = PaperBrokerAdapter(broker=broker)
    
    acc = adapter.get_account_state()
    assert acc.account_id == "paper_account"
    assert acc.cash == 10000
    assert acc.equity == 10000
    assert acc.is_live is False


import pytest
from atlas_agent.execution.order import Order


@pytest.mark.parametrize("bad_price", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_paper_broker_rejects_invalid_limit_price(bad_price):
    state = PortfolioState(cash=10000)
    broker = PaperBroker(state=state)
    order = Order(symbol="AAPL", side="buy", quantity=10, order_type="limit", limit_price=bad_price)
    result = broker.place_order(order)
    assert result.status == "rejected"
    assert "positive price" in result.message


@pytest.mark.parametrize("bad_quantity", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_paper_broker_rejects_invalid_quantity(bad_quantity):
    state = PortfolioState(cash=10000)
    broker = PaperBroker(state=state)
    order = Order(symbol="AAPL", side="buy", quantity=bad_quantity, order_type="limit", limit_price=100.0)
    result = broker.place_order(order)
    assert result.status == "rejected"
    assert "positive quantity" in result.message


def test_paper_broker_accepts_valid_positive_finite_values():
    state = PortfolioState(cash=10000)
    broker = PaperBroker(state=state)
    order = Order(symbol="AAPL", side="buy", quantity=10, order_type="limit", limit_price=150.0)
    result = broker.place_order(order)
    assert result.status == "filled"
    assert result.filled is True


@pytest.mark.parametrize("bad_quantity", ["abc", {}, [], object()])
def test_paper_broker_rejects_non_numeric_quantity(bad_quantity):
    state = PortfolioState(cash=10000)
    broker = PaperBroker(state=state)
    initial_cash = state.cash
    order = Order(symbol="AAPL", side="buy", quantity=bad_quantity, order_type="limit", limit_price=100.0)
    result = broker.place_order(order)
    assert result.status == "rejected"
    assert "positive quantity" in result.message
    assert state.cash == initial_cash
    assert not state.positions


@pytest.mark.parametrize("bad_price", ["abc", {}, [], object()])
def test_paper_broker_rejects_non_numeric_limit_price(bad_price):
    state = PortfolioState(cash=10000)
    broker = PaperBroker(state=state)
    initial_cash = state.cash
    order = Order(symbol="AAPL", side="buy", quantity=10, order_type="limit", limit_price=bad_price)
    result = broker.place_order(order)
    assert result.status == "rejected"
    assert "positive price" in result.message
    assert state.cash == initial_cash
    assert not state.positions


@pytest.mark.parametrize("bad_quantity", [True, False])
def test_paper_broker_rejects_boolean_quantity(bad_quantity):
    state = PortfolioState(cash=10000)
    broker = PaperBroker(state=state)
    initial_cash = state.cash
    order = Order(symbol="AAPL", side="buy", quantity=bad_quantity, order_type="limit", limit_price=100.0)
    result = broker.place_order(order)
    assert result.status == "rejected"
    assert "positive quantity" in result.message
    assert state.cash == initial_cash
    assert not state.positions


@pytest.mark.parametrize("bad_price", [True, False])
def test_paper_broker_rejects_boolean_limit_price(bad_price):
    state = PortfolioState(cash=10000)
    broker = PaperBroker(state=state)
    initial_cash = state.cash
    order = Order(symbol="AAPL", side="buy", quantity=10, order_type="limit", limit_price=bad_price)
    result = broker.place_order(order)
    assert result.status == "rejected"
    assert "positive price" in result.message
    assert state.cash == initial_cash
    assert not state.positions
