# CAND-003 Stateful Runner Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.
> Work directly on `main`. Do not create a feature branch or worktree.

**Goal:** Add a deterministic, fail-closed, per-state-directory exclusive lock to the CAND-003 stateful autonomous paper runner so two concurrent invocations cannot race against the same state/checkpoint files.

**Architecture:** Introduce a small `StateDirectoryLock` helper that uses POSIX `fcntl.flock` on a lock file inside the state directory. The runner acquires the lock immediately after validating configuration and before reading or writing any state, checkpoint, decisions, fills, metrics, manifest, or audit artifacts. Lock failure is surfaced as a `StatefulPaperResult` with status `"failed"` and a redacted user-facing error. Non-stateful autonomous-paper behavior is unchanged.

**Tech Stack:** Python 3.11+, `fcntl` (Unix/macOS), `pytest`, existing `atlas_agent` modules.

---

## Lock file choice

- Path: `<state_dir>/.atlas_state.lock`
- Content: single line containing the process PID (no secrets, no paths).
- Mode: `w+` so the file is created/truncated and kept open for `fcntl.flock`.
- Advisory exclusive lock (`fcntl.LOCK_EX | fcntl.LOCK_NB`).
- Released by closing the file descriptor, with an explicit `release()` method for tests.

## Failure behavior

- If lock acquisition fails with `OSError`/`IOError`/`BlockingIOError`, `run_stateful_autonomous_paper` returns:
  - `status="failed"`
  - `errors=["state_directory_locked: another stateful autonomous-paper run may already be active for <state_dir>"]`
- No state/checkpoint/decisions/fills/metrics/manifest/audit writes occur.
- CLI prints the error line(s) and exits with code 2.

---

## Task 1: Implement `StateDirectoryLock` module

**Files:**
- Create: `src/atlas_agent/agent/autonomous_paper_lock.py`
- Test: `tests/test_autonomous_paper_lock.py`

### Step 1: Write the failing tests

```python
import fcntl
from pathlib import Path

import pytest

from atlas_agent.agent.autonomous_paper_lock import (
    StateDirectoryLock,
    StateDirectoryLockError,
    acquire_state_directory_lock,
    state_directory_lock,
)


def test_lock_acquires_and_releases(tmp_path: Path):
    lock = acquire_state_directory_lock(tmp_path)
    assert (tmp_path / ".atlas_state.lock").exists()
    lock.release()
    assert not (tmp_path / ".atlas_state.lock").exists()


def test_concurrent_lock_fails_closed(tmp_path: Path):
    lock1 = acquire_state_directory_lock(tmp_path)
    try:
        with pytest.raises(StateDirectoryLockError):
            acquire_state_directory_lock(tmp_path)
    finally:
        lock1.release()


def test_context_manager_releases_on_exit(tmp_path: Path):
    with state_directory_lock(tmp_path):
        assert (tmp_path / ".atlas_state.lock").exists()
    assert not (tmp_path / ".atlas_state.lock").exists()


def test_context_manager_releases_on_exception(tmp_path: Path):
    class SentinelError(Exception):
        pass

    with pytest.raises(SentinelError):
        with state_directory_lock(tmp_path):
            raise SentinelError("boom")
    assert not (tmp_path / ".atlas_state.lock").exists()


def test_lock_error_includes_state_dir_not_internal_path(tmp_path: Path):
    lock1 = acquire_state_directory_lock(tmp_path)
    try:
        with pytest.raises(StateDirectoryLockError) as exc_info:
            acquire_state_directory_lock(tmp_path)
        message = str(exc_info.value)
        assert str(tmp_path) in message
        assert "/Users/" not in message.replace(str(tmp_path), "")
        assert "Traceback" not in message
    finally:
        lock1.release()
```

Run: `python3.11 -m pytest tests/test_autonomous_paper_lock.py -v`
Expected: FAIL (module not defined).

### Step 2: Implement the lock module

```python
from __future__ import annotations

import errno
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class StateDirectoryLockError(RuntimeError):
    """Raised when the state-directory lock cannot be acquired."""

    pass


class StateDirectoryLock:
    """Exclusive advisory lock for a stateful autonomous-paper directory."""

    def __init__(self, state_dir: str | Path, lock_path: Path, fd: int):
        self.state_dir = Path(state_dir)
        self.lock_path = lock_path
        self._fd = fd

    def release(self) -> None:
        if self._fd < 0:
            return
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = -1
        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
        except OSError:
            pass

    def __del__(self) -> None:
        self.release()


def _lock_path(state_dir: Path) -> Path:
    return state_dir / ".atlas_state.lock"


def acquire_state_directory_lock(
    state_dir: str | Path,
) -> StateDirectoryLock:
    """Acquire an exclusive lock for ``state_dir``.

    Raises:
        StateDirectoryLockError: if another process already holds the lock.
    """
    path = Path(state_dir)
    path.mkdir(parents=True, exist_ok=True)
    lock_file = _lock_path(path)

    try:
        fd = os.open(
            str(lock_file),
            os.O_RDWR | os.O_CREAT,
            0o644,
        )
        try:
            os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
            os.fsync(fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
    except (OSError, IOError, BlockingIOError) as exc:
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
            raise StateDirectoryLockError(
                f"state_directory_locked: another stateful autonomous-paper run "
                f"may already be active for {path}"
            ) from None
        raise StateDirectoryLockError(
            f"state_directory_locked: another stateful autonomous-paper run "
            f"may already be active for {path}"
        ) from None

    return StateDirectoryLock(state_dir=path, lock_path=lock_file, fd=fd)


@contextmanager
def state_directory_lock(
    state_dir: str | Path,
) -> Iterator[StateDirectoryLock]:
    """Context-manager wrapper around :func:`acquire_state_directory_lock`."""
    lock = acquire_state_directory_lock(state_dir)
    try:
        yield lock
    finally:
        lock.release()
```

Run: `python3.11 -m pytest tests/test_autonomous_paper_lock.py -v`
Expected: PASS.

### Step 3: Commit

```bash
git add src/atlas_agent/agent/autonomous_paper_lock.py tests/test_autonomous_paper_lock.py
git commit -m "feat(cand-003): add state-directory lock module"
```

---

## Task 2: Integrate lock into stateful runner

**Files:**
- Modify: `src/atlas_agent/agent/autonomous_paper_runner.py`

### Step 1: Write the failing test

Append to `tests/test_autonomous_paper_runner.py`:

```python
def test_runner_fails_closed_when_state_directory_locked(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    existing_lock = acquire_state_directory_lock(config.state_dir)
    try:
        result = run_stateful_autonomous_paper(
            config=config,
            atlas_config=atlas_config,
            max_cycles=2,
        )
        assert result.status == "failed"
        assert any("state_directory_locked" in e.lower() for e in result.errors)
        assert not Path(config.output_dir).exists() or not any(
            Path(config.output_dir).iterdir()
        )
    finally:
        existing_lock.release()


def test_runner_releases_lock_after_success(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(atlas_config, tmp_path)
    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result.status == "completed"
    assert not (Path(config.state_dir) / ".atlas_state.lock").exists()


def test_runner_releases_lock_after_failure(tmp_path: Path):
    atlas_config = _make_config(tmp_path)
    config = _make_stateful_config(
        atlas_config, tmp_path, data_path=str(tmp_path / "missing.csv")
    )
    result = run_stateful_autonomous_paper(
        config=config,
        atlas_config=atlas_config,
        max_cycles=2,
    )
    assert result.status == "failed"
    assert not (Path(config.state_dir) / ".atlas_state.lock").exists()
```

Add import at the top of `tests/test_autonomous_paper_runner.py`:

```python
from atlas_agent.agent.autonomous_paper_lock import acquire_state_directory_lock
```

Run: `python3.11 -m pytest tests/test_autonomous_paper_runner.py::test_runner_fails_closed_when_state_directory_locked -v`
Expected: FAIL (lock not integrated yet).

### Step 2: Integrate the lock

In `src/atlas_agent/agent/autonomous_paper_runner.py`:

1. Add import:

```python
from atlas_agent.agent.autonomous_paper_lock import (
    StateDirectoryLockError,
    state_directory_lock,
)
```

2. In `run_stateful_autonomous_paper`, replace the early directory creation and audit start sequence with:

```python
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_dir = Path(config.state_dir)

    try:
        with state_directory_lock(state_dir):
            state_dir.mkdir(parents=True, exist_ok=True)
            return _run_stateful_autonomous_paper_locked(
                config=config,
                atlas_config=atlas_config,
                resume=resume,
                max_cycles=max_cycles,
                audit_writer=audit_writer,
                event_logger=event_logger,
                kill_switch=kill_switch,
            )
    except StateDirectoryLockError as exc:
        error = str(exc)
        return StatefulPaperResult(
            run_id=config.run_id,
            status="failed",
            bars_processed_this_run=0,
            total_bars_processed=0,
            decisions_path=str(output_dir / f"{config.run_id}-decisions.jsonl"),
            fills_path=str(output_dir / f"{config.run_id}-fills.jsonl"),
            metrics_path=str(output_dir / f"{config.run_id}-metrics.json"),
            checkpoint_path=str(_checkpoint_path(state_dir, config.run_id)),
            manifest_path=str(output_dir / f"{config.run_id}-manifest.json"),
            audit_log_path=str(Path(atlas_config.audit_dir) / "events.jsonl"),
            metrics=None,
            errors=[error],
        )
```

3. Rename the existing function body to `_run_stateful_autonomous_paper_locked(...)` with the same signature, removing the directory creation already done by the wrapper.

Run: `python3.11 -m pytest tests/test_autonomous_paper_runner.py -v`
Expected: PASS.

### Step 3: Commit

```bash
git add src/atlas_agent/agent/autonomous_paper_runner.py tests/test_autonomous_paper_runner.py
git commit -m "feat(cand-003): integrate state-directory lock into runner"
```

---

## Task 3: CLI smoke test for lock failure output

**Files:**
- Create: `tests/test_cli_autonomous_paper_lock.py`

### Step 1: Write the test

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_cli_stateful_lock_failure_is_user_facing(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_file = state_dir / ".atlas_state.lock"
    lock_file.write_text("12345\n", encoding="utf-8")

    # Hold the lock in a short-lived subprocess so the main CLI invocation fails.
    holder = subprocess.Popen(
        [sys.executable, "-c", "import fcntl, time; f=open('" + str(lock_file) + "'); fcntl.flock(f, fcntl.LOCK_EX); time.sleep(5)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "atlas_agent.cli",
                "agent",
                "autonomous-paper",
                "--state-dir",
                str(state_dir),
                "--data-path",
                str(tmp_path / "missing.csv"),
                "--max-cycles",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 2
        combined = result.stdout + result.stderr
        assert "state_directory_locked" in combined.lower()
        assert "another stateful autonomous-paper run" in combined.lower()
    finally:
        holder.terminate()
        try:
            holder.wait(timeout=5)
        except Exception:
            holder.kill()
```

Run: `python3.11 -m pytest tests/test_cli_autonomous_paper_lock.py -v`
Expected: PASS.

### Step 2: Commit

```bash
git add tests/test_cli_autonomous_paper_lock.py
git commit -m "test(cand-003): add CLI smoke test for state-directory lock failure"
```

---

## Task 4: Verify safety boundaries and required checks

Run each command fresh and confirm output:

```bash
git status --short
git diff --check
python3.11 -m compileall src
python3.11 -m pytest tests/test_autonomous_paper_lock.py tests/test_autonomous_paper_runner.py tests/test_cli_autonomous_paper_lock.py -v
python3.11 scripts/check_autonomous_paper_loop_contract.py
python3.11 scripts/check_autonomous_paper_scorecard_contract.py
python3.11 scripts/check_shadow_live_contract.py
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_cli_command_compatibility.py
python3.11 -m pip check
bash scripts/demo_autonomous_paper_stateful.sh
atlas run --mode paper
atlas run --mode live
./scripts/release_check.sh --quick
```

If any check fails, fix the cause and re-run the failing check before claiming completion.

### Final commit

```bash
git commit --amend -m "fix(cand-003): add stateful runner lock"
```

Or, if multiple commits were made, squash them:

```bash
git reset --soft HEAD~3
git commit -m "fix(cand-003): add stateful runner lock"
```

### Push

```bash
git push origin main
```

---

## Self-review checklist

1. **Spec coverage:**
   - Exclusive lock per state directory → Task 1.
   - Acquired before any mutation → Task 2 wrapper.
   - Second concurrent invocation fails closed → Tasks 1-2 tests.
   - Lock released on exit → Task 1/2 tests.
   - No mutation on lock failure → Task 2 test.
   - Deterministic/local-only → uses `fcntl`, no network.
   - Non-stateful path unchanged → only `run_stateful_autonomous_paper` modified.
   - `atlas run` behavior unchanged → no `atlas run` code touched.

2. **Placeholder scan:** All steps contain exact code/commands.

3. **Type consistency:** `StateDirectoryLock` signature stable across module and tests.
