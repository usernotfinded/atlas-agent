"""Tests for reviewer onboarding script and docs — Batch 10.10.

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
SCRIPT = ROOT / "scripts" / "check_reviewer_onboarding.py"
WALKTHROUGH = ROOT / "docs" / "external-reviewer-walkthrough.md"
CHECKLIST = ROOT / "docs" / "reviewer-checklist.md"

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


class TestDocsExist:
    def test_walkthrough_exists(self) -> None:
        assert WALKTHROUGH.exists(), f"Walkthrough not found: {WALKTHROUGH}"

    def test_checklist_exists(self) -> None:
        assert CHECKLIST.exists(), f"Checklist not found: {CHECKLIST}"

    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestReadmeLinks:
    @pytest.fixture
    def readme_text(self) -> str:
        return (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_links_to_walkthrough(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "external-reviewer-walkthrough.md" in readme_text
            or "reviewer walkthrough" in lower
        )

    def test_readme_links_to_checklist(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "reviewer-checklist.md" in readme_text
            or "reviewer checklist" in lower
        )

    def test_readme_links_to_public_launch_readiness(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "public-launch-readiness.md" in readme_text
            or "public launch readiness" in lower
        )


class TestPublicLaunchDocsLinks:
    def test_public_launch_readiness_links_to_walkthrough(self) -> None:
        text = (ROOT / "docs" / "public-launch-readiness.md").read_text(encoding="utf-8")
        lower = text.lower()
        assert (
            "external-reviewer-walkthrough.md" in text
            or "reviewer walkthrough" in lower
        )

    def test_public_launch_readiness_links_to_checklist(self) -> None:
        text = (ROOT / "docs" / "public-launch-readiness.md").read_text(encoding="utf-8")
        lower = text.lower()
        assert (
            "reviewer-checklist.md" in text
            or "reviewer checklist" in lower
        )


class TestOnboardingDocsSafety:
    def _doc_paths(self) -> list[Path]:
        return [WALKTHROUGH, CHECKLIST]

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

    def test_no_live_trading_readiness_claims(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "live trading ready" not in text
            assert "production trading ready" not in text
            assert "safe to trade" not in text

    def test_no_profitability_claims(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "guaranteed profit" not in text
            assert "profitable strategy" not in text
            assert "verified alpha" not in text
            assert "beats the market" not in text

    def test_mentions_no_credentials_required(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "no credentials" in text or "credentials are not" in text

    def test_mentions_live_trading_disabled(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "live trading disabled by default" in text

    def test_mentions_provider_execution_locked(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "provider execution remains locked" in text

    def test_mentions_trust_blocked(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "trust remains blocked" in text

    def test_safe_commands_present(self) -> None:
        text = WALKTHROUGH.read_text(encoding="utf-8").lower()
        assert "check_version_consistency.py" in text
        assert "check_forbidden_claims.py" in text
        assert "check_public_docs_consistency.py" in text
        assert "check_public_launch_readiness.py" in text
        assert "release_check.sh --quick" in text


class TestScriptBehavior:
    def test_script_passes(self) -> None:
        result = _run_script()
        assert result.returncode == 0, (
            f"Reviewer onboarding script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_script_json_output(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, (
            f"Reviewer onboarding script --json failed:\n{result.stdout}\n{result.stderr}"
        )
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["package_version"] == "0.5.8.1"
        assert data["public_tag"] == "v0.5.8"
        assert data["errors"] == []

    def test_json_output_has_no_absolute_paths(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in result.stdout, f"JSON output contains absolute path: {frag}"


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

    def test_no_shell_true(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "shell=True" not in text

    def test_no_secrets_required(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "api_key" not in text
        assert "secret" not in text or "secret-like" in text
