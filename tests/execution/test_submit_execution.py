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


class FakeConfig:
    enable_live_trading = True
    max_position_size = 10000.0
    max_order_notional = 5000.0
    symbol_allowlist = None
    symbol_blocklist = set()
    require_stop_loss_live = True
    pending_orders_dir = Path("pending_orders")
    live_broker = "alpaca"
    memory_dir = Path("memory")


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
