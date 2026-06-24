#!/usr/bin/env python3
"""CLI smoke test for stateful autonomous-paper lock failure.

Verifies that ``atlas agent autonomous-paper --state-dir <dir>`` fails closed
with a clear, user-facing error when the state directory is already locked by
another process.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fcntl")

from tests.cli.test_autonomous_paper_stateful_cli import (
    REPO_ROOT,
    SAMPLE_DATA,
    _init_workspace,
)

_LOCK_HOLDER_SCRIPT = '''\
import fcntl
import os
import sys
import time
from pathlib import Path

state_dir = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
stop_path = Path(sys.argv[3])

state_dir.mkdir(parents=True, exist_ok=True)
lock_path = state_dir / ".atlas_state.lock"
fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
try:
    fcntl.flock(fd, fcntl.LOCK_EX)
    ready_path.write_text(str(os.getpid()), encoding="utf-8")
    while not stop_path.exists():
        time.sleep(0.05)
finally:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
'''


def _start_lock_holder(state_dir: Path, tmp_path: Path) -> tuple[subprocess.Popen, Path]:
    """Start a subprocess that holds ``state_dir`` locked until told to stop."""
    helper = tmp_path / "lock_holder.py"
    helper.write_text(_LOCK_HOLDER_SCRIPT, encoding="utf-8")

    ready_path = tmp_path / "holder_ready"
    stop_path = tmp_path / "holder_stop"

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    proc = subprocess.Popen(
        [sys.executable, str(helper), str(state_dir), str(ready_path), str(stop_path)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.monotonic() + 10
    while not ready_path.exists() and time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.05)

    if not ready_path.exists():
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        stdout, stderr = proc.communicate()
        raise AssertionError(f"Lock holder did not become ready: {stdout}{stderr}")

    return proc, stop_path


def _stop_lock_holder(proc: subprocess.Popen, stop_path: Path) -> None:
    """Signal the lock holder to stop and wait for it to exit."""
    stop_path.write_text("stop", encoding="utf-8")
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        output = stdout + stderr
        pytest.fail(f"Lock holder exited with code {proc.returncode}: {output}")


def _run_autonomous_paper(state_dir: Path, workspace: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the CLI ``agent autonomous-paper`` command for the test state dir."""
    cmd = [
        sys.executable,
        "-m",
        "atlas_agent.cli",
        "agent",
        "autonomous-paper",
        "--symbol",
        "DEMO-SYMBOL",
        "--data-path",
        str(SAMPLE_DATA),
        "--max-cycles",
        "1",
        "--state-dir",
        str(state_dir),
    ]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(workspace),
    )


def test_cli_autonomous_paper_fails_closed_when_state_dir_locked(tmp_path: Path) -> None:
    """The CLI exits with code 2 and a user-facing lock error when locked."""
    workspace = _init_workspace(tmp_path)
    state_dir = tmp_path / "state"
    holder, stop_path = _start_lock_holder(state_dir, tmp_path)

    try:
        result = _run_autonomous_paper(state_dir, workspace)
        combined = result.stdout + result.stderr
        assert result.returncode == 2, combined
        assert "state_directory_locked" in combined
        assert "another stateful autonomous-paper run" in combined
        assert "Traceback" not in combined
        assert "src/atlas_agent" not in combined
    finally:
        _stop_lock_holder(holder, stop_path)
