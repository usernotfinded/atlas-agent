from __future__ import annotations

import hashlib
import json
from typing import Any

from atlas_agent.audit.models import AuditEvent


def compute_event_hash(event: AuditEvent) -> str:
    """
    Compute SHA-256 hash of the event content excluding event_hash.
    Uses canonical JSON serialization.
    """
    # Convert to dict, exclude event_hash
    data = event.model_dump(exclude={"event_hash"})
    
    # Canonical JSON: sorted keys, no extra whitespace
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def verify_event_integrity(event: AuditEvent, expected_previous_hash: str | None) -> bool:
    """
    Verify that the event's hash is correct and its previous_hash matches the expectation.
    """
    if event.previous_hash != expected_previous_hash:
        return False
        
    actual_hash = compute_event_hash(event)
    return actual_hash == event.event_hash
