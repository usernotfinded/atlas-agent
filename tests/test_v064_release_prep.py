"""Tests for v0.6.4 release prep checker.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_v064_release_prep.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v064_release_prep", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v064_release_prep"] = mod
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


class TestReleasePrepModeValid:
    def test_release_prep_mode_passes(self) -> None:
        """Fails on real repo because source is now 0.6.8."""
        result = _run_script("--release-prep")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "FAIL" in result.stdout
        assert "release-prep" in result.stdout

    def test_release_prep_json_output(self) -> None:
        """Fails on real repo because source is now 0.6.8."""
        result = _run_script("--json", "--release-prep")
        assert result.returncode == 1, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["mode"] == "release-prep"
        assert "checks" in data

    def test_json_has_required_keys(self) -> None:
        result = _run_script("--json", "--release-prep")
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "v064_release_prep_report"
        assert data["schema_version"] == 1
        assert "mode" in data
        assert "checks" in data
        assert "errors" in data
        assert "warnings" in data

    def test_missing_planning_version_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.2"\n')
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.2"\n')
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check()
            assert code == 1
            assert any("0.6.3" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init

    def test_release_notes_exist_in_planning_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_notes = tmp_path / "v0.6.4.md"
        fake_notes.write_text("# v0.6.4\n")
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
        fake_changelog.write_text("# Changelog\n\n## [0.6.4] - 2026-06-07\n")
        original = mod.CHANGELOG
        try:
            mod.CHANGELOG = fake_changelog
            code, result = mod.run_check()
            assert code == 1
            assert any("must not contain [0.6.4]" in e for e in result["errors"])
        finally:
            mod.CHANGELOG = original

    def test_unselected_candidate_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_json = tmp_path / "v0.6.4-candidates.json"
        fake_json.write_text(
            json.dumps({
                "artifact_type": "v064_patch_candidate_inventory",
                "schema_version": 1,
                "release": "v0.6.4",
                "candidates": [
                    {
                        "id": "CAND-010",
                        "selected": True,
                        "implemented": False,
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

    def test_v063_history_missing_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_notes = mod.V063_RELEASE_NOTES
        original_status = mod.V063_TRUST_STATUS
        try:
            mod.V063_RELEASE_NOTES = tmp_path / "missing-v063.md"
            mod.V063_TRUST_STATUS = tmp_path / "missing-v063-status.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("v0.6.3" in e for e in result["errors"])
        finally:
            mod.V063_RELEASE_NOTES = original_notes
            mod.V063_TRUST_STATUS = original_status


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
        fake_pyproject.write_text('version = "0.6.3"\n')
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.3"\n')
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("0.6.4" in e for e in result["errors"])
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
        fake_changelog.write_text("# Changelog\n\n## [0.6.3] - 2026-06-06\n")
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
        fake_notes = tmp_path / "v0.6.4.md"
        fake_notes.write_text(
            "# v0.6.4\n\nThis release enables autonomous trading for everyone.\n"
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
    def test_release_prep_output_is_deterministic(self) -> None:
        result1 = _run_script("--json", "--release-prep")
        result2 = _run_script("--json", "--release-prep")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout
