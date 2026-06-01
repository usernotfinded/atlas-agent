"""Tests for public launch messaging script and docs — Batch 10.11.

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
SCRIPT = ROOT / "scripts" / "check_public_launch_messaging.py"
LAUNCH_DOC = ROOT / "docs" / "public-launch-messaging.md"
FEEDBACK_GUIDE = ROOT / "docs" / "feedback-request-guide.md"
PUBLIC_FAQ = ROOT / "docs" / "public-faq.md"

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
    "beat the market",
    "makes money",
    "earns money",
    "passive income",
    "financial freedom",
)

_HYPE_WORDS = (
    "revolutionary",
    "game-changing",
    "unstoppable",
    "fully autonomous",
    "production-grade trading bot",
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
    def test_launch_messaging_doc_exists(self) -> None:
        assert LAUNCH_DOC.exists(), f"Launch messaging doc not found: {LAUNCH_DOC}"

    def test_feedback_request_guide_exists(self) -> None:
        assert FEEDBACK_GUIDE.exists(), f"Feedback request guide not found: {FEEDBACK_GUIDE}"

    def test_public_faq_exists(self) -> None:
        assert PUBLIC_FAQ.exists(), f"Public FAQ not found: {PUBLIC_FAQ}"

    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestReadmeLinks:
    @pytest.fixture
    def readme_text(self) -> str:
        return (ROOT / "README.md").read_text(encoding="utf-8")

    def test_readme_links_to_launch_messaging(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "public-launch-messaging.md" in readme_text
            or "launch messaging" in lower
        )

    def test_readme_links_to_feedback_guide(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "feedback-request-guide.md" in readme_text
            or "feedback request guide" in lower
        )

    def test_readme_links_to_public_faq(self, readme_text: str) -> None:
        lower = readme_text.lower()
        assert (
            "public-faq.md" in readme_text
            or "public faq" in lower
        )


class TestPublicLaunchDocsLinks:
    def test_public_launch_readiness_links_to_launch_messaging(self) -> None:
        text = (ROOT / "docs" / "public-launch-readiness.md").read_text(encoding="utf-8")
        lower = text.lower()
        assert (
            "public-launch-messaging.md" in text
            or "launch messaging" in lower
        )

    def test_public_launch_readiness_links_to_feedback_guide(self) -> None:
        text = (ROOT / "docs" / "public-launch-readiness.md").read_text(encoding="utf-8")
        lower = text.lower()
        assert (
            "feedback-request-guide.md" in text
            or "feedback request guide" in lower
        )

    def test_public_launch_readiness_links_to_public_faq(self) -> None:
        text = (ROOT / "docs" / "public-launch-readiness.md").read_text(encoding="utf-8")
        lower = text.lower()
        assert (
            "public-faq.md" in text
            or "public faq" in lower
        )


class TestLaunchDocsSafety:
    def _doc_paths(self) -> list[Path]:
        return [LAUNCH_DOC, FEEDBACK_GUIDE, PUBLIC_FAQ]

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

    def test_no_hype_words(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            for hype in _HYPE_WORDS:
                assert hype not in text, f"{path.name} contains hype word: {hype}"

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

    def test_asks_for_technical_feedback(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "technical feedback" in text or "feedback" in text

    def test_does_not_ask_for_profit_feedback(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            # Allow negative contexts like "do not ask for profit feedback"
            for phrase in ("profit feedback", "trading signal quality"):
                if phrase not in text:
                    continue
                idx = text.index(phrase)
                context = text[max(0, idx - 120):min(len(text), idx + 120)]
                negative_indicators = (
                    "not ", "do not", "never", "no ", "avoid",
                    "must not", "cannot", "prohibited", "forbidden",
                )
                if not any(ind in context for ind in negative_indicators):
                    pytest.fail(f"{path.name} asks for profit feedback: {phrase}")

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

    def test_mentions_not_financial_advice(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "not financial advice" in text

    def test_mentions_no_profitability_implication(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "does not imply profitability" in text or "no promise of returns" in text

    def test_does_not_invite_real_money_trading(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            for phrase in (
                "use atlas with real money",
                "connect real broker credentials",
                "trade real money",
            ):
                if phrase not in text:
                    continue
                idx = text.index(phrase)
                context = text[max(0, idx - 60):min(len(text), idx + 60)]
                negative_indicators = (
                    "not ", "do not", "never", "no ", "avoid",
                    "must not", "cannot", "prohibited", "forbidden",
                )
                if not any(ind in context for ind in negative_indicators):
                    pytest.fail(f"{path.name} invites real-money trading: {phrase}")

    def test_does_not_request_credentials(self) -> None:
        for path in self._doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            assert "send me your api key" not in text
            assert "share your credentials" not in text


class TestScriptBehavior:
    def test_script_passes(self) -> None:
        result = _run_script()
        assert result.returncode == 0, (
            f"Public launch messaging script failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_script_json_output(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, (
            f"Public launch messaging script --json failed:\n{result.stdout}\n{result.stderr}"
        )
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert data["package_version"] == "0.5.8"
        assert data["public_tag"] == "v0.5.8"
        assert data["errors"] == []

    def test_json_output_has_no_absolute_paths(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in result.stdout, f"JSON output contains absolute path: {frag}"


class TestScriptSafety:
    def test_no_network_calls(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "urllib" not in text
        assert "httpx" not in text
        # "requests" as a plain word is too brittle; check for import patterns
        assert "import requests" not in text
        assert "from requests" not in text

    def test_no_social_posting(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "reddit" not in text
        assert "hacker news" not in text
        assert "twitter" not in text
        assert "discord" not in text

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
