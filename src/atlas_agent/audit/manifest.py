from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from atlas_agent.audit.models import AuditManifest


def _rolling_hash_step(previous: str | None, event_hash: str) -> str:
    """Compute one step of the rolling hash over event hashes."""
    payload = (previous or "") + event_hash
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_event_hash_rolling_root(event_hashes: list[str]) -> str | None:
    """Compute the compact rolling root over an ordered list of event hashes."""
    if not event_hashes:
        return None
    rolling: str | None = None
    for h in event_hashes:
        rolling = _rolling_hash_step(rolling, h)
    return rolling


def compute_root_hash(manifest: AuditManifest) -> str:
    """
    Compute the root hash of the audit manifest to seal the run.
    """
    # Deterministic subset for root hash
    # Fields that should be final when sealing
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

    # Canonical JSON
    canonical_json = json.dumps(seal_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def create_initial_manifest(run_id: str, log_path: str) -> AuditManifest:
    return AuditManifest(
        run_id=run_id,
        started_at=datetime.now(UTC).isoformat(),
        audit_log_path=log_path,
        status="running"
    )
