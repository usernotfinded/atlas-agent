from __future__ import annotations

import json

from atlas_agent.backtest.metrics import TradeRecord, calculate_metrics
from atlas_agent.backtest.runner import run_backtest
from atlas_agent.config import AtlasConfig


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

    assert metrics.total_return == 0.05
    assert round(metrics.max_drawdown, 4) == 0.0909
    assert metrics.win_rate == 1.0
    assert metrics.number_of_trades == 2
    assert metrics.best_trade == 0.1
    assert metrics.worst_trade == 0.1
    assert metrics.exposure_time == 0.5
    assert metrics.buy_and_hold_return == 0.2


def test_backtest_report_files_are_written(tmp_path) -> None:
    config = AtlasConfig(reports_dir=tmp_path)

    result = run_backtest(symbol="BTC-USD", config=config)

    assert result.report_paths is not None
    json_path, markdown_path, csv_path = result.report_paths
    assert json_path.exists()
    assert markdown_path.exists()
    assert csv_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "backtest"
    assert "total_return" in payload["metrics"]

