from __future__ import annotations

import json
from datetime import datetime

from atlas_agent.backtest.metrics import MetricsCalculator, MetricsInput, TradeRecord, calculate_metrics
from atlas_agent.backtest.models import BacktestMetrics


def test_metrics_calculate_correctly() -> None:
    metrics = calculate_metrics(
        starting_cash=10_000,
        ending_equity=10_500,
        equity_curve=[10_000, 11_000, 10_000, 10_500],
        trades=[
            TradeRecord("buy", 1, 100, 100),
            TradeRecord("sell", 1, 110, 110, 10),
        ],
        exposure_points=[False, True, True, False],
        start_price=100,
        end_price=120,
    )

    assert metrics.total_return_pct == 5.0
    assert round(metrics.max_drawdown_pct, 2) == 9.09
    assert metrics.win_rate == 1.0
    assert metrics.trade_count == 2
    assert metrics.best_trade_pct == 10.0
    assert metrics.worst_trade_pct == 10.0
    assert metrics.average_trade_pct == 10.0
    assert metrics.exposure_time_pct == 50.0
    assert metrics.buy_and_hold_return_pct == 20.0


def test_metrics_calculator_accepts_benchmark_abstraction() -> None:
    metrics = MetricsCalculator().calculate(
        MetricsInput(
            starting_cash=10_000,
            ending_equity=10_250,
            equity_curve=[10_000, 10_250],
            trades=[],
            exposure_points=[False, False],
            start_price=100,
            end_price=101,
            benchmark_return_pct=1.0,
        )
    )

    assert metrics.total_return_pct == 2.5
    assert metrics.buy_and_hold_return_pct == 1.0
