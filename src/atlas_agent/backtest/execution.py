# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    backtest/execution.py
# PURPOSE: Simulates how an order would have filled. This is where a backtest is
#          honest or a lie: an execution model that ignores slippage and commission
#          produces the P&L of a market that does not exist.
# DEPS:    backtest.models
#
# NOTE:    Optimistic by construction. Limit orders are assumed to fill whenever the
#          bar merely TOUCHED the price, and market orders at the close. Real fills
#          face queue position and partial fills; treat backtest results as an upper
#          bound, not an expectation.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from datetime import datetime
from typing import Optional

from atlas_agent.backtest.models import (
    BacktestOrder,
    BacktestFill,
    MarketBar,
    BacktestConfig
)


# ==============================================================================
# EXECUTION SIMULATOR
# ==============================================================================

class ExecutionSimulator:
    def __init__(self, config: BacktestConfig):
        self.config = config

    def process_order(
        self,
        order: BacktestOrder,
        bar: MarketBar
    ) -> Optional[BacktestFill]:
        """
        Simulate deterministic execution.
        Market orders fill at the current bar's close (simplified for MVP).
        Limit orders fill if the price was touched.
        """
        if order.status != "proposed":
            return None

        fill_price = 0.0
        can_fill = False

        if order.type == "market":
            fill_price = bar.close
            can_fill = True
        elif order.type == "limit":
            if order.price is None:
                return None

            # Touch-fill: if the bar's range crossed the limit, assume we filled at it.
            # Generous — in reality a touched limit may never reach the front of the
            # queue — but it is at least DETERMINISTIC, which a probabilistic model
            # would not be. See the module warning.
            if bar.low <= order.price <= bar.high:
                fill_price = order.price
                can_fill = True

        if can_fill:
            # Slippage always works AGAINST us: a buy fills higher, a sell lower. Any
            # other sign convention would manufacture free money in every backtest.
            slippage_amt = 0.0
            if self.config.slippage_bps > 0:
                slippage_factor = self.config.slippage_bps / 10000.0
                slippage_amt = fill_price * slippage_factor
                if order.side == "buy":
                    fill_price += slippage_amt
                else:
                    fill_price -= slippage_amt

            # Notional is computed from the POST-slippage price, so commission is
            # charged on what we actually paid rather than on the ideal price.
            notional = order.quantity * fill_price

            commission_amt = 0.0
            if self.config.commission_bps > 0:
                commission_amt = notional * (self.config.commission_bps / 10000.0)

            return BacktestFill(
                fill_id=f"fill-{order.order_id}",
                order_id=order.order_id,
                timestamp=bar.timestamp,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=fill_price,
                notional=notional,
                commission=commission_amt,
                slippage=slippage_amt
            )
        
        return None
