# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_approval_integrity.py
# PURPOSE: Verifies approval integrity behavior and regression expectations.
# DEPS:    json, datetime, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidPendingOrderError,
    _compute_approval_hash,
    _compute_order_hash,
    _order_to_dict,
    _upgrade_v1_to_v2,
)
from atlas_agent.execution.order import Order


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


def _write_payload(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


class TestApprovalDecisionIntegrity:
    """Approval hash binds decision fields so tampering is detectable."""

    def test_create_pending_order_writes_valid_approval_hash(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        path = manager.create_pending_order(order)
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert "approval_hash" in payload
        assert isinstance(payload["approval_hash"], str)
        assert len(payload["approval_hash"]) == 64

        expected = _compute_approval_hash(
            order_hash=payload["order_hash"],
            approved=False,
            approved_at=None,
            approval_actor=None,
            status="pending_approval",
            status_transitions=payload["status_transitions"],
            expires_at=payload["expires_at"],
        )
        assert payload["approval_hash"] == expected

    def test_approve_writes_valid_approval_hash(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="test:user")

        payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))
        assert "approval_hash" in payload
        expected = _compute_approval_hash(
            order_hash=payload["order_hash"],
            approved=True,
            approved_at=payload["approved_at"],
            approval_actor="test:user",
            status="approved",
            status_transitions=payload["status_transitions"],
            expires_at=payload["expires_at"],
        )
        assert payload["approval_hash"] == expected

    def test_valid_approved_order_passes_is_approved(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="test:user")
        assert manager.is_approved(order.id) is True

    def test_flipping_approved_to_true_manually_fails(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))

        payload["approved"] = True
        _write_payload(manager.path_for(order.id), payload)

        assert manager.is_approved(order.id) is False

    def test_changing_status_to_approved_manually_fails(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))

        payload["status"] = "approved"
        _write_payload(manager.path_for(order.id), payload)

        assert manager.is_approved(order.id) is False

    def test_changing_approval_actor_after_approval_fails(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="test:user")

        payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))
        payload["approval_actor"] = "evil"
        _write_payload(manager.path_for(order.id), payload)

        assert manager.is_approved(order.id) is False

    def test_changing_approved_at_after_approval_fails(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="test:user")

        payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))
        payload["approved_at"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        _write_payload(manager.path_for(order.id), payload)

        assert manager.is_approved(order.id) is False

    def test_changing_status_transitions_after_approval_fails(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="test:user")

        payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))
        payload["status_transitions"].append(
            {"status": "tampered", "at": datetime.now(UTC).isoformat(), "actor": "evil"}
        )
        _write_payload(manager.path_for(order.id), payload)

        assert manager.is_approved(order.id) is False


class TestLegacyV1FailClosed:
    """v1 approved orders must not auto-upgrade to approved v2."""

    def test_v1_approved_payload_fails_closed(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order(id="v1-approved")
        order_dict = _order_to_dict(order)
        v1_payload = {
            "order": order_dict,
            "approved": True,
            "created_at": datetime.now(UTC).isoformat(),
            "approved_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        }
        path = manager.path_for(order.id)
        _write_payload(path, v1_payload)

        assert manager.is_approved(order.id) is False

    def test_v1_unapproved_payload_upgrades_to_pending_safely(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order(id="v1-pending")
        order_dict = _order_to_dict(order)
        v1_payload = {
            "order": order_dict,
            "approved": False,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        }
        path = manager.path_for(order.id)
        _write_payload(path, v1_payload)

        assert manager.is_approved(order.id) is False
        # Should be readable for approve()
        manager.approve(order.id, actor="test:user")
        assert manager.is_approved(order.id) is True

    def test_v1_approved_strips_approval_on_read(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order(id="v1-approved-strip")
        order_dict = _order_to_dict(order)
        v1_payload = {
            "order": order_dict,
            "approved": True,
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        }
        path = manager.path_for(order.id)
        _write_payload(path, v1_payload)

        # approve() should work because the file is upgraded to pending first
        manager.approve(order.id, actor="reapprover")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["approved"] is True
        assert payload["approval_actor"] == "reapprover"
        assert payload["approval_hash"] is not None


class TestUnknownActorRejected:
    def test_unknown_actor_fails_for_approved_orders(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="test:user")

        payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))
        payload["approval_actor"] = "unknown"
        payload["approval_hash"] = _compute_approval_hash(
            order_hash=payload["order_hash"],
            approved=True,
            approved_at=payload["approved_at"],
            approval_actor="unknown",
            status="approved",
            status_transitions=payload["status_transitions"],
            expires_at=payload["expires_at"],
        )
        _write_payload(manager.path_for(order.id), payload)

        assert manager.is_approved(order.id) is False


class TestExpiryAndMalformedTimestamps:
    def test_expired_orders_still_fail_closed(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order, ttl_minutes=-1)
        assert manager.is_approved(order.id) is False

    def test_malformed_timestamps_still_fail_closed(self, tmp_path: Path) -> None:
        manager = ApprovalManager(tmp_path / "pending")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="test:user")

        payload = json.loads(manager.path_for(order.id).read_text(encoding="utf-8"))
        payload["expires_at"] = "not-a-timestamp"
        _write_payload(manager.path_for(order.id), payload)

        assert manager.is_approved(order.id) is False


class TestPathTraversalRemainsGreen:
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
    def test_approval_manager_rejects_unsafe_order_ids(self, tmp_path: Path, order_id: str) -> None:
        from atlas_agent.execution.approval import InvalidApprovalIdError

        manager = ApprovalManager(tmp_path / "pending")
        with pytest.raises(InvalidApprovalIdError, match="Invalid pending order id"):
            manager.path_for(order_id)

        assert not (tmp_path / "secret.json").exists()
        assert not (tmp_path / "pending" / "secret.json").exists()
