import pytest
import csv
from pathlib import Path
from datetime import datetime, timedelta
from atlas_agent.backtest import BacktestConfig, BacktestEngine
from atlas_agent.backtest.models import BacktestOrder, BacktestPosition
from atlas_agent.backtest.data import load_market_data

@pytest.fixture
def sample_csv(tmp_path):
    csv_path = tmp_path / "test_data.csv"
    with open(csv_path, mode="w", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "symbol", "open", "high", "low", "close", "volume"])
        base_date = datetime(2026, 1, 1)
        for i in range(10):
            writer.writerow([
                (base_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "AAPL",
                100 + i,
                105 + i,
                95 + i,
                101 + i,
                1000
            ])
    return csv_path

def test_engine_buy_and_hold(sample_csv):
    config = BacktestConfig(
        run_id="test-buy-hold",
        symbol="AAPL",
        data_path=str(sample_csv),
        initial_equity=10000.0,
        strategy_mode="buy_and_hold",
        risk_enabled=False
    )
    engine = BacktestEngine(config)
    result = engine.run()
    
    assert result.status == "completed"
    assert len(result.fills) == 1
    assert result.fills[0].side == "buy"
    assert result.fills[0].order_id == "test-buy-hold-000000-buy-and-hold"
    assert result.fills[0].fill_id == "fill-test-buy-hold-000000-buy-and-hold"
    assert result.strategy_metadata["strategy_id"] == "buy_and_hold"
    assert result.benchmark["benchmark_id"] == "buy_and_hold"
    assert result.metrics.final_equity > 10000.0
    assert len(result.equity_curve) == 10

def test_engine_risk_blocking(sample_csv):
    # Set a very low max position size to trigger risk blocking
    config = BacktestConfig(
        symbol="AAPL",
        data_path=str(sample_csv),
        initial_equity=10000.0,
        strategy_mode="buy_and_hold",
        risk_enabled=True
    )
    
    engine = BacktestEngine(config)
    # Manually override limits for the test
    from atlas_agent.risk.limits import RiskLimits
    engine.risk_manager.limits = RiskLimits(
        max_position_notional=100.0, # Very low
        live_trading_enabled=False,
        paper_only=True
    )
    
    result = engine.run()
    
    assert len(result.fills) == 0
    assert len(result.diagnostics["blocked_orders"]) > 0
    assert result.metrics.final_equity == 10000.0

def test_engine_slippage_affects_equity(sample_csv):
    config_no_slip = BacktestConfig(
        symbol="AAPL",
        data_path=str(sample_csv),
        initial_equity=10000.0,
        strategy_mode="buy_and_hold",
        slippage_bps=0.0,
        risk_enabled=False
    )
    result_no_slip = BacktestEngine(config_no_slip).run()
    
    config_slip = BacktestConfig(
        symbol="AAPL",
        data_path=str(sample_csv),
        initial_equity=10000.0,
        strategy_mode="buy_and_hold",
        slippage_bps=100.0, # 1% slippage
        risk_enabled=False
    )
    result_slip = BacktestEngine(config_slip).run()
    
    assert result_slip.metrics.final_equity < result_no_slip.metrics.final_equity


def test_portfolio_snapshot_with_existing_position_does_not_crash(sample_csv):
    config = BacktestConfig(
        symbol="AAPL",
        data_path=str(sample_csv),
        initial_equity=10000.0,
        strategy_mode="buy_and_hold",
        risk_enabled=True,
    )
    engine = BacktestEngine(config)
    engine.positions["AAPL"] = BacktestPosition(
        symbol="AAPL",
        quantity=5.0,
        average_entry_price=100.0,
        notional=500.0,
    )

    snapshot = engine._get_portfolio_snapshot(current_price=105.0)

    assert len(snapshot.positions) == 1
    pos = snapshot.positions[0]
    assert pos.symbol == "AAPL"
    assert pos.quantity == 5.0
    assert pos.market_price == 105.0
    assert pos.side == "long"
    assert pos.notional == 525.0


def test_existing_position_can_be_evaluated_on_later_tick_without_crash(sample_csv):
    config = BacktestConfig(
        symbol="AAPL",
        data_path=str(sample_csv),
        initial_equity=10000.0,
        strategy_mode="buy_and_hold",
        risk_enabled=True,
    )
    engine = BacktestEngine(config)
    from atlas_agent.risk.limits import RiskLimits

    engine.risk_manager.limits = RiskLimits(
        max_position_notional=20000.0,
        max_single_trade_notional=20000.0,
        max_symbol_exposure_pct=2.0,
        max_portfolio_exposure_pct=2.0,
        live_trading_enabled=False,
        paper_only=True,
    )
    bars = load_market_data(str(sample_csv), "AAPL")

    # First step opens and fills an initial position.
    engine._step(bars[0])
    assert "AAPL" in engine.positions

    # Add a second order so risk evaluation snapshots include an existing position.
    engine.pending_orders.append(
        BacktestOrder(
            order_id="second-order",
            timestamp=bars[1].timestamp,
            symbol="AAPL",
            side="sell",
            quantity=engine.positions["AAPL"].quantity / 2,
            price=bars[1].open,
        )
    )

    # Must not raise when evaluating the later tick with an existing position.
    engine._step(bars[1])
    engine._step(bars[2])

    assert len(engine.equity_curve) == 3


def test_buy_and_hold_sample_data_is_deterministic(sample_csv):
    config = BacktestConfig(
        symbol="AAPL",
        data_path=str(sample_csv),
        initial_equity=10000.0,
        strategy_mode="buy_and_hold",
        risk_enabled=False,
    )
    result = BacktestEngine(config).run()

    assert result.status == "completed"
    assert result.metrics.final_equity == pytest.approx(10900.0)
