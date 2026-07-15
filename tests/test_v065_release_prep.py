# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_v065_release_prep.py
# PURPOSE: Verifies v065 release prep behavior and regression expectations.
# DEPS:    importlib, json, subprocess, sys, pathlib, types, additional local
#         modules.
# ==============================================================================

"""Tests for v0.6.5 release prep checker.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

# --- IMPORTS ---

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "historical_release_checkers" / "check_v065_release_prep.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v065_release_prep", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v065_release_prep"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestPlanningModeValid:
    def test_planning_mode_fails_after_bump(self) -> None:
        """Planning mode fails on real repo because source is now 0.6.5."""
        result = _run_script()
        assert result.returncode == 1, result.stdout + result.stderr
        assert "FAIL" in result.stdout
        assert "planning" in result.stdout

    def test_planning_json_output_after_bump(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 1, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["mode"] == "planning"
        assert any("0.6.4" in e for e in data["errors"])
        assert "checks" in data

    def test_json_has_required_keys(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "v065_release_prep_report"
        assert data["schema_version"] == 1
        assert "mode" in data
        assert "checks" in data
        assert "errors" in data
        assert "warnings" in data

    def test_missing_planning_version_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.5"\n')
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.5"\n')
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check()
            assert code == 1
            assert any("0.6.4" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init

    def test_release_notes_exist_in_planning_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_notes = tmp_path / "v0.6.5.md"
        fake_notes.write_text("# v0.6.5\n")
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = fake_notes
            code, result = mod.run_check()
            assert code == 1
            assert any("must not exist" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original

    def test_changelog_has_release_entry_in_planning_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\n## [0.6.5] - 2026-06-07\n")
        original = mod.CHANGELOG
        try:
            mod.CHANGELOG = fake_changelog
            code, result = mod.run_check()
            assert code == 1
            assert any("must not contain [0.6.5]" in e for e in result["errors"])
        finally:
            mod.CHANGELOG = original

    def test_unselected_candidate_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_json = tmp_path / "v0.6.5-candidates.json"
        fake_json.write_text(
            json.dumps({
                "artifact_type": "v065_patch_candidate_inventory",
                "schema_version": 1,
                "release": "v0.6.5",
                "candidates": [
                    {
                        "id": "CAND-010",
                        "selected_for_v065": True,
                        "implementation_status": "not implemented",
                    }
                ],
                "rejected": [],
            })
        )
        original = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = fake_json
            code, result = mod.run_check()
            assert code == 1
            assert any("not yet implemented" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original

    def test_v064_history_missing_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_notes = mod.V064_RELEASE_NOTES
        original_status = mod.V064_TRUST_STATUS
        try:
            mod.V064_RELEASE_NOTES = tmp_path / "missing-v064.md"
            mod.V064_TRUST_STATUS = tmp_path / "missing-v064-status.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("v0.6.4" in e for e in result["errors"])
        finally:
            mod.V064_RELEASE_NOTES = original_notes
            mod.V064_TRUST_STATUS = original_status


class TestReleasePrepMode:
    def test_release_prep_mode_passes_after_bump(self) -> None:
        """Fails on real repo because source is now 0.6.8."""
        result = _run_script("--release-prep")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "FAIL" in result.stdout

    def test_release_prep_json_passes_after_bump(self) -> None:
        """Fails on real repo because source is now 0.6.8."""
        result = _run_script("--release-prep", "--json")
        assert result.returncode == 1, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["mode"] == "release-prep"

    def test_release_prep_version_missing_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.4"\n')
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.4"\n')
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("0.6.5" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init

    def test_release_prep_missing_release_notes_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = tmp_path / "nonexistent.md"
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("Release notes missing" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original

    def test_release_prep_missing_trust_status_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.TRUST_STATUS
        try:
            mod.TRUST_STATUS = tmp_path / "nonexistent.md"
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("Trust status missing" in e for e in result["errors"])
        finally:
            mod.TRUST_STATUS = original

    def test_release_prep_missing_changelog_entry_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\n## [0.6.4] - 2026-06-06\n")
        original = mod.CHANGELOG
        try:
            mod.CHANGELOG = fake_changelog
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("CHANGELOG missing entry" in e for e in result["errors"])
        finally:
            mod.CHANGELOG = original

    def test_release_prep_unsafe_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_notes = tmp_path / "v0.6.5.md"
        fake_notes.write_text(
            "# v0.6.5\n\nThis release enables autonomous trading for everyone.\n"
        )
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = fake_notes
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("Unsafe claim" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original


class TestDeterminism:
    def test_planning_output_is_deterministic(self) -> None:
        result1 = _run_script("--json")
        result2 = _run_script("--json")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout

    def test_release_prep_output_is_deterministic(self) -> None:
        result1 = _run_script("--json", "--release-prep")
        result2 = _run_script("--json", "--release-prep")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout

    def test_json_keys_are_sorted(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert list(data.keys()) == sorted(data.keys())
