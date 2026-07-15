#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_release_assurance_bundle_manifest.py
# PURPOSE: Validate a release-assurance bundle manifest.
# DEPS:    argparse, hashlib, json, re, sys, pathlib, additional local modules.
# ==============================================================================

"""Validate a release-assurance bundle manifest.

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or invoke broker/provider execution.

Exit codes:
  0 = manifest valid
  1 = blocking findings
  2 = operational error (e.g., missing file)
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_SCHEMA_VERSION = "atlas-release-assurance-bundle-manifest/1.0"
MANIFEST_FILENAME = "release-assurance-bundle-manifest.json"

REQUIRED_FILES_PER_BUNDLE = [
    "release-assurance-summary.json",
    "release-assurance-report.md",
    "sha256sums.txt",
]

REQUIRED_SAFETY_INVARIANTS: dict[str, bool] = {
    "live_trading_disabled_by_default": True,
    "live_submit_disabled_by_default": True,
    "provider_execution_disabled_by_default": True,
    "broker_execution_disabled_by_default": True,
    "credentials_required_for_demo": False,
    "network_required_for_demo": False,
    "autonomous_trading_claimed": False,
    "profit_claims_absent": True,
    "no_risk_claims_absent": True,
}

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bAPCA-[A-Z0-9]{10,}", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}", re.IGNORECASE),
]

FORBIDDEN_CLAIMS = [
    "guaranteed profit",
    "guaranteed returns",
    "no risk trading",
    "risk-free trading",
    "risk free trading",
    "safe live trading",
    "production trading ready",
    "autonomous trading ready",
    "passive income",
    "financial freedom",
    "beat the market",
    "zero risk",
]

UNSAFE_COMMAND_PREFIXES = [
    "git push",
    "git tag ",
    "gh release create",
    "gh release upload",
    "twine" + " upload",
]


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    text = _read_text(manifest_path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Manifest is not valid JSON: {e}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_schema(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {MANIFEST_SCHEMA_VERSION!r}, "
            f"got {manifest.get('schema_version')!r}"
        )
    for key in ("release", "generated_at", "baseline_bundle", "snapshot_bundle",
                "reviewer_trust_snapshot_included", "generated_files", "checksums",
                "safety_invariants", "commands", "validation_summary"):
        if key not in manifest:
            errors.append(f"manifest missing key: {key}")
    return errors


def _check_bundle(
    manifest: dict[str, Any],
    bundle_key: str,
    *,
    expect_snapshot: bool,
    manifest_dir: Path,
) -> list[str]:
    errors: list[str] = []
    bundle = manifest.get(bundle_key)
    if not isinstance(bundle, dict):
        errors.append(f"{bundle_key} must be an object")
        return errors

    if not bundle.get("exists"):
        errors.append(f"{bundle_key} does not exist")
        return errors

    bundle_dir = manifest_dir / bundle.get("relative_path", bundle_key)
    if not bundle_dir.exists():
        # Fall back to absolute path if relative path is not under manifest dir.
        bundle_dir = Path(bundle.get("path", bundle_dir))

    if not bundle_dir.exists():
        errors.append(f"{bundle_key} path does not exist: {bundle_dir}")
        return errors

    for name in REQUIRED_FILES_PER_BUNDLE:
        if not (bundle_dir / name).is_file():
            errors.append(f"[{bundle_key}] Required file missing: {name}")

    included = bool(bundle.get("reviewer_trust_snapshot_included"))
    if included != expect_snapshot:
        errors.append(
            f"[{bundle_key}] reviewer_trust_snapshot_included must be "
            f"{expect_snapshot}, got {included}"
        )

    # Verify recorded file checksums for this bundle.
    for entry in bundle.get("files", []):
        rel = entry.get("relative_path")
        expected = entry.get("sha256")
        if not rel or not expected:
            continue
        file_path = bundle_dir / rel
        if not file_path.is_file():
            errors.append(f"[{bundle_key}] Referenced file missing: {rel}")
            continue
        actual = _sha256(file_path)
        if actual != expected:
            errors.append(
                f"[{bundle_key}] Checksum mismatch for {rel}"
            )

    return errors


def _check_snapshot_presence_consistency(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mapping = manifest.get("reviewer_trust_snapshot_included", {})
    baseline = manifest.get("baseline_bundle", {})
    snapshot = manifest.get("snapshot_bundle", {})

    baseline_name = baseline.get("relative_path", "baseline")
    snapshot_name = snapshot.get("relative_path", "snapshot_bundle")

    if mapping.get(baseline_name) is not False:
        errors.append(
            f"reviewer_trust_snapshot_included[{baseline_name}] must be False"
        )
    if mapping.get(snapshot_name) is not True:
        errors.append(
            f"reviewer_trust_snapshot_included[{snapshot_name}] must be True"
        )
    return errors


def _check_safety_invariants(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    invariants = manifest.get("safety_invariants", {})
    if not isinstance(invariants, dict):
        errors.append("safety_invariants must be an object")
        return errors
    for key, expected in REQUIRED_SAFETY_INVARIANTS.items():
        if key not in invariants:
            errors.append(f"safety_invariants missing key: {key}")
        elif invariants[key] is not expected:
            errors.append(
                f"safety_invariants['{key}'] must be {expected!r}, got {invariants[key]!r}"
            )
    return errors


def _scan_bundle_text(
    bundle_dir: Path,
    *,
    scan_secrets: bool = True,
    scan_claims: bool = True,
) -> list[str]:
    errors: list[str] = []
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = _read_text(path).lower()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(bundle_dir)

        if scan_secrets:
            for pattern in SECRET_PATTERNS:
                for m in pattern.finditer(text):
                    errors.append(
                        f"[{rel}] Secret-like pattern matched: {m.group(0)[:40]}"
                    )

        if scan_claims:
            for claim in FORBIDDEN_CLAIMS:
                if claim in text:
                    errors.append(
                        f"[{rel}] Forbidden claim found: {claim!r}"
                    )
    return errors


def _check_unsafe_commands(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    commands = manifest.get("commands", [])
    if not isinstance(commands, list):
        errors.append("commands must be a list")
        return errors
    for cmd in commands:
        if not isinstance(cmd, str):
            continue
        lower = cmd.lower()
        for unsafe in UNSAFE_COMMAND_PREFIXES:
            if lower.startswith(unsafe):
                if unsafe == "git tag " and "-l" in lower.split():
                    continue
                errors.append(f"Manifest command contains unsafe prefix: {cmd!r}")
    return errors


def _check_checksums(manifest: dict[str, Any], manifest_path: Path) -> list[str]:
    errors: list[str] = []
    checksums = manifest.get("checksums", {})
    if not isinstance(checksums, dict):
        errors.append("checksums must be an object")
        return errors

    return errors


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    if not manifest_path.exists():
        return {
            "passed": False,
            "errors": [f"Manifest file does not exist: {manifest_path}"],
            "warnings": [],
        }

    try:
        manifest = _load_manifest(manifest_path)
    except ValueError as e:
        return {
            "passed": False,
            "errors": [str(e)],
            "warnings": [],
        }

    errors: list[str] = []
    warnings: list[str] = []
    manifest_dir = manifest_path.parent

    errors.extend(_check_schema(manifest))
    errors.extend(_check_bundle(manifest, "baseline_bundle", expect_snapshot=False, manifest_dir=manifest_dir))
    errors.extend(_check_bundle(manifest, "snapshot_bundle", expect_snapshot=True, manifest_dir=manifest_dir))
    errors.extend(_check_snapshot_presence_consistency(manifest))
    errors.extend(_check_safety_invariants(manifest))
    errors.extend(_check_checksums(manifest, manifest_path))
    errors.extend(_check_unsafe_commands(manifest))

    # Scan bundle text for secrets and forbidden claims.
    for bundle_key, expect_snapshot in (
        ("baseline_bundle", False),
        ("snapshot_bundle", True),
    ):
        bundle = manifest.get(bundle_key, {})
        if not bundle.get("exists"):
            continue
        rel_path = bundle.get("relative_path", bundle_key)
        bundle_dir = manifest_dir / rel_path
        if not bundle_dir.exists():
            bundle_dir = Path(bundle.get("path", bundle_dir))
        if bundle_dir.exists():
            errors.extend(_scan_bundle_text(bundle_dir))

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a release-assurance bundle manifest. Static and local-only."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to manifest file or directory containing it.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    if not args.path:
        parser.error("path is required")

    input_path = Path(args.path).resolve()
    if input_path.is_dir():
        manifest_path = input_path / MANIFEST_FILENAME
    else:
        manifest_path = input_path

    result = validate_manifest(manifest_path)

    if args.json:
        summary = (
            "Release assurance bundle manifest check PASSED"
            if result["passed"]
            else "Release assurance bundle manifest check FAILED"
        )
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "manifest_path": str(manifest_path),
                    "summary": summary,
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Release assurance bundle manifest check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Release assurance bundle manifest check PASSED")
        print(f"  Manifest: {manifest_path}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
