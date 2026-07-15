# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_reviewer_trust_snapshot.py
# PURPOSE: Verifies reviewer trust snapshot behavior and regression
#         expectations.
# DEPS:    json, subprocess, sys, tempfile, pathlib, pytest.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[1]
BUILDER_SCRIPT = ROOT / "scripts" / "build_reviewer_trust_snapshot.py"
CHECKER_SCRIPT = ROOT / "scripts" / "check_reviewer_trust_snapshot.py"

REQUIRED_JSON_FILES = [
    "reviewer-trust-snapshot.json",
    "reviewer-trust-snapshot.md",
    "checksums.sha256",
]

REQUIRED_SAFETY_INVARIANTS = {
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


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run_builder(tmp_path: Path, *, deterministic: bool = True, extra_args: list[str] | None = None) -> Path:
    out_dir = tmp_path / "snapshot"
    cmd = [sys.executable, str(BUILDER_SCRIPT), "--output-dir", str(out_dir)]
    if deterministic:
        cmd.append("--deterministic")
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"Builder failed:\n{result.stderr}\n{result.stdout}"
    return out_dir


def _run_checker(snapshot_dir: Path, *, json_output: bool = False, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(CHECKER_SCRIPT)]
    if json_output:
        cmd.append("--json")
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(str(snapshot_dir))
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def test_builder_generates_required_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        for name in REQUIRED_JSON_FILES:
            assert (out_dir / name).exists(), f"Missing {name}"


def test_builder_json_has_required_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        snapshot = json.loads((out_dir / "reviewer-trust-snapshot.json").read_text(encoding="utf-8"))
        assert snapshot["schema_version"] == "atlas-reviewer-trust-snapshot/1.0"
        assert snapshot["repository"] == "usernotfinded/atlas-agent"
        assert snapshot["source_version"] != "unknown"
        assert snapshot["current_public_release"].startswith("v")
        assert snapshot["next_planned_release"].startswith("v")
        assert snapshot["pypi_published"] is False
        for key, expected in REQUIRED_SAFETY_INVARIANTS.items():
            assert snapshot["safety_invariants"][key] is expected, key
        assert "generated_files" in snapshot
        assert "checksums" in snapshot
        assert snapshot["checksums"]["reviewer-trust-snapshot.json"]
        assert snapshot["checksums"]["reviewer-trust-snapshot.md"]
        assert snapshot["checksums"]["checksums.sha256"]


def test_deterministic_mode_is_stable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp), deterministic=True)
        json_text_a = (out_dir / "reviewer-trust-snapshot.json").read_text(encoding="utf-8")
        md_text_a = (out_dir / "reviewer-trust-snapshot.md").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp), deterministic=True)
        json_text_b = (out_dir / "reviewer-trust-snapshot.json").read_text(encoding="utf-8")
        md_text_b = (out_dir / "reviewer-trust-snapshot.md").read_text(encoding="utf-8")

    assert json_text_a == json_text_b
    assert md_text_a == md_text_b
    assert "1970-01-01T00:00:00Z" in json_text_a


def test_checker_passes_on_valid_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        result = _run_checker(out_dir)
        assert result.returncode == 0, (
            f"Checker failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "PASSED" in result.stdout


def test_checker_json_output_on_valid_snapshot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        result = _run_checker(out_dir, json_output=True)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert "errors" in data
        assert "warnings" in data


def test_checker_self_test_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--self-test"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Checker self-test failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "PASSED" in result.stdout


def test_checker_fails_on_missing_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        (out_dir / "reviewer-trust-snapshot.json").unlink()
        result = _run_checker(out_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("reviewer-trust-snapshot.json" in err for err in data["errors"])


def test_checker_fails_on_missing_markdown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        (out_dir / "reviewer-trust-snapshot.md").unlink()
        result = _run_checker(out_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("reviewer-trust-snapshot.md" in err for err in data["errors"])


def test_checker_fails_on_unsafe_safety_booleans() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        snapshot_path = out_dir / "reviewer-trust-snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["safety_invariants"]["live_trading_disabled_by_default"] = False
        snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

        result = _run_checker(out_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("live_trading_disabled_by_default" in err for err in data["errors"])


def test_checker_fails_on_pypi_published_true() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        snapshot_path = out_dir / "reviewer-trust-snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["pypi_published"] = True
        snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

        result = _run_checker(out_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("pypi_published" in err for err in data["errors"])


def test_checker_fails_on_credential_like_strings() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        md_path = out_dir / "reviewer-trust-snapshot.md"
        md_path.write_text(
            md_path.read_text(encoding="utf-8")
            + "\nSecret token: sk-abcdefghijklmnopqrstuvwxyz\n",
            encoding="utf-8",
        )
        result = _run_checker(out_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("Secret-like pattern" in err for err in data["errors"])


def test_checker_fails_on_forbidden_claims() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        md_path = out_dir / "reviewer-trust-snapshot.md"
        md_path.write_text(
            md_path.read_text(encoding="utf-8") + "\nAtlas provides guaranteed profit.\n",
            encoding="utf-8",
        )
        result = _run_checker(out_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("guaranteed" in err.lower() or "profit" in err.lower() for err in data["errors"])


def test_checker_validates_checksums() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = _run_builder(Path(tmp))
        checksums_path = out_dir / "checksums.sha256"
        original = checksums_path.read_text(encoding="utf-8")
        # Corrupt a checksum line by changing the first hex char.
        corrupted = original[:1] + ("0" if original[0] != "0" else "1") + original[2:]
        checksums_path.write_text(corrupted, encoding="utf-8")

        result = _run_checker(out_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("Checksum mismatch" in err for err in data["errors"])


def test_builder_and_checker_help() -> None:
    for script in [BUILDER_SCRIPT, CHECKER_SCRIPT]:
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()


def test_builder_rejects_unknown_options() -> None:
    result = subprocess.run(
        [sys.executable, str(BUILDER_SCRIPT), "--not-a-real-option"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "Unknown option should be rejected"
    assert "error" in result.stderr.lower()


def test_checker_rejects_unknown_options() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--not-a-real-option"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "Unknown option should be rejected"
    assert "error" in result.stderr.lower()


def test_builder_accepts_ci_run_ids_and_evidence_bundle(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "evidence.json").write_text('{"demo_mode": "paper/dry-run"}\n', encoding="utf-8")

    out_dir = tmp_path / "snapshot"
    cmd = [
        sys.executable,
        str(BUILDER_SCRIPT),
        "--output-dir",
        str(out_dir),
        "--deterministic",
        "--ci-run-id",
        "12345",
        "--ci-run-id",
        "67890",
        "--research-ci-run-id",
        "54321",
        "--evidence-bundle",
        str(evidence_dir),
    ]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"Builder failed:\n{result.stderr}\n{result.stdout}"

    snapshot = json.loads((out_dir / "reviewer-trust-snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["ci_runs"]["main_ci_run_ids"] == ["12345", "67890"]
    assert snapshot["ci_runs"]["research_ci_run_id"] == "54321"
    assert snapshot["evidence_bundle"] is not None
    assert "checksum_sha256" in snapshot["evidence_bundle"]
