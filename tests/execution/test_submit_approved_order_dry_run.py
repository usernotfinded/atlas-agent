from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas_agent.execution.approval import ApprovalManager, _compute_order_hash, _order_to_dict
from atlas_agent.execution.order import Order
from atlas_agent.execution.submit_dry_run import run_submit_dry_run, DryRunReport


def _make_order(**kwargs) -> Order:
    defaults = {
        "symbol": "TEST-SYMBOL",
        "side": "buy",
        "quantity": 1.0,
        "limit_price": 100.0,
        "confidence": 1.0,
        "stop_loss": 95.0,
    }
    defaults.update(kwargs)
    return Order(**defaults)


def _valid_v2_payload(manager: ApprovalManager, order: Order) -> dict:
    path = manager.create_pending_order(order)
    return json.loads(path.read_text(encoding="utf-8"))


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
    mock_resolution.sync_provider = MagicMock()

    mock_resolver = MagicMock()
    mock_resolver.resolve_status.return_value = mock_status
    mock_resolver.resolve_sync_provider.return_value = mock_resolution
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
    from atlas_agent.risk.models import RiskDecision

    mock_decision = RiskDecision(
        allowed=allowed,
        status="requires_approval" if allowed else "blocked",
        reason="All risk checks passed" if allowed else "Risk violations detected",
        violations=[],
        classification="opens_new_position",
    )
    mock_manager = MagicMock()
    mock_manager.evaluate_order.return_value = mock_decision
    return mock_manager


class FakeConfig:
    enable_live_trading = True
    max_position_size = 10000.0
    max_order_notional = 5000.0
    symbol_allowlist = None
    symbol_blocklist = set()
    require_stop_loss_live = True
    pending_orders_dir = Path("pending_orders")


# ---------------------------------------------------------------------------
# Gate tests
# ---------------------------------------------------------------------------

def test_dry_run_path_traversal_rejected(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    report = run_submit_dry_run("../secret", FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["path_traversal"] == "fail"


def test_dry_run_missing_file(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    report = run_submit_dry_run("nonexistent-order", FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["pending_file"] == "fail"


def test_dry_run_malformed_json(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed")
    path = manager.path_for(order.id)
    path.write_text("not valid json {{{", encoding="utf-8")
    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["integrity"] == "fail"


def test_dry_run_unapproved_order(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    manager.create_pending_order(order)
    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["approved"] == "fail"


def test_dry_run_expired_order(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="expired")
    payload = _valid_v2_payload(manager, order)
    payload["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["not_expired"] == "fail"


def test_dry_run_client_order_id_present(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="has-client-id")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    payload["client_order_id"] = "already-set"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["idempotency"] == "fail"
    assert report.blocked_reason == "client_order_id_already_present"


def test_dry_run_broker_order_id_present(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="has-broker-id")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    payload["broker_order_id"] = "already-set"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["no_broker_order_id"] == "fail"


def test_dry_run_submit_attempts_present(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="has-attempts")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    payload["submit_attempts"] = [{"at": datetime.now(UTC).isoformat()}]
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["no_submit_attempts"] == "fail"


def test_dry_run_live_trading_disabled(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="live-disabled")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    config = FakeConfig()
    config.enable_live_trading = False
    report = run_submit_dry_run(order.id, config, manager)
    assert report.ok is False
    assert report.gates["live_trading_enabled"] == "fail"


def test_dry_run_can_sync_false_blocks(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-sync")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_cls:
        mock_cls.return_value = _mock_broker_resolver(can_sync=False)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.gates["can_sync"] == "fail"
    assert report.blocked_reason == "broker sync unavailable"


def test_dry_run_can_submit_false_does_not_block(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cant-submit")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.gates["can_submit"] == "fail_expected"
    assert report.status == "dry_run_ready"


def test_dry_run_sync_critical_failure_blocks(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sync-fail")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = (
            [],
            {
                "status": "error",
                "errors": ["live broker sync failed: sync_account_state"],
                "diagnostics": {"failed_operations": ["sync_account_state"]},
            },
        )
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.gates["fresh_sync"] == "fail"


def test_dry_run_sync_balances_warning_proceeds(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sync-balance-warn")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = (
            [{"operation": "sync_balances", "code": "broker_operation_failed", "broker": "alpaca"}],
            None,
        )
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.gates["fresh_sync"] == "pass"
    assert any("sync_balances" in w for w in report.warnings)


def test_dry_run_risk_rejection_blocks(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="risk-fail")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=False)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.gates["risk_revalidation"] == "fail"
    assert report.blocked_reason == "blocked_by_risk_revalidation"


def test_dry_run_happy_path(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="happy")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "dry_run_ready"
    assert report.gates["pending_file"] == "pass"
    assert report.gates["integrity"] == "pass"
    assert report.gates["approved"] == "pass"
    assert report.gates["not_expired"] == "pass"
    assert report.gates["idempotency"] == "pass"
    assert report.gates["no_broker_order_id"] == "pass"
    assert report.gates["no_submit_attempts"] == "pass"
    assert report.gates["live_trading_enabled"] == "pass"
    assert report.gates["can_sync"] == "pass"
    assert report.gates["can_submit"] == "fail_expected"
    assert report.gates["fresh_sync"] == "pass"
    assert report.gates["risk_revalidation"] == "pass"
    assert report.message == "Dry-run passed. Live submit remains disabled."
    assert report.risk is not None
    assert report.sync is not None


def test_dry_run_does_not_modify_pending_file(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-mutate")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        run_submit_dry_run(order.id, FakeConfig(), manager)

    after = path.read_text(encoding="utf-8")
    assert before == after


def test_dry_run_tampered_hash_blocks(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="tampered")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    payload["order"]["quantity"] = 999.0
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["integrity"] == "fail"


def test_dry_run_invalid_order_fields_blocks(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="invalid-fields")
    order_dict = _order_to_dict(order)
    del order_dict["side"]
    payload = {
        "schema_version": "2",
        "order": order_dict,
        "approved": True,
        "created_at": datetime.now(UTC).isoformat(),
        "approved_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        "approval_actor": "test",
        "order_hash": _compute_order_hash(order_dict),
        "status": "approved",
        "status_transitions": [{"status": "approved", "at": datetime.now(UTC).isoformat(), "actor": "test"}],
        "submit_attempts": [],
        "broker_order_id": None,
        "client_order_id": None,
        "fill_quantity": 0.0,
        "fill_price": None,
        "submitted_at": None,
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["integrity"] == "fail"


def test_dry_run_report_to_dict_is_safe(tmp_path: Path) -> None:
    report = DryRunReport(
        ok=False,
        status="blocked",
        order_id="test-id",
        gates={"pending_file": "fail"},
        blocked_reason="pending order not found",
        message="Pending order not found.",
    )
    d = report.to_dict()
    assert d["ok"] is False
    assert d["status"] == "blocked"
    assert "order_id" in d
    assert "gates" in d


def test_dry_run_still_does_not_call_place_order(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker
    from unittest.mock import patch

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="guard-place")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls, \
         patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    mock_place.assert_not_called()


# ---------------------------------------------------------------------------
# Negative guard tests — dry-run must never call mutation helpers
# ---------------------------------------------------------------------------

def test_dry_run_never_calls_manager_create_pending_order(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="guard-create")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls, \
         patch.object(manager, "create_pending_order", side_effect=AssertionError("create_pending_order must not be called")) as mock_create:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    mock_create.assert_not_called()


def test_dry_run_never_calls_manager_approve(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="guard-approve")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls, \
         patch.object(manager, "approve", side_effect=AssertionError("approve must not be called")) as mock_approve:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    mock_approve.assert_not_called()


def test_dry_run_never_calls_order_router_route(tmp_path: Path) -> None:
    from atlas_agent.execution.order_router import OrderRouter

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="guard-route")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls, \
         patch.object(OrderRouter, "route", side_effect=AssertionError("OrderRouter.route must not be called")) as mock_route:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    mock_route.assert_not_called()


# ---------------------------------------------------------------------------
# Batch 4.4 dry-run preview + idempotency gates
# ---------------------------------------------------------------------------

def test_dry_run_includes_client_order_id_preview(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="preview-cid")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.client_order_id_preview is not None
    assert report.client_order_id_preview.startswith("atlas-")


def test_dry_run_does_not_persist_client_order_id(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-persist-cid")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        run_submit_dry_run(order.id, FakeConfig(), manager)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.get("client_order_id") is None


def test_dry_run_blocks_submit_uncertain(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="uncertain")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "submit_uncertain"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["idempotency"] == "fail"
    assert report.blocked_reason == "reconciliation_required"
    assert "Run --reconcile first" in report.message


def test_dry_run_blocks_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="recon-req")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "reconciliation_required"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    report = run_submit_dry_run(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.gates["idempotency"] == "fail"
    assert report.blocked_reason == "reconciliation_required"
    assert "Run --reconcile first" in report.message


def test_dry_run_does_not_call_get_order_by_client_order_id(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-get-order")
    payload = _valid_v2_payload(manager, order)
    payload["approved"] = True
    payload["status"] = "approved"
    payload["approved_at"] = datetime.now(UTC).isoformat()
    payload["approval_actor"] = "test"
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mock_risk_cls, \
         patch.object(AlpacaBrokerAdapter, "get_order_by_client_order_id", side_effect=AssertionError("must not be called")) as mock_get:
        mock_resolver_cls.return_value = _mock_broker_resolver(can_sync=True, can_submit=False)
        mock_sync_cls.return_value = _mock_sync_service()
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = _mock_risk_manager(allowed=True)
        report = run_submit_dry_run(order.id, FakeConfig(), manager)

    assert report.ok is True
    mock_get.assert_not_called()
