# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_release_assurance_workflow_artifact.py
# PURPOSE: Verifies release assurance workflow artifact behavior and regression
#         expectations.
# DEPS:    json, shutil, subprocess, sys, zipfile, pathlib, additional local
#         modules.
# ==============================================================================

"""Tests for the release-assurance workflow artifact checker."""

# --- IMPORTS ---

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.check_release_assurance_workflow_artifact import validate_artifact


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_release_assurance_workflow_artifact.py"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_release_assurance_bundle_manifest.py"
RELEASE = "v0.6.11"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run(*args: str | Path, cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(a) for a in args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )


def _make_bundle_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Create baseline and snapshot bundle directories with required files."""
    baseline_dir = tmp_path / "baseline"
    snapshot_dir = tmp_path / "with-reviewer-trust-snapshot"
    for bundle in (baseline_dir, snapshot_dir):
        bundle.mkdir(parents=True)
        for name in ("release-assurance-summary.json", "release-assurance-report.md", "sha256sums.txt"):
            (bundle / name).write_text("{}", encoding="utf-8")
    return baseline_dir, snapshot_dir


def _make_snapshot_subdir(snapshot_dir: Path, *, valid_checksums: bool = True) -> Path:
    """Create the reviewer-trust-snapshot subdirectory inside the snapshot bundle."""
    snap_dir = snapshot_dir / "reviewer-trust-snapshot"
    snap_dir.mkdir(parents=True)
    json_text = json.dumps({"schema_version": "atlas-reviewer-trust-snapshot/1.0"}, indent=2)
    (snap_dir / "reviewer-trust-snapshot.json").write_text(json_text, encoding="utf-8")
    (snap_dir / "reviewer-trust-snapshot.md").write_text("# Reviewer trust snapshot\n", encoding="utf-8")
    if valid_checksums:
        import hashlib

        lines: list[str] = []
        for name in ("reviewer-trust-snapshot.json", "reviewer-trust-snapshot.md"):
            digest = hashlib.sha256((snap_dir / name).read_bytes()).hexdigest()
            lines.append(f"{digest}  {name}")
        (snap_dir / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return snap_dir


def _build_manifest(baseline_dir: Path, snapshot_dir: Path, output_dir: Path) -> Path:
    result = _run(
        sys.executable,
        BUILD_SCRIPT,
        "--baseline-dir",
        str(baseline_dir),
        "--snapshot-dir",
        str(snapshot_dir),
        "--release",
        RELEASE,
        "--output-dir",
        str(output_dir),
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    manifest_path = output_dir / "release-assurance-bundle-manifest.json"
    assert manifest_path.exists()
    return manifest_path


def _make_valid_artifact(tmp_path: Path) -> Path:
    """Create a valid extracted artifact directory and return its path."""
    artifact_dir = tmp_path / "release-assurance-bundle-demo"
    baseline_dir = artifact_dir / "baseline"
    snapshot_dir = artifact_dir / "with-reviewer-trust-snapshot"
    _make_bundle_dirs(artifact_dir)
    _make_snapshot_subdir(snapshot_dir)
    _build_manifest(baseline_dir, snapshot_dir, artifact_dir)
    return artifact_dir


def _zip_artifact(artifact_dir: Path) -> Path:
    """Zip an extracted artifact directory and return the zip path."""
    zip_path = artifact_dir.parent / "artifact.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(artifact_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(artifact_dir.parent))
    return zip_path


class TestValidateArtifact:
    def test_passes_on_valid_directory(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        result = validate_artifact(artifact_dir)
        assert result["passed"] is True, result["errors"]
        assert result["artifact_path"] == str(artifact_dir)

    def test_passes_on_valid_zip(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        zip_path = _zip_artifact(artifact_dir)
        result = validate_artifact(zip_path)
        assert result["passed"] is True, result["errors"]
        assert result["artifact_path"] == str(zip_path)

    def test_fails_when_baseline_contains_snapshot(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        (artifact_dir / "baseline" / "reviewer-trust-snapshot").mkdir()
        (artifact_dir / "baseline" / "reviewer-trust-snapshot" / "reviewer-trust-snapshot.json").write_text(
            "{}", encoding="utf-8"
        )
        result = validate_artifact(artifact_dir)
        assert result["passed"] is False
        assert any("baseline" in e.lower() and "reviewer-trust-snapshot" in e.lower() for e in result["errors"])

    def test_fails_when_opt_in_bundle_lacks_snapshot(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        shutil.rmtree(artifact_dir / "with-reviewer-trust-snapshot" / "reviewer-trust-snapshot")
        # Rebuild manifest without the snapshot subdirectory.
        manifest_path = _build_manifest(
            artifact_dir / "baseline",
            artifact_dir / "with-reviewer-trust-snapshot",
            artifact_dir,
        )
        assert manifest_path.exists()
        result = validate_artifact(artifact_dir)
        assert result["passed"] is False
        assert any(
            "reviewer-trust-snapshot" in e.lower() and "snapshot" in e.lower() for e in result["errors"]
        )

    def test_fails_when_manifest_missing(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        (artifact_dir / "baseline").mkdir()
        (artifact_dir / "with-reviewer-trust-snapshot").mkdir()
        result = validate_artifact(artifact_dir)
        assert result["passed"] is False
        assert any("manifest" in e.lower() for e in result["errors"])

    def test_fails_on_credential_like_string(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        (artifact_dir / "baseline" / "leaked.txt").write_text(
            "sk-12345678901234567890abcdef", encoding="utf-8"
        )
        # Rebuild manifest so it references the new file.
        _build_manifest(
            artifact_dir / "baseline",
            artifact_dir / "with-reviewer-trust-snapshot",
            artifact_dir,
        )
        result = validate_artifact(artifact_dir)
        assert result["passed"] is False
        assert any("secret" in e.lower() for e in result["errors"])

    def test_fails_on_forbidden_claim(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        (artifact_dir / "with-reviewer-trust-snapshot" / "marketing.txt").write_text(
            "guaranteed profit", encoding="utf-8"
        )
        _build_manifest(
            artifact_dir / "baseline",
            artifact_dir / "with-reviewer-trust-snapshot",
            artifact_dir,
        )
        result = validate_artifact(artifact_dir)
        assert result["passed"] is False
        assert any("forbidden" in e.lower() for e in result["errors"])

    def test_fails_on_unsafe_command_evidence(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        (artifact_dir / "baseline" / "unsafe.sh").write_text(
            "gh release upload v0.0.0 dist/*\n", encoding="utf-8"
        )
        _build_manifest(
            artifact_dir / "baseline",
            artifact_dir / "with-reviewer-trust-snapshot",
            artifact_dir,
        )
        result = validate_artifact(artifact_dir)
        assert result["passed"] is False
        assert any("unsafe" in e.lower() for e in result["errors"])

    def test_json_output(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        result = validate_artifact(artifact_dir)
        assert "passed" in result
        assert "artifact_path" in result
        assert "manifest_path" in result
        assert "summary" in result
        assert "errors" in result
        assert "warnings" in result

    def test_fails_on_bad_snapshot_checksum(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        checksums_path = (
            artifact_dir
            / "with-reviewer-trust-snapshot"
            / "reviewer-trust-snapshot"
            / "checksums.sha256"
        )
        checksums_path.write_text(
            "0000000000000000000000000000000000000000000000000000000000000000  reviewer-trust-snapshot.json\n",
            encoding="utf-8",
        )
        result = validate_artifact(artifact_dir)
        assert result["passed"] is False
        assert any("checksum" in e.lower() for e in result["errors"])


class TestCLI:
    def test_help_works(self) -> None:
        result = _run(sys.executable, CHECK_SCRIPT, "--help", cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()

    def test_unknown_option_fails(self) -> None:
        result = _run(sys.executable, CHECK_SCRIPT, "--bad-option", cwd=REPO_ROOT)
        assert result.returncode != 0
        assert "unrecognized" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_cli_passes_on_valid_directory(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        result = _run(sys.executable, CHECK_SCRIPT, str(artifact_dir), cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr + "\n" + result.stdout
        assert "PASSED" in result.stdout

    def test_cli_passes_on_valid_zip(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        zip_path = _zip_artifact(artifact_dir)
        result = _run(sys.executable, CHECK_SCRIPT, str(zip_path), cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr + "\n" + result.stdout
        assert "PASSED" in result.stdout

    def test_cli_json_output(self, tmp_path: Path) -> None:
        artifact_dir = _make_valid_artifact(tmp_path)
        result = _run(sys.executable, CHECK_SCRIPT, str(artifact_dir), "--json", cwd=REPO_ROOT)
        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout)
        assert output["passed"] is True
        assert output["artifact_path"] == str(artifact_dir)
        assert "errors" in output
        assert "warnings" in output

    def test_cli_fails_on_invalid_artifact(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "artifact"
        artifact_dir.mkdir()
        result = _run(sys.executable, CHECK_SCRIPT, str(artifact_dir), cwd=REPO_ROOT)
        assert result.returncode == 2
