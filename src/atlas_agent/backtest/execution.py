from __future__ import annotations

from datetime import datetime
from typing import Optional

from atlas_agent.backtest.models import (
    BacktestOrder, 
    BacktestFill, 
    MarketBar, 
    BacktestConfig
)


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
            
            # Simplified limit fill: if price is within [low, high]
            if bar.low <= order.price <= bar.high:
                fill_price = order.price
                can_fill = True

        if can_fill:
            # Apply slippage
            slippage_amt = 0.0
            if self.config.slippage_bps > 0:
                slippage_factor = self.config.slippage_bps / 10000.0
                slippage_amt = fill_price * slippage_factor
                if order.side == "buy":
                    fill_price += slippage_amt
                else:
                    fill_price -= slippage_amt

            notional = order.quantity * fill_price
            
            # Apply commission
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
