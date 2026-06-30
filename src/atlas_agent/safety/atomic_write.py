from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["atomic_write_text", "atomic_write_json"]


def _unique_temp_path(target: Path) -> Path:
    fd, temp_str = tempfile.mkstemp(
        dir=target.parent,
        prefix=f"{target.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    return Path(temp_str)


def _try_remove(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


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
        temp_path = _unique_temp_path(target)
        temp_path.write_text(content, encoding=encoding)
        temp_path.replace(target)
        if chmod is not None:
            try:
                target.chmod(chmod)
            except (OSError, PermissionError):
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
