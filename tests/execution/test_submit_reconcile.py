from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
from atlas_agent.brokers.base import BrokerOperationError
from atlas_agent.brokers.models import BrokerOrder
from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidPendingOrderError,
    _compute_order_hash,
    _order_to_dict,
)
from atlas_agent.execution.order import Order
from atlas_agent.execution.submit_reconcile import run_reconcile
from atlas_agent.execution.submit_state import SubmitStateError


def _mock_resolution(adapter=None):
    return BrokerResolution(
        execution_broker=None,
        sync_provider=adapter,
        status=MagicMock(),
    )


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
    return Order(**defaults)


def _make_v2_payload(order: Order, **overrides) -> dict:
    from atlas_agent.execution.approval import _compute_approval_hash

    order_dict = _order_to_dict(order)
    now = datetime.now(UTC)
    transitions = [
        {"status": "pending_approval", "at": now.isoformat(), "actor": "system"},
        {"status": "approved", "at": now.isoformat(), "actor": "test"},
    ]
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
        "status_transitions": transitions,
        "submit_attempts": [],
        "broker_order_id": None,
        "client_order_id": None,
        "fill_quantity": 0.0,
        "fill_price": None,
        "submitted_at": None,
    }
    payload["approval_hash"] = _compute_approval_hash(
        order_hash=payload["order_hash"],
        approved=payload["approved"],
        approved_at=payload["approved_at"],
        approval_actor=payload["approval_actor"],
        status=payload["status"],
        status_transitions=transitions,
        expires_at=payload["expires_at"],
    )
    payload.update(overrides)
    # Recompute approval_hash if overrides changed decision fields
    if payload.get("approved") and payload.get("status") == "approved":
        payload["approval_hash"] = _compute_approval_hash(
            order_hash=payload["order_hash"],
            approved=payload["approved"],
            approved_at=payload["approved_at"],
            approval_actor=payload["approval_actor"],
            status=payload["status"],
            status_transitions=payload["status_transitions"],
            expires_at=payload["expires_at"],
        )
    return payload


def _write_payload(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _add_submit_evidence(payload: dict, attempt_status: str = "submit_requested") -> dict:
    """Add a submit_requested transition and matching submit_attempt to payload."""
    import copy
    now = payload.get("created_at", datetime.now(UTC).isoformat())
    cid = payload.get("client_order_id", "atlas-test-cid")
    payload = copy.deepcopy(payload)
    payload["status_transitions"].append({
        "status": "submit_requested",
        "at": now,
        "actor": "submit:cli",
    })
    payload["submit_attempts"] = [{
        "attempt_id": "b1d7ed33-8092-4eca-beed-ddef20ae4319",
        "client_order_id": cid,
        "status": attempt_status,
        "created_at": now,
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    return payload


class FakeConfig:
    enable_live_trading = True
    max_position_size = 10000.0
    max_order_notional = 5000.0
    symbol_allowlist = None
    symbol_blocklist = set()
    require_stop_loss_live = True
    pending_orders_dir = Path("pending_orders")
    live_broker = "alpaca"


# ---------------------------------------------------------------------------
# client_order_id=None
# ---------------------------------------------------------------------------

def test_reconcile_client_order_id_none_returns_not_available(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-cid")
    payload = _make_v2_payload(order)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    report = run_reconcile(order.id, FakeConfig(), manager)
    assert report.ok is False
    assert report.status == "reconcile_not_available"
    assert "No client_order_id is present" in report.message


# ---------------------------------------------------------------------------
# Invalid client_order_id blocks before broker query
# ---------------------------------------------------------------------------

def test_reconcile_invalid_client_order_id_blocks_before_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="bad-cid")
    payload = _make_v2_payload(order, client_order_id="../../etc/passwd")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch.object(AlpacaBrokerAdapter, "get_order_by_client_order_id", side_effect=AssertionError("must not be called")) as mock_get:
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_invalid_client_order_id"
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# enable_live_trading=false blocks before broker query
# ---------------------------------------------------------------------------

def test_reconcile_live_trading_disabled_blocks_before_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="live-off")
    payload = _make_v2_payload(order, client_order_id="atlas-abc123-deadbeef")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    config = FakeConfig()
    config.enable_live_trading = False

    with patch.object(AlpacaBrokerAdapter, "get_order_by_client_order_id", side_effect=AssertionError("must not be called")) as mock_get:
        report = run_reconcile(order.id, config, manager)

    assert report.ok is False
    assert report.status == "reconcile_live_disabled"
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# Tampered file blocks before broker query
# ---------------------------------------------------------------------------

def test_reconcile_tampered_file_blocks_before_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="tampered")
    payload = _make_v2_payload(order, client_order_id="atlas-abc123-deadbeef")
    payload["order_hash"] = "tampered"
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch.object(AlpacaBrokerAdapter, "get_order_by_client_order_id", side_effect=AssertionError("must not be called")) as mock_get:
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_invalid"
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# Broker order found
# ---------------------------------------------------------------------------

def test_reconcile_found_updates_local_state(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="found")
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id="atlas-found-deadbeef", status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-123",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="filled",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.broker_order_id == "broker-123"

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"
    assert loaded["broker_order_id"] == "broker-123"
    assert loaded["broker_status"] == "filled"
    assert "reconciled_at" in loaded
    assert loaded["status_transitions"][-1]["actor"] == "reconcile:cli"
    assert loaded["status_transitions"][-1]["reason"] == "broker_found_during_reconcile"


def test_reconcile_found_stores_broker_order_id_and_status(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="found-details")
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id="atlas-details-deadbeef", status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-456",
        symbol="TEST",
        side="buy",
        quantity=2.0,
        status="partially_filled",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["broker_order_id"] == "broker-456"
    assert loaded["broker_status"] == "partially_filled"
    assert loaded["reconciled_at"] is not None
    assert loaded["submitted_at"] is not None


# ---------------------------------------------------------------------------
# Broker order not found
# ---------------------------------------------------------------------------

def test_reconcile_not_found_does_not_submit(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="not-found")
    payload = _make_v2_payload(order, client_order_id="atlas-notfound-deadbeef")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("order not found")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_not_found"

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "approved"  # unchanged
    assert loaded.get("broker_order_id") is None


def test_reconcile_not_found_from_submit_uncertain_keeps_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="uncertain-notfound")
    payload = _make_v2_payload(
        order,
        client_order_id="atlas-uncertain-deadbeef",
        status="submit_uncertain",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("order not found")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_not_found"
    assert "Manual review required" in report.message

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


# ---------------------------------------------------------------------------
# Transport / malformed response sanitization
# ---------------------------------------------------------------------------

def test_reconcile_transport_failure_sanitized(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="transport-fail")
    payload = _make_v2_payload(order, client_order_id="atlas-transport-deadbeef")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("broker transport request failed")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert "Reconciliation required" in report.message
    # No raw exception text leak
    assert "transport request failed" not in report.message

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


def test_reconcile_malformed_broker_response_sanitized(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed")
    payload = _make_v2_payload(order, client_order_id="atlas-malformed-deadbeef")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("malformed broker response")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert "Reconciliation required" in report.message
    # No raw exception text leak
    assert "malformed" not in report.message.lower()


# ---------------------------------------------------------------------------
# No raw values leak
# ---------------------------------------------------------------------------

def test_reconcile_no_raw_values_leak(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-leak")
    cid = "atlas-noleak-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid)
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("broker transport request failed")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    # Message must not contain raw payload values
    assert cid not in report.message
    assert "TEST" not in report.message
    assert "buy" not in report.message


# ---------------------------------------------------------------------------
# Never calls forbidden functions
# ---------------------------------------------------------------------------

def test_reconcile_never_calls_place_order(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-place")
    payload = _make_v2_payload(order, client_order_id="atlas-noplace-deadbeef")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = BrokerOperationError("order not found")
    with patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place, \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_place.assert_not_called()


def test_reconcile_never_calls_resolve_execution_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-exec-broker")
    payload = _make_v2_payload(order, client_order_id="atlas-noexec-deadbeef")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = BrokerOperationError("order not found")
    with patch.object(BrokerResolver, "resolve_execution_broker", side_effect=AssertionError("resolve_execution_broker must not be called")) as mock_resolve, \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_resolve.assert_not_called()


def test_reconcile_never_calls_order_router_route(tmp_path: Path) -> None:
    from atlas_agent.execution.order_router import OrderRouter

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="no-route")
    payload = _make_v2_payload(order, client_order_id="atlas-noroute-deadbeef")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = BrokerOperationError("order not found")
    with patch.object(OrderRouter, "route", side_effect=AssertionError("OrderRouter.route must not be called")) as mock_route, \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    mock_route.assert_not_called()


# ---------------------------------------------------------------------------
# No duplicate reconcile
# ---------------------------------------------------------------------------

def test_reconcile_duplicate_reconciled_short_circuits_before_broker_query(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="already-reconciled")
    payload = _make_v2_payload(
        order,
        client_order_id="atlas-already-deadbeef",
        status="duplicate_reconciled",
        broker_order_id="broker-789",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = AssertionError("get_order_by_client_order_id must not be called")
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "duplicate_reconciled"
    assert report.broker_order_id == "broker-789"
    assert "already reconciled" in report.message.lower()
    mock_adapter.get_order_by_client_order_id.assert_not_called()


def test_reconcile_duplicate_reconciled_does_not_mutate_file(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="already-reconciled-no-mutate")
    payload = _make_v2_payload(
        order,
        client_order_id="atlas-already-deadbeef",
        status="duplicate_reconciled",
        broker_order_id="broker-789",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_reconcile_duplicate_reconciled_never_calls_place_order(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="already-reconciled-no-place")
    payload = _make_v2_payload(
        order,
        client_order_id="atlas-already-deadbeef",
        status="duplicate_reconciled",
        broker_order_id="broker-789",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    mock_place.assert_not_called()


# ---------------------------------------------------------------------------
# Reuses existing client_order_id
# ---------------------------------------------------------------------------

def test_reconcile_reuses_existing_client_order_id(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="reuse-cid")
    cid = "my-existing-cid-123"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-999",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    mock_adapter.get_order_by_client_order_id.assert_called_once_with(cid)


def test_reconcile_unchanged(tmp_path: Path) -> None:
    """Confirm reconcile behavior transitions post-submit states to acknowledged."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="reconcile-unchanged")
    cid = "reconcile-unchanged-cid"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_uncertain"),
        attempt_status="submit_uncertain",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)
    before = path.read_text(encoding="utf-8")

    broker_order = BrokerOrder(
        order_id="broker-001",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    after = path.read_text(encoding="utf-8")
    assert before != after  # reconcile is allowed to mutate
    loaded = json.loads(after)
    assert loaded["status"] == "acknowledged"


# ---------------------------------------------------------------------------
# Batch 4.7: Reconcile support for submit_requested status
# ---------------------------------------------------------------------------

def test_reconcile_submit_requested_found_becomes_acknowledged(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sr-found")
    cid = "atlas-sr-found-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-sr-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="filled",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.broker_order_id == "broker-sr-111"

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"
    assert loaded["broker_order_id"] == "broker-sr-111"
    assert loaded["status_transitions"][-1]["reason"] == "broker_found_during_reconcile"


def test_reconcile_submit_requested_not_found_marks_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sr-notfound")
    cid = "atlas-sr-nf-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("order not found")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_not_found"
    assert "Manual review required" in report.message

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


def test_reconcile_submit_requested_transport_error_marks_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sr-transport")
    cid = "atlas-sr-tr-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("broker transport request failed")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert "Reconciliation required" in report.message

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


def test_reconcile_submit_requested_never_calls_place_order(tmp_path: Path) -> None:
    from atlas_agent.brokers.alpaca import AlpacaBroker

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sr-no-place")
    cid = "atlas-sr-nop-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = BrokerOrder(
        order_id="broker-sr-222", symbol="TEST", side="buy", quantity=1.0, status="open"
    )
    with patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place, \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    mock_place.assert_not_called()


def test_reconcile_submit_requested_never_calls_resolve_execution_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="sr-no-exec")
    cid = "atlas-sr-noex-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = BrokerOrder(
        order_id="broker-sr-333", symbol="TEST", side="buy", quantity=1.0, status="open"
    )
    with patch.object(BrokerResolver, "resolve_execution_broker", side_effect=AssertionError("must not be called")) as mock_resolve, \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    mock_resolve.assert_not_called()


# ---------------------------------------------------------------------------
# Batch 5.3: Reconcile hardening
# ---------------------------------------------------------------------------

def test_reconcile_submit_uncertain_found_becomes_acknowledged(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="su-found")
    cid = "atlas-su-found-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_uncertain"),
        attempt_status="submit_uncertain",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-su-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="filled",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.broker_order_id == "broker-su-111"

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"
    assert loaded["broker_order_id"] == "broker-su-111"
    assert loaded["status_transitions"][-1]["reason"] == "broker_found_during_reconcile"


def test_reconcile_reconciliation_required_found_becomes_acknowledged(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rr-found")
    cid = "atlas-rr-found-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="reconciliation_required"),
        attempt_status="submit_uncertain",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-rr-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.broker_order_id == "broker-rr-111"

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"
    assert loaded["broker_order_id"] == "broker-rr-111"


def test_reconcile_approved_found_does_not_become_acknowledged(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="approved-found")
    cid = "atlas-approved-found-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="approved")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-approved-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious"
    assert report.broker_order_id is None

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"
    assert loaded["status_transitions"][-1]["reason"] == "broker order found for approved order; manual review required"


def test_reconcile_not_found_from_reconciliation_required_keeps_reconciliation_required(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rr-notfound")
    payload = _make_v2_payload(
        order,
        client_order_id="atlas-rr-nf-deadbeef",
        status="reconciliation_required",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("order not found")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_not_found"
    assert "Manual review required" in report.message

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


def test_reconcile_output_safety_for_acknowledged_path(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="safe-ack")
    cid = "atlas-safe-ack-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-safe-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    # Message must not contain raw payload values
    assert cid not in report.message
    assert "TEST" not in report.message
    assert "buy" not in report.message
    # JSON must not contain raw exception text or secrets
    payload_dict = report.to_dict()
    assert "error" not in payload_dict
    assert cid not in str(payload_dict)


# ---------------------------------------------------------------------------
# Batch 5.3 blocking fixes: submit evidence and mutation safety
# ---------------------------------------------------------------------------

def test_reconcile_approved_then_transport_then_found_must_not_acknowledge(tmp_path: Path) -> None:
    """Approved -> broker transport failure -> reconciliation_required -> broker found must NOT acknowledge."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="approved-then-found")
    cid = "atlas-approved-then-found-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="approved")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    # First reconcile: broker transport error
    exc = BrokerOperationError("broker transport request failed")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report1 = run_reconcile(order.id, FakeConfig(), manager)

    assert report1.ok is False
    assert report1.status == "reconcile_failed"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"

    # Second reconcile: broker found
    broker_order = BrokerOrder(
        order_id="broker-approved-then-found-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )
    mock_adapter2 = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter2.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter2)):
        report2 = run_reconcile(order.id, FakeConfig(), manager)

    assert report2.ok is False
    assert report2.status == "reconcile_suspicious_origin"
    assert "local submit evidence is missing" in report2.message

    loaded2 = json.loads(path.read_text(encoding="utf-8"))
    assert loaded2["status"] == "reconciliation_required"


def test_reconcile_reconciliation_required_no_evidence_must_not_acknowledge(tmp_path: Path) -> None:
    """reconciliation_required with no submit_attempt and no submit_requested transition must NOT acknowledge."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rr-no-evidence")
    cid = "atlas-rr-no-evidence-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-rr-no-evidence-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"
    assert "local submit evidence is missing" in report.message
    assert report.broker_order_id is None

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


def test_reconcile_reconciliation_required_with_submit_attempt_can_acknowledge(tmp_path: Path) -> None:
    """reconciliation_required with matching submit_attempt can acknowledge."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rr-with-attempt")
    cid = "atlas-rr-with-attempt-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="reconciliation_required"),
        attempt_status="submit_uncertain",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-rr-attempt-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"


def test_reconcile_broker_found_mutation_submit_state_error_sanitized(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="mut-ss-error")
    cid = "atlas-mut-ss-error-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-mut-ss-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)), \
         patch("atlas_agent.execution.submit_reconcile.mark_acknowledged_from_reconcile", side_effect=SubmitStateError("bad state")):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_state_update_failed"
    assert "local reconcile state update failed" in report.message
    assert "bad state" not in report.message
    assert "bad state" not in str(report.to_dict())


def test_reconcile_broker_found_mutation_oserror_sanitized(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="mut-os-error")
    cid = "atlas-mut-os-error-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-mut-os-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)), \
         patch("atlas_agent.execution.submit_reconcile.mark_acknowledged_from_reconcile", side_effect=OSError("disk full")):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_state_update_failed"
    assert "local reconcile state update failed" in report.message
    assert "disk full" not in report.message
    assert "disk full" not in str(report.to_dict())


# ---------------------------------------------------------------------------
# Batch 5.3 blocking fixes: submit evidence, mutation safety, broker_order_id sanitization
# ---------------------------------------------------------------------------

def test_reconcile_reconciliation_required_transition_only_not_acknowledged(tmp_path: Path) -> None:
    """reconciliation_required with only a submit_requested transition and NO matching submit_attempt must NOT acknowledge."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="rr-transition-only")
    cid = "atlas-rr-transition-only-deadbeef"
    now = datetime.now(UTC).isoformat()
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    payload["status_transitions"].append({"status": "submit_requested", "at": now, "actor": "submit:cli"})
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-rr-transition-only-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"
    assert "local submit evidence is missing" in report.message

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


def test_reconcile_not_found_mark_reconciliation_raises_oserror_sanitized(tmp_path: Path) -> None:
    """Broker not found + mark_reconciliation_required raises OSError returns sanitized report."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="not-found-oserror")
    cid = "atlas-nf-oserror-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("order not found")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc

    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)), \
         patch("atlas_agent.execution.submit_reconcile._safe_mark_reconciliation_required", return_value=False):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_not_found"
    assert "Manual review required" in report.message
    assert "OSError" not in report.message
    assert "disk full" not in str(report.to_dict())


def test_reconcile_transport_mark_reconciliation_raises_submit_state_error_sanitized(tmp_path: Path) -> None:
    """Broker query failure + mark_reconciliation_required raises SubmitStateError returns sanitized report."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="transport-sserror")
    cid = "atlas-tr-sserror-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    exc = BrokerOperationError("broker transport request failed")
    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = exc

    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)), \
         patch("atlas_agent.execution.submit_reconcile._safe_mark_reconciliation_required", return_value=False):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert "Reconciliation required" in report.message
    assert "SubmitStateError" not in report.message
    assert "bad state" not in str(report.to_dict())


def test_reconcile_unexpected_exception_mark_reconciliation_raises_sanitized(tmp_path: Path) -> None:
    """Unexpected broker exception + mark_reconciliation_required raises returns sanitized report."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="unexpected-raise")
    cid = "atlas-unexpected-raise-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = RuntimeError("something went wrong")

    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)), \
         patch("atlas_agent.execution.submit_reconcile._safe_mark_reconciliation_required", return_value=False):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert "Reconciliation required" in report.message
    assert "RuntimeError" not in report.message
    assert "something went wrong" not in str(report.to_dict())


def test_reconcile_approved_found_no_broker_order_id_leak(tmp_path: Path) -> None:
    """approved + broker found must not leak unvalidated broker_order_id and cannot acknowledge."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="approved-no-leak")
    cid = "atlas-approved-no-leak-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="approved")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-approved-no-leak-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious"
    assert report.broker_order_id is None
    assert "Manual review required" in report.message
    assert cid not in report.message
    assert "TEST" not in report.message

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


def test_reconcile_invalid_broker_order_secret_shaped_broker_order_id_filtered(tmp_path: Path) -> None:
    """Secret-shaped broker_order_id must not appear in report or JSON."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="suspicious-secret")
    cid = "atlas-suspicious-secret-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="FAKE_API_KEY_123",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_invalid_broker_order"
    assert report.broker_order_id is None
    assert "FAKE_API_KEY_123" not in report.message
    assert "FAKE_API_KEY_123" not in str(report.to_dict())


def test_reconcile_duplicate_reconciled_unsafe_broker_order_id_filtered(tmp_path: Path) -> None:
    """Stored unsafe broker_order_id in duplicate_reconciled must not leak."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="dup-secret")
    payload = _make_v2_payload(
        order,
        client_order_id="atlas-dup-secret-deadbeef",
        status="duplicate_reconciled",
        broker_order_id="/etc/passwd",
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "duplicate_reconciled"
    assert report.broker_order_id is None
    assert "/etc/passwd" not in report.message
    assert "/etc/passwd" not in str(report.to_dict())


def test_reconcile_state_update_failed_secret_shaped_broker_order_id_filtered(tmp_path: Path) -> None:
    """Secret-shaped broker_order_id must not leak in reconcile_state_update_failed report."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="state-fail-secret")
    cid = "atlas-state-fail-secret-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-safe-123",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)), \
         patch("atlas_agent.execution.submit_reconcile.mark_acknowledged_from_reconcile", side_effect=OSError("disk full")):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_state_update_failed"
    assert report.broker_order_id is None
    assert "disk full" not in report.message
    assert "disk full" not in str(report.to_dict())


# ---------------------------------------------------------------------------
# Batch 5.3 blocking fixes: strict broker_order_id allowlist
# ---------------------------------------------------------------------------

def test_sanitize_broker_order_id_rejects_path() -> None:
    from atlas_agent.execution.submit_reconcile import _sanitize_broker_order_id
    assert _sanitize_broker_order_id("/Users/name/.config/alpaca") is None


def test_sanitize_broker_order_id_rejects_header_like() -> None:
    from atlas_agent.execution.submit_reconcile import _sanitize_broker_order_id
    assert _sanitize_broker_order_id("Authorization: Bearer abc123") is None


def test_sanitize_broker_order_id_rejects_traversal() -> None:
    from atlas_agent.execution.submit_reconcile import _sanitize_broker_order_id
    assert _sanitize_broker_order_id("../../broker-body") is None


def test_sanitize_broker_order_id_rejects_url() -> None:
    from atlas_agent.execution.submit_reconcile import _sanitize_broker_order_id
    assert _sanitize_broker_order_id("https://example.com/order") is None


def test_sanitize_broker_order_id_rejects_unsafe_characters() -> None:
    from atlas_agent.execution.submit_reconcile import _sanitize_broker_order_id
    assert _sanitize_broker_order_id("has space") is None
    assert _sanitize_broker_order_id("has:colon") is None
    assert _sanitize_broker_order_id("has/slash") is None
    assert _sanitize_broker_order_id("has\\backslash") is None
    assert _sanitize_broker_order_id("has.dot") is None
    assert _sanitize_broker_order_id("has..dots") is None
    assert _sanitize_broker_order_id("has@symbol") is None
    assert _sanitize_broker_order_id("has#hash") is None
    assert _sanitize_broker_order_id("") is None
    assert _sanitize_broker_order_id(None) is None


def test_sanitize_broker_order_id_accepts_safe_values() -> None:
    from atlas_agent.execution.submit_reconcile import _sanitize_broker_order_id
    assert _sanitize_broker_order_id("broker-123") == "broker-123"
    assert _sanitize_broker_order_id("abc123") == "abc123"
    assert _sanitize_broker_order_id("ABC_123-xyz") == "ABC_123-xyz"


# ---------------------------------------------------------------------------
# Batch 5.3 blocking fixes: early operation exception safety
# ---------------------------------------------------------------------------

def test_reconcile_oserror_during_path_exists_returns_sanitized(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="oserror-exists")
    cid = "atlas-oserror-exists-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch.object(Path, "exists", side_effect=OSError("disk full")):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert "Manual review required" in report.message
    assert "disk full" not in report.message
    assert "disk full" not in str(report.to_dict())
    assert report.broker_order_id is None


def test_reconcile_oserror_during_load_pending_returns_sanitized(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="oserror-load")
    cid = "atlas-oserror-load-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_reconcile.load_pending_order", side_effect=OSError("permission denied")):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert "Manual review required" in report.message
    assert "permission denied" not in report.message
    assert "permission denied" not in str(report.to_dict())
    assert report.broker_order_id is None


def test_reconcile_resolver_unexpected_failure_returns_sanitized(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="resolver-fail")
    cid = "atlas-resolver-fail-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    with patch("atlas_agent.execution.submit_reconcile.BrokerResolver", side_effect=RuntimeError("bad config")):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert "Manual review required" in report.message
    assert "RuntimeError" not in report.message
    assert "bad config" not in str(report.to_dict())
    assert report.broker_order_id is None


# ---------------------------------------------------------------------------
# Batch 5.3 blocking fixes: malformed submit_attempt entries
# ---------------------------------------------------------------------------

def test_reconcile_malformed_submit_attempt_missing_client_order_id_not_evidence(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed-missing-cid")
    cid = "atlas-malformed-missing-cid-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    payload["submit_attempts"] = [{
        "attempt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "status": "submit_requested",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-malformed-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"


def test_reconcile_malformed_submit_attempt_bad_actor_not_evidence(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed-bad-actor")
    cid = "atlas-malformed-bad-actor-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    payload["submit_attempts"] = [{
        "attempt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "client_order_id": cid,
        "status": "submit_requested",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "hacker",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-malformed-222",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"


def test_reconcile_malformed_submit_attempt_bad_status_not_evidence(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed-bad-status")
    cid = "atlas-malformed-bad-status-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    payload["submit_attempts"] = [{
        "attempt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "client_order_id": cid,
        "status": "hacked",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-malformed-333",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"


def test_sanitize_broker_order_id_rejects_secret_shaped() -> None:
    from atlas_agent.execution.submit_reconcile import _sanitize_broker_order_id
    assert _sanitize_broker_order_id("FAKE_API_KEY_123") is None
    assert _sanitize_broker_order_id("LEAKED_PASSWORD_999") is None
    assert _sanitize_broker_order_id("SECRET_TOKEN_ABC") is None
    assert _sanitize_broker_order_id("AUTHORIZATION_BEARER_ABC") is None
    assert _sanitize_broker_order_id("APCA_API_KEY_ID") is None
    assert _sanitize_broker_order_id("ALPACA_SECRET_KEY") is None
    assert _sanitize_broker_order_id("MY_CREDENTIAL_123") is None
    assert _sanitize_broker_order_id("PRIVATE_KEY_XYZ") is None


def test_reconcile_malformed_submit_attempt_missing_attempt_id_not_evidence(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed-missing-aid")
    cid = "atlas-malformed-missing-aid-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    payload["submit_attempts"] = [{
        "client_order_id": cid,
        "status": "submit_requested",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-malformed-aid-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"


def test_reconcile_malformed_submit_attempt_missing_created_at_not_evidence(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed-missing-cat")
    cid = "atlas-malformed-missing-cat-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    payload["submit_attempts"] = [{
        "attempt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "client_order_id": cid,
        "status": "submit_requested",
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-malformed-cat-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(mock_adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"


# ---------------------------------------------------------------------------
# Batch 5.8: Broker-neutral reconcile capability
# ---------------------------------------------------------------------------

class FakeCapabilityProvider:
    """A non-Alpaca sync provider that implements the read-only lookup capability."""
    def __init__(self, lookup_result=None, side_effect=None):
        self._lookup_result = lookup_result
        self._side_effect = side_effect
        self.get_order_by_client_order_id_call_count = 0
        self.last_cid = None

    def get_order_by_client_order_id(self, client_order_id: str):
        self.get_order_by_client_order_id_call_count += 1
        self.last_cid = client_order_id
        if self._side_effect is not None:
            raise self._side_effect
        return self._lookup_result


class FakeNoCapabilityProvider:
    """A sync provider with no lookup capability."""
    pass


class FakeNonCallableCapabilityProvider:
    """A sync provider with a non-callable lookup attribute."""
    get_order_by_client_order_id = "not-callable"


class FakeCapabilityProviderWithPlaceOrder(FakeCapabilityProvider):
    """A capability provider that also has place_order (must never be called)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.place_order = MagicMock(side_effect=AssertionError("place_order must not be called"))


# A. Capability-based provider accepted
def test_reconcile_capability_provider_accepted(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-accepted")
    cid = "atlas-cap-accepted-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-cap-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="filled",
    )
    fake = FakeCapabilityProvider(lookup_result=broker_order)
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.broker_order_id == "broker-cap-111"
    assert fake.get_order_by_client_order_id_call_count == 1
    assert fake.last_cid == cid

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"


# B. Provider without capability is rejected safely
def test_reconcile_provider_without_capability_rejected_safely(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-missing")
    cid = "atlas-cap-missing-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    fake = FakeNoCapabilityProvider()
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_no_provider"
    assert report.message == "Broker reconciliation provider is not available."
    assert report.broker_order_id is None
    # No raw provider repr or path leak
    assert "FakeNoCapabilityProvider" not in report.message
    assert "object at 0x" not in str(report.to_dict())


# C. Capability method not callable is rejected safely
def test_reconcile_noncallable_capability_rejected_safely(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-noncallable")
    cid = "atlas-cap-noncallable-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    fake = FakeNonCallableCapabilityProvider()
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_no_provider"
    assert report.message == "Broker reconciliation provider is not available."
    assert report.broker_order_id is None
    assert "not-callable" not in report.message


# D. Capability provider never submits
def test_reconcile_capability_provider_never_submits(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-no-submit")
    cid = "atlas-cap-no-submit-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-cap-ns-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )
    fake = FakeCapabilityProviderWithPlaceOrder(lookup_result=broker_order)
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert fake.get_order_by_client_order_id_call_count == 1
    fake.place_order.assert_not_called()


# E. Reconcile never calls resolve_execution_broker("live")
def test_reconcile_capability_provider_never_resolves_execution_broker(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-no-exec")
    cid = "atlas-cap-no-exec-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-cap-ne-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )
    fake = FakeCapabilityProvider(lookup_result=broker_order)
    with patch.object(BrokerResolver, "resolve_execution_broker", side_effect=AssertionError("resolve_execution_broker must not be called")) as mock_resolve, \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    mock_resolve.assert_not_called()


# F. Broker lookup failure from capability provider is sanitized
def test_reconcile_capability_provider_lookup_failure_sanitized(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-unsafe-fail")
    cid = "atlas-cap-unsafe-fail-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    unsafe_msg = (
        "https://broker.example.com/orders/raw-body "
        "Authorization: Bearer abc123 "
        '{"account_id":"ACCT_SECRET","secret":"abc"}'
    )
    fake = FakeCapabilityProvider(side_effect=BrokerOperationError(unsafe_msg))
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_failed"
    assert fake.get_order_by_client_order_id_call_count == 1
    d = report.to_dict()
    assert "broker.example.com" not in d.get("message", "")
    assert "Authorization:" not in d.get("message", "")
    assert "Bearer abc123" not in d.get("message", "")
    assert "ACCT_SECRET" not in d.get("message", "")
    assert '"secret"' not in str(d)
    assert "/Users/" not in str(d)
    assert "/private/var/" not in str(d)


# G. Approved-origin broker found remains suspicious
def test_reconcile_capability_provider_approved_found_remains_suspicious(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-approved-suspicious")
    cid = "atlas-cap-approved-suspicious-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="approved")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-cap-as-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )
    fake = FakeCapabilityProvider(lookup_result=broker_order)
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious"
    assert report.broker_order_id is None
    assert "Manual review required" in report.message
    assert fake.get_order_by_client_order_id_call_count == 1

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


# H. Missing submit evidence still blocks acknowledge
def test_reconcile_capability_provider_missing_evidence_blocks_acknowledge(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-missing-evidence")
    cid = "atlas-cap-missing-evidence-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-cap-me-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )
    fake = FakeCapabilityProvider(lookup_result=broker_order)
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"
    assert report.broker_order_id is None
    assert "local submit evidence is missing" in report.message
    assert fake.get_order_by_client_order_id_call_count == 1

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


# I. Malformed submit evidence still blocks acknowledge
def test_reconcile_capability_provider_malformed_evidence_blocks_acknowledge(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-malformed-evidence")
    cid = "atlas-cap-malformed-evidence-deadbeef"
    payload = _make_v2_payload(order, client_order_id=cid, status="reconciliation_required")
    # Malformed: attempt_id is not a valid UUID4
    payload["submit_attempts"] = [{
        "attempt_id": "not-a-uuid",
        "client_order_id": cid,
        "status": "submit_requested",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-cap-mfe-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )
    fake = FakeCapabilityProvider(lookup_result=broker_order)
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(fake)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is False
    assert report.status == "reconcile_suspicious_origin"
    assert report.broker_order_id is None
    assert fake.get_order_by_client_order_id_call_count == 1

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"


# J. Existing Alpaca path still works through capability
def test_reconcile_alpaca_adapter_still_works_through_capability(tmp_path: Path) -> None:
    """AlpacaBrokerAdapter passes the capability check, not isinstance."""
    from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
    from atlas_agent.execution.submit_reconcile import _get_reconcile_lookup

    adapter = MagicMock(spec=AlpacaBrokerAdapter)
    lookup = _get_reconcile_lookup(adapter)
    assert lookup is not None
    assert callable(lookup)

    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="cap-alpaca-works")
    cid = "atlas-cap-alpaca-works-deadbeef"
    payload = _add_submit_evidence(
        _make_v2_payload(order, client_order_id=cid, status="submit_requested")
    )
    path = manager.path_for(order.id)
    _write_payload(path, payload)

    broker_order = BrokerOrder(
        order_id="broker-alpaca-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="filled",
    )
    adapter.get_order_by_client_order_id.return_value = broker_order
    with patch.object(BrokerResolver, "resolve_sync_provider", return_value=_mock_resolution(adapter)):
        report = run_reconcile(order.id, FakeConfig(), manager)

    assert report.ok is True
    assert report.status == "acknowledged"
    assert report.broker_order_id == "broker-alpaca-111"
    adapter.get_order_by_client_order_id.assert_called_once_with(cid)
