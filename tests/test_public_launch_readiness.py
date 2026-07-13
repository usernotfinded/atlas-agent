"""Tests for public launch readiness script and docs — Batch 10.9.

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

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_public_launch_readiness.py"
PUBLIC_DOCS_TEST = ROOT / "tests" / "test_public_docs_consistency.py"

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


def _load_public_docs_test_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_public_docs_consistency_local", PUBLIC_DOCS_TEST
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["test_public_docs_consistency_local"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_public_docs_script_on_text(text: str) -> subprocess.CompletedProcess:
    mod = _load_public_docs_test_module()
    return mod._run_script_on_text(text)

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
        assert (ROOT / "docs" / "releases" / "v0.5.8.1.md").exists()


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
        assert "v0.6.24" in readme_text, "README must reference v0.6.24 as current source status"

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
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from release_metadata import load_metadata, ReleaseMetadata
        _meta = ReleaseMetadata(load_metadata(ROOT / "docs" / "releases" / "release-metadata.json"))
        sys.path.pop(0)

        result = _run_script("--json")
        assert result.returncode == 0, (
            f"Launch readiness script --json failed:\n{result.stdout}\n{result.stderr}"
        )
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["package_version"] == _meta.source_version
        assert data["public_tag"] == _meta.current_public_release
        assert data["errors"] == []

    def test_json_output_has_no_absolute_paths(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in result.stdout, f"JSON output contains absolute path: {frag}"


class TestStaleRCReferencesBlocked:
    def test_readme_with_current_status_rc9_fails(self) -> None:
        text = (
            "# README\n\n```bash\natlas --help\n```\n\n"
            "## Current Status (v0.5.8-rc9)\n\n"
            "Sandbox-only, paper-first, offline-safe.\n"
            "Live trading disabled by default. Not financial advice.\n"
        )
        result = _run_public_docs_script_on_text(text)
        assert result.returncode != 0, "Expected failure on stale RC current-status reference"
        assert "v0.5.8-rc9" in result.stdout or "stale" in result.stdout.lower()

    def test_public_launch_readiness_saying_release_candidate_fails(self) -> None:
        text = (
            "# Public Launch Readiness\n\n"
            "Atlas Agent is a sandbox/paper/preflight release candidate.\n\n"
            "Not financial advice.\n"
        )
        result = _run_public_docs_script_on_text(text)
        assert result.returncode != 0, "Expected failure on stale RC status claim"
        assert "release candidate" in result.stdout.lower()

    def test_historical_changelog_rc9_reference_allowed(self) -> None:
        text = (
            "# Changelog\n\n## [0.5.7rc9] - 2026-05-26\n\n"
            "Ninth release candidate for the v0.5.8 line.\n\n"
            "Not financial advice.\n"
        )
        result = _run_public_docs_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for historical RC changelog entry:\n{result.stdout}"
        )

    def test_current_source_version_0624_accepted(self) -> None:
        text = (
            "# README\n\n```bash\natlas --help\n```\n\n"
            "Sandbox-only, paper-first, offline-safe.\n"
            "Live trading disabled by default. Not financial advice.\n"
            "Current Status (v0.6.24)\n"
        )
        result = _run_public_docs_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for current source version:\n{result.stdout}"
        )

    @pytest.mark.parametrize("stale_version", [
        "v0.5.7.dev15",
        "v0.5.7.dev29",
        "0.5.9.dev0",
    ])
    def test_readme_with_stale_dev_status_fails(self, stale_version: str) -> None:
        text = (
            "# README\n\n```bash\natlas --help\n```\n\n"
            f"## Current Status ({stale_version})\n\n"
            "Sandbox-only, paper-first, offline-safe.\n"
            "Live trading disabled by default. Not financial advice.\n"
        )
        result = _run_public_docs_script_on_text(text)
        assert result.returncode != 0, f"Expected failure on stale {stale_version} current-status reference"
        assert stale_version in result.stdout or "stale" in result.stdout.lower()


class TestReleaseDocConsistency:
    def test_public_launch_readiness_doc_has_v0624_as_current_release(self) -> None:
        text = (ROOT / "docs" / "public-launch-readiness.md").read_text(encoding="utf-8")
        assert "latest stable public GitHub release is `v0.6.24`" in text, (
            "public-launch-readiness.md must describe v0.6.24 as the current stable release"
        )

    def test_public_launch_readiness_doc_does_not_claim_v062_as_latest(self) -> None:
        text = (ROOT / "docs" / "public-launch-readiness.md").read_text(encoding="utf-8")
        assert "latest stable public GitHub release is `v0.6.3`" not in text, (
            "public-launch-readiness.md must not describe v0.6.3 as the latest stable release"
        )

    def test_public_launch_readiness_doc_lists_v0615_as_historical(self) -> None:
        text = (ROOT / "docs" / "public-launch-readiness.md").read_text(encoding="utf-8")
        assert "v0.6.15" in text and "historical" in text.lower(), (
            "public-launch-readiness.md must list v0.6.15 as historical"
        )

    def test_release_checklist_does_not_reference_v062_as_public_tag(self) -> None:
        text = (ROOT / "docs" / "release-checklist.md").read_text(encoding="utf-8")
        assert "public tag `v0.6.2`" not in text, (
            "release-checklist.md must not reference v0.6.2 as the current public tag"
        )

    def test_readme_release_assurance_example_uses_v0624(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "--version v0.6.24" in text, (
            "README release assurance example must use v0.6.24"
        )
        assert "v0.6.1-local-check" not in text, (
            "README must not use stale v0.6.1 release assurance example"
        )

    def test_checks_reference_release_assurance_uses_v0624(self) -> None:
        text = (ROOT / "docs" / "development" / "checks-reference.md").read_text(encoding="utf-8")
        assert "--version v0.6.24" in text, (
            "checks-reference.md release assurance example must use v0.6.24"
        )
        assert "v0.6.0-local-check" not in text, (
            "checks-reference.md must not use stale v0.6.0 release assurance example"
        )

    def test_v064_described_as_planning_only(self) -> None:
        text = (ROOT / "docs" / "releases" / "v0.6.4-candidates.md").read_text(encoding="utf-8")
        assert "planning" in text.lower(), (
            "v0.6.4 candidates doc must describe v0.6.4 as planning-only"
        )
        assert "not" in text.lower() and "tagged" in text.lower(), (
            "v0.6.4 candidates doc must state v0.6.4 is not tagged"
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
