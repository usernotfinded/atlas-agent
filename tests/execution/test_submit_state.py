from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidPendingOrderError,
    _compute_order_hash,
    _order_to_dict,
)
from atlas_agent.execution.order import Order
from atlas_agent.execution.submit_state import (
    SubmitStateError,
    append_submit_attempt,
    build_submit_requested_payload,
    compute_client_order_id,
    load_pending_order,
    mark_submit_requested,
    verify_order_hash,
    is_submit_blocked_by_state,
    append_status_transition,
    mark_reconciliation_required,
    mark_duplicate_reconciled,
    _atomic_write_json,
    _validate_broker_order_id,
    mark_acknowledged,
    mark_acknowledged_from_reconcile,
    mark_submit_failed,
    mark_submit_uncertain,
    mark_submit_prepare_failed,
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
    """Return a minimal valid v2 pending order payload dict."""
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


# ---------------------------------------------------------------------------
# compute_client_order_id
# ---------------------------------------------------------------------------

def test_compute_client_order_id_is_stable() -> None:
    cid1 = compute_client_order_id("abc123", "deadbeef" * 4)
    cid2 = compute_client_order_id("abc123", "deadbeef" * 4)
    assert cid1 == cid2


def test_compute_client_order_id_max_64_chars() -> None:
    cid = compute_client_order_id("a" * 100, "b" * 64)
    assert len(cid) <= 64


def test_compute_client_order_id_matches_allowed_chars() -> None:
    import re
    cid = compute_client_order_id("order-123_test.456", "abc123" * 8)
    assert re.fullmatch(r"[A-Za-z0-9_-]+", cid)


def test_compute_client_order_id_changes_with_order_hash() -> None:
    cid1 = compute_client_order_id("abc123", "deadbeef" * 4)
    cid2 = compute_client_order_id("abc123", "cafebabe" * 4)
    assert cid1 != cid2


def test_compute_client_order_id_no_raw_symbol_quantity_side() -> None:
    cid = compute_client_order_id("abc123", "deadbeef" * 4)
    assert "TEST" not in cid
    assert "buy" not in cid
    assert "1.0" not in cid


def test_compute_client_order_id_replaces_disallowed_chars() -> None:
    cid = compute_client_order_id("order.id:has*bad!chars", "deadbeef" * 4)
    import re
    assert re.fullmatch(r"[A-Za-z0-9_-]+", cid)
    assert ":" not in cid
    assert "*" not in cid
    assert "!" not in cid


# ---------------------------------------------------------------------------
# load_pending_order
# ---------------------------------------------------------------------------

def test_load_pending_order_success(tmp_path: Path) -> None:
    order = _make_order()
    payload = _make_v2_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    loaded = load_pending_order(path)
    assert loaded["status"] == "approved"
    assert loaded["order_hash"] == payload["order_hash"]


def test_load_pending_order_tampered_hash_fails(tmp_path: Path) -> None:
    order = _make_order()
    payload = _make_v2_payload(order)
    payload["order_hash"] = "tampered"
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(InvalidPendingOrderError, match="order hash mismatch"):
        load_pending_order(path)


def test_load_pending_order_malformed_json_fails(tmp_path: Path) -> None:
    path = tmp_path / "order.json"
    path.write_text("not valid json {{{", encoding="utf-8")

    with pytest.raises(InvalidPendingOrderError, match="invalid pending order file"):
        load_pending_order(path)


# ---------------------------------------------------------------------------
# verify_order_hash
# ---------------------------------------------------------------------------

def test_verify_order_hash_matches() -> None:
    order = _make_order()
    payload = _make_v2_payload(order)
    assert verify_order_hash(payload) is True


def test_verify_order_hash_mismatch() -> None:
    order = _make_order()
    payload = _make_v2_payload(order)
    payload["order_hash"] = "tampered"
    assert verify_order_hash(payload) is False


# ---------------------------------------------------------------------------
# is_submit_blocked_by_state
# ---------------------------------------------------------------------------

def test_is_submit_blocked_by_state_approved() -> None:
    blocked, reason = is_submit_blocked_by_state({"status": "approved"})
    assert blocked is False
    assert reason is None


def test_is_submit_blocked_by_state_submit_uncertain() -> None:
    blocked, reason = is_submit_blocked_by_state({"status": "submit_uncertain"})
    assert blocked is True
    assert reason == "submit_uncertain"


def test_is_submit_blocked_by_state_reconciliation_required() -> None:
    blocked, reason = is_submit_blocked_by_state({"status": "reconciliation_required"})
    assert blocked is True
    assert reason == "reconciliation_required"


def test_is_submit_blocked_by_state_submitted() -> None:
    blocked, reason = is_submit_blocked_by_state({"status": "submitted"})
    assert blocked is True
    assert reason == "submitted"


def test_is_submit_blocked_by_state_duplicate_reconciled() -> None:
    blocked, reason = is_submit_blocked_by_state({"status": "duplicate_reconciled"})
    assert blocked is True
    assert reason == "duplicate_reconciled"


def test_is_submit_blocked_by_state_cancelled() -> None:
    blocked, reason = is_submit_blocked_by_state({"status": "cancelled"})
    assert blocked is True
    assert reason == "cancelled"


def test_is_submit_blocked_by_state_invalid_status() -> None:
    blocked, reason = is_submit_blocked_by_state({"status": 123})
    assert blocked is True
    assert reason == "invalid status"


# ---------------------------------------------------------------------------
# append_status_transition
# ---------------------------------------------------------------------------

def test_append_status_transition_adds_entry(tmp_path: Path) -> None:
    order = _make_order()
    payload = _make_v2_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    append_status_transition(path, "reconciliation_required", "system", reason="test reason")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"
    assert len(loaded["status_transitions"]) == 3
    assert loaded["status_transitions"][-1]["status"] == "reconciliation_required"
    assert loaded["status_transitions"][-1]["actor"] == "system"
    assert loaded["status_transitions"][-1]["reason"] == "test reason"
    assert "at" in loaded["status_transitions"][-1]


# ---------------------------------------------------------------------------
# mark_reconciliation_required
# ---------------------------------------------------------------------------

def test_mark_reconciliation_required_updates_status(tmp_path: Path) -> None:
    order = _make_order()
    payload = _make_v2_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_reconciliation_required(path, "broker unavailable")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "reconciliation_required"
    assert loaded["status_transitions"][-1]["reason"] == "broker unavailable"
    assert loaded["status_transitions"][-1]["code"] == "reconcile_failed"


# ---------------------------------------------------------------------------
# mark_duplicate_reconciled
# ---------------------------------------------------------------------------

def test_mark_duplicate_reconciled_updates_status(tmp_path: Path) -> None:
    order = _make_order()
    payload = _make_v2_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_duplicate_reconciled(path, "broker-abc-123", "filled")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "duplicate_reconciled"
    assert loaded["broker_order_id"] == "broker-abc-123"
    assert loaded["broker_status"] == "filled"
    assert "reconciled_at" in loaded
    assert loaded["status_transitions"][-1]["actor"] == "reconcile:cli"


# ---------------------------------------------------------------------------
# atomic write
# ---------------------------------------------------------------------------

def test_atomic_write_preserves_original_on_failure(tmp_path: Path) -> None:
    order = _make_order()
    payload = _make_v2_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    original = path.read_text(encoding="utf-8")

    # Patch Path.write_text to fail after temp file creation
    def _failing_write(*args, **kwargs):
        raise OSError("disk full")

    with patch.object(Path, "write_text", _failing_write):
        with pytest.raises(OSError, match="disk full"):
            _atomic_write_json(path, {"status": "corrupt"})

    # Original must be intact
    after = path.read_text(encoding="utf-8")
    assert after == original


def test_atomic_write_leaves_no_temp_on_success(tmp_path: Path) -> None:
    path = tmp_path / "order.json"
    _atomic_write_json(path, {"status": "ok"})

    assert path.exists()
    # No .tmp-* files should remain
    tmp_files = list(tmp_path.glob("*.tmp-*"))
    assert len(tmp_files) == 0


# ---------------------------------------------------------------------------
# append_submit_attempt
# ---------------------------------------------------------------------------

def _valid_attempt(**overrides) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "attempt_id": str(uuid.uuid4()),
        "client_order_id": "atlas-test-deadbeef",
        "status": "submit_requested",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }
    defaults.update(overrides)
    return defaults


def test_append_submit_attempt_returns_new_dict() -> None:
    payload = _make_v2_payload(_make_order())
    attempt = _valid_attempt()
    result = append_submit_attempt(payload, attempt)
    assert result is not payload
    assert len(result["submit_attempts"]) == 1
    assert len(payload["submit_attempts"]) == 0


def test_append_submit_attempt_validates_required_fields() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = {"attempt_id": str(uuid.uuid4())}  # missing required fields
    with pytest.raises(SubmitStateError, match="missing required fields"):
        append_submit_attempt(payload, bad_attempt)


def test_append_submit_attempt_rejects_invalid_status() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(status="bogus_status")
    with pytest.raises(SubmitStateError, match="invalid submit attempt status"):
        append_submit_attempt(payload, bad_attempt)


def test_append_submit_attempt_rejects_non_bool_risk_revalidated() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(risk_revalidated="true")
    with pytest.raises(SubmitStateError, match="invalid risk_revalidated"):
        append_submit_attempt(payload, bad_attempt)


def test_append_submit_attempt_rejects_non_bool_sync_revalidated() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(sync_revalidated="true")
    with pytest.raises(SubmitStateError, match="invalid sync_revalidated"):
        append_submit_attempt(payload, bad_attempt)


def test_append_submit_attempt_rejects_unknown_extra_field() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt()
    bad_attempt["FAKE_API_KEY_12345"] = "leaked"
    with pytest.raises(SubmitStateError, match="invalid submit attempt"):
        append_submit_attempt(payload, bad_attempt)
    # Confirm raw secret does not appear in exception text
    with pytest.raises(SubmitStateError) as exc_info:
        append_submit_attempt(payload, bad_attempt)
    assert "FAKE_API_KEY" not in str(exc_info.value)


def test_append_submit_attempt_rejects_unsafe_error_code() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(error_code="raw error with spaces and <>")
    with pytest.raises(SubmitStateError, match="invalid submit attempt"):
        append_submit_attempt(payload, bad_attempt)


def test_append_submit_attempt_rejects_secret_shaped_attempt_id() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(attempt_id="FAKE_API_KEY_12345")
    with pytest.raises(SubmitStateError, match="invalid submit attempt") as exc_info:
        append_submit_attempt(payload, bad_attempt)
    assert "FAKE_API_KEY" not in str(exc_info.value)


def test_append_submit_attempt_rejects_secret_shaped_actor() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(actor="FAKE_SECRET_ACTOR")
    with pytest.raises(SubmitStateError, match="invalid submit attempt") as exc_info:
        append_submit_attempt(payload, bad_attempt)
    assert "FAKE_SECRET_ACTOR" not in str(exc_info.value)


def test_append_submit_attempt_rejects_secret_shaped_error_code() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(error_code="FAKE_API_KEY_12345")
    with pytest.raises(SubmitStateError, match="invalid submit attempt") as exc_info:
        append_submit_attempt(payload, bad_attempt)
    assert "FAKE_API_KEY" not in str(exc_info.value)


def test_append_submit_attempt_rejects_non_uuid_attempt_id() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(attempt_id="attempt-001")
    with pytest.raises(SubmitStateError, match="invalid submit attempt"):
        append_submit_attempt(payload, bad_attempt)


def test_append_submit_attempt_accepts_valid_uuid4_attempt_id() -> None:
    payload = _make_v2_payload(_make_order())
    attempt_id = str(uuid.uuid4())
    result = append_submit_attempt(payload, _valid_attempt(attempt_id=attempt_id))
    assert result["submit_attempts"][0]["attempt_id"] == attempt_id


def test_append_submit_attempt_accepts_submit_cli_actor() -> None:
    payload = _make_v2_payload(_make_order())
    result = append_submit_attempt(payload, _valid_attempt(actor="submit:cli"))
    assert result["submit_attempts"][0]["actor"] == "submit:cli"


def test_append_submit_attempt_accepts_allowed_error_codes() -> None:
    allowed = {
        None,
        "broker_rejected_order",
        "broker_unavailable",
        "broker_transport_failed",
        "malformed_broker_response",
        "client_order_id_mismatch",
        "order_not_found",
        "unknown",
    }
    for error_code in allowed:
        payload = _make_v2_payload(_make_order())
        result = append_submit_attempt(payload, _valid_attempt(error_code=error_code))
        assert result["submit_attempts"][0]["error_code"] == error_code


def test_append_submit_attempt_rejects_invalid_client_order_id() -> None:
    payload = _make_v2_payload(_make_order())
    bad_attempt = _valid_attempt(client_order_id="../../etc/passwd")
    with pytest.raises(SubmitStateError, match="invalid client_order_id"):
        append_submit_attempt(payload, bad_attempt)


def test_append_submit_attempt_output_contains_only_allowed_keys() -> None:
    payload = _make_v2_payload(_make_order())
    attempt = _valid_attempt()
    result = append_submit_attempt(payload, attempt)
    stored = result["submit_attempts"][0]
    allowed = {
        "attempt_id",
        "client_order_id",
        "status",
        "created_at",
        "actor",
        "risk_revalidated",
        "sync_revalidated",
        "broker_order_id",
        "error_code",
    }
    assert set(stored.keys()) == allowed


def test_append_submit_attempt_rejects_non_list_submit_attempts() -> None:
    payload = _make_v2_payload(_make_order())
    payload["submit_attempts"] = "not-a-list"
    attempt = _valid_attempt()
    with pytest.raises(SubmitStateError, match="submit_attempts must be a list"):
        append_submit_attempt(payload, attempt)


# ---------------------------------------------------------------------------
# build_submit_requested_payload
# ---------------------------------------------------------------------------

def test_build_submit_requested_payload_sets_submit_requested_state() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    result = build_submit_requested_payload(
        payload,
        order_id=order.id,
        client_order_id=cid,
        now=now,
    )
    assert result["status"] == "submit_requested"


def test_build_submit_requested_payload_sets_client_order_id() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    result = build_submit_requested_payload(
        payload,
        order_id=order.id,
        client_order_id=cid,
        now=now,
    )
    assert result["client_order_id"] == cid


def test_build_submit_requested_payload_sets_submit_requested_at_not_submitted_at() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    result = build_submit_requested_payload(
        payload,
        order_id=order.id,
        client_order_id=cid,
        now=now,
    )
    assert result["submit_requested_at"] == now.isoformat()
    assert result.get("submitted_at") is None


def test_build_submit_requested_payload_appends_status_transition() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    result = build_submit_requested_payload(
        payload,
        order_id=order.id,
        client_order_id=cid,
        now=now,
    )
    assert len(result["status_transitions"]) == 3
    assert result["status_transitions"][-1]["status"] == "submit_requested"
    assert result["status_transitions"][-1]["actor"] == "submit:cli"


def test_build_submit_requested_payload_appends_submit_attempt() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    attempt_id = str(uuid.uuid4())
    result = build_submit_requested_payload(
        payload,
        order_id=order.id,
        client_order_id=cid,
        now=now,
        attempt_id=attempt_id,
    )
    assert len(result["submit_attempts"]) == 1
    attempt = result["submit_attempts"][0]
    assert attempt["attempt_id"] == attempt_id
    assert attempt["client_order_id"] == cid
    assert attempt["status"] == "submit_requested"
    assert attempt["actor"] == "submit:cli"
    assert attempt["risk_revalidated"] is True
    assert attempt["sync_revalidated"] is True
    assert attempt["broker_order_id"] is None
    assert attempt["error_code"] is None


def test_build_submit_requested_payload_does_not_mutate_input() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    original = json.dumps(payload, sort_keys=True)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    build_submit_requested_payload(
        payload,
        order_id=order.id,
        client_order_id=cid,
        now=now,
    )
    after = json.dumps(payload, sort_keys=True)
    assert after == original


def test_build_submit_requested_payload_rejects_non_approved_status() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order, status="submitted")
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError, match="status must be approved"):
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id=cid,
            now=now,
        )


def test_build_submit_requested_payload_rejects_tampered_hash() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    payload["order_hash"] = "tampered"
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with pytest.raises(InvalidPendingOrderError, match="order hash mismatch"):
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id=cid,
            now=now,
        )


def test_build_submit_requested_payload_rejects_invalid_client_order_id() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError, match="invalid client_order_id"):
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id="../../etc/passwd",
            now=now,
        )


def test_build_submit_requested_payload_rejects_non_deterministic_client_order_id() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError, match="does not match deterministic computation"):
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id="atlas-wrong-wrongwrong",
            now=now,
        )


def test_build_submit_requested_payload_rejects_existing_mismatched_client_order_id() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    payload["client_order_id"] = "atlas-wrong-wrongwrong"
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError, match="client_order_id mismatch"):
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id=cid,
            now=now,
        )


def test_build_submit_requested_payload_rejects_existing_invalid_client_order_id() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    payload["client_order_id"] = "../../etc/passwd"
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError, match="invalid client_order_id"):
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id=cid,
            now=now,
        )


def test_build_submit_requested_payload_accepts_existing_matching_client_order_id() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    payload["client_order_id"] = cid
    now = datetime.now(UTC)
    result = build_submit_requested_payload(
        payload,
        order_id=order.id,
        client_order_id=cid,
        now=now,
    )
    assert result["client_order_id"] == cid


def test_build_submit_requested_payload_does_not_overwrite_mismatched_existing() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    payload["client_order_id"] = "atlas-wrong-wrongwrong"
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError):
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id=cid,
            now=now,
        )
    # Input must remain unchanged
    assert payload["client_order_id"] == "atlas-wrong-wrongwrong"


def test_build_submit_requested_payload_rejects_secret_shaped_actor() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError, match="invalid submit attempt") as exc_info:
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id=cid,
            now=now,
            actor="FAKE_SECRET_ACTOR",
        )
    assert "FAKE_SECRET_ACTOR" not in str(exc_info.value)
    assert all(
        transition.get("actor") != "FAKE_SECRET_ACTOR"
        for transition in payload["status_transitions"]
    )


def test_build_submit_requested_payload_rejects_secret_shaped_attempt_id() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError, match="invalid submit attempt") as exc_info:
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id=cid,
            now=now,
            attempt_id="FAKE_API_KEY_12345",
        )
    assert "FAKE_API_KEY" not in str(exc_info.value)
    assert payload["submit_attempts"] == []


def test_build_submit_requested_payload_generates_uuid4_attempt_id() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    result = build_submit_requested_payload(
        payload,
        order_id=order.id,
        client_order_id=cid,
        now=now,
    )
    attempt_id = result["submit_attempts"][0]["attempt_id"]
    parsed = uuid.UUID(attempt_id, version=4)
    assert parsed.version == 4
    assert str(parsed) == attempt_id


def test_build_submit_requested_payload_validates_status_transition_actor() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError, match="invalid submit attempt"):
        build_submit_requested_payload(
            payload,
            order_id=order.id,
            client_order_id=cid,
            now=now,
            actor="FAKE_SECRET_ACTOR",
        )
    assert all(
        transition.get("actor") != "FAKE_SECRET_ACTOR"
        for transition in payload["status_transitions"]
    )


def test_build_submit_requested_payload_validates_submit_attempt_through_helper() -> None:
    order = _make_order(id="build-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    now = datetime.now(UTC)
    with patch(
        "atlas_agent.execution.submit_state.append_submit_attempt",
        side_effect=SubmitStateError("invalid submit attempt"),
    ) as mock_append:
        with pytest.raises(SubmitStateError, match="invalid submit attempt"):
            build_submit_requested_payload(
                payload,
                order_id=order.id,
                client_order_id=cid,
                now=now,
            )
    mock_append.assert_called_once()


# ---------------------------------------------------------------------------
# mark_submit_requested
# ---------------------------------------------------------------------------

def test_mark_submit_requested_atomic_write(tmp_path: Path) -> None:
    order = _make_order(id="mark-test")
    payload = _make_v2_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    cid = compute_client_order_id(order.id, payload["order_hash"])

    mark_submit_requested(
        path,
        order_id=order.id,
        client_order_id=cid,
        now=datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC),
        attempt_id=str(uuid.UUID("12345678-1234-4234-9234-123456789abc")),
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_requested"
    assert loaded["client_order_id"] == cid
    assert loaded["submit_requested_at"] == "2026-05-14T12:00:00+00:00"
    assert loaded["submitted_at"] is None
    assert len(loaded["status_transitions"]) == 3
    assert loaded["status_transitions"][-1]["status"] == "submit_requested"
    assert len(loaded["submit_attempts"]) == 1
    assert loaded["submit_attempts"][0]["attempt_id"] == "12345678-1234-4234-9234-123456789abc"


def test_mark_submit_requested_preserves_original_on_write_failure(tmp_path: Path) -> None:
    order = _make_order(id="mark-test")
    payload = _make_v2_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    original = path.read_text(encoding="utf-8")
    cid = compute_client_order_id(order.id, payload["order_hash"])

    def _failing_write(*args, **kwargs):
        raise OSError("disk full")

    with patch.object(Path, "write_text", _failing_write):
        with pytest.raises(OSError, match="disk full"):
            mark_submit_requested(
                path,
                order_id=order.id,
                client_order_id=cid,
            )

    after = path.read_text(encoding="utf-8")
    assert after == original


def test_mark_submit_requested_reuses_matching_existing_client_order_id(tmp_path: Path) -> None:
    order = _make_order(id="mark-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    payload["client_order_id"] = cid
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_submit_requested(
        path,
        order_id=order.id,
        client_order_id=cid,
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_requested"
    assert loaded["client_order_id"] == cid


def test_mark_submit_requested_rejects_mismatched_existing_client_order_id(tmp_path: Path) -> None:
    order = _make_order(id="mark-test")
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    payload["client_order_id"] = "atlas-wrong-wrongwrong"
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="does not match deterministic computation"):
        mark_submit_requested(
            path,
            order_id=order.id,
            client_order_id=cid,
        )


def test_mark_submit_requested_rejects_invalid_status(tmp_path: Path) -> None:
    order = _make_order(id="mark-test")
    payload = _make_v2_payload(order, status="submitted")
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    cid = compute_client_order_id(order.id, payload["order_hash"])

    with pytest.raises(SubmitStateError, match="status must be approved"):
        mark_submit_requested(
            path,
            order_id=order.id,
            client_order_id=cid,
        )


def test_mark_submit_requested_rejects_tampered_hash(tmp_path: Path) -> None:
    order = _make_order(id="mark-test")
    payload = _make_v2_payload(order)
    payload["order_hash"] = "tampered"
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    cid = compute_client_order_id(order.id, payload["order_hash"])

    with pytest.raises(InvalidPendingOrderError, match="order hash mismatch"):
        mark_submit_requested(
            path,
            order_id=order.id,
            client_order_id=cid,
        )


# ---------------------------------------------------------------------------
# Batch 4.8: Post-submit state mutation helpers (unwired)
# ---------------------------------------------------------------------------

def _make_submit_requested_payload(order: Order, **overrides) -> dict:
    """Return a payload already in submit_requested state."""
    payload = _make_v2_payload(order)
    cid = compute_client_order_id(order.id, payload["order_hash"])
    payload["status"] = "submit_requested"
    payload["client_order_id"] = cid
    payload["submit_requested_at"] = datetime.now(UTC).isoformat()
    payload["status_transitions"].append({
        "status": "submit_requested",
        "at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
    })
    payload["submit_attempts"] = [{
        "attempt_id": str(uuid.uuid4()),
        "client_order_id": cid,
        "status": "submit_requested",
        "created_at": datetime.now(UTC).isoformat(),
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": None,
    }]
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# mark_acknowledged
# ---------------------------------------------------------------------------

def test_mark_acknowledged_sets_status_and_submitted_at(tmp_path: Path) -> None:
    order = _make_order(id="ack-test")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    now = datetime(2026, 5, 14, 13, 0, 0, tzinfo=UTC)

    mark_acknowledged(
        path,
        broker_order_id="broker-123",
        broker_status="new",
        now=now,
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"
    assert loaded["submitted_at"] == "2026-05-14T13:00:00+00:00"
    assert loaded["broker_order_id"] == "broker-123"
    assert loaded["broker_status"] == "new"


def test_mark_acknowledged_updates_last_attempt(tmp_path: Path) -> None:
    order = _make_order(id="ack-attempt")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_acknowledged(
        path,
        broker_order_id="broker-456",
        broker_status="filled",
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert len(loaded["submit_attempts"]) == 1
    attempt = loaded["submit_attempts"][0]
    assert attempt["status"] == "acknowledged"
    assert attempt["broker_order_id"] == "broker-456"
    assert attempt.get("error_code") is None


def test_mark_acknowledged_appends_status_transition(tmp_path: Path) -> None:
    order = _make_order(id="ack-transition")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_acknowledged(
        path,
        broker_order_id="broker-789",
        broker_status="accepted",
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    transition = loaded["status_transitions"][-1]
    assert transition["status"] == "acknowledged"
    assert transition["actor"] == "system"
    assert transition["reason"] == "broker_acknowledged"
    assert "broker-789" not in transition["reason"]


def test_mark_acknowledged_rejects_non_submit_requested_status(tmp_path: Path) -> None:
    order = _make_order(id="ack-bad-status")
    payload = _make_v2_payload(order, status="approved")
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="status must be submit_requested"):
        mark_acknowledged(path, broker_order_id="broker-123", broker_status="new")


def test_mark_acknowledged_rejects_empty_broker_order_id(tmp_path: Path) -> None:
    order = _make_order(id="ack-bad-boid")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        mark_acknowledged(path, broker_order_id="", broker_status="new")


def test_mark_acknowledged_rejects_none_broker_order_id(tmp_path: Path) -> None:
    order = _make_order(id="ack-none-boid")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        mark_acknowledged(path, broker_order_id=None, broker_status="new")


def test_mark_acknowledged_rejects_unknown_broker_status(tmp_path: Path) -> None:
    order = _make_order(id="ack-bad-status2")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid broker_status"):
        mark_acknowledged(path, broker_order_id="broker-123", broker_status="hacked")


def test_mark_acknowledged_rejects_path_like_broker_order_id(tmp_path: Path) -> None:
    order = _make_order(id="ack-path")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        mark_acknowledged(path, broker_order_id="/Users/name/.config/alpaca", broker_status="new")


def test_mark_acknowledged_preserves_original_on_write_failure(tmp_path: Path) -> None:
    order = _make_order(id="ack-atomic")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    original = path.read_text(encoding="utf-8")

    def _failing_write(*args, **kwargs):
        raise OSError("disk full")

    with patch.object(Path, "write_text", _failing_write):
        with pytest.raises(OSError, match="disk full"):
            mark_acknowledged(path, broker_order_id="broker-999", broker_status="new")

    after = path.read_text(encoding="utf-8")
    assert after == original


# ---------------------------------------------------------------------------
# mark_acknowledged_from_reconcile
# ---------------------------------------------------------------------------

def _make_submit_uncertain_payload(order: Order, **overrides) -> dict:
    payload = _make_v2_payload(order, status="submit_requested", **overrides)
    payload["status"] = "submit_uncertain"
    payload["status_transitions"].append({
        "status": "submit_uncertain",
        "at": payload["created_at"],
        "actor": "system",
        "reason": "broker_uncertain",
        "code": "broker_transport_failed",
    })
    payload["submit_attempts"] = [{
        "attempt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "client_order_id": payload.get("client_order_id", "atlas-test-cid"),
        "status": "submit_uncertain",
        "created_at": payload["created_at"],
        "actor": "submit:cli",
        "risk_revalidated": True,
        "sync_revalidated": True,
        "broker_order_id": None,
        "error_code": "broker_transport_failed",
    }]
    return payload


def test_mark_acknowledged_from_reconcile_sets_status_and_fields(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-test")
    payload = _make_submit_uncertain_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    now = datetime(2026, 5, 14, 13, 0, 0, tzinfo=UTC)

    mark_acknowledged_from_reconcile(
        path,
        broker_order_id="broker-123",
        broker_status="new",
        now=now,
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"
    assert loaded["submitted_at"] == "2026-05-14T13:00:00+00:00"
    assert loaded["broker_order_id"] == "broker-123"
    assert loaded["broker_status"] == "new"
    assert loaded["reconciled_at"] == "2026-05-14T13:00:00+00:00"


def test_mark_acknowledged_from_reconcile_preserves_existing_submitted_at(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-preserve")
    payload = _make_submit_uncertain_payload(order)
    payload["submitted_at"] = "2026-05-14T10:00:00+00:00"
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    now = datetime(2026, 5, 14, 13, 0, 0, tzinfo=UTC)

    mark_acknowledged_from_reconcile(
        path,
        broker_order_id="broker-123",
        broker_status="new",
        now=now,
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "acknowledged"
    assert loaded["submitted_at"] == "2026-05-14T10:00:00+00:00"


def test_mark_acknowledged_from_reconcile_updates_last_attempt(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-attempt")
    payload = _make_submit_uncertain_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_acknowledged_from_reconcile(
        path,
        broker_order_id="broker-456",
        broker_status="filled",
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert len(loaded["submit_attempts"]) == 1
    attempt = loaded["submit_attempts"][0]
    assert attempt["status"] == "acknowledged"
    assert attempt["broker_order_id"] == "broker-456"
    assert attempt.get("error_code") == "broker_transport_failed"


def test_mark_acknowledged_from_reconcile_appends_transition(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-transition")
    payload = _make_submit_uncertain_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_acknowledged_from_reconcile(
        path,
        broker_order_id="broker-789",
        broker_status="accepted",
    )

    loaded = json.loads(path.read_text(encoding="utf-8"))
    transition = loaded["status_transitions"][-1]
    assert transition["status"] == "acknowledged"
    assert transition["actor"] == "reconcile:cli"
    assert transition["reason"] == "broker_found_during_reconcile"


def test_mark_acknowledged_from_reconcile_rejects_approved_status(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-bad")
    payload = _make_v2_payload(order, status="approved")
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="status must be a post-submit reconcile state"):
        mark_acknowledged_from_reconcile(path, broker_order_id="broker-123", broker_status="new")


def test_mark_acknowledged_from_reconcile_rejects_empty_broker_order_id(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-bad-boid")
    payload = _make_submit_uncertain_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        mark_acknowledged_from_reconcile(path, broker_order_id="", broker_status="new")


def test_mark_acknowledged_from_reconcile_rejects_unknown_broker_status(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-bad-status")
    payload = _make_submit_uncertain_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid broker_status"):
        mark_acknowledged_from_reconcile(path, broker_order_id="broker-123", broker_status="hacked")


def test_mark_acknowledged_from_reconcile_requires_matching_client_order_id(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-cid-mismatch")
    payload = _make_submit_uncertain_payload(order)
    payload["client_order_id"] = "payload-cid-123"
    payload["submit_attempts"][0]["client_order_id"] = "attempt-cid-456"
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="client_order_id mismatch"):
        mark_acknowledged_from_reconcile(path, broker_order_id="broker-123", broker_status="new")


def test_mark_acknowledged_from_reconcile_preserves_original_on_write_failure(tmp_path: Path) -> None:
    order = _make_order(id="ack-rec-atomic")
    payload = _make_submit_uncertain_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    original = path.read_text(encoding="utf-8")

    def _failing_write(*args, **kwargs):
        raise OSError("disk full")

    with patch.object(Path, "write_text", _failing_write):
        with pytest.raises(OSError, match="disk full"):
            mark_acknowledged_from_reconcile(path, broker_order_id="broker-999", broker_status="new")

    after = path.read_text(encoding="utf-8")
    assert after == original


# ---------------------------------------------------------------------------
# mark_submit_failed
# ---------------------------------------------------------------------------

def test_mark_submit_failed_sets_status_and_error_code(tmp_path: Path) -> None:
    order = _make_order(id="fail-test")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_submit_failed(path, error_code="broker_rejected_order")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "failed"
    assert loaded.get("submitted_at") is None
    assert loaded.get("broker_order_id") is None
    assert len(loaded["submit_attempts"]) == 1
    assert loaded["submit_attempts"][0]["status"] == "failed"
    assert loaded["submit_attempts"][0]["error_code"] == "broker_rejected_order"


def test_mark_submit_failed_rejects_non_submit_requested_status(tmp_path: Path) -> None:
    order = _make_order(id="fail-bad-status")
    payload = _make_v2_payload(order, status="approved")
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="status must be submit_requested"):
        mark_submit_failed(path, error_code="broker_rejected_order")


def test_mark_submit_failed_rejects_unknown_error_code(tmp_path: Path) -> None:
    order = _make_order(id="fail-bad-code")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid submit attempt"):
        mark_submit_failed(path, error_code="hacked")


def test_mark_submit_failed_rejects_secret_shaped_error_code(tmp_path: Path) -> None:
    order = _make_order(id="fail-secret")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid submit attempt"):
        mark_submit_failed(path, error_code="FAKE_API_KEY_123")

    # Verify secret does not leak in exception message
    try:
        mark_submit_failed(path, error_code="FAKE_API_KEY_123")
    except SubmitStateError as exc:
        assert "FAKE_API_KEY" not in str(exc)


def test_mark_submit_failed_preserves_original_on_write_failure(tmp_path: Path) -> None:
    order = _make_order(id="fail-atomic")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    original = path.read_text(encoding="utf-8")

    def _failing_write(*args, **kwargs):
        raise OSError("disk full")

    with patch.object(Path, "write_text", _failing_write):
        with pytest.raises(OSError, match="disk full"):
            mark_submit_failed(path, error_code="broker_rejected_order")

    after = path.read_text(encoding="utf-8")
    assert after == original


# ---------------------------------------------------------------------------
# mark_submit_uncertain
# ---------------------------------------------------------------------------

def test_mark_submit_uncertain_sets_status_and_error_code(tmp_path: Path) -> None:
    order = _make_order(id="uncertain-test")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_submit_uncertain(path, error_code="broker_transport_failed")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_uncertain"
    assert loaded.get("submitted_at") is None
    assert loaded.get("broker_order_id") is None
    assert len(loaded["submit_attempts"]) == 1
    assert loaded["submit_attempts"][0]["status"] == "submit_uncertain"
    assert loaded["submit_attempts"][0]["error_code"] == "broker_transport_failed"


def test_mark_submit_uncertain_rejects_non_submit_requested_status(tmp_path: Path) -> None:
    order = _make_order(id="uncertain-bad-status")
    payload = _make_v2_payload(order, status="approved")
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="status must be submit_requested"):
        mark_submit_uncertain(path, error_code="broker_transport_failed")


def test_mark_submit_uncertain_rejects_unknown_error_code(tmp_path: Path) -> None:
    order = _make_order(id="uncertain-bad-code")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="invalid submit attempt"):
        mark_submit_uncertain(path, error_code="hacked")


def test_mark_submit_uncertain_preserves_original_on_write_failure(tmp_path: Path) -> None:
    order = _make_order(id="uncertain-atomic")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    original = path.read_text(encoding="utf-8")

    def _failing_write(*args, **kwargs):
        raise OSError("disk full")

    with patch.object(Path, "write_text", _failing_write):
        with pytest.raises(OSError, match="disk full"):
            mark_submit_uncertain(path, error_code="broker_unavailable")

    after = path.read_text(encoding="utf-8")
    assert after == original


# ---------------------------------------------------------------------------
# mark_submit_prepare_failed
# ---------------------------------------------------------------------------

def test_mark_submit_prepare_failed_sets_status_and_error_code(tmp_path: Path) -> None:
    order = _make_order(id="prepare-fail-test")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_submit_prepare_failed(path, error_code="execution_broker_unavailable")

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"
    assert loaded.get("submitted_at") is None
    assert loaded.get("broker_order_id") is None
    assert len(loaded["submit_attempts"]) == 1
    assert loaded["submit_attempts"][0]["status"] == "submit_prepare_failed"
    assert loaded["submit_attempts"][0]["error_code"] == "execution_broker_unavailable"


def test_mark_submit_prepare_failed_rejects_non_submit_requested_status(tmp_path: Path) -> None:
    order = _make_order(id="prepare-bad-status")
    payload = _make_v2_payload(order, status="approved")
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    with pytest.raises(SubmitStateError, match="status must be submit_requested"):
        mark_submit_prepare_failed(path, error_code="execution_broker_unavailable")


def test_mark_submit_prepare_failed_rejects_non_preparation_error_codes(tmp_path: Path) -> None:
    order = _make_order(id="prepare-bad-code")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    # These are post-broker error codes, not allowed for submit_prepare_failed
    for bad_code in ("broker_rejected_order", "broker_transport_failed", "unknown"):
        with pytest.raises(SubmitStateError, match="invalid submit attempt"):
            mark_submit_prepare_failed(path, error_code=bad_code)


def test_mark_submit_prepare_failed_accepts_both_valid_codes(tmp_path: Path) -> None:
    order = _make_order(id="prepare-valid")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_submit_prepare_failed(path, error_code="execution_broker_unavailable")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"

    # Reset and try the other valid code
    _write_payload(path, payload)
    mark_submit_prepare_failed(path, error_code="execution_broker_invalid")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"


def test_mark_submit_prepare_failed_preserves_original_on_write_failure(tmp_path: Path) -> None:
    order = _make_order(id="prepare-atomic")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)
    original = path.read_text(encoding="utf-8")

    def _failing_write(*args, **kwargs):
        raise OSError("disk full")

    with patch.object(Path, "write_text", _failing_write):
        with pytest.raises(OSError, match="disk full"):
            mark_submit_prepare_failed(path, error_code="execution_broker_invalid")

    after = path.read_text(encoding="utf-8")
    assert after == original


# ---------------------------------------------------------------------------
# submitted_at semantics across all post-submit helpers
# ---------------------------------------------------------------------------

def test_submitted_at_null_for_failed(tmp_path: Path) -> None:
    order = _make_order(id="at-null-fail")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_submit_failed(path, error_code="broker_rejected_order")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.get("submitted_at") is None


def test_submitted_at_null_for_submit_prepare_failed(tmp_path: Path) -> None:
    order = _make_order(id="at-null-prepare")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_submit_prepare_failed(path, error_code="execution_broker_unavailable")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.get("submitted_at") is None


def test_submitted_at_null_for_submit_uncertain(tmp_path: Path) -> None:
    order = _make_order(id="at-null-uncertain")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    mark_submit_uncertain(path, error_code="broker_transport_failed")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.get("submitted_at") is None


def test_submitted_at_set_for_acknowledged(tmp_path: Path) -> None:
    order = _make_order(id="at-set-ack")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    now = datetime(2026, 5, 14, 14, 0, 0, tzinfo=UTC)
    mark_acknowledged(path, broker_order_id="broker-999", broker_status="new", now=now)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["submitted_at"] == "2026-05-14T14:00:00+00:00"


class _FakeConfig:
    enable_live_trading = True
    max_position_size = 10000.0
    max_order_notional = 5000.0
    symbol_allowlist = None
    symbol_blocklist = set()
    require_stop_loss_live = True
    pending_orders_dir = Path("pending_orders")
    live_broker = "alpaca"
    memory_dir = Path("memory")


# ---------------------------------------------------------------------------
# Batch 4.9: mark_submit_prepare_failed allowlist
# ---------------------------------------------------------------------------

def test_mark_submit_prepare_failed_accepts_kill_switch_active(tmp_path: Path) -> None:
    order = _make_order(id="prep-ks")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    now = datetime.now(UTC)
    mark_submit_prepare_failed(path, error_code="kill_switch_active", now=now)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"
    assert loaded["submit_attempts"][0]["error_code"] == "kill_switch_active"
    assert loaded.get("submitted_at") is None
    assert loaded.get("broker_order_id") is None


def test_mark_submit_prepare_failed_rejects_broker_rejected_order(tmp_path: Path) -> None:
    order = _make_order(id="prep-rej")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError) as exc:
        mark_submit_prepare_failed(path, error_code="broker_rejected_order", now=now)
    assert str(exc.value) == "invalid submit attempt"


def test_mark_submit_prepare_failed_rejects_broker_unavailable(tmp_path: Path) -> None:
    order = _make_order(id="prep-unav")
    payload = _make_submit_requested_payload(order)
    path = tmp_path / "order.json"
    _write_payload(path, payload)

    now = datetime.now(UTC)
    with pytest.raises(SubmitStateError) as exc:
        mark_submit_prepare_failed(path, error_code="broker_unavailable", now=now)
    assert str(exc.value) == "invalid submit attempt"


# ---------------------------------------------------------------------------
# Batch 5.3: strict broker_order_id allowlist
# ---------------------------------------------------------------------------

def test_validate_broker_order_id_rejects_path() -> None:
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("/Users/name/.config/alpaca")


def test_validate_broker_order_id_rejects_header_like() -> None:
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("Authorization: Bearer abc123")


def test_validate_broker_order_id_rejects_traversal() -> None:
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("../../broker-body")


def test_validate_broker_order_id_rejects_url() -> None:
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("https://example.com/order")


def test_validate_broker_order_id_rejects_unsafe_characters() -> None:
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("has space")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("has:colon")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("has/slash")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("has\\backslash")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("has.dot")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("has..dots")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("has@symbol")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("has#hash")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id(None)


def test_validate_broker_order_id_accepts_safe_values() -> None:
    _validate_broker_order_id("broker-123")
    _validate_broker_order_id("abc123")
    _validate_broker_order_id("ABC_123-xyz")


def test_validate_broker_order_id_rejects_secret_shaped() -> None:
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("FAKE_API_KEY_123")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("LEAKED_PASSWORD_999")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("SECRET_TOKEN_ABC")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("AUTHORIZATION_BEARER_ABC")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("APCA_API_KEY_ID")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("ALPACA_SECRET_KEY")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("MY_CREDENTIAL_123")
    with pytest.raises(SubmitStateError, match="invalid broker_order_id"):
        _validate_broker_order_id("PRIVATE_KEY_XYZ")
