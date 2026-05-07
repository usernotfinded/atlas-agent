from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any


CACHE_PATH = Path(".atlas") / "cache" / "model_roster.json"


def cache_path(workspace_dir: str | Path = ".") -> Path:
    return Path(workspace_dir).resolve() / CACHE_PATH


def read_cache(workspace_dir: str | Path = ".") -> dict[str, Any] | None:
    path = cache_path(workspace_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(payload: dict[str, Any], workspace_dir: str | Path = ".") -> Path:
    path = cache_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = _to_jsonable(payload)
    path.write_text(json.dumps(serializable, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _to_jsonable(value):
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value
