from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.jsonl import JsonlWriter
from atlas_agent.redaction import redact_payload


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
            "payload": _redact(payload),
        }
        self._writer.write(record)


def _redact(value: Any) -> Any:
    return redact_payload(value)
