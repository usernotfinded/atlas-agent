# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    audit/manifest.py
# PURPOSE: Seals a run. The manifest is the notarised receipt for an audit log:
#          it records how many events there were and commits to their exact
#          sequence, which is what makes truncation and reordering detectable.
# DEPS:    hashlib (SHA-256), audit.models (AuditManifest)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from atlas_agent.audit.models import AuditManifest


# ==============================================================================
# ROLLING ROOT (commits to the whole event sequence)
# ==============================================================================

def _rolling_hash_step(previous: str | None, event_hash: str) -> str:
    """Compute one step of the rolling hash over event hashes."""
    # Order-dependent by construction: the accumulator is prepended, so swapping two
    # events produces a different root. That is the entire point — a plain set or sum
    # of hashes would be blind to reordering.
    payload = (previous or "") + event_hash
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_event_hash_rolling_root(event_hashes: list[str]) -> str | None:
    """Compute the compact rolling root over an ordered list of event hashes."""
    # The verify-side counterpart of the incremental fold the writer does per event.
    # Both must produce the same value from the same sequence; keep them in step.
    if not event_hashes:
        return None
    rolling: str | None = None
    for h in event_hashes:
        rolling = _rolling_hash_step(rolling, h)
    return rolling


# ==============================================================================
# RUN SEALING
# ==============================================================================

def compute_root_hash(manifest: AuditManifest) -> str:
    """
    Compute the root hash of the audit manifest to seal the run.
    """
    # An explicit allowlist, not the whole model. Only fields that are *final* at
    # seal time may be bound: including a mutable one would make the seal fail to
    # reproduce later, turning every honest run into an apparent forgery.
    seal_data: dict[str, Any] = {
        "run_id": manifest.run_id,
        "event_count": manifest.event_count,
        "first_event_hash": manifest.first_event_hash,
        "final_event_hash": manifest.final_event_hash,
        "final_status": manifest.final_status,
        "completed_at": manifest.completed_at,
        "status": manifest.status,
    }
    # Only bind rolling root when present so legacy manifests (schema_version=2
    # created before this field existed) still verify with their original hash.
    if manifest.event_hash_rolling_root is not None:
        seal_data["event_hash_rolling_root"] = manifest.event_hash_rolling_root

    # Same canonicalisation contract as audit/chain.py — sorted keys, no incidental
    # whitespace — because the seal must be reproducible byte-for-byte on verify.
    canonical_json = json.dumps(seal_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def create_initial_manifest(run_id: str, log_path: str) -> AuditManifest:
    # Opens as "running" with no root hash. A manifest left in this state is the
    # trace of a run that died before it could seal itself — a fact worth keeping,
    # not an inconsistency to paper over.
    return AuditManifest(
        run_id=run_id,
        started_at=datetime.now(UTC).isoformat(),
        audit_log_path=log_path,
        status="running"
    )
