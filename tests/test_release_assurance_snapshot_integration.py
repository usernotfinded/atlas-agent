"""Integration tests for the optional reviewer trust snapshot in release assurance."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ASSURANCE_SCRIPT = REPO_ROOT / "scripts" / "release_assurance.py"


def _run_release_assurance(output_dir: Path, *extra_args: str) -> subprocess.CompletedProcess:
    """Run scripts/release_assurance.py with the given args and return the result."""
    return subprocess.run(
        [
            sys.executable,
            str(RELEASE_ASSURANCE_SCRIPT),
            "--version",
            "v0.6.11",
            "--output",
            str(output_dir),
            *extra_args,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_release_assurance_help_includes_snapshot_flag() -> None:
    text = RELEASE_ASSURANCE_SCRIPT.read_text(encoding="utf-8")
    assert "--include-reviewer-trust-snapshot" in text


def test_default_release_assurance_does_not_include_reviewer_snapshot(tmp_path: Path) -> None:
    result = _run_release_assurance(tmp_path)
    # The assurance pack itself is written even if some unrelated checks fail.
    summary_path = tmp_path / "release-assurance-summary.json"
    assert summary_path.exists(), result.stderr

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    snapshot_dir = tmp_path / "reviewer-trust-snapshot"
    assert not snapshot_dir.exists()
    assert "reviewer_trust_snapshot_included" not in summary


def test_opt_in_release_assurance_includes_valid_reviewer_snapshot(tmp_path: Path) -> None:
    result = _run_release_assurance(tmp_path, "--include-reviewer-trust-snapshot")
    summary_path = tmp_path / "release-assurance-summary.json"
    assert summary_path.exists(), result.stderr

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    snapshot_dir = tmp_path / "reviewer-trust-snapshot"
    assert snapshot_dir.exists()
    assert (snapshot_dir / "reviewer-trust-snapshot.json").exists()
    assert (snapshot_dir / "reviewer-trust-snapshot.md").exists()
    assert (snapshot_dir / "checksums.sha256").exists()
    assert summary.get("reviewer_trust_snapshot_included") is True
