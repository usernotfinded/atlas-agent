# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_live_path_safety_assertions.py
# PURPOSE: Verifies live path safety assertions behavior and regression
#         expectations.
# DEPS:    json, pathlib, pytest.
# ==============================================================================

"""Live-path safety assertions — documentation and contract tests.

These tests verify that public docs, README, issue templates, and release
docs continue to state the correct safety posture. They do not exercise
runtime live-trading code or bypass gates.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# README safety assertions
# ---------------------------------------------------------------------------


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestReadmeSafetyPosture:
    def test_readme_says_live_trading_disabled_by_default(self) -> None:
        path = REPO_ROOT / "README.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "live trading is disabled by default" in text or "disabled by default" in text

    def test_readme_says_provider_execution_locked(self) -> None:
        path = REPO_ROOT / "README.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "provider execution" in text
        assert "locked" in text or "disabled" in text or "not implemented" in text

    def test_readme_says_broker_execution_blocked(self) -> None:
        path = REPO_ROOT / "README.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "broker" in text
        assert "blocked" in text or "disabled by default" in text or "can_submit=false" in text

    def test_readme_denies_profitability(self) -> None:
        path = REPO_ROOT / "README.md"
        text = path.read_text(encoding="utf-8").lower()
        # README must mention profit only to deny it
        if "profit" in text:
            assert (
                "not" in text
                or "no " in text
                or "risk" in text
                or "loss" in text
            )

    def test_readme_denies_production_readiness(self) -> None:
        path = REPO_ROOT / "README.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "not production ready" in text or "not a live trading system" in text

    def test_readme_has_not_financial_advice(self) -> None:
        path = REPO_ROOT / "README.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "not financial advice" in text


# ---------------------------------------------------------------------------
# Public docs safety assertions
# ---------------------------------------------------------------------------


class TestPublicDocsSafetyPosture:
    def test_public_launch_readiness_says_live_disabled(self) -> None:
        path = REPO_ROOT / "docs" / "public-launch-readiness.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "live trading is explicitly disabled by default" in text

    def test_public_launch_readiness_says_provider_not_implemented(self) -> None:
        path = REPO_ROOT / "docs" / "public-launch-readiness.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "provider execution is not implemented for real providers" in text

    def test_public_launch_readiness_says_broker_beta(self) -> None:
        path = REPO_ROOT / "docs" / "public-launch-readiness.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "broker adapters are in beta" in text

    def test_live_submit_safety_contract_exists(self) -> None:
        path = REPO_ROOT / "docs" / "live-submit-safety-contract.md"
        assert path.exists(), "live-submit-safety-contract.md must exist"

    def test_live_submit_contract_says_default_can_submit_false(self) -> None:
        path = REPO_ROOT / "docs" / "live-submit-safety-contract.md"
        text = path.read_text(encoding="utf-8").lower()
        assert "can_submit" in text
        assert "false" in text or "disabled" in text or "blocked" in text


# ---------------------------------------------------------------------------
# Issue template safety assertions
# ---------------------------------------------------------------------------


class TestIssueTemplateSafety:
    def test_no_issue_template_asks_for_credentials(self) -> None:
        issue_dir = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
        for path in issue_dir.glob("*.yml"):
            text = path.read_text(encoding="utf-8").lower()
            assert "api key" not in text or "do not" in text, (
                f"{path.name} may ask for credentials without a warning"
            )
            assert "secret" not in text or "do not" in text or "redact" in text, (
                f"{path.name} may ask for secrets without a warning"
            )
            assert "password" not in text, f"{path.name} asks for passwords"

    def test_no_issue_template_has_unsafe_credential_prompt(self) -> None:
        """Issue templates must not prompt for credentials without warnings."""
        issue_dir = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
        for path in issue_dir.glob("*.yml"):
            text = path.read_text(encoding="utf-8").lower()
            # If the template mentions credentials, it must also warn not to share them
            if "api key" in text or "secret" in text or "token" in text:
                assert "do not" in text or "redact" in text or "remove" in text, (
                    f"{path.name} mentions credentials without a do-not-share warning"
                )


# ---------------------------------------------------------------------------
# Release docs safety assertions
# ---------------------------------------------------------------------------


class TestReleaseDocsSafety:
    def test_latest_release_notes_do_not_claim_pypi_publish(self) -> None:
        """Release notes for versions without PyPI publish must say so."""
        release_dir = REPO_ROOT / "docs" / "releases"
        for path in sorted(release_dir.glob("v0.5.8.1.md")):
            text = path.read_text(encoding="utf-8").lower()
            assert "no pypi" in text or "not published" in text or "no publish" in text, (
                f"{path.name} should disclaim PyPI publish"
            )

    def test_latest_release_notes_do_not_claim_github_release(self) -> None:
        for path in sorted((REPO_ROOT / "docs" / "releases").glob("v0.5.8.1.md")):
            text = path.read_text(encoding="utf-8").lower()
            assert "no github release" in text or "not created" in text or "no release" in text, (
                f"{path.name} should disclaim GitHub Release creation"
            )

    def test_changelog_unreleased_does_not_claim_pypi(self) -> None:
        path = REPO_ROOT / "CHANGELOG.md"
        text = path.read_text(encoding="utf-8").lower()
        unreleased = text.split("## [unreleased]")[1].split("## [")[0]
        assert "pypi" not in unreleased or "no pypi" in unreleased or "not" in unreleased


# ---------------------------------------------------------------------------
# Capability inventory safety assertions
# ---------------------------------------------------------------------------


class TestCapabilityInventorySafety:
    def test_live_trading_capability_is_disabled_by_default(self) -> None:
        path = REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for cap in data.get("capabilities", []):
            if cap.get("id") == "live-trading-default":
                assert cap["status"] == "disabled_by_default"
                assert cap["public_claim_level"] == "safe_to_claim"
                return
        pytest.fail("Missing live-trading-default capability in inventory")

    def test_provider_execution_capability_is_docs_only(self) -> None:
        path = REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for cap in data.get("capabilities", []):
            if cap.get("id") == "provider-execution-locked":
                assert cap["status"] == "docs_only"
                assert cap["public_claim_level"] == "safe_to_claim"
                return
        pytest.fail("Missing provider-execution-locked capability in inventory")

    def test_broker_execution_capability_is_disabled_by_default(self) -> None:
        path = REPO_ROOT / "tests" / "fixtures" / "product_capability_inventory.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for cap in data.get("capabilities", []):
            if cap.get("id") == "broker-execution-blocked":
                assert cap["status"] == "disabled_by_default"
                assert cap["public_claim_level"] == "safe_to_claim"
                return
        pytest.fail("Missing broker-execution-blocked capability in inventory")
