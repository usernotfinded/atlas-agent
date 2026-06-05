from __future__ import annotations

import csv
from datetime import datetime

from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.models import BacktestConfig
from atlas_agent.backtest.validation import validate_strategy


def test_validate_builtin_strategy_with_local_bars(tmp_path) -> None:
    data_path = tmp_path / "bars.csv"
    with open(data_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "symbol", "open", "high", "low", "close", "volume"])
        writer.writerow([datetime(2026, 1, 1).date().isoformat(), "AAPL", 100, 105, 99, 101, 1000])

    config = BacktestConfig(symbol="AAPL", data_path=str(data_path), strategy_mode="buy_and_hold")
    bars = load_market_data(str(data_path), "AAPL")

    result = validate_strategy("buy_and_hold", bars=bars, config=config)

    assert result.status == "valid"
    assert result.metadata is not None
    assert result.metadata.strategy_id == "buy_and_hold"


def test_validate_unknown_strategy_fails_closed() -> None:
    result = validate_strategy("missing_strategy")

    assert result.status == "invalid"
    assert result.issues[0].code == "strategy_not_found"


def test_validate_invalid_strategy_parameters_fails_closed(tmp_path) -> None:
    data_path = tmp_path / "bars.csv"
    with open(data_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "symbol", "open", "high", "low", "close", "volume"])
        writer.writerow([datetime(2026, 1, 1).date().isoformat(), "AAPL", 100, 105, 99, 101, 1000])

    config = BacktestConfig(
        symbol="AAPL",
        data_path=str(data_path),
        strategy_mode="moving_average_cross",
        strategy_parameters={"short_window": "5", "long_window": "3"},
    )
    bars = load_market_data(str(data_path), "AAPL")

    result = validate_strategy("moving_average_cross", bars=bars, config=config)

    assert result.status == "invalid"
    assert result.issues[0].code == "strategy_parameters_invalid"
