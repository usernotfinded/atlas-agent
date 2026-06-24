#!/usr/bin/env python3
"""Fail-closed exclusive lock for a stateful autonomous-paper state directory.

Uses POSIX ``fcntl.flock`` so that only one autonomous-paper run can hold a
given state directory at a time. The lock is deterministic, local-only, and
only depends on the stdlib.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
from pathlib import Path
from typing import Generator


class StateDirectoryLockError(RuntimeError):
    """Raised when the state directory is already locked by another process."""


class StateDirectoryLock:
    """Holds an open fd and the path to the lock file it owns."""

    __slots__ = ("_fd", "_lock_path", "_released")

    def __init__(self, fd: int, lock_path: Path) -> None:
        self._fd = fd
        self._lock_path = lock_path
        self._released = False

    def release(self) -> None:
        """Release the lock, unlink the lock file, and close the fd."""
        if self._released:
            return
        self._released = True

        lock_path = self._lock_path
        self._lock_path = None
        try:
            if lock_path is not None and lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass

        fd = self._fd
        if fd is not None:
            self._fd = None
            try:
                os.close(fd)
            except OSError:
                pass

    def __del__(self) -> None:
        self.release()


def acquire_state_directory_lock(state_dir: str | Path) -> StateDirectoryLock:
    """Acquire an exclusive non-blocking lock on ``state_dir``.

    Creates ``state_dir`` if it does not exist, opens
    ``<state_dir>/.atlas_state.lock``, and acquires the lock. The current PID
    is written to the file after the lock is held so the file identifies the
    holder.

    Raises:
        StateDirectoryLockError: If another process already holds the lock.
    """
    path = Path(state_dir)
    path.mkdir(parents=True, exist_ok=True)

    lock_path = path / ".atlas_state.lock"
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        try:
            os.close(fd)
        except OSError:
            pass
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
            raise StateDirectoryLockError(
                f"state_directory_locked: another stateful autonomous-paper run "
                f"may already be active for {path}"
            ) from exc
        raise

    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
    os.fsync(fd)

    return StateDirectoryLock(fd, lock_path)


@contextlib.contextmanager
def state_directory_lock(
    state_dir: str | Path,
) -> Generator[StateDirectoryLock, None, None]:
    """Context manager wrapping :func:`acquire_state_directory_lock`."""
    lock = acquire_state_directory_lock(state_dir)
    try:
        yield lock
    finally:
        lock.release()
