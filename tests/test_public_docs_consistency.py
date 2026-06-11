"""Tests for public docs consistency script — Batch 10.0.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_public_docs_consistency.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_public_docs_consistency", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_public_docs_consistency"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_script_on_text(text: str) -> subprocess.CompletedProcess[str]:
    """Run the consistency script with a temporary doc under REPO_ROOT.

    The temporary doc is placed inside a temp directory under REPO_ROOT
    so that Path.relative_to(REPO_ROOT) works in the script.
    """
    tmp_dir = Path(tempfile.mkdtemp(dir=REPO_ROOT))
    tmp_path = tmp_dir / "test_doc.md"
    tmp_path.write_text(text, encoding="utf-8")

    original_script = SCRIPT.read_text(encoding="utf-8")
    # Replace the entire PUBLIC_DOC_PATHS list so only the temp doc is scanned
    old_paths_block = (
        'PUBLIC_DOC_PATHS = [\n'
        '    REPO_ROOT / "README.md",\n'
        '    REPO_ROOT / "SECURITY.md",\n'
        '    REPO_ROOT / "CONTRIBUTING.md",\n'
        '    REPO_ROOT / "docs" / "provider-safety-dossier.md",\n'
        '    REPO_ROOT / "docs" / "examples" / "provider-safety-dossier-workflow.md",\n'
        '    REPO_ROOT / "docs" / "release-checklist.md",\n'
        '    REPO_ROOT / "docs" / "release-candidate-readiness.md",\n'
        '    REPO_ROOT / "docs" / "release-candidate-cutover.md",\n'
        '    REPO_ROOT / "docs" / "package-distribution-verification.md",\n'
        '    REPO_ROOT / "docs" / "public-repo-hygiene.md",\n'
        '    REPO_ROOT / "docs" / "public-launch-readiness.md",\n'
        '    REPO_ROOT / "docs" / "github-repo-settings.md",\n'
        '    REPO_ROOT / "docs" / "external-reviewer-walkthrough.md",\n'
        '    REPO_ROOT / "docs" / "reviewer-checklist.md",\n'
        '    REPO_ROOT / "docs" / "public-launch-messaging.md",\n'
        '    REPO_ROOT / "docs" / "feedback-request-guide.md",\n'
        '    REPO_ROOT / "docs" / "public-faq.md",\n'
        '    REPO_ROOT / "docs" / "final-rc-audit.md",\n'
        '    REPO_ROOT / "docs" / "final-release-candidate-checklist.md",\n'
        '    REPO_ROOT / "docs" / "stable-release-decision.md",\n'
        '    REPO_ROOT / "docs" / "stable-release-checklist.md",\n'
        '    REPO_ROOT / "docs" / "trust" / "README.md",\n'
        ']'
    )
    new_paths_block = f'PUBLIC_DOC_PATHS = [Path("{tmp_path}")]'
    patched_script = original_script.replace(old_paths_block, new_paths_block)

    tmp_script = tmp_dir / "check.py"
    tmp_script.write_text(patched_script, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(tmp_script)],
        capture_output=True,
        text=True,
    )
    # Clean up temp files
    try:
        tmp_path.unlink()
        tmp_script.unlink()
        tmp_dir.rmdir()
    except OSError:
        pass
    return result


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestScriptPassesOnCurrentDocs:
    def test_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Public docs consistency script failed:\n{result.stdout}\n{result.stderr}"
        )


class TestScriptRejectsUnsafePositiveClaims:
    def test_rejects_live_trading_ready(self) -> None:
        text = "# Doc\n\n```bash\natlas --help\n```\n\nLive trading ready.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected failure on live trading ready claim"
        assert "live trading ready" in result.stdout.lower()

    def test_rejects_provider_execution_enabled(self) -> None:
        text = "# Doc\n\nProvider execution enabled.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "provider execution enabled" in result.stdout.lower()

    def test_rejects_guaranteed_profit(self) -> None:
        text = "# Doc\n\nThis strategy produces guaranteed profit.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "guaranteed profit" in result.stdout.lower()


class TestScriptAcceptsNegativeSafetyWording:
    def test_accepts_not_live_trading_ready(self) -> None:
        text = "# Doc\n\nLive trading is not ready.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for negative wording:\n{result.stdout}\n{result.stderr}"
        )

    def test_accepts_live_trading_disabled(self) -> None:
        text = "# Doc\n\nLive trading remains disabled by default.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for disabled wording:\n{result.stdout}\n{result.stderr}"
        )

    def test_accepts_provider_execution_locked(self) -> None:
        text = "# Doc\n\nProvider execution remains locked.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for locked wording:\n{result.stdout}\n{result.stderr}"
        )


class TestScriptRejectsAbsolutePaths:
    def test_rejects_users_path(self) -> None:
        text = "# Doc\n\n```bash\ncd /Users/natan/dev\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "/Users/" in result.stdout

    def test_rejects_private_var_path(self) -> None:
        text = "# Doc\n\n```bash\ncd /private/var/tmp\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "/private/var/" in result.stdout


class TestScriptRejectsForbiddenFragments:
    def test_rejects_sk_token(self) -> None:
        text = "# Doc\n\n```bash\nexport KEY=sk-abc123def456\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "sk-" in result.stdout.lower()

    def test_rejects_bearer_token(self) -> None:
        text = "# Doc\n\n```bash\ncurl -H 'Authorization: Bearer xyz123'\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "bearer" in result.stdout.lower()


class TestScriptRejectsUnsafeCommands:
    def test_rejects_curl(self) -> None:
        text = "# Doc\n\n```bash\ncurl https://api.example.com\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "curl" in result.stdout.lower()

    def test_rejects_order_create(self) -> None:
        text = "# Doc\n\n```bash\natlas order create --symbol AAPL\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "order create" in result.stdout.lower()


class TestScriptRequiresNotFinancialAdvice:
    def test_requires_not_financial_advice(self) -> None:
        text = "# Doc\n\nSome safe text.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "not financial advice" in result.stdout.lower()


class TestReadmeCurrentVersion:
    def test_readme_missing_current_status_fails(self) -> None:
        mod = _load_script_module()
        text = "# README\n\nSome text.\nNot financial advice.\n"
        violations = mod._check_readme_current_version(text, "README.md", "v1.2.3")
        assert len(violations) == 1
        assert "v1.2.3" in violations[0]

    def test_readme_has_current_status_passes(self) -> None:
        mod = _load_script_module()
        text = "# README\n\n> **Current Status (v0.6.8)**\n\nNot financial advice.\n"
        violations = mod._check_readme_current_version(text, "README.md", "v0.6.8")
        assert violations == []

    def test_skipped_for_non_readme(self) -> None:
        mod = _load_script_module()
        text = "# Doc\n\nNo status here.\nNot financial advice.\n"
        violations = mod._check_readme_current_version(text, "OTHER.md", "v0.6.8")
        assert violations == []


class TestStaleCurrentStatusInReadme:
    def test_stale_current_status_fails(self) -> None:
        mod = _load_script_module()
        text = "# README\n\n> **Current Status (v0.6.4)**\n\nNot financial advice.\n"
        violations = mod._check_stale_current_status_in_readme(text, "README.md", "v1.2.3")
        assert len(violations) == 1
        assert "v0.6.4" in violations[0]
        assert "v1.2.3" in violations[0]

    def test_current_status_passes(self) -> None:
        mod = _load_script_module()
        text = "# README\n\n> **Current Status (v0.6.8)**\n\nNot financial advice.\n"
        violations = mod._check_stale_current_status_in_readme(text, "README.md", "v0.6.8")
        assert violations == []

    def test_skipped_for_non_readme(self) -> None:
        mod = _load_script_module()
        text = "# Doc\n\n> **Current Status (v0.6.4)**\n\nNot financial advice.\n"
        violations = mod._check_stale_current_status_in_readme(text, "OTHER.md", "v1.2.3")
        assert violations == []


class TestChangelogReferencesReleaseNotes:
    def test_orphaned_release_note_warns(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_releases = tmp_path / "releases"
        fake_releases.mkdir()
        (fake_releases / "v0.5.8.1.md").write_text("# v0.5.8.1\n")
        (fake_releases / "v0.6.5.md").write_text("# v0.6.5\n")
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\n## [0.6.5]\n\nSee v0.6.5.md\n")

        original_releases_dir = mod.RELEASES_DIR
        original_changelog = mod.CHANGELOG_PATH
        try:
            mod.RELEASES_DIR = fake_releases
            mod.CHANGELOG_PATH = fake_changelog
            warnings = mod._check_changelog_references_release_notes()
            assert any("v0.5.8.1.md" in w for w in warnings)
            assert not any("v0.6.5.md" in w for w in warnings)
        finally:
            mod.RELEASES_DIR = original_releases_dir
            mod.CHANGELOG_PATH = original_changelog

    def test_all_referenced_no_warnings(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_releases = tmp_path / "releases"
        fake_releases.mkdir()
        (fake_releases / "v0.6.5.md").write_text("# v0.6.5\n")
        fake_changelog = tmp_path / "CHANGELOG.md"
        fake_changelog.write_text("# Changelog\n\nSee v0.6.5.md\n")

        original_releases_dir = mod.RELEASES_DIR
        original_changelog = mod.CHANGELOG_PATH
        try:
            mod.RELEASES_DIR = fake_releases
            mod.CHANGELOG_PATH = fake_changelog
            warnings = mod._check_changelog_references_release_notes()
            assert warnings == []
        finally:
            mod.RELEASES_DIR = original_releases_dir
            mod.CHANGELOG_PATH = original_changelog

    def test_missing_changelog_warns(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        fake_releases = tmp_path / "releases"
        fake_releases.mkdir()
        (fake_releases / "v0.6.5.md").write_text("# v0.6.5\n")
        fake_changelog = tmp_path / "CHANGELOG.md"

        original_releases_dir = mod.RELEASES_DIR
        original_changelog = mod.CHANGELOG_PATH
        try:
            mod.RELEASES_DIR = fake_releases
            mod.CHANGELOG_PATH = fake_changelog
            warnings = mod._check_changelog_references_release_notes()
            assert any("not found" in w for w in warnings)
        finally:
            mod.RELEASES_DIR = original_releases_dir
            mod.CHANGELOG_PATH = original_changelog

class TestDynamicMetadata:
    def test_reads_dynamic_metadata(self, tmp_path: Path) -> None:
        """Test that changing fixture metadata changes expected checker targets."""
        mod = _load_script_module()
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()
        meta_dir = fake_repo / "docs" / "releases"
        meta_dir.mkdir(parents=True)

        meta_path = meta_dir / "release-metadata.json"
        meta_path.write_text('{"source_version": "0.9.9", "current_public_release": "v0.9.8"}', encoding="utf-8")

        current_version = mod._get_current_version(fake_repo)
        assert current_version == "v0.9.9"

        text = "# README\n\n> **Current Status (v0.9.9)**\n\nNot financial advice.\n"
        violations = mod._check_readme_current_version(text, "README.md", current_version)
        assert violations == []

        text_bad = "# README\n\n> **Current Status (v0.6.8)**\n\nNot financial advice.\n"
        violations_bad = mod._check_readme_current_version(text_bad, "README.md", current_version)
        assert len(violations_bad) == 1
        assert "v0.9.9" in violations_bad[0]

        violations_stale = mod._check_stale_current_status_in_readme(text_bad, "README.md", current_version)
        assert len(violations_stale) == 1
        assert "expected v0.9.9" in violations_stale[0]

    def test_missing_metadata_fallback(self, tmp_path: Path) -> None:
        """invalid/missing metadata fails clearly."""
        mod = _load_script_module()
        fake_repo = tmp_path / "repo"
        fake_repo.mkdir()

        import pytest
        with pytest.raises(FileNotFoundError, match="Release metadata not found"):
            mod._get_current_version(fake_repo)

        meta_dir = fake_repo / "docs" / "releases"
        meta_dir.mkdir(parents=True)
        meta_path = meta_dir / "release-metadata.json"
        meta_path.write_text('{"bad_schema": "0.9.9"}', encoding="utf-8")

        with pytest.raises(Exception, match="source_version is empty in metadata"):
            mod._get_current_version(fake_repo)
