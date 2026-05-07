from __future__ import annotations

import shutil
import sysconfig
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TEMPLATE = "routine-trader"
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


def init_workspace(
    target: str | Path,
    *,
    template: str = DEFAULT_TEMPLATE,
    force: bool = False,
) -> WorkspaceInitResult:
    target_path = Path(target)
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
