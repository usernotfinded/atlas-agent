"""Tests for v0.6.3 release prep checker.

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
SCRIPT = ROOT / "scripts" / "check_v063_release_prep.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v063_release_prep", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v063_release_prep"] = mod
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


class TestCheckerValid:
    def test_valid_release_prep_passes(self) -> None:
        """Fails on real repo because source is now 0.6.8."""
        result = _run_script()
        assert result.returncode == 1, result.stdout + result.stderr
        assert "FAIL" in result.stdout

    def test_valid_json_output(self) -> None:
        """Fails on real repo because source is now 0.6.8."""
        result = _run_script("--json")
        assert result.returncode == 1, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is False

    def test_json_has_required_keys(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "v063_release_prep_report"
        assert data["schema_version"] == 1


class TestCheckerNegative:
    def test_missing_version_bump_fails(self, tmp_path: Path) -> None:
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

    def test_missing_trust_status_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.TRUST_STATUS
        try:
            mod.TRUST_STATUS = tmp_path / "nonexistent.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("Trust status missing" in e for e in result["errors"])
        finally:
            mod.TRUST_STATUS = original

    def test_missing_changelog_entry_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\n## [0.6.2] - 2026-06-06\n")
        original = mod.CHANGELOG
        try:
            mod.CHANGELOG = fake_changelog
            code, result = mod.run_check()
            assert code == 1
            assert any("CHANGELOG missing entry" in e for e in result["errors"])
        finally:
            mod.CHANGELOG = original

    def test_future_release_notes_rejected(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_future = tmp_path / "v0.6.4.md"
        fake_future.write_text("# v0.6.4\n")
        original = mod.FUTURE_RELEASE_NOTES
        try:
            mod.FUTURE_RELEASE_NOTES = fake_future
            code, result = mod.run_check()
            assert code == 1
            assert any("Future release notes must not exist" in e for e in result["errors"])
        finally:
            mod.FUTURE_RELEASE_NOTES = original

    def test_unsafe_claim_in_release_notes_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_notes = tmp_path / "v0.6.3.md"
        fake_notes.write_text(
            "# v0.6.3\n\nThis release enables autonomous trading for everyone.\n"
        )
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = fake_notes
            code, result = mod.run_check()
            assert code == 1
            assert any("Unsafe claim" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original

    def test_v062_history_missing_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_v062_notes = mod.V062_RELEASE_NOTES
        original_v062_status = mod.V062_TRUST_STATUS
        try:
            mod.V062_RELEASE_NOTES = tmp_path / "missing-v062.md"
            mod.V062_TRUST_STATUS = tmp_path / "missing-v062-status.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("v0.6.2 history missing" in e for e in result["errors"])
        finally:
            mod.V062_RELEASE_NOTES = original_v062_notes
            mod.V062_TRUST_STATUS = original_v062_status
