from __future__ import annotations

from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.execution.order import Order
from atlas_agent.portfolio.state import PortfolioState


def test_paper_broker_works() -> None:
    state = PortfolioState(cash=1_000)
    broker = PaperBroker(state)

    result = broker.place_order(Order("BTC-USD", "buy", 1, limit_price=100))

    assert result.accepted
    assert result.filled
    assert state.cash == 900
    assert state.positions["BTC-USD"].quantity == 1

