# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    update/manager.py
# PURPOSE: Performs the self-update. Gated by update/safety.py, which decides
#          whether replacing the running code is safe right now — the answer is no
#          while there are open positions or pending orders.
# DEPS:    update.safety (the gate), update.sources, update.state
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from atlas_agent import __version__
from atlas_agent.config import AtlasConfig
from atlas_agent.update.safety import (
    RuntimeUpdateSafetyCheck,
    UpdateSafetyCheck,
    UpdateSafetyResult,
    evaluate_update_safety,
)
from atlas_agent.update.sources import (
    AvailableUpdate,
    GitHubReleaseSource,
    PyPIReleaseSource,
    UpdateSource,
    discover_github_repo,
    is_version_newer,
)
from atlas_agent.update.state import UpdateState, UpdateStateStore, utc_now_iso


@dataclass(frozen=True)
class UpdateCheckReport:
    current_version: str
    latest_version: str | None
    source: str | None
    notes: str | None
    update_available: bool
    checked_at: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpdateStatusReport:
    current_version: str
    last_checked_at: str | None
    latest_version: str | None
    latest_source: str | None
    auto_apply_enabled: bool
    auto_check_schedule: str
    safe_to_apply: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class UpdateApplyReport:
    applied: bool
    rolled_back: bool
    message: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


SENSITIVE_FILES = {
    ".env",
    ".env.atlas",
    ".env.local",
    ".atlas/config.json",
    ".atlas/config.toml",
}


class SafeUpdateManager:
    def __init__(
        self,
        *,
        config: AtlasConfig,
        workspace_root: str | Path,
        state_path: str | Path | None = None,
        sources: list[UpdateSource] | None = None,
        safety_check: UpdateSafetyCheck | None = None,
        repo_root: str | Path | None = None,
        pypi_package_name: str | None = None,
        command_runner: Callable[[list[str], Path], subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.config = config
        self.workspace_root = Path(workspace_root)
        self.repo_root = Path(repo_root) if repo_root is not None else self.workspace_root
        self.state_store = UpdateStateStore(state_path or (self.workspace_root / ".atlas_update_state.json"))
        self.command_runner = command_runner or _run_command
        self.sources = sources or self._build_default_sources(
            pypi_package_name=pypi_package_name,
        )
        self.safety_check = safety_check or RuntimeUpdateSafetyCheck(
            config=config,
            workspace_root=self.workspace_root,
            repo_root=self.repo_root,
        )

    def check(self) -> UpdateCheckReport:
        state = self._load_state()
        warnings: list[str] = []
        best: AvailableUpdate | None = None

        for source in self.sources:
            try:
                candidate = source.check(state.current_version)
            except Exception as exc:
                warnings.append(f"{source.name} check failed: {exc}")
                continue
            if candidate is None:
                continue
            if best is None or is_version_newer(candidate.latest_version, best.latest_version):
                best = candidate

        checked_at = utc_now_iso()
        state.last_checked_at = checked_at
        if best is None:
            state.latest_version = state.current_version
            state.latest_source = None
            state.latest_notes = None
            update_available = False
        else:
            state.latest_version = best.latest_version
            state.latest_source = best.source
            state.latest_notes = best.notes
            update_available = is_version_newer(best.latest_version, state.current_version)
        self.state_store.save(state)
        return UpdateCheckReport(
            current_version=state.current_version,
            latest_version=state.latest_version,
            source=state.latest_source,
            notes=state.latest_notes,
            update_available=update_available,
            checked_at=checked_at,
            warnings=tuple(warnings),
        )

    def status(self) -> UpdateStatusReport:
        state = self._load_state()
        safety = evaluate_update_safety(self.safety_check)
        return UpdateStatusReport(
            current_version=state.current_version,
            last_checked_at=state.last_checked_at,
            latest_version=state.latest_version,
            latest_source=state.latest_source,
            auto_apply_enabled=state.auto_apply_enabled,
            auto_check_schedule=state.auto_check_schedule,
            safe_to_apply=safety.safe,
            blockers=tuple(safety.blockers),
            warnings=tuple(safety.warnings),
        )

    def configure(
        self,
        *,
        auto_check: str | None = None,
        auto_apply: bool | None = None,
    ) -> UpdateState:
        state = self._load_state()
        if auto_check is not None:
            state.auto_check_schedule = auto_check
        if auto_apply is not None:
            state.auto_apply_enabled = auto_apply
        self.state_store.save(state)
        return state

    def _is_sensitive(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self.workspace_root)
            return str(rel) in SENSITIVE_FILES or rel.name.startswith(".env.")
        except ValueError:
            return False

    def apply(self, *, force: bool = False, auto: bool = False) -> UpdateApplyReport:
        state = self._load_state()
        safety = evaluate_update_safety(self.safety_check)
        blockers = list(safety.blockers)
        warnings = list(safety.warnings)

        # Check for sensitive files in git if applicable
        if self._is_git_repo() and not force:
            sensitive_changes = self._get_git_sensitive_changes()
            if sensitive_changes:
                for f in sensitive_changes:
                    blockers.append(f"update would overwrite sensitive file: {f}")
                    warnings.append(f"Preserved local secrets file: {f}")
                warnings.append("Skipped sensitive file during update due to local protection.")

        if auto and not state.auto_apply_enabled:
            return UpdateApplyReport(
                applied=False,
                rolled_back=False,
                message="auto-apply is disabled",
                blockers=tuple(blockers),
                warnings=tuple(warnings),
            )

        if blockers and not force:
            return UpdateApplyReport(
                applied=False,
                rolled_back=False,
                message="update apply refused by safety checks",
                blockers=tuple(blockers),
                warnings=tuple(warnings),
            )
        if blockers and force:
            warnings.append("FORCE applied: bypassing safety blockers")

        check_report = self.check()
        if not check_report.update_available:
            return UpdateApplyReport(
                applied=False,
                rolled_back=False,
                message="already up to date",
                blockers=tuple(blockers),
                warnings=tuple(warnings + list(check_report.warnings)),
            )

        state = self._load_state()
        state.last_update_attempt_at = utc_now_iso()
        state.previous_version = state.current_version
        is_git_repo = self._is_git_repo()
        state.previous_git_commit = self._git_head_commit() if is_git_repo else None
        self.state_store.save(state)

        rolled_back = False
        try:
            if is_git_repo:
                previous_commit = state.previous_git_commit
                if previous_commit:
                    self._create_git_backup(previous_commit)
                    state.rollback_available = True
                self.state_store.save(state)
                self._git_pull_ff_only()
            else:
                backup_path = self._create_filesystem_backup()
                state.backup_path = str(backup_path)
                state.rollback_available = True
                self.state_store.save(state)
                self._pip_upgrade()

            if not self.safety_check.smoke_check():
                raise RuntimeError("smoke check failed after update")

            refreshed = self._load_state()
            refreshed.current_version = _read_local_version(self.workspace_root)
            refreshed.last_successful_update_at = utc_now_iso()
            refreshed.last_error = None
            self.state_store.save(refreshed)

            return UpdateApplyReport(
                applied=True,
                rolled_back=False,
                message="update applied successfully",
                blockers=tuple(blockers),
                warnings=tuple(warnings + list(check_report.warnings)),
            )
        except Exception as exc:
            warnings.append(f"apply failed: {exc}")
            rollback_message = ""
            if state.rollback_available:
                try:
                    rollback_message = self._rollback_internal(state)
                    rolled_back = True
                except Exception as rollback_exc:
                    warnings.append(f"rollback failed: {rollback_exc}")

            failed = self._load_state()
            failed.last_error = str(exc)
            self.state_store.save(failed)
            message = "update failed"
            if rollback_message:
                message = f"{message}; {rollback_message}"
            return UpdateApplyReport(
                applied=False,
                rolled_back=rolled_back,
                message=message,
                blockers=tuple(blockers),
                warnings=tuple(warnings + list(check_report.warnings)),
            )

    def rollback(self, *, confirm: bool) -> UpdateApplyReport:
        state = self._load_state()
        if not confirm:
            return UpdateApplyReport(
                applied=False,
                rolled_back=False,
                message="rollback refused: pass --yes to confirm",
                blockers=(),
                warnings=(),
            )
        if not state.rollback_available:
            return UpdateApplyReport(
                applied=False,
                rolled_back=False,
                message="rollback is not available",
                blockers=(),
                warnings=(),
            )
        if self.safety_check.has_uncommitted_changes():
            return UpdateApplyReport(
                applied=False,
                rolled_back=False,
                message="rollback refused: working tree has uncommitted changes",
                blockers=("working tree has uncommitted changes",),
                warnings=(),
            )

        message = self._rollback_internal(state)
        refreshed = self._load_state()
        refreshed.current_version = _read_local_version(self.workspace_root)
        refreshed.rollback_available = False
        refreshed.last_error = None
        self.state_store.save(refreshed)
        return UpdateApplyReport(
            applied=True,
            rolled_back=True,
            message=message,
            blockers=(),
            warnings=(),
        )

    def _load_state(self) -> UpdateState:
        return self.state_store.load(current_version=_read_local_version(self.workspace_root))

    def _build_default_sources(self, *, pypi_package_name: str | None) -> list[UpdateSource]:
        resolved_sources: list[UpdateSource] = []
        repo = discover_github_repo(self.repo_root)
        if repo:
            resolved_sources.append(GitHubReleaseSource(repo=repo))
        package_name = pypi_package_name or os.getenv("ATLAS_UPDATE_PYPI_PACKAGE")
        if package_name:
            resolved_sources.append(PyPIReleaseSource(package_name=package_name))
        return resolved_sources

    def _get_git_sensitive_changes(self) -> list[str]:
        # Fetch first to ensure we know about remote changes
        self.command_runner(["git", "fetch"], self.repo_root)
        
        # Check diff between HEAD and origin/main (or current tracking branch)
        # For simplicity, we compare with the upstream branch
        result = self.command_runner(
            ["git", "diff", "--name-only", "HEAD", "@{u}"],
            self.repo_root,
        )
        if result.returncode != 0:
            return []
            
        changed_files = result.stdout.strip().splitlines()
        sensitive = []
        for f in changed_files:
            path = self.repo_root / f
            if self._is_sensitive(path):
                sensitive.append(f)
        return sensitive

    def _is_git_repo(self) -> bool:
        result = self.command_runner(["git", "rev-parse", "--is-inside-work-tree"], self.repo_root)
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _git_head_commit(self) -> str | None:
        result = self.command_runner(["git", "rev-parse", "HEAD"], self.repo_root)
        if result.returncode != 0:
            return None
        commit = result.stdout.strip()
        return commit or None

    def _create_git_backup(self, commit: str) -> None:
        backup_name = f"backup/atlas-update-{utc_now_iso().replace(':', '').replace('+00:00', 'Z')}"
        self.command_runner(["git", "branch", backup_name, commit], self.repo_root)

    def _git_pull_ff_only(self) -> None:
        result = self.command_runner(["git", "pull", "--ff-only"], self.repo_root)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git pull failed")

    def _create_filesystem_backup(self) -> Path:
        backup_root = self.workspace_root / ".atlas_update_backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = utc_now_iso().replace(":", "").replace("+00:00", "Z")
        backup_path = backup_root / timestamp
        backup_path.mkdir(parents=True, exist_ok=True)
        source_tree = self.workspace_root / "src"
        if source_tree.exists():
            shutil.copytree(source_tree, backup_path / "src")
        pyproject = self.workspace_root / "pyproject.toml"
        if pyproject.exists():
            shutil.copy2(pyproject, backup_path / "pyproject.toml")
        return backup_path

    def _pip_upgrade(self) -> None:
        package_name = os.getenv("ATLAS_UPDATE_PYPI_PACKAGE")
        if not package_name:
            raise RuntimeError("non-git updates require ATLAS_UPDATE_PYPI_PACKAGE")
        result = self.command_runner(
            [sys.executable, "-m", "pip", "install", "--upgrade", package_name],
            self.workspace_root,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "pip upgrade failed")

    def _rollback_internal(self, state: UpdateState) -> str:
        if self._is_git_repo() and state.previous_git_commit:
            result = self.command_runner(
                ["git", "reset", "--hard", state.previous_git_commit],
                self.repo_root,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "git rollback failed")
            return f"rolled back to {state.previous_git_commit}"
        if state.backup_path:
            backup = Path(state.backup_path)
            if not backup.exists():
                raise RuntimeError(f"backup path does not exist: {backup}")
            backup_src = backup / "src"
            target_src = self.workspace_root / "src"
            if backup_src.exists():
                if target_src.exists():
                    shutil.rmtree(target_src)
                shutil.copytree(backup_src, target_src)
            backup_pyproject = backup / "pyproject.toml"
            if backup_pyproject.exists():
                shutil.copy2(backup_pyproject, self.workspace_root / "pyproject.toml")
            return f"restored backup from {backup}"
        raise RuntimeError("rollback data unavailable")


def _run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _read_local_version(workspace_root: Path) -> str:
    init_file = workspace_root / "src" / "atlas_agent" / "__init__.py"
    if init_file.exists():
        text = init_file.read_text(encoding="utf-8")
        marker = "__version__ = "
        for line in text.splitlines():
            if line.startswith(marker):
                value = line[len(marker) :].strip().strip('"').strip("'")
                if value:
                    return value
    return __version__
