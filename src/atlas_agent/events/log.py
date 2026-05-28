from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from atlas_agent.events.schema import validate_event_record
from atlas_agent.jsonl import tail_jsonl, write_jsonl
from atlas_agent.redaction import redact_payload


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
            "payload": redact_payload(payload or {}),
        }
        # Final pass immediately before writing any event record.
        record = redact_payload(record)
        errors = validate_event_record(record)
        if errors:
            raise ValueError(f"invalid event record: {', '.join(errors)}")
        write_jsonl(self.path_for_day(), record, sort_keys=True)


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
    recent_events: list[dict[str, Any]] = []
    for path in reversed(list_event_files(events_dir)):
        remaining = limit - len(recent_events)
        events = tail_jsonl(path, remaining)
        recent_events[0:0] = events
        if len(recent_events) >= limit:
            break
    if len(recent_events) > limit:
        return recent_events[-limit:]
    return recent_events


def latest_event_file(events_dir: str | Path = "events") -> Path | None:
    files = list_event_files(events_dir)
    if not files:
        return None
    return files[-1]
