# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    audit/verify.py
# PURPOSE: The read half of the tamper-evidence scheme. Replays a log against its
#          manifest and reports every way the record fails to add up.
# DEPS:    audit.chain (per-event integrity), audit.manifest (root/rolling hashes)
#
# DESIGN:  Verification never raises on a bad log — a corrupt audit trail is the
#          expected input here, not an exceptional one. Failures accumulate into
#          the result so the caller sees the whole picture at once.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from atlas_agent.audit.chain import verify_event_integrity
from atlas_agent.audit.manifest import compute_root_hash, compute_event_hash_rolling_root
from atlas_agent.audit.models import (
    AuditEvent,
    VerificationResult,
    AuditManifest,
    ManifestVerificationResult
)


# ==============================================================================
# LOG VERIFICATION
# ==============================================================================

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
    event_hashes: list[str] = []

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

                # Advance the chain even on failure, so a single corrupted event does
                # not cascade into a spurious error on every line after it. We want to
                # report where the damage is, not how far it echoes.
                previous_hash = event.event_hash
                last_event_hash = event.event_hash
                events_checked += 1
                event_hashes.append(event.event_hash)

        # The hash chain alone cannot see a *truncated* log: chop off the last N
        # events and what remains is still perfectly self-consistent. Only the
        # manifest's expected count and final hash — recorded when the run sealed —
        # can reveal that the tail is gone.
        if expected_event_count is not None and events_checked != expected_event_count:
            errors.append(f"Event count mismatch: expected {expected_event_count}, found {events_checked} (Tail deletion detected)")

        if expected_final_hash is not None and last_event_hash != expected_final_hash:
            errors.append(f"Final event hash mismatch: expected {expected_final_hash}, found {last_event_hash}")

    except Exception as e:
        errors.append(f"Failed to read audit log: {e}")

    rolling_root = compute_event_hash_rolling_root(event_hashes) if event_hashes else None
    return VerificationResult(
        valid=len(errors) == 0,
        events_checked=events_checked,
        first_error_index=first_error_index,
        errors=errors,
        rolling_root=rolling_root,
    )


# ==============================================================================
# MANIFEST VERIFICATION
# ==============================================================================

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

    # Three checks, each closing a hole the others leave open. An attacker has to
    # defeat all three, and they constrain each other:
    #
    #   1. root hash    → the manifest itself was not edited after sealing.
    #      Without it, someone could simply rewrite the expected count and hashes to
    #      match a doctored log, and checks 2-3 would happily agree.
    actual_root_hash = compute_root_hash(manifest)
    if manifest.root_hash != actual_root_hash:
        errors.append("Manifest root hash mismatch: manifest was likely modified after sealing.")

    #   2. log integrity → the chain is intact AND the tail was not truncated
    #      (the count/final-hash arguments are what catch truncation).
    log_result = verify_audit_log(
        manifest.audit_log_path,
        expected_event_count=manifest.event_count,
        expected_final_hash=manifest.final_event_hash,
        filter_run_id=manifest.run_id
    )

    if not log_result.valid:
        errors.extend(log_result.errors)

    #   3. rolling root → the *middle* of the chain was not swapped out. Pinning only
    #      the first and last hashes would leave the interior replaceable wholesale.
    #      `None` means a legacy manifest predating this field: skipped rather than
    #      failed, or every historical run would be reported as tampered with.
    if manifest.event_hash_rolling_root is not None:
        if log_result.rolling_root != manifest.event_hash_rolling_root:
            errors.append(
                "Manifest rolling root mismatch: intermediate events may have been tampered with."
            )

    return ManifestVerificationResult(
        valid=len(errors) == 0,
        manifest_status=manifest.status,
        events_checked=log_result.events_checked,
        log_integrity=log_result,
        errors=errors
    )
