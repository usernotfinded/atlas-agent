from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def write_report(name: str, content: str, output_dir: str | Path = "reports") -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}-{datetime.now(UTC).date().isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    return path

