# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_autonomous_paper_metrics.py
# PURPOSE: Verifies autonomous paper metrics behavior and regression
#         expectations.
# DEPS:    datetime, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from atlas_agent.agent.autonomous_paper_metrics import (
    build_trade_records_from_fills,
    calculate_stateful_paper_metrics,
)
from atlas_agent.backtest.models import BacktestFill, BacktestPosition


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _dt() -> datetime:
    return datetime.now(UTC)


def _buy_fill(quantity: float, price: float) -> BacktestFill:
    return BacktestFill(
        fill_id="f-buy",
        order_id="o-buy",
        timestamp=_dt(),
        symbol="DEMO",
        side="buy",
        quantity=quantity,
        price=price,
        notional=quantity * price,
        commission=0.0,
        slippage=0.0,
    )


def _sell_fill(quantity: float, price: float) -> BacktestFill:
    return BacktestFill(
        fill_id="f-sell",
        order_id="o-sell",
        timestamp=_dt(),
        symbol="DEMO",
        side="sell",
        quantity=quantity,
        price=price,
        notional=quantity * price,
        commission=0.0,
        slippage=0.0,
    )


def test_build_trade_records_computes_sell_realized_pnl():
    fills = [_buy_fill(10.0, 100.0), _sell_fill(10.0, 110.0)]
    records = build_trade_records_from_fills(fills)
    assert len(records) == 2
    assert records[0].side == "buy"
    assert records[0].realized_pnl == 0.0
    assert records[1].side == "sell"
    assert records[1].realized_pnl == pytest.approx(100.0)


def test_metrics_include_return_and_drawdown():
    fills = [_buy_fill(10.0, 100.0), _sell_fill(10.0, 110.0)]
    metrics = calculate_stateful_paper_metrics(
        starting_cash=10_000.0,
        cash=10_100.0,
        positions={},
        fill_history=fills,
        bars_processed=2,
        current_price=110.0,
        data_source="data/sample/ohlcv.csv",
    )
    assert metrics.total_return_pct is not None
    assert metrics.total_return_pct == pytest.approx(1.0)
    assert metrics.max_drawdown_pct is not None
    assert metrics.max_drawdown_pct >= 0.0


def test_metrics_track_rejections():
    metrics = calculate_stateful_paper_metrics(
        starting_cash=10_000.0,
        cash=10_000.0,
        positions={},
        fill_history=[],
        bars_processed=0,
        current_price=100.0,
        data_source="ohlcv.csv",
        number_of_rejections=5,
    )
    assert metrics.number_of_rejections == 5


def test_metrics_honestly_omit_uncomputable():
    fills = [_buy_fill(10.0, 100.0)]
    position = BacktestPosition(
        symbol="DEMO",
        quantity=10.0,
        average_entry_price=100.0,
        notional=1_000.0,
    )
    metrics = calculate_stateful_paper_metrics(
        starting_cash=10_000.0,
        cash=9_000.0,
        positions={"DEMO": position},
        fill_history=fills,
        bars_processed=1,
        current_price=110.0,
        data_source="ohlcv.csv",
    )
    assert metrics.realized_pnl is None
    assert metrics.unrealized_pnl == pytest.approx(100.0)
    assert any("approximated" in note for note in metrics.notes)
    assert any("realized_pnl is omitted" in note for note in metrics.notes)


def test_metrics_turnover_computed():
    fills = [_buy_fill(10.0, 100.0), _sell_fill(10.0, 110.0)]
    metrics = calculate_stateful_paper_metrics(
        starting_cash=10_000.0,
        cash=10_100.0,
        positions={},
        fill_history=fills,
        bars_processed=2,
        current_price=110.0,
        data_source="ohlcv.csv",
    )
    assert metrics.turnover is not None
    assert metrics.turnover > 0.0
    assert any("turnover is total notional" in note for note in metrics.notes)


def test_metrics_realized_pnl_includes_commission():
    buy = _buy_fill(10.0, 100.0)
    sell = BacktestFill(
        fill_id="f-sell",
        order_id="o-sell",
        timestamp=_dt(),
        symbol="DEMO",
        side="sell",
        quantity=10.0,
        price=110.0,
        notional=1_100.0,
        commission=10.0,
        slippage=0.0,
    )
    metrics = calculate_stateful_paper_metrics(
        starting_cash=10_000.0,
        cash=10_090.0,
        positions={},
        fill_history=[buy, sell],
        bars_processed=2,
        current_price=110.0,
        data_source="ohlcv.csv",
    )
    assert metrics.realized_pnl is not None
    assert metrics.realized_pnl == pytest.approx(90.0)
    assert metrics.total_commission == pytest.approx(10.0)
