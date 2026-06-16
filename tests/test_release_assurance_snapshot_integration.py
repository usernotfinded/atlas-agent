"""Integration tests for the optional reviewer trust snapshot in release assurance."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ASSURANCE_SCRIPT = REPO_ROOT / "scripts" / "release_assurance.py"
CHECKER_SCRIPT = (
    REPO_ROOT / "scripts" / "check_release_assurance_snapshot_integration.py"
)

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


def _write_minimal_release_assurance(
    path: Path,
    *,
    include_flag: bool = True,
    extra_body: str = "",
    unsafe_command: str = "",
) -> None:
    flag_arg = (
        """    parser.add_argument(
        "--include-reviewer-trust-snapshot",
        action="store_true",
        help="Include snapshot.",
    )
"""
        if include_flag
        else ""
    )
    body = f"""
    if args.include_reviewer_trust_snapshot:
        import build_reviewer_trust_snapshot
        import check_reviewer_trust_snapshot
        snapshot_dir = out_dir / "reviewer-trust-snapshot"
        build_reviewer_trust_snapshot.build_snapshot(snapshot_dir, deterministic=True)
        check_result = check_reviewer_trust_snapshot.run_checks(snapshot_dir)
        print(check_result)
{extra_body}
"""
    source = f"""import argparse
import subprocess
from pathlib import Path

def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)

def main():
    parser = argparse.ArgumentParser()
{flag_arg}    args = parser.parse_args()
    out_dir = Path(".")
{body}{unsafe_command}
    return 0

if __name__ == "__main__":
    main()
"""
    path.write_text(source, encoding="utf-8")


def _setup_temp_repo(tmp_path: Path) -> Path:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "build_reviewer_trust_snapshot.py").write_text("", encoding="utf-8")
    (scripts_dir / "check_reviewer_trust_snapshot.py").write_text("", encoding="utf-8")
    return scripts_dir


def _write_minimal_workflow(
    path: Path,
    *,
    include_input: bool = True,
    input_default_false: bool = True,
    secret: str = "",
) -> None:
    input_block = ""
    if include_input:
        default_line = "        default: false" if input_default_false else "        default: true"
        input_block = f"""      include_reviewer_trust_snapshot:
        description: "Include snapshot"
        type: boolean
        required: false
{default_line}
"""
    source = f"""name: Release Assurance

on:
  workflow_dispatch:
    inputs:
      release:
        description: "Release tag to verify"
        required: true
        default: "v0.6.11"
{input_block}
permissions:
  contents: read

jobs:
  release-assurance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Generate pack
        run: python scripts/release_assurance.py --version v0.6.11 --output out
{secret}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_checker_passes_on_real_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_checker_json_passes_on_real_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert "Release assurance snapshot integration check PASSED" in data["summary"]
    assert data["errors"] == []


def test_checker_fails_when_snapshot_flag_missing(tmp_path: Path) -> None:
    scripts_dir = _setup_temp_repo(tmp_path)
    _write_minimal_release_assurance(
        scripts_dir / "release_assurance.py", include_flag=False
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--repo-root", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "does not expose --include-reviewer-trust-snapshot" in result.stdout


def test_checker_fails_on_unsafe_command(tmp_path: Path) -> None:
    scripts_dir = _setup_temp_repo(tmp_path)
    _write_minimal_release_assurance(
        scripts_dir / "release_assurance.py",
        unsafe_command='    run_cmd(["git", "push"])\n',
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--repo-root", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "unsafe command" in result.stdout
    assert "git push" in result.stdout


def test_checker_fails_on_secret_reference(tmp_path: Path) -> None:
    scripts_dir = _setup_temp_repo(tmp_path)
    _write_minimal_release_assurance(
        scripts_dir / "release_assurance.py",
        extra_body='        secret = "sk-12345678901234567890"\n',
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--repo-root", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Secret-like reference" in result.stdout


def test_checker_json_reports_failure(tmp_path: Path) -> None:
    scripts_dir = _setup_temp_repo(tmp_path)
    _write_minimal_release_assurance(
        scripts_dir / "release_assurance.py", include_flag=False
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER_SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is False
    assert data["errors"]


def test_checker_fails_when_required_scripts_missing(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--repo-root", str(tmp_path), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is False
    assert any("build_reviewer_trust_snapshot.py" in e for e in data["errors"])


def test_checker_fails_when_workflow_input_defaults_to_true(tmp_path: Path) -> None:
    scripts_dir = _setup_temp_repo(tmp_path)
    _write_minimal_release_assurance(scripts_dir / "release_assurance.py")
    _write_minimal_workflow(
        tmp_path / ".github" / "workflows" / "release-assurance.yml",
        input_default_false=False,
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--repo-root", str(tmp_path), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is False
    assert any("default to false" in e for e in data["errors"])


def test_checker_fails_when_workflow_has_secret(tmp_path: Path) -> None:
    scripts_dir = _setup_temp_repo(tmp_path)
    _write_minimal_release_assurance(scripts_dir / "release_assurance.py")
    _write_minimal_workflow(
        tmp_path / ".github" / "workflows" / "release-assurance.yml",
        secret='        env:\n          TOKEN: "${{ secrets.GITHUB_TOKEN }}"\n',
    )

    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--repo-root", str(tmp_path), "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is False
    assert any("references secrets" in e for e in data["errors"])
