# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_config_public_api.py
# PURPOSE: Verifies config public api behavior and regression expectations.
# DEPS:    None.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_market_config_is_publicly_exported() -> None:
    """MarketConfig must be importable from the public atlas_agent.config API."""
    from atlas_agent.config import AtlasConfig, MarketConfig

    config = AtlasConfig()
    assert isinstance(config.market, MarketConfig)


def test_market_config_defaults_to_no_symbol() -> None:
    """MarketConfig must not default to any hardcoded product symbol."""
    from atlas_agent.config import MarketConfig

    market = MarketConfig()
    assert market.symbol == ""
    assert market.watchlist == []
