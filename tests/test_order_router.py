# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_order_router.py
# PURPOSE: Verifies order router behavior and regression expectations.
# DEPS:    dataclasses, json, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from atlas_agent.config import AtlasConfig
from atlas_agent.execution.approval import ApprovalManager, InvalidApprovalIdError
from atlas_agent.execution.audit import AuditLogger
from atlas_agent.execution.order import AccountSnapshot, Order, OrderResult
from atlas_agent.execution.order_router import OrderRouter
from atlas_agent.portfolio.positions import Position
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.risk.manager import RiskManager


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


@dataclass
class ExplodingBroker:
    error_text: str = "token=raw-secret should never leak"

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(0, 0, 0, "exploding")

    def get_positions(self) -> list[Position]:
        return []

    def place_order(self, order: Order) -> OrderResult:
        raise RuntimeError(self.error_text)

    def cancel_order(self, order_id: str) -> OrderResult:
        return OrderResult(True, False, order_id, "cancelled", "cancelled")


def make_router(tmp_path, config: AtlasConfig) -> OrderRouter:
    audit = AuditLogger(tmp_path / "audit")
    return OrderRouter(
        config=config,
        risk_manager=RiskManager.from_config(config, audit),
        approval_manager=ApprovalManager(tmp_path / "pending"),
        audit=audit,
    )


def test_risk_rejection_prevents_broker_place_order(tmp_path) -> None:
    config = AtlasConfig(max_position_size=50)
    broker = SpyBroker()
    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", 1, limit_price=100, confidence=1),
        mode="paper",
        broker=broker,
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )

    assert result.status == "rejected"
    assert broker.called is False


def test_live_order_without_approval_creates_pending_and_does_not_execute(tmp_path) -> None:
    config = AtlasConfig(
        trading_mode="live",
        enable_live_trading=True,
        live_broker="alpaca",
        pending_orders_dir=tmp_path / "pending",
        audit_dir=tmp_path / "audit",
    )
    broker = SpyBroker()
    order = Order(
        "TEST-SYMBOL",
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


def test_approval_manager_accepts_valid_machine_generated_ids(tmp_path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = Order(
        "TEST-SYMBOL",
        "buy",
        1,
        limit_price=100,
        confidence=1,
        stop_loss=95,
        id="order_ABC-123.45",
    )

    path = manager.create_pending_order(order)
    approved_path = manager.approve(order.id)

    assert path == approved_path
    assert approved_path.name == "order_ABC-123.45.json"
    assert approved_path.parent.resolve() == (tmp_path / "pending").resolve()
    assert manager.is_approved(order.id) is True


@pytest.mark.parametrize(
    "order_id",
    [
        "",
        "   ",
        "abc/def",
        r"abc\def",
        ".",
        "..",
        "../secret",
        "/tmp/order",
        r"C:\tmp\order",
    ],
)
def test_approval_manager_rejects_unsafe_order_ids(tmp_path, order_id) -> None:
    manager = ApprovalManager(tmp_path / "pending")

    with pytest.raises(InvalidApprovalIdError, match="Invalid pending order id"):
        manager.path_for(order_id)

    assert not (tmp_path / "secret.json").exists()
    assert not (tmp_path / "pending" / "secret.json").exists()


def test_live_order_with_stale_missing_approval_fails_safely(tmp_path) -> None:
    config = AtlasConfig(
        trading_mode="live",
        enable_live_trading=True,
        live_broker="alpaca",
        pending_orders_dir=tmp_path / "pending",
    )

    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", 1, limit_price=100, confidence=1, stop_loss=95),
        mode="live",
        broker=SpyBroker(),
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )

    assert result.status == "pending_approval"


def test_ai_output_cannot_call_broker_directly() -> None:
    order = Order("TEST-SYMBOL", "buy", 1, limit_price=100, source="ai_committee")

    assert order.source == "ai_committee"
    assert not hasattr(order, "place_order")


def test_broker_place_order_exception_is_sanitized_and_audited_safely(tmp_path) -> None:
    config = AtlasConfig()
    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", 1, limit_price=100, confidence=1),
        mode="paper",
        broker=ExplodingBroker(error_text="api_key=raw-secret account_id=acct-123"),
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )

    assert result.status == "failed"
    assert result.message == "broker operation failed"
    assert "broker_operation_failed" in result.reasons
    assert "operation=place_order" in result.reasons
    assert "broker=explodingbroker" in result.reasons

    audit_path = tmp_path / "audit" / "audit.jsonl"
    payload = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[-1])
    serialized = json.dumps(payload, sort_keys=True)
    assert payload["event_type"] == "broker_order_result"
    assert payload["payload"]["broker_error"]["code"] == "broker_operation_failed"
    assert payload["payload"]["broker_error"]["operation"] == "place_order"
    assert payload["payload"]["broker_error"]["broker"] == "explodingbroker"
    assert payload["payload"]["broker_error"]["message"] == "broker operation failed"
    assert "raw-secret" not in serialized
    assert "account_id=acct-123" not in serialized


@pytest.mark.parametrize("bad_quantity", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_order_router_rejects_invalid_quantity(tmp_path, bad_quantity) -> None:
    config = AtlasConfig()
    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", bad_quantity, limit_price=100, confidence=1),
        mode="paper",
        broker=SpyBroker(),
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )
    assert result.status == "rejected"
    assert "invalid_quantity" in result.reasons
    assert "raw-secret" not in str(result)


@pytest.mark.parametrize("bad_limit_price", [float("nan"), float("inf"), float("-inf"), 0, -1])
def test_order_router_rejects_invalid_limit_price(tmp_path, bad_limit_price) -> None:
    config = AtlasConfig()
    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", 1, limit_price=bad_limit_price, confidence=1),
        mode="paper",
        broker=SpyBroker(),
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )
    assert result.status == "rejected"
    assert "invalid_limit_price" in result.reasons
    assert "raw-secret" not in str(result)


@pytest.mark.parametrize("bad_quantity", ["abc", {}, [], object()])
def test_order_router_rejects_non_numeric_quantity(tmp_path, bad_quantity) -> None:
    config = AtlasConfig()
    broker = SpyBroker()
    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", bad_quantity, limit_price=100, confidence=1),
        mode="paper",
        broker=broker,
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )
    assert result.status == "rejected"
    assert "invalid_quantity" in result.reasons
    assert broker.called is False


@pytest.mark.parametrize("bad_limit_price", ["abc", {}, [], object()])
def test_order_router_rejects_non_numeric_limit_price(tmp_path, bad_limit_price) -> None:
    config = AtlasConfig()
    broker = SpyBroker()
    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", 1, limit_price=bad_limit_price, confidence=1),
        mode="paper",
        broker=broker,
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )
    assert result.status == "rejected"
    assert "invalid_limit_price" in result.reasons
    assert broker.called is False


@pytest.mark.parametrize("bad_quantity", [True, False])
def test_order_router_rejects_boolean_quantity(tmp_path, bad_quantity) -> None:
    config = AtlasConfig()
    broker = SpyBroker()
    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", bad_quantity, limit_price=100, confidence=1),
        mode="paper",
        broker=broker,
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )
    assert result.status == "rejected"
    assert "invalid_quantity" in result.reasons
    assert broker.called is False


@pytest.mark.parametrize("bad_limit_price", [True, False])
def test_order_router_rejects_boolean_limit_price(tmp_path, bad_limit_price) -> None:
    config = AtlasConfig()
    broker = SpyBroker()
    result = make_router(tmp_path, config).route(
        Order("TEST-SYMBOL", "buy", 1, limit_price=bad_limit_price, confidence=1),
        mode="paper",
        broker=broker,
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )
    assert result.status == "rejected"
    assert "invalid_limit_price" in result.reasons
    assert broker.called is False
