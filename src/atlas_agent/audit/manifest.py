from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from atlas_agent.audit.models import AuditManifest


def compute_root_hash(manifest: AuditManifest) -> str:
    """
    Compute the root hash of the audit manifest to seal the run.
    """
    # Deterministic subset for root hash
    # Fields that should be final when sealing
    seal_data = {
        "run_id": manifest.run_id,
        "event_count": manifest.event_count,
        "first_event_hash": manifest.first_event_hash,
        "final_event_hash": manifest.final_event_hash,
        "final_status": manifest.final_status,
        "completed_at": manifest.completed_at,
        "status": manifest.status,
    }
    
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
