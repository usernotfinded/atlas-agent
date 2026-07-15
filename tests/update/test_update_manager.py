# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/update/test_update_manager.py
# PURPOSE: Verifies update manager behavior and regression expectations.
# DEPS:    os, subprocess, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from atlas_agent.config import AtlasConfig
from atlas_agent.update.manager import SafeUpdateManager
from atlas_agent.update.safety import UpdateSafetyCheck
from atlas_agent.update.sources import AvailableUpdate, UpdateSource


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class StubSource(UpdateSource):
    def __init__(self, name: str, result: AvailableUpdate | None = None, error: Exception | None = None) -> None:
        self.name = name
        self._result = result
        self._error = error

    def check(self, current_version: str) -> AvailableUpdate | None:
        if self._error is not None:
            raise self._error
        return self._result


class StubSafety(UpdateSafetyCheck):
    def __init__(
        self,
        *,
        live: bool = False,
        open_positions: bool = False,
        pending_orders: bool = False,
        dirty_tree: bool = False,
        kill_switch: bool = True,
        smoke_ok: bool = True,
    ) -> None:
        self.live = live
        self.open_positions = open_positions
        self.pending_orders = pending_orders
        self.dirty_tree = dirty_tree
        self.kill_switch = kill_switch
        self.smoke_ok = smoke_ok

    def is_live_trading_enabled(self) -> bool:
        return self.live

    def has_open_positions(self) -> bool:
        return self.open_positions

    def has_pending_orders(self) -> bool:
        return self.pending_orders

    def has_uncommitted_changes(self) -> bool:
        return self.dirty_tree

    def kill_switch_available(self) -> bool:
        return self.kill_switch

    def smoke_check(self) -> bool:
        return self.smoke_ok


def make_config(root: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=root / "memory",
        pending_orders_dir=root / "pending_orders",
        reports_dir=root / "reports",
        events_dir=root / "events",
        audit_dir=root / "audit",
    )


def test_check_detects_no_update(tmp_path: Path) -> None:
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[StubSource("none", result=None)],
        safety_check=StubSafety(),
    )
    report = manager.check()
    assert not report.update_available
    assert report.latest_version == report.current_version


def test_check_detects_newer_version(tmp_path: Path) -> None:
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[
            StubSource(
                "new",
                result=AvailableUpdate(
                    latest_version="9.9.9",
                    source="test-source",
                    notes="release notes",
                ),
            )
        ],
        safety_check=StubSafety(),
    )
    report = manager.check()
    assert report.update_available
    assert report.latest_version == "9.9.9"
    assert report.source == "test-source"


def test_check_handles_source_failure_gracefully(tmp_path: Path) -> None:
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[StubSource("broken", error=RuntimeError("network down"))],
        safety_check=StubSafety(),
    )
    report = manager.check()
    assert not report.update_available
    assert report.warnings
    assert "network down" in report.warnings[0]


def test_apply_refuses_when_live_trading_enabled(tmp_path: Path) -> None:
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[],
        safety_check=StubSafety(live=True),
    )
    report = manager.apply()
    assert not report.applied
    assert "live trading is enabled" in report.blockers


def test_apply_refuses_when_open_positions_exist(tmp_path: Path) -> None:
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[],
        safety_check=StubSafety(open_positions=True),
    )
    report = manager.apply()
    assert not report.applied
    assert "broker has open positions" in report.blockers


def test_apply_refuses_when_pending_orders_exist(tmp_path: Path) -> None:
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[],
        safety_check=StubSafety(pending_orders=True),
    )
    report = manager.apply()
    assert not report.applied
    assert "broker has pending orders" in report.blockers


def test_apply_refuses_when_working_tree_dirty(tmp_path: Path) -> None:
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[],
        safety_check=StubSafety(dirty_tree=True),
    )
    report = manager.apply()
    assert not report.applied
    assert "working tree has uncommitted changes" in report.blockers


def test_apply_succeeds_when_safety_checks_pass(tmp_path: Path, monkeypatch) -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr="")
        if command[:5] == [os.sys.executable, "-m", "pip", "install", "--upgrade"]:
            return subprocess.CompletedProcess(command, returncode=0, stdout="ok", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setenv("ATLAS_UPDATE_PYPI_PACKAGE", "atlas-agent")
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[
            StubSource(
                "new",
                result=AvailableUpdate(latest_version="9.9.9", source="test"),
            )
        ],
        safety_check=StubSafety(smoke_ok=True),
        command_runner=fake_runner,
    )
    report = manager.apply()
    assert report.applied
    assert not report.rolled_back


def test_rollback_restores_previous_version_metadata(tmp_path: Path) -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return subprocess.CompletedProcess(command, returncode=0, stdout="true\n", stderr="")
        if command[:2] == ["git", "reset"]:
            return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[],
        safety_check=StubSafety(),
        command_runner=fake_runner,
    )
    state = manager.state_store.load(current_version="0.1.0")
    state.rollback_available = True
    state.previous_git_commit = "abc123"
    manager.state_store.save(state)

    report = manager.rollback(confirm=True)
    assert report.rolled_back
    saved = manager.state_store.load(current_version="0.1.0")
    assert not saved.rollback_available


def test_auto_apply_is_disabled_by_default(tmp_path: Path) -> None:
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[],
        safety_check=StubSafety(),
    )
    status = manager.status()
    assert not status.auto_apply_enabled
    report = manager.apply(auto=True)
    assert not report.applied
    assert "auto-apply is disabled" in report.message


def test_auto_apply_never_applies_during_live_trading(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_UPDATE_PYPI_PACKAGE", "atlas-agent")
    manager = SafeUpdateManager(
        config=make_config(tmp_path),
        workspace_root=tmp_path,
        repo_root=tmp_path,
        sources=[
            StubSource(
                "new",
                result=AvailableUpdate(latest_version="9.9.9", source="test"),
            )
        ],
        safety_check=StubSafety(live=True),
        command_runner=lambda command, cwd: subprocess.CompletedProcess(
            command, returncode=0, stdout="", stderr=""
        ),
    )
    manager.configure(auto_apply=True)
    report = manager.apply(auto=True)
    assert not report.applied
    assert "live trading is enabled" in report.blockers
