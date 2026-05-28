"""Tests for the reviewer golden-path smoke test.

These tests verify that:
- The smoke script passes against the current repo.
- JSON output is well-formed and contains passed: true.
- Output redacts absolute paths.
- The script source remains safe (no shell=True, no suspicious imports).
- Failure paths return nonzero.
- --keep-temp preserves the workspace.
- Default mode cleans up the workspace.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "smoke_reviewer_golden_path.py"


def _load_smoke_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "smoke_reviewer_golden_path", SMOKE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["smoke_reviewer_golden_path"] = mod
    spec.loader.exec_module(mod)
    return mod


SMOKE_MOD = _load_smoke_module()


# ---------------------------------------------------------------------------
# Positive integration tests
# ---------------------------------------------------------------------------


def test_smoke_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--skip-release-check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_smoke_script_json_output_has_passed_true() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--json", "--skip-release-check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["errors"] == []
    assert len(data["steps"]) > 0


def test_output_redacts_temp_absolute_paths() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--json", "--skip-release-check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0
    # The JSON command string should contain <REPO_ROOT> not the real path
    assert REPO_ROOT.name not in result.stdout or "<REPO_ROOT>" in result.stdout


def test_smoke_does_not_require_credentials() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--json", "--skip-release-check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "ATLAS_CI": "1",
        },
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True


# ---------------------------------------------------------------------------
# Source safety checks
# ---------------------------------------------------------------------------


def test_script_source_no_shell_true() -> None:
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_script_source_no_unsafe_network_calls() -> None:
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in smoke script"


# ---------------------------------------------------------------------------
# Failure path tests (unit level, fast)
# ---------------------------------------------------------------------------


def test_failure_path_returns_nonzero() -> None:
    """Simulate a failing atlas command and verify the smoke reports failure."""
    call_count = 0

    def _failing_run_atlas(
        args: list[str],
        cwd: Path,
        env: dict[str, str],
    ) -> tuple[int, str, str]:
        nonlocal call_count
        call_count += 1
        # Let --help pass, init pass, then fail on the first golden-path command
        if args == ["--help"]:
            return 0, "", ""
        if args[0] == "init":
            return 0, "", ""
        return 1, "", "simulated failure"

    with patch.object(SMOKE_MOD, "_run_atlas", _failing_run_atlas):
        result = SMOKE_MOD._smoke(keep_temp=False, skip_release_check=True)
    assert result["passed"] is False
    assert any("failed with exit code 1" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Temp workspace lifecycle tests
# ---------------------------------------------------------------------------


def test_keep_temp_preserves_workspace() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--json", "--skip-release-check", "--keep-temp"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["temp_workspace"] is not None
    temp_path = Path(data["temp_workspace"])
    assert temp_path.exists()
    # Clean up after test
    import shutil
    shutil.rmtree(temp_path, ignore_errors=True)


def test_default_mode_cleans_up_workspace() -> None:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--json", "--skip-release-check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["temp_workspace"] is None
