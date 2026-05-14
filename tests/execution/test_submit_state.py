from __future__ import annotations

import json
import os
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
    compute_client_order_id,
    load_pending_order,
    verify_order_hash,
    is_submit_blocked_by_state,
    append_status_transition,
    mark_reconciliation_required,
    mark_duplicate_reconciled,
    _atomic_write_json,
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


def _make_v2_payload(order: Order) -> dict:
    """Return a minimal valid v2 pending order payload dict."""
    order_dict = _order_to_dict(order)
    now = datetime.now(UTC)
    return {
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
