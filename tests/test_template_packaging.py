"""Verify template packaging parity and safety.

No network calls, no credentials, no broker/provider contact, no live trading.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT_TEMPLATE = REPO_ROOT / "templates" / "routine-trader"
PKG_TEMPLATE = REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader"

SECRET_MARKERS = ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY")
SAFE_EXCLUSIONS = {
    # These files are allowed to mention secret-related terms in instructional context
    REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example",
    REPO_ROOT / "templates" / "routine-trader" / ".env.example",
    REPO_ROOT / "src" / "atlas_agent" / "templates" / "routine-trader" / "routines" / "schedules" / "github-actions.yml",
    REPO_ROOT / "templates" / "routine-trader" / "routines" / "schedules" / "github-actions.yml",
}


def _relative_files(directory: Path) -> set[str]:
    if not directory.exists():
        return set()
    return {
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file()
    }


class TestTemplateParity:
    def test_root_and_package_templates_have_same_files(self) -> None:
        root_files = _relative_files(ROOT_TEMPLATE)
        pkg_files = _relative_files(PKG_TEMPLATE)
        missing_in_pkg = root_files - pkg_files
        missing_in_root = pkg_files - root_files
        assert not missing_in_pkg, (
            f"Package template missing files present in root: {sorted(missing_in_pkg)}"
        )
        assert not missing_in_root, (
            f"Root template missing files present in package: {sorted(missing_in_root)}"
        )

    def test_package_template_contains_memory_portfolio_md(self) -> None:
        assert PKG_TEMPLATE.joinpath("memory", "portfolio.md").is_file()

    def test_package_template_contains_all_memory_files(self) -> None:
        root_memory = _relative_files(ROOT_TEMPLATE / "memory")
        pkg_memory = _relative_files(PKG_TEMPLATE / "memory")
        assert root_memory == pkg_memory, (
            f"Memory directory mismatch:\n"
            f"  root only: {sorted(root_memory - pkg_memory)}\n"
            f"  pkg only: {sorted(pkg_memory - root_memory)}"
        )


class TestPackagedResources:
    def test_portfolio_md_is_packaged_resource(self) -> None:
        template = resources.files("atlas_agent").joinpath("templates", "routine-trader")
        assert template.is_dir()
        assert template.joinpath("memory", "portfolio.md").is_file()

    def test_all_memory_files_are_packaged_resources(self) -> None:
        root_memory = _relative_files(ROOT_TEMPLATE / "memory")
        template = resources.files("atlas_agent").joinpath("templates", "routine-trader")
        for rel in sorted(root_memory):
            pkg_rel = "memory" / Path(rel)
            assert template.joinpath(str(pkg_rel)).is_file(), (
                f"Packaged template missing memory file: {pkg_rel}"
            )


class TestNoSecretsInTemplates:
    def test_no_secret_values_in_template_starter_files(self) -> None:
        for directory in (ROOT_TEMPLATE, PKG_TEMPLATE):
            for path in directory.rglob("*"):
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
        for directory in (ROOT_TEMPLATE, PKG_TEMPLATE):
            assert not directory.joinpath(".env").exists(), (
                f"Template must not include real .env file: {directory / '.env'}"
            )

    def test_gitignore_ignores_env_in_templates(self) -> None:
        for directory in (ROOT_TEMPLATE, PKG_TEMPLATE):
            gitignore = directory / ".gitignore"
            assert gitignore.is_file()
            content = gitignore.read_text(encoding="utf-8")
            assert ".env" in content, (
                f"Template .gitignore must ignore .env: {gitignore}"
            )
