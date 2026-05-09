from __future__ import annotations

import pytest
from atlas_agent.brokers.paper import PaperBroker, PaperBrokerAdapter
from atlas_agent.brokers.sync import BrokerSyncService
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.brokers.models import BrokerOrder


@pytest.fixture
def paper_adapter():
    state = PortfolioState(cash=50000)
    broker = PaperBroker(state=state)
    return PaperBrokerAdapter(broker=broker)


def test_paper_adapter_deterministic_state(paper_adapter):
    acc = paper_adapter.get_account_state()
    assert acc.cash == 50000
    assert acc.is_live is False
    assert len(paper_adapter.get_positions()) == 0
    assert len(paper_adapter.get_open_orders()) == 0


def test_sync_service_normalizes_to_snapshot(paper_adapter):
    # Add a position and an order to paper broker
    paper_adapter.broker.state.positions["AAPL"] = __import__("atlas_agent.portfolio.positions", fromlist=["Position"]).Position(
        symbol="AAPL", quantity=10, average_price=150
    )
    paper_adapter.broker.open_orders_list.append(
        BrokerOrder(order_id="o1", symbol="MSFT", side="buy", quantity=5, status="open")
    )
    
    sync_service = BrokerSyncService(broker=paper_adapter)
    result = sync_service.sync()
    
    assert result.status == "success"
    assert len(result.positions) == 1
    assert len(result.open_orders) == 1
    
    snapshot = sync_service.get_portfolio_snapshot(result)
    assert snapshot.cash == 50000
    assert len(snapshot.positions) == 1
    assert snapshot.positions[0].symbol == "AAPL"
    assert len(snapshot.open_orders) == 1
    assert snapshot.open_orders[0].order_id == "o1"
    assert snapshot.open_orders[0].symbol == "MSFT"


def test_sync_service_handles_partial_failure():
    class FailingProvider:
        def get_account_state(self): return None
        def get_positions(self): raise ValueError("Fail positions")
        def get_open_orders(self): return []
        def get_balances(self): return []
        
    sync_service = BrokerSyncService(broker=FailingProvider()) # type: ignore
    result = sync_service.sync()
    
    assert result.status == "partial"
    assert "Fail positions" in result.errors[0]
