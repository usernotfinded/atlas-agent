"""RC1 cutover consistency tests.

No execution code, no network calls, no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_rc1_cutover.py"
VERSION_SCRIPT = REPO_ROOT / "scripts" / "check_version_consistency.py"

PACKAGE_VERSION = "0.5.7"
PUBLIC_TAG = "v0.5.7"


class TestRc1ScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestRc1ScriptPassesOnCurrentRepo:
    def test_rc1_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"RC1 cutover script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_version_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VERSION_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Version consistency script failed:\n{result.stdout}\n{result.stderr}"
        )


class TestRc1PackageVersion:
    def test_pyproject_version(self) -> None:
        import tomllib
        pyproject = REPO_ROOT / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        assert data.get("project", {}).get("version") == PACKAGE_VERSION

    def test_init_version(self) -> None:
        import re
        init_path = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
        text = init_path.read_text(encoding="utf-8")
        m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        assert m is not None
        assert m.group(1) == PACKAGE_VERSION


class TestRc1ReleaseNote:
    def test_rc1_release_note_exists(self) -> None:
        note_path = REPO_ROOT / "docs" / "releases" / f"{PUBLIC_TAG}.md"
        assert note_path.exists()

    def test_rc1_release_note_has_safety_posture(self) -> None:
        note_path = REPO_ROOT / "docs" / "releases" / f"{PUBLIC_TAG}.md"
        text = note_path.read_text(encoding="utf-8").lower()
        assert "provider execution remains locked" in text
        assert "trust remains blocked" in text
        assert "live trading disabled by default" in text


class TestRc1Changelog:
    def test_rc1_entry_in_changelog(self) -> None:
        changelog = REPO_ROOT / "CHANGELOG.md"
        text = changelog.read_text(encoding="utf-8")
        assert f"[{PACKAGE_VERSION}]" in text


class TestRc1Readme:
    def test_readme_current_status_rc1(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert PUBLIC_TAG in text

    def test_readme_no_stale_dev50_status(self) -> None:
        import re
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        stale_patterns = [
            r"Current Status \(v0\.5\.7\.dev5[0-9]\)",
            r"Current Status \(0\.5\.7\.dev5[0-9]\)",
        ]
        for pattern in stale_patterns:
            assert not re.search(pattern, text), f"Stale dev status found matching {pattern}"


class TestRc1ReleaseChecklist:
    def test_checklist_refers_to_rc1(self) -> None:
        checklist = REPO_ROOT / "docs" / "release-checklist.md"
        text = checklist.read_text(encoding="utf-8")
        assert PUBLIC_TAG in text


class TestRc1SafetyClaims:
    def test_no_live_trading_ready_claim(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8").lower()
        assert "live trading ready" not in text

    def test_no_profitability_claim(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8").lower()
        assert "guaranteed profit" not in text


class TestRc1ForbiddenFragments:
    def test_no_users_path_in_readme(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert "/Users/" not in text

    def test_no_private_var_in_readme(self) -> None:
        readme = REPO_ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert "/private/var/" not in text
