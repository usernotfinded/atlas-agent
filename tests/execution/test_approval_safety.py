# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/execution/test_approval_safety.py
# PURPOSE: Verifies approval safety behavior and regression expectations.
# DEPS:    pytest, pathlib, atlas_agent, datetime.
# ==============================================================================

# --- IMPORTS ---

import pytest
from pathlib import Path
from atlas_agent.execution.approval import ApprovalManager, InvalidPendingOrderError
from atlas_agent.execution.order import Order
from datetime import datetime, UTC

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---


def _order(order_id: str = "order-atomic") -> Order:
    return Order(
        id=order_id,
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="market",
        confidence=0.9,
        leverage=1.0,
        source="test",
        created_at=datetime.now(UTC),
    )

def test_approval_safety_requires_actor_and_rejects_auto_approve(tmp_path: Path):
    manager = ApprovalManager(pending_dir=tmp_path)
    order = Order(
        id="order-1",
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="market",
        confidence=0.9,
        leverage=1.0,
        source="test",
        created_at=datetime.now(UTC),
    )
    
    # Create the pending order
    path = manager.create_pending_order(order, ttl_minutes=30)
    
    # Assert not approved initially
    assert not manager.is_approved("order-1")
    
    # Try to approve with invalid actor
    with pytest.raises(InvalidPendingOrderError, match="approval actor invalid"):
        manager.approve("order-1", actor="")
        
    # Manual tamper: try to fake approval without hash
    import json
    payload = json.loads(path.read_text())
    payload["approved"] = True
    payload["status"] = "approved"
    path.write_text(json.dumps(payload))
    
    # The hash mismatch should fail the integrity check implicitly inside is_approved
    assert not manager.is_approved("order-1")
    
    # Fix the file to be structurally valid but unapproved again
    path = manager.create_pending_order(order, ttl_minutes=30)
    
    # Real approval works
    manager.approve("order-1", actor="human-test")
    assert manager.is_approved("order-1")


def test_approval_records_are_written_atomically(tmp_path: Path, monkeypatch) -> None:
    """A crash mid-write must leave the previous record intact, not a torn one.

    The reader already fails closed on an unparseable record, so a torn write was
    safe — but it destroyed a pending approval that an operator would then have to
    recreate. Writing through the same helper the kill switch uses makes the torn
    state impossible rather than merely harmless.
    """
    from atlas_agent.execution import approval as approval_module

    seen: list[Path] = []
    real_atomic = approval_module.atomic_write_json

    def _tracking_atomic(target, payload, **kwargs):
        seen.append(Path(target))
        return real_atomic(target, payload, **kwargs)

    monkeypatch.setattr(approval_module, "atomic_write_json", _tracking_atomic)

    manager = ApprovalManager(pending_dir=tmp_path)
    order = _order()
    created = manager.create_pending_order(order)
    manager.approve(order.id, actor="cli:test")

    # Both the creation and the approval go through the atomic helper.
    assert seen == [created, created]
    assert manager.is_approved(order.id) is True
    assert not list(tmp_path.glob("*.tmp*"))


def test_approval_record_content_is_unchanged_by_atomic_write(tmp_path: Path) -> None:
    """The swap must be byte-for-byte, since the record is hash-protected."""
    import json

    manager = ApprovalManager(pending_dir=tmp_path)
    order = _order()
    path = manager.create_pending_order(order)

    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert raw == json.dumps(payload, indent=2, sort_keys=True)
