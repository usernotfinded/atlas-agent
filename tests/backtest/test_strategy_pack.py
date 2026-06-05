from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from atlas_agent.backtest.benchmarks import SPYBenchmark
from atlas_agent.backtest.models import BacktestConfig, BacktestPosition, MarketBar
from atlas_agent.backtest.registry import default_strategy_registry
from atlas_agent.backtest.strategy import StrategyContext
from atlas_agent.backtest.strategies import MovingAverageCrossStrategy, RSIMeanReversionStrategy


def _bars(closes: list[float], symbol: str = "AAPL") -> list[MarketBar]:
    base = datetime(2026, 1, 1)
    return [
        MarketBar(
            timestamp=base + timedelta(days=index),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1000,
            symbol=symbol,
        )
        for index, close in enumerate(closes)
    ]


def _context(
    *,
    strategy_id: str,
    bar_index: int,
    position_quantity: float = 0.0,
) -> StrategyContext:
    positions = {}
    if position_quantity:
        positions["AAPL"] = BacktestPosition(
            symbol="AAPL",
            quantity=position_quantity,
            average_entry_price=10.0,
            notional=position_quantity * 10.0,
        )
    return StrategyContext(
        run_id=f"test-{strategy_id}",
        symbol="AAPL",
        bar_index=bar_index,
        cash=1000.0,
        positions=positions,
        pending_orders=[],
        config=BacktestConfig(
            run_id=f"test-{strategy_id}",
            symbol="AAPL",
            data_path="unused.csv",
            risk_enabled=False,
        ),
    )


def test_moving_average_cross_generates_entry_order() -> None:
    bars = _bars([10, 10, 10, 9, 12])
    strategy = MovingAverageCrossStrategy(short_window=2, long_window=3, position_pct=0.5)

    orders = strategy.generate_orders(
        bars=bars,
        context=_context(strategy_id="mac", bar_index=len(bars) - 1),
    )

    assert len(orders) == 1
    assert orders[0].side == "buy"
    assert orders[0].quantity == pytest.approx((1000.0 * 0.5) / 12)
    assert orders[0].order_id == "test-mac-000004-moving_average_cross-buy"


def test_moving_average_cross_generates_exit_order() -> None:
    bars = _bars([10, 9, 12, 12, 8])
    strategy = MovingAverageCrossStrategy(short_window=2, long_window=3)

    orders = strategy.generate_orders(
        bars=bars,
        context=_context(strategy_id="mac", bar_index=len(bars) - 1, position_quantity=7.0),
    )

    assert len(orders) == 1
    assert orders[0].side == "sell"
    assert orders[0].quantity == 7.0


def test_rsi_mean_reversion_generates_entry_and_exit_orders() -> None:
    entry = RSIMeanReversionStrategy(period=3, oversold=30.0, overbought=70.0, position_pct=0.25)

    entry_orders = entry.generate_orders(
        bars=_bars([10, 9, 8, 7]),
        context=_context(strategy_id="rsi", bar_index=3),
    )
    exit_orders = entry.generate_orders(
        bars=_bars([7, 8, 9, 10]),
        context=_context(strategy_id="rsi", bar_index=3, position_quantity=4.0),
    )

    assert entry_orders[0].side == "buy"
    assert entry_orders[0].quantity == pytest.approx((1000.0 * 0.25) / 7)
    assert exit_orders[0].side == "sell"
    assert exit_orders[0].quantity == 4.0


def test_invalid_cross_parameter_relationship_raises() -> None:
    registry = default_strategy_registry(include_entry_points=False)

    with pytest.raises(ValueError, match="short_window"):
        registry.get(
            "moving_average_cross",
            parameters={"short_window": 5, "long_window": 3},
        )


def test_spy_benchmark_uses_local_data(tmp_path) -> None:
    data_path = tmp_path / "spy.csv"
    data_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-01,SPY,100,101,99,100,1000\n"
        "2026-01-02,SPY,110,111,109,110,1000\n",
        encoding="utf-8",
    )

    result = SPYBenchmark(str(data_path)).calculate(_bars([10, 11]))

    assert result.benchmark_id == "spy"
    assert result.symbol == "SPY"
    assert result.return_pct == 10.0
    assert result.data_path == str(data_path)
