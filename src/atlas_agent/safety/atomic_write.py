# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/atomic_write.py
# PURPOSE: Write-or-don't file writes. Every piece of safety state — the kill
#          switch, the heartbeat, the deadman — goes through here, because a
#          half-written safety file is worse than no file at all: it reads as
#          "disarmed" to a parser that cannot tell truncation from intent.
# DEPS:    stdlib only (tempfile, os, json)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["atomic_write_text", "atomic_write_json"]


# --- Temp-file plumbing ---

def _unique_temp_path(target: Path) -> Path:
    # Same directory as the target, because os.replace() is only atomic *within* a
    # filesystem — a temp file in /tmp could land on another volume and silently
    # degrade the rename into a copy.
    # mkstemp also creates the file 0600, so the content is never briefly world-
    # readable while it is being written.
    fd, temp_str = tempfile.mkstemp(
        dir=target.parent,
        prefix=f"{target.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    return Path(temp_str)


def _try_remove(path: Path | None) -> None:
    # Swallowing OSError is intentional: after a successful replace() the temp path
    # is already gone, so failing to unlink it is the normal case, not an error.
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


# ==============================================================================
# ATOMIC WRITES
# ==============================================================================

def atomic_write_text(
    target: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    chmod: int | None = None,
    ensure_parent: bool = True,
) -> Path:
    target = Path(target)
    if ensure_parent:
        target.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        # Write fully to the side, then swap in one atomic rename. A reader either
        # sees the whole old file or the whole new one — never a torn mix of both.
        temp_path = _unique_temp_path(target)
        temp_path.write_text(content, encoding=encoding)
        temp_path.replace(target)
        # chmod after the swap. Safe because the temp file was already created 0600
        # by mkstemp, so we widen permissions here, never narrow them from a
        # temporarily-open state.
        if chmod is not None:
            try:
                target.chmod(chmod)
            except (OSError, PermissionError):
                # A filesystem that cannot chmod (a mounted share, Windows) must not
                # fail the write: the content is already safely in place.
                pass
    finally:
        # Best-effort cleanup in both success and failure paths. A leftover temp
        # file does not affect target safety because replace happens only after a
        # successful write.
        _try_remove(temp_path)

    return target


def atomic_write_json(
    target: str | Path,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    encoding: str = "utf-8",
    chmod: int | None = None,
    ensure_parent: bool = True,
) -> Path:
    content = json.dumps(payload, indent=indent, sort_keys=sort_keys)
    return atomic_write_text(
        target,
        content,
        encoding=encoding,
        chmod=chmod,
        ensure_parent=ensure_parent,
    )
