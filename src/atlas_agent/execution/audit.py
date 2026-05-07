from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


SECRET_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


class AuditLogger:
    def __init__(self, audit_dir: str | Path = "audit") -> None:
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.audit_dir / "audit.jsonl"

    def write(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": _redact(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _redact(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).upper()
            if any(marker in key_text for marker in SECRET_MARKERS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value
