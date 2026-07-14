# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    audit/writer.py
# PURPOSE: Appends events to the hash-chained audit log and maintains the per-run
#          manifest that seals it. This is the write half of the tamper-evidence
#          scheme; audit/verify.py is the read half.
# DEPS:    audit.chain (hashing), audit.manifest (sealing), audit.redaction (scrubbing)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional, Literal

from atlas_agent.audit.chain import compute_event_hash
from atlas_agent.audit.manifest import (
    compute_root_hash,
    create_initial_manifest,
    _rolling_hash_step,
)
from atlas_agent.audit.models import AuditEvent, AuditEventType, AuditManifest
from atlas_agent.audit.redaction import redact_payload

logger = logging.getLogger(__name__)


# ==============================================================================
# AUDIT WRITER
# ==============================================================================

class AuditWriter:

    # --- Lifecycle & lazy initialisation ---

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
            # Pick the chain back up where the previous process left it: seek to the
            # last line and read its hash. Scanning the whole file would be O(n) on
            # every single startup, and audit logs only grow.
            recovery_error: Exception | None = None
            try:
                with open(self.audit_path, "rb") as f:
                    try:
                        # Walk backwards to the newline before the final record.
                        # Starts at -2 to step over the trailing newline itself.
                        f.seek(-2, os.SEEK_END)
                        while f.read(1) != b"\n":
                            f.seek(-2, os.SEEK_CUR)
                    except OSError:
                        # Hit the start of the file: it holds a single line, so the
                        # backwards walk ran off the front. Read from the top instead.
                        f.seek(0)

                    last_line = f.readline().decode("utf-8")
                    if last_line:
                        last_event = AuditEvent.model_validate_json(last_line)
                        self.last_hash = last_event.event_hash
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                recovery_error = exc

            if recovery_error is not None:
                # Degrade rather than die: a corrupt tail must not stop the agent from
                # recording what happens next. The chain restarts with previous_hash=None,
                # and verify.py will report the break — evidence of the gap is preserved,
                # which is exactly what a tamper-evident log is supposed to do.
                logger.warning(
                    "Audit log recovery failed for %s (%s: %s). "
                    "Starting fresh chain; previous hash will be None.",
                    self.audit_path.name,
                    type(recovery_error).__name__,
                    recovery_error,
                )

        self._initialized = True

    # --- Run boundaries (manifest sealing) ---

    def start_run(self, run_id: str):
        self._ensure_initialized()
        self.current_run_id = run_id
        self.current_manifest = create_initial_manifest(run_id, str(self.audit_path))
        # Each run starts its own chain. Runs are the unit of verification, so a
        # run's manifest must be checkable on its own without replaying the entire
        # history of the log file it happens to share.
        self.last_hash = None # Start new chain for this run
        # Written before any event: an interrupted run then leaves a manifest with
        # status != "completed", which is itself the evidence that it was cut short.
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
        # The root hash seals the manifest: computed last, over the now-final counts
        # and hashes, so any later edit to the manifest itself becomes detectable.
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

    # --- Event append (the hot path) ---

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
            # Redaction happens BEFORE hashing, so the hash covers the redacted form.
            # Scrubbing afterwards would change the bytes and break the chain — the
            # log would be unverifiable and the secret would already be on disk.
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
            # First/final hashes alone would only pin the ends of the chain, leaving
            # the middle swappable. The rolling root folds every event hash in, so
            # the manifest commits to the whole sequence, not just its endpoints.
            prev = self.current_manifest.event_hash_rolling_root
            self.current_manifest.event_hash_rolling_root = _rolling_hash_step(
                prev, event.event_hash
            )

        # Append-only: the log is never rewritten in place, which is what lets the
        # chain stand as evidence rather than as a mutable record.
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

        return event
