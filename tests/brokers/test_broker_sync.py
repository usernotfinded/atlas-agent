from __future__ import annotations

import threading
import time

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
    assert result.errors[0] == "sync_positions failed [broker_operation_failed]: broker operation failed"
    assert result.diagnostics["broker_errors"] == [
        {
            "code": "broker_operation_failed",
            "operation": "sync_positions",
            "broker": "failingprovider",
            "message": "broker operation failed",
        }
    ]


def test_portfolio_snapshot_includes_sync_provenance(paper_adapter):
    sync_service = BrokerSyncService(broker=paper_adapter)
    result = sync_service.sync()
    snapshot = sync_service.get_portfolio_snapshot(result, broker_id="paper")

    assert snapshot.synced_at is not None
    assert snapshot.sync_status == "success"
    assert snapshot.sync_source == "broker_sync"
    assert snapshot.broker_id == "paper"


def test_sync_service_parallelizes_independent_reads():
    class SlowProvider:
        def __init__(self):
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def _call(self, value):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.05)
            with self.lock:
                self.active -= 1
            return value

        def get_account_state(self):
            return self._call(None)

        def get_positions(self):
            return self._call([])

        def get_open_orders(self):
            return self._call([])

        def get_balances(self):
            return self._call([])

    provider = SlowProvider()
    result = BrokerSyncService(broker=provider).sync()  # type: ignore[arg-type]

    assert result.status == "success"
    assert provider.max_active > 1
