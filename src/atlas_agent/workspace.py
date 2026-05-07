import json
import os
import shutil
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TEMPLATE = "routine-trader"
SENSITIVE_CONFIG_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")
MANAGED_TEMPLATE_PATHS = (
    "memory",
    "routines",
    "skills",
    "reports",
    "pending_orders",
    "audit",
    "events",
    "configs",
    ".env.example",
    ".gitignore",
    "README.md",
)


class WorkspaceInitError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceInitResult:
    path: Path
    template: str
    overwritten: bool = False


@dataclass(frozen=True)
class WorkspaceResolution:
    path: Path | None
    source: str | None
    warning: str | None = None


def init_workspace(
    target: str | Path,
    *,
    template: str = DEFAULT_TEMPLATE,
    force: bool = False,
) -> WorkspaceInitResult:
    target_path = Path(target).resolve()
    template_path = resolve_template_path(template)
    if target_path.exists() and not target_path.is_dir():
        raise WorkspaceInitError(f"target exists and is not a directory: {target_path}")

    had_contents = target_path.exists() and any(target_path.iterdir())
    if had_contents and not force:
        raise WorkspaceInitError(
            f"target directory is not empty: {target_path}; pass --force to overwrite"
        )

    target_path.mkdir(parents=True, exist_ok=True)
    if force:
        _remove_managed_paths(target_path)

    for source in template_path.iterdir():
        destination = target_path / source.name
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source, destination)

    _ensure_runtime_dirs(target_path)
    return WorkspaceInitResult(
        path=target_path,
        template=template,
        overwritten=had_contents and force,
    )


def resolve_template_path(template: str) -> Path:
    if template != DEFAULT_TEMPLATE:
        raise WorkspaceInitError(f"unknown template: {template}")
    candidates = (
        Path.cwd() / "templates" / template,
        Path(__file__).resolve().parents[2] / "templates" / template,
        Path(sysconfig.get_path("data"))
        / "share"
        / "atlas-agent"
        / "templates"
        / template,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise WorkspaceInitError(f"template not found: {template}")


def _remove_managed_paths(target_path: Path) -> None:
    for relative in MANAGED_TEMPLATE_PATHS:
        path = target_path / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _ensure_runtime_dirs(target_path: Path) -> None:
    for directory in (
        target_path / "reports" / "daily",
        target_path / "reports" / "weekly",
        target_path / "reports" / "learning",
        target_path / "reports" / "reflections",
        target_path / "pending_orders",
        target_path / "audit",
        target_path / "events",
        target_path / "skills" / "active",
        target_path / "skills" / "proposed",
        target_path / "skills" / "archived",
        target_path / "memory" / "conversations",
    ):
        directory.mkdir(parents=True, exist_ok=True)


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
    return (path / "memory").exists() and (
        (path / "configs").exists() or (path / "routines").exists()
    )


def resolve_workspace_path(args_workspace: str | None = None) -> Path | None:
    return resolve_workspace(args_workspace).path


def resolve_workspace(args_workspace: str | None = None) -> WorkspaceResolution:
    # 1. CLI flag
    if args_workspace:
        candidate = Path(args_workspace).expanduser().resolve()
        if is_workspace(candidate):
            return WorkspaceResolution(path=candidate, source="flag")
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
            return WorkspaceResolution(path=candidate, source="env")
        return WorkspaceResolution(
            path=None,
            source="env",
            warning=f"ATLAS_WORKSPACE is set but invalid: {candidate}",
        )

    # 3. Current directory
    cwd = Path.cwd()
    if is_workspace(cwd):
        return WorkspaceResolution(path=cwd, source="cwd")

    # 4. Saved default workspace
    default_ws = _default_workspace_candidate()
    if default_ws is not None:
        if is_workspace(default_ws):
            return WorkspaceResolution(path=default_ws, source="default")
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
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _write_default_config(data: dict[str, Any]) -> None:
    config_path = get_default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_default_config(data)
    config_path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")


def _sanitize_default_config(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        key_text = str(key)
        if any(marker in key_text.upper() for marker in SENSITIVE_CONFIG_MARKERS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key_text] = value
    return sanitized
