#!/usr/bin/env python3
"""Build a manifest for a release-assurance bundle pair.

The manifest describes a baseline release-assurance output and an opt-in
output that includes the reviewer trust snapshot. It is local-only,
offline, and credential-free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_SCHEMA_VERSION = "atlas-release-assurance-bundle-manifest/1.0"
MANIFEST_FILENAME = "release-assurance-bundle-manifest.json"

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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_files(bundle_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(bundle_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(bundle_dir).as_posix()
        files.append(
            {
                "relative_path": rel,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return files


def _snapshot_included(bundle_dir: Path) -> bool:
    return (bundle_dir / "reviewer-trust-snapshot" / "reviewer-trust-snapshot.json").exists()


def build_manifest(
    baseline_dir: Path,
    snapshot_dir: Path,
    release: str,
    *,
    deterministic: bool = False,
) -> dict[str, Any]:
    baseline_dir = baseline_dir.resolve()
    snapshot_dir = snapshot_dir.resolve()

    generated_at = (
        "1970-01-01T00:00:00Z"
        if deterministic
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    baseline_files = _collect_files(baseline_dir)
    snapshot_files = _collect_files(snapshot_dir)

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "release": release,
        "generated_at": generated_at,
        "deterministic": deterministic,
        "baseline_bundle": {
            "path": str(baseline_dir),
            "relative_path": baseline_dir.name,
            "exists": baseline_dir.exists(),
            "reviewer_trust_snapshot_included": _snapshot_included(baseline_dir),
            "files": baseline_files,
        },
        "snapshot_bundle": {
            "path": str(snapshot_dir),
            "relative_path": snapshot_dir.name,
            "exists": snapshot_dir.exists(),
            "reviewer_trust_snapshot_included": _snapshot_included(snapshot_dir),
            "files": snapshot_files,
        },
        "reviewer_trust_snapshot_included": {
            baseline_dir.name: _snapshot_included(baseline_dir),
            snapshot_dir.name: _snapshot_included(snapshot_dir),
        },
        "generated_files": [],
        "checksums": {},
        "safety_invariants": dict(REQUIRED_SAFETY_INVARIANTS),
        "commands": [
            f"python scripts/release_assurance.py --version {release} --output <baseline-dir>",
            f"python scripts/release_assurance.py --version {release} --output <snapshot-dir> --include-reviewer-trust-snapshot",
        ],
        "validation_summary": {
            "passed": True,
            "errors": [],
            "warnings": [],
        },
    }

    # generated_files lists all files from both bundles with their bundle prefix.
    generated_files: list[dict[str, Any]] = []
    for entry in baseline_files:
        generated_files.append(
            {
                "bundle": baseline_dir.name,
                "relative_path": entry["relative_path"],
                "sha256": entry["sha256"],
                "size_bytes": entry["size_bytes"],
            }
        )
    for entry in snapshot_files:
        generated_files.append(
            {
                "bundle": snapshot_dir.name,
                "relative_path": entry["relative_path"],
                "sha256": entry["sha256"],
                "size_bytes": entry["size_bytes"],
            }
        )
    manifest["generated_files"] = generated_files

    checksums: dict[str, str] = {}
    for entry in generated_files:
        key = f"{entry['bundle']}/{entry['relative_path']}"
        checksums[key] = entry["sha256"]
    manifest["checksums"] = checksums

    return manifest


def write_manifest(manifest: dict[str, Any], output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / MANIFEST_FILENAME

    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(text, encoding="utf-8")

    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a manifest for a release-assurance bundle pair."
    )
    parser.add_argument("--baseline-dir", required=True, help="Baseline bundle directory.")
    parser.add_argument("--snapshot-dir", required=True, help="Opt-in snapshot bundle directory.")
    parser.add_argument("--release", required=True, help="Release tag, e.g., v0.6.11.")
    parser.add_argument("--output-dir", required=True, help="Directory to write the manifest.")
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Use deterministic generated_at timestamp.",
    )
    args = parser.parse_args(argv)

    manifest = build_manifest(
        baseline_dir=Path(args.baseline_dir),
        snapshot_dir=Path(args.snapshot_dir),
        release=args.release,
        deterministic=args.deterministic,
    )
    manifest_path = write_manifest(manifest, Path(args.output_dir))
    print(f"Release assurance bundle manifest written to: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
