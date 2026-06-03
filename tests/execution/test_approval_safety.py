import pytest
from pathlib import Path
from atlas_agent.execution.approval import ApprovalManager, InvalidPendingOrderError
from atlas_agent.execution.order import Order
from datetime import datetime, UTC

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
