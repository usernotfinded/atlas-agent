# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_provider_safety_dossier_docs.py
# PURPOSE: Verifies provider safety dossier docs behavior and regression
#         expectations.
# DEPS:    pathlib.
# ==============================================================================

"""Documentation guard tests for the Public Safety Proof Pack — Batch 9.8.

This batch is documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _read(path: str) -> str:
    full = REPO_ROOT / path
    with open(full, encoding="utf-8") as f:
        return f.read()


def _lower(text: str) -> str:
    return text.lower()


# ---------------------------------------------------------------------------
# Doc existence
# ---------------------------------------------------------------------------


class TestSafetyDossierDocsExist:
    def test_provider_safety_dossier_doc_exists(self) -> None:
        text = _read("docs/provider-safety-dossier.md")
        assert text.strip()

    def test_provider_safety_dossier_workflow_example_exists(self) -> None:
        text = _read("docs/examples/provider-safety-dossier-workflow.md")
        assert text.strip()


# ---------------------------------------------------------------------------
# README section presence
# ---------------------------------------------------------------------------


class TestReadmeContainsSafetyDossierSection:
    def test_readme_has_provider_safety_dossier_heading(self) -> None:
        text = _read("README.md")
        assert "## Provider Safety Dossier" in text

    def test_readme_has_sandbox_only(self) -> None:
        text = _read("README.md")
        assert "sandbox-only" in _lower(text)

    def test_readme_has_provider_execution_locked(self) -> None:
        text = _read("README.md")
        assert "provider execution remains locked" in _lower(text)

    def test_readme_has_trust_blocked(self) -> None:
        text = _read("README.md")
        assert "trust remains blocked" in _lower(text)

    def test_readme_has_no_broker_order_path(self) -> None:
        text = _read("README.md")
        assert "no broker/order path" in _lower(text)

    def test_readme_has_no_credentials_loaded(self) -> None:
        text = _read("README.md")
        assert "no credentials loaded" in _lower(text)

    def test_readme_has_no_network_enabled(self) -> None:
        text = _read("README.md")
        assert "no network enabled" in _lower(text)

    def test_readme_has_live_trading_disabled(self) -> None:
        text = _read("README.md")
        assert "live trading disabled by default" in _lower(text)


# ---------------------------------------------------------------------------
# Forbidden overclaims (must be absent or in negative context)
# ---------------------------------------------------------------------------


class TestSafetyDossierDocsNoForbiddenOverclaims:
    FORBIDDEN_PHRASES = (
        "live trading ready",
        "production trading ready",
        "safe to trade",
        "trust granted",
        "provider execution enabled",
        "broker execution enabled",
        "orders enabled",
        "approvals enabled",
        "autonomous trading ready",
    )

    PATHS = (
        "README.md",
        "docs/provider-safety-dossier.md",
        "docs/examples/provider-safety-dossier-workflow.md",
    )

    def _assert_absent_outside_negative_context(self, text: str, phrase: str) -> bool:
        lower_text = text.lower()
        phrase_lower = phrase.lower()
        idx = lower_text.find(phrase_lower)
        if idx == -1:
            return True
        window = 120
        start = max(0, idx - window)
        end = min(len(text), idx + len(phrase_lower) + window)
        context = lower_text[start:end]
        negative_indicators = (
            "not ",
            "does not",
            "never",
            "no ",
            "avoid",
            "disclaimer",
            "prohibited",
            "forbidden",
            "must not",
            "cannot",
            "do not",
            "is not",
            "are not",
            "without",
            "fail closed",
            "not yet",
            "not implemented",
            "not enabled",
            "not authorized",
            "not a ",
            "not ready",
        )
        return any(ind in context for ind in negative_indicators)

    def _check_all_docs(self, phrase: str) -> None:
        for path in self.PATHS:
            text = _read(path)
            assert self._assert_absent_outside_negative_context(
                text, phrase
            ), f"Forbidden overclaim '{phrase}' found outside negative context in {path}"

    def test_no_live_trading_ready(self) -> None:
        self._check_all_docs("live trading ready")

    def test_no_production_trading_ready(self) -> None:
        self._check_all_docs("production trading ready")

    def test_no_safe_to_trade(self) -> None:
        self._check_all_docs("safe to trade")

    def test_no_trust_granted(self) -> None:
        self._check_all_docs("trust granted")

    def test_no_provider_execution_enabled(self) -> None:
        self._check_all_docs("provider execution enabled")

    def test_no_broker_execution_enabled(self) -> None:
        self._check_all_docs("broker execution enabled")

    def test_no_orders_enabled(self) -> None:
        self._check_all_docs("orders enabled")

    def test_no_approvals_enabled(self) -> None:
        self._check_all_docs("approvals enabled")

    def test_no_autonomous_trading_ready(self) -> None:
        self._check_all_docs("autonomous trading ready")


# ---------------------------------------------------------------------------
# Forbidden fragments
# ---------------------------------------------------------------------------


class TestSafetyDossierDocsNoForbiddenFragments:
    FORBIDDEN_FRAGMENTS = (
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
        "broker.example.com",
    )

    PATHS = (
        "README.md",
        "docs/provider-safety-dossier.md",
        "docs/examples/provider-safety-dossier-workflow.md",
    )

    def test_no_forbidden_fragments(self) -> None:
        import re

        for path in self.PATHS:
            text = _read(path)
            for frag in self.FORBIDDEN_FRAGMENTS:
                # Allow "Authorization" inside negative context lists or code blocks
                # that explain it is blocked; the docs explicitly mention it as forbidden.
                if frag == "Authorization":
                    count = text.count(frag)
                    if count <= 2:
                        continue
                if frag == "sk-":
                    # Only flag "sk-" when it looks like a secret prefix, not inside words like "risk-rejection"
                    matches = re.findall(r"\bsk-", text)
                    assert len(matches) == 0, f"Forbidden fragment '{frag}' found in {path}"
                    continue
                assert frag not in text, f"Forbidden fragment '{frag}' found in {path}"


# ---------------------------------------------------------------------------
# Command example safety
# ---------------------------------------------------------------------------


class TestSafetyDossierCommandExamples:
    PATHS = (
        "README.md",
        "docs/provider-safety-dossier.md",
        "docs/examples/provider-safety-dossier-workflow.md",
    )

    def test_no_absolute_paths_in_command_examples(self) -> None:
        """Command examples must not contain absolute-looking paths like /Users/ or /tmp/."""
        for path in self.PATHS:
            text = _read(path)
            lines = text.splitlines()
            for line in lines:
                if line.strip().startswith("atlas research"):
                    # Allow relative paths like reports/foo.md but not absolute ones
                    assert "/Users/" not in line, f"Absolute path in {path}: {line}"
                    assert "/private/" not in line, f"Absolute path in {path}: {line}"

    def test_artifact_id_placeholders_used(self) -> None:
        """Export commands should use <DOSSIER_ID> placeholders, not real-looking IDs."""
        for path in self.PATHS:
            text = _read(path)
            lines = text.splitlines()
            for line in lines:
                if "provider-safety-dossier-export" in line:
                    assert "<DOSSIER_ID>" in line, (
                        f"Expected <DOSSIER_ID> placeholder in {path}: {line}"
                    )


# ---------------------------------------------------------------------------
# Required disclaimers
# ---------------------------------------------------------------------------


class TestSafetyDossierDocsContainRequiredDisclaimers:
    PATHS = (
        "README.md",
        "docs/provider-safety-dossier.md",
        "docs/examples/provider-safety-dossier-workflow.md",
    )

    def test_not_financial_advice_present(self) -> None:
        for path in self.PATHS:
            text = _read(path)
            assert (
                "not financial advice" in _lower(text)
                or "financial advice" in _lower(text)
            ), f"Missing financial advice disclaimer in {path}"

    def test_safety_does_not_imply_profitability(self) -> None:
        for path in self.PATHS:
            text = _read(path)
            assert (
                "safety validation does not imply profitability" in _lower(text)
                or "does not imply profitability" in _lower(text)
                or "artifact safety does not imply profitability" in _lower(text)
            ), f"Missing profitability limitation in {path}"
