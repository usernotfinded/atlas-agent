"""Historical v0.5.7 release record check tests.

No execution code, no network calls, no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_rc1_cutover.py"
VERSION_SCRIPT = REPO_ROOT / "scripts" / "check_version_consistency.py"

HISTORICAL_STABLE_VERSION = "0.5.7"
HISTORICAL_STABLE_TAG = "v0.5.7"
CURRENT_DEV_SERIES = "0.6.15"


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestScriptPassesOnCurrentRepo:
    def test_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Historical release record script failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "PASSED" in result.stdout

    def test_version_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VERSION_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Version consistency script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_json_output(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["current_package_version"] == CURRENT_DEV_SERIES
        assert data["current_init_version"] == CURRENT_DEV_SERIES
        assert data["stable_tag"] == HISTORICAL_STABLE_TAG
        assert data["stable_tag_version"] == HISTORICAL_STABLE_VERSION


class TestCurrentDevVersion:
    def test_pyproject_version_is_post_stable_dev(self) -> None:
        import tomllib
        pyproject = REPO_ROOT / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        version = data.get("project", {}).get("version")
        assert version == CURRENT_DEV_SERIES

    def test_init_version_is_post_stable_dev(self) -> None:
        init_path = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
        text = init_path.read_text(encoding="utf-8")
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        assert m is not None
        assert m.group(1) == CURRENT_DEV_SERIES


class TestHistoricalStableTag:
    def test_historical_tag_pyproject_version(self) -> None:
        result = subprocess.run(
            ["git", "show", f"{HISTORICAL_STABLE_TAG}:pyproject.toml"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Could not read pyproject.toml from {HISTORICAL_STABLE_TAG}"
        data = tomllib.loads(result.stdout)
        assert data.get("project", {}).get("version") == HISTORICAL_STABLE_VERSION

    def test_historical_tag_init_version(self) -> None:
        result = subprocess.run(
            ["git", "show", f"{HISTORICAL_STABLE_TAG}:src/atlas_agent/__init__.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Could not read __init__.py from {HISTORICAL_STABLE_TAG}"
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', result.stdout, re.MULTILINE)
        assert m is not None
        assert m.group(1) == HISTORICAL_STABLE_VERSION


class TestHistoricalReleaseNote:
    def test_stable_release_note_exists(self) -> None:
        note_path = REPO_ROOT / "docs" / "releases" / f"{HISTORICAL_STABLE_TAG}.md"
        assert note_path.exists()

    def test_stable_release_note_has_safety_posture(self) -> None:
        note_path = REPO_ROOT / "docs" / "releases" / f"{HISTORICAL_STABLE_TAG}.md"
        text = note_path.read_text(encoding="utf-8").lower()
        assert "provider execution remains locked" in text
        assert "trust remains blocked" in text
        assert "live trading disabled by default" in text


class TestChangelog:
    def test_unreleased_section_exists(self) -> None:
        changelog = REPO_ROOT / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        assert "[Unreleased]" in text

    def test_stable_entry_in_changelog(self) -> None:
        changelog = REPO_ROOT / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        assert f"[{HISTORICAL_STABLE_VERSION}]" in text


class TestReadme:
    def test_readme_references_stable_tag(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert "v0.5.8" in text

    def test_readme_no_stale_rc_status(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        stale_patterns = [
            r"Current Status \(v0\.5\.7\.dev5[0-9]\)",
            r"Current Status \(0\.5\.7\.dev5[0-9]\)",
            r"Current Status \(v0\.5\.7-rc\d+\)",
            r"Current Status \(0\.5\.7rc\d+\)",
        ]
        for pattern in stale_patterns:
            assert not re.search(pattern, text), f"Stale RC/dev status found matching {pattern}"


class TestReleaseChecklist:
    def test_checklist_refers_to_stable(self) -> None:
        checklist = REPO_ROOT / "docs" / "release-checklist.md"
        text = checklist.read_text(encoding="utf-8")
        assert HISTORICAL_STABLE_TAG in text


class TestSafetyClaims:
    def test_no_live_trading_ready_claim(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8").lower()
        assert "live trading ready" not in text

    def test_no_profitability_claim(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8").lower()
        assert "guaranteed profit" not in text


class TestForbiddenFragments:
    def test_no_users_path_in_readme(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert "/Users/" not in text

    def test_no_private_var_in_readme(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert "/private/var/" not in text


class TestScriptSourceSafety:
    def test_no_shell_true(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        assert "shell=True" not in source

    def test_no_unsafe_network_imports(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        suspicious = ["urllib.request", "urllib.parse", "http.client", "socket"]
        for name in suspicious:
            assert name not in source, f"Suspicious import '{name}' found"
