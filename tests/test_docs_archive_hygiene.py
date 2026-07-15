# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_docs_archive_hygiene.py
# PURPOSE: Verifies docs archive hygiene behavior and regression expectations.
# DEPS:    subprocess, sys, pathlib, pytest, scripts.
# ==============================================================================

"""Tests for the docs archive hygiene checker."""

# --- IMPORTS ---

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_docs_archive_hygiene as checker


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _test_workspace() -> Path:
    path = _repo_root() / ".pytest_cache" / "docs-archive-hygiene-tests"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestDocsArchiveHygieneChecker:
    def test_checker_passes_on_real_repo(self) -> None:
        result = checker.check_archive_hygiene()
        assert result["passed"], f"Expected checker to pass, got errors: {result['errors']}"
        assert result["active_docs_scanned"] > 0
        assert result["archived_docs_scanned"] > 0

    def test_archive_readme_exists(self) -> None:
        readme = _repo_root() / "docs" / "archive" / "README.md"
        assert readme.exists()
        text = readme.read_text(encoding="utf-8")
        assert "Historical Docs Archive" in text
        assert "What was archived" in text
        assert "What remains current" in text

    def test_archive_readme_mentions_all_archived_docs(self) -> None:
        result = checker.check_archive_hygiene()
        readme_inventory_errors = [
            e for e in result["errors"] if "Archive README does not mention" in e
        ]
        assert not readme_inventory_errors, readme_inventory_errors

    def test_candidate_docs_are_accounted_for(self) -> None:
        result = checker.check_archive_hygiene()
        disposition_errors = [
            e for e in result["errors"] if "neither active nor archived" in e
        ]
        assert not disposition_errors, disposition_errors

    def test_active_links_are_not_broken(self) -> None:
        result = checker.check_archive_hygiene()
        broken_link_errors = [e for e in result["errors"] if "Broken link" in e]
        assert not broken_link_errors, broken_link_errors

    def test_archived_docs_not_presented_as_current(self) -> None:
        result = checker.check_archive_hygiene()
        stale_errors = [e for e in result["errors"] if "present-tense label" in e]
        assert not stale_errors, stale_errors

    def test_no_forbidden_claims_introduced(self) -> None:
        result = checker.check_archive_hygiene()
        claim_errors = [e for e in result["errors"] if "Forbidden claim" in e]
        assert not claim_errors, claim_errors

    def test_checker_fails_if_archive_readme_missing(self) -> None:
        workspace = _test_workspace() / "no-readme"
        workspace.mkdir(parents=True, exist_ok=True)
        result = checker.check_archive_hygiene(repo_root=workspace)
        assert not result["passed"]
        assert any("Archive README missing" in e for e in result["errors"])

    def test_checker_fails_if_archived_file_not_in_inventory(self) -> None:
        workspace = _test_workspace() / "orphan"
        workspace.mkdir(parents=True, exist_ok=True)
        archive_dir = workspace / "docs" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        readme = archive_dir / "README.md"
        readme.write_text("# Archive\n\nNo files here.\n", encoding="utf-8")
        extra = archive_dir / "legacy-plans"
        extra.mkdir(parents=True, exist_ok=True)
        (extra / "orphan.md").write_text("orphan", encoding="utf-8")
        result = checker.check_archive_hygiene(repo_root=workspace)
        assert not result["passed"]
        assert any("does not mention archived doc" in e for e in result["errors"])

    def test_checker_fails_on_broken_active_link(self) -> None:
        workspace = _test_workspace() / "broken-link"
        workspace.mkdir(parents=True, exist_ok=True)
        docs_dir = workspace / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        doc = docs_dir / "active.md"
        doc.write_text("[missing](missing-file.md)", encoding="utf-8")
        result = checker.check_archive_hygiene(repo_root=workspace)
        assert not result["passed"]
        assert any("Broken link" in e for e in result["errors"])

    def test_checker_fails_on_archived_doc_presented_as_current(self) -> None:
        workspace = _test_workspace() / "present-as-current"
        workspace.mkdir(parents=True, exist_ok=True)
        docs_dir = workspace / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        archive_dir = docs_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "README.md").write_text("# Archive\n", encoding="utf-8")
        archived = archive_dir / "legacy-plans" / "old-plan.md"
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_text("old", encoding="utf-8")
        doc = docs_dir / "active.md"
        doc.write_text(
            "See [Current Plan](archive/legacy-plans/old-plan.md) for current guidance.",
            encoding="utf-8",
        )
        result = checker.check_archive_hygiene(repo_root=workspace)
        assert not result["passed"]
        assert any("present-tense label" in e for e in result["errors"])

    def test_cli_returns_zero_on_valid_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_repo_root() / "scripts" / "check_docs_archive_hygiene.py")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_cli_json_output(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_repo_root() / "scripts" / "check_docs_archive_hygiene.py"), "--json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert '"passed": true' in result.stdout

    def test_cli_fails_when_archive_readme_missing(self) -> None:
        workspace = _test_workspace() / "cli-no-readme"
        workspace.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                sys.executable,
                str(_repo_root() / "scripts" / "check_docs_archive_hygiene.py"),
                "--repo-root",
                str(workspace),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
