"""Tests for v0.6.5 patch candidate selection checker."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_v065_candidates.py"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestPlanningMode:
    def test_planning_mode_fails_after_bump(self) -> None:
        """Planning mode fails on real repo because source is now 0.6.5."""
        result = _run_script()
        assert result.returncode == 1, (
            f"v0.6.5 candidate check failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "FAIL" in result.stdout

    def test_json_mode_fails_after_bump(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 1, (
            f"v0.6.5 candidate check --json failed:\n{result.stdout}\n{result.stderr}"
        )
        data = json.loads(result.stdout)
        assert data["valid"] is False
        assert data["artifact_type"] == "v065_candidate_check_report"
        assert any("0.6.5" in e for e in data.get("errors", []))

    def test_fails_if_release_notes_exist(self, tmp_path: Path) -> None:
        # This test verifies the checker logic by creating a temp repo
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "docs" / "releases").mkdir(parents=True)
        (repo / "docs" / "trust").mkdir(parents=True)
        (repo / "src" / "atlas_agent").mkdir(parents=True)

        # Copy candidate docs
        candidates_md = REPO_ROOT / "docs" / "releases" / "v0.6.5-candidates.md"
        candidates_json = REPO_ROOT / "docs" / "releases" / "v0.6.5-candidates.json"
        (repo / "docs" / "releases" / "v0.6.5-candidates.md").write_text(
            candidates_md.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (repo / "docs" / "releases" / "v0.6.5-candidates.json").write_text(
            candidates_json.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (repo / "docs" / "releases" / "v0.6.5.md").write_text("# v0.6.5\n", encoding="utf-8")
        (repo / "pyproject.toml").write_text('version = "0.6.4"\n', encoding="utf-8")
        (repo / "src" / "atlas_agent" / "__init__.py").write_text('__version__ = "0.6.4"\n', encoding="utf-8")

        # Run checker against temp repo by modifying script path resolution
        # Since the script uses Path(__file__).resolve().parent.parent,
        # we run it from the temp repo by copying the script
        script_copy = repo / "scripts" / "check_v065_candidates.py"
        script_copy.parent.mkdir(parents=True, exist_ok=True)
        script_copy.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(script_copy)],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )
        assert result.returncode == 1, (
            f"Expected failure when release notes exist:\n{result.stdout}"
        )
        assert "Release notes file must not exist yet" in result.stdout

    def test_fails_if_version_bumped(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "docs" / "releases").mkdir(parents=True, exist_ok=True)
        (repo / "src" / "atlas_agent").mkdir(parents=True, exist_ok=True)

        candidates_md = REPO_ROOT / "docs" / "releases" / "v0.6.5-candidates.md"
        candidates_json = REPO_ROOT / "docs" / "releases" / "v0.6.5-candidates.json"
        (repo / "docs" / "releases" / "v0.6.5-candidates.md").write_text(
            candidates_md.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (repo / "docs" / "releases" / "v0.6.5-candidates.json").write_text(
            candidates_json.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (repo / "pyproject.toml").write_text('version = "0.6.5"\n', encoding="utf-8")
        (repo / "src" / "atlas_agent" / "__init__.py").write_text('__version__ = "0.6.5"\n', encoding="utf-8")

        script_copy = repo / "scripts" / "check_v065_candidates.py"
        script_copy.parent.mkdir(parents=True, exist_ok=True)
        script_copy.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(script_copy)],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )
        assert result.returncode == 1, (
            f"Expected failure when version bumped:\n{result.stdout}"
        )
        assert "Version bump to 0.6.5 detected" in result.stdout


class TestReleasePrepMode:
    def test_release_prep_mode_requires_release_notes(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "docs" / "releases").mkdir(parents=True, exist_ok=True)
        (repo / "src" / "atlas_agent").mkdir(parents=True, exist_ok=True)

        candidates_md = REPO_ROOT / "docs" / "releases" / "v0.6.5-candidates.md"
        candidates_json = REPO_ROOT / "docs" / "releases" / "v0.6.5-candidates.json"
        (repo / "docs" / "releases" / "v0.6.5-candidates.md").write_text(
            candidates_md.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (repo / "docs" / "releases" / "v0.6.5-candidates.json").write_text(
            candidates_json.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (repo / "pyproject.toml").write_text('version = "0.6.5"\n', encoding="utf-8")
        (repo / "src" / "atlas_agent" / "__init__.py").write_text('__version__ = "0.6.5"\n', encoding="utf-8")

        script_copy = repo / "scripts" / "check_v065_candidates.py"
        script_copy.parent.mkdir(parents=True, exist_ok=True)
        script_copy.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(script_copy), "--release-prep"],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )
        assert result.returncode == 1, (
            f"Expected failure in release-prep without release notes:\n{result.stdout}"
        )
        assert "Release notes file must exist in release-prep mode" in result.stdout


class TestScriptSafety:
    def test_no_github_api_usage(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "github api" not in text or "does not" in text

    def test_no_publish_or_upload(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "twine upload" not in text
        assert "gh release create" not in text

    def test_no_git_push_or_tag(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "git push" not in text
        assert "git tag" not in text
