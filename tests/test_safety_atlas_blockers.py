from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.agent import runner
from atlas_agent.ai.discipline import write_user_discipline
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.approval import ApprovalManager
from atlas_agent.execution.audit import AuditLogger
from atlas_agent.execution.order import AccountSnapshot, Order, OrderResult
from atlas_agent.execution.order_router import OrderRouter
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.risk.validation import RiskDecision
from atlas_agent.routines.engine import RoutineResult
from atlas_agent.cli import main

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


def _config(tmp_path: Path, **overrides) -> AtlasConfig:
    values = {
        "memory_dir": tmp_path / "memory",
        "audit_dir": tmp_path / "audit",
        "pending_orders_dir": tmp_path / "pending_orders",
        "reports_dir": tmp_path / "reports",
        "data_path": tmp_path / "data" / "ohlcv.csv",
    }
    values.update(overrides)
    return AtlasConfig(**values)


@dataclass
class SpyBroker:
    called: bool = False

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(0, 0, 0, "spy")

    def get_positions(self) -> list:
        return []

    def place_order(self, order: Order) -> OrderResult:
        self.called = True
        return OrderResult(True, True, order.id, "filled", "filled")

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(True, False, order_id, "cancelled", "cancelled")


class BlockingRiskManager:
    def __init__(self) -> None:
        self.calls = 0

    def validate_order(self, *args, **kwargs) -> RiskDecision:
        self.calls += 1
        return RiskDecision(False, ("blocked by mandatory RiskManager",))


def test_live_trading_defaults_remain_disabled_and_gated() -> None:
    config = AtlasConfig()

    assert config.trading_mode == "paper"
    assert config.enable_live_trading is False
    assert config.live_broker == "none"
    assert config.order_approval_mode == "manual_live"
    assert "ENABLE_LIVE_TRADING must be true" in config.live_disabled_reasons()
    assert "LIVE_BROKER must name a supported live broker" in config.live_disabled_reasons()


def test_unknown_market_state_never_runs_live_open_market_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(
        tmp_path,
        trading_mode="live",
        enable_live_trading=True,
        live_broker="alpaca",
    )
    write_user_discipline(tmp_path, GOOD_PROFILE)
    closed_modes: list[str] = []

    def fake_closed_market_cycle(config: AtlasConfig, mode: str) -> RoutineResult:
        closed_modes.append(mode)
        return RoutineResult(
            name="pre_market",
            mode=mode,
            status="complete",
            report_path=tmp_path / "reports" / "agent" / "closed.md",
            memory_files_updated=(),
            order_status=None,
            notification_status="not_configured",
            git_status="commit refused: disabled",
        )

    def fail_open_market_cycle(config: AtlasConfig, mode: str) -> RoutineResult:
        raise AssertionError("unknown market state must not run live open-market cycle")

    monkeypatch.setattr(runner.MarketSessionDetector, "get_state", lambda self: "unknown")
    monkeypatch.setattr(runner, "run_closed_market_cycle", fake_closed_market_cycle)
    monkeypatch.setattr(runner, "run_open_market_cycle", fail_open_market_cycle)

    result = runner._run_cycle("live", config)

    assert result.mode == "paper"
    assert closed_modes == ["paper"]


def test_risk_manager_rejection_blocks_live_broker_and_pending_order(
    tmp_path: Path,
) -> None:
    config = _config(
        tmp_path,
        trading_mode="live",
        enable_live_trading=True,
        live_broker="alpaca",
    )
    risk_manager = BlockingRiskManager()
    broker = SpyBroker()
    order = Order(
        "BTC-USD",
        "buy",
        1,
        limit_price=100,
        confidence=1,
        stop_loss=95,
    )
    router = OrderRouter(
        config=config,
        risk_manager=risk_manager,
        approval_manager=ApprovalManager(config.pending_orders_dir),
        audit=AuditLogger(config.audit_dir),
    )

    result = router.route(
        order,
        mode="live",
        broker=broker,
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )

    assert risk_manager.calls == 1
    assert result.status == "rejected"
    assert result.reasons == ("blocked by mandatory RiskManager",)
    assert broker.called is False
    assert not (config.pending_orders_dir / f"{order.id}.json").exists()

