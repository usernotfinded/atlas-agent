"""CHANGELOG consistency and safety checks.

No execution code, no network calls, no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
RELEASES_DIR = ROOT / "docs" / "releases"


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
    "live_trading_ready",
    "production_trading_ready",
    "safe_to_trade",
    "trust_granted",
    "provider_execution_enabled",
    "broker_execution_enabled",
    "orders_enabled",
    "approvals_enabled",
    "autonomous_trading_ready",
    "profitable_strategy",
    "verified_alpha",
    "beats_the_market",
    "real_money_ready",
)

_FORBIDDEN_FRAGMENTS = (
    "/Users/",
    "/private/var/",
    "Authorization",
    "Bearer",
    "APCA",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "API_KEY",
    "sk-",
)

_REQUIRED_VERSIONS = (
    "0.5.7rc1",
    "0.5.7.dev40",
    "0.5.7.dev41",
    "0.5.7.dev42",
    "0.5.7.dev43",
    "0.5.7.dev44",
    "0.5.7.dev45",
    "0.5.7.dev46",
    "0.5.7.dev47",
    "0.5.7.dev48",
    "0.5.7.dev49",
    "0.5.7.dev50",
)


@pytest.fixture
def changelog_text() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


class TestChangelogStructure:
    def test_changelog_exists(self) -> None:
        assert CHANGELOG.exists()

    def test_dev40_through_dev50_present(self, changelog_text: str) -> None:
        for version in _REQUIRED_VERSIONS:
            assert f"[{version}]" in changelog_text, f"Missing CHANGELOG entry for {version}"

    def test_rc1_release_note_exists(self) -> None:
        assert (RELEASES_DIR / "v0.5.7-rc1.md").exists()

    def test_dev50_release_note_exists(self) -> None:
        assert (RELEASES_DIR / "v0.5.7.dev50.md").exists()

    def test_release_notes_match_changelog_versions(self, changelog_text: str) -> None:
        for version in _REQUIRED_VERSIONS:
            note_path = RELEASES_DIR / f"{version}.md"
            if note_path.exists():
                assert f"[{version}]" in changelog_text, f"CHANGELOG missing {version} but release note exists"


class TestChangelogSafety:
    def test_no_forbidden_positive_claims(self, changelog_text: str) -> None:
        lower = changelog_text.lower()
        for claim in _FORBIDDEN_POSITIVE_CLAIMS:
            assert claim not in lower, f"Forbidden positive claim in CHANGELOG: {claim}"

    def test_no_forbidden_fragments(self, changelog_text: str) -> None:
        for frag in _FORBIDDEN_FRAGMENTS:
            assert frag not in changelog_text, f"Forbidden fragment in CHANGELOG: {frag}"

    def test_no_live_trading_readiness_claims(self, changelog_text: str) -> None:
        lower = changelog_text.lower()
        unsafe_phrases = (
            "live trading ready",
            "production trading ready",
            "safe to trade",
            "real-money ready",
        )
        for phrase in unsafe_phrases:
            assert phrase not in lower, f"Unsafe live-trading readiness claim: {phrase}"

    def test_no_profitability_claims(self, changelog_text: str) -> None:
        lower = changelog_text.lower()
        profit_phrases = (
            "guaranteed profit",
            "profitable strategy",
            "verified alpha",
            "beats the market",
        )
        for phrase in profit_phrases:
            assert phrase not in lower, f"Unsafe profitability claim: {phrase}"


class TestChangelogVersionReferences:
    def test_current_rc_version_in_changelog(self, changelog_text: str) -> None:
        assert "[0.5.7rc1]" in changelog_text

    def test_current_dev_version_in_changelog(self, changelog_text: str) -> None:
        assert "[0.5.7.dev50]" in changelog_text

    def test_unreleased_section_present(self, changelog_text: str) -> None:
        assert "## [Unreleased]" in changelog_text
