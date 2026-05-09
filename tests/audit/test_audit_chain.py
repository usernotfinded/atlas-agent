from __future__ import annotations

from atlas_agent.audit.chain import compute_event_hash, verify_event_integrity
from atlas_agent.audit.models import AuditEvent


def test_deterministic_event_hashing():
    event = AuditEvent(
        event_type="run_started",
        run_id="run_123",
        payload={"foo": "bar"}
    )
    
    hash1 = compute_event_hash(event)
    hash2 = compute_event_hash(event)
    
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256


def test_hash_chain_verification_passes_for_untouched_event():
    event = AuditEvent(
        event_type="run_started",
        run_id="run_123",
        previous_hash="abc"
    )
    event.event_hash = compute_event_hash(event)
    
    assert verify_event_integrity(event, "abc") is True


def test_verification_fails_after_payload_tampering():
    event = AuditEvent(
        event_type="run_started",
        run_id="run_123",
        payload={"amount": 100}
    )
    event.event_hash = compute_event_hash(event)
    
    # Tamper
    event.payload["amount"] = 200
    
    assert verify_event_integrity(event, None) is False


def test_verification_fails_with_wrong_previous_hash():
    event = AuditEvent(
        event_type="run_started",
        run_id="run_123",
        previous_hash="correct_prev"
    )
    event.event_hash = compute_event_hash(event)
    
    assert verify_event_integrity(event, "wrong_prev") is False
