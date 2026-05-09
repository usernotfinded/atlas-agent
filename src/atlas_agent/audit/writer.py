from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional, Literal

from atlas_agent.audit.chain import compute_event_hash
from atlas_agent.audit.manifest import compute_root_hash, create_initial_manifest
from atlas_agent.audit.models import AuditEvent, AuditEventType, AuditManifest
from atlas_agent.audit.redaction import redact_payload


class AuditWriter:
    def __init__(self, audit_path: str | Path, manifest_dir: Optional[str | Path] = None):
        self.audit_path = Path(audit_path)
        self.manifest_dir = Path(manifest_dir) if manifest_dir else self.audit_path.parent / "manifests"
        self.last_hash: Optional[str] = None
        self._initialized = False
        
        # Run-specific tracking
        self.current_run_id: Optional[str] = None
        self.current_manifest: Optional[AuditManifest] = None

    def _ensure_initialized(self):
        if self._initialized:
            return
            
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        
        if self.audit_path.exists():
            # Try to recover last hash from the last line
            try:
                with open(self.audit_path, "rb") as f:
                    try:
                        f.seek(-2, os.SEEK_END)
                        while f.read(1) != b"\n":
                            f.seek(-2, os.SEEK_CUR)
                    except OSError:
                        f.seek(0)
                        
                    last_line = f.readline().decode("utf-8")
                    if last_line:
                        last_event = AuditEvent.model_validate_json(last_line)
                        self.last_hash = last_event.event_hash
            except Exception:
                # If recovery fails, we start fresh or with None last_hash
                pass
                
        self._initialized = True

    def start_run(self, run_id: str):
        self._ensure_initialized()
        self.current_run_id = run_id
        self.current_manifest = create_initial_manifest(run_id, str(self.audit_path))
        self.last_hash = None # Start new chain for this run
        self._save_manifest()

    def finish_run(
        self, 
        status: Literal["completed", "failed", "interrupted"], 
        final_status_text: Optional[str] = None
    ):
        if not self.current_manifest:
            return
            
        self.current_manifest.status = status
        self.current_manifest.completed_at = datetime.now(UTC).isoformat()
        self.current_manifest.final_status = final_status_text
        self.current_manifest.root_hash = compute_root_hash(self.current_manifest)
        self._save_manifest()
        
        # Reset current run
        self.current_run_id = None
        self.current_manifest = None

    def _save_manifest(self):
        if not self.current_manifest:
            return
        path = self.manifest_dir / f"{self.current_manifest.run_id}.json"
        path.write_text(self.current_manifest.model_dump_json(indent=2), encoding="utf-8")

    def write_event(
        self,
        event_type: AuditEventType,
        run_id: str,
        iteration: Optional[int] = None,
        tool_name: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        status: Optional[str] = None,
        payload: dict[str, Any] = None,
    ) -> AuditEvent:
        self._ensure_initialized()
        
        event = AuditEvent(
            event_type=event_type,
            run_id=run_id,
            iteration=iteration,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            status=status,
            payload=redact_payload(payload or {}),
            previous_hash=self.last_hash,
        )
        
        event.event_hash = compute_event_hash(event)
        self.last_hash = event.event_hash
        
        # Update manifest if this belongs to current run
        if self.current_manifest and run_id == self.current_run_id:
            if self.current_manifest.event_count == 0:
                self.current_manifest.first_event_hash = event.event_hash
            self.current_manifest.event_count += 1
            self.current_manifest.final_event_hash = event.event_hash
        
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
            
        return event
