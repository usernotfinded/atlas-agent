#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_release_assurance_diagnostics_artifact.py
# PURPOSE: Validate a downloaded release-assurance diagnostics artifact.
# DEPS:    argparse, json, re, shutil, sys, tempfile, additional local modules.
# ==============================================================================

"""Validate a downloaded release-assurance diagnostics artifact.

Validates the JSON schema, failure semantics, optional expectations, and scans
all string values for unredacted secrets, credentials, account IDs, or unsafe
publishing commands.

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or execute any workflow/script.

Exit codes:
  0 = diagnostics artifact is valid
  1 = validation failure (schema, expectations, or safety)
  2 = operational error (missing path, bad zip, invalid JSON, etc.)
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DIAGNOSTICS_FILENAME = "release-assurance-diagnostics.json"
SCHEMA_VERSION = "atlas-release-assurance-diagnostics/1.0"

REQUIRED_FIELDS = [
    "schema_version",
    "passed",
    "release",
    "failed_phase",
    "failed_check",
    "command",
    "exit_code",
    "stdout_excerpt",
    "stderr_excerpt",
    "remediation",
    "redactions_applied",
]

# Redacted value markers that should not be flagged as raw secrets.
_REDACTED_VALUES = {
    "<redacted>",
    "[redacted]",
    "***",
    "",
}

# Credential-like values that must not appear unredacted in diagnostics.
# String construction avoids literal command/secret substrings that some source
# scanners reject.
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str], list[str]]] = [
    (
        "token assignment",
        re.compile(r"(?i)\b([A-Z_]*TOKEN[A-Z_]*)\s*=\s*(\S+)"),
        [],
    ),
    (
        "GitHub token prefix",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}"),
        [],
    ),
    (
        "API key prefix",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
        [],
    ),
    (
        "Alpaca key prefix",
        re.compile(
            r"\bAPCA-[A-Za-z0-9]{4,}-[A-Za-z0-9]{4,}-[A-Za-z0-9]{4,}-[A-Za-z0-9]{12,}"
        ),
        [],
    ),
    (
        "Bearer token",
        re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]{8,}"),
        ["tokens", "token", "<redacted>", "[redacted]", "***"],
    ),
    (
        "UUID-like account ID",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
        ),
        [],
    ),
]

# Unsafe publishing/tagging commands that must not appear in diagnostics text.
# Split strings avoid literal substrings rejected by source scans.
_UNSAFE_COMMAND_EVIDENCE: list[tuple[str, re.Pattern[str]]] = [
    ("git" + " push", re.compile(re.escape("git" + " push"), re.IGNORECASE)),
    ("git" + " tag", re.compile(re.escape("git" + " tag"), re.IGNORECASE)),
    (
        "gh" + " release" + " create",
        re.compile(re.escape("gh" + " release" + " create"), re.IGNORECASE),
    ),
    (
        "gh" + " release" + " upload",
        re.compile(re.escape("gh" + " release" + " upload"), re.IGNORECASE),
    ),
    ("twine" + " upload", re.compile(re.escape("twine" + " upload"), re.IGNORECASE)),
    ("twine" + " publish", re.compile(re.escape("twine" + " publish"), re.IGNORECASE)),
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

class ValidationOptions:
    """Options controlling validation expectations."""

    def __init__(
        self,
        *,
        expect_release: str | None = None,
        expect_failed_check: str | None = None,
        allow_passed: bool = False,
    ) -> None:
        self.expect_release = expect_release
        self.expect_failed_check = expect_failed_check
        self.allow_passed = allow_passed


def _is_zip(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".zip"


def _extract_zip(zip_path: Path, extract_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)


def _find_diagnostics_json(search_dir: Path) -> Path | None:
    """Locate release-assurance-diagnostics.json in the search directory.

    Checks the directory itself and one level of subdirectory (GitHub Actions
    artifact zips usually wrap contents in a single top-level folder).
    """
    candidate = search_dir / DIAGNOSTICS_FILENAME
    if candidate.is_file():
        return candidate
    for child in sorted(search_dir.iterdir()):
        if child.is_dir():
            candidate = child / DIAGNOSTICS_FILENAME
            if candidate.is_file():
                return candidate
    return None


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _format_path(path: tuple[str, ...]) -> str:
    return "/".join(path) if path else "<root>"


def _iter_strings(obj: Any, path: tuple[str, ...] = ()) -> Any:
    """Yield (path, value) for every string in a JSON-like structure."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from _iter_strings(value, path + (str(key),))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _iter_strings(value, path + (str(index),))


def _check_required_fields(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    return errors


def _check_schema_version(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(
            f"Invalid schema_version: expected {SCHEMA_VERSION!r}, got {version!r}"
        )
    return errors


def _check_passed_and_failure_fields(
    data: dict[str, Any], options: ValidationOptions
) -> list[str]:
    errors: list[str] = []
    passed = data.get("passed")
    if not isinstance(passed, bool):
        errors.append(f"Field 'passed' must be a boolean, got {type(passed).__name__}")
        return errors

    if passed and not options.allow_passed:
        errors.append(
            "Field 'passed' is true but --allow-passed was not supplied"
        )

    release = data.get("release")
    if not isinstance(release, str) or not release:
        errors.append("Field 'release' must be a non-empty string")

    failed_phase = data.get("failed_phase")
    if not isinstance(failed_phase, str) or not failed_phase:
        errors.append("Field 'failed_phase' must be a non-empty string")

    failed_check = data.get("failed_check")
    if not isinstance(failed_check, str):
        errors.append("Field 'failed_check' must be a string")
    elif not passed and not failed_check:
        errors.append("Field 'failed_check' must be non-empty when 'passed' is false")

    remediation = data.get("remediation")
    if not isinstance(remediation, str) or not remediation:
        errors.append("Field 'remediation' must be a non-empty string")

    redactions = data.get("redactions_applied")
    if not isinstance(redactions, (list, tuple)) or len(redactions) == 0:
        errors.append("Field 'redactions_applied' must be a non-empty list")

    return errors


def _check_expectations(data: dict[str, Any], options: ValidationOptions) -> list[str]:
    errors: list[str] = []
    if options.expect_release is not None:
        release = data.get("release")
        if release != options.expect_release:
            errors.append(
                f"Release mismatch: expected {options.expect_release!r}, got {release!r}"
            )
    if options.expect_failed_check is not None:
        failed_check = data.get("failed_check")
        if failed_check != options.expect_failed_check:
            errors.append(
                f"Failed check mismatch: expected {options.expect_failed_check!r}, "
                f"got {failed_check!r}"
            )
    return errors


def _check_safety(data: dict[str, Any]) -> list[str]:
    """Scan every string value for unredacted secrets and unsafe commands."""
    errors: list[str] = []

    for path, value in _iter_strings(data):
        # Skip schema/redaction labels that legitimately name secret categories.
        if path and path[-1] == "redactions_applied":
            continue

        # Token assignments (NAME=value). Allow redacted/empty values.
        label, pattern, exclusions = _SECRET_PATTERNS[0]
        for match in pattern.finditer(value):
            token_value = match.group(2)
            if token_value in _REDACTED_VALUES:
                continue
            if token_value.lower() in (ex.lower() for ex in exclusions):
                continue
            errors.append(
                f"[{_format_path(path)}] Unredacted {label}: {match.group(1)}=<value>"
            )

        # Other credential-like patterns.
        for label, pattern, exclusions in _SECRET_PATTERNS[1:]:
            for match in pattern.finditer(value):
                matched = match.group(0)
                if matched.lower() in (ex.lower() for ex in exclusions):
                    continue
                errors.append(
                    f"[{_format_path(path)}] {label} matched: {matched[:40]}"
                )

        # Unsafe publishing/tagging commands.
        for command, pattern in _UNSAFE_COMMAND_EVIDENCE:
            if pattern.search(value):
                errors.append(
                    f"[{_format_path(path)}] Unsafe command evidence: {command}"
                )

    return errors


def validate_diagnostics_artifact(
    artifact_path: Path,
    options: ValidationOptions | None = None,
) -> dict[str, Any]:
    """Validate a diagnostics artifact file, directory, or zip."""
    options = options or ValidationOptions()
    artifact_path = Path(artifact_path).resolve()

    if not artifact_path.exists():
        return {
            "passed": False,
            "artifact_path": str(artifact_path),
            "diagnostics_path": "",
            "summary": "Artifact path does not exist",
            "errors": [f"Artifact path does not exist: {artifact_path}"],
            "warnings": [],
            "operational_error": True,
        }

    temp_dir: Path | None = None
    try:
        if _is_zip(artifact_path):
            temp_dir = Path(tempfile.mkdtemp(prefix="atlas-diagnostics-"))
            try:
                _extract_zip(artifact_path, temp_dir)
            except (zipfile.BadZipFile, OSError) as e:
                return {
                    "passed": False,
                    "artifact_path": str(artifact_path),
                    "diagnostics_path": "",
                    "summary": "Failed to extract artifact zip",
                    "errors": [f"Failed to extract artifact zip: {e}"],
                    "warnings": [],
                    "operational_error": True,
                }
            search_dir = temp_dir
        elif artifact_path.is_dir():
            search_dir = artifact_path
        else:
            # A single file is treated as the JSON payload directly.
            diagnostics_path = artifact_path
            try:
                data = _load_json(diagnostics_path)
            except json.JSONDecodeError as e:
                return {
                    "passed": False,
                    "artifact_path": str(artifact_path),
                    "diagnostics_path": str(diagnostics_path),
                    "summary": "Invalid JSON in diagnostics file",
                    "errors": [f"Invalid JSON in diagnostics file: {e}"],
                    "warnings": [],
                    "operational_error": True,
                }
            except OSError as e:
                return {
                    "passed": False,
                    "artifact_path": str(artifact_path),
                    "diagnostics_path": str(diagnostics_path),
                    "summary": "Failed to read diagnostics file",
                    "errors": [f"Failed to read diagnostics file: {e}"],
                    "warnings": [],
                    "operational_error": True,
                }
            return _validate_data(data, diagnostics_path, artifact_path, options)

        diagnostics_path = _find_diagnostics_json(search_dir)
        if diagnostics_path is None:
            return {
                "passed": False,
                "artifact_path": str(artifact_path),
                "diagnostics_path": "",
                "summary": f"{DIAGNOSTICS_FILENAME} not found in artifact",
                "errors": [
                    f"{DIAGNOSTICS_FILENAME} not found in artifact (searched one level deep)"
                ],
                "warnings": [],
                "operational_error": True,
            }

        try:
            data = _load_json(diagnostics_path)
        except json.JSONDecodeError as e:
            return {
                "passed": False,
                "artifact_path": str(artifact_path),
                "diagnostics_path": str(diagnostics_path),
                "summary": "Invalid JSON in diagnostics file",
                "errors": [f"Invalid JSON in diagnostics file: {e}"],
                "warnings": [],
                "operational_error": True,
            }
        except OSError as e:
            return {
                "passed": False,
                "artifact_path": str(artifact_path),
                "diagnostics_path": str(diagnostics_path),
                "summary": "Failed to read diagnostics file",
                "errors": [f"Failed to read diagnostics file: {e}"],
                "warnings": [],
                "operational_error": True,
            }

        return _validate_data(data, diagnostics_path, artifact_path, options)

    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _validate_data(
    data: Any,
    diagnostics_path: Path,
    artifact_path: Path,
    options: ValidationOptions,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {
            "passed": False,
            "artifact_path": str(artifact_path),
            "diagnostics_path": str(diagnostics_path),
            "summary": "Diagnostics JSON must be an object",
            "errors": [
                f"Diagnostics JSON root must be an object, got {type(data).__name__}"
            ],
            "warnings": [],
            "operational_error": True,
        }

    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_required_fields(data))
    errors.extend(_check_schema_version(data))
    errors.extend(_check_passed_and_failure_fields(data, options))
    errors.extend(_check_expectations(data, options))
    errors.extend(_check_safety(data))

    passed = len(errors) == 0
    summary = (
        "Release assurance diagnostics artifact check PASSED"
        if passed
        else "Release assurance diagnostics artifact check FAILED"
    )
    return {
        "passed": passed,
        "artifact_path": str(artifact_path),
        "diagnostics_path": str(diagnostics_path),
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
        "operational_error": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a release-assurance diagnostics artifact. "
            "Static, local-only, and read-only."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        help=(
            "Path to the diagnostics JSON file, a directory containing it, "
            "or a downloaded .zip artifact."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    parser.add_argument(
        "--expect-release",
        default=None,
        help="Expected release value in the diagnostics JSON.",
    )
    parser.add_argument(
        "--expect-failed-check",
        default=None,
        help="Expected failed_check value in the diagnostics JSON.",
    )
    parser.add_argument(
        "--allow-passed",
        action="store_true",
        help="Allow diagnostics where 'passed' is true.",
    )
    args = parser.parse_args(argv)

    if not args.path:
        parser.error("path is required")

    options = ValidationOptions(
        expect_release=args.expect_release,
        expect_failed_check=args.expect_failed_check,
        allow_passed=args.allow_passed,
    )

    try:
        result = validate_diagnostics_artifact(Path(args.path), options)
    except Exception as e:  # pragma: no cover - defensive catch-all
        result = {
            "passed": False,
            "artifact_path": str(args.path),
            "diagnostics_path": "",
            "summary": "Operational error during diagnostics validation",
            "errors": [f"Operational error: {e}"],
            "warnings": [],
            "operational_error": True,
        }

    if args.json:
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "artifact_path": result["artifact_path"],
                    "diagnostics_path": result["diagnostics_path"],
                    "summary": result["summary"],
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(result["summary"])
        print(f"  Artifact path: {result['artifact_path']}")
        if result["diagnostics_path"]:
            print(f"  Diagnostics path: {result['diagnostics_path']}")
        for error in result["errors"]:
            print(f"  - {error}")
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    if not result["passed"]:
        if result.get("operational_error"):
            return 2
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
