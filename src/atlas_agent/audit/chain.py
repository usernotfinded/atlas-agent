# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    audit/chain.py
# PURPOSE: The cryptographic spine of the audit log. Each event carries the hash of
#          the one before it, so the log is a blockchain-style chain: altering or
#          removing any past event invalidates every hash downstream of it.
# DEPS:    hashlib (SHA-256), audit.models (AuditEvent)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import hashlib
import json
from typing import Any

from atlas_agent.audit.models import AuditEvent


# ==============================================================================
# HASH COMPUTATION
# ==============================================================================

def compute_event_hash(event: AuditEvent) -> str:
    """
    Compute SHA-256 hash of the event content excluding event_hash.
    Uses canonical JSON serialization.
    """
    # event_hash is excluded because it is the output: hashing a field that holds
    # the hash would be self-referential and could never be reproduced on verify.
    data = event.model_dump(exclude={"event_hash"})

    # Canonicalisation is what makes the hash reproducible at all. Same event, same
    # bytes, every time and on every machine — so sorted keys and no incidental
    # whitespace. Without this, a re-serialisation with different key order would
    # look exactly like tampering.
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))

    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


# ==============================================================================
# INTEGRITY VERIFICATION
# ==============================================================================

def verify_event_integrity(event: AuditEvent, expected_previous_hash: str | None) -> bool:
    """
    Verify that the event's hash is correct and its previous_hash matches the expectation.
    """
    # Two independent checks, and both must hold:
    #   1. the back-link is intact  → nothing was deleted or reordered before it;
    #   2. the recomputed hash matches → the event's own content was not edited.
    # Check 1 alone would miss an in-place edit; check 2 alone would miss a deletion.
    if event.previous_hash != expected_previous_hash:
        return False

    actual_hash = compute_event_hash(event)
    return actual_hash == event.event_hash
