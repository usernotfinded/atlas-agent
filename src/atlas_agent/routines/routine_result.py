# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    routines/routine_result.py
# PURPOSE: What a routine reports back. Structured because nobody is watching an
#          unattended run — the result IS the only record anyone will read.
# DEPS:    stdlib only
# ==============================================================================

# --- IMPORTS ---
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
