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
