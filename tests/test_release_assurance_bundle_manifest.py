"""Tests for release-assurance bundle manifest scripts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_release_assurance_bundle_manifest.py"
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_release_assurance_bundle_manifest.py"
RELEASE_ASSURANCE_SCRIPT = REPO_ROOT / "scripts" / "release_assurance.py"
DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_release_assurance_snapshot_bundle.sh"

RELEASE = "v0.6.12"


def _run(*args: str | Path, cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(a) for a in args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )


def _make_valid_fake_bundles(tmp_path: Path) -> tuple[Path, Path]:
    """Create minimal baseline and snapshot bundle dirs that pass validation."""
    baseline_dir = tmp_path / "baseline"
    snapshot_dir = tmp_path / "with-reviewer-trust-snapshot"
    for bundle in (baseline_dir, snapshot_dir):
        bundle.mkdir(parents=True)
        for name in ("release-assurance-summary.json", "release-assurance-report.md", "sha256sums.txt"):
            (bundle / name).write_text("", encoding="utf-8")
    (snapshot_dir / "reviewer-trust-snapshot").mkdir()
    (snapshot_dir / "reviewer-trust-snapshot" / "reviewer-trust-snapshot.json").write_text(
        "{}", encoding="utf-8"
    )
    return baseline_dir, snapshot_dir


def _build_manifest(
    baseline_dir: Path,
    snapshot_dir: Path,
    output_dir: Path,
    release: str = RELEASE,
    deterministic: bool = False,
) -> Path:
    args = [
        sys.executable,
        BUILD_SCRIPT,
        "--baseline-dir",
        str(baseline_dir),
        "--snapshot-dir",
        str(snapshot_dir),
        "--release",
        release,
        "--output-dir",
        str(output_dir),
    ]
    if deterministic:
        args.append("--deterministic")
    result = _run(*args, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    manifest_path = output_dir / "release-assurance-bundle-manifest.json"
    assert manifest_path.exists()
    return manifest_path


def test_demo_help_works():
    result = _run("bash", DEMO_SCRIPT, "--help")
    assert result.returncode == 0, result.stderr
    assert "Usage" in result.stdout


def test_demo_rejects_unknown_option():
    result = _run("bash", DEMO_SCRIPT, "--bad-option")
    assert result.returncode != 0
    assert "Unknown option" in result.stderr


def test_manifest_checker_passes_on_valid_temp_output(tmp_path: Path):
    baseline_dir = tmp_path / "baseline"
    snapshot_dir = tmp_path / "with-reviewer-trust-snapshot"

    baseline_result = _run(
        sys.executable,
        RELEASE_ASSURANCE_SCRIPT,
        "--version",
        RELEASE,
        "--output",
        str(baseline_dir),
        cwd=REPO_ROOT,
        timeout=180,
    )
    assert baseline_result.returncode == 0, baseline_result.stderr

    snapshot_result = _run(
        sys.executable,
        RELEASE_ASSURANCE_SCRIPT,
        "--version",
        RELEASE,
        "--output",
        str(snapshot_dir),
        "--include-reviewer-trust-snapshot",
        cwd=REPO_ROOT,
        timeout=180,
    )
    assert snapshot_result.returncode == 0, snapshot_result.stderr

    manifest_path = _build_manifest(baseline_dir, snapshot_dir, tmp_path)

    check_result = _run(sys.executable, CHECK_SCRIPT, str(manifest_path), cwd=REPO_ROOT)
    assert check_result.returncode == 0, check_result.stderr + "\n" + check_result.stdout
    assert "PASSED" in check_result.stdout


def test_manifest_checker_fails_snapshot_in_baseline(tmp_path: Path):
    baseline_dir, snapshot_dir = _make_valid_fake_bundles(tmp_path)
    manifest_path = _build_manifest(baseline_dir, snapshot_dir, tmp_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline_name = manifest["baseline_bundle"]["relative_path"]
    manifest["baseline_bundle"]["reviewer_trust_snapshot_included"] = True
    manifest["reviewer_trust_snapshot_included"][baseline_name] = True
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    result = _run(sys.executable, CHECK_SCRIPT, str(manifest_path), cwd=REPO_ROOT)
    assert result.returncode != 0
    assert "reviewer_trust_snapshot_included" in result.stdout


def test_manifest_checker_fails_snapshot_missing_in_opt_in(tmp_path: Path):
    baseline_dir, snapshot_dir = _make_valid_fake_bundles(tmp_path)
    manifest_path = _build_manifest(baseline_dir, snapshot_dir, tmp_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_name = manifest["snapshot_bundle"]["relative_path"]
    manifest["snapshot_bundle"]["reviewer_trust_snapshot_included"] = False
    manifest["reviewer_trust_snapshot_included"][snapshot_name] = False
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    result = _run(sys.executable, CHECK_SCRIPT, str(manifest_path), cwd=REPO_ROOT)
    assert result.returncode != 0
    assert "reviewer_trust_snapshot_included" in result.stdout


def test_manifest_checker_fails_credential_like_string(tmp_path: Path):
    baseline_dir, snapshot_dir = _make_valid_fake_bundles(tmp_path)
    (baseline_dir / "leaked.txt").write_text("sk-12345678901234567890", encoding="utf-8")
    manifest_path = _build_manifest(baseline_dir, snapshot_dir, tmp_path)

    result = _run(sys.executable, CHECK_SCRIPT, str(manifest_path), cwd=REPO_ROOT)
    assert result.returncode != 0
    assert "Secret-like pattern matched" in result.stdout


def test_manifest_checker_fails_forbidden_claim(tmp_path: Path):
    baseline_dir, snapshot_dir = _make_valid_fake_bundles(tmp_path)
    (baseline_dir / "marketing.txt").write_text("guaranteed profit", encoding="utf-8")
    manifest_path = _build_manifest(baseline_dir, snapshot_dir, tmp_path)

    result = _run(sys.executable, CHECK_SCRIPT, str(manifest_path), cwd=REPO_ROOT)
    assert result.returncode != 0
    assert "Forbidden claim found" in result.stdout


def test_manifest_checker_json_output(tmp_path: Path):
    baseline_dir, snapshot_dir = _make_valid_fake_bundles(tmp_path)
    manifest_path = _build_manifest(baseline_dir, snapshot_dir, tmp_path)

    result = _run(sys.executable, CHECK_SCRIPT, str(manifest_path), "--json", cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert isinstance(output["passed"], bool)
    assert output["passed"] is True


@pytest.mark.slow
def test_demo_runs_end_to_end(tmp_path: Path):
    result = _run(
        "bash",
        DEMO_SCRIPT,
        "--output-dir",
        str(tmp_path),
        "--deterministic",
        cwd=REPO_ROOT,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr + "\n" + result.stdout

    manifest_path = tmp_path / "release-assurance-bundle-manifest.json"
    assert manifest_path.exists()
    assert (tmp_path / "baseline").is_dir()
    assert (tmp_path / "with-reviewer-trust-snapshot").is_dir()

    check_result = _run(sys.executable, CHECK_SCRIPT, str(manifest_path), cwd=REPO_ROOT)
    assert check_result.returncode == 0, check_result.stderr + "\n" + check_result.stdout
    assert "PASSED" in check_result.stdout
