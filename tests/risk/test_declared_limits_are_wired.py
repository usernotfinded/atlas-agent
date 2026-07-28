# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/risk/test_declared_limits_are_wired.py
# PURPOSE: States, executably, which limits `RiskLimits` declares and `RiskManager`
#         actually evaluates.
# DEPS:    pytest, atlas_agent.risk.
# ==============================================================================

"""Coverage for hard invariant 5's list of enforced limits.

`docs/bounded-live-autonomy-governance.md` invariant 5 says `RiskManager`
enforces "hard-coded limits on position size, notional, daily loss, exposure,
symbols, and leverage". Four of those six are enforced and have rules. Two are
not:

- `max_daily_loss_pct` is declared in `RiskLimits` and read by no rule.
  `realized_pnl_today` is carried from `PortfolioState` through
  `PortfolioSnapshot` into every evaluation and then ignored — and nothing in
  `src/` ever increments it, so the chain is a stub at both ends.
- `OrderRiskInput.leverage` is populated from the order on both the paper and
  the live-submit path, and read by no rule. No broker adapter forwards it
  either, so today it is a field nothing acts on.

The two enforced-limit tests are `xfail`: they state the behaviour the invariant
promises, so implementing it turns them green and the marker into a visible
XPASS that has to be removed. Asserting the current behaviour instead would
record the gap as intended and have to be deleted by whoever closes it.

The third test is not `xfail`. It pins the four limits that do work, so this
file cannot quietly become a list of things that used to be checked.

`docs/development/safety-invariant-audit-followups.md` records the finding and
`CAND-033` proposes the work.
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


@pytest.mark.xfail(
    reason=(
        "max_daily_loss_pct is declared in RiskLimits and evaluated by no rule. "
        "realized_pnl_today reaches every evaluation and is ignored, and nothing "
        "in src/ increments it. See CAND-033."
    ),
    strict=True,
)
def test_a_day_past_the_loss_limit_blocks_the_next_order() -> None:
    """A portfolio 50% down on the day, against a 2% limit, must not keep trading."""
    limits = RiskLimits()
    assert limits.max_daily_loss_pct == 0.02

    breached = -EQUITY * 0.5
    violations = _violations(_order(), _portfolio(realized_pnl_today=breached))

    assert "max_daily_loss_pct" in violations


@pytest.mark.xfail(
    reason=(
        "OrderRiskInput.leverage is populated on both order paths and evaluated by "
        "no rule. No broker adapter forwards it either. See CAND-033."
    ),
    strict=True,
)
def test_a_leveraged_order_is_rejected() -> None:
    """`allow_leverage` defaults to false, so a 10x order has nothing authorising it."""
    violations = _violations(_order(leverage=10.0), _portfolio())

    assert violations != []


@pytest.mark.xfail(
    reason=(
        "max_trades_per_day is configured, defaults to 5, and is printed by "
        "`atlas risk check`, but RiskLimits has no such field and no rule reads "
        "trades_today — which the paper broker does increment. See CAND-033."
    ),
    strict=True,
)
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
