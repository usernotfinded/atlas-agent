# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    workspace.py
# PURPOSE: Answers "which workspace am I operating on?" and creates new ones from
#          templates. Every command depends on this: pick the wrong workspace and
#          the agent trades against the wrong config, portfolio and audit trail.
# DEPS:    tomlkit (global config), importlib.resources (packaged templates)
# ==============================================================================

# --- IMPORTS ---
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


# --- CONFIGURATIONS & CONSTANTS ---

DEFAULT_TEMPLATE = "routine-trader"

# The global config is written to disk in the clear, so secret-looking keys are
# stripped on the way out. See _sanitize_default_config().
SENSITIVE_CONFIG_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


# ==============================================================================
# MODELS
# ==============================================================================

@dataclass(frozen=True)
class WorkspaceResolution:
    # `path=None` with a non-None `warning` is the "found something, rejected it"
    # case — distinct from `path=None, warning=None`, which means "nothing found".
    # Callers rely on that distinction to decide whether to complain or to offer
    # `atlas init`.
    path: Path | None
    source: str | None
    warning: str | None
    overwritten: bool = False
    template: str | None = None


class WorkspaceInitError(RuntimeError):
    pass


# ==============================================================================
# GLOBAL DEFAULT WORKSPACE
# ==============================================================================

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


# ==============================================================================
# WORKSPACE RESOLUTION
# ==============================================================================

def is_workspace(path: Path) -> bool:
    # `memory/` is the marker directory: it is the one thing every template creates
    # and no bare directory has by accident.
    return path.is_dir() and (path / "memory").exists()


def resolve_workspace_path(args_workspace: str | None = None) -> Path | None:
    return resolve_workspace(args_workspace).path


def resolve_workspace(args_workspace: str | None = None) -> WorkspaceResolution:
    """Resolve the active workspace using a fixed precedence chain.

    Args:
        args_workspace: the value of the --workspace flag, if the user passed one.

    Returns:
        A WorkspaceResolution naming the winning source, or carrying a warning if a
        source was configured but pointed somewhere invalid.
    """
    # Precedence runs explicit → ambient. Note that an *invalid* source at any tier
    # stops the chain and returns a warning, instead of silently falling through to
    # the next one: if you passed --workspace and it was wrong, quietly trading
    # against the cwd instead would be the worst possible outcome.

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


# ==============================================================================
# GLOBAL CONFIG FILE I/O
# ==============================================================================

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
            except Exception:
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
        # A corrupt global config degrades to "no default workspace" rather than
        # taking down every `atlas` invocation on the machine. The user can still
        # pass --workspace, and `set_default_workspace` will rewrite the file clean.
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
    # Allowlist, not blocklist. Two independent filters:
    #   - secret-looking keys are dropped outright;
    #   - only scalars survive, so no nested structure can smuggle a credential
    #     past the key check inside a dict or list value.
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        key_text = str(key)
        if any(marker in key_text.upper() for marker in SENSITIVE_CONFIG_MARKERS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key_text] = value
    return sanitized


# ==============================================================================
# WORKSPACE CREATION
# ==============================================================================

def init_workspace(
    path: str | Path,
    template: str = DEFAULT_TEMPLATE,
    force: bool = False,
) -> WorkspaceResolution:
    target_path = Path(path).expanduser().resolve()
    overwritten = False

    # Re-initialising an existing workspace without --force is a no-op, not an
    # error: `atlas init` has to stay idempotent so it can be run from a setup
    # script without guarding it.
    if is_workspace(target_path):
        if not force:
            return WorkspaceResolution(path=target_path, source="cwd", warning=None)
        overwritten = True

    # A non-empty directory that is *not* a workspace is someone else's data. We
    # refuse rather than scatter template files into it.
    if not force and target_path.exists() and any(target_path.iterdir()):
        raise WorkspaceInitError(f"workspace path already exists and is not empty: {target_path}")

    target_path.mkdir(parents=True, exist_ok=True)
    template_source = _resolve_template(template)
    if template_source is None:
        raise WorkspaceInitError(
            f"Template '{template}' not found. "
            "Ensure atlas_agent is installed with package data "
            f"(src/atlas_agent/templates/{template})."
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


# --- Template plumbing ---

def _resolve_template(template: str) -> Traversable | Path | None:
    # Two lookups because the two deployment shapes differ: importlib.resources is
    # the only thing that works from an installed wheel (the template may live
    # inside a zip), while the __file__-relative path is what works in an editable
    # checkout where package data was never staged.
    try:
        packaged_template = resources.files("atlas_agent").joinpath("templates", template)
        if packaged_template.is_dir():
            return packaged_template
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass

    fallback = Path(__file__).parent / "templates" / template
    if fallback.is_dir():
        return fallback
    return None


def _copy_template_tree(source_root: Traversable | Path, target_path: Path) -> None:
    # Hand-rolled instead of shutil.copytree because the source may be a Traversable
    # backed by a zipped wheel, which has no filesystem path for copytree to walk.
    for source in source_root.iterdir():
        destination = target_path / source.name
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            _copy_template_tree(source, destination)
        elif source.is_file():
            with source.open("rb") as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _ensure_runtime_dirs(target_path: Path) -> None:
    # Created eagerly rather than lazily at first write. Templates ship no empty
    # directories (git cannot track them), and a missing audit/ or events/ dir on
    # the write path would mean losing the very record that explains the failure.
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
