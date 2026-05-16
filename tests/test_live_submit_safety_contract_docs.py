"""Docs-truth tests for docs/live-submit-safety-contract.md.

These tests keep the live-submit safety contract aligned with the
actual implementation without modifying runtime behavior.
"""

import re
from pathlib import Path

import pytest


def _read_contract() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "docs" / "live-submit-safety-contract.md"
    return path.read_text(encoding="utf-8")


def _read_readme() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "README.md"
    return path.read_text(encoding="utf-8")


def _read_release_checklist() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "docs" / "release-checklist.md"
    return path.read_text(encoding="utf-8")


def _extract_section(text: str, heading: str) -> str:
    """Return the text under a markdown heading until the next heading at the same or higher level.

    Works for ## and ### headings.  Raises AssertionError if heading is missing.
    """
    assert heading in text, f"Missing required heading: {heading}"

    # Determine the heading level from the prefix
    level = heading.count("#", 0, heading.index(" ") + 1)

    # Find the start of the section
    start_idx = text.index(heading) + len(heading)

    # Find the next heading at the same or higher level (higher = fewer hashes)
    # Scan line by line for a heading with level <= current level
    for i in range(start_idx, len(text)):
        if text[i] == "\n":
            # Check if the next line is a heading
            line_start = i + 1
            if line_start >= len(text):
                break
            hash_count = 0
            j = line_start
            while j < len(text) and text[j] == "#":
                hash_count += 1
                j += 1
            if 1 <= hash_count <= level and j < len(text) and text[j] == " ":
                return text[start_idx:i]

    return text[start_idx:]


# ---------------------------------------------------------------------------
# 1. Contract file exists
# ---------------------------------------------------------------------------

class TestContractFileExists:
    def test_contract_file_exists(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        path = repo_root / "docs" / "live-submit-safety-contract.md"
        assert path.exists(), "docs/live-submit-safety-contract.md must exist"


# ---------------------------------------------------------------------------
# 2. Required sections exist
# ---------------------------------------------------------------------------

class TestRequiredSections:
    @pytest.fixture
    def contract(self) -> str:
        return _read_contract()

    @pytest.mark.parametrize("heading", [
        "# Live-Submit Safety Contract",
        "## 1. Scope",
        "## 2. Definitions",
        "## 3. Default Behavior",
        "## 4. Conditions Required for Live Submit",
        "## 5. Commands and Capabilities",
        "## 6. State Machine",
        "## 7. Reconciliation Contract",
        "## 8. Audit Contract",
        "## 9. Output Safety Contract",
        "## 10. Forbidden Claims",
        "## 11. Non-Goals",
    ])
    def test_heading_exists(self, contract: str, heading: str) -> None:
        assert heading in contract, f"Missing required heading: {heading}"


# ---------------------------------------------------------------------------
# 3. can_submit separation
# ---------------------------------------------------------------------------

class TestCanSubmitSeparation:
    @pytest.fixture
    def contract(self) -> str:
        return _read_contract()

    def test_resolver_level_readiness_mentioned(self, contract: str) -> None:
        assert "resolver-level" in contract.lower(), (
            "Document must mention resolver-level readiness for can_submit"
        )

    def test_execution_time_gates_mentioned(self, contract: str) -> None:
        assert "execution-time" in contract.lower() or "execution time" in contract.lower(), (
            "Document must mention execution-time gates"
        )

    def test_can_submit_mentioned(self, contract: str) -> None:
        assert "can_submit" in contract, "Document must mention can_submit"

    def test_run_submit_execution_mentioned(self, contract: str) -> None:
        assert "run_submit_execution" in contract, (
            "Document must mention run_submit_execution for execution-time gates"
        )


# ---------------------------------------------------------------------------
# 4. can_submit must not overclaim
# ---------------------------------------------------------------------------

class TestCanSubmitDoesNotOverclaim:
    @pytest.fixture
    def contract(self) -> str:
        return _read_contract()

    def test_can_submit_section_excludes_execution_time_gates(self, contract: str) -> None:
        """The can_submit section must NOT list execution-time gates."""
        section = _extract_section(contract, "### A. Resolver Readiness Gate: `can_submit`")
        section_lower = section.lower()

        forbidden_in_can_submit = [
            "fresh live sync",
            "sync validation",
            "risk revalidation",
            "live-submit hard limits",
            "submit-state mutation",
            "broker boundary",
            "market-order handling",
            "final kill-switch check",
        ]

        for phrase in forbidden_in_can_submit:
            assert phrase.lower() not in section_lower, (
                f"can_submit section must not contain execution-time gate: {phrase}"
            )


# ---------------------------------------------------------------------------
# 5. Execution-time gates documented
# ---------------------------------------------------------------------------

class TestExecutionTimeGatesDocumented:
    @pytest.fixture
    def contract(self) -> str:
        return _read_contract()

    def test_execution_time_gates_are_documented_after_can_submit(self, contract: str) -> None:
        """Execution-time gates must be in their own section and mention they come after can_submit."""
        section = _extract_section(contract, "### B. Submit Execution Gates")
        section_lower = section.lower()

        required_phrases = [
            "after can_submit",
            "fresh live sync",
            "sync validation",
            "risk revalidation",
            "live-submit hard limits",
            "submit-state mutation",
            "final kill-switch check",
            "broker boundary checks",
        ]

        for phrase in required_phrases:
            assert phrase.lower() in section_lower, (
                f"Submit Execution Gates section must document: {phrase}"
            )


# ---------------------------------------------------------------------------
# 6. Reconciliation contract includes submit evidence
# ---------------------------------------------------------------------------

class TestReconciliationContract:
    @pytest.fixture
    def contract(self) -> str:
        return _read_contract()

    def test_reconciliation_requires_valid_matching_submit_attempt_rule(self, contract: str) -> None:
        """Reconciliation must require a valid submit_attempt matching the client_order_id."""
        section = _extract_section(contract, "## 7. Reconciliation Contract")

        # Match the exact rule: valid submit_attempt + matching client_order_id in the same sentence/idea
        evidence_rule = re.search(
            r"valid\s+`?submit_attempt`?.{0,120}matching.{0,120}client_order_id",
            section,
            re.IGNORECASE,
        )
        assert evidence_rule is not None, (
            "Reconciliation contract must state that evidence requires a valid submit_attempt matching the client_order_id"
        )

    def test_reconciliation_approved_origin_is_suspicious(self, contract: str) -> None:
        """An approved-origin broker-found order must remain suspicious/manual-review."""
        section = _extract_section(contract, "## 7. Reconciliation Contract")
        section_lower = section.lower()

        assert "`approved` origin" in section or "approved origin" in section_lower, (
            "Reconciliation contract must mention approved-origin broker-found orders"
        )
        assert "manual review" in section_lower, (
            "Reconciliation contract must require manual review for approved-origin finds"
        )
        assert "not `acknowledged`" in section or "must be placed into a **manual review state**, not" in section, (
            "Reconciliation contract must state approved-origin finds are not acknowledged"
        )

    def test_reconciliation_no_submit_no_resolve_live(self, contract: str) -> None:
        """Reconciliation must not submit orders or resolve live broker."""
        section = _extract_section(contract, "## 7. Reconciliation Contract")
        section_lower = section.lower()

        assert "must not submit orders" in section_lower, (
            "Reconciliation contract must state that reconciliation must not submit orders"
        )
        assert "must not call" in section_lower and "resolve_execution_broker" in section_lower, (
            "Reconciliation contract must state that reconciliation must not call resolve_execution_broker"
        )


# ---------------------------------------------------------------------------
# 7. Output safety contract bounded, not absolute
# ---------------------------------------------------------------------------

class TestOutputSafetyContract:
    @pytest.fixture
    def contract(self) -> str:
        return _read_contract()

    @pytest.mark.parametrize("phrase", [
        "bounded",
        "sanitized",
        "raw exception text",
        "file paths",
        "headers",
        "broker response bodies",
        "secrets",
    ])
    def test_bounded_language_present(self, contract: str, phrase: str) -> None:
        assert phrase.lower() in contract.lower(), (
            f"Output safety contract must include bounded language: {phrase}"
        )

    def test_no_static_predefined_overclaim(self, contract: str) -> None:
        assert "must use static, pre-defined messages" not in contract.lower(), (
            "Document must not overclaim that all messages are static and pre-defined"
        )


# ---------------------------------------------------------------------------
# 8. Forbidden claims absent outside explicit section
# ---------------------------------------------------------------------------

class TestForbiddenClaimsAbsent:
    @pytest.fixture
    def contract(self) -> str:
        return _read_contract()

    def test_forbidden_claims_do_not_appear_outside_forbidden_claims_section(self, contract: str) -> None:
        """Forbidden phrases must not appear outside Section 10 (Forbidden Claims)."""
        parts = contract.split("## 10. Forbidden Claims")
        assert len(parts) >= 2, "Document must have a Forbidden Claims section"

        before_forbidden = parts[0]

        forbidden_phrases = [
            "zero risk",
            "risk-free",
            "guaranteed profit",
            "profit guaranteed",
            "safe live trading",
            "unattended live trading",
            "guaranteed returns",
            "can't lose",
            "no risk",
            "impossible",
            "guaranteed safety",
            "cannot lose",
        ]

        for phrase in forbidden_phrases:
            assert phrase.lower() not in before_forbidden.lower(), (
                f"Forbidden phrase '{phrase}' found outside Section 10"
            )


# ---------------------------------------------------------------------------
# 9. README link exists
# ---------------------------------------------------------------------------

class TestReadmeLink:
    def test_readme_links_to_safety_contract(self) -> None:
        readme = _read_readme()
        assert "docs/live-submit-safety-contract.md" in readme, (
            "README.md must link to docs/live-submit-safety-contract.md"
        )


# ---------------------------------------------------------------------------
# 10. Release checklist mentions safety contract
# ---------------------------------------------------------------------------

class TestReleaseChecklist:
    def test_release_checklist_mentions_safety_contract(self) -> None:
        checklist = _read_release_checklist()
        assert "docs/live-submit-safety-contract.md" in checklist, (
            "release-checklist.md must mention docs/live-submit-safety-contract.md"
        )

    def test_release_checklist_requires_review_on_behavior_change(self) -> None:
        checklist = _read_release_checklist()
        text = checklist.lower()
        assert "broker" in text and "live-submit-safety-contract" in text, (
            "release-checklist.md must require safety contract review when behavior changes"
        )


# ---------------------------------------------------------------------------
# 11. Quote gate docs-truth tests (Batch 5.20)
# ---------------------------------------------------------------------------

class TestQuoteGateDocumented:
    @pytest.fixture
    def contract(self) -> str:
        return _read_contract()

    def _quote_section(self, contract: str) -> str:
        """Return the combined Submit Execution Gates + Market-Order Quote Validation text."""
        gates = _extract_section(contract, "### B. Submit Execution Gates")
        # The quote validation subsection is nested under the gates heading
        quote = _extract_section(contract, "### Market-Order Quote Validation")
        return gates + "\n" + quote

    def test_execution_time_gates_section_contains_quote_gate(self, contract: str) -> None:
        """The Submit Execution Gates section must document the market-order quote gate."""
        section = self._quote_section(contract)
        section_lower = section.lower()

        required_phrases = [
            "market orders",
            "quote",
            "fresh",
            "risk revalidation",
            "buy",
            "ask",
            "sell",
            "bid",
            "missing",
            "stale",
            "malformed",
            "blocked",
        ]

        for phrase in required_phrases:
            assert phrase.lower() in section_lower, (
                f"Submit Execution Gates section must document quote gate concept: {phrase}"
            )

    def test_can_submit_section_excludes_quote_gate(self, contract: str) -> None:
        """The can_submit section must NOT contain quote-provider or quote-gate concepts."""
        section = _extract_section(contract, "### A. Resolver Readiness Gate: `can_submit`")
        section_lower = section.lower()

        forbidden_in_can_submit = [
            "market quote",
            "quote provider",
            "fresh quote",
            "market-order quote",
            "buy uses ask",
            "sell uses bid",
            "stale quote",
            "malformed quote",
            "quote-derived notional",
        ]

        for phrase in forbidden_in_can_submit:
            assert phrase.lower() not in section_lower, (
                f"can_submit section must not contain quote gate concept: {phrase}"
            )

    def test_conservative_price_rule_in_same_section(self, contract: str) -> None:
        """Buy->ask and sell->bid must appear in the same execution-time section."""
        section = self._quote_section(contract)

        buy_ask = re.search(r"buy.{0,80}ask", section, re.IGNORECASE)
        sell_bid = re.search(r"sell.{0,80}bid", section, re.IGNORECASE)

        assert buy_ask is not None, (
            "Submit Execution Gates must state that buy orders use the ask price"
        )
        assert sell_bid is not None, (
            "Submit Execution Gates must state that sell orders use the bid price"
        )

    def test_no_mid_or_last_price_claim(self, contract: str) -> None:
        """The safety contract must not claim market orders can use mid/last/cached prices."""
        section = self._quote_section(contract)
        section_lower = section.lower()

        prohibited_pricing = [
            "mid price",
            "midpoint",
            "last price",
            "previous close",
            "cached price",
        ]

        for phrase in prohibited_pricing:
            assert phrase.lower() not in section_lower, (
                f"Quote gate section must not mention unsupported pricing: {phrase}"
            )

    def test_default_blocked_behavior_documented(self, contract: str) -> None:
        """The doc must state that market orders are blocked by default without a quote provider."""
        section = self._quote_section(contract)
        section_lower = section.lower()

        has_blocked_by_default = "blocked by default" in section_lower
        has_no_quote_provider = "no quote provider" in section_lower
        has_market_price_unavailable = "market_price_unavailable" in section_lower

        assert has_blocked_by_default or has_no_quote_provider or has_market_price_unavailable, (
            "Quote gate must document that market orders are blocked by default without a quote provider"
        )

    def test_quote_gate_does_not_imply_safety(self, contract: str) -> None:
        """The quote gate must include a caution that it does not make market orders safe."""
        section = self._quote_section(contract)
        section_lower = section.lower()

        caution_phrases = [
            "does not make market orders safe",
            "does not guarantee safe execution",
            "bounded price for risk evaluation only",
        ]

        has_caution = any(phrase in section_lower for phrase in caution_phrases)
        assert has_caution, (
            "Quote gate must include a caution that it does not make market orders safe"
        )

        # Also ensure no forbidden overclaim phrases appear in the quote section
        forbidden_overclaims = [
            "safe live trading",
            "risk-free",
            "zero risk",
            "guaranteed profit",
            "no risk",
            "production-ready live trading",
            "market orders are safe",
            "market order safety guaranteed",
        ]

        for phrase in forbidden_overclaims:
            assert phrase.lower() not in section_lower, (
                f"Quote gate section must not contain overclaim: {phrase}"
            )

    def test_quote_failure_modes_documented(self, contract: str) -> None:
        """The quote gate must document the specific failure modes that block market orders."""
        section = self._quote_section(contract)
        section_lower = section.lower()

        failure_modes = [
            ("missing", "missing"),
            ("stale", "stale"),
            ("malformed", "malformed"),
            ("symbol mismatch", "mismatched"),  # "symbol-mismatched" counts
            ("invalid quote", "invalid"),
        ]

        matched = sum(
            1 for _label, keyword in failure_modes if keyword in section_lower
        )
        # Require all 5 failure-mode indicators
        assert matched >= 5, (
            f"Quote gate must document failure modes (matched {matched}/5): {failure_modes}"
        )
