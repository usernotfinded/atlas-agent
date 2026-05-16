from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from typing import Any


class JsonlWriter:
    def __init__(self, path: str | Path, *, sort_keys: bool = True) -> None:
        self.path = Path(path)
        self.sort_keys = sort_keys

    def write(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=self.sort_keys) + "\n")


def write_jsonl(path: str | Path, record: dict[str, Any], *, sort_keys: bool = True) -> None:
    JsonlWriter(path, sort_keys=sort_keys).write(record)


def tail_lines(path: str | Path, limit: int) -> list[str]:
    target = Path(path)
    if limit <= 0 or not target.exists():
        return []

    lines: deque[str] = deque(maxlen=limit)
    with target.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        buffer = b""
        chunk_size = 8192

        while position > 0 and len(lines) < limit:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            buffer = handle.read(read_size) + buffer
            parts = buffer.splitlines()
            if position > 0:
                buffer = parts[0]
                parts = parts[1:]
            else:
                buffer = b""
            for raw in reversed(parts):
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    lines.appendleft(line)
                    if len(lines) >= limit:
                        break

        if buffer and len(lines) < limit:
            line = buffer.decode("utf-8", errors="replace").strip()
            if line:
                lines.appendleft(line)

    return list(lines)[-limit:]


def tail_jsonl(path: str | Path, limit: int) -> list[dict[str, Any]]:
    target = Path(path)
    events: list[dict[str, Any]] = []
    for raw_line in tail_lines(target, limit):
        try:
            parsed = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{target}: invalid JSON in tailed JSONL: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{target}: tailed JSONL event must be a JSON object")
        events.append(parsed)
    return events
