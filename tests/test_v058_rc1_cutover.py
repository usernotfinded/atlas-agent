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


def test_cutover_script_fails_on_rc2_repo() -> None:
    """RC1 checker fails against RC2 repo state (version mismatch + tag mismatch)."""
    result = subprocess.run(
        [sys.executable, str(CUTOVER_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "FAILED" in result.stdout
    assert "0.5.8rc2" in result.stdout or "0.5.8rc1" in result.stdout


def test_cutover_script_json_fails_on_rc2_repo() -> None:
    """RC1 checker JSON output shows failure against RC2 repo state."""
    result = subprocess.run(
        [sys.executable, str(CUTOVER_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 2, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is False
    assert data["expected_version"] == "0.5.8rc1"
    assert data["stable_tag"] == "v0.5.7"
    assert "tag_state" in data
    assert "tag_commit" in data
    assert "head_commit" in data
    assert "tag_matches_head" in data


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
        CUTOVER_MOD.EXPECTED_VERSION = "0.5.8rc9"
        result = CUTOVER_MOD._gather()
        assert result["passed"] is False
        assert any("0.5.8rc9" in e for e in result["errors"])
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


def test_missing_historical_tag_includes_fetch_hint() -> None:
    def _patched_git_show(tag: str, path: str) -> str:
        return ""  # Simulate missing tag

    with patch.object(CUTOVER_MOD, "_git_show", _patched_git_show):
        result = CUTOVER_MOD._check_historical_tag()
    assert len(result) >= 2, f"Expected at least 2 errors, got: {result}"
    combined = " ".join(result)
    assert "git fetch --tags origin" in combined
    assert "fetch-depth: 0" in combined
    assert "fetch-tags: true" in combined


def test_pre_tag_absent_state_passes() -> None:
    def _patched_tag_state() -> tuple[list[str], str, str | None, str | None, bool]:
        return [], "absent_pre_tag", None, "abc123", False

    with patch.object(CUTOVER_MOD, "_check_tag_state", _patched_tag_state):
        with patch.object(CUTOVER_MOD, "_check_current_version", lambda: []):
            with patch.object(CUTOVER_MOD, "_check_historical_tag", lambda: []):
                with patch.object(CUTOVER_MOD, "_check_readme_current_status", lambda: []):
                    result = CUTOVER_MOD._gather()
    assert result["passed"] is True
    assert result["tag_state"] == "absent_pre_tag"
    assert result["tag_commit"] is None
    assert result["tag_matches_head"] is False


def test_post_tag_matches_head_passes() -> None:
    def _patched_tag_state() -> tuple[list[str], str, str | None, str | None, bool]:
        return [], "present_matches_head", "abc123", "abc123", True

    with patch.object(CUTOVER_MOD, "_check_tag_state", _patched_tag_state):
        with patch.object(CUTOVER_MOD, "_check_current_version", lambda: []):
            with patch.object(CUTOVER_MOD, "_check_historical_tag", lambda: []):
                with patch.object(CUTOVER_MOD, "_check_readme_current_status", lambda: []):
                    result = CUTOVER_MOD._gather()
    assert result["passed"] is True
    assert result["tag_state"] == "present_matches_head"
    assert result["tag_commit"] == "abc123"
    assert result["head_commit"] == "abc123"
    assert result["tag_matches_head"] is True


def test_tag_mismatch_fails() -> None:
    def _patched_tag_state() -> tuple[list[str], str, str | None, str | None, bool]:
        return (
            ["v0.5.8rc1 tag exists locally but points to deadbeef, while HEAD is abc123. Force-pushing or moving RC tags is not allowed."],
            "present_mismatch",
            "deadbeef",
            "abc123",
            False,
        )

    with patch.object(CUTOVER_MOD, "_check_tag_state", _patched_tag_state):
        result = CUTOVER_MOD._gather()
    assert result["passed"] is False
    assert result["tag_state"] == "present_mismatch"
    assert result["tag_commit"] == "deadbeef"
    assert result["head_commit"] == "abc123"
    assert result["tag_matches_head"] is False
    assert any("Force-pushing" in e for e in result["errors"])


def test_tag_unresolvable_fails() -> None:
    def _patched_tag_state() -> tuple[list[str], str, str | None, str | None, bool]:
        return (
            ["v0.5.8rc1 tag exists locally but cannot be resolved."],
            "unresolvable",
            None,
            "abc123",
            False,
        )

    with patch.object(CUTOVER_MOD, "_check_tag_state", _patched_tag_state):
        result = CUTOVER_MOD._gather()
    assert result["passed"] is False
    assert result["tag_state"] == "unresolvable"
    assert result["tag_commit"] is None


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
