from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Sequence

from atlas_agent.backtest.models import BacktestOrder, MarketBar
from atlas_agent.backtest.strategy import (
    StrategyContext,
    StrategyMetadata,
    StrategyParameterSpec,
)


def _position_quantity(context: StrategyContext) -> float:
    position = context.positions.get(context.symbol)
    return position.quantity if position else 0.0


def _buy_order(
    *,
    strategy_id: str,
    bars: Sequence[MarketBar],
    context: StrategyContext,
    position_pct: float,
) -> list[BacktestOrder]:
    bar = bars[-1]
    if bar.open <= 0 or context.cash <= 0:
        return []
    quantity = (context.cash * position_pct) / bar.open
    if quantity <= 0:
        return []
    return [
        BacktestOrder(
            order_id=f"{context.run_id}-{context.bar_index:06d}-{strategy_id}-buy",
            timestamp=bar.timestamp,
            symbol=bar.symbol or context.symbol,
            side="buy",
            quantity=quantity,
            price=bar.open,
        )
    ]


def _sell_order(
    *,
    strategy_id: str,
    bars: Sequence[MarketBar],
    context: StrategyContext,
    quantity: float,
) -> list[BacktestOrder]:
    if quantity <= 0:
        return []
    bar = bars[-1]
    return [
        BacktestOrder(
            order_id=f"{context.run_id}-{context.bar_index:06d}-{strategy_id}-sell",
            timestamp=bar.timestamp,
            symbol=bar.symbol or context.symbol,
            side="sell",
            quantity=quantity,
            price=bar.open,
        )
    ]


@dataclass(frozen=True)
class BuyAndHoldStrategy:
    position_pct: float = 1.0

    metadata = StrategyMetadata(
        strategy_id="buy_and_hold",
        name="Buy and Hold",
        description=(
            "Open one long market position on the first eligible bar and hold it "
            "for the rest of the backtest."
        ),
        version="1.1",
        parameters={
            "position_pct": StrategyParameterSpec(
                type="float",
                description="Fraction of available cash to allocate on the opening order.",
                default=1.0,
                min_value=0.0,
                max_value=1.0,
            )
        },
        tags=["builtin", "benchmark-compatible", "long-only"],
    )

    def generate_orders(self, *, bars, context: StrategyContext) -> list[BacktestOrder]:
        if not bars or context.positions or context.pending_orders:
            return []
        bar = bars[-1]
        if bar.open <= 0 or context.cash <= 0:
            return []
        quantity = (context.cash * self.position_pct) / bar.open
        if quantity <= 0:
            return []
        return [
            BacktestOrder(
                order_id=f"{context.run_id}-{context.bar_index:06d}-buy-and-hold",
                timestamp=bar.timestamp,
                symbol=bar.symbol or context.symbol,
                side="buy",
                quantity=quantity,
                price=bar.open,
            )
        ]


@dataclass(frozen=True)
class MovingAverageCrossStrategy:
    short_window: int = 3
    long_window: int = 5
    position_pct: float = 1.0
    exit_on_cross: bool = True

    metadata = StrategyMetadata(
        strategy_id="moving_average_cross",
        name="Moving Average Cross",
        description=(
            "Open a long position when the short moving average crosses above "
            "the long moving average, and optionally close on the opposite cross."
        ),
        version="1.0",
        parameters={
            "short_window": StrategyParameterSpec(
                type="int",
                description="Number of bars in the short moving average.",
                default=3,
                min_value=1,
            ),
            "long_window": StrategyParameterSpec(
                type="int",
                description="Number of bars in the long moving average.",
                default=5,
                min_value=2,
            ),
            "position_pct": StrategyParameterSpec(
                type="float",
                description="Fraction of available cash to allocate on entry.",
                default=1.0,
                min_value=0.0,
                max_value=1.0,
            ),
            "exit_on_cross": StrategyParameterSpec(
                type="bool",
                description="Close the long position when the short average crosses below the long average.",
                default=True,
            ),
        },
        tags=["builtin", "trend", "long-only"],
    )

    def __post_init__(self) -> None:
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be less than long_window")

    def generate_orders(self, *, bars, context: StrategyContext) -> list[BacktestOrder]:
        required = self.long_window + 1
        if len(bars) < required or context.pending_orders:
            return []

        closes = [bar.close for bar in bars]
        previous_short = fmean(closes[-self.short_window - 1 : -1])
        previous_long = fmean(closes[-self.long_window - 1 : -1])
        current_short = fmean(closes[-self.short_window :])
        current_long = fmean(closes[-self.long_window :])
        quantity = _position_quantity(context)

        crossed_up = previous_short <= previous_long and current_short > current_long
        crossed_down = previous_short >= previous_long and current_short < current_long

        if quantity <= 0 and crossed_up:
            return _buy_order(
                strategy_id=self.metadata.strategy_id,
                bars=bars,
                context=context,
                position_pct=self.position_pct,
            )
        if quantity > 0 and self.exit_on_cross and crossed_down:
            return _sell_order(
                strategy_id=self.metadata.strategy_id,
                bars=bars,
                context=context,
                quantity=quantity,
            )
        return []


@dataclass(frozen=True)
class RSIMeanReversionStrategy:
    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    position_pct: float = 1.0

    metadata = StrategyMetadata(
        strategy_id="rsi_mean_reversion",
        name="RSI Mean Reversion",
        description=(
            "Open a long position when RSI is below the oversold threshold and "
            "close it when RSI is above the overbought threshold."
        ),
        version="1.0",
        parameters={
            "period": StrategyParameterSpec(
                type="int",
                description="Number of close-to-close changes used for RSI.",
                default=14,
                min_value=2,
            ),
            "oversold": StrategyParameterSpec(
                type="float",
                description="RSI threshold used for long entries.",
                default=30.0,
                min_value=0.0,
                max_value=100.0,
            ),
            "overbought": StrategyParameterSpec(
                type="float",
                description="RSI threshold used for exits.",
                default=70.0,
                min_value=0.0,
                max_value=100.0,
            ),
            "position_pct": StrategyParameterSpec(
                type="float",
                description="Fraction of available cash to allocate on entry.",
                default=1.0,
                min_value=0.0,
                max_value=1.0,
            ),
        },
        tags=["builtin", "mean-reversion", "long-only"],
    )

    def __post_init__(self) -> None:
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be less than overbought")

    def generate_orders(self, *, bars, context: StrategyContext) -> list[BacktestOrder]:
        if len(bars) < self.period + 1 or context.pending_orders:
            return []

        rsi = _rsi([bar.close for bar in bars], self.period)
        quantity = _position_quantity(context)
        if quantity <= 0 and rsi <= self.oversold:
            return _buy_order(
                strategy_id=self.metadata.strategy_id,
                bars=bars,
                context=context,
                position_pct=self.position_pct,
            )
        if quantity > 0 and rsi >= self.overbought:
            return _sell_order(
                strategy_id=self.metadata.strategy_id,
                bars=bars,
                context=context,
                quantity=quantity,
            )
        return []


def _rsi(closes: Sequence[float], period: int) -> float:
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    window = changes[-period:]
    gains = [change for change in window if change > 0]
    losses = [-change for change in window if change < 0]
    average_gain = sum(gains) / period
    average_loss = sum(losses) / period
    if average_loss == 0:
        return 100.0
    if average_gain == 0:
        return 0.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))
