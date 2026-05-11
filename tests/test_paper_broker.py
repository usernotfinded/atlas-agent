from __future__ import annotations

from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.execution.order import Order
from atlas_agent.portfolio.positions import Position
from atlas_agent.portfolio.state import PortfolioState


def test_paper_broker_works() -> None:
    state = PortfolioState(cash=1_000)
    broker = PaperBroker(state)

    result = broker.place_order(Order("TEST-A", "buy", 1, limit_price=100))

    assert result.accepted
    assert result.filled
    assert state.cash == 900
    assert state.positions["TEST-A"].quantity == 1


def test_paper_broker_flatten_all_closes_open_positions() -> None:
    state = PortfolioState(cash=10_000)
    broker = PaperBroker(state)
    broker.place_order(Order("TEST-A", "buy", 1, limit_price=100))
    broker.place_order(Order("TEST-B", "buy", 2, limit_price=50))

    result = broker.flatten_all(strategy="market", bps=25)

    assert result.accepted
    assert result.status == "flattened"
    assert result.attempted == 2
    assert result.closed == 2
    assert result.failed == 0
    assert state.positions["TEST-A"].quantity == 0
    assert state.positions["TEST-B"].quantity == 0


def test_paper_broker_flatten_all_is_idempotent_on_second_call() -> None:
    state = PortfolioState(cash=10_000)
    broker = PaperBroker(state)
    broker.place_order(Order("TEST-A", "buy", 1, limit_price=100))

    first = broker.flatten_all(strategy="aggressive_limit", bps=20)
    second = broker.flatten_all(strategy="aggressive_limit", bps=20)

    assert first.status == "flattened"
    assert first.closed == 1
    assert second.accepted
    assert second.status == "noop"
    assert second.attempted == 0


def test_paper_broker_flatten_all_reports_partial_success() -> None:
    state = PortfolioState(cash=10_000)
    state.positions["TEST-A"] = Position(symbol="TEST-A", quantity=1.0, average_price=100.0)
    state.positions["TEST-B"] = Position(symbol="TEST-B", quantity=-1.0, average_price=50.0)
    broker = PaperBroker(state)

    result = broker.flatten_all(strategy="market", bps=25)

    assert result.accepted
    assert result.status == "partial"
    assert result.attempted == 2
    assert result.closed == 1
    assert result.failed == 1
    assert result.failed_symbols == ("TEST-B",)
    assert state.positions["TEST-A"].quantity == 0
