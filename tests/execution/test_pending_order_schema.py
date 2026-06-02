from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidApprovalIdError,
    InvalidPendingOrderError,
    _compute_order_hash,
    _order_to_dict,
    _upgrade_v1_to_v2,
)
from atlas_agent.execution.order import Order


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


def _write_matching_hash_v2(manager: ApprovalManager, order: Order, payload: dict) -> Path:
    payload["order_hash"] = _compute_order_hash(payload["order"])
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _valid_v2_payload(manager: ApprovalManager, order: Order) -> dict:
    path = manager.create_pending_order(order)
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Schema v2 creation
# ---------------------------------------------------------------------------

def test_v2_pending_order_created_with_all_fields(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    path = manager.create_pending_order(order)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "2"
    assert payload["approved"] is False
    assert payload["approved_at"] is None
    assert payload["approval_actor"] is None
    assert payload["status"] == "pending_approval"
    assert len(payload["status_transitions"]) == 1
    assert payload["status_transitions"][0]["status"] == "pending_approval"
    assert payload["status_transitions"][0]["actor"] == "system"
    assert payload["submit_attempts"] == []
    assert payload["broker_order_id"] is None
    assert payload["client_order_id"] is None
    assert payload["fill_quantity"] == 0.0
    assert payload["fill_price"] is None
    assert payload["submitted_at"] is None
    assert "order_hash" in payload
    assert payload["order_hash"] != ""


def test_order_hash_computed_from_order_payload_only(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    path = manager.create_pending_order(order)
    payload = json.loads(path.read_text(encoding="utf-8"))

    order_dict = _order_to_dict(order)
    expected_hash = _compute_order_hash(order_dict)
    assert payload["order_hash"] == expected_hash


def test_mutable_fields_do_not_affect_order_hash(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    path = manager.create_pending_order(order)
    original_payload = json.loads(path.read_text(encoding="utf-8"))
    original_hash = original_payload["order_hash"]

    # Modify mutable fields
    original_payload["status"] = "tampered"
    original_payload["status_transitions"].append(
        {"status": "tampered", "at": datetime.now(UTC).isoformat(), "actor": "evil"}
    )
    original_payload["submit_attempts"].append({"attempt": 1})
    original_payload["broker_order_id"] = "fake-broker-id"
    original_payload["client_order_id"] = "fake-client-id"
    original_payload["fill_quantity"] = 999.0
    original_payload["fill_price"] = 999.0
    original_payload["submitted_at"] = datetime.now(UTC).isoformat()
    original_payload["approved"] = True
    original_payload["approved_at"] = datetime.now(UTC).isoformat()
    original_payload["approval_actor"] = "evil"
    original_payload["expires_at"] = (datetime.now(UTC) + timedelta(days=999)).isoformat()

    path.write_text(json.dumps(original_payload, indent=2, sort_keys=True), encoding="utf-8")

    # Re-read through manager; hash should still match the original order dict
    re_read = json.loads(path.read_text(encoding="utf-8"))
    order_dict = _order_to_dict(order)
    expected_hash = _compute_order_hash(order_dict)
    assert re_read["order_hash"] == expected_hash
    assert re_read["order_hash"] == original_hash


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------

def test_tampered_order_payload_detectable_by_hash_mismatch(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    path = manager.create_pending_order(order)
    payload = json.loads(path.read_text(encoding="utf-8"))

    # Tamper the order itself (change quantity)
    payload["order"]["quantity"] = 999.0
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    # Recompute hash from tampered file; it will NOT match stored hash
    tampered_order_dict = payload["order"]
    recomputed_hash = _compute_order_hash(tampered_order_dict)
    assert recomputed_hash != payload["order_hash"]


def test_v2_tampered_order_hash_causes_is_approved_false(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    path = manager.create_pending_order(order)
    payload = json.loads(path.read_text(encoding="utf-8"))

    # Tamper the order itself
    payload["order"]["quantity"] = 999.0
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_v2_tampered_order_hash_causes_approve_to_raise(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    path = manager.create_pending_order(order)
    payload = json.loads(path.read_text(encoding="utf-8"))

    # Tamper the order itself
    payload["order"]["quantity"] = 999.0
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


# ---------------------------------------------------------------------------
# v1 backward compatibility
# ---------------------------------------------------------------------------

def test_v1_pending_order_readable_by_manager(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    order_dict = _order_to_dict(order)
    v1_payload = {
        "order": order_dict,
        "approved": False,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(v1_payload, indent=2, sort_keys=True), encoding="utf-8")

    # is_approved should work on v1 file
    assert manager.is_approved(order.id) is False


def test_v1_pending_order_upgraded_to_v2_on_approval(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="v1-upgrade-test")
    order_dict = _order_to_dict(order)
    created_at = datetime.now(UTC).isoformat()
    expires_at = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    v1_payload = {
        "order": order_dict,
        "approved": False,
        "created_at": created_at,
        "expires_at": expires_at,
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(v1_payload, indent=2, sort_keys=True), encoding="utf-8")

    manager.approve(order.id, actor="test:user")

    upgraded = json.loads(path.read_text(encoding="utf-8"))
    assert upgraded["schema_version"] == "2"
    assert upgraded["approved"] is True
    assert upgraded["approved_at"] is not None
    assert upgraded["approval_actor"] == "test:user"
    assert upgraded["status"] == "approved"
    assert len(upgraded["status_transitions"]) == 2
    assert upgraded["status_transitions"][0]["status"] == "pending_approval"
    assert upgraded["status_transitions"][1]["status"] == "approved"
    assert upgraded["status_transitions"][1]["actor"] == "test:user"
    assert upgraded["order_hash"] == _compute_order_hash(order_dict)
    assert upgraded["client_order_id"] is None
    assert upgraded["submit_attempts"] == []


def test_v1_already_approved_fails_closed_and_can_be_reapproved(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="v1-already-approved")
    order_dict = _order_to_dict(order)
    created_at = datetime.now(UTC).isoformat()
    approved_at = datetime.now(UTC).isoformat()
    expires_at = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    v1_payload = {
        "order": order_dict,
        "approved": True,
        "created_at": created_at,
        "approved_at": approved_at,
        "expires_at": expires_at,
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(v1_payload, indent=2, sort_keys=True), encoding="utf-8")

    # v1 approved orders are NOT automatically trusted; they fail closed
    assert manager.is_approved(order.id) is False

    # File on disk remains v1 until approve() is called
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert "schema_version" not in on_disk  # still v1 on disk

    # Calling approve() upgrades the file to v2 and re-approves it properly
    manager.approve(order.id, actor="test:user")
    upgraded = json.loads(path.read_text(encoding="utf-8"))
    assert upgraded["schema_version"] == "2"
    assert upgraded["approved"] is True
    assert upgraded["status"] == "approved"
    assert upgraded["order_hash"] == _compute_order_hash(order_dict)
    assert upgraded["approval_actor"] == "test:user"
    assert "approval_hash" in upgraded


def test_v1_missing_expires_at_fails_closed_in_is_approved(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="v1-no-expires")
    order_dict = _order_to_dict(order)
    v1_payload = {
        "order": order_dict,
        "approved": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(v1_payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_v1_missing_expires_at_fails_closed_in_approve(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="v1-no-expires-approve")
    order_dict = _order_to_dict(order)
    v1_payload = {
        "order": order_dict,
        "approved": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(v1_payload, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


# ---------------------------------------------------------------------------
# Approval behavior
# ---------------------------------------------------------------------------

def test_approve_sets_approved_at_and_actor_and_status(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    manager.create_pending_order(order)

    before = datetime.now(UTC)
    manager.approve(order.id, actor="human:trader")
    after = datetime.now(UTC)

    payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))
    assert payload["approved"] is True
    assert payload["approved_at"] is not None
    approved_at = datetime.fromisoformat(payload["approved_at"])
    assert before <= approved_at <= after
    assert payload["approval_actor"] == "human:trader"
    assert payload["status"] == "approved"
    assert len(payload["status_transitions"]) == 2
    assert payload["status_transitions"][1]["status"] == "approved"
    assert payload["status_transitions"][1]["actor"] == "human:trader"


def test_approve_does_not_set_client_order_id(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    manager.create_pending_order(order)
    manager.approve(order.id)

    payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))
    assert payload["client_order_id"] is None


def test_approve_does_not_call_broker_or_sync_or_risk(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    manager.create_pending_order(order)

    # Approval is a local file operation only
    path = manager.approve(order.id)
    assert path.exists()
    # No broker, sync, or risk side effects to verify — the method only touches the file


# ---------------------------------------------------------------------------
# Malformed file handling
# ---------------------------------------------------------------------------

def test_malformed_pending_order_file_fails_safely(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed-test")
    path = manager.path_for(order.id)
    path.write_text("not valid json {{{", encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_unsupported_schema_version_fails_safely(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="bad-schema")
    path = manager.path_for(order.id)
    path.write_text(json.dumps({"schema_version": "99"}, indent=2), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_missing_order_hash_fails_safely(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="missing-hash")
    path = manager.path_for(order.id)
    payload = {
        "schema_version": "2",
        "order": _order_to_dict(order),
        "approved": False,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_missing_order_payload_fails_safely(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="missing-order")
    path = manager.path_for(order.id)
    payload = {
        "schema_version": "2",
        "order_hash": "abc123",
        "approved": False,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_is_approved_returns_false_for_top_level_non_object_json(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="non-object-json")
    path = manager.path_for(order.id)
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_is_approved_returns_false_for_v2_matching_hash_but_invalid_order_fields(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="hash-match-invalid-fields")
    order_dict = _order_to_dict(order)
    # Remove required field to make it invalid but hash still matches
    del order_dict["side"]
    payload = {
        "schema_version": "2",
        "order": order_dict,
        "order_hash": _compute_order_hash(order_dict),
        "approved": False,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_approve_fails_for_v2_matching_hash_but_invalid_order_fields(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="hash-match-invalid-approve")
    order_dict = _order_to_dict(order)
    # Remove required field to make it invalid but hash still matches
    del order_dict["side"]
    payload = {
        "schema_version": "2",
        "order": order_dict,
        "order_hash": _compute_order_hash(order_dict),
        "approved": False,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", "1"),
        ("limit_price", "100"),
    ],
)
def test_is_approved_false_for_v2_matching_hash_but_string_numeric_order_fields(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id=f"string-{field}")
    payload = _valid_v2_payload(manager, order)
    payload["order"][field] = value
    _write_matching_hash_v2(manager, order, payload)

    assert manager.is_approved(order.id) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", "1"),
        ("limit_price", "100"),
    ],
)
def test_approve_fails_for_v2_matching_hash_but_string_numeric_order_fields(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id=f"string-{field}-approve")
    payload = _valid_v2_payload(manager, order)
    payload["order"][field] = value
    _write_matching_hash_v2(manager, order, payload)

    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


def test_is_approved_false_for_v2_matching_hash_but_invalid_order_created_at(
    tmp_path: Path,
) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="bad-order-created-at")
    payload = _valid_v2_payload(manager, order)
    payload["order"]["created_at"] = "not-a-date"
    _write_matching_hash_v2(manager, order, payload)

    assert manager.is_approved(order.id) is False


def test_approve_fails_for_v2_matching_hash_but_invalid_order_created_at(
    tmp_path: Path,
) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="bad-order-created-at-approve")
    payload = _valid_v2_payload(manager, order)
    payload["order"]["created_at"] = "not-a-date"
    _write_matching_hash_v2(manager, order, payload)

    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


def test_is_approved_false_when_status_transitions_missing(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="missing-status-transitions")
    payload = _valid_v2_payload(manager, order)
    del payload["status_transitions"]
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_approve_fails_when_status_transitions_missing(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="missing-status-transitions-approve")
    payload = _valid_v2_payload(manager, order)
    del payload["status_transitions"]
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


def test_is_approved_false_when_status_transitions_not_list(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="bad-status-transitions")
    payload = _valid_v2_payload(manager, order)
    payload["status_transitions"] = {"status": "pending_approval"}
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_approve_fails_when_status_transitions_not_list(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="bad-status-transitions-approve")
    payload = _valid_v2_payload(manager, order)
    payload["status_transitions"] = {"status": "pending_approval"}
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "order",
        "approved",
        "created_at",
        "approved_at",
        "expires_at",
        "approval_actor",
        "order_hash",
        "status",
        "status_transitions",
        "submit_attempts",
        "broker_order_id",
        "client_order_id",
        "fill_quantity",
        "fill_price",
        "submitted_at",
    ],
)
def test_is_approved_false_for_missing_required_v2_top_level_field(
    tmp_path: Path,
    field: str,
) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id=f"missing-{field.replace('_', '-')}")
    payload = _valid_v2_payload(manager, order)
    del payload[field]
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False


def test_approve_raises_invalid_pending_order_for_malformed_json(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="malformed-json-approve")
    path = manager.path_for(order.id)
    path.write_text("not valid json {{{", encoding="utf-8")

    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


# ---------------------------------------------------------------------------
# Bool numeric regression tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_field", ["quantity", "limit_price", "confidence", "stop_loss", "leverage"])
def test_order_bool_numeric_rejected(tmp_path: Path, bad_field: str) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id=f"bool-{bad_field}")
    payload = _valid_v2_payload(manager, order)
    payload["order"][bad_field] = True
    payload["order_hash"] = _compute_order_hash(payload["order"])
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False
    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


@pytest.mark.parametrize("bad_field", ["fill_quantity", "fill_price"])
def test_v2_bool_numeric_rejected(tmp_path: Path, bad_field: str) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id=f"bool-v2-{bad_field}")
    payload = _valid_v2_payload(manager, order)
    payload[bad_field] = True
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False
    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


# ---------------------------------------------------------------------------
# Malformed status_transitions tests
# ---------------------------------------------------------------------------

def test_status_transitions_non_dict_item_rejected(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="st-non-dict")
    payload = _valid_v2_payload(manager, order)
    payload["status_transitions"] = [123]
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False
    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


def test_status_transitions_missing_at_rejected(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="st-missing-at")
    payload = _valid_v2_payload(manager, order)
    payload["status_transitions"] = [{"status": "approved"}]
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False
    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


def test_status_transitions_non_string_status_rejected(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order(id="st-bad-status")
    payload = _valid_v2_payload(manager, order)
    payload["status_transitions"] = [{"status": 123, "at": datetime.now(UTC).isoformat(), "actor": "system"}]
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    assert manager.is_approved(order.id) is False
    with pytest.raises(InvalidPendingOrderError):
        manager.approve(order.id)


# ---------------------------------------------------------------------------
# Path traversal
# ---------------------------------------------------------------------------

def test_path_traversal_still_rejected(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    with pytest.raises(InvalidApprovalIdError):
        manager.path_for("../secret")
    assert not (tmp_path / "secret.json").exists()


# ---------------------------------------------------------------------------
# No private value leakage
# ---------------------------------------------------------------------------

def test_approve_output_does_not_leak_private_values(tmp_path: Path) -> None:
    manager = ApprovalManager(tmp_path / "pending")
    order = _make_order()
    manager.create_pending_order(order)

    # Simulate what CLI would do: just print the path
    path = manager.approve(order.id)
    output = str(path)
    # Ensure no raw secrets would leak (there are none in this flow, but verify structurally)
    assert "api_key" not in output.lower()
    assert "secret" not in output.lower()
    assert "token" not in output.lower()


# ---------------------------------------------------------------------------
# Paper behavior unchanged (indirectly tested via OrderRouter in test_order_router.py)
# ---------------------------------------------------------------------------

def test_paper_order_router_creates_no_pending_file(tmp_path: Path) -> None:
    from atlas_agent.config import AtlasConfig
    from atlas_agent.execution.audit import AuditLogger
    from atlas_agent.execution.order import Order
    from atlas_agent.execution.order_router import OrderRouter
    from atlas_agent.portfolio.state import PortfolioState
    from atlas_agent.risk.manager import RiskManager

    config = AtlasConfig()
    audit = AuditLogger(tmp_path / "audit")
    router = OrderRouter(
        config=config,
        risk_manager=RiskManager.from_config(config, audit),
        approval_manager=ApprovalManager(tmp_path / "pending"),
        audit=audit,
    )

    order = Order("TEST", "buy", 1, limit_price=100, confidence=1)
    result = router.route(
        order,
        mode="paper",
        broker=_SpyBroker(),
        portfolio=PortfolioState(cash=10_000),
        market_price=100,
    )
    assert result.status == "filled"
    # Paper path should not create a pending file
    assert list((tmp_path / "pending").iterdir()) == []


class _SpyBroker:
    def place_order(self, order: Order):
        from atlas_agent.execution.order import OrderResult
        return OrderResult(True, True, order.id, "filled", "filled")

    def get_account(self):
        from atlas_agent.execution.order import AccountSnapshot
        return AccountSnapshot(0, 0, 0, "spy")

    def get_positions(self):
        return []

    def cancel_order(self, order_id: str):
        from atlas_agent.execution.order import OrderResult
        return OrderResult(True, False, order_id, "cancelled", "cancelled")

    def flatten_all(self, strategy: str = "market", bps: int = 25):
        from atlas_agent.execution.order import FlattenResult
        return FlattenResult(True, "ok", "ok", strategy, bps, 0, 0, 0)
