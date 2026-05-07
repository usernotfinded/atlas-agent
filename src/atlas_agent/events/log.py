from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from atlas_agent.events.schema import validate_event_record


SECRET_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")
BEARER_TOKEN_RE = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


def generate_run_id() -> str:
    return uuid4().hex


class EventLogger:
    def __init__(self, events_dir: str | Path = "events") -> None:
        self.events_dir = Path(events_dir)
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def path_for_day(self, day: date | None = None) -> Path:
        effective_day = day or datetime.now(UTC).date()
        return self.events_dir / f"{effective_day.isoformat()}.jsonl"

    def write(
        self,
        event_type: str,
        *,
        run_id: str,
        command: str,
        mode: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "event_type": event_type,
            "run_id": run_id,
            "command": command,
            "mode": mode,
            "payload": _redact(payload or {}),
        }
        errors = validate_event_record(record)
        if errors:
            raise ValueError(f"invalid event record: {', '.join(errors)}")
        with self.path_for_day().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def list_event_files(events_dir: str | Path = "events") -> list[Path]:
    base = Path(events_dir)
    if not base.exists():
        return []
    return sorted(path for path in base.glob("*.jsonl") if path.is_file())


def read_event_file(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{target}:{line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{target}:{line_no}: event must be a JSON object")
        events.append(parsed)
    return events


def read_recent_events(events_dir: str | Path = "events", *, limit: int = 50) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    all_events: list[dict[str, Any]] = []
    for path in reversed(list_event_files(events_dir)):
        events = read_event_file(path)
        all_events[0:0] = events
        if len(all_events) >= limit:
            break
    if len(all_events) > limit:
        return all_events[-limit:]
    return all_events


def latest_event_file(events_dir: str | Path = "events") -> Path | None:
    files = list_event_files(events_dir)
    if not files:
        return None
    return files[-1]


def _redact(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_upper = str(key).upper()
            if any(marker in key_upper for marker in SECRET_MARKERS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, str):
        return BEARER_TOKEN_RE.sub(r"\1[REDACTED]", value)
    return value
