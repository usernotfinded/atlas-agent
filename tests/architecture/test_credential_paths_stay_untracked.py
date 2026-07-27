# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/architecture/test_credential_paths_stay_untracked.py
# PURPOSE: Keeps the paths that hold real credentials ignored by git and absent
#         from the tracked tree.
# DEPS:    subprocess, pathlib, pytest.
# ==============================================================================

"""Structural guard for the no-credentials-in-the-repository invariant.

`check_env_templates.py` already validates that every `.env.example` ships with
empty secrets, which covers the templates. What it cannot see is the other
half: the real files those templates stand in for must stay out of the tree.

That half held only by convention. Deleting a line from `.gitignore`, or a
`git add -f` on a working `.env`, would have committed live credentials without
failing anything.

This deliberately checks paths rather than scanning file contents for
key-shaped strings. A content scanner has to tell a real credential from a
fixture, and this suite is full of deliberate fakes like `sk-ant-test` and
`sk-live-AUDITPROBE123456`; one that guesses wrong gets muted, and a muted
guard protects nothing.
"""

# --- IMPORTS ---

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[2]

#: Paths that hold real credentials at runtime. Each must be ignored by git.
CREDENTIAL_PATHS = (
    ".env",
    ".env.atlas",
    "workspace.key",
    "broker.secret",
)

#: Tracked files matching these suffixes would be a committed credential.
CREDENTIAL_SUFFIXES = (".env", ".key", ".pem", ".secret", ".p12", ".pfx")


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


@pytest.mark.parametrize("path", CREDENTIAL_PATHS)
def test_credential_path_is_ignored(path: str) -> None:
    """`git check-ignore` must claim each path that can hold a live secret."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"{path} is no longer ignored by git. A working copy of it would be "
        "committable, and it holds real credentials at runtime."
    )


def test_no_credential_file_is_tracked() -> None:
    """Ignoring a path does not help if a file was force-added before."""
    tracked = _git("ls-files").splitlines()
    offenders = [
        name
        for name in tracked
        if name.endswith(CREDENTIAL_SUFFIXES) and not name.endswith(".env.example")
    ]

    assert offenders == [], (
        f"Files that look like committed credentials are tracked: {offenders}. "
        "If one is a fixture, give it a name that does not claim to be a key."
    )


def test_env_examples_are_the_only_tracked_env_files() -> None:
    """Templates are tracked on purpose; the files they model are not."""
    tracked_env = [
        name for name in _git("ls-files").splitlines() if ".env" in Path(name).name
    ]

    assert tracked_env, "expected at least one tracked .env.example template"
    for name in tracked_env:
        assert name.endswith(".env.example") or name.endswith(".gitignore"), (
            f"{name} is tracked and looks like a real environment file rather "
            "than a template."
        )
