# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    backtest/demo_strategy.py
# PURPOSE: A trivial strategy used to exercise the stateful paper loop end to end.
#          A test fixture, not a trading idea.
# DEPS:    backtest.strategy (the contract), backtest.models
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from atlas_agent.backtest.models import BacktestOrder, MarketBar
from atlas_agent.backtest.strategy import (
    StrategyContext,
    StrategyMetadata,
    StrategyParameterSpec,
)


@dataclass(frozen=True)
class DemoStatefulPaperStrategy:
    """Deterministic demo strategy for the CAND-003 stateful paper runner.

    Generates a buy on ``entry_bar``, holds until ``exit_bar``, then attempts a
    sell. This is intentionally simple and paper-only: it lets a demo show a
    fill, subsequent holds, and a risk rejection on the sell without depending
    on market-data patterns.
    """

    entry_bar: int = 2
    exit_bar: int = 5
    position_pct: float = 1.0

    metadata = StrategyMetadata(
        strategy_id="demo_stateful_paper",
        name="Demo Stateful Paper",
        description=(
            "Deterministic demo strategy: buy at entry_bar, hold until "
            "exit_bar, then sell. Intended for paper-only demonstrations."
        ),
        version="1.0",
        parameters={
            "entry_bar": StrategyParameterSpec(
                type="int",
                description="Bar index (0-based) on which to enter a long position.",
                default=2,
                min_value=0,
            ),
            "exit_bar": StrategyParameterSpec(
                type="int",
                description="Bar index (0-based) on which to exit the long position.",
                default=5,
                min_value=0,
            ),
            "position_pct": StrategyParameterSpec(
                type="float",
                description="Fraction of available cash to allocate on entry.",
                default=1.0,
                min_value=0.0,
                max_value=1.0,
            ),
        },
        tags=["builtin", "demo", "paper-only"],
    )

    def __post_init__(self) -> None:
        if self.exit_bar <= self.entry_bar:
            raise ValueError("exit_bar must be greater than entry_bar")

    def generate_orders(
        self, *, bars: Sequence[MarketBar], context: StrategyContext
    ) -> list[BacktestOrder]:
        if context.bar_index < self.entry_bar or context.pending_orders:
            return []

        bar = bars[-1]
        position = context.positions.get(context.symbol)
        has_position = position is not None and position.quantity > 0

        if not has_position:
            if bar.open <= 0 or context.cash <= 0:
                return []
            quantity = (context.cash * self.position_pct) / bar.open
            if quantity <= 0:
                return []
            return [
                BacktestOrder(
                    order_id=f"{context.run_id}-{context.bar_index:06d}-demo-buy",
                    timestamp=bar.timestamp,
                    symbol=bar.symbol or context.symbol,
                    side="buy",
                    quantity=quantity,
                    price=bar.open,
                )
            ]

        if context.bar_index >= self.exit_bar:
            return [
                BacktestOrder(
                    order_id=f"{context.run_id}-{context.bar_index:06d}-demo-sell",
                    timestamp=bar.timestamp,
                    symbol=bar.symbol or context.symbol,
                    side="sell",
                    quantity=position.quantity,
                    price=bar.open,
                )
            ]

        return []
