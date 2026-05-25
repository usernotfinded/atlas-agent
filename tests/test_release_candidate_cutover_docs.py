"""Tests for release candidate cutover docs - Batch 10.2.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "release-candidate-cutover.md"


class TestDocExists:
    def test_doc_exists(self) -> None:
        assert DOC_PATH.exists(), f"Doc not found: {DOC_PATH}"


class TestRequiredSafeWording:
    def test_dry_run_only_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "dry-run only" in text or "dry run only" in text

    def test_sandbox_release_candidate_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "sandbox release candidate" in text

    def test_paper_first_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "paper-first" in text or "paper first" in text

    def test_provider_execution_locked_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "provider execution remains locked" in text

    def test_trust_blocked_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "trust remains blocked" in text

    def test_no_broker_order_path_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "no broker/order path" in text or "no broker order path" in text

    def test_no_credentials_loaded_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "no credentials loaded" in text

    def test_no_network_enabled_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "no network enabled" in text

    def test_live_trading_disabled_by_default_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "live trading disabled by default" in text

    def test_not_financial_advice_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "not financial advice" in text

    def test_does_not_imply_profitability_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "does not imply profitability" in text

    def test_does_not_imply_trading_correctness_present(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert (
            "does not imply trading correctness" in text
            or "trading-correctness" in text
        )


class TestForbiddenClaimsAbsent:
    def test_no_live_trading_ready(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "live trading ready" not in text

    def test_no_production_trading_ready(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "production trading ready" not in text

    def test_no_safe_to_trade(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "safe to trade" not in text

    def test_no_trust_granted(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "trust granted" not in text

    def test_no_provider_execution_enabled(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "provider execution enabled" not in text

    def test_no_broker_execution_enabled(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "broker execution enabled" not in text

    def test_no_orders_enabled(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "orders enabled" not in text

    def test_no_approvals_enabled(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "approvals enabled" not in text

    def test_no_real_money_ready(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "real-money ready" not in text

    def test_no_guaranteed_profit(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        assert "guaranteed profit" not in text


class TestForbiddenFragmentsAbsent:
    def test_no_absolute_paths(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert "/private/var/" not in text

    def test_no_secret_patterns(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "sk-" not in text
        assert "Bearer" not in text
        assert "APCA" not in text
        assert "API_KEY" not in text
        assert "SECRET" not in text
        assert "TOKEN" not in text
        assert "PASSWORD" not in text
        assert "Authorization" not in text
