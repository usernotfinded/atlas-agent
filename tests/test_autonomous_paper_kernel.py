from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.autonomous_paper_kernel import (
    KernelCycleResult,
    apply_fill,
    build_portfolio_snapshot,
    observations_for_bar,
    run_kernel_cycle,
)
from atlas_agent.audit import AuditWriter
from atlas_agent.backtest.data import load_market_data
from atlas_agent.backtest.execution import ExecutionSimulator
from atlas_agent.backtest.models import BacktestConfig, BacktestOrder, BacktestPosition, MarketBar
from atlas_agent.backtest.registry import get_strategy
from atlas_agent.risk.limits import RiskLimits
from atlas_agent.risk.manager import RiskManager


SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample" / "ohlcv.csv"


def _make_bar(**overrides: Any) -> MarketBar:
    defaults = {
        "timestamp": datetime(2026, 4, 20, 9, 30, 0),
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": 1200.0,
        "symbol": "DEMO-SYMBOL",
    }
    defaults.update(overrides)
    return MarketBar(**defaults)


def _permissive_risk_manager() -> RiskManager:
    return RiskManager(
        limits=RiskLimits(
            max_position_notional=1_000_000.0,
            max_single_trade_notional=1_000_000.0,
            max_symbol_exposure_pct=1.0,
            max_portfolio_exposure_pct=10.0,
            minimum_confidence=0.0,
            allowed_symbols=None,
            blocked_symbols=set(),
            allow_shorting=False,
        ),
    )


def _blocking_risk_manager(*, kill_switch: bool = False) -> RiskManager:
    limits = RiskLimits(
        max_position_notional=1_000_000.0,
        max_single_trade_notional=1_000_000.0,
        minimum_confidence=0.0,
        allowed_symbols={"OTHER"},
    )
    return RiskManager(limits=limits, kill_switch_enabled=kill_switch)


class _MockStrategy:
    def __init__(self, orders: list[BacktestOrder] | None = None):
        self._orders = list(orders) if orders else []

    def generate_orders(self, *, bars: list[MarketBar], context: Any) -> list[BacktestOrder]:
        return list(self._orders)


class TestKernelHelpers:
    def test_build_portfolio_snapshot_computes_exposure(self):
        positions = {
            "DEMO-SYMBOL": BacktestPosition(
                symbol="DEMO-SYMBOL",
                quantity=10.0,
                average_entry_price=100.0,
                notional=1000.0,
            ),
        }
        snapshot = build_portfolio_snapshot(
            cash=9000.0,
            positions=positions,
            pending_orders=[],
            current_price=110.0,
        )
        assert snapshot.cash == pytest.approx(9000.0)
        assert snapshot.equity == pytest.approx(10100.0)
        assert snapshot.total_exposure == pytest.approx(1100.0)
        assert len(snapshot.positions) == 1
        assert snapshot.positions[0].side == "long"

    def test_apply_fill_buy_updates_position(self):
        from atlas_agent.backtest.models import BacktestFill

        fill = BacktestFill(
            fill_id="fill-001",
            order_id="order-001",
            timestamp=datetime(2026, 4, 20, 9, 30, 0),
            symbol="DEMO-SYMBOL",
            side="buy",
            quantity=10.0,
            price=100.0,
            notional=1000.0,
            commission=1.0,
        )
        cash, positions = apply_fill(fill=fill, cash=10000.0, positions={})
        assert cash == pytest.approx(8999.0)
        assert positions["DEMO-SYMBOL"].quantity == pytest.approx(10.0)
        assert positions["DEMO-SYMBOL"].average_entry_price == pytest.approx(100.0)

    def test_apply_fill_sell_removes_position(self):
        from atlas_agent.backtest.models import BacktestFill

        positions = {
            "DEMO-SYMBOL": BacktestPosition(
                symbol="DEMO-SYMBOL",
                quantity=10.0,
                average_entry_price=100.0,
                notional=1000.0,
            ),
        }
        fill = BacktestFill(
            fill_id="fill-002",
            order_id="order-002",
            timestamp=datetime(2026, 4, 20, 9, 30, 0),
            symbol="DEMO-SYMBOL",
            side="sell",
            quantity=10.0,
            price=110.0,
            notional=1100.0,
            commission=1.0,
        )
        cash, positions = apply_fill(fill=fill, cash=9000.0, positions=positions)
        assert cash == pytest.approx(10099.0)
        assert "DEMO-SYMBOL" not in positions

    def test_observations_for_bar_includes_signals(self):
        bar = _make_bar()
        orders = [
            BacktestOrder(
                order_id="order-001",
                timestamp=bar.timestamp,
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=10.0,
                price=100.0,
            ),
        ]
        obs = observations_for_bar(bar, orders)
        assert obs["signal_count"] == 1
        assert obs["signals"][0]["side"] == "buy"
        assert obs["bar"]["close"] == pytest.approx(101.0)

    def test_apply_fill_sell_exceeds_position_raises_when_shorting_disabled(self):
        from atlas_agent.backtest.models import BacktestFill

        positions = {
            "DEMO-SYMBOL": BacktestPosition(
                symbol="DEMO-SYMBOL",
                quantity=10.0,
                average_entry_price=100.0,
                notional=1000.0,
            ),
        }
        fill = BacktestFill(
            fill_id="fill-003",
            order_id="order-003",
            timestamp=datetime(2026, 4, 20, 9, 30, 0),
            symbol="DEMO-SYMBOL",
            side="sell",
            quantity=20.0,
            price=110.0,
            notional=2200.0,
            commission=1.0,
        )
        with pytest.raises(ValueError, match="sell fill quantity exceeds position"):
            apply_fill(fill=fill, cash=9000.0, positions=positions)


class TestKernelCycle:
    def test_kernel_no_trade_when_strategy_returns_no_orders(self, tmp_path: Path):
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-001")
        bar = _make_bar()
        config = BacktestConfig(run_id="run-001", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)
        risk_manager = _permissive_risk_manager()

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=[bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_MockStrategy(orders=[]),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-001",
            config=config,
            audit_writer=audit_writer,
        )

        assert isinstance(result, KernelCycleResult)
        assert result.decision_state == "no_trade"
        assert result.proposed_action == "hold"
        assert result.proposed_order is None
        assert result.fills == []
        assert result.rejected_orders == []
        assert result.cash == pytest.approx(10000.0)
        assert result.positions == {}
        assert len(result.audit_event_ids) == 1
        assert result.blocked_reason is None

    def test_kernel_processes_all_orders_sequentially(self, tmp_path: Path):
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-002")
        bar = _make_bar(close=100.0)
        orders = [
            BacktestOrder(
                order_id=f"order-{i:03d}",
                timestamp=bar.timestamp,
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=1.0,
                price=100.0,
            )
            for i in range(3)
        ]
        config = BacktestConfig(run_id="run-002", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)
        risk_manager = _permissive_risk_manager()

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=[bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_MockStrategy(orders=orders),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-002",
            config=config,
            audit_writer=audit_writer,
        )

        assert result.decision_state == "paper_executed"
        assert len(result.fills) == 3
        assert len(result.rejected_orders) == 0
        assert result.cash < 10000.0
        assert result.positions["DEMO-SYMBOL"].quantity == pytest.approx(3.0)
        assert len(result.audit_event_ids) == 4  # decision + 3 fills

    def test_kernel_risk_blocked_order_does_not_change_portfolio(self, tmp_path: Path):
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-003")
        bar = _make_bar()
        order = BacktestOrder(
            order_id="order-001",
            timestamp=bar.timestamp,
            symbol="DEMO-SYMBOL",
            side="buy",
            quantity=10.0,
            price=100.0,
        )
        config = BacktestConfig(run_id="run-003", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)
        risk_manager = _blocking_risk_manager()

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=[bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_MockStrategy(orders=[order]),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-003",
            config=config,
            audit_writer=audit_writer,
        )

        assert result.decision_state == "risk_blocked"
        assert result.fills == []
        assert len(result.rejected_orders) == 1
        assert result.cash == pytest.approx(10000.0)
        assert result.positions == {}
        assert result.blocked_reason is not None
        assert "allowed_symbols" in str(result.risk_result)

    def test_kernel_fill_updates_cash_and_position(self, tmp_path: Path):
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-004")
        bars = load_market_data(str(SAMPLE_CSV), symbol="DEMO-SYMBOL")
        bar = bars[0]
        strategy = get_strategy("buy_and_hold", parameters={"position_pct": 1.0})
        config = BacktestConfig(run_id="run-004", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)
        risk_manager = _permissive_risk_manager()

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=bars[:1],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=strategy,
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-004",
            config=config,
            audit_writer=audit_writer,
        )

        assert result.decision_state == "paper_executed"
        assert result.proposed_action == "buy"
        assert len(result.fills) == 1
        assert result.cash < 10000.0
        assert "DEMO-SYMBOL" in result.positions
        assert result.positions["DEMO-SYMBOL"].quantity > 0

    def test_kernel_respects_max_orders_per_cycle(self, tmp_path: Path):
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-005")
        bar = _make_bar(close=100.0)
        orders = [
            BacktestOrder(
                order_id=f"order-{i:03d}",
                timestamp=bar.timestamp,
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=1.0,
                price=100.0,
            )
            for i in range(5)
        ]
        config = BacktestConfig(run_id="run-005", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)
        risk_manager = _permissive_risk_manager()

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=[bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_MockStrategy(orders=orders),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-005",
            config=config,
            audit_writer=audit_writer,
            max_orders_per_cycle=3,
        )

        assert result.risk_result["orders_generated"] == 5
        assert result.risk_result["orders_evaluated"] == 3
        assert len(result.fills) == 3
        assert any("truncated" in str(w) for w in result.risk_result["warnings"])

    def test_kernel_does_not_import_brokers_or_providers(self):
        module_path = Path(__file__).resolve().parents[1] / "src" / "atlas_agent" / "agent" / "autonomous_paper_kernel.py"
        source = module_path.read_text(encoding="utf-8")
        forbidden = [
            "atlas_agent.brokers",
            "atlas_agent.providers",
            "atlas_agent.execution.live",
        ]
        for ref in forbidden:
            assert ref not in source, f"Forbidden import/reference found: {ref}"

    def test_kernel_risk_blocked_does_not_affect_later_orders(self, tmp_path: Path):
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-blocked-then-allowed")
        bar = _make_bar(close=100.0)
        orders = [
            BacktestOrder(
                order_id="order-001",
                timestamp=bar.timestamp,
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=100.0,
                price=100.0,
            ),
            BacktestOrder(
                order_id="order-002",
                timestamp=bar.timestamp,
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=1.0,
                price=100.0,
            ),
        ]
        risk_manager = RiskManager(
            limits=RiskLimits(
                max_position_notional=1_000_000.0,
                max_single_trade_notional=500.0,
                minimum_confidence=0.0,
                allowed_symbols=None,
                blocked_symbols=set(),
                allow_shorting=False,
            ),
        )
        config = BacktestConfig(run_id="run-blocked-then-allowed", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=[bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_MockStrategy(orders=orders),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-blocked-then-allowed",
            config=config,
            audit_writer=audit_writer,
        )

        assert result.decision_state == "partially_executed"
        assert len(result.rejected_orders) == 1
        assert len(result.fills) == 1
        # The second order must have been evaluated against the original cash and
        # positions, not a portfolio mutated by the blocked first order.
        assert result.fills[0].quantity == pytest.approx(1.0)
        assert result.cash == pytest.approx(9900.0)
        assert result.positions["DEMO-SYMBOL"].quantity == pytest.approx(1.0)

    def test_kernel_mixed_fill_and_rejection_is_partially_executed(self, tmp_path: Path):
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-partial")
        bar = _make_bar(close=100.0)
        orders = [
            BacktestOrder(
                order_id="order-001",
                timestamp=bar.timestamp,
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=1.0,
                price=100.0,
            ),
            BacktestOrder(
                order_id="order-002",
                timestamp=bar.timestamp,
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=100.0,
                price=100.0,
            ),
        ]
        risk_manager = RiskManager(
            limits=RiskLimits(
                max_position_notional=1_000_000.0,
                max_single_trade_notional=500.0,
                minimum_confidence=0.0,
                allowed_symbols=None,
                blocked_symbols=set(),
                allow_shorting=False,
            ),
        )
        config = BacktestConfig(run_id="run-partial", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=[bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_MockStrategy(orders=orders),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-partial",
            config=config,
            audit_writer=audit_writer,
        )

        assert result.decision_state == "partially_executed"
        assert len(result.fills) == 1
        assert len(result.rejected_orders) == 1
        assert result.cash < 10000.0

    def test_kernel_handles_strategy_exception(self, tmp_path: Path):
        class _ExplodingStrategy:
            def generate_orders(self, *, bars, context):
                raise RuntimeError("strategy boom")

        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-strategy-err")
        bar = _make_bar()
        config = BacktestConfig(run_id="run-strategy-err", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)
        risk_manager = _permissive_risk_manager()

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=[bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_ExplodingStrategy(),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-strategy-err",
            config=config,
            audit_writer=audit_writer,
        )

        assert result.decision_state == "failed"
        assert result.proposed_action == "hold"
        assert result.blocked_reason == "cycle_error: RuntimeError"
        assert result.cash == pytest.approx(10000.0)
        assert result.positions == {}

        events = [
            json.loads(line)
            for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        failed_events = [e for e in events if e["event_type"] == "autonomous_paper_cycle_failed"]
        assert len(failed_events) == 1
        assert failed_events[0]["payload"]["error_type"] == "RuntimeError"

    def test_kernel_handles_audit_exception(self, tmp_path: Path):
        class _FailingDecisionAuditWriter(AuditWriter):
            def write_event(self, event_type, **kwargs):
                if event_type == "autonomous_paper_decision":
                    raise RuntimeError("audit decision boom")
                return super().write_event(event_type, **kwargs)

        audit_writer = _FailingDecisionAuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-audit-err")
        bar = _make_bar(close=100.0)
        order = BacktestOrder(
            order_id="order-001",
            timestamp=bar.timestamp,
            symbol="DEMO-SYMBOL",
            side="buy",
            quantity=1.0,
            price=100.0,
        )
        config = BacktestConfig(run_id="run-audit-err", symbol="DEMO-SYMBOL", data_path=str(SAMPLE_CSV))
        executor = ExecutionSimulator(config)
        risk_manager = _permissive_risk_manager()

        result = run_kernel_cycle(
            bar=bar,
            bar_index=0,
            bars_so_far=[bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_MockStrategy(orders=[order]),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-audit-err",
            config=config,
            audit_writer=audit_writer,
        )

        assert result.decision_state == "failed"
        assert result.proposed_action == "hold"
        assert result.blocked_reason == "cycle_error: RuntimeError"
        # The fill was applied before the audit write failed; cash reflects it.
        assert result.cash < 10000.0

        events = [
            json.loads(line)
            for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        failed_events = [e for e in events if e["event_type"] == "autonomous_paper_cycle_failed"]
        assert len(failed_events) == 1
        assert failed_events[0]["payload"]["error_type"] == "RuntimeError"
        assert any(e["event_type"] == "autonomous_paper_fill" for e in events)

    def test_kernel_uses_fill_bar_for_execution(self, tmp_path: Path):
        audit_writer = AuditWriter(tmp_path / "audit.jsonl")
        audit_writer.start_run("run-fill-bar")
        signal_bar = _make_bar(close=100.0)
        fill_bar = _make_bar(close=105.0)
        order = BacktestOrder(
            order_id="order-001",
            timestamp=signal_bar.timestamp,
            symbol="DEMO-SYMBOL",
            side="buy",
            quantity=1.0,
            price=100.0,
        )
        config = BacktestConfig(
            run_id="run-fill-bar",
            symbol="DEMO-SYMBOL",
            data_path=str(SAMPLE_CSV),
            slippage_bps=0.0,
            commission_bps=0.0,
        )
        executor = ExecutionSimulator(config)
        risk_manager = _permissive_risk_manager()

        result = run_kernel_cycle(
            bar=signal_bar,
            fill_bar=fill_bar,
            bar_index=0,
            bars_so_far=[signal_bar],
            cash=10000.0,
            positions={},
            pending_orders=[],
            strategy=_MockStrategy(orders=[order]),
            executor=executor,
            risk_manager=risk_manager,
            symbol="DEMO-SYMBOL",
            run_id="run-fill-bar",
            config=config,
            audit_writer=audit_writer,
        )

        assert result.decision_state == "paper_executed"
        assert len(result.fills) == 1
        assert result.fills[0].price == pytest.approx(105.0)
        assert result.fills[0].timestamp == fill_bar.timestamp
