"""Tests for v0.6.1 patch candidate selection checker.

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
SCRIPT = ROOT / "scripts" / "historical_release_checkers" / "check_v061_candidates.py"
CANDIDATES_MD = ROOT / "docs" / "releases" / "v0.6.1-candidates.md"
CANDIDATES_JSON = ROOT / "docs" / "releases" / "v0.6.1-candidates.json"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v061_candidates", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v061_candidates"] = mod
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

    def test_candidates_md_exists(self) -> None:
        assert CANDIDATES_MD.exists(), f"Candidate doc not found: {CANDIDATES_MD}"

    def test_candidates_json_exists(self) -> None:
        assert CANDIDATES_JSON.exists(), f"Candidate JSON not found: {CANDIDATES_JSON}"


class TestCheckerValid:
    def test_valid_candidate_doc_passes_release_prep(self) -> None:
        """Fails on real repo because source is not 0.6.1."""
        result = _run_script("--release-prep")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "FAIL" in result.stdout

    def test_valid_json_output_release_prep(self) -> None:
        """Fails on real repo because source is not 0.6.1."""
        result = _run_script("--json", "--release-prep")
        assert result.returncode == 1, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is False

    def test_json_has_required_keys(self) -> None:
        result = _run_script("--json", "--release-prep")
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "v061_candidate_check_report"
        assert data["schema_version"] == 1

    def test_release_prep_mode_allows_version_bump(self) -> None:
        """Fails on real repo because source is not 0.6.1."""
        mod = _load_script_module()
        code, result = mod.run_check(release_prep=True)
        assert code == 1
        assert any("Version bump" in e for e in result["errors"])

    def test_release_prep_mode_allows_release_notes(self) -> None:
        """Fails on real repo because source is not 0.6.1."""
        mod = _load_script_module()
        code, result = mod.run_check(release_prep=True)
        assert code == 1
        assert not any("Release notes file must not exist" in e for e in result["errors"])


class TestCheckerNegative:
    def test_missing_candidate_doc_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = tmp_path / "nonexistent.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing candidate selection doc" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_missing_selection_criteria_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_doc = tmp_path / "v0.6.1-candidates.md"
        fake_doc.write_text("# Candidates\n\n## Accepted candidates\n\n## Rejected / deferred candidates\n\n## Safety boundaries\n\n## Non-goals\n")
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = fake_doc
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing section" in e and "Selection criteria" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_missing_safety_boundaries_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_doc = tmp_path / "v0.6.1-candidates.md"
        fake_doc.write_text("# Candidates\n\n## Selection criteria\n\n## Candidate table\n\n## Accepted candidates\n\n## Rejected / deferred candidates\n\n## Non-goals\n")
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = fake_doc
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing section" in e and "Safety boundaries" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_missing_non_goals_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_doc = tmp_path / "v0.6.1-candidates.md"
        fake_doc.write_text("# Candidates\n\n## Selection criteria\n\n## Candidate table\n\n## Accepted candidates\n\n## Rejected / deferred candidates\n\n## Safety boundaries\n")
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = fake_doc
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing section" in e and "Non-goals" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_version_bump_detected(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.1"\n')
        original = mod.PYPROJECT
        try:
            mod.PYPROJECT = fake_pyproject
            code, result = mod.run_check()
            assert code == 1
            assert any("Version bump to 0.6.1" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original

    def test_version_bump_allowed_in_release_prep(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.1"\n')
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.1"\n')
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check(release_prep=True)
            assert code == 0
            assert not any("Version bump" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init

    def test_release_notes_existing_rejected(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_release_notes = tmp_path / "v0.6.1.md"
        fake_release_notes.write_text("# v0.6.1\n")
        original = mod.RELEASE_NOTES_MD
        try:
            mod.RELEASE_NOTES_MD = fake_release_notes
            code, result = mod.run_check()
            assert code == 1
            assert any("Release notes file must not exist yet" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES_MD = original

    def test_unsafe_scope_selected_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_doc = tmp_path / "v0.6.1-candidates.md"
        fake_doc.write_text(
            "# Candidates\n\n## Selection criteria\n\n## Candidate table\n\n"
            "## Accepted candidates\n\nselected: **yes** | provider execution unlock\n\n"
            "## Rejected / deferred candidates\n\n## Safety boundaries\n\n## Non-goals\n"
        )
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = fake_doc
            code, result = mod.run_check()
            assert code == 1
            assert any("Unsafe scope phrase detected in accepted candidates" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_missing_json_inventory_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_json = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = tmp_path / "nonexistent.json"
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing JSON candidate inventory" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original_json

    def test_invalid_json_inventory_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        bad_json = tmp_path / "v0.6.1-candidates.json"
        bad_json.write_text("not json")
        original_json = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = bad_json
            code, result = mod.run_check()
            assert code == 1
            assert any("Invalid JSON" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original_json
