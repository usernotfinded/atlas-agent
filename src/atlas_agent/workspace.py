from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import tomlkit


DEFAULT_TEMPLATE = "routine-trader"
SENSITIVE_CONFIG_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


@dataclass(frozen=True)
class WorkspaceResolution:
    path: Path | None
    source: str | None
    warning: str | None
    overwritten: bool = False
    template: str | None = None


class WorkspaceInitError(RuntimeError):
    pass


def get_default_config_path() -> Path:
    return Path.home() / ".atlas" / "config.json"


def get_default_workspace() -> Path | None:
    candidate = _default_workspace_candidate()
    if candidate is None:
        return None
    if is_workspace(candidate):
        return candidate
    return None


def set_default_workspace(path: str | Path) -> None:
    target = Path(path).resolve()
    if not is_workspace(target):
        raise WorkspaceInitError(
            f"default workspace must point to a valid Atlas workspace: {target}"
        )
    data = _load_default_config()
    data["default_workspace"] = str(target)
    _write_default_config(data)


def clear_default_workspace() -> None:
    data = _load_default_config()
    if "default_workspace" not in data:
        return
    del data["default_workspace"]
    _write_default_config(data)


def is_workspace(path: Path) -> bool:
    # A workspace is identified by the presence of core directories
    return path.is_dir() and (path / "memory").exists()


def resolve_workspace_path(args_workspace: str | None = None) -> Path | None:
    return resolve_workspace(args_workspace).path


def resolve_workspace(args_workspace: str | None = None) -> WorkspaceResolution:
    # 1. CLI flag
    if args_workspace:
        candidate = Path(args_workspace).expanduser().resolve()
        if is_workspace(candidate):
            return WorkspaceResolution(path=candidate, source="flag", warning=None)
        return WorkspaceResolution(
            path=None,
            source="flag",
            warning=f"--workspace path is not a valid Atlas workspace: {candidate}",
        )

    # 2. Environment variable
    env_ws = os.getenv("ATLAS_WORKSPACE")
    if env_ws:
        candidate = Path(env_ws).expanduser().resolve()
        if is_workspace(candidate):
            return WorkspaceResolution(path=candidate, source="env", warning=None)
        return WorkspaceResolution(
            path=None,
            source="env",
            warning=f"ATLAS_WORKSPACE is set but invalid: {candidate}",
        )

    # 3. Current directory
    cwd = Path.cwd()
    if is_workspace(cwd):
        return WorkspaceResolution(path=cwd, source="cwd", warning=None)

    # 4. Saved default workspace
    default_ws = _default_workspace_candidate()
    if default_ws is not None:
        if is_workspace(default_ws):
            return WorkspaceResolution(path=default_ws, source="default", warning=None)
        return WorkspaceResolution(
            path=None,
            source="default",
            warning=f"Saved default workspace is invalid: {default_ws}",
        )

    return WorkspaceResolution(path=None, source=None, warning=None)


def _default_workspace_candidate() -> Path | None:
    data = _load_default_config()
    raw = data.get("default_workspace")
    if not raw or not isinstance(raw, str):
        return None
    return Path(raw).expanduser().resolve()


def _load_default_config() -> dict[str, Any]:
    path = get_default_config_path()
    if not path.exists():
        # Fallback to legacy config.json (if path was changed to global.toml)
        legacy_path = Path.home() / ".atlas" / "config.json"
        if legacy_path.exists() and legacy_path != path:
            try:
                parsed = json.loads(legacy_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    return parsed
            except:
                pass
        return {}
    
    try:
        if path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(path, "r", encoding="utf-8") as f:
                parsed = tomlkit.load(f)
                return dict(parsed)
    except Exception:
        return {}


def _write_default_config(data: dict[str, Any]) -> None:
    config_path = get_default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_default_config(data)
    if config_path.suffix == ".json":
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=2, sort_keys=True)
    else:
        with open(config_path, "w", encoding="utf-8") as f:
            tomlkit.dump(sanitized, f)


def _sanitize_default_config(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        key_text = str(key)
        if any(marker in key_text.upper() for marker in SENSITIVE_CONFIG_MARKERS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key_text] = value
    return sanitized


def init_workspace(
    path: str | Path,
    template: str = DEFAULT_TEMPLATE,
    force: bool = False,
) -> WorkspaceResolution:
    target_path = Path(path).expanduser().resolve()
    overwritten = False
    if is_workspace(target_path):
        if not force:
            return WorkspaceResolution(path=target_path, source="cwd", warning=None)
        overwritten = True
    
    # If not force and directory exists and is not empty, fail
    if not force and target_path.exists() and any(target_path.iterdir()):
        raise WorkspaceInitError(f"workspace path already exists and is not empty: {target_path}")

    target_path.mkdir(parents=True, exist_ok=True)
    template_source = _resolve_template(template)
    if template_source is None:
        raise WorkspaceInitError(
            f"template not found: {template}. Expected packaged resource "
            f"atlas_agent/templates/{template} or repo fallback templates/{template}."
        )

    _copy_template_tree(template_source, target_path)

    _ensure_runtime_dirs(target_path)
    return WorkspaceResolution(
        path=target_path, 
        source="init", 
        warning=None, 
        overwritten=overwritten,
        template=template
    )


def _resolve_template(template: str) -> Traversable | Path | None:
    try:
        packaged_template = resources.files("atlas_agent").joinpath("templates", template)
        if packaged_template.is_dir():
            return packaged_template
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass

    fallback = Path(__file__).parent.parent.parent / "templates" / template
    if fallback.is_dir():
        return fallback
    return None


def _copy_template_tree(source_root: Traversable | Path, target_path: Path) -> None:
    for source in source_root.iterdir():
        destination = target_path / source.name
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            _copy_template_tree(source, destination)
        elif source.is_file():
            with source.open("rb") as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _ensure_runtime_dirs(target_path: Path) -> None:
    for directory in (
        target_path / ".atlas" / "backtests",
        target_path / ".atlas" / "locks",
        target_path / ".atlas" / "safety",
        target_path / "memory" / "conversations",
        target_path / "reports" / "daily",
        target_path / "reports" / "agent",
        target_path / "reports" / "learning",
        target_path / "reports" / "reflections",
        target_path / "reports" / "weekly",
        target_path / "pending_orders",
        target_path / "audit",
        target_path / "events",
    ):
        directory.mkdir(parents=True, exist_ok=True)
