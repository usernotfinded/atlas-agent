"""Tests for public launch readiness script and docs — Batch 10.9.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_public_launch_readiness.py"

_FORBIDDEN_POSITIVE_CLAIMS = (
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "real-money ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
)

_FORBIDDEN_FRAGMENTS = (
    "/Users/",
    "/private/var/",
    "/var/folders/",
    "/tmp/",
    "/var/tmp/",
)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result


class TestScriptAndDocsExist:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

    def test_public_launch_readiness_doc_exists(self) -> None:
        assert (ROOT / "docs" / "public-launch-readiness.md").exists()

    def test_github_repo_settings_doc_exists(self) -> None:
        assert (ROOT / "docs" / "github-repo-settings.md").exists()

    def test_release_note_exists(self) -> None:
        assert (ROOT / "docs" / "releases" / "v0.5.7.md").exists()


class TestReadmePublicLaunch:
    @pytest.fixture
    def readme_text(self) -> str:
        return (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_has_what_this_is(self, readme_text: str) -> None:
        assert "What this is" in readme_text

    def test_readme_has_what_this_is_not(self, readme_text: str) -> None:
        assert "What this is not" in readme_text

    def test_readme_links_to_security(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert "security.md" in lower

    def test_readme_links_to_contributing(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert "contributing.md" in lower

    def test_readme_links_to_changelog_or_release_notes(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert "changelog" in lower or "release notes" in lower

    def test_readme_contains_current_status(self, readme_text: str) -> None:
        assert "v0.5.7" in readme_text

    def test_readme_does_not_claim_live_trading_readiness(self, readme_text: str) -> None:
        lower = readme_text.lower()
        for claim in _FORBIDDEN_POSITIVE_CLAIMS:
            assert claim not in lower, f"README contains forbidden claim: {claim}"

    def test_readme_does_not_claim_profitability(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert "guaranteed profit" not in lower
        assert "profitable strategy" not in lower
        assert "verified alpha" not in lower
        assert "beats the market" not in lower


class TestPublicLaunchDocsSafety:
    def _doc_paths(self) -> list[Path]:
        return [
            ROOT / "docs" / "public-launch-readiness.md",
            ROOT / "docs" / "github-repo-settings.md",
        ]

    def test_no_forbidden_claims(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            for claim in _FORBIDDEN_POSITIVE_CLAIMS:
                if claim not in text:
                    continue
                idx = text.index(claim)
                context_start = max(0, idx - 120)
                context_end = min(len(text), idx + 120)
                context = text[context_start:context_end]
                negative_indicators = (
                    "not ", "does not", "never", "no ", "avoid",
                    "disclaimer", "prohibited", "forbidden", "must not",
                    "cannot", "do not", "is not", "are not", "without",
                    "fail closed", "not yet", "not implemented", "not enabled",
                    "not authorized", "not a ", "not ready", "remains disabled",
                    "remains locked", "remains blocked", "do not assume",
                )
                if not any(ind in context for ind in negative_indicators):
                    pytest.fail(f"{path.name} contains forbidden claim: {claim}")

    def test_no_forbidden_fragments(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8")
            for frag in _FORBIDDEN_FRAGMENTS:
                assert frag not in text, f"{path.name} contains forbidden fragment: {frag}"

    def test_no_absolute_paths(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8")
            for frag in _FORBIDDEN_FRAGMENTS:
                assert frag not in text, f"{path.name} contains absolute path: {frag}"


class TestRepoSettingsDoc:
    def test_does_not_include_unsafe_topics(self) -> None:
        text = (ROOT / "docs" / "github-repo-settings.md").read_text(encoding="utf-8").lower()
        assert "live-trading" not in text or "not include" in text
        assert "profit" not in text or "not include" in text
        assert "alpha" not in text or "not include" in text


class TestScriptBehavior:
    def test_script_passes(self) -> None:
        result = _run_script()
        assert result.returncode == 0, (
            f"Launch readiness script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_script_json_output(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, (
            f"Launch readiness script --json failed:\n{result.stdout}\n{result.stderr}"
        )
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["package_version"] == "0.5.8rc1"
        assert data["public_tag"] == "v0.5.7"
        assert data["errors"] == []

    def test_json_output_has_no_absolute_paths(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in result.stdout, f"JSON output contains absolute path: {frag}"


class TestStaleRCReferencesBlocked:
    def test_readme_with_current_status_rc9_fails(self) -> None:
        from tests.test_public_docs_consistency import _run_script_on_text
        text = (
            "# README\n\n```bash\natlas --help\n```\n\n"
            "## Current Status (v0.5.7-rc9)\n\n"
            "Sandbox-only, paper-first, offline-safe.\n"
            "Live trading disabled by default. Not financial advice.\n"
        )
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected failure on stale RC current-status reference"
        assert "v0.5.7-rc9" in result.stdout or "stale" in result.stdout.lower()

    def test_public_launch_readiness_saying_release_candidate_fails(self) -> None:
        from tests.test_public_docs_consistency import _run_script_on_text
        text = (
            "# Public Launch Readiness\n\n"
            "Atlas Agent is a sandbox/paper/preflight release candidate.\n\n"
            "Not financial advice.\n"
        )
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected failure on stale RC status claim"
        assert "release candidate" in result.stdout.lower()

    def test_historical_changelog_rc9_reference_allowed(self) -> None:
        from tests.test_public_docs_consistency import _run_script_on_text
        text = (
            "# Changelog\n\n## [0.5.7rc9] - 2026-05-26\n\n"
            "Ninth release candidate for the v0.5.7 line.\n\n"
            "Not financial advice.\n"
        )
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for historical RC changelog entry:\n{result.stdout}"
        )

    def test_current_dev_version_058dev0_accepted(self) -> None:
        from tests.test_public_docs_consistency import _run_script_on_text
        text = (
            "# README\n\n```bash\natlas --help\n```\n\n"
            "Sandbox-only, paper-first, offline-safe.\n"
            "Live trading disabled by default. Not financial advice.\n"
            "Current development version is 0.5.8.dev0.\n"
        )
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for current dev version:\n{result.stdout}"
        )


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

    def test_no_secrets_required(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "api_key" not in text
        assert "secret" not in text or "secret-like" in text
