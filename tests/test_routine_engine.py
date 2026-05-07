from __future__ import annotations

from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order import OrderResult
from atlas_agent.research.web_research import OfflineResearchProvider
from atlas_agent.routines.engine import run_routine


def _config(tmp_path, **kwargs) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        reports_dir=tmp_path / "reports",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending",
        **kwargs,
    )


def test_routine_engine_can_run_pre_market_in_paper_mode(tmp_path) -> None:
    result = run_routine(
        "pre_market",
        mode="paper",
        config=_config(tmp_path),
        research_provider=OfflineResearchProvider(),
    )

    assert result.status == "complete"
    assert result.report_path.exists()
    assert (tmp_path / "memory" / "daily_notes.md").exists()


def test_routine_engine_can_run_market_open_in_paper_mode(tmp_path) -> None:
    def order_runner(*, mode, config):
        return OrderResult(True, True, "order-1", "filled", f"{mode} filled")

    result = run_routine(
        "market_open",
        mode="paper",
        config=_config(tmp_path),
        order_runner=order_runner,
        research_provider=OfflineResearchProvider(),
    )

    assert result.order_status == "filled"
    assert (tmp_path / "memory" / "trade_journal.md").exists()


def test_routine_engine_live_mode_creates_pending_without_execution(tmp_path) -> None:
    def order_runner(*, mode, config):
        pending = config.pending_orders_dir / "order-1.json"
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text('{"approved": false}', encoding="utf-8")
        return OrderResult(False, False, "order-1", "pending_approval", "pending")

    result = run_routine(
        "market_open",
        mode="live",
        config=_config(
            tmp_path,
            trading_mode="live",
            enable_live_trading=True,
            live_broker="alpaca",
        ),
        order_runner=order_runner,
        research_provider=OfflineResearchProvider(),
    )

    assert result.order_status == "pending_approval"
    assert (tmp_path / "pending" / "order-1.json").exists()

