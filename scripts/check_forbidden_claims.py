#!/usr/bin/env python3
"""Scan docs and marketing files for forbidden safety/profit claims."""

import sys
from pathlib import Path

_FORBIDDEN_PHRASES = [
    "zero risk",
    "risk-free",
    "guaranteed profit",
    "profit guaranteed",
    "safe live trading",
    "unattended live trading",
    "guaranteed returns",
    "can't lose",
    "no risk",
]

_SCAN_TARGETS = [
    "README.md",
    "CHANGELOG.md",
    "docs",
    ".github/pull_request_template.md",
]


def _normalize_for_scan(line: str) -> str:
    """Return a normalized form where hyphens become spaces for phrase matching."""
    return line.replace("-", " ")


def _scan_file(path: Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, raw_line in enumerate(f, start=1):
                line_lower = raw_line.lower()
                norm_lower = _normalize_for_scan(line_lower)
                for phrase in _FORBIDDEN_PHRASES:
                    if phrase in line_lower or phrase in norm_lower:
                        findings.append((lineno, phrase))
    except (OSError, UnicodeDecodeError):
        # Skip unreadable or binary files
        pass
    return findings


def _collect_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for target in _SCAN_TARGETS:
        target_path = repo_root / target
        if not target_path.exists():
            continue
        if target_path.is_dir():
            for child in target_path.rglob("*"):
                if child.is_file() and not _is_binary(child):
                    paths.append(child)
        elif target_path.is_file():
            paths.append(target_path)
    return paths


def _is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        if b"\x00" in chunk:
            return True
    except OSError:
        return True
    return False


def main() -> int:
    if len(sys.argv) > 1:
        repo_root = Path(sys.argv[1])
    else:
        repo_root = Path(__file__).resolve().parent.parent

    paths = _collect_paths(repo_root)
    total_findings = 0

    for path in sorted(paths):
        findings = _scan_file(path)
        for lineno, phrase in findings:
            rel = path.relative_to(repo_root)
            print(f"{rel}:{lineno}: forbidden phrase: {phrase}")
            total_findings += 1

    if total_findings:
        return 2

    print("Forbidden claims scan clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
