from __future__ import annotations

from dataclasses import dataclass

from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.execution.approval import ApprovalManager
from omni_trade_ai.execution.audit import AuditLogger
from omni_trade_ai.execution.order import AccountSnapshot, Order, OrderResult
from omni_trade_ai.execution.order_router import OrderRouter
from omni_trade_ai.portfolio.positions import Position
from omni_trade_ai.portfolio.state import PortfolioState
from omni_trade_ai.risk.manager import RiskManager


@dataclass
class SpyBroker:
    called: bool = False

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(0, 0, 0, "spy")

    def get_positions(self) -> list[Position]:
        return []

    def place_order(self, order: Order) -> OrderResult:
        self.called = True
        return OrderResult(True, True, order.id, "filled", "filled")

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(True, False, order_id, "cancelled", "cancelled")


def make_router(tmp_path, config: OmniTradeConfig) -> OrderRouter:
    audit = AuditLogger(tmp_path / "audit")
    return OrderRouter(
        config=config,
        risk_manager=RiskManager.from_config(config, audit),
        approval_manager=ApprovalManager(tmp_path / "pending"),
        audit=audit,
    )


def test_risk_rejection_prevents_broker_place_order(tmp_path) -> None:
    config = OmniTradeConfig(max_position_size=50)
    broker = SpyBroker()
    result = make_router(tmp_path, config).route(
        Order("BTC-USD", "buy", 1, limit_price=100, confidence=1),
        mode="paper",
        broker=broker,
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )

    assert result.status == "rejected"
    assert broker.called is False


def test_live_order_without_approval_creates_pending_and_does_not_execute(tmp_path) -> None:
    config = OmniTradeConfig(
        trading_mode="live",
        enable_live_trading=True,
        live_broker="alpaca",
        pending_orders_dir=tmp_path / "pending",
        audit_dir=tmp_path / "audit",
    )
    broker = SpyBroker()
    order = Order(
        "BTC-USD",
        "buy",
        1,
        limit_price=100,
        confidence=1,
        stop_loss=95,
    )

    result = make_router(tmp_path, config).route(
        order,
        mode="live",
        broker=broker,
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )

    assert result.status == "pending_approval"
    assert broker.called is False
    assert (tmp_path / "pending" / f"{order.id}.json").exists()


def test_live_order_with_stale_missing_approval_fails_safely(tmp_path) -> None:
    config = OmniTradeConfig(
        trading_mode="live",
        enable_live_trading=True,
        live_broker="alpaca",
        pending_orders_dir=tmp_path / "pending",
    )

    result = make_router(tmp_path, config).route(
        Order("BTC-USD", "buy", 1, limit_price=100, confidence=1, stop_loss=95),
        mode="live",
        broker=SpyBroker(),
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )

    assert result.status == "pending_approval"


def test_ai_output_cannot_call_broker_directly() -> None:
    order = Order("BTC-USD", "buy", 1, limit_price=100, source="ai_committee")

    assert order.source == "ai_committee"
    assert not hasattr(order, "place_order")

