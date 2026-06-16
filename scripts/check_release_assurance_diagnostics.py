#!/usr/bin/env python3
"""Static checker for release-assurance failure diagnostics (CAND-011).

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or execute any workflow/script.

Exit codes:
  0 = all checks passed
  1 = blocking findings
  2 = operational error
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_FILE = REPO_ROOT / "tests" / "test_release_assurance_diagnostics.py"
DOCS_FILE = REPO_ROOT / "docs" / "security" / "release-assurance-diagnostics.md"
RELEASE_ASSURANCE_SCRIPT = REPO_ROOT / "scripts" / "release_assurance.py"

REQUIRED_REDACTION_CATEGORIES = [
    ("GH_TOKEN", ["GH_TOKEN", "[A-Z_]*TOKEN[A-Z_]*"]),
    ("GITHUB_TOKEN", ["GITHUB_TOKEN", "[A-Z_]*TOKEN[A-Z_]*"]),
    ("*_TOKEN", ["[A-Z_]*TOKEN[A-Z_]*"]),
    ("Bearer", ["Bearer"]),
    ("sk-", ["sk-"]),
    ("APCA-", ["APCA-"]),
    ("UUID-like account IDs", ["{8}-", "{4}-", "{12}"]),
]

REQUIRED_TEST_COVERAGE = [
    ("failing check name", re.compile(r"failing_check|failing check name", re.IGNORECASE)),
    ("release version", re.compile(r"release.*version|version.*release", re.IGNORECASE)),
    ("remediation hint", re.compile(r"remediation", re.IGNORECASE)),
    ("exit code", re.compile(r"exit_code|exit code", re.IGNORECASE)),
    ("redaction", re.compile(r"redact", re.IGNORECASE)),
    ("diagnostics JSON", re.compile(r"diagnostics.*json|diagnostics_json", re.IGNORECASE)),
]


def _read_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def _check_file_exists(path: Path, label: str) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        errors.append(f"{label} missing: {rel}")
    return errors


def _check_redact_text_defined(source: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        errors.append(f"Could not parse {RELEASE_ASSURANCE_SCRIPT.name}: {e}")
        return errors

    found = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "redact_text"
        for node in ast.walk(tree)
    )
    if not found:
        errors.append(
            f"{RELEASE_ASSURANCE_SCRIPT.name} must define a function named 'redact_text'"
        )
    return errors


def _check_redaction_patterns(source: str) -> list[str]:
    errors: list[str] = []

    # Extract the _REDACTION_PATTERNS assignment block as raw text so regex
    # literals can be inspected without evaluating them.
    match = re.search(
        r"_REDACTION_PATTERNS\s*=\s*\[(.*?)\n\]",
        source,
        re.DOTALL,
    )
    if not match:
        errors.append(
            f"{RELEASE_ASSURANCE_SCRIPT.name} must define _REDACTION_PATTERNS"
        )
        return errors

    block = match.group(1)
    for label, fragments in REQUIRED_REDACTION_CATEGORIES:
        if not any(fragment in block for fragment in fragments):
            errors.append(
                f"_REDACTION_PATTERNS must cover {label} redaction"
            )
    return errors


def _check_test_coverage(source: str) -> list[str]:
    errors: list[str] = []
    for label, pattern in REQUIRED_TEST_COVERAGE:
        if not pattern.search(source):
            errors.append(
                f"{TEST_FILE.name} must contain a test covering {label}"
            )
    return errors


def check_diagnostics() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_file_exists(TEST_FILE, "Test file"))
    errors.extend(_check_file_exists(DOCS_FILE, "Documentation file"))

    if not RELEASE_ASSURANCE_SCRIPT.exists():
        errors.append(
            f"Release assurance script missing: {RELEASE_ASSURANCE_SCRIPT.relative_to(REPO_ROOT)}"
        )
        return {"passed": False, "errors": errors, "warnings": warnings}

    try:
        release_source = _read_file(RELEASE_ASSURANCE_SCRIPT)
    except FileNotFoundError as e:
        return {"passed": False, "errors": [str(e)], "warnings": warnings}

    try:
        test_source = _read_file(TEST_FILE)
    except FileNotFoundError as e:
        errors.append(str(e))
        test_source = ""

    errors.extend(_check_redact_text_defined(release_source))
    errors.extend(_check_redaction_patterns(release_source))

    if test_source:
        errors.extend(_check_test_coverage(test_source))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static checker for release-assurance failure diagnostics (CAND-011)."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    args = parser.parse_args(argv)

    try:
        result = check_diagnostics()
    except Exception as e:
        if args.json:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "errors": [f"Operational error: {e}"],
                        "warnings": [],
                        "summary": "Release assurance diagnostics check: operational error",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("Release assurance diagnostics check: operational error")
            print(f"  - {e}")
        return 2

    summary = (
        "Release assurance diagnostics check PASSED"
        if result["passed"]
        else "Release assurance diagnostics check FAILED"
    )

    if args.json:
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                    "summary": summary,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Release assurance diagnostics check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Release assurance diagnostics check PASSED")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
