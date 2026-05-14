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
    payload = _make_v2_payload(order, client_order_id="atlas-found-deadbeef")
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
    assert report.status == "duplicate_reconciled"
    assert report.broker_order_id == "broker-123"

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "duplicate_reconciled"
    assert loaded["broker_order_id"] == "broker-123"
    assert loaded["broker_status"] == "filled"
    assert "reconciled_at" in loaded
    assert loaded["status_transitions"][-1]["actor"] == "reconcile:cli"


def test_reconcile_found_stores_broker_order_id_and_status(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="found-details")
    payload = _make_v2_payload(order, client_order_id="atlas-details-deadbeef")
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
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["broker_order_id"] == "broker-456"
    assert loaded["broker_status"] == "partially_filled"
    assert loaded["reconciled_at"] is not None


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
    payload = _make_v2_payload(order, client_order_id=cid)
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
    mock_adapter.get_order_by_client_order_id.assert_called_once_with(cid)


def test_reconcile_unchanged(tmp_path: Path) -> None:
    """Confirm reconcile behavior is unchanged after Batch 4.6 helper additions."""
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="reconcile-unchanged")
    cid = "reconcile-unchanged-cid"
    payload = _make_v2_payload(order, client_order_id=cid, status="submit_uncertain")
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
    assert loaded["status"] == "duplicate_reconciled"
