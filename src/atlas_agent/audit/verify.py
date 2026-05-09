from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from atlas_agent.audit.chain import verify_event_integrity
from atlas_agent.audit.models import AuditEvent, VerificationResult


def verify_audit_log(audit_path: str | Path) -> VerificationResult:
    """
    Verify the integrity of a JSONL audit log file.
    """
    path = Path(audit_path)
    if not path.exists():
        return VerificationResult(
            valid=False,
            events_checked=0,
            errors=[f"Audit log file not found: {path}"]
        )
        
    events_checked = 0
    previous_hash: Optional[str] = None
    errors: list[str] = []
    first_error_index: Optional[int] = None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if not line.strip():
                    continue
                    
                try:
                    event = AuditEvent.model_validate_json(line)
                except Exception as e:
                    if first_error_index is None:
                        first_error_index = i
                    errors.append(f"Line {i}: Invalid JSON or event model: {e}")
                    continue
                
                if not verify_event_integrity(event, previous_hash):
                    if first_error_index is None:
                        first_error_index = i
                    errors.append(f"Line {i}: Hash chain broken (event_id={event.event_id})")
                
                previous_hash = event.event_hash
                events_checked += 1
    except Exception as e:
        errors.append(f"Failed to read audit log: {e}")
        
    return VerificationResult(
        valid=len(errors) == 0,
        events_checked=events_checked,
        first_error_index=first_error_index,
        errors=errors
    )
