"""Tests for v0.6.4 patch candidate selection checker.

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
SCRIPT = ROOT / "scripts" / "check_v064_candidates.py"
CANDIDATES_MD = ROOT / "docs" / "releases" / "v0.6.4-candidates.md"
CANDIDATES_JSON = ROOT / "docs" / "releases" / "v0.6.4-candidates.json"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v064_candidates", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v064_candidates"] = mod
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
    def test_valid_candidate_doc_passes(self) -> None:
        result = _run_script()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS" in result.stdout

    def test_valid_json_output(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["errors"] == []

    def test_json_has_required_keys(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "v064_candidate_check_report"
        assert data["schema_version"] == 1

    def test_no_version_bump_detected_in_planning_mode(self) -> None:
        mod = _load_script_module()
        code, result = mod.run_check()
        assert code == 0
        assert not any("Version bump" in e for e in result["errors"])

    def test_release_notes_not_existing_in_planning_mode(self) -> None:
        mod = _load_script_module()
        code, result = mod.run_check()
        assert code == 0
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
        fake_doc = tmp_path / "v0.6.4-candidates.md"
        fake_doc.write_text(
            "# Candidates\n\n## Status\n\n## Candidate Table\n\n"
            "## Accepted Candidates\n\n## Deferred Candidates\n\n"
            "## Rejected / Out-of-Scope Candidates\n\n"
            "## Safety Boundaries\n\n## Test and Release Criteria\n\n"
            "## Non-Goals\n\n## Next Steps\n"
        )
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = fake_doc
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing section" in e and "Selection Criteria" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_missing_safety_boundaries_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_doc = tmp_path / "v0.6.4-candidates.md"
        fake_doc.write_text(
            "# Candidates\n\n## Status\n\n## Selection Criteria\n\n"
            "## Candidate Table\n\n## Accepted Candidates\n\n"
            "## Deferred Candidates\n\n## Rejected / Out-of-Scope Candidates\n\n"
            "## Test and Release Criteria\n\n## Non-Goals\n\n## Next Steps\n"
        )
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = fake_doc
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing section" in e and "Safety Boundaries" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_missing_non_goals_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_doc = tmp_path / "v0.6.4-candidates.md"
        fake_doc.write_text(
            "# Candidates\n\n## Status\n\n## Selection Criteria\n\n"
            "## Candidate Table\n\n## Accepted Candidates\n\n"
            "## Deferred Candidates\n\n## Rejected / Out-of-Scope Candidates\n\n"
            "## Safety Boundaries\n\n## Test and Release Criteria\n\n## Next Steps\n"
        )
        original = mod.CANDIDATES_MD
        try:
            mod.CANDIDATES_MD = fake_doc
            code, result = mod.run_check()
            assert code == 1
            assert any("Missing section" in e and "Non-Goals" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_MD = original

    def test_version_bump_detected(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.4"\n')
        original = mod.PYPROJECT
        try:
            mod.PYPROJECT = fake_pyproject
            code, result = mod.run_check()
            assert code == 1
            assert any("Version bump to 0.6.4" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original

    def test_release_prep_mode_allows_version_bump(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.4"\n')
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.4"\n')
        fake_release_notes = tmp_path / "v0.6.4.md"
        fake_release_notes.write_text("# v0.6.4\n")
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        original_release_notes = mod.RELEASE_NOTES_MD
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            mod.RELEASE_NOTES_MD = fake_release_notes
            code, result = mod.run_check(release_prep=True)
            assert code == 0
            assert not any("Version bump" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init
            mod.RELEASE_NOTES_MD = original_release_notes

    def test_release_notes_existing_rejected(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_release_notes = tmp_path / "v0.6.4.md"
        fake_release_notes.write_text("# v0.6.4\n")
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
        fake_doc = tmp_path / "v0.6.4-candidates.md"
        fake_doc.write_text(
            "# Candidates\n\n## Status\n\n## Selection Criteria\n\n## Candidate Table\n\n"
            "## Accepted Candidates\n\nselected: **yes** | provider execution unlock\n\n"
            "## Deferred Candidates\n\n## Rejected / Out-of-Scope Candidates\n\n"
            "## Safety Boundaries\n\n## Test and Release Criteria\n\n"
            "## Non-Goals\n\n## Next Steps\n"
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
        bad_json = tmp_path / "v0.6.4-candidates.json"
        bad_json.write_text("not json")
        original_json = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = bad_json
            code, result = mod.run_check()
            assert code == 1
            assert any("Invalid JSON" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original_json

    def test_json_release_mismatch_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        bad_json = tmp_path / "v0.6.4-candidates.json"
        bad_json.write_text(
            json.dumps({
                "artifact_type": "v064_patch_candidate_inventory",
                "schema_version": 1,
                "release": "v0.6.5",
                "candidates": [],
                "rejected": [],
            })
        )
        original_json = mod.CANDIDATES_JSON
        try:
            mod.CANDIDATES_JSON = bad_json
            code, result = mod.run_check()
            assert code == 1
            assert any("release mismatch" in e for e in result["errors"])
        finally:
            mod.CANDIDATES_JSON = original_json
