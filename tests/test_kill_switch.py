# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_kill_switch.py
# PURPOSE: Verifies kill switch behavior and regression expectations.
# DEPS:    atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order import Order
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.risk.kill_switch import KillSwitch
from atlas_agent.risk.manager import RiskManager


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_kill_switch_file_toggle(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "kill")

    switch.enable()
    assert switch.is_enabled()
    switch.disable()
    assert not switch.is_enabled()


def test_kill_switch_blocks_order() -> None:
    manager = RiskManager.from_config(AtlasConfig(kill_switch_enabled=True))
    decision = manager.validate_order(
        Order("TEST-SYMBOL", "buy", 1, limit_price=100, confidence=1),
        PortfolioState(cash=10_000),
        mode="paper",
        market_price=100,
    )

    assert not decision.allowed
    assert "kill switch is enabled" in decision.reasons
