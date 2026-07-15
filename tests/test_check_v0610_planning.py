# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_check_v0610_planning.py
# PURPOSE: Verifies check v0610 planning behavior and regression expectations.
# DEPS:    importlib, json, subprocess, sys, pathlib, types, additional local
#         modules.
# ==============================================================================

"""Tests for v0.6.10 planning baseline checker.

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
SCRIPT = ROOT / "scripts" / "check_v0610_planning.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v0610_planning", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0610_planning"] = mod
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
        """Planning mode fails because source is now 0.6.10 and release-prep artifacts exist."""
        result = _run_script()
        assert result.returncode == 1, result.stdout + result.stderr
        assert "FAIL" in result.stdout
        assert "planning" in result.stdout

    def test_planning_json_output_fails_after_bump(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 1, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["mode"] == "planning"
        assert "checks" in data

    def test_json_has_required_keys(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "v0610_planning_check_report"
        assert data["schema_version"] == 1
        assert "mode" in data
        assert "checks" in data
        assert "errors" in data
        assert "warnings" in data

    def test_missing_candidate_md_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = tmp_path / "missing.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing candidate selection doc" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_missing_candidate_json_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = tmp_path / "missing.json"
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing JSON candidate inventory" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original

    def test_invalid_json_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_json = tmp_path / "v0.6.10-candidates.json"
        fake_json.write_text("{not valid json", encoding="utf-8")
        original = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = fake_json
            code, result = mod.run_check()
            assert code == 1
            assert any("Invalid JSON" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original

    def test_candidate_missing_required_key_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_json = tmp_path / "v0.6.10-candidates.json"
        fake_json.write_text(
            json.dumps({
                "artifact_type": "v0610_candidate_inventory",
                "schema_version": 1,
                "release": "v0.6.10",
                "candidates": [{"id": "CAND-001", "title": "Title only"}],
                "rejected": [],
            }),
            encoding="utf-8",
        )
        original = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = fake_json
            code, result = mod.run_check()
            assert code == 1
            assert any("missing required key" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original

    def test_markdown_missing_candidate_id_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_md = tmp_path / "v0.6.10-candidates.md"
        fake_md.write_text("# v0.6.10 Candidates\n\nNo candidate table here.\n", encoding="utf-8")
        original_md = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = fake_md
            code, result = mod.run_check()
            assert code == 1
            assert any("not mentioned" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original_md

    def test_unsafe_selected_candidate_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_json = tmp_path / "v0.6.10-candidates.json"
        fake_json.write_text(
            json.dumps({
                "artifact_type": "v0610_candidate_inventory",
                "schema_version": 1,
                "release": "v0.6.10",
                "candidates": [
                    {
                        "id": "CAND-001",
                        "title": "Unsafe",
                        "summary": "This candidate enables live trading by default",
                        "user_value": "none",
                        "safety_boundary": "none",
                        "risk": "high",
                        "likely_files": [],
                        "tests_checks": [],
                        "recommendation": "now",
                        "ranking_reason": "test",
                        "selected_for_v0610": True,
                        "implemented": False,
                    }
                ],
                "rejected": [],
            }),
            encoding="utf-8",
        )
        original = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = fake_json
            code, result = mod.run_check()
            assert code == 1
            assert any("Unsafe scope phrase" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original

    def test_immediate_pypi_candidate_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_json = tmp_path / "v0.6.10-candidates.json"
        fake_json.write_text(
            json.dumps({
                "artifact_type": "v0610_candidate_inventory",
                "schema_version": 1,
                "release": "v0.6.10",
                "candidates": [
                    {
                        "id": "CAND-001",
                        "title": "PyPI",
                        "summary": "Publish this release to PyPI immediately",
                        "user_value": "none",
                        "safety_boundary": "none",
                        "risk": "low",
                        "likely_files": [],
                        "tests_checks": [],
                        "recommendation": "now",
                        "ranking_reason": "test",
                        "selected_for_v0610": True,
                        "implemented": False,
                    }
                ],
                "rejected": [],
            }),
            encoding="utf-8",
        )
        original = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = fake_json
            code, result = mod.run_check()
            assert code == 1
            assert any("Immediate cutover" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original

    def test_version_bump_detected_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.10"\n', encoding="utf-8")
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.9"\n', encoding="utf-8")
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check()
            assert code == 1
            assert any("Version bump to 0.6.10" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init

    def test_release_notes_exist_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_notes = tmp_path / "v0.6.10.md"
        fake_notes.write_text("# v0.6.10\n", encoding="utf-8")
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = fake_notes
            code, result = mod.run_check()
            assert code == 1
            assert any("must not exist" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original

    def test_trust_status_exists_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_status = tmp_path / "v0.6.10-status.md"
        fake_status.write_text("# Trust\n", encoding="utf-8")
        original = mod.TRUST_STATUS
        try:
            mod.TRUST_STATUS = fake_status
            code, result = mod.run_check()
            assert code == 1
            assert any("Trust status must not exist" in e for e in result["errors"])
        finally:
            mod.TRUST_STATUS = original

    def test_changelog_has_release_entry_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\n## [0.6.10] - 2026-06-11\n", encoding="utf-8")
        original = mod.CHANGELOG
        try:
            mod.CHANGELOG = fake_changelog
            code, result = mod.run_check()
            assert code == 1
            assert any("must not contain [0.6.10]" in e for e in result["errors"])
        finally:
            mod.CHANGELOG = original


class TestDeterminism:
    def test_planning_output_is_deterministic(self) -> None:
        result1 = _run_script("--json")
        result2 = _run_script("--json")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout

    def test_json_keys_are_sorted(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert list(data.keys()) == sorted(data.keys())
