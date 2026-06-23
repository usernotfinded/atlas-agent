from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from atlas_agent.agent.autonomous_paper_models import (
    StatefulPaperConfig,
    StatefulPaperCursor,
    StatefulPaperMetrics,
    StatefulPaperResult,
    StatefulPaperState,
)
from atlas_agent.backtest.models import BacktestFill, BacktestPosition


class TestStatefulPaperModels:
    def test_state_serializes_round_trip(self) -> None:
        fill = BacktestFill(
            fill_id="fill-001",
            order_id="order-001",
            timestamp=datetime(2026, 6, 23, 12, 0, 0),
            symbol="DEMO-SYMBOL",
            side="buy",
            quantity=10.0,
            price=100.0,
            notional=1000.0,
        )
        state = StatefulPaperState(
            run_id="run-001",
            symbol="DEMO-SYMBOL",
            strategy_id="buy_and_hold",
            data_path="data/sample/ohlcv.csv",
            cash=9000.0,
            positions={
                "DEMO-SYMBOL": BacktestPosition(
                    symbol="DEMO-SYMBOL",
                    quantity=10.0,
                    average_entry_price=100.0,
                    notional=1000.0,
                ),
            },
            cursor=StatefulPaperCursor(
                last_processed_bar_index=5,
                last_processed_bar_timestamp="2026-06-23T12:00:00",
                processed_bar_hashes=["abc123", "def456"],
            ),
            fill_history=[fill],
            decision_refs=[{"cycle": 1, "action": "buy"}],
            metrics_history=[{"equity": 10000.0}],
            created_at="2026-06-23T10:00:00",
            updated_at="2026-06-23T12:00:00",
            status="active",
            errors=[],
        )

        serialized = state.model_dump(mode="json")
        restored = StatefulPaperState.model_validate(serialized)

        assert restored.run_id == state.run_id
        assert restored.symbol == state.symbol
        assert restored.strategy_id == state.strategy_id
        assert restored.data_path == state.data_path
        assert restored.cash == pytest.approx(state.cash)
        assert restored.positions["DEMO-SYMBOL"].quantity == pytest.approx(10.0)
        assert restored.cursor.last_processed_bar_index == 5
        assert restored.cursor.processed_bar_hashes == ["abc123", "def456"]
        assert len(restored.fill_history) == 1
        assert restored.fill_history[0].fill_id == "fill-001"
        assert restored.decision_refs == [{"cycle": 1, "action": "buy"}]
        assert restored.status == "active"

    def test_metrics_model_defaults(self) -> None:
        metrics = StatefulPaperMetrics(
            starting_cash=10_000.0,
            ending_cash=9500.0,
            ending_equity=10_500.0,
            total_return_pct=5.0,
            max_drawdown_pct=-2.5,
            number_of_trades=3,
            number_of_fills=3,
            number_of_rejections=0,
            gross_exposure=3000.0,
            net_exposure=1000.0,
            total_commission=0.0,
            total_slippage=0.0,
            bars_processed=10,
            data_source_redacted="local-ohlcv",
            generated_at="2026-06-23T12:00:00",
        )

        assert metrics.starting_cash == pytest.approx(10_000.0)
        assert metrics.ending_cash == pytest.approx(9500.0)
        assert metrics.ending_equity == pytest.approx(10_500.0)
        assert metrics.total_return_pct == pytest.approx(5.0)
        assert metrics.max_drawdown_pct == pytest.approx(-2.5)
        assert metrics.number_of_trades == 3
        assert metrics.number_of_fills == 3
        assert metrics.number_of_rejections == 0
        assert metrics.realized_pnl is None
        assert metrics.unrealized_pnl is None
        assert metrics.turnover is None
        assert metrics.notes == []

    def test_config_defaults(self) -> None:
        config = StatefulPaperConfig(
            run_id="run-002",
            symbol="DEMO-SYMBOL",
            strategy_id="moving_average_cross",
            data_path="data/sample/ohlcv.csv",
            output_dir="output",
            state_dir="state",
        )
        assert config.initial_cash == pytest.approx(10_000.0)
        assert config.commission_bps == pytest.approx(0.0)
        assert config.slippage_bps == pytest.approx(0.0)
        assert config.max_orders_per_cycle == 10
        assert config.fill_timing == "next_bar"

    def test_result_status_literals(self) -> None:
        result = StatefulPaperResult(
            run_id="run-003",
            status="no_new_data",
            bars_processed_this_run=0,
            total_bars_processed=5,
            decisions_path="output/decisions.jsonl",
            fills_path="output/fills.jsonl",
            metrics_path="output/metrics.json",
            checkpoint_path="state/checkpoint.json",
            manifest_path="output/manifest.json",
            audit_log_path="output/audit.jsonl",
        )
        assert result.status == "no_new_data"
        assert result.metrics is None
        assert result.errors == []

    def test_config_rejects_invalid_literals(self) -> None:
        with pytest.raises(ValidationError):
            StatefulPaperConfig(
                run_id="run-004",
                symbol="DEMO-SYMBOL",
                strategy_id="buy_and_hold",
                data_path="data/sample/ohlcv.csv",
                output_dir="output",
                state_dir="state",
                fill_timing="invalid_timing",
            )

        with pytest.raises(ValidationError):
            StatefulPaperResult(
                run_id="run-005",
                status="invalid_status",
                bars_processed_this_run=0,
                total_bars_processed=0,
                decisions_path="output/decisions.jsonl",
                fills_path="output/fills.jsonl",
                metrics_path="output/metrics.json",
                checkpoint_path="state/checkpoint.json",
                manifest_path="output/manifest.json",
                audit_log_path="output/audit.jsonl",
            )

    @pytest.mark.parametrize("initial_cash", [0.0, -1.0])
    def test_config_rejects_non_positive_initial_cash(self, initial_cash: float) -> None:
        with pytest.raises(ValidationError):
            StatefulPaperConfig(
                run_id="run-006",
                symbol="DEMO-SYMBOL",
                strategy_id="buy_and_hold",
                data_path="data/sample/ohlcv.csv",
                output_dir="output",
                state_dir="state",
                initial_cash=initial_cash,
            )
