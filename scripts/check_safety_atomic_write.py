#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_safety_atomic_write.py
# PURPOSE: Static regression guard for fixed <target>.tmp safety-state writes.
# DEPS:    argparse, re, sys, pathlib, typing.
# ==============================================================================

"""Static regression guard for fixed <target>.tmp safety-state writes.

Deterministic and local-only. Does not import Atlas runtime modules, load
credentials, contact brokers, or make network calls.
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

class Violation(NamedTuple):
    path: Path
    line: int
    pattern: str
    snapshot: str


# Files that must not contain fixed <target>.tmp construction patterns.
GUARDED_RELATIVE_PATHS = [
    "src/atlas_agent/safety/heartbeat.py",
    "src/atlas_agent/safety/deadman.py",
    "src/atlas_agent/safety/kill_switch.py",
    "src/atlas_agent/safety/state.py",
]

# Helper file is allowed to construct .tmp names via mkstemp.
HELPER_RELATIVE_PATH = "src/atlas_agent/safety/atomic_write.py"

# Patterns are (regex, human-readable description).
# Order matters: the first matching pattern on a line wins.
DISALLOWED_PATTERNS: list[tuple[str, str]] = [
    (
        r'\.with_suffix\s*\([^)]*\+\s*["\']\.json\.tmp["\']',
        "fixed with_suffix .json.tmp pattern",
    ),
    (
        r'\.with_suffix\s*\([^)]*\+\s*["\']\.tmp["\']',
        "fixed with_suffix .tmp pattern",
    ),
    (r'suffix\s*\+\s*["\']\.json\.tmp["\']', "suffix + .json.tmp pattern"),
    (r'suffix\s*\+\s*["\']\.tmp["\']', "suffix + .tmp pattern"),
    (r'["\']\.json\.tmp["\']', "literal .json.tmp"),
    (
        r'Path\s*\(\s*str\s*\([^)]+\)\s*\+\s*["\']\.tmp["\']\s*\)',
        "Path(str(target) + .tmp) pattern",
    ),
    (r'str\s*\([^)]+\)\s*\+\s*["\']\.tmp["\']', "str(target) + .tmp pattern"),
    (r'NamedTemporaryFile\s*\(', "NamedTemporaryFile usage outside helper"),
    (r'\bmktemp\b', "mktemp usage"),
    (r'["\'][^"\']*\.json\.tmp["\']', "hardcoded .json.tmp path"),
]

# Broad .tmp concatenation is only an error in a code-context line.
BROAD_TMP_PATTERN = (
    r'\+\s*["\']\.tmp["\']',
    "broad + .tmp concatenation",
)

# A line is considered code-context for the broad pattern if it contains any
# of these signals. This avoids flagging comments/docstrings that merely
# mention the old pattern.
_BROAD_CONTEXT_SIGNALS = [
    "with_suffix",
    "write_text",
    "replace",
    "Path(",
    "tmp_path",
    "temp_path",
    "tmp =",
    "temp =",
]


def _is_comment_line(line: str) -> bool:
    return line.strip().startswith("#")


def _has_broad_context_signal(line: str) -> bool:
    return any(signal in line for signal in _BROAD_CONTEXT_SIGNALS)


def _scan_line(line: str) -> str | None:
    for pattern, description in DISALLOWED_PATTERNS:
        if re.search(pattern, line):
            return description
    broad_pattern, broad_description = BROAD_TMP_PATTERN
    if not _is_comment_line(line) and _has_broad_context_signal(line):
        if re.search(broad_pattern, line):
            return broad_description
    return None


def _scan_file(path: Path, repo_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        description = _scan_line(line)
        if description is not None:
            violations.append(
                Violation(
                    path=path.relative_to(repo_root),
                    line=lineno,
                    pattern=description,
                    snapshot=line.strip(),
                )
            )
    return violations


def _resolve_repo_root(args: argparse.Namespace) -> Path:
    raw = args.repo_root or (args.positional_root if args.positional_root else None)
    if raw is None:
        return Path(__file__).resolve().parent.parent
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"repo root is not a directory: {root}")
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "positional_root",
        nargs="?",
        default=None,
        help="repository root path (default: parent of script directory)",
    )
    parser.add_argument(
        "--repo-root",
        dest="repo_root",
        default=None,
        help="repository root path (alternative to positional)",
    )
    args = parser.parse_args(argv)

    try:
        repo_root = _resolve_repo_root(args)
    except ValueError as exc:
        print(f"Safety atomic-write regression check ERROR: {exc}", file=sys.stderr)
        return 1

    guarded_paths = [repo_root / rel for rel in GUARDED_RELATIVE_PATHS]
    helper_path = repo_root / HELPER_RELATIVE_PATH

    missing = [p for p in guarded_paths + [helper_path] if not p.exists()]
    if missing:
        for p in missing:
            rel = p.relative_to(repo_root) if p.is_relative_to(repo_root) else p
            print(
                f"Safety atomic-write regression check ERROR: missing file {rel}",
                file=sys.stderr,
            )
        return 1

    violations: list[Violation] = []
    for path in guarded_paths:
        violations.extend(_scan_file(path, repo_root))

    if violations:
        print("Safety atomic-write regression check FAILED")
        for v in violations:
            print(f"  {v.path}:{v.line}: {v.pattern}")
            print(f"      {v.snapshot}")
        return 2

    print("Safety atomic-write regression check PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
