#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_no_protected_staged.py
# PURPOSE: Fail if protected local/runtime artifacts are staged.
# DEPS:    subprocess, sys, typing.
# ==============================================================================

"""Fail if protected local/runtime artifacts are staged."""

# --- IMPORTS ---

from __future__ import annotations

import subprocess
import sys
from typing import Iterable


# --- CONFIGURATION AND CONSTANTS ---

PROTECTED_PATTERNS = [
    "AUDIT_ENHANCEMENTS_2026-05-13.md",
    "BATCH2_PLAN.md",
    "memory/",
    "build/",
    "dist/",
    ".egg-info",
    ".egg-info/",
    ".whl",
    ".tar.gz",
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    "__pycache__/",
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

class StagedFilesError(Exception):
    """Raised when staged files cannot be read."""


def is_protected_path(path: str) -> bool:
    """Return True if *path* matches a protected artifact pattern."""
    if path in {"AUDIT_ENHANCEMENTS_2026-05-13.md", "BATCH2_PLAN.md"}:
        return True
    if path.startswith("memory/") or path == "memory":
        return True
    if path.startswith("build/") or path == "build":
        return True
    if path.startswith("dist/") or path == "dist":
        return True
    if ".egg-info" in path:
        return True
    if path.endswith(".whl"):
        return True
    if path.endswith(".tar.gz"):
        return True
    if ".pytest_cache/" in path or path.startswith(".pytest_cache/"):
        return True
    if ".ruff_cache/" in path or path.startswith(".ruff_cache/"):
        return True
    if ".mypy_cache/" in path or path.startswith(".mypy_cache/"):
        return True
    if "__pycache__/" in path or path.startswith("__pycache__/"):
        return True
    return False


def find_protected_paths(paths: Iterable[str]) -> list[str]:
    """Return the subset of *paths* that are protected."""
    return [p for p in paths if is_protected_path(p)]


def get_staged_paths() -> list[str]:
    """Return currently staged file paths from git."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise StagedFilesError("unable to read staged files. Is this a git repository?")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None, staged_paths: list[str] | None = None) -> int:
    """Check staged paths for protected artifacts and return exit code."""
    if staged_paths is None:
        try:
            staged_paths = get_staged_paths()
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    protected = find_protected_paths(staged_paths)
    if protected:
        print("Protected staged files detected:")
        for p in protected:
            print(f"- {p}")
        return 2

    print("No protected staged files detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
