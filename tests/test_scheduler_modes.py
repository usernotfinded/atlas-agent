from __future__ import annotations

from omni_trade_ai.cli import run_once
from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.scheduler.runner import run_scheduler_once


def test_paper_scheduler_can_run_autonomously(tmp_path) -> None:
    config = OmniTradeConfig(
        reports_dir=tmp_path / "reports",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending",
        memory_dir=tmp_path / "memory",
    )

    result = run_scheduler_once(
        routine="market_open",
        mode="paper",
        config=config,
        run_once_func=run_once,
    )

    assert result.order_result.status == "filled"


def test_live_scheduler_creates_pending_order_without_approval(tmp_path) -> None:
    config = OmniTradeConfig(
        trading_mode="live",
        enable_live_trading=True,
        live_broker="alpaca",
        reports_dir=tmp_path / "reports",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending",
        memory_dir=tmp_path / "memory",
    )

    result = run_scheduler_once(
        routine="market_open",
        mode="live",
        config=config,
        run_once_func=run_once,
    )

    assert result.order_result.status == "pending_approval"
    assert list((tmp_path / "pending").glob("*.json"))


def test_kill_switch_blocks_scheduler_execution(tmp_path) -> None:
    config = OmniTradeConfig(
        kill_switch_enabled=True,
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending",
        memory_dir=tmp_path / "memory",
    )

    result = run_scheduler_once(
        routine="market_open",
        mode="paper",
        config=config,
        run_once_func=run_once,
    )

    assert result.order_result.status == "rejected"
    assert "kill switch is enabled" in result.order_result.reasons

