#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_release_assurance_workflow_artifact.py
# PURPOSE: Validate a downloaded GitHub Actions artifact from the
#         release-assurance.yml optional `run_bundle_demo` path.
# DEPS:    argparse, hashlib, json, shutil, sys, tempfile, additional local
#         modules.
# ==============================================================================

"""Validate a downloaded GitHub Actions artifact from the release-assurance.yml
optional `run_bundle_demo` path.

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or invoke broker/provider execution.

Exit codes:
  0 = artifact valid
  1 = blocking findings
  2 = operational error (e.g., missing file or bad zip)
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


# Ensure the repository root is on sys.path so `scripts.*` imports work when this
# script is invoked directly.
# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_release_assurance_bundle_manifest import (
    FORBIDDEN_CLAIMS,
    MANIFEST_FILENAME,
    SECRET_PATTERNS,
    validate_manifest,
)


BASELINE_DIR_NAME = "baseline"
SNAPSHOT_DIR_NAME = "with-reviewer-trust-snapshot"
REVIEWER_TRUST_SNAPSHOT_DIR_NAME = "reviewer-trust-snapshot"
REQUIRED_SNAPSHOT_FILES = [
    "reviewer-trust-snapshot.json",
    "reviewer-trust-snapshot.md",
]

# Unsafe command evidence to look for anywhere in artifact text files. Keep in
# sync with the manifest checker's command prefix list, plus twine publish.
UNSAFE_COMMAND_EVIDENCE = [
    "git push",
    "git tag",
    "gh release create",
    "gh release upload",
    "twine" + " upload",
    "twine" + " publish",
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _is_zip(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".zip"


def _extract_zip(zip_path: Path, extract_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)


def _find_artifact_root(search_dir: Path) -> Path | None:
    """Return the directory containing the manifest, searching one level deep."""
    candidate = search_dir / MANIFEST_FILENAME
    if candidate.is_file():
        return search_dir
    for child in sorted(search_dir.iterdir()):
        if child.is_dir():
            candidate = child / MANIFEST_FILENAME
            if candidate.is_file():
                return child
    return None


def _check_required_directories(artifact_root: Path) -> list[str]:
    errors: list[str] = []
    baseline_dir = artifact_root / BASELINE_DIR_NAME
    snapshot_dir = artifact_root / SNAPSHOT_DIR_NAME
    if not baseline_dir.is_dir():
        errors.append(f"Missing required directory: {BASELINE_DIR_NAME}/")
    if not snapshot_dir.is_dir():
        errors.append(f"Missing required directory: {SNAPSHOT_DIR_NAME}/")
    return errors


def _check_snapshot_presence(artifact_root: Path) -> list[str]:
    """Ensure baseline has no snapshot and the opt-in bundle has one."""
    errors: list[str] = []
    baseline_snapshot = artifact_root / BASELINE_DIR_NAME / REVIEWER_TRUST_SNAPSHOT_DIR_NAME
    snapshot_snapshot = artifact_root / SNAPSHOT_DIR_NAME / REVIEWER_TRUST_SNAPSHOT_DIR_NAME

    if baseline_snapshot.exists():
        errors.append(
            f"Baseline directory must not contain {REVIEWER_TRUST_SNAPSHOT_DIR_NAME}/"
        )
    if not snapshot_snapshot.exists():
        errors.append(
            f"Opt-in snapshot directory must contain {REVIEWER_TRUST_SNAPSHOT_DIR_NAME}/"
        )
    return errors


def _check_snapshot_files(snapshot_dir: Path) -> list[str]:
    """Validate reviewer-trust-snapshot contents inside the opt-in bundle."""
    errors: list[str] = []
    for name in REQUIRED_SNAPSHOT_FILES:
        if not (snapshot_dir / name).is_file():
            errors.append(f"Missing required reviewer trust snapshot file: {name}")

    checksums_path = snapshot_dir / "checksums.sha256"
    if checksums_path.is_file():
        errors.extend(_check_snapshot_checksums(snapshot_dir, checksums_path))

    return errors


def _check_snapshot_checksums(snapshot_dir: Path, checksums_path: Path) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for lineno, line in enumerate(_read_text(checksums_path).splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            errors.append(f"[checksums.sha256] Malformed line {lineno}: {line!r}")
            continue
        digest, rel_path = parts
        if rel_path in seen:
            errors.append(f"[checksums.sha256] Duplicate entry: {rel_path}")
            continue
        seen.add(rel_path)
        file_path = snapshot_dir / rel_path
        if not file_path.is_file():
            errors.append(f"[checksums.sha256] Referenced file missing: {rel_path}")
            continue
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual != digest:
            errors.append(f"[checksums.sha256] Checksum mismatch for {rel_path}")
    return errors


def _scan_text_files(artifact_root: Path) -> list[str]:
    """Scan all readable text files for secrets, forbidden claims, and unsafe commands."""
    errors: list[str] = []
    for path in sorted(artifact_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = _read_text(path).lower()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(artifact_root)

        for pattern in SECRET_PATTERNS:
            for m in pattern.finditer(text):
                errors.append(
                    f"[{rel}] Secret-like pattern matched: {m.group(0)[:40]}"
                )

        for claim in FORBIDDEN_CLAIMS:
            if claim in text:
                errors.append(f"[{rel}] Forbidden claim found: {claim!r}")

        for unsafe in UNSAFE_COMMAND_EVIDENCE:
            if unsafe in text:
                errors.append(f"[{rel}] Unsafe command evidence found: {unsafe!r}")

    return errors


def validate_artifact(artifact_path: Path) -> dict[str, Any]:
    """Validate an extracted artifact directory or a downloaded artifact zip."""
    artifact_path = Path(artifact_path).resolve()
    warnings: list[str] = []

    if not artifact_path.exists():
        return {
            "passed": False,
            "artifact_path": str(artifact_path),
            "manifest_path": "",
            "summary": "Artifact path does not exist",
            "errors": [f"Artifact path does not exist: {artifact_path}"],
            "warnings": warnings,
            "operational_error": True,
        }

    temp_dir: Path | None = None
    try:
        if _is_zip(artifact_path):
            temp_dir = Path(tempfile.mkdtemp(prefix="atlas-artifact-"))
            try:
                _extract_zip(artifact_path, temp_dir)
            except (zipfile.BadZipFile, OSError) as e:
                return {
                    "passed": False,
                    "artifact_path": str(artifact_path),
                    "manifest_path": "",
                    "summary": "Failed to extract artifact zip",
                    "errors": [f"Failed to extract artifact zip: {e}"],
                    "warnings": warnings,
                    "operational_error": True,
                }
            search_dir = temp_dir
        else:
            search_dir = artifact_path

        artifact_root = _find_artifact_root(search_dir)
        if artifact_root is None:
            return {
                "passed": False,
                "artifact_path": str(artifact_path),
                "manifest_path": "",
                "summary": f"Manifest {MANIFEST_FILENAME} not found in artifact",
                "errors": [f"Manifest {MANIFEST_FILENAME} not found in artifact (searched one level deep)"],
                "warnings": warnings,
                "operational_error": True,
            }

        manifest_path = artifact_root / MANIFEST_FILENAME
        errors: list[str] = []

        errors.extend(_check_required_directories(artifact_root))
        errors.extend(_check_snapshot_presence(artifact_root))

        snapshot_dir = artifact_root / SNAPSHOT_DIR_NAME / REVIEWER_TRUST_SNAPSHOT_DIR_NAME
        if snapshot_dir.is_dir():
            errors.extend(_check_snapshot_files(snapshot_dir))

        # Run the existing manifest checker on the manifest.
        manifest_result = validate_manifest(manifest_path)
        if not manifest_result["passed"]:
            errors.extend(manifest_result["errors"])
        if manifest_result.get("warnings"):
            warnings.extend(manifest_result["warnings"])

        # Scan all artifact text files for secrets, claims, and unsafe commands.
        errors.extend(_scan_text_files(artifact_root))

        passed = len(errors) == 0
        summary = (
            "Release assurance workflow artifact check PASSED"
            if passed
            else "Release assurance workflow artifact check FAILED"
        )
        return {
            "passed": passed,
            "artifact_path": str(artifact_path),
            "manifest_path": str(manifest_path),
            "summary": summary,
            "errors": errors,
            "warnings": warnings,
            "operational_error": False,
        }

    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a downloaded release-assurance workflow artifact. "
            "Static, local-only, and read-only."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to the extracted artifact directory or the downloaded .zip file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output.",
    )
    args = parser.parse_args(argv)

    if not args.path:
        parser.error("path is required")

    try:
        result = validate_artifact(Path(args.path))
    except Exception as e:  # pragma: no cover - defensive catch-all
        result = {
            "passed": False,
            "artifact_path": str(args.path),
            "manifest_path": "",
            "summary": "Operational error during artifact validation",
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
                    "manifest_path": result["manifest_path"],
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
        if result["manifest_path"]:
            print(f"  Manifest path: {result['manifest_path']}")
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
