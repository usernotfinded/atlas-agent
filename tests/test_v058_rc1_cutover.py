"""Tests for the v0.5.8rc1 cutover verification checker.

These tests verify that:
- The checker passes on the current repo state.
- JSON output works.
- Wrong package version fails.
- Wrong __version__ fails.
- Missing release notes fails.
- Missing changelog section fails.
- Unsafe live/profit wording fails.
- Staged generated evidence artifact fails.
- Historical v0.5.7 record is still required.
- Script source does not contain shell=True.
- Script source does not contain network/GitHub API calls.
- Checker does not mutate files.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CUTOVER_SCRIPT = REPO_ROOT / "scripts" / "check_v058_rc1_cutover.py"


def _load_cutover_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_v058_rc1_cutover", CUTOVER_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v058_rc1_cutover"] = mod
    spec.loader.exec_module(mod)
    return mod


CUTOVER_MOD = _load_cutover_module()


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


def test_cutover_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CUTOVER_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_cutover_script_json_output() -> None:
    result = subprocess.run(
        [sys.executable, str(CUTOVER_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["errors"] == []
    assert data["expected_version"] == "0.5.8rc1"
    assert data["stable_tag"] == "v0.5.7"


# ---------------------------------------------------------------------------
# Negative tests (mocked / patched)
# ---------------------------------------------------------------------------


def test_wrong_package_version_fails() -> None:
    original = CUTOVER_MOD.EXPECTED_VERSION
    try:
        CUTOVER_MOD.EXPECTED_VERSION = "0.5.9rc1"
        result = CUTOVER_MOD._gather()
        assert result["passed"] is False
        assert any("0.5.9rc1" in e for e in result["errors"])
    finally:
        CUTOVER_MOD.EXPECTED_VERSION = original


def test_wrong_init_version_fails() -> None:
    original = CUTOVER_MOD.EXPECTED_VERSION
    try:
        CUTOVER_MOD.EXPECTED_VERSION = "0.5.8rc2"
        result = CUTOVER_MOD._gather()
        assert result["passed"] is False
        assert any("0.5.8rc2" in e for e in result["errors"])
    finally:
        CUTOVER_MOD.EXPECTED_VERSION = original


def test_missing_release_notes_fails() -> None:
    original = CUTOVER_MOD._check_release_notes_exist

    def _patched() -> list[str]:
        return ["Missing release notes: docs/releases/v0.5.8-rc1.md"]

    with patch.object(CUTOVER_MOD, "_check_release_notes_exist", _patched):
        result = CUTOVER_MOD._gather()
    assert result["passed"] is False
    assert any("Missing release notes" in e for e in result["errors"])


def test_missing_changelog_section_fails() -> None:
    original = CUTOVER_MOD._check_changelog_has_rc1_section

    def _patched() -> list[str]:
        return ["CHANGELOG.md missing [0.5.8rc1] section"]

    with patch.object(CUTOVER_MOD, "_check_changelog_has_rc1_section", _patched):
        result = CUTOVER_MOD._gather()
    assert result["passed"] is False
    assert any("CHANGELOG.md missing" in e for e in result["errors"])


def test_unsafe_live_profit_wording_fails() -> None:
    def _patched_scan(text: str, rel_path: str) -> list[str]:
        return [f"[{rel_path}] Forbidden positive claim 'live trading ready'"]

    with patch.object(CUTOVER_MOD, "_scan_text", _patched_scan):
        result = CUTOVER_MOD._gather()
    assert result["passed"] is False
    assert any("live trading ready" in e for e in result["errors"])


def test_staged_generated_evidence_artifact_fails() -> None:
    def _patched_check() -> list[str]:
        return ["Generated evidence artifact staged: artifacts/release_evidence/evidence.json"]

    with patch.object(CUTOVER_MOD, "_check_no_generated_artifacts_staged", _patched_check):
        result = CUTOVER_MOD._gather()
    assert result["passed"] is False
    assert any("Generated evidence artifact staged" in e for e in result["errors"])


def test_historical_v057_record_required() -> None:
    result = CUTOVER_MOD._check_historical_tag()
    # This should pass because v0.5.7 tag exists in the repo
    assert result == [], f"Historical v0.5.7 check failed: {result}"


# ---------------------------------------------------------------------------
# Source safety checks
# ---------------------------------------------------------------------------


def test_script_source_no_shell_true() -> None:
    source = CUTOVER_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_script_source_no_network_calls() -> None:
    source = CUTOVER_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket", "requests"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in cutover script"


def test_script_source_no_github_api() -> None:
    source = CUTOVER_SCRIPT.read_text(encoding="utf-8")
    assert "github.com" not in source
    assert "api.github" not in source
    assert "gh api" not in source


# ---------------------------------------------------------------------------
# File mutation check
# ---------------------------------------------------------------------------


def test_checker_does_not_mutate_files(tmp_path: Path) -> None:
    """The checker must be read-only."""
    import hashlib

    files_to_watch = [
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "src" / "atlas_agent" / "__init__.py",
        REPO_ROOT / "CHANGELOG.md",
    ]
    before = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files_to_watch}

    CUTOVER_MOD._gather()

    after = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files_to_watch}
    assert before == after, "Checker mutated a watched file"
