# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/cli/test_autonomous_paper_stateful_cli.py
# PURPOSE: Verifies autonomous paper stateful cli behavior and regression
#         expectations.
# DEPS:    json, os, subprocess, sys, pathlib, pytest.
# ==============================================================================

"""CLI tests for stateful autonomous paper mode.

These tests exercise ``atlas agent autonomous-paper`` with ``--state-dir``
end-to-end via subprocess. They verify that:

- A stateful run persists state and checkpoint files.
- A second invocation with ``--resume`` continues the same run and advances the
  cursor instead of starting a fresh run_id.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_DATA = REPO_ROOT / "data" / "sample" / "ohlcv.csv"

pytestmark = pytest.mark.slow


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run_atlas(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "atlas_agent.cli", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _init_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    result = _run_atlas(
        "init",
        "--template",
        "routine-trader",
        str(workspace),
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    # Set up discipline profile (non-interactive confirmation)
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli", "discipline", "setup", "--manual"],
        input="yes\n",
        capture_output=True,
        text=True,
        cwd=str(workspace),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return workspace


def test_autonomous_paper_stateful_cli_runs(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    state_dir = workspace / "state"

    result = _run_atlas(
        "agent",
        "autonomous-paper",
        "--symbol",
        "DEMO-SYMBOL",
        "--data-path",
        str(SAMPLE_DATA),
        "--max-cycles",
        "2",
        "--state-dir",
        str(state_dir),
        "--json",
        cwd=workspace,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["status"] == "completed"
    assert data["data"]["bars_processed_this_run"] == 2

    state_files = list(state_dir.glob("*-state.json"))
    checkpoint_files = list(state_dir.glob("*-checkpoint.json"))
    assert state_files, "Expected state file to be created in --state-dir"
    assert checkpoint_files, "Expected checkpoint file to be created in --state-dir"


def test_autonomous_paper_stateful_resume(tmp_path: Path) -> None:
    workspace = _init_workspace(tmp_path)
    state_dir = workspace / "state"

    def run(max_cycles: int, resume: bool = False) -> dict:
        args = [
            "agent",
            "autonomous-paper",
            "--symbol",
            "DEMO-SYMBOL",
            "--data-path",
            str(SAMPLE_DATA),
            "--max-cycles",
            str(max_cycles),
            "--state-dir",
            str(state_dir),
            "--json",
        ]
        if resume:
            args.append("--resume")
        result = _run_atlas(*args, cwd=workspace)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)["data"]

    first = run(max_cycles=2)
    assert first["status"] == "completed"
    assert first["total_bars_processed"] == 2
    first_run_id = first["run_id"]

    second = run(max_cycles=2, resume=True)
    assert second["status"] == "completed"
    assert second["run_id"] == first_run_id, "Resume should reuse the existing run_id"
    assert second["total_bars_processed"] == 4, "Resume should advance total processed bars"
    assert second["bars_processed_this_run"] == 2

    state_files = list(state_dir.glob("*-state.json"))
    assert len(state_files) == 1, "Resume should not create a second run state file"
