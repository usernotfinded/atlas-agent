# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/risk/test_risk_manager.py
# PURPOSE: Verifies the risk gate rejects unusable portfolio state instead of
#         evaluating limits against it.
# DEPS:    atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from atlas_agent.risk.manager import RiskManager
from atlas_agent.risk.models import OrderRiskInput, PortfolioSnapshot, RiskPosition


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestNonFinitePortfolioState:
    """A non-finite portfolio figure must block, not disable the limit."""

    def _order(self):
        return OrderRiskInput(
            symbol="AAA", side="buy", quantity=4, price=100.0, notional=400.0
        )

    def test_nan_equity_no_longer_bypasses_percentage_limits(self):
        """Regression: NaN equity let an order through with zero violations.

        The percentage limits take their ceiling from equity, so `equity = NaN`
        made `projected > ceiling` false and both limits stopped rejecting. An
        order inside the absolute notional caps then passed the gate entirely.
        """
        manager = RiskManager()
        healthy = manager.evaluate_order(
            self._order(),
            PortfolioSnapshot(cash=100.0, equity=100.0, total_exposure=0.0),
        )
        assert healthy.allowed is False
        assert {"max_symbol_exposure_pct", "max_portfolio_exposure_pct"} <= {
            v.rule for v in healthy.violations
        }

        nan_equity = manager.evaluate_order(
            self._order(),
            PortfolioSnapshot(cash=100.0, equity=float("nan"), total_exposure=0.0),
        )
        assert nan_equity.allowed is False
        assert [v.rule for v in nan_equity.violations] == ["invalid_portfolio_state"]

    def test_infinite_equity_is_blocked(self):
        manager = RiskManager()
        decision = manager.evaluate_order(
            self._order(),
            PortfolioSnapshot(cash=100.0, equity=float("inf"), total_exposure=0.0),
        )
        assert decision.allowed is False
        assert decision.violations[0].rule == "invalid_portfolio_state"

    def test_non_finite_total_exposure_is_blocked(self):
        manager = RiskManager()
        decision = manager.evaluate_order(
            self._order(),
            PortfolioSnapshot(
                cash=100.0, equity=100000.0, total_exposure=float("nan")
            ),
        )
        assert decision.allowed is False
        assert decision.violations[0].rule == "invalid_portfolio_state"

    def test_non_finite_position_notional_is_blocked(self):
        manager = RiskManager()
        decision = manager.evaluate_order(
            self._order(),
            PortfolioSnapshot(
                cash=100.0,
                equity=100000.0,
                total_exposure=0.0,
                positions=[
                    RiskPosition(
                        symbol="AAA",
                        quantity=1.0,
                        average_price=100.0,
                        market_price=100.0,
                        notional=float("nan"),
                        side="long",
                    )
                ],
            ),
        )
        assert decision.allowed is False
        assert decision.violations[0].rule == "invalid_portfolio_state"

    def test_healthy_portfolio_is_unaffected(self):
        manager = RiskManager()
        decision = manager.evaluate_order(
            OrderRiskInput(
                symbol="AAA", side="buy", quantity=1, price=100.0, notional=100.0
            ),
            PortfolioSnapshot(cash=10000.0, equity=10000.0, total_exposure=0.0),
        )
        assert "invalid_portfolio_state" not in {v.rule for v in decision.violations}
