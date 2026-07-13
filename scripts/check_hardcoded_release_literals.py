#!/usr/bin/env python3
"""Detect hardcoded release-identity literals in active checker scripts.

Release identity (source version, current public tag, next planned tag) is
metadata-driven in docs/releases/release-metadata.json. Checker scripts that
embed the current version as string literals become stale at every release and
must be updated manually. This script scans active scripts for such literals and
fails when it finds them, so drift is caught at development time rather than
after a release cutover.

Deterministic and local. Does not:
- call network
- load credentials
- tag, push, publish, or mutate repository files
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
METADATA_PATH = REPO_ROOT / "docs" / "releases" / "release-metadata.json"
SCRIPTS_DIR = REPO_ROOT / "scripts"

DOCS_CONFIG_DIRS = [
    REPO_ROOT / "configs",
    REPO_ROOT / "examples",
    REPO_ROOT / "docs" / "examples",
]

# Historical release-specific checkers are intentionally pinned to their release
# and are excluded from this scan.
HISTORICAL_SCRIPT_PATTERN = ("check_v06", "check_v05")


class _LiteralVisitor(ast.NodeVisitor):
    def __init__(self, literals: set[str]) -> None:
        self.literals = literals
        self.findings: list[tuple[int, str, str]] = []

    def _record(self, lineno: int, value: str, context: str) -> None:
        if value in self.literals:
            self.findings.append((lineno, value, context))

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            # Skip docstrings (expression-statement strings).
            if isinstance(node.parent, ast.Expr):  # type: ignore[attr-defined]
                return
            context = self._context_name(node)
            self._record(node.lineno, node.value, context)
        self.generic_visit(node)

    def _context_name(self, node: ast.AST) -> str:
        parent = getattr(node, "parent", None)
        if isinstance(parent, ast.Compare):
            return "comparison"
        if isinstance(parent, ast.Assign):
            return "assignment"
        if isinstance(parent, ast.AnnAssign):
            return "annotated-assignment"
        if isinstance(parent, ast.Call):
            func = parent.func
            if isinstance(func, ast.Attribute):
                return f"call.{func.attr}"
            return "call"
        if isinstance(parent, ast.List | ast.Tuple | ast.Set | ast.Dict):
            return "collection"
        return "expression"


def _load_release_literals() -> set[str]:
    import json

    data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    source_version = data.get("source_version", "")
    current_public = data.get("current_public_release", "")
    next_planned = data.get("next_planned_release", "")

    literals: set[str] = set()
    for value in (source_version, current_public, next_planned):
        if value:
            literals.add(value)
            # Some scripts drop the leading "v".
            if value.startswith("v"):
                literals.add(value[1:])
            else:
                literals.add(f"v{value}")
    return literals


def _set_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)


def _is_active_script(path: Path) -> bool:
    if not path.name.endswith(".py"):
        return False
    if path.name.startswith(HISTORICAL_SCRIPT_PATTERN):
        return False
    return True


def _scan_file(path: Path, literals: set[str]) -> list[tuple[int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []

    _set_parents(tree)
    visitor = _LiteralVisitor(literals)
    visitor.visit(tree)
    return visitor.findings


def _scan_text_file(path: Path, pattern: re.Pattern[str]) -> list[tuple[int, str, str]]:
    """Scan a single text file for monitored release-identity literals.

    Returns a list of (lineno, literal, snippet) tuples.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Warning: could not read {path}: {exc}", file=sys.stderr)
        return []

    findings: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            snippet = line.strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            findings.append((lineno, match.group(0), snippet))
    return findings


def _scan_docs_config_dirs(
    literals: set[str],
) -> tuple[list[tuple[Path, int, str, str]], list[Path]]:
    """Scan configured docs/config example directories for monitored literals.

    Returns (findings, scanned_file_paths).
    """
    if not literals:
        return [], []

    pattern = re.compile("|".join(re.escape(lit) for lit in literals))
    findings: list[tuple[Path, int, str, str]] = []
    scanned_paths: list[Path] = []
    for directory in DOCS_CONFIG_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            scanned_paths.append(path)
            for lineno, value, snippet in _scan_text_file(path, pattern):
                findings.append((path, lineno, value, snippet))
    return findings, scanned_paths


def main() -> int:
    literals = _load_release_literals()
    if not literals:
        print("No release-identity literals loaded from metadata; nothing to check.")
        return 0

    script_findings: list[tuple[Path, int, str, str]] = []
    for path in sorted(SCRIPTS_DIR.iterdir()):
        if not _is_active_script(path):
            continue
        for lineno, value, context in _scan_file(path, literals):
            script_findings.append((path, lineno, value, context))

    docs_findings, docs_paths = _scan_docs_config_dirs(literals)

    if not script_findings and not docs_findings:
        print("Hardcoded release-literal check PASSED")
        print(f"  Scanned {len(list(SCRIPTS_DIR.glob('*.py')))} script file(s)")
        print(f"  Scanned {len(docs_paths)} docs/config example file(s)")
        print(f"  Monitored literals: {sorted(literals)}")
        return 0

    print("Hardcoded release-literal check FAILED")
    if script_findings:
        print("  Active scripts contain literals that should be metadata-driven:")
        for path, lineno, value, context in script_findings:
            rel = path.relative_to(REPO_ROOT)
            print(f"  - {rel}:{lineno} {context!r} literal {value!r}")
    if docs_findings:
        print("  Docs/config examples contain literals that should be metadata-driven:")
        for path, lineno, value, snippet in docs_findings:
            rel = path.relative_to(REPO_ROOT)
            print(f"  - {rel}:{lineno} literal {value!r}  # {snippet}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
