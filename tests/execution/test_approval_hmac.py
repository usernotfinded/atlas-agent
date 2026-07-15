# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/execution/test_approval_hmac.py
# PURPOSE: Verifies approval hmac behavior and regression expectations.
# DEPS:    json, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas_agent.execution.approval import (
    ApprovalManager,
    InvalidPendingOrderError,
    assert_live_hmac_approval,
    _compute_approval_hash,
)
from atlas_agent.execution.order import Order


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _make_order(order_id: str = "test-1") -> Order:
    return Order(
        id=order_id,
        symbol="AAPL",
        side="buy",
        quantity=1.0,
        order_type="market",
        confidence=0.8,
        source="test",
    )


class TestPaperPathWithoutSecret:
    def test_plain_sha256_approval_works(self, tmp_path: Path) -> None:
        manager = ApprovalManager(pending_dir=tmp_path, secret_key=None)
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="tester")
        assert manager.is_approved(order.id) is True

    def test_legacy_order_without_alg_still_verifies(self, tmp_path: Path) -> None:
        manager = ApprovalManager(pending_dir=tmp_path, secret_key=None)
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="tester")

        # Strip approval_hash_alg to simulate legacy order
        path = manager.path_for(order.id)
        payload = json.loads(path.read_text())
        del payload["approval_hash_alg"]
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

        assert manager.is_approved(order.id) is True


class TestHMACPath:
    def test_hmac_approval_validates(self, tmp_path: Path) -> None:
        manager = ApprovalManager(pending_dir=tmp_path, secret_key="super-secret")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="tester")
        assert manager.is_approved(order.id) is True

    def test_hmac_order_rejected_without_secret(self, tmp_path: Path) -> None:
        # Create with HMAC
        manager_with_secret = ApprovalManager(pending_dir=tmp_path, secret_key="super-secret")
        order = _make_order()
        manager_with_secret.create_pending_order(order)
        manager_with_secret.approve(order.id, actor="tester")

        # Verify without secret fails
        manager_without = ApprovalManager(pending_dir=tmp_path, secret_key=None)
        assert manager_without.is_approved(order.id) is False

    def test_tampered_hmac_approval_fails(self, tmp_path: Path) -> None:
        manager = ApprovalManager(pending_dir=tmp_path, secret_key="super-secret")
        order = _make_order()
        manager.create_pending_order(order)
        manager.approve(order.id, actor="tester")

        path = manager.path_for(order.id)
        payload = json.loads(path.read_text())
        payload["approved_at"] = "2100-01-01T00:00:00+00:00"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

        assert manager.is_approved(order.id) is False

    def test_approval_hash_alg_present(self, tmp_path: Path) -> None:
        manager = ApprovalManager(pending_dir=tmp_path, secret_key="super-secret")
        order = _make_order()
        manager.create_pending_order(order)
        path = manager.path_for(order.id)
        payload = json.loads(path.read_text())
        assert payload.get("approval_hash_alg") == "hmac-sha256"

    def test_plain_sha256_marked_in_payload(self, tmp_path: Path) -> None:
        manager = ApprovalManager(pending_dir=tmp_path, secret_key=None)
        order = _make_order()
        manager.create_pending_order(order)
        path = manager.path_for(order.id)
        payload = json.loads(path.read_text())
        assert payload.get("approval_hash_alg") == "sha256"


class TestLiveHMACEnforcement:
    def test_assert_live_hmac_rejects_sha256(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_APPROVAL_SECRET_KEY", "secret")
        payload = {"approval_hash_alg": "sha256"}
        with pytest.raises(InvalidPendingOrderError, match="HMAC-backed approval"):
            assert_live_hmac_approval(payload)

    def test_assert_live_hmac_rejects_missing_alg(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_APPROVAL_SECRET_KEY", "secret")
        payload = {}
        with pytest.raises(InvalidPendingOrderError, match="HMAC-backed approval"):
            assert_live_hmac_approval(payload)

    def test_assert_live_hmac_accepts_hmac(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_APPROVAL_SECRET_KEY", "secret")
        payload = {"approval_hash_alg": "hmac-sha256"}
        assert_live_hmac_approval(payload)  # should not raise

    def test_assert_live_hmac_skips_when_no_secret(self) -> None:
        # When no secret is configured, legacy SHA-256 is accepted
        payload = {"approval_hash_alg": "sha256"}
        assert_live_hmac_approval(payload)  # should not raise


class TestComputeApprovalHash:
    def test_hmac_differs_from_plain(self) -> None:
        fields = {
            "order_hash": "abc",
            "approved": True,
            "approved_at": "2024-01-01T00:00:00+00:00",
            "approval_actor": "user",
            "status": "approved",
            "status_transitions": [],
            "expires_at": "2024-01-02T00:00:00+00:00",
        }
        plain = _compute_approval_hash(**fields, secret_key=None)
        hmac_hash = _compute_approval_hash(**fields, secret_key="secret")
        assert plain != hmac_hash

    def test_hmac_deterministic(self) -> None:
        fields = {
            "order_hash": "abc",
            "approved": True,
            "approved_at": None,
            "approval_actor": None,
            "status": "pending_approval",
            "status_transitions": [],
            "expires_at": "2024-01-01T00:00:00+00:00",
        }
        h1 = _compute_approval_hash(**fields, secret_key="same")
        h2 = _compute_approval_hash(**fields, secret_key="same")
        assert h1 == h2
