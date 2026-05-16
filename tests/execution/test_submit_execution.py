from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
from atlas_agent.brokers.base import BrokerOperationError
from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidPendingOrderError,
    _compute_order_hash,
    _order_to_dict,
)
from atlas_agent.execution.order import Order
from atlas_agent.execution.submit_execution import run_submit_execution
from atlas_agent.risk.models import RiskDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_order(**kwargs) -> Order:
    defaults = {
        "symbol": "TEST",
        "side": "buy",
        "quantity": 1.0,
        "limit_price": 100.0,
        "confidence": 1.0,
        "stop_loss": 95.0,
    }
    defaults.update(kwargs)
    # If limit_price is set but order_type is not, infer limit type
    if defaults.get("limit_price") is not None and "order_type" not in kwargs:
        defaults["order_type"] = "limit"
    return Order(**defaults)


def _make_v2_payload(order: Order, **overrides) -> dict:
    order_dict = _order_to_dict(order)
    now = datetime.now(UTC)
    payload = {
        "schema_version": "2",
        "order": order_dict,
        "approved": True,
        "created_at": now.isoformat(),
        "approved_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "approval_actor": "test",
        "order_hash": _compute_order_hash(order_dict),
        "status": "approved",
        "status_transitions": [
            {"status": "pending_approval", "at": now.isoformat(), "actor": "system"},
            {"status": "approved", "at": now.isoformat(), "actor": "test"},
        ],
        "submit_attempts": [],
        "broker_order_id": None,
        "client_order_id": None,
        "fill_quantity": 0.0,
        "fill_price": None,
        "submitted_at": None,
    }
    payload.update(overrides)
    return payload


def _write_payload(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


class _FakeRiskConfig:
    max_order_notional = 5000.0
    symbol_allowlist = None
    symbol_blocklist = set()
    live_submit_max_order_notional = 0.0
    live_submit_allowed_symbols = None
    live_submit_allowed_sides = None


class FakeConfig:
    enable_live_trading = True
    enable_live_submit = False
    max_position_size = 10000.0
    max_order_notional = 5000.0
    symbol_allowlist = None
    symbol_blocklist = set()
    require_stop_loss_live = True
    pending_orders_dir = Path("pending_orders")
    live_broker = "alpaca"
    memory_dir = Path("memory")
    risk = _FakeRiskConfig()


def _mock_broker_resolver(
    can_sync: bool = True,
    can_submit: bool = False,
    broker_id: str = "alpaca",
) -> MagicMock:
    mock_status = MagicMock()
    mock_status.can_sync = can_sync
    mock_status.can_submit = can_submit
    mock_status.broker_id = broker_id
    mock_status.to_dict.return_value = {"can_sync": can_sync, "can_submit": can_submit}

    mock_resolution = MagicMock()
    mock_resolution.sync_provider = MagicMock(spec=AlpacaBrokerAdapter)

    mock_exec_resolution = MagicMock()
    mock_exec_resolution.execution_broker = None

    mock_resolver = MagicMock()
    mock_resolver.resolve_status.return_value = mock_status
    mock_resolver.resolve_sync_provider.return_value = mock_resolution
    mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
    return mock_resolver


def _mock_sync_service() -> MagicMock:
    from atlas_agent.risk.models import PortfolioSnapshot

    mock_result = MagicMock()
    mock_result.status = "success"
    mock_result.account = MagicMock()
    mock_result.positions = []
    mock_result.open_orders = []
    mock_result.balances = []
    mock_result.errors = []
    mock_result.diagnostics = {"broker_errors": []}

    mock_service = MagicMock()
    mock_service.sync.return_value = mock_result
    mock_service.get_portfolio_snapshot.return_value = PortfolioSnapshot(
        cash=10000, equity=10000, total_exposure=0
    )
    return mock_service


def _mock_risk_manager(allowed: bool = True) -> MagicMock:
    mock_decision = RiskDecision(
        allowed=allowed,
        status="allowed" if allowed else "blocked",
        reason="All risk checks passed" if allowed else "Risk violations detected",
        violations=[],
        classification="opens_new_position",
    )
    mock_manager = MagicMock()
    mock_manager.evaluate_order.return_value = mock_decision
    return mock_manager


# ---------------------------------------------------------------------------
# Invalid order id: no raw value stored or returned
# ---------------------------------------------------------------------------

def test_skeleton_invalid_order_id_masks_raw_value(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    report = run_submit_execution("../../etc/passwd", FakeConfig(), manager)
    assert report.ok is False
    assert report.status == "blocked"
    assert report.order_id == "<invalid>"
    assert report.blocked_reason == "invalid_pending_order_id"
    assert report.message == "Invalid pending order id."
    assert "etc/passwd" not in report.message
    assert "etc/passwd" not in str(report.gates)


def test_skeleton_fake_secret_order_id_not_leaked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    # Path-traversal + fake secret combination triggers InvalidApprovalIdError
    report = run_submit_execution("../../etc/FAKE_API_KEY_12345", FakeConfig(), manager)
    assert report.ok is False
    assert report.order_id == "<invalid>"
    assert "FAKE_API_KEY" not in report.message
    assert "FAKE_API_KEY" not in str(report.gates)
    assert "etc/passwd" not in report.message
    assert "etc/passwd" not in str(report.gates)


# ---------------------------------------------------------------------------
# Happy path: all gates pass, blocked at can_submit=false
# ---------------------------------------------------------------------------

def test_skeleton_blocks_at_can_submit_false_when_all_gates_pass(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="happy")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "blocked"
    assert report.blocked_reason == "can_submit_false"
    assert report.gates["can_submit"] == "fail"
    assert report.gates["risk_revalidation"] == "pass"
    assert report.gates["fresh_sync"] == "pass"
    assert report.client_order_id is not None
    assert report.client_order_id.startswith("atlas-")


# ---------------------------------------------------------------------------
# Never calls forbidden functions
# ---------------------------------------------------------------------------

def test_skeleton_no_broker_place_order_called(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-place")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_place.assert_not_called()


def test_skeleton_no_resolve_execution_broker_called(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-exec")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_resolver.resolve_execution_broker = MagicMock(side_effect=AssertionError("must not be called"))
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_resolver.resolve_execution_broker.assert_not_called()


def test_skeleton_no_order_router_route_called(tmp_path: Path) -> None:
    from atlas_agent.execution.order_router import OrderRouter

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-route")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(OrderRouter, "route", side_effect=AssertionError("OrderRouter.route must not be called")) as mock_route:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_route.assert_not_called()


# ---------------------------------------------------------------------------
# No file mutation
# ---------------------------------------------------------------------------

def test_skeleton_does_not_mark_submitted(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-submit-mark")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "approved"


def test_skeleton_does_not_mutate_file(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-mutate")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    after = path.read_text(encoding="utf-8")
    assert before == after


# ---------------------------------------------------------------------------
# Gate tests: block before sync
# ---------------------------------------------------------------------------

def test_skeleton_expired_approval_blocks_before_sync(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="expired")
    payload = _make_v2_payload(order)
    payload["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls:
        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "approval_expired"
    mock_sync_cls.assert_not_called()


def test_skeleton_tampered_file_blocks_before_sync(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="tampered")
    payload = _make_v2_payload(order)
    payload["order_hash"] = "tampered"
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls:
        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "invalid_pending_order"
    mock_sync_cls.assert_not_called()


def test_skeleton_live_trading_disabled_blocks_before_sync(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="live-off")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    config = FakeConfig()
    config.enable_live_trading = False

    with patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls:
        report = run_submit_execution(order.id, config, manager)

    assert report.ok is False
    assert report.blocked_reason == "live_trading_disabled"
    mock_sync_cls.assert_not_called()


def test_skeleton_kill_switch_active_blocks_before_sync(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="ks-active")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=True, mode="soft_pause")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "kill_switch_active"
    mock_sync_cls.assert_not_called()


def test_skeleton_invalid_client_order_id_blocks_before_sync(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="bad-cid")
    payload = _make_v2_payload(order, client_order_id="../../etc/passwd")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls:
        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "invalid_client_order_id"
    mock_sync_cls.assert_not_called()


def test_skeleton_missing_client_order_id_computed_not_persisted(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-cid")
    payload = _make_v2_payload(order, client_order_id=None)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    assert report.client_order_id is not None
    assert report.client_order_id.startswith("atlas-")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.get("client_order_id") is None


def test_skeleton_existing_client_order_id_allowed(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="has-cid")
    cid = "atlas-existing-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    assert report.client_order_id == cid


# ---------------------------------------------------------------------------
# Terminal state blocks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,expected_reason", [
    ("submitted", "already_submitted"),
    ("duplicate_reconciled", "already_reconciled"),
    ("submit_uncertain", "reconciliation_required"),
    ("reconciliation_required", "reconciliation_required"),
])
def test_skeleton_terminal_state_blocks(tmp_path: Path, status: str, expected_reason: str) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id=f"term-{status}")
    payload = _make_v2_payload(order, status=status)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == expected_reason
    assert report.gates["idempotency"] == "fail"


# ---------------------------------------------------------------------------
# Market order block
# ---------------------------------------------------------------------------

def test_skeleton_market_order_blocks_with_market_price_unavailable(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "market_price_unavailable"
    assert report.gates["market_price"] == "fail"


# ---------------------------------------------------------------------------
# Sync failure blocks
# ---------------------------------------------------------------------------

def test_skeleton_fresh_sync_critical_failure_blocks_before_risk(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sync-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = (
            [],
            {
                "status": "error",
                "errors": ["live broker sync failed: sync_account_state"],
                "diagnostics": {"failed_operations": ["sync_account_state"]},
            },
        )
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_sync_failed"
    assert report.gates["fresh_sync"] == "fail"
    mock_risk_cls.assert_not_called()


def test_skeleton_malformed_broker_errors_blocks_before_risk(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed-diag")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = (
            [],
            {
                "status": "error",
                "errors": ["malformed broker_errors"],
                "diagnostics": {"broker_errors": "not_a_list"},
            },
        )
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_sync_failed"
    mock_risk_cls.assert_not_called()


def test_skeleton_balances_only_warning_proceeds_to_can_submit(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="balance-warn")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = (
            [{"operation": "sync_balances", "code": "broker_operation_failed", "broker": "alpaca"}],
            None,
        )
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    assert report.gates["fresh_sync"] == "pass"
    assert any("sync_balances" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# Risk revalidation failure
# ---------------------------------------------------------------------------

def test_skeleton_risk_revalidation_failure_blocks_before_can_submit(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="risk-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=False)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "risk_revalidation_failed"
    assert report.gates["risk_revalidation"] == "fail"
    assert "can_submit" not in report.gates


# ---------------------------------------------------------------------------
# No private values leak
# ---------------------------------------------------------------------------

def test_skeleton_no_private_values_leak(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-leak")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    # No raw payload values in message
    assert "TEST" not in report.message
    assert "buy" not in report.message
    assert "100.0" not in report.message


# ---------------------------------------------------------------------------
# Batch 4.6: confirm helpers remain unwired
# ---------------------------------------------------------------------------

def test_submit_execution_still_does_not_mutate_file_while_can_submit_false(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-mutate-46")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_submit_execution_still_does_not_call_mark_submit_requested(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-mark-46")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_state.mark_submit_requested", side_effect=AssertionError("mark_submit_requested must not be called")) as mock_mark:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_mark.assert_not_called()


def test_submit_execution_still_does_not_call_place_order(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-place-46")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_place.assert_not_called()


# ---------------------------------------------------------------------------
# Batch 4.7: Pre-Submit Mutation Wiring Behind Hard-Disabled Gate
# ---------------------------------------------------------------------------

def test_can_submit_false_no_mutation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="can-submit-false")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_can_submit_false_does_not_call_mark_submit_requested(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-mark-47")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested", side_effect=AssertionError("mark_submit_requested must not be called")) as mock_mark:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_mark.assert_not_called()


def test_mocked_can_submit_true_marks_submit_requested_then_prepare_failed(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="mock-true")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"
    assert loaded["client_order_id"] is not None
    assert loaded["client_order_id"].startswith("atlas-")
    assert loaded["submit_requested_at"] is not None
    assert loaded.get("submitted_at") is None
    assert loaded.get("broker_order_id") is None
    assert loaded["status_transitions"][-2]["status"] == "submit_requested"
    assert loaded["status_transitions"][-1]["status"] == "submit_prepare_failed"
    assert len(loaded["submit_attempts"]) == 1
    assert loaded["submit_attempts"][0]["status"] == "submit_prepare_failed"
    assert loaded["submit_attempts"][0]["error_code"] == "execution_broker_unavailable"


def test_mocked_can_submit_true_returns_execution_broker_unavailable(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="mock-block")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "blocked"
    assert report.blocked_reason == "execution_broker_unavailable"
    assert report.message == "Execution broker is not available."
    assert report.gates["can_submit"] == "pass"
    assert report.gates["execution_broker"] == "unavailable"


def test_mocked_can_submit_true_keeps_submitted_at_null(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-submitted-at")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.get("submitted_at") is None


def test_mocked_can_submit_true_keeps_broker_order_id_null(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-broker-id")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.get("broker_order_id") is None


def test_mocked_can_submit_true_does_not_call_place_order(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-place-47")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_place.assert_not_called()


def test_mocked_can_submit_true_calls_resolve_execution_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="calls-exec-49")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_resolver.resolve_execution_broker.assert_called_once_with("live")


def test_mocked_can_submit_true_does_not_call_order_router_route(tmp_path: Path) -> None:
    from atlas_agent.execution.order_router import OrderRouter

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-route-47")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(OrderRouter, "route", side_effect=AssertionError("OrderRouter.route must not be called")) as mock_route:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_route.assert_not_called()


def test_rerun_on_submit_requested_blocks_before_sync(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rerun-sr")
    payload = _make_v2_payload(order, status="submit_requested")
    # Pre-seed a submit_attempt to simulate prior Batch 4.7 run
    payload["submit_attempts"] = [{
        "attempt_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "client_order_id": "atlas-rerun-deadbeef",
        "status": "submit_requested",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    payload["client_order_id"] = "atlas-rerun-deadbeef"
    payload["submit_requested_at"] = datetime.now(UTC).isoformat()
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls:
        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.gates["idempotency"] == "fail"
    mock_sync_cls.assert_not_called()


def test_rerun_on_submit_requested_does_not_append_second_attempt(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rerun-no-dup")
    payload = _make_v2_payload(order, status="submit_requested")
    payload["submit_attempts"] = [{
        "attempt_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "client_order_id": "atlas-rerun2-deadbeef",
        "status": "submit_requested",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    payload["client_order_id"] = "atlas-rerun2-deadbeef"
    payload["submit_requested_at"] = datetime.now(UTC).isoformat()
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert len(loaded["submit_attempts"]) == 1


def test_sync_failure_blocks_before_mutation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sync-fail-before")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested", side_effect=AssertionError("must not be called")) as mock_mark:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = (
            [],
            {"status": "error", "errors": ["sync failed"], "diagnostics": {"failed_operations": ["sync_account_state"]}},
        )
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_sync_failed"
    mock_mark.assert_not_called()


def test_risk_failure_blocks_before_mutation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="risk-fail-before")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested", side_effect=AssertionError("must not be called")) as mock_mark:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=False)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "risk_revalidation_failed"
    mock_mark.assert_not_called()


def test_kill_switch_blocks_before_mutation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="ks-before")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested", side_effect=AssertionError("must not be called")) as mock_mark:
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=True, mode="soft_pause")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "kill_switch_active"
    mock_mark.assert_not_called()
    mock_sync_cls.assert_not_called()


def test_market_order_blocks_before_mutation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-before", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested", side_effect=AssertionError("must not be called")) as mock_mark:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "market_price_unavailable"
    mock_mark.assert_not_called()


# ---------------------------------------------------------------------------
# Batch 4.9: Broker Submit Boundary
# ---------------------------------------------------------------------------

def _mock_execution_broker(result=None, side_effect=None):
    mock_broker = MagicMock()
    if result is not None:
        mock_broker.place_order.return_value = result
    if side_effect is not None:
        mock_broker.place_order.side_effect = side_effect
    return mock_broker


def _setup_resolver_with_broker(mock_resolver_cls, broker):
    mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
    mock_resolver.resolve_execution_broker.return_value.execution_broker = broker
    mock_resolver_cls.return_value = mock_resolver
    return mock_resolver


# Production path: can_submit=false

def test_production_can_submit_false_no_mutation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="prod-no-mut")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_production_can_submit_false_no_place_order(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="prod-no-place")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_place.assert_not_called()


def test_production_can_submit_false_no_resolve_execution_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="prod-no-res")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_resolver.resolve_execution_broker = MagicMock(side_effect=AssertionError("must not be called"))
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_resolver.resolve_execution_broker.assert_not_called()


# Mocked can_submit=true with valid broker

def test_mocked_can_submit_true_reconstructs_order_before_mark_submit_requested(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="reconstruct")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    call_order = []
    original_reconstruct = None

    def _capture_reconstruct(order_dict):
        call_order.append("reconstruct")
        from copy import deepcopy
        d = deepcopy(order_dict)
        created_at_raw = d.get("created_at")
        if isinstance(created_at_raw, str):
            d["created_at"] = datetime.fromisoformat(created_at_raw)
        return Order(**d)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution._reconstruct_order") as mock_recon, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested") as mock_mark:
        mock_recon.side_effect = lambda d: (_capture_reconstruct(d), call_order.append("mark"))[0] if False else _capture_reconstruct(d)
        mock_mark.side_effect = lambda *a, **k: (call_order.append("mark_requested"), None)[1] if False else call_order.append("mark_requested")
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    assert "reconstruct" in call_order
    assert "mark_requested" in call_order
    assert call_order.index("reconstruct") < call_order.index("mark_requested")


def test_mocked_can_submit_true_calls_mark_submit_requested_before_place_order(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="before-place")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok")
    )

    call_order = []
    original_mark = None

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested") as mock_mark:
        def _mark_then_record(*args, **kwargs):
            from atlas_agent.execution.submit_state import mark_submit_requested as real_mark
            real_mark(*args, **kwargs)
            call_order.append("mark_submit_requested")
        mock_mark.side_effect = _mark_then_record
        mock_broker.place_order = MagicMock(side_effect=lambda *a, **k: (call_order.append("place_order"), OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok"))[1])
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    assert "mark_submit_requested" in call_order
    assert "place_order" in call_order
    assert call_order.index("mark_submit_requested") < call_order.index("place_order")


def test_place_order_receives_deterministic_client_order_id(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult
    from atlas_agent.execution.submit_state import compute_client_order_id

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cid-check")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    expected_cid = compute_client_order_id(order.id, payload["order_hash"])
    mock_broker.place_order.assert_called_once()
    call_kwargs = mock_broker.place_order.call_args
    assert call_kwargs.kwargs.get("client_order_id") == expected_cid


def test_accepted_result_marks_acknowledged(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="ack")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.blocked_reason is None
    assert report.message == "Broker acknowledged order."
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"
    assert loaded["submitted_at"] is not None
    assert loaded["broker_order_id"] == "b-123"
    assert loaded["broker_status"] == "new"


def test_rejected_result_returns_broker_rejected_report_when_mark_failed_succeeds(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rej")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=False, filled=False, order_id="", status="rejected", message="rejected")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "broker_rejected_order"
    assert report.message == "Broker rejected order."
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "failed"
    assert loaded["submit_attempts"][0]["error_code"] == "broker_rejected_order"


def test_broker_rejected_error_returns_broker_rejected_report_when_mark_failed_succeeds(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rej-exc")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker rejected order")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "broker_rejected_order"
    assert report.message == "Broker rejected order."
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "failed"
    assert loaded["submit_attempts"][0]["error_code"] == "broker_rejected_order"


def test_broker_unavailable_marks_submit_uncertain(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="unav")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker unavailable")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker submission outcome is uncertain. Run --reconcile first."
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_uncertain"
    assert loaded["submit_attempts"][0]["error_code"] == "broker_unavailable"


def test_broker_transport_failure_marks_submit_uncertain(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="trans")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker transport request failed")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker submission outcome is uncertain. Run --reconcile first."
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_uncertain"
    assert loaded["submit_attempts"][0]["error_code"] == "broker_transport_failed"


def test_malformed_broker_response_marks_submit_uncertain(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="mal")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("malformed broker response")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker submission outcome is uncertain. Run --reconcile first."
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_uncertain"
    assert loaded["submit_attempts"][0]["error_code"] == "malformed_broker_response"


def test_client_order_id_mismatch_marks_submit_uncertain(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cid-mis")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("client_order_id mismatch")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker submission outcome is uncertain. Run --reconcile first."
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_uncertain"
    assert loaded["submit_attempts"][0]["error_code"] == "client_order_id_mismatch"


def test_unexpected_broker_exception_marks_submit_uncertain_unknown(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="unk")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=RuntimeError("unexpected")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker submission outcome is uncertain. Run --reconcile first."
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_uncertain"
    assert loaded["submit_attempts"][0]["error_code"] == "unknown"


def test_resolve_execution_broker_none_marks_submit_prepare_failed(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-exec")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "execution_broker_unavailable"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"
    assert loaded["submit_attempts"][0]["error_code"] == "execution_broker_unavailable"


def test_execution_broker_missing_place_order_marks_submit_prepare_failed(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-place")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = MagicMock()
    # No place_order attribute
    del mock_broker.place_order

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "execution_broker_invalid"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"
    assert loaded["submit_attempts"][0]["error_code"] == "execution_broker_invalid"


def test_kill_switch_active_before_final_place_order_blocks_without_broker_call(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="ks-final")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        # First check passes, second check (before broker) fails
        mock_ks.status.side_effect = [
            MagicMock(enabled=False, mode="normal"),
            MagicMock(enabled=True, mode="soft_pause"),
        ]
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "kill_switch_active"
    assert report.message == "Kill switch is active."
    mock_broker.place_order.assert_not_called()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"
    assert loaded["submit_attempts"][0]["error_code"] == "kill_switch_active"


def test_mark_submit_requested_failure_prevents_place_order(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="mark-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested", side_effect=RuntimeError("disk full")) as mock_mark:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "submit_state_mutation_failed"
    assert report.message == "Submit state could not be prepared."
    mock_broker.place_order.assert_not_called()


def test_mark_submit_requested_failure_prevents_resolve_execution_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="mark-fail-no-res")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested", side_effect=RuntimeError("disk full")):
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_resolver.resolve_execution_broker = MagicMock(side_effect=AssertionError("must not be called"))
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_resolver.resolve_execution_broker.assert_not_called()


def test_final_kill_switch_error_code_allowed_by_mark_submit_prepare_failed(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="ks-allowed")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.side_effect = [
            MagicMock(enabled=False, mode="normal"),
            MagicMock(enabled=True, mode="soft_pause"),
        ]
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "kill_switch_active"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"
    assert loaded["submit_attempts"][0]["error_code"] == "kill_switch_active"


def test_broker_rejected_but_mark_failed_fails_returns_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rej-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker rejected order")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_failed", side_effect=RuntimeError("disk full")):
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker response received, but local state update failed. Run --reconcile first."
    mock_broker.place_order.assert_called_once()


def test_broker_unavailable_but_mark_uncertain_fails_returns_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="unav-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker unavailable")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_uncertain", side_effect=RuntimeError("disk full")):
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker response received, but local state update failed. Run --reconcile first."
    mock_broker.place_order.assert_called_once()


def test_malformed_broker_response_but_mark_uncertain_fails_returns_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="mal-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("malformed broker response")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_uncertain", side_effect=RuntimeError("disk full")):
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker response received, but local state update failed. Run --reconcile first."
    mock_broker.place_order.assert_called_once()


def test_unexpected_broker_exception_but_mark_uncertain_fails_returns_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="unk-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=RuntimeError("unexpected")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_uncertain", side_effect=RuntimeError("disk full")):
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker response received, but local state update failed. Run --reconcile first."
    mock_broker.place_order.assert_called_once()


def test_acknowledged_but_mark_acknowledged_fails_uses_ack_specific_message(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="ack-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_acknowledged", side_effect=RuntimeError("FAKE_SECRET_INTERNAL_ERROR")):
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert report.message == "Broker acknowledged order, but local state update failed. Run --reconcile first."
    mock_broker.place_order.assert_called_once()
    # Ensure no raw exception text leaks
    report_dict = report.to_dict()
    assert "FAKE_SECRET_INTERNAL_ERROR" not in str(report_dict)
    assert "FAKE_SECRET_INTERNAL_ERROR" not in report.message


def test_uncertain_broker_error_uses_uncertain_message(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="unc-msg")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker unavailable")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.message == "Broker submission outcome is uncertain. Run --reconcile first."


def test_post_broker_local_write_failure_no_raw_exception_leak(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-leak")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker unavailable")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_uncertain", side_effect=RuntimeError("SECRET_DISK_ERROR_42")):
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    report_dict = report.to_dict()
    assert "SECRET_DISK_ERROR_42" not in str(report_dict)
    assert "SECRET_DISK_ERROR_42" not in report.message


def test_broker_error_code_maps_client_order_id_mismatch_exactly() -> None:
    from atlas_agent.execution.submit_execution import _broker_error_code

    assert _broker_error_code(BrokerOperationError("client_order_id mismatch")) == "client_order_id_mismatch"
    assert _broker_error_code(BrokerOperationError("client order id mismatch")) == "unknown"
    assert _broker_error_code(BrokerOperationError("broker rejected order")) == "broker_rejected_order"
    assert _broker_error_code(BrokerOperationError("broker unavailable")) == "broker_unavailable"
    assert _broker_error_code(BrokerOperationError("broker transport request failed")) == "broker_transport_failed"
    assert _broker_error_code(BrokerOperationError("malformed broker response")) == "malformed_broker_response"
    assert _broker_error_code(BrokerOperationError("unknown error")) == "unknown"


def test_accepted_true_missing_order_id_marks_submit_uncertain_malformed(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="ack-no-id")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="", status="new", message="ok")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_uncertain"
    assert loaded["submit_attempts"][0]["error_code"] == "malformed_broker_response"


# Idempotency gate expansion

def test_rerun_on_acknowledged_blocks(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rerun-ack")
    payload = _make_v2_payload(order, status="acknowledged")
    payload["broker_order_id"] = "b-123"
    payload["submitted_at"] = datetime.now(UTC).isoformat()
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "already_submitted"
    assert report.gates["idempotency"] == "fail"


def test_rerun_on_submit_prepare_failed_blocks(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rerun-spf")
    payload = _make_v2_payload(order, status="submit_prepare_failed")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "submit_prepare_failed"
    assert report.gates["idempotency"] == "fail"


# Reruns on terminal states still block

def test_rerun_on_failed_blocks_before_sync_and_no_mutation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rerun-fail")
    payload = _make_v2_payload(order, status="failed")
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls:
        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "submit_failed"
    assert report.gates["idempotency"] == "fail"
    assert report.message == "Order is in a terminal failed state."
    # Must block before sync/risk/mutation
    mock_sync_cls.assert_not_called()
    # Must not append submit_attempts
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_rerun_on_submit_uncertain_blocks_and_requires_reconcile(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rerun-unc")
    payload = _make_v2_payload(order, status="submit_uncertain")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    assert "reconcile" in report.message.lower()
    assert report.gates["idempotency"] == "fail"


# Safety / leak tests

def test_no_raw_broker_body_or_secret_leaks_in_text_output(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-leak-txt")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker unavailable")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    # Message must be exactly one of the static safe messages
    safe_messages = {
        "Broker submission outcome is uncertain. Run --reconcile first.",
        "Broker acknowledged order, but local state update failed. Run --reconcile first.",
        "Broker response received, but local state update failed. Run --reconcile first.",
        "Broker rejected order.",
        "Broker acknowledged order.",
        "Execution broker is not available.",
        "Execution broker is not valid.",
        "Kill switch is active.",
        "Submit state could not be prepared.",
        "Pending order file is invalid or corrupted.",
    }
    assert report.message in safe_messages


def test_no_raw_broker_body_or_secret_leaks_in_json_output(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-leak-json")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = _mock_execution_broker(
        side_effect=BrokerOperationError("broker unavailable")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        _setup_resolver_with_broker(mock_resolver_cls, mock_broker)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    d = report.to_dict()
    assert "broker unavailable" not in str(d)
    assert "HTTP" not in str(d)
    assert "api_key" not in str(d).lower()
    assert "secret" not in str(d).lower()


# Dry-run and reconcile invariants

def test_dry_run_still_read_only(tmp_path: Path) -> None:
    """Dry-run is not yet wired in run_submit_execution, but the function must not mutate."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="dry")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    after = path.read_text(encoding="utf-8")
    assert before == after


def test_reconcile_still_never_calls_place_order(tmp_path: Path) -> None:
    """Reconcile path does not exist in run_submit_execution, but confirm place_order is never called."""
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="reconcile")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager)

    mock_place.assert_not_called()


def test_paper_workflow_unchanged(tmp_path: Path) -> None:
    """Paper mode is not enabled in FakeConfig, but live_trading_enabled=False should block before broker."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="paper")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    config = FakeConfig()
    config.enable_live_trading = False

    report = run_submit_execution(order.id, config, manager)

    assert report.ok is False
    assert report.blocked_reason == "live_trading_disabled"
    after = path.read_text(encoding="utf-8")
    assert before == after


# ---------------------------------------------------------------------------
# Batch 5.0: Live-submit hard limits
# ---------------------------------------------------------------------------

class _FakeRiskConfigCanSubmit(_FakeRiskConfig):
    live_submit_max_order_notional = 1000.0
    live_submit_allowed_symbols = {"TEST", "AAPL"}
    live_submit_allowed_sides = {"buy"}


class FakeConfigCanSubmit(FakeConfig):
    """FakeConfig with can_submit=True defaults for live-submit limit testing."""
    enable_live_submit = True
    risk = _FakeRiskConfigCanSubmit()


def test_live_submit_limits_block_when_notional_exceeded(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="notional-exceeded", symbol="TEST", quantity=20.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_max_notional_exceeded"
    assert report.gates["live_submit_limits"] == "fail"


def test_live_submit_limits_block_when_symbol_not_allowed(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="symbol-blocked", symbol="UNAUTHORIZED")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_symbol_not_allowed"
    assert report.gates["live_submit_limits"] == "fail"


def test_live_submit_limits_block_when_side_not_allowed(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="side-blocked", side="sell")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_side_not_allowed"
    assert report.gates["live_submit_limits"] == "fail"


def test_live_submit_limits_pass_when_within_limits(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="within-limits", symbol="TEST", side="buy", quantity=1.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_broker = MagicMock()
    mock_broker.place_order.return_value = MagicMock(accepted=True, order_id="broker-123", status="accepted")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(AlpacaBroker, "place_order", return_value=mock_broker.place_order.return_value):
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = mock_broker
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.gates.get("live_submit_limits") == "pass"


def test_live_submit_limits_skipped_when_can_submit_false(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="skipped", symbol="UNAUTHORIZED", side="sell", quantity=100.0, limit_price=1000.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    config = FakeConfigCanSubmit()
    # can_submit=False on the broker_status means limits should be skipped
    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, config, manager)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    assert "live_submit_limits" not in report.gates


def test_live_submit_limits_fail_prevents_mark_submit_requested(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-mutation", symbol="UNAUTHORIZED")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_symbol_not_allowed"
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_live_submit_limits_fail_prevents_resolve_execution_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-resolve", symbol="UNAUTHORIZED")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_resolver.resolve_execution_broker = MagicMock(side_effect=AssertionError("must not be called"))
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_symbol_not_allowed"
    mock_resolver.resolve_execution_broker.assert_not_called()


def test_live_submit_limits_fail_prevents_place_order(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-place", symbol="UNAUTHORIZED")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = None
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_symbol_not_allowed"
    mock_place.assert_not_called()


def test_live_submit_limits_normalizes_configured_symbols(tmp_path: Path) -> None:
    """Lowercase configured symbols like {'aapl'} must allow order symbol 'AAPL'."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="normalized-symbol", symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    # Create a config with lowercase symbols in the allowlist
    class _FakeRiskConfigLowercase(_FakeRiskConfig):
        live_submit_max_order_notional = 1000.0
        live_submit_allowed_symbols = {"aapl", "tsla"}  # lowercase
        live_submit_allowed_sides = {"buy"}

    class FakeConfigLowercase(FakeConfig):
        enable_live_submit = True
        risk = _FakeRiskConfigLowercase()

    from atlas_agent.brokers.alpaca import AlpacaBroker
    mock_broker = MagicMock()
    mock_broker.place_order.return_value = MagicMock(accepted=True, order_id="broker-123", status="accepted")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch.object(AlpacaBroker, "place_order", return_value=mock_broker.place_order.return_value):
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = mock_broker
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigLowercase(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.gates.get("live_submit_limits") == "pass"


# ---------------------------------------------------------------------------
# Batch 5.1: Live-submit audit hardening
# ---------------------------------------------------------------------------

def _mock_audit_writer(event_log: list[tuple] | None = None) -> MagicMock:
    """Return a mock audit writer that records all written events."""
    mock = MagicMock()
    mock.events: list[dict] = []

    def capture(event_type: str, *, run_id: str = "", payload: dict | None = None, **kwargs: Any) -> None:
        if event_log is not None:
            event_log.append(("audit", event_type, payload or {}))
        mock.events.append({
            "event_type": event_type,
            "run_id": run_id,
            "payload": payload or {},
        })

    mock.write_event.side_effect = capture
    return mock


def test_initial_invalid_pending_order_emits_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-invalid-pending", symbol="FAKE_SECRET_SYMBOL")
    payload = _make_v2_payload(order)
    payload["order"]["symbol"] = "FAKE_SECRET_TAMPERED"
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "invalid_pending_order"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    payload_str = str(blocked_events[0]["payload"])
    assert blocked_events[0]["payload"]["reason_code"] == "invalid_pending_order"
    assert blocked_events[0]["payload"]["gate"] == "integrity"
    assert "FAKE_SECRET" not in payload_str
    assert "TAMPERED" not in payload_str
    assert "symbol" not in payload_str.lower()
    assert "traceback" not in payload_str.lower()
    assert str(path) not in payload_str
    assert "pending_orders" not in payload_str


def test_invalid_client_order_id_emits_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-invalid-cid")
    invalid_cid = "../../etc/FAKE_API_KEY_12345"
    payload = _make_v2_payload(order, client_order_id=invalid_cid)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "invalid_client_order_id"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    event_payload = blocked_events[0]["payload"]
    payload_str = str(event_payload)
    assert event_payload["reason_code"] == "invalid_client_order_id"
    assert event_payload["gate"] == "client_order_id"
    assert event_payload["client_order_id"] is None
    assert invalid_cid not in payload_str
    assert "FAKE_API_KEY" not in payload_str
    assert "../../etc" not in payload_str
    assert "etc/passwd" not in payload_str


def test_can_submit_false_emits_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-blocked")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "can_submit_false"
    assert blocked_events[0]["payload"]["gate"] == "can_submit"
    assert blocked_events[0]["payload"]["order_id"] == order.id
    assert blocked_events[0]["payload"]["broker_id"] == "alpaca"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_live_submit_hard_limit_notional_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-notional", symbol="TEST", quantity=20.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_max_notional_exceeded"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "live_submit_max_notional_exceeded"
    assert blocked_events[0]["payload"]["gate"] == "live_submit_limits"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_live_submit_hard_limit_symbol_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-symbol", symbol="UNAUTHORIZED")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_symbol_not_allowed"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "live_submit_symbol_not_allowed"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_risk_revalidation_failure_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-risk")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=False)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "risk_revalidation_failed"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "risk_revalidation_failed"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_kill_switch_active_before_place_order_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-ks-final")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = MagicMock()
        mock_exec_resolution.execution_broker.place_order = MagicMock()
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        # First check passes, final check fails
        mock_ks.status.side_effect = [
            MagicMock(enabled=False, mode="normal"),
            MagicMock(enabled=True, mode="soft_pause"),
        ]
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "kill_switch_active"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "kill_switch_active"
    assert blocked_events[0]["payload"]["gate"] == "kill_switch"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_mark_submit_requested_failure_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-mutation")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution.mark_submit_requested", side_effect=RuntimeError("disk full")):
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = MagicMock()
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "submit_state_mutation_failed"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "submit_state_mutation_failed"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_order_reconstruction_failure_emits_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-reconstruct-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls, \
         patch("atlas_agent.execution.submit_execution._reconstruct_order", side_effect=RuntimeError("FAKE_SECRET_PAYLOAD {'symbol': 'LEAK'}")):
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = MagicMock()
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "invalid_pending_order"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    event_payload = blocked_events[0]["payload"]
    assert event_payload["reason_code"] == "invalid_pending_order"
    assert event_payload["gate"] == "order_reconstruction"
    assert event_payload["order_id"] == order.id
    payload_str = str(event_payload)
    # Zero live_submit_attempted
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0
    # No payload leaks
    assert "FAKE_SECRET" not in payload_str
    assert "LEAK" not in payload_str
    assert "symbol" not in payload_str.lower()
    assert "traceback" not in payload_str.lower()


def test_resolve_execution_broker_none_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-no-broker")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = None
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "execution_broker_unavailable"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "execution_broker_unavailable"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_mocked_can_submit_true_happy_path_emits_attempted(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-attempted", symbol="TEST", side="buy", quantity=1.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    call_log: list[tuple] = []
    mock_audit = _mock_audit_writer(call_log)

    mock_broker = MagicMock()

    def place_order(*args: Any, **kwargs: Any) -> OrderResult:
        call_log.append(("place_order", args, kwargs))
        return OrderResult(
            accepted=True,
            filled=False,
            order_id="broker-123",
            status="accepted",
            message="ok",
        )

    mock_broker.place_order.side_effect = place_order

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = mock_broker
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is True
    assert report.status == "acknowledged"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 1
    assert attempted_events[0]["payload"]["order_id"] == order.id
    assert attempted_events[0]["payload"]["broker_id"] == "alpaca"
    assert attempted_events[0]["payload"]["status"] == "attempted"
    attempted_markers = [
        i for i, item in enumerate(call_log)
        if item[0] == "audit" and item[1] == "live_submit_attempted"
    ]
    place_order_markers = [
        i for i, item in enumerate(call_log)
        if item[0] == "place_order"
    ]
    assert len(attempted_markers) == 1
    assert len(place_order_markers) == 1
    assert attempted_markers[0] < place_order_markers[0]
    # No blocked events
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 0


def test_broker_rejected_still_emits_attempted(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-rejected", symbol="TEST", side="buy", quantity=1.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    mock_broker = MagicMock()
    mock_broker.place_order.side_effect = BrokerOperationError("broker rejected order")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = mock_broker
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "broker_rejected_order"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 1
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 0


def test_broker_timeout_still_emits_attempted(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-timeout", symbol="TEST", side="buy", quantity=1.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    mock_broker = MagicMock()
    mock_broker.place_order.side_effect = BrokerOperationError("broker transport request failed")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = mock_broker
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "reconciliation_required"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 1
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 0


def test_audit_writer_failure_does_not_change_report(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = MagicMock()
    mock_audit.write_event.side_effect = RuntimeError("audit disk full")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    # write_event was called but raised; no crash propagated
    mock_audit.write_event.assert_called()


def test_invalid_pending_order_audit_failure_does_not_change_report(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-invalid-pending-fail")
    payload = _make_v2_payload(order)
    payload["order"]["quantity"] = 999.0
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = MagicMock()
    mock_audit.write_event.side_effect = RuntimeError("audit disk full")

    report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "invalid_pending_order"
    mock_audit.write_event.assert_called_once()


def test_invalid_client_order_id_audit_failure_does_not_change_report(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-invalid-cid-fail")
    payload = _make_v2_payload(order, client_order_id="../../etc/FAKE_SECRET_CID")
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = MagicMock()
    mock_audit.write_event.side_effect = RuntimeError("audit disk full")

    report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "invalid_client_order_id"
    mock_audit.write_event.assert_called_once()


def test_audit_payload_does_not_contain_secrets(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-payload-safety")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    for event in mock_audit.events:
        payload_str = str(event["payload"])
        assert "SECRET" not in payload_str
        assert "API_KEY" not in payload_str
        assert "password" not in payload_str.lower()
        assert "path" not in payload_str.lower() or "order_id" in payload_str
        # Ensure no raw order dict or broker response
        assert "symbol" not in payload_str.lower()
        assert "quantity" not in payload_str.lower()
        assert "limit_price" not in payload_str.lower()


# ---------------------------------------------------------------------------
# Batch 5.2: Live-submit audit hardening — missing gate coverage
# ---------------------------------------------------------------------------

def test_live_trading_disabled_emits_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-live-off")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    config = FakeConfig()
    config.enable_live_trading = False

    report = run_submit_execution(order.id, config, manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "live_trading_disabled"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "live_trading_disabled"
    assert blocked_events[0]["payload"]["gate"] == "live_trading_enabled"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_kill_switch_active_first_check_emits_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-ks-first")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=True, mode="soft_pause")
        mock_ks_cls.return_value = mock_ks
        report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "kill_switch_active"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "kill_switch_active"
    assert blocked_events[0]["payload"]["gate"] == "kill_switch"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_broker_sync_unavailable_can_sync_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-sync")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=False, can_submit=False)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks
        report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "broker_sync_unavailable"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "broker_sync_unavailable"
    assert blocked_events[0]["payload"]["gate"] == "can_sync"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_broker_sync_unavailable_provider_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-provider")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_resolver.resolve_sync_provider.return_value = MagicMock(sync_provider=None)
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks
        report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "broker_sync_unavailable"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "broker_sync_unavailable"
    assert blocked_events[0]["payload"]["gate"] == "fresh_sync"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_live_sync_failed_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-sync-fail")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([{"operation": "test", "error": "FAKE_BROKER_ERROR_BODY"}], "sync_failed")
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks
        report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "live_sync_failed"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "live_sync_failed"
    assert blocked_events[0]["payload"]["gate"] == "fresh_sync"
    # Payload must not contain raw broker error text
    payload_str = str(blocked_events[0]["payload"])
    assert "FAKE_BROKER_ERROR_BODY" not in payload_str
    assert "traceback" not in payload_str.lower()
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_market_price_unavailable_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-market", order_type="market")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks
        report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "market_price_unavailable"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "market_price_unavailable"
    assert blocked_events[0]["payload"]["gate"] == "market_price"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_live_submit_side_not_allowed_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-side", side="sell")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks
        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "live_submit_side_not_allowed"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "live_submit_side_not_allowed"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


def test_execution_broker_invalid_emits_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-broker-invalid", symbol="TEST", side="buy", quantity=1.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        # execution_broker exists but has no place_order callable
        mock_exec_resolution.execution_broker = object()
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks
        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    assert report.blocked_reason == "execution_broker_invalid"
    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    assert blocked_events[0]["payload"]["reason_code"] == "execution_broker_invalid"
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 0


# ---------------------------------------------------------------------------
# Batch 5.2: Negative tests — these gates must NOT emit live_submit_blocked
# ---------------------------------------------------------------------------

def test_path_traversal_does_not_emit_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    mock_audit = _mock_audit_writer()
    report = run_submit_execution("../../etc/passwd", FakeConfig(), manager, audit_writer=mock_audit)
    assert report.ok is False
    assert report.blocked_reason == "invalid_pending_order_id"
    assert len(mock_audit.events) == 0


def test_pending_order_not_found_does_not_emit_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    mock_audit = _mock_audit_writer()
    report = run_submit_execution("nonexistent-order", FakeConfig(), manager, audit_writer=mock_audit)
    assert report.ok is False
    assert report.blocked_reason == "pending_order_not_found"
    assert len(mock_audit.events) == 0


def test_already_submitted_does_not_emit_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="already-submitted")
    payload = _make_v2_payload(order, status="submitted")
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()
    report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)
    assert report.ok is False
    assert report.blocked_reason == "already_submitted"
    assert len(mock_audit.events) == 0


def test_not_approved_does_not_emit_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="not-approved")
    payload = _make_v2_payload(order, approved=False, status="pending_approval")
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()
    report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)
    assert report.ok is False
    assert report.blocked_reason == "not_approved"
    assert len(mock_audit.events) == 0


def test_approval_expired_does_not_emit_live_submit_blocked(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="expired")
    payload = _make_v2_payload(order)
    payload["expires_at"] = "2020-01-01T00:00:00+00:00"
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()
    report = run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)
    assert report.ok is False
    assert report.blocked_reason == "approval_expired"
    assert len(mock_audit.events) == 0


# ---------------------------------------------------------------------------
# Batch 5.2: Payload safety hardening
# ---------------------------------------------------------------------------

def test_attempted_payload_on_broker_error_contains_no_broker_body(tmp_path: Path) -> None:
    """live_submit_attempted payload must not contain broker response body or exception text."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-attempt-payload", symbol="TEST", side="buy", quantity=1.0, limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    mock_broker = MagicMock()
    mock_broker.place_order.side_effect = BrokerOperationError("broker transport request failed")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = mock_broker
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks
        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, audit_writer=mock_audit)

    assert report.ok is False
    attempted_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_attempted"]
    assert len(attempted_events) == 1
    p = attempted_events[0]["payload"]
    p_str = str(p)
    assert p["status"] == "attempted"
    assert "broker transport" not in p_str
    assert "exception" not in p_str.lower()
    assert "traceback" not in p_str.lower()
    assert "response" not in p_str.lower()
    assert "body" not in p_str.lower()
    assert "FAKE_BROKER" not in p_str
    assert "symbol" not in p_str.lower()
    assert "quantity" not in p_str.lower()
    assert "limit_price" not in p_str.lower()
    assert "APCA" not in p_str
    assert "header" not in p_str.lower()


def test_blocked_payload_contains_only_safe_fields(tmp_path: Path) -> None:
    """live_submit_blocked payload must contain only the safe structured field set."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="audit-safe-payload")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    mock_audit = _mock_audit_writer()

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks
        run_submit_execution(order.id, FakeConfig(), manager, audit_writer=mock_audit)

    blocked_events = [e for e in mock_audit.events if e["event_type"] == "live_submit_blocked"]
    assert len(blocked_events) == 1
    p = blocked_events[0]["payload"]
    allowed_keys = {"mode", "broker_id", "order_id", "client_order_id", "reason_code", "gate", "status"}
    assert set(p.keys()) == allowed_keys
    p_str = str(p)
    assert "symbol" not in p_str.lower()
    assert "quantity" not in p_str.lower()
    assert "limit_price" not in p_str.lower()
    assert "side" not in p_str.lower()
    assert "stop_loss" not in p_str.lower()
    assert "confidence" not in p_str.lower()
    assert "leverage" not in p_str.lower()
    assert "path" not in p_str.lower() or "order_id" in p_str
    assert "pending_orders" not in p_str
    assert str(path) not in p_str
    assert "traceback" not in p_str.lower()
    assert "exception" not in p_str.lower()
    assert "APCA" not in p_str
    assert "api_key" not in p_str.lower()
    assert "secret" not in p_str.lower()


# ---------------------------------------------------------------------------
# Batch 5.19: Safe quote source for market-order live-submit gating
# ---------------------------------------------------------------------------

from atlas_agent.execution.quotes import MarketQuote


def _make_quote(**kwargs) -> MarketQuote:
    defaults = {
        "symbol": "TEST",
        "bid": 99.0,
        "ask": 101.0,
        "timestamp": datetime.now(UTC),
        "source": "test",
    }
    defaults.update(kwargs)
    return MarketQuote(**defaults)


class _FakeQuoteProvider:
    def __init__(self, quote: MarketQuote | None = None, exc: Exception | None = None) -> None:
        self.quote = quote
        self.exc = exc

    def get_quote(self, symbol: str) -> MarketQuote | None:
        if self.exc is not None:
            raise self.exc
        return self.quote


# A. Default market order remains blocked without quote_provider

def test_market_order_blocks_without_quote_provider(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-no-quote", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.blocked_reason == "market_price_unavailable"
    assert report.gates["market_price"] == "fail"


# B. Market buy uses ask for risk revalidation

def test_market_buy_uses_ask_for_risk_revalidation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-buy", order_type="market", limit_price=None, side="buy", quantity=2.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    captured_risk_inputs: list[Any] = []

    def capture_evaluate(risk_input: Any, portfolio: Any, mode: str = "live") -> Any:
        captured_risk_inputs.append(risk_input)
        return RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

    quote_provider = _FakeQuoteProvider(_make_quote(bid=99.0, ask=101.0))

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk = _mock_risk_manager(allowed=True)
        mock_risk.evaluate_order.side_effect = capture_evaluate
        mock_risk_cls.return_value = mock_risk
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    assert report.gates["market_price"] == "pass"
    assert len(captured_risk_inputs) == 1
    risk_input = captured_risk_inputs[0]
    assert risk_input.price == 101.0
    assert risk_input.notional == 202.0


# C. Market sell uses bid for risk revalidation

def test_market_sell_uses_bid_for_risk_revalidation(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-sell", order_type="market", limit_price=None, side="sell", quantity=2.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    captured_risk_inputs: list[Any] = []

    def capture_evaluate(risk_input: Any, portfolio: Any, mode: str = "live") -> Any:
        captured_risk_inputs.append(risk_input)
        return RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

    quote_provider = _FakeQuoteProvider(_make_quote(bid=99.0, ask=101.0))

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk = _mock_risk_manager(allowed=True)
        mock_risk.evaluate_order.side_effect = capture_evaluate
        mock_risk_cls.return_value = mock_risk
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    assert report.gates["market_price"] == "pass"
    assert len(captured_risk_inputs) == 1
    risk_input = captured_risk_inputs[0]
    assert risk_input.price == 99.0
    assert risk_input.notional == 198.0


# D. Quote provider None return blocks

def test_market_order_blocks_when_quote_provider_returns_none(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-none", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    quote_provider = _FakeQuoteProvider(None)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "market_quote_unavailable"
    assert report.gates["market_price"] == "fail"


# E. Quote provider exception blocks safely without leaking raw output

def test_market_order_blocks_safely_when_quote_provider_raises(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-exc", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    quote_provider = _FakeQuoteProvider(
        exc=RuntimeError("Authorization: Bearer abc123 /Users/natan/secret")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "market_quote_unavailable"
    assert report.gates["market_price"] == "fail"
    report_dict = report.to_dict()
    report_str = str(report_dict)
    assert "Authorization:" not in report_str
    assert "Bearer abc123" not in report_str
    assert "/Users/" not in report_str
    assert "secret" not in report_str.lower()


# F. Stale quote blocks

def test_market_order_blocks_when_quote_is_stale(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-stale", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    stale_ts = datetime.now(UTC) - timedelta(seconds=60)
    quote_provider = _FakeQuoteProvider(_make_quote(timestamp=stale_ts))

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "market_quote_stale"
    assert report.gates["market_price"] == "fail"


# G. Symbol mismatch blocks

def test_market_order_blocks_when_quote_symbol_mismatches(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-mismatch", order_type="market", limit_price=None, symbol="AAPL")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    quote_provider = _FakeQuoteProvider(_make_quote(symbol="MSFT"))

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "market_quote_symbol_mismatch"
    assert report.gates["market_price"] == "fail"


# H. Invalid bid/ask blocks

@pytest.mark.parametrize("bid,ask", [
    (0.0, 101.0),
    (-1.0, 101.0),
    (99.0, 0.0),
    (99.0, -1.0),
    (101.0, 99.0),  # ask < bid
    (float("nan"), 101.0),
    (99.0, float("inf")),
])
def test_market_order_blocks_when_quote_bid_ask_invalid(tmp_path: Path, bid: float, ask: float) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-invalid", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    quote_provider = _FakeQuoteProvider(_make_quote(bid=bid, ask=ask))

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "market_quote_invalid"
    assert report.gates["market_price"] == "fail"


# I. Quote-derived notional is used for live-submit hard limits

def test_quote_derived_notional_used_for_live_submit_hard_limits(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-hard-limit", order_type="market", limit_price=None, side="buy", quantity=20.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    quote_provider = _FakeQuoteProvider(_make_quote(bid=99.0, ask=101.0))

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, quote_provider=quote_provider)

    # notional = 20 * 101 = 2020, which exceeds live_submit_max_order_notional=1000
    assert report.ok is False
    assert report.blocked_reason == "live_submit_max_notional_exceeded"
    assert report.gates["live_submit_limits"] == "fail"
    after = path.read_text(encoding="utf-8")
    assert before == after


# J. Valid quote passes market-price gate but still blocks at can_submit false

def test_valid_quote_passes_market_gate_then_blocks_at_can_submit_false(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-then-can-submit", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    quote_provider = _FakeQuoteProvider(_make_quote())

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    assert report.gates["market_price"] == "pass"
    assert report.gates["risk_revalidation"] == "pass"


# K. Valid quote with mocked can_submit true reaches broker boundary

def test_valid_quote_market_order_reaches_broker_boundary(tmp_path: Path) -> None:
    from atlas_agent.execution.order import OrderResult

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-broker", order_type="market", limit_price=None, side="buy", quantity=1.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    quote_provider = _FakeQuoteProvider(_make_quote(bid=99.0, ask=101.0))
    mock_broker = _mock_execution_broker(
        result=OrderResult(accepted=True, filled=False, order_id="b-123", status="new", message="ok")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver = _mock_broker_resolver(can_sync=True, can_submit=True)
        mock_exec_resolution = MagicMock()
        mock_exec_resolution.execution_broker = mock_broker
        mock_resolver.resolve_execution_broker.return_value = mock_exec_resolution
        mock_resolver_cls.return_value = mock_resolver
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfigCanSubmit(), manager, quote_provider=quote_provider)

    assert report.ok is True
    assert report.status == "acknowledged"
    mock_broker.place_order.assert_called_once()


# L. Limit orders unaffected by quote_provider

def test_limit_order_does_not_call_quote_provider(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="limit-no-quote", order_type="limit", limit_price=100.0)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    quote_provider = MagicMock()
    quote_provider.get_quote.side_effect = AssertionError("get_quote must not be called for limit orders")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    assert report.blocked_reason == "can_submit_false"
    quote_provider.get_quote.assert_not_called()


# M. Output safety for quote failure reports

def test_quote_failure_report_contains_no_forbidden_fragments(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="market-safety", order_type="market", limit_price=None)
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    quote_provider = _FakeQuoteProvider(
        exc=RuntimeError("broker.example.com returned {\"Authorization\": \"Bearer SECRET_TOKEN_APCA\"}")
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mock_ks_cls.return_value = mock_ks

        report = run_submit_execution(order.id, FakeConfig(), manager, quote_provider=quote_provider)

    assert report.ok is False
    report_dict = report.to_dict()
    report_str = str(report_dict)
    assert "/Users/" not in report_str
    assert "Authorization:" not in report_str
    assert "Bearer" not in report_str
    assert "APCA" not in report_str
    assert "SECRET" not in report_str
    assert "TOKEN" not in report_str
    assert "broker.example.com" not in report_str
    assert "raw JSON" not in report_str
