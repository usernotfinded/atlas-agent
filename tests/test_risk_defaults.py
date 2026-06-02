from __future__ import annotations

import re
from pathlib import Path

from atlas_agent.risk.limits import (
    DEFAULT_MAX_DAILY_LOSS_PCT,
    DEFAULT_MAX_POSITION_NOTIONAL,
    DEFAULT_MAX_SINGLE_TRADE_NOTIONAL,
    DEFAULT_MINIMUM_CONFIDENCE,
    RiskLimits,
)

REPO_ROOT = Path(__file__).parent.parent


class TestEnvExampleSafety:
    """.env.example must disable live trading and require approval by default."""

    def test_env_example_disables_live_trading(self) -> None:
        text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "ENABLE_LIVE_TRADING=false" in text
        assert "TRADING_MODE=paper" in text
        assert "REQUIRE_ORDER_APPROVAL=true" in text

    def test_env_example_minimum_confidence_matches_canonical(self) -> None:
        text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        match = re.search(r"^MINIMUM_CONFIDENCE=(.+)$", text, re.MULTILINE)
        assert match is not None, "MINIMUM_CONFIDENCE not found in .env.example"
        assert float(match.group(1)) == DEFAULT_MINIMUM_CONFIDENCE

    def test_env_example_documents_canonical_defaults(self) -> None:
        text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        assert "Canonical model defaults live in src/atlas_agent/risk/limits.py" in text
        assert "max_position_notional=1000.0" in text
        assert "max_single_trade_notional=500.0" in text
        assert "max_daily_loss_pct=0.02" in text
        assert "minimum_confidence=0.6" in text


class TestRiskLimitsCanonicalDefaults:
    """RiskLimits model defaults must match the canonical constants."""

    def test_max_position_notional_default(self) -> None:
        assert RiskLimits().max_position_notional == DEFAULT_MAX_POSITION_NOTIONAL

    def test_max_single_trade_notional_default(self) -> None:
        assert RiskLimits().max_single_trade_notional == DEFAULT_MAX_SINGLE_TRADE_NOTIONAL

    def test_max_daily_loss_pct_default(self) -> None:
        assert RiskLimits().max_daily_loss_pct == DEFAULT_MAX_DAILY_LOSS_PCT

    def test_minimum_confidence_default(self) -> None:
        assert RiskLimits().minimum_confidence == DEFAULT_MINIMUM_CONFIDENCE

    def test_paper_only_default(self) -> None:
        assert RiskLimits().paper_only is True

    def test_live_trading_enabled_default(self) -> None:
        assert RiskLimits().live_trading_enabled is False


class TestRiskConfigDefault:
    """AtlasConfig risk defaults must not silently drift from canonicals."""

    def test_atlas_config_minimum_confidence_matches_canonical(self) -> None:
        from atlas_agent.config import AtlasConfig

        config = AtlasConfig()
        assert config.risk.minimum_confidence == DEFAULT_MINIMUM_CONFIDENCE

    def test_atlas_config_trading_mode_is_paper(self) -> None:
        from atlas_agent.config import AtlasConfig

        config = AtlasConfig()
        assert config.trading_mode == "paper"

    def test_atlas_config_enable_live_trading_is_false(self) -> None:
        from atlas_agent.config import AtlasConfig

        config = AtlasConfig()
        assert config.enable_live_trading is False
