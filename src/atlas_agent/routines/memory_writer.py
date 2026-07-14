# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    routines/memory_writer.py
# PURPOSE: Appends a routine's outcome to the workspace memory.
# DEPS:    stdlib only
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def append_memory(
    memory_dir: str | Path,
    filename: str,
    heading: str,
    body: str,
) -> Path:
    directory = Path(memory_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    if not path.exists():
        title = filename.replace("_", " ").replace(".md", "").title()
        path.write_text(f"# {title}\n\n", encoding="utf-8")
    timestamp = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {heading} - {timestamp}\n\n{body.strip()}\n")
    return path


def overwrite_memory(memory_dir: str | Path, filename: str, content: str) -> Path:
    directory = Path(memory_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    return path

