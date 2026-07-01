"""Tests for the v0.5.8.1 hotfix cutover verification checker.

These tests verify that:
- The checker passes on the current repo state.
- JSON output works.
- Wrong package version fails.
- Missing release notes fails.
- Missing changelog section fails.
- Unsafe live/profit wording fails.
- Historical v0.5.8 remains intact.
- Active v0.5.8.1 tag absence passes before tagging.
- Active v0.5.8.1 tag must match HEAD when present.
- Script source does not contain shell=True.
- Script source does not contain network/GitHub API calls.
- Checker does not mutate files.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CUTOVER_SCRIPT = REPO_ROOT / "scripts" / "historical_release_checkers" / "check_v0581_hotfix_cutover.py"


def _load_cutover_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_v0581_hotfix_cutover", CUTOVER_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0581_hotfix_cutover"] = mod
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
    assert data["expected_version"] == "0.6.17"
    assert data["stable_tag"] == "v0.5.8"
    assert data["active_release"] == "v0.5.8.1"
    assert "historical_rc_tags" in data
    assert "tag_state" in data
    assert data["tag_state"] in {
        "absent_pre_tag",
        "present_matches_head",
        "present_historical_release",
    }
    assert "tag_commit" in data
    assert "head_commit" in data
    assert "tag_matches_head" in data


# ---------------------------------------------------------------------------
# Negative tests (mocked / patched)
# ---------------------------------------------------------------------------


def test_wrong_package_version_fails() -> None:
    original = CUTOVER_MOD.EXPECTED_VERSION
    try:
        CUTOVER_MOD.EXPECTED_VERSION = "0.5.9rc3"
        result = CUTOVER_MOD._gather()
        assert result["passed"] is False
        assert any("0.5.9rc3" in e for e in result["errors"])
    finally:
        CUTOVER_MOD.EXPECTED_VERSION = original


def test_wrong_init_version_fails() -> None:
    original = CUTOVER_MOD.EXPECTED_VERSION
    try:
        CUTOVER_MOD.EXPECTED_VERSION = "0.5.8.2"
        result = CUTOVER_MOD._gather()
        assert result["passed"] is False
        assert any("0.5.8.2" in e for e in result["errors"])
    finally:
        CUTOVER_MOD.EXPECTED_VERSION = original


def test_missing_release_notes_fails() -> None:
    original = CUTOVER_MOD._check_release_notes_exist

    def _patched() -> list[str]:
        return ["Missing release notes: docs/releases/v0.5.8.1.md"]

    with patch.object(CUTOVER_MOD, "_check_release_notes_exist", _patched):
        result = CUTOVER_MOD._gather()
    assert result["passed"] is False
    assert any("Missing release notes" in e for e in result["errors"])


def test_missing_changelog_section_fails() -> None:
    original = CUTOVER_MOD._check_changelog_has_stable_section

    def _patched() -> list[str]:
        return ["CHANGELOG.md missing [0.5.8.1] section"]

    with patch.object(CUTOVER_MOD, "_check_changelog_has_stable_section", _patched):
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


def test_historical_v058_record_required() -> None:
    result = CUTOVER_MOD._check_historical_tag()
    # This should pass because v0.5.8 tag exists in the repo
    assert result == [], f"Historical v0.5.8 check failed: {result}"


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
        with patch.object(CUTOVER_MOD, "_check_historical_tag", lambda: []):
            result = CUTOVER_MOD._gather()
    assert result["passed"] is True
    assert result["tag_state"] == "absent_pre_tag"
    assert result["tag_commit"] is None
    assert result["tag_matches_head"] is False


def test_post_tag_matches_head_passes() -> None:
    def _patched_tag_state() -> tuple[list[str], str, str | None, str | None, bool]:
        return [], "present_matches_head", "abc123", "abc123", True

    with patch.object(CUTOVER_MOD, "_check_tag_state", _patched_tag_state):
        with patch.object(CUTOVER_MOD, "_check_historical_tag", lambda: []):
            result = CUTOVER_MOD._gather()
    assert result["passed"] is True
    assert result["tag_state"] == "present_matches_head"
    assert result["tag_commit"] == "abc123"
    assert result["head_commit"] == "abc123"
    assert result["tag_matches_head"] is True


def test_post_hotfix_main_tag_mismatch_is_historical() -> None:
    def _patched_version() -> str:
        return CUTOVER_MOD.POST_HOTFIX_DEV_VERSION

    def _run(args: list[str], **_: object) -> subprocess.CompletedProcess:
        if args[:2] == ["git", "rev-parse"] and args[2] == "HEAD":
            return subprocess.CompletedProcess(args, 0, "main123\n", "")
        if args[:3] == ["git", "tag", "--list"]:
            return subprocess.CompletedProcess(args, 0, "v0.5.8.1\n", "")
        if args[:2] == ["git", "rev-parse"] and args[2] == "v0.5.8.1^{}":
            return subprocess.CompletedProcess(args, 0, "tag123\n", "")
        return subprocess.CompletedProcess(args, 1, "", "")

    with patch.object(CUTOVER_MOD, "_current_pyproject_version", _patched_version):
        with patch.object(CUTOVER_MOD.subprocess, "run", _run):
            errors, state, tag_commit, head_commit, matches_head = CUTOVER_MOD._check_tag_state()

    assert errors == []
    assert state == "present_historical_release"
    assert tag_commit == "tag123"
    assert head_commit == "main123"
    assert matches_head is False


def test_tag_mismatch_fails() -> None:
    def _patched_tag_state() -> tuple[list[str], str, str | None, str | None, bool]:
        return (
            ["v0.5.8.1 tag exists locally but points to deadbeef, while HEAD is abc123. Force-pushing or moving release tags is not allowed."],
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
            ["v0.5.8.1 tag exists locally but cannot be resolved."],
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
    files_to_watch = [
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "src" / "atlas_agent" / "__init__.py",
        REPO_ROOT / "CHANGELOG.md",
    ]
    before = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files_to_watch}

    CUTOVER_MOD._gather()

    after = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files_to_watch}
    assert before == after, "Checker mutated a watched file"
