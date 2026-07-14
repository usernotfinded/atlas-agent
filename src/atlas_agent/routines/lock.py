# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    routines/lock.py
# PURPOSE: Stops two routines running at once. Without it, a cron-triggered run and
#          a manual one could evaluate the same signal and each place an order for
#          it — two positions where the user intended one.
# DEPS:    stdlib only (os, errno, contextlib)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import errno
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator


# --- CONFIGURATIONS & CONSTANTS ---

DEFAULT_STALE_AFTER = timedelta(hours=6)
LOCK_RELATIVE_PATH = Path(".atlas") / "locks" / "routine.lock"


class RoutineLockError(RuntimeError):
    pass


# ==============================================================================
# LOCK STATE
# ==============================================================================

@dataclass(frozen=True)
class RoutineLockInfo:
    routine: str
    pid: int | None
    timestamp: datetime
    path: Path

    @property
    def age(self) -> timedelta:
        return datetime.now(UTC) - self.timestamp

    def is_stale(self, *, stale_after: timedelta = DEFAULT_STALE_AFTER) -> bool:
        """Is this lock abandoned, and therefore safe to break?"""
        # Two independent staleness tests, because each one alone has a failure mode:
        #   - AGE alone would break the lock of a legitimately long-running routine;
        #   - PID alone would never break the lock of a crashed process whose pid has
        #     since been recycled by an unrelated program.
        # Requiring EITHER means a crashed routine unblocks quickly (dead pid), while a
        # slow-but-alive one keeps its lock until the age ceiling.
        if self.age > stale_after:
            return True
        return self.pid is not None and not _pid_is_running(self.pid)


@dataclass
class RoutineLock:
    path: Path
    routine: str
    pid: int
    timestamp: datetime
    recovery_message: str | None = None

    def release(self) -> None:
        if not self.path.exists():
            return
        try:
            info = read_routine_lock(self.path.parent.parent.parent)
        except RoutineLockError:
            return
        if (
            info is not None
            and info.routine == self.routine
            and info.pid == self.pid
            and info.timestamp == self.timestamp
        ):
            self.path.unlink()


@contextmanager
def routine_lock(
    workspace_dir: str | Path,
    routine: str,
    *,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> Iterator[RoutineLock]:
    lock = acquire_routine_lock(
        workspace_dir,
        routine,
        stale_after=stale_after,
    )
    try:
        yield lock
    finally:
        lock.release()


def acquire_routine_lock(
    workspace_dir: str | Path,
    routine: str,
    *,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> RoutineLock:
    root = Path(workspace_dir)
    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    recovery_message: str | None = None

    existing = read_routine_lock(root)
    if existing is not None:
        if not existing.is_stale(stale_after=stale_after):
            raise RoutineLockError(
                "routine lock is active: "
                f"{existing.routine} pid={existing.pid} "
                f"started={existing.timestamp.isoformat()}; "
                "use `atlas routine status` to inspect it"
            )
        recovery_message = (
            "recovered stale routine lock: "
            f"{existing.routine} pid={existing.pid} "
            f"started={existing.timestamp.isoformat()}"
        )
        path.unlink()

    timestamp = datetime.now(UTC)
    payload = {
        "routine": routine,
        "pid": os.getpid(),
        "timestamp": timestamp.isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return RoutineLock(
        path=path,
        routine=routine,
        pid=os.getpid(),
        timestamp=timestamp,
        recovery_message=recovery_message,
    )


def read_routine_lock(workspace_dir: str | Path) -> RoutineLockInfo | None:
    path = lock_path(Path(workspace_dir))
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        timestamp = datetime.fromisoformat(payload["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return RoutineLockInfo(
            routine=str(payload["routine"]),
            pid=int(payload["pid"]) if payload.get("pid") is not None else None,
            timestamp=timestamp.astimezone(UTC),
            path=path,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RoutineLockError(f"routine lock is unreadable: {path}") from exc


def unlock_routine(
    workspace_dir: str | Path,
    *,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> str:
    info = read_routine_lock(workspace_dir)
    if info is None:
        return "no routine lock present"
    if not info.is_stale(stale_after=stale_after):
        raise RoutineLockError(
            "routine lock is active and was not removed: "
            f"{info.routine} pid={info.pid} started={info.timestamp.isoformat()}"
        )
    info.path.unlink()
    return (
        "removed stale routine lock: "
        f"{info.routine} pid={info.pid} started={info.timestamp.isoformat()}"
    )


def routine_status(workspace_dir: str | Path) -> str:
    info = read_routine_lock(workspace_dir)
    if info is None:
        return "no routine lock present"
    state = "stale" if info.is_stale() else "active"
    return (
        f"routine lock {state}: {info.routine} "
        f"pid={info.pid} started={info.timestamp.isoformat()}"
    )


def lock_path(workspace_dir: Path) -> Path:
    return workspace_dir / LOCK_RELATIVE_PATH


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        if exc.errno == errno.EPERM:
            return True
        return False
    return True

