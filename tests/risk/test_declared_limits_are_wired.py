# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/risk/test_declared_limits_are_wired.py
# PURPOSE: States, executably, which limits `RiskLimits` declares and `RiskManager`
#         actually evaluates.
# DEPS:    pytest, atlas_agent.risk.
# ==============================================================================

"""Every limit the project declares is a limit `RiskManager` evaluates.

`docs/bounded-live-autonomy-governance.md` invariant 5 says `RiskManager`
enforces "hard-coded limits on position size, notional, daily loss, exposure,
symbols, and leverage", and `atlas risk check` additionally shows the operator a
max-trades-per-day. Four of those were enforced. Three were not: a portfolio 50%
down on the day against a 2% ceiling passed with zero violations, as did an order
carrying 10x leverage and a session that had already made a hundred trades.

They are enforced now, which is a prerequisite for the L3 bounded-live-autonomy
tier — that rung requires "strict RiskManager limits", and limits that evaluate
nothing do not qualify.

The daily-loss chain needed both ends built. `realized_pnl_today` had existed on
`PortfolioState` since the beginning, documented as backing this limit, and
nothing ever wrote it; the paper broker now records it at the fill, where the
position's average price is still known.

Two ceilings, not one: the config carries an absolute `max_daily_loss` while
`RiskLimits` carries a percentage. Those are different units and neither
substitutes for the other, so both bind and whichever is hit first stops new
risk.

The case that matters most is the last one. A session halt must never trap a
position open — an operator who has hit the loss limit has to be able to close
what they are holding, so these limits refuse new risk and let risk reduction
through.
"""

# --- IMPORTS ---

from __future__ import annotations

import pytest

from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot

# --- CONFIGURATION AND CONSTANTS ---

EQUITY = 100_000.0


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _order(**overrides: object) -> OrderRiskInput:
    """A small order that passes every limit that is wired."""
    fields: dict[str, object] = {
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 1,
        "price": 100.0,
        "notional": 100.0,
        "leverage": 1.0,
        "confidence": 0.9,
        "stop_loss": 90.0,
    }
    fields.update(overrides)
    return OrderRiskInput(**fields)  # type: ignore[arg-type]


def _portfolio(**overrides: object) -> PortfolioSnapshot:
    fields: dict[str, object] = {
        "equity": EQUITY,
        "cash": EQUITY,
        "total_exposure": 0.0,
    }
    fields.update(overrides)
    return PortfolioSnapshot(**fields)  # type: ignore[arg-type]


def _violations(order: OrderRiskInput, portfolio: PortfolioSnapshot) -> list[str]:
    decision = RiskManager().evaluate_order(order, portfolio)
    return [violation.rule for violation in decision.violations or []]


def test_a_clean_order_passes() -> None:
    """The baseline the two xfail cases below are measured against.

    Without it, those cases could be failing because the fixture is malformed
    rather than because the limit is missing.
    """
    assert _violations(_order(), _portfolio()) == []


def test_a_day_past_the_loss_limit_blocks_the_next_order() -> None:
    """A portfolio 50% down on the day, against a 2% limit, must not keep trading."""
    limits = RiskLimits()
    assert limits.max_daily_loss_pct == 0.02

    breached = -EQUITY * 0.5
    violations = _violations(_order(), _portfolio(realized_pnl_today=breached))

    assert "max_daily_loss_pct" in violations


def test_a_leveraged_order_is_rejected() -> None:
    """`allow_leverage` defaults to false, so a 10x order has nothing authorising it."""
    violations = _violations(_order(leverage=10.0), _portfolio())

    assert violations != []


def test_the_daily_trade_count_limit_is_enforced() -> None:
    """The one an operator is shown directly.

    `atlas risk check` prints three lines — kill switch, max position size, and
    max trades per day. The first two are enforced. An operator reading the third
    has been told a limit exists.
    """
    from atlas_agent.config import AtlasConfig

    assert AtlasConfig().max_trades_per_day == 5

    violations = _violations(_order(), _portfolio(trades_today=100))

    assert violations != []


@pytest.mark.parametrize(
    "label, order, portfolio, expected_rule",
    [
        (
            "single-trade notional",
            _order(quantity=100_000, notional=10_000_000.0),
            _portfolio(),
            "max_single_trade_notional",
        ),
        (
            "blocked symbol",
            _order(symbol="BLOCKED"),
            _portfolio(),
            "blocked_symbols",
        ),
        (
            "portfolio exposure",
            _order(),
            _portfolio(total_exposure=EQUITY * 5),
            "max_portfolio_exposure_pct",
        ),
    ],
)
def test_the_wired_limits_still_reject(
    label: str,
    order: OrderRiskInput,
    portfolio: PortfolioSnapshot,
    expected_rule: str,
) -> None:
    """The limits that do work, pinned.

    Two of invariant 5's six limits are missing. This is what stops a third from
    going the same way unnoticed.
    """
    limits = RiskLimits(blocked_symbols={"BLOCKED"})
    decision = RiskManager(limits=limits).evaluate_order(order, portfolio)
    rules = [violation.rule for violation in decision.violations or []]

    assert expected_rule in rules, f"{label}: expected {expected_rule}, got {rules}"


def test_the_absolute_daily_loss_ceiling_also_binds() -> None:
    """The config's `max_daily_loss` is currency, not a percentage.

    Folding it into `max_daily_loss_pct` would read 100.0 as 10000% of equity —
    the wrong-domain write this project has fixed elsewhere — so it has its own
    ceiling and both apply.
    """
    limits = RiskLimits(max_daily_loss_notional=100.0)
    decision = RiskManager(limits=limits).evaluate_order(
        _order(), _portfolio(realized_pnl_today=-150.0)
    )

    assert "max_daily_loss_notional" in [v.rule for v in decision.violations or []]


def test_a_session_halt_never_blocks_closing_a_position() -> None:
    """The property the whole design turns on.

    An operator who has hit the daily loss limit, or the trade count, still has a
    position open. Refusing the order that closes it would trap them in the loss
    the limit exists to stop — so these limits refuse new risk only.
    """
    from atlas_agent.risk.models import RiskPosition

    held = RiskPosition(
        symbol="AAPL", quantity=10, average_price=100.0,
        market_price=100.0, notional=1000.0, side="long",
    )
    battered = _portfolio(
        total_exposure=1000.0,
        positions=[held],
        realized_pnl_today=-EQUITY * 0.5,
        trades_today=100,
    )

    closing = OrderRiskInput(
        symbol="AAPL", side="sell", quantity=10, price=100.0,
        notional=1000.0, leverage=1.0, confidence=0.9, stop_loss=None,
    )
    opening = OrderRiskInput(
        symbol="AAPL", side="buy", quantity=1, price=100.0,
        notional=100.0, leverage=1.0, confidence=0.9, stop_loss=90.0,
    )

    assert RiskManager().evaluate_order(closing, battered).allowed is True, (
        "a session halt blocked a risk-reducing order, trapping the position open"
    )
    assert RiskManager().evaluate_order(opening, battered).allowed is False


def test_the_paper_broker_records_the_loss_the_limit_reads() -> None:
    """A ceiling over a number nobody writes is not a limit.

    `realized_pnl_today` was declared, plumbed into every evaluation, and left at
    zero forever. This is the write that makes the daily-loss limit mean
    something.
    """
    from atlas_agent.brokers.paper import PaperBroker
    from atlas_agent.execution.order import Order
    from atlas_agent.portfolio.state import PortfolioState

    state = PortfolioState(cash=10_000.0)
    broker = PaperBroker(state=state)
    broker.place_order(
        Order(symbol="AAPL", side="buy", quantity=10, limit_price=100.0, order_type="limit")
    )
    assert state.realized_pnl_today == 0.0, "an opening fill realizes nothing"

    broker.place_order(
        Order(symbol="AAPL", side="sell", quantity=10, limit_price=90.0, order_type="limit")
    )
    assert state.realized_pnl_today == pytest.approx(-100.0)
