from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from atlas_agent.audit.chain import compute_event_hash
from atlas_agent.audit.models import AuditEvent, AuditEventType
from atlas_agent.audit.redaction import redact_payload


class AuditWriter:
    def __init__(self, audit_path: str | Path):
        self.audit_path = Path(audit_path)
        self.last_hash: Optional[str] = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
            
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        
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
        
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
            
        return event
