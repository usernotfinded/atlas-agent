from __future__ import annotations

from omni_trade_ai.brokers.paper import PaperBroker
from omni_trade_ai.execution.order import Order
from omni_trade_ai.portfolio.state import PortfolioState


def test_paper_broker_works() -> None:
    state = PortfolioState(cash=1_000)
    broker = PaperBroker(state)

    result = broker.place_order(Order("BTC-USD", "buy", 1, limit_price=100))

    assert result.accepted
    assert result.filled
    assert state.cash == 900
    assert state.positions["BTC-USD"].quantity == 1

