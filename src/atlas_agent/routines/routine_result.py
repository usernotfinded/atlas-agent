from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RoutineResult:
    name: str
    mode: str
    status: str
    report_path: Path
    memory_files_updated: tuple[Path, ...]
    order_status: str | None = None
    notification_status: str = "not_configured"
    git_status: str = "skipped"
    lock_status: str | None = None
