"""Regression tests for post-v0.5.8.1 development transition.

Verifies the correct lifecycle model:
- current main = 0.5.9.4
- public stable = v0.5.8.1
- historical stable = v0.5.8
- no stale 0.5.7 assertions on current main
- forbidden phrases removed
- historical docs can still mention 0.5.7 and 0.5.8
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Current version assertions
# ---------------------------------------------------------------------------


def test_pyproject_version_is_current_dev() -> None:
    import tomllib
    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    assert data.get("project", {}).get("version") == "0.5.9.4"


def test_init_version_is_current_dev() -> None:
    init = ROOT / "src" / "atlas_agent" / "__init__.py"
    text = init.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    assert m is not None
    assert m.group(1) == "0.5.9.4"


def test_public_stable_v058_tag_exists() -> None:
    result = subprocess.run(
        ["git", "show", "v0.5.8:src/atlas_agent/__init__.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"v0.5.8 tag not found or missing expected file: {result.stderr}"
    assert "0.5.8" in result.stdout


def test_public_stable_v058_release_note_exists() -> None:
    assert (ROOT / "docs" / "releases" / "v0.5.8.md").exists()


def test_public_stable_v0581_release_note_exists() -> None:
    assert (ROOT / "docs" / "releases" / "v0.5.8.1.md").exists()


# ---------------------------------------------------------------------------
# Historical stable tag verification
# ---------------------------------------------------------------------------


def test_historical_v057_tag_exists() -> None:
    result = subprocess.run(
        ["git", "show", "v0.5.7:src/atlas_agent/__init__.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"v0.5.7 tag not found or missing expected file: {result.stderr}"
    assert "0.5.7" in result.stdout


def test_historical_v057_release_note_exists() -> None:
    assert (ROOT / "docs" / "releases" / "v0.5.7.md").exists()


def test_historical_v057_rc9_release_note_exists() -> None:
    assert (ROOT / "docs" / "releases" / "v0.5.7-rc9.md").exists()


# ---------------------------------------------------------------------------
# Stale test prevention: no hardcoded current-version == 0.5.7 assertions
# ---------------------------------------------------------------------------


def test_no_stale_current_version_057_assertions() -> None:
    """Ensure no test file asserts that the current package/init version equals 0.5.7.

    Historical checks against git-show or fixture files are allowed.
    """
    stale_patterns = [
        r'assert\s+.*==\s*"0\.5\.7"',
        r'assert\s+.*==\s*\'0\.5\.7\'',
    ]
    test_files = list((ROOT / "tests").rglob("test_*.py"))
    failures: list[str] = []
    for path in test_files:
        text = path.read_text(encoding="utf-8")
        for pattern in stale_patterns:
            for m in re.finditer(pattern, text):
                # Allow assertions inside comments or strings that are clearly historical
                line = text[:m.start()].splitlines()[-1] if text[:m.start()] else ""
                if "historical" in line.lower() or "stable" in line.lower() or "rc" in line.lower():
                    continue
                # Allow the rc1_cutover tests which explicitly test historical v0.5.7
                if "rc1_cutover" in path.name:
                    continue
                failures.append(f"{path.name}:{text[:m.start()].count(chr(10))+1} {m.group(0)!r}")
    assert not failures, f"Stale 0.5.7 current-version assertions found:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Forbidden phrase regression
# ---------------------------------------------------------------------------


def test_autonomous_trading_bot_not_in_current_docs() -> None:
    """The forbidden phrase must not appear in any current docs."""
    for path in (ROOT / "docs").rglob("*.md"):
        text = path.read_text(encoding="utf-8").lower()
        assert "autonomous trading bot" not in text, (
            f"Forbidden phrase 'autonomous trading bot' found in {path.relative_to(ROOT)}"
        )


def test_unsupervised_real_money_trading_system_used_instead() -> None:
    """The replacement phrase should be present in controlled outreach."""
    outreach = ROOT / "docs" / "controlled-reviewer-outreach.md"
    text = outreach.read_text(encoding="utf-8").lower()
    assert "unsupervised real-money trading system" in text


# ---------------------------------------------------------------------------
# Safety claim checks still block unsafe phrases
# ---------------------------------------------------------------------------


def test_forbidden_claims_scan_still_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_forbidden_claims.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Forbidden claims scan failed:\n{result.stdout}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Version consistency script accepts dev
# ---------------------------------------------------------------------------


def test_version_consistency_script_accepts_dev() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_version_consistency.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Version consistency check failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "0.5.9" in result.stdout
    assert "v0.5.9" in result.stdout


# ---------------------------------------------------------------------------
# Historical docs can still mention 0.5.7 / RC history
# ---------------------------------------------------------------------------


def test_changelog_can_mention_057_and_rc_history() -> None:
    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    assert "0.5.7" in text or "v0.5.7" in text


def test_release_checklist_can_mention_historical_stable() -> None:
    checklist = ROOT / "docs" / "release-checklist.md"
    text = checklist.read_text(encoding="utf-8")
    # Must mention current version
    assert "0.5.8.1" in text
    # Can also mention historical stable
    assert "v0.5.8" in text or "0.5.7" in text
