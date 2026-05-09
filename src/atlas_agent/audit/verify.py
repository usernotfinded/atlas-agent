from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from atlas_agent.audit.chain import verify_event_integrity
from atlas_agent.audit.manifest import compute_root_hash
from atlas_agent.audit.models import (
    AuditEvent, 
    VerificationResult, 
    AuditManifest, 
    ManifestVerificationResult
)


def verify_audit_log(
    audit_path: str | Path, 
    expected_event_count: Optional[int] = None,
    expected_final_hash: Optional[str] = None,
    filter_run_id: Optional[str] = None
) -> VerificationResult:
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
    last_event_hash: Optional[str] = None
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
                
                # If we are filtering by run_id (manifest verification), ignore other runs
                if filter_run_id and event.run_id != filter_run_id:
                    continue

                if not verify_event_integrity(event, previous_hash):
                    if first_error_index is None:
                        first_error_index = i
                    errors.append(f"Line {i}: Hash chain broken (event_id={event.event_id})")
                
                previous_hash = event.event_hash
                last_event_hash = event.event_hash
                events_checked += 1
                
        # Check tail deletion if expected values are provided
        if expected_event_count is not None and events_checked != expected_event_count:
            errors.append(f"Event count mismatch: expected {expected_event_count}, found {events_checked} (Tail deletion detected)")
            
        if expected_final_hash is not None and last_event_hash != expected_final_hash:
            errors.append(f"Final event hash mismatch: expected {expected_final_hash}, found {last_event_hash}")

    except Exception as e:
        errors.append(f"Failed to read audit log: {e}")
        
    return VerificationResult(
        valid=len(errors) == 0,
        events_checked=events_checked,
        first_error_index=first_error_index,
        errors=errors
    )


def verify_run_manifest(manifest_path: str | Path) -> ManifestVerificationResult:
    """
    Verify an audit manifest and its associated log file.
    """
    path = Path(manifest_path)
    if not path.exists():
        return ManifestVerificationResult(
            valid=False,
            manifest_status="missing",
            events_checked=0,
            log_integrity=VerificationResult(valid=False, events_checked=0),
            errors=[f"Manifest file not found: {path}"]
        )
        
    try:
        manifest = AuditManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:
        return ManifestVerificationResult(
            valid=False,
            manifest_status="corrupt",
            events_checked=0,
            log_integrity=VerificationResult(valid=False, events_checked=0),
            errors=[f"Failed to parse manifest: {e}"]
        )
        
    errors = []
    
    # 1. Verify root hash
    actual_root_hash = compute_root_hash(manifest)
    if manifest.root_hash != actual_root_hash:
        errors.append(f"Manifest root hash mismatch: manifest was likely modified after sealing.")
        
    # 2. Verify log integrity
    log_result = verify_audit_log(
        manifest.audit_log_path,
        expected_event_count=manifest.event_count,
        expected_final_hash=manifest.final_event_hash,
        filter_run_id=manifest.run_id
    )
    
    if not log_result.valid:
        errors.extend(log_result.errors)
        
    return ManifestVerificationResult(
        valid=len(errors) == 0,
        manifest_status=manifest.status,
        events_checked=log_result.events_checked,
        log_integrity=log_result,
        errors=errors
    )
