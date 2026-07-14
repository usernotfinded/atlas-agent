# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    execution/audit.py
# PURPOSE: Plain append-only audit sink for the execution path. Distinct from
#          atlas_agent.audit, which is the hash-chained, tamper-evident trail —
#          this one is a simple journal with no chain and no manifest.
# DEPS:    jsonl (append), redaction (scrubbing)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.jsonl import JsonlWriter
from atlas_agent.redaction import redact_payload


# ==============================================================================
# AUDIT LOGGER
# ==============================================================================

class AuditLogger:
    def __init__(self, audit_dir: str | Path = "audit") -> None:
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.audit_dir / "audit.jsonl"
        self._writer = JsonlWriter(self.path, sort_keys=True)

    def write(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            # Scrubbed on the way in, unconditionally. Callers pass raw broker payloads
            # here, and the caller is exactly who cannot be trusted to remember.
            "payload": redact_payload(payload),
        }
        self._writer.write(record)
