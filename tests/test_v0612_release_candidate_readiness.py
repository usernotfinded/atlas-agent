# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_v0612_release_candidate_readiness.py
# PURPOSE: Verifies v0612 release candidate readiness behavior and regression
#         expectations.
# DEPS:    importlib, json, subprocess, sys, pathlib, types, additional local
#         modules.
# ==============================================================================

"""Tests for v0.6.12 release candidate readiness checker.

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
SCRIPT = ROOT / "scripts" / "check_v0612_release_candidate_readiness.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v0612_release_candidate_readiness", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0612_release_candidate_readiness"] = mod
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


@pytest.mark.skip(reason="Historical v0.6.12 real-repo posture superseded by v0.6.13")
class TestScriptPassesOnCurrentRepo:
    def test_script_passes(self) -> None:
        result = _run_script()
        assert result.returncode == 0, (
            f"v0.6.12 release candidate readiness check failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "PASS" in result.stdout

    def test_script_json_passes(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["expected_current_public_release"] == "v0.6.12"
        assert data["expected_source_version"] == "0.6.12"
        assert data["next_planned_release"] == "v0.6.13"


class TestReadinessDoc:
    def test_missing_readiness_doc_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.READINESS_MD
        try:
            mod.READINESS_MD = tmp_path / "missing.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing readiness doc" in e for e in result["errors"])
        finally:
            mod.READINESS_MD = original

    def test_missing_candidate_coverage_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_readiness = tmp_path / "v0.6.12-candidate-readiness.md"
        fake_readiness.write_text("# v0.6.12\n\nNo candidate references.\n")
        fake_candidates = tmp_path / "v0.6.12-candidates.md"
        fake_candidates.write_text("# Candidates\n\nNo candidate references.\n")
        original_readiness = mod.READINESS_MD
        original_candidates = mod.CANDIDATES_MD
        try:
            mod.READINESS_MD = fake_readiness
            mod.CANDIDATES_MD = fake_candidates
            code, result = mod.run_check()
            assert code == 1
            assert any("CAND-001" in e for e in result["errors"])
        finally:
            mod.READINESS_MD = original_readiness
            mod.CANDIDATES_MD = original_candidates


class TestReleaseMetadata:
    def test_wrong_current_public_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_metadata = tmp_path / "release-metadata.json"
        fake_metadata.write_text(
            json.dumps({
                "schema_version": 1,
                "source_version": "0.6.12",
                "current_public_release": "v0.6.11",
                "next_planned_release": "v0.6.13",
                "pypi_published": False,
                "releases": [
                    {
                        "tag": "v0.6.12",
                        "version": "0.6.12",
                        "status": "current_public",
                        "github_release": True,
                        "pypi_published": False,
                    }
                ],
            })
        )
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = fake_metadata
            code, result = mod.run_check()
            assert code == 1
            assert any("current_public_release mismatch" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original

    def test_v0612_not_current_public_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_metadata = tmp_path / "release-metadata.json"
        fake_metadata.write_text(
            json.dumps({
                "schema_version": 1,
                "source_version": "0.6.12",
                "current_public_release": "v0.6.12",
                "next_planned_release": "v0.6.13",
                "pypi_published": False,
                "releases": [
                    {
                        "tag": "v0.6.12",
                        "version": "0.6.12",
                        "status": "prepared",
                        "github_release": False,
                        "pypi_published": False,
                    }
                ],
            })
        )
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = fake_metadata
            code, result = mod.run_check()
            assert code == 1
            assert any("status must be 'current_public'" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original


class TestPrematureClaims:
    def test_pypi_publish_claim_in_readme_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_readme = tmp_path / "README.md"
        fake_readme.write_text(
            "# README\n\nv0.6.12 was published to PyPI.\n"
        )
        original = mod.README
        try:
            mod.README = fake_readme
            code, result = mod.run_check()
            assert code == 1
            assert any("published to pypi" in e.lower() for e in result["errors"])
        finally:
            mod.README = original


class TestSourceVersion:
    def test_stale_source_version_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.11"\n')
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.11"\n')
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check()
            assert code == 1
            assert any("0.6.12" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init


class TestReleasePrepArtifacts:
    def test_missing_release_notes_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = tmp_path / "nonexistent.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("Release notes missing" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original

    def test_missing_changelog_entry_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\n## [0.6.11] - 2026-06-15\n")
        original = mod.CHANGELOG
        try:
            mod.CHANGELOG = fake_changelog
            code, result = mod.run_check()
            assert code == 1
            assert any("CHANGELOG missing entry" in e for e in result["errors"])
        finally:
            mod.CHANGELOG = original


class TestDeterminism:
    def test_output_is_deterministic(self) -> None:
        result1 = _run_script("--json")
        result2 = _run_script("--json")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout

    def test_json_keys_are_sorted(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert list(data.keys()) == sorted(data.keys())
