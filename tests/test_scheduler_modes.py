from __future__ import annotations

from atlas_agent.ai.discipline import write_user_discipline
from atlas_agent.cli import run_once
from atlas_agent.config import AtlasConfig, MarketConfig
from atlas_agent.scheduler.runner import run_scheduler_once

GOOD_PROFILE = (
    "# Profile\n\n"
    "## Decision temperament\n\nCautious.\n\n"
    "## Reasoning style\n\nStep-by-step.\n\n"
    "## Communication style\n\nConcise.\n\n"
    "## Risk posture\n\nConservative.\n\n"
    "## Uncertainty handling\n\nExplicit.\n\n"
    "## No-trade bias\n\nDefault to hold.\n\n"
    "## Forbidden overrides\n\n"
    "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
    "audit logging, broker sync checks, reference price requirements, or live-trading safeguards.\n"
)


def test_paper_scheduler_can_run_autonomously(tmp_path) -> None:
    write_user_discipline(tmp_path, GOOD_PROFILE)
    config = AtlasConfig(
        reports_dir=tmp_path / "reports",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending",
        memory_dir=tmp_path / "memory",
        market=MarketConfig(symbol="DEMO-SYMBOL"),
    )

    result = run_scheduler_once(
        routine="market_open",
        mode="paper",
        config=config,
        run_once_func=run_once,
    )

    assert result.order_result.status == "filled"


def test_live_scheduler_fails_closed_at_broker_resolver_gate(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    write_user_discipline(tmp_path, GOOD_PROFILE)
    config = AtlasConfig(
        trading_mode="live",
        enable_live_trading=True,
        live_broker="alpaca",
        reports_dir=tmp_path / "reports",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending",
        memory_dir=tmp_path / "memory",
        market=MarketConfig(symbol="DEMO-SYMBOL"),
    )

    result = run_scheduler_once(
        routine="market_open",
        mode="live",
        config=config,
        run_once_func=run_once,
    )

    assert result.order_result.status == "rejected"
    assert "credentials are missing" in result.order_result.message or "deferred" in result.order_result.message


def test_kill_switch_blocks_scheduler_execution(tmp_path) -> None:
    write_user_discipline(tmp_path, GOOD_PROFILE)
    config = AtlasConfig(
        kill_switch_enabled=True,
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending",
        memory_dir=tmp_path / "memory",
        market=MarketConfig(symbol="DEMO-SYMBOL"),
    )

    result = run_scheduler_once(
        routine="market_open",
        mode="paper",
        config=config,
        run_once_func=run_once,
    )

    assert result.order_result.status == "rejected"
    assert "kill switch is enabled" in result.order_result.reasons

