#!/usr/bin/env python3
"""Unit tests for the autonomous-paper state directory lock."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("fcntl")

from atlas_agent.agent.autonomous_paper_lock import (
    StateDirectoryLock,
    StateDirectoryLockError,
    acquire_state_directory_lock,
    state_directory_lock,
)


pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fcntl is POSIX-only")


REPO_ROOT = Path(__file__).resolve().parent.parent


_HOLDER_SCRIPT = '''\
import os
import sys
import time
from pathlib import Path

from atlas_agent.agent.autonomous_paper_lock import acquire_state_directory_lock

state_dir = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
stop_path = Path(sys.argv[3])

lock = acquire_state_directory_lock(state_dir)
try:
    ready_path.write_text(str(os.getpid()), encoding="utf-8")
    while not stop_path.exists():
        time.sleep(0.05)
finally:
    lock.release()
'''


def _start_lock_holder(state_dir: Path, tmp_path: Path) -> tuple[subprocess.Popen, Path, Path]:
    """Start a subprocess that holds ``state_dir`` locked until told to stop."""
    helper = tmp_path / "lock_holder.py"
    helper.write_text(_HOLDER_SCRIPT, encoding="utf-8")

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
        try:
            _, errs = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            errs = ""
        proc.kill()
        proc.wait()
        raise AssertionError(f"Lock holder did not start: {errs}")

    return proc, ready_path, stop_path


def _stop_lock_holder(proc: subprocess.Popen, stop_path: Path) -> None:
    stop_path.write_text("stop", encoding="utf-8")
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    if proc.returncode != 0:
        outs, errs = proc.communicate()
        raise AssertionError(f"Lock holder exited {proc.returncode}: {outs}\n{errs}")


def test_lock_acquires_and_releases(tmp_path: Path) -> None:
    """Acquiring then releasing removes the lock file and closes the fd."""
    state_dir = tmp_path / "state"
    lock = acquire_state_directory_lock(state_dir)

    assert isinstance(lock, StateDirectoryLock)
    assert lock._fd is not None
    assert (state_dir / ".atlas_state.lock").exists()

    lock.release()
    assert not (state_dir / ".atlas_state.lock").exists()


def test_concurrent_lock_fails_closed(tmp_path: Path) -> None:
    """A second process cannot acquire the same state directory lock."""
    state_dir = tmp_path / "state"
    holder, _, stop_path = _start_lock_holder(state_dir, tmp_path)

    try:
        with pytest.raises(StateDirectoryLockError):
            acquire_state_directory_lock(state_dir)
    finally:
        _stop_lock_holder(holder, stop_path)


def test_context_manager_releases_on_exit(tmp_path: Path) -> None:
    """The context manager releases the lock on normal exit."""
    state_dir = tmp_path / "state"

    with state_directory_lock(state_dir) as lock:
        assert lock._fd is not None
        assert (state_dir / ".atlas_state.lock").exists()

    assert not (state_dir / ".atlas_state.lock").exists()


def test_context_manager_releases_on_exception(tmp_path: Path) -> None:
    """The context manager releases the lock even when an exception is raised."""
    state_dir = tmp_path / "state"

    with pytest.raises(ValueError, match="boom"):
        with state_directory_lock(state_dir):
            assert (state_dir / ".atlas_state.lock").exists()
            raise ValueError("boom")

    assert not (state_dir / ".atlas_state.lock").exists()


def test_lock_error_message_is_user_facing(tmp_path: Path) -> None:
    """The lock error names the state directory and the conflicting run."""
    state_dir = tmp_path / "state"
    holder, _, stop_path = _start_lock_holder(state_dir, tmp_path)

    try:
        with pytest.raises(StateDirectoryLockError) as exc_info:
            acquire_state_directory_lock(state_dir)
    finally:
        _stop_lock_holder(holder, stop_path)

    expected = (
        f"state_directory_locked: another stateful autonomous-paper run "
        f"may already be active for {state_dir}"
    )
    assert str(exc_info.value) == expected


def test_lock_file_contains_pid_after_acquire(tmp_path: Path) -> None:
    """After acquisition the lock file contains this process's PID."""
    state_dir = tmp_path / "state"
    lock = acquire_state_directory_lock(state_dir)

    try:
        content = (state_dir / ".atlas_state.lock").read_text(encoding="utf-8").strip()
        assert content == str(os.getpid())
    finally:
        lock.release()


def test_release_is_idempotent(tmp_path: Path) -> None:
    """Calling release() more than once is safe and does not raise."""
    state_dir = tmp_path / "state"
    lock = acquire_state_directory_lock(state_dir)
    lock.release()
    assert not (state_dir / ".atlas_state.lock").exists()
    lock.release()  # should not raise or re-unlink anything
    assert not (state_dir / ".atlas_state.lock").exists()


def test_del_after_release_does_not_delete_newer_lock(tmp_path: Path) -> None:
    """Releasing then deleting an old lock must not remove a newer lock file."""
    state_dir = tmp_path / "state"
    lock1 = acquire_state_directory_lock(state_dir)
    lock1.release()

    lock2 = acquire_state_directory_lock(state_dir)
    try:
        assert (state_dir / ".atlas_state.lock").exists()
        del lock1  # lock1 is already released; its __del__ must be idempotent
        assert (state_dir / ".atlas_state.lock").exists()
    finally:
        lock2.release()
