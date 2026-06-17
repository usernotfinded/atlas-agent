"""Tests for v0.6.12 release prep checker.

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

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_v0612_release_prep.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v0612_release_prep", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0612_release_prep"] = mod
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
        """Planning mode fails on real repo because source is now 0.6.12."""
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

    def test_json_has_required_keys(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "v0612_release_prep_report"
        assert data["schema_version"] == 1
        assert "mode" in data
        assert "checks" in data
        assert "errors" in data
        assert "warnings" in data

    def test_missing_planning_version_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_pyproject.write_text('version = "0.6.12"\n')
        fake_init = tmp_path / "__init__.py"
        fake_init.write_text('__version__ = "0.6.12"\n')
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check()
            assert code == 1
            assert any("0.6.11" in e for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init

    def test_release_notes_exist_in_planning_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_notes = tmp_path / "v0.6.12.md"
        fake_notes.write_text("# v0.6.12\n")
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
        fake_changelog.write_text("# Changelog\n\n## [0.6.12] - 2026-06-17\n")
        original = mod.CHANGELOG
        try:
            mod.CHANGELOG = fake_changelog
            code, result = mod.run_check()
            assert code == 1
            assert any("must not contain [0.6.12]" in e for e in result["errors"])
        finally:
            mod.CHANGELOG = original

    def test_unselected_candidate_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_json = tmp_path / "v0.6.12-candidates.json"
        fake_json.write_text(
            json.dumps({
                "artifact_type": "v0612_candidate_inventory",
                "schema_version": 1,
                "release": "v0.6.12",
                "candidates": [
                    {
                        "id": "CAND-018",
                        "selected_for_v0612": True,
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

    def test_v0611_history_missing_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_notes = mod.V0611_RELEASE_NOTES
        original_status = mod.V0611_TRUST_STATUS
        try:
            mod.V0611_RELEASE_NOTES = tmp_path / "missing-v0611.md"
            mod.V0611_TRUST_STATUS = tmp_path / "missing-v0611-status.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("v0.6.11" in e for e in result["errors"])
        finally:
            mod.V0611_RELEASE_NOTES = original_notes
            mod.V0611_TRUST_STATUS = original_status


class TestReleasePrepMode:
    def test_release_prep_mode_passes_on_real_repo(self) -> None:
        """Release-prep mode passes on real repo after the version bump."""
        result = _run_script("--release-prep")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS" in result.stdout
        assert "release-prep" in result.stdout

    def test_release_prep_json_passes_on_real_repo(self) -> None:
        result = _run_script("--release-prep", "--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["mode"] == "release-prep"

    def test_release_prep_version_missing_fails(self, tmp_path: Path) -> None:
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
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("0.6.12" in e for e in result["errors"])
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
        fake_changelog.write_text("# Changelog\n\n## [0.6.11] - 2026-06-15\n")
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
        fake_notes = tmp_path / "v0.6.12.md"
        fake_notes.write_text(
            "# v0.6.12\n\nThis release enables autonomous trading for everyone.\n"
        )
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = fake_notes
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("Unsafe claim" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original

    def test_release_prep_premature_tag_claim_fails(self, tmp_path: Path) -> None:
        """A doc that mentions v0.6.12 and claims the tag was created must fail."""
        mod = _load_script_module()
        fake_notes = tmp_path / "v0.6.12.md"
        fake_notes.write_text(
            "# v0.6.12\n\nThe v0.6.12 tag created and the GitHub release created.\n"
        )
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = fake_notes
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("tag was already created" in e for e in result["errors"])
            assert any("GitHub release was already created" in e for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original

    def test_release_prep_premature_public_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_notes = tmp_path / "v0.6.12.md"
        fake_notes.write_text(
            "# v0.6.12\n\nv0.6.12 is the current public release.\n"
        )
        original = mod.RELEASE_NOTES
        try:
            mod.RELEASE_NOTES = fake_notes
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("current public" in e.lower() for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original

    def test_release_prep_readme_stale_version_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_readme = mod.README
        try:
            fake_readme = tmp_path / "README.md"
            fake_readme.write_text(
                "# README\n\n> **Current Status (v0.6.11)** — package/source version is `0.6.11`;\n"
            )
            mod.README = fake_readme
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("package/source version is 0.6.12" in e for e in result["errors"])
        finally:
            mod.README = original_readme

    def test_release_prep_security_stale_version_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_security = mod.SECURITY
        try:
            fake_security = tmp_path / "SECURITY.md"
            fake_security.write_text(
                "# Security\n\n| 0.6.11 (main) | Yes — active development |\n"
            )
            mod.SECURITY = fake_security
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("0.6.12 (main)" in e for e in result["errors"])
        finally:
            mod.SECURITY = original_security

    def test_release_prep_trust_readme_stale_version_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_trust_readme = mod.TRUST_README
        try:
            fake_trust = tmp_path / "README.md"
            fake_trust.write_text(
                "# Trust\n\n- Source package version on `main`: `0.6.11`\n"
            )
            mod.TRUST_README = fake_trust
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("source package version on main is 0.6.12" in e for e in result["errors"])
        finally:
            mod.TRUST_README = original_trust_readme

    def test_release_prep_metadata_prepared_state_fails_if_public(self, tmp_path: Path) -> None:
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
                    },
                    {
                        "tag": "v0.6.11",
                        "version": "0.6.11",
                        "status": "historical",
                        "github_release": True,
                        "pypi_published": False,
                    },
                ],
            })
        )
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = fake_metadata
            code, result = mod.run_check(release_prep=True)
            assert code == 1
            assert any("v0.6.12 status must be 'prepared'" in e for e in result["errors"])
            assert any("v0.6.11 status must be 'current_public'" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original


class TestPostReleaseMode:
    def test_post_release_mode_fails_on_real_repo(self) -> None:
        """Post-release mode fails on real repo because v0.6.12 is not public yet."""
        result = _run_script("--post-release")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "FAIL" in result.stdout
        assert "post-release" in result.stdout

    def test_post_release_json_fails_on_real_repo(self) -> None:
        result = _run_script("--post-release", "--json")
        assert result.returncode == 1, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["mode"] == "post-release"

    def test_post_release_missing_public_tag_record_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_metadata = tmp_path / "release-metadata.json"
        fake_metadata.write_text(
            json.dumps({
                "schema_version": 1,
                "source_version": "0.6.12",
                "current_public_release": "v0.6.12",
                "next_planned_release": "v0.6.13",
                "pypi_published": False,
                "releases": [],
            })
        )
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = fake_metadata
            code, result = mod.run_check(post_release=True)
            assert code == 1
            assert any("Release metadata missing v0.6.12 record" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original

    def test_post_release_v0612_not_current_public_fails(self, tmp_path: Path) -> None:
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
                        "github_release": True,
                        "pypi_published": False,
                    }
                ],
            })
        )
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = fake_metadata
            code, result = mod.run_check(post_release=True)
            assert code == 1
            assert any("v0.6.12 status must be 'current_public'" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original

    def test_post_release_rejects_pypi_published(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_metadata = tmp_path / "release-metadata.json"
        fake_metadata.write_text(
            json.dumps({
                "schema_version": 1,
                "source_version": "0.6.12",
                "current_public_release": "v0.6.12",
                "next_planned_release": "v0.6.13",
                "pypi_published": True,
                "releases": [
                    {
                        "tag": "v0.6.12",
                        "version": "0.6.12",
                        "status": "current_public",
                        "github_release": True,
                        "pypi_published": True,
                    }
                ],
            }),
            encoding="utf-8",
        )
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = fake_metadata
            code, result = mod.run_check(post_release=True)
            assert code == 1
            assert any(
                "pypi_published must be false in post-release mode" in error
                for error in result["errors"]
            )
            assert any(
                "v0.6.12 pypi_published must be false" in error
                for error in result["errors"]
            )
        finally:
            mod.RELEASE_METADATA = original


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

    def test_post_release_output_is_deterministic(self) -> None:
        result1 = _run_script("--json", "--post-release")
        result2 = _run_script("--json", "--post-release")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout

    def test_json_keys_are_sorted(self) -> None:
        result = _run_script("--json", "--release-prep")
        data = json.loads(result.stdout)
        assert list(data.keys()) == sorted(data.keys())
