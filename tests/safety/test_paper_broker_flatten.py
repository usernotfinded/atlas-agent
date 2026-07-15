# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_paper_broker_flatten.py
# PURPOSE: Verifies paper broker flatten behavior and regression expectations.
# DEPS:    atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from atlas_agent.brokers.paper import PaperBroker
from atlas_agent.execution.order import Order
from atlas_agent.portfolio.positions import Position
from atlas_agent.portfolio.state import PortfolioState


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_paper_flatten_market_closes_multiple_positions() -> None:
    state = PortfolioState(cash=10_000)
    broker = PaperBroker(state)
    broker.place_order(Order("TEST-A", "buy", 1, limit_price=100))
    broker.place_order(Order("TEST-B", "buy", 2, limit_price=50))

    result = broker.flatten_all(strategy="market", bps=25)

    assert result.accepted is True
    assert result.status == "flattened"
    assert result.attempted == 2
    assert result.closed == 2
    assert result.failed == 0
    assert state.positions["TEST-A"].quantity == 0
    assert state.positions["TEST-B"].quantity == 0


def test_paper_flatten_reports_partial_when_short_position_exists() -> None:
    state = PortfolioState(cash=10_000)
    state.positions["TEST-A"] = Position(symbol="TEST-A", quantity=1.0, average_price=100.0)
    state.positions["TEST-B"] = Position(symbol="TEST-B", quantity=-1.0, average_price=50.0)
    broker = PaperBroker(state)

    result = broker.flatten_all(strategy="market", bps=25)

    assert result.accepted is True
    assert result.status == "partial"
    assert result.attempted == 2
    assert result.closed == 1
    assert result.failed == 1
    assert result.failed_symbols == ("TEST-B",)
    assert state.positions["TEST-A"].quantity == 0


def test_paper_flatten_is_idempotent_when_already_flat() -> None:
    state = PortfolioState(cash=10_000)
    broker = PaperBroker(state)
    broker.place_order(Order("TEST-A", "buy", 1, limit_price=100))

    first = broker.flatten_all(strategy="aggressive_limit", bps=20)
    second = broker.flatten_all(strategy="aggressive_limit", bps=20)

    assert first.status == "flattened"
    assert first.closed == 1
    assert second.accepted is True
    assert second.status == "noop"
    assert second.attempted == 0
    assert second.closed == 0
    assert second.failed == 0
