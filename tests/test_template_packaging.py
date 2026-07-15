# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_template_packaging.py
# PURPOSE: Verifies template packaging behavior and regression expectations.
# DEPS:    importlib, pathlib, pytest.
# ==============================================================================

"""Verify template packaging parity and safety.

No network calls, no credentials, no broker/provider contact, no live trading.
"""

# --- IMPORTS ---

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_TEMPLATE = REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader"

SECRET_MARKERS = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY")
SAFE_EXCLUSIONS = {
    # These files are allowed to mention secret-related terms in instructional context
    REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
    REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader" / "routines" / "schedules" / "github-actions.yml",
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _relative_files(directory: Path) -> set[str]:
    if not directory.exists():
        return set()
    return {
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file()
    }


class TestPackagedResources:
    def test_portfolio_md_is_packaged_resource(self) -> None:
        template = resources.files("atlas_agent").joinpath("templates", "routine-trader")
        assert template.is_dir()
        assert template.joinpath("memory", "portfolio.md").is_file()

    def test_all_memory_files_are_packaged_resources(self) -> None:
        pkg_memory = _relative_files(PKG_TEMPLATE / "memory")
        template = resources.files("atlas_agent").joinpath("templates", "routine-trader")
        for rel in sorted(pkg_memory):
            pkg_rel = "memory" / Path(rel)
            assert template.joinpath(str(pkg_rel)).is_file(), (
                f"Packaged template missing memory file: {pkg_rel}"
            )


class TestNoSecretsInTemplates:
    def test_no_secret_values_in_template_starter_files(self) -> None:
        for path in PKG_TEMPLATE.rglob("*"):
            if not path.is_file():
                continue
            if path in SAFE_EXCLUSIONS:
                continue
            text = path.read_text(encoding="utf-8")
            for marker in SECRET_MARKERS:
                # Only fail if the marker appears in a value-looking context,
                # not just as a word in markdown instructions.
                if f"{marker}=" in text or f"{marker}:" in text:
                    pytest.fail(
                        f"Possible secret value in template file {path}: "
                        f"found '{marker}=' or '{marker}:'"
                    )

    def test_no_real_env_file_in_templates(self) -> None:
        assert not PKG_TEMPLATE.joinpath(".env").exists(), (
            f"Template must not include real .env file: {PKG_TEMPLATE / '.env'}"
        )

    def test_gitignore_ignores_env_in_templates(self) -> None:
        gitignore = PKG_TEMPLATE / ".gitignore"
        assert gitignore.is_file()
        content = gitignore.read_text(encoding="utf-8")
        assert ".env" in content, (
            f"Template .gitignore must ignore .env: {gitignore}"
        )


class TestNoDuplicateRootTemplate:
    def test_no_root_level_template_shadows_packaged_copy(self) -> None:
        root_template = REPO_ROOT / "templates" / "routine-trader"
        assert not root_template.exists(), (
            f"Root-level template duplicate must not exist: {root_template}"
        )
