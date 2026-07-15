# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_public_repo_hygiene.py
# PURPOSE: Verifies public repo hygiene behavior and regression expectations.
# DEPS:    pathlib, pytest.
# ==============================================================================

"""Tests for public repository hygiene files — Batch 10.8.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[1]

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

_SECRET_LIKE_FRAGMENTS = (
    "Authorization: Bearer",
    "Bearer ",
    "APCA-",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "API_KEY",
    "sk-",
    "broker.example.com",
)

_REQUIRED_SAFE_WORDING = (
    "not financial advice",
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestRepoHygieneFilesExist:
    def test_security_md_exists(self) -> None:
        assert (ROOT / "SECURITY.md").exists()

    def test_contributing_md_exists(self) -> None:
        assert (ROOT / "CONTRIBUTING.md").exists()

    def test_pr_template_exists(self) -> None:
        assert (ROOT / ".github" / "pull_request_template.md").exists()

    def test_issue_template_dir_exists(self) -> None:
        assert (ROOT / ".github" / "ISSUE_TEMPLATE").exists()

    def test_bug_report_template_exists(self) -> None:
        assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").exists()

    def test_docs_issue_template_exists(self) -> None:
        assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "docs_issue.yml").exists()

    def test_safety_concern_template_exists(self) -> None:
        assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "safety_concern.yml").exists()

    def test_feature_request_template_exists(self) -> None:
        assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").exists()

    def test_issue_template_config_exists(self) -> None:
        assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").exists()

    def test_public_repo_hygiene_doc_exists(self) -> None:
        assert (ROOT / "docs" / "public-repo-hygiene.md").exists()


class TestTemplatesWarnAgainstSecrets:
    def _template_texts(self) -> list[tuple[str, str]]:
        templates = [
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "docs_issue.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "safety_concern.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
        ]
        result: list[tuple[str, str]] = []
        for path in templates:
            text = path.read_text(encoding="utf-8")
            result.append((path.name, text))
        return result

    def test_templates_warn_not_to_paste_secrets(self) -> None:
        for name, text in self._template_texts():
            lower = text.lower()
            assert "do not paste" in lower or "do not include" in lower or "remove any" in lower, (
                f"{name} should warn against pasting secrets"
            )


class TestTemplatesContainNoRealSecretExamples:
    def _template_texts(self) -> list[tuple[str, str]]:
        templates = [
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "docs_issue.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "safety_concern.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
        ]
        result: list[tuple[str, str]] = []
        for path in templates:
            text = path.read_text(encoding="utf-8")
            result.append((path.name, text))
        return result

    def test_no_secret_like_examples_in_templates(self) -> None:
        for name, text in self._template_texts():
            for frag in _SECRET_LIKE_FRAGMENTS:
                assert frag not in text, (
                    f"{name} contains secret-like example: {frag!r}"
                )


class TestPublicDocsContainNoForbiddenClaims:
    def _public_doc_paths(self) -> list[Path]:
        return [
            ROOT / "SECURITY.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "docs" / "public-repo-hygiene.md",
            ROOT / ".github" / "pull_request_template.md",
        ]

    def test_no_forbidden_positive_claims(self) -> None:
        for path in self._public_doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            for claim in _FORBIDDEN_POSITIVE_CLAIMS:
                assert claim not in text, (
                    f"{path.name} contains forbidden claim: {claim!r}"
                )

    def test_no_forbidden_fragments(self) -> None:
        for path in self._public_doc_paths():
            text = path.read_text(encoding="utf-8")
            for frag in _FORBIDDEN_FRAGMENTS:
                assert frag not in text, (
                    f"{path.name} contains forbidden fragment: {frag!r}"
                )

    def test_no_secret_like_fragments(self) -> None:
        for path in self._public_doc_paths():
            text = path.read_text(encoding="utf-8")
            for frag in _SECRET_LIKE_FRAGMENTS:
                assert frag not in text, (
                    f"{path.name} contains secret-like fragment: {frag!r}"
                )


class TestPublicDocsContainRequiredSafetyWording:
    def _public_doc_paths(self) -> list[Path]:
        return [
            ROOT / "SECURITY.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "docs" / "public-repo-hygiene.md",
        ]

    def test_required_safety_wording_present(self) -> None:
        for path in self._public_doc_paths():
            text = path.read_text(encoding="utf-8").lower()
            for phrase in _REQUIRED_SAFE_WORDING:
                assert phrase in text, (
                    f"{path.name} missing required safety wording: {phrase!r}"
                )


class TestSafetyPostureWording:
    def test_security_md_has_safety_posture(self) -> None:
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower()
        assert "sandbox" in text or "paper" in text or "preflight" in text
        assert "live trading disabled by default" in text
        assert "provider execution remains locked" in text
        assert "trust remains blocked" in text

    def test_contributing_md_has_safety_boundaries(self) -> None:
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8").lower()
        assert "protected" in text
        assert "src/atlas_agent/config" in text
        assert "src/atlas_agent/brokers" in text
        assert "src/atlas_agent/execution" in text
        assert "src/atlas_agent/safety" in text
        assert "src/atlas_agent/risk" in text

    def test_public_repo_hygiene_has_safety_posture(self) -> None:
        text = (ROOT / "docs" / "public-repo-hygiene.md").read_text(encoding="utf-8").lower()
        assert "live trading disabled by default" in text
        assert "provider execution remains locked" in text
        assert "trust remains blocked" in text
        assert "no broker/order path" in text


class TestProtectedBoundaryCommands:
    def test_pr_template_includes_protected_boundary_commands(self) -> None:
        text = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
        assert "git diff -- src/atlas_agent/config" in text
        assert "git diff --cached -- src/atlas_agent/config" in text

    def test_contributing_md_includes_protected_boundary_commands(self) -> None:
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        assert "git diff -- src/atlas_agent/config" in text
        assert "git diff --cached -- src/atlas_agent/config" in text


class TestIssueTemplatesDoNotRequestCredentials:
    def _issue_templates(self) -> list[tuple[str, str]]:
        templates = [
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "docs_issue.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "safety_concern.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
        ]
        result: list[tuple[str, str]] = []
        for path in templates:
            text = path.read_text(encoding="utf-8").lower()
            result.append((path.name, text))
        return result

    def test_no_api_key_requests(self) -> None:
        for name, text in self._issue_templates():
            # Templates may warn against including API keys; they must not ask for them.
            # Check for input fields that request keys (not warning text).
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if "api key" in line or "apikey" in line:
                    # If the line is a warning/do-not-include, it's fine
                    if "do not" in line or "remove" in line or "include" in line or "paste" in line:
                        continue
                    pytest.fail(f"{name} appears to ask for API keys: {line!r}")

    def test_no_broker_credential_requests(self) -> None:
        for name, text in self._issue_templates():
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if "broker credential" in line:
                    if "do not" in line or "remove" in line or "include" in line or "paste" in line or "out of scope" in line or "requests for" in line:
                        continue
                    pytest.fail(f"{name} appears to ask for broker credentials: {line!r}")

    def test_no_password_requests(self) -> None:
        for name, text in self._issue_templates():
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if "password" in line:
                    if "do not" in line or "remove" in line or "include" in line or "paste" in line:
                        continue
                    pytest.fail(f"{name} appears to ask for passwords: {line!r}")


class TestFeatureRequestGuardrails:
    def test_feature_template_warns_against_bypass(self) -> None:
        text = (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").read_text(encoding="utf-8").lower()
        assert "bypass" in text
        assert "risk gate" in text
        assert "live trading" in text

    def test_feature_template_has_safety_boundary_checkboxes(self) -> None:
        text = (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").read_text(encoding="utf-8")
        assert "bypassing risk gates" in text
        assert "enabling live trading" in text
        assert "profit guarantees" in text


class TestSecurityPolicySafety:
    def test_security_md_does_not_claim_live_trading_readiness(self) -> None:
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower()
        assert "live trading ready" not in text
        assert "production trading ready" not in text
        assert "safe to trade" not in text

    def test_security_md_does_not_claim_profitability(self) -> None:
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8").lower()
        assert "guaranteed profit" not in text
        assert "profitable strategy" not in text
        assert "verified alpha" not in text
