"""Integration tests for the optional reviewer trust snapshot in release assurance."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ASSURANCE_SCRIPT = REPO_ROOT / "scripts" / "release_assurance.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import release_assurance  # noqa: E402


def _run_release_assurance(
    output_dir: Path, *extra_args: str
) -> subprocess.CompletedProcess:
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


def test_release_assurance_help_exposes_snapshot_flag() -> None:
    result = subprocess.run(
        [sys.executable, str(RELEASE_ASSURANCE_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--include-reviewer-trust-snapshot" in result.stdout


def test_default_release_assurance_does_not_include_reviewer_snapshot(
    tmp_path: Path,
) -> None:
    result = _run_release_assurance(tmp_path)
    # The assurance pack itself is written even if some unrelated checks fail.
    summary_path = tmp_path / "release-assurance-summary.json"
    assert summary_path.exists(), result.stderr

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    snapshot_dir = tmp_path / "reviewer-trust-snapshot"
    assert not snapshot_dir.exists()
    assert "reviewer_trust_snapshot_valid" not in summary


def test_opt_in_release_assurance_includes_valid_reviewer_snapshot(
    tmp_path: Path,
) -> None:
    result = _run_release_assurance(tmp_path, "--include-reviewer-trust-snapshot")
    summary_path = tmp_path / "release-assurance-summary.json"
    assert summary_path.exists(), result.stderr

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    snapshot_dir = tmp_path / "reviewer-trust-snapshot"
    assert snapshot_dir.exists()
    assert (snapshot_dir / "reviewer-trust-snapshot.json").exists()
    assert (snapshot_dir / "reviewer-trust-snapshot.md").exists()
    assert (snapshot_dir / "checksums.sha256").exists()
    assert summary.get("reviewer_trust_snapshot_valid") is True

    report = (tmp_path / "release-assurance-report.md").read_text(encoding="utf-8")
    assert "Reviewer Trust Snapshot" in report


def test_opt_in_release_assurance_fails_when_snapshot_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def mock_build_snapshot(*args, **kwargs):
        pass

    def mock_run_checks(*args, **kwargs):
        return {"passed": False, "errors": ["mock snapshot validation failure"]}

    monkeypatch.setattr(
        "build_reviewer_trust_snapshot.build_snapshot", mock_build_snapshot
    )
    monkeypatch.setattr("check_reviewer_trust_snapshot.run_checks", mock_run_checks)
    monkeypatch.setattr(
        "sys.argv",
        [
            "release_assurance.py",
            "--version",
            "v0.6.11",
            "--output",
            str(tmp_path),
            "--include-reviewer-trust-snapshot",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        release_assurance.main()

    assert exc_info.value.code == 1
    summary = json.loads(
        (tmp_path / "release-assurance-summary.json").read_text(encoding="utf-8")
    )
    assert summary.get("reviewer_trust_snapshot_valid") is False
    assert any("mock snapshot validation failure" in f for f in summary["findings"])

    report = (tmp_path / "release-assurance-report.md").read_text(encoding="utf-8")
    assert "mock snapshot validation failure" in report
