# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/update/test_update_safety.py
# PURPOSE: Verifies update safety behavior and regression expectations.
# DEPS:    atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from atlas_agent.update.safety import UpdateSafetyCheck, evaluate_update_safety


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class StubSafetyCheck(UpdateSafetyCheck):
    def __init__(
        self,
        *,
        live: bool = False,
        open_positions: bool = False,
        pending_orders: bool = False,
        dirty_tree: bool = False,
        kill_switch: bool = True,
        smoke_ok: bool = True,
    ) -> None:
        self.live = live
        self.open_positions = open_positions
        self.pending_orders = pending_orders
        self.dirty_tree = dirty_tree
        self.kill_switch = kill_switch
        self.smoke_ok = smoke_ok

    def is_live_trading_enabled(self) -> bool:
        return self.live

    def has_open_positions(self) -> bool:
        return self.open_positions

    def has_pending_orders(self) -> bool:
        return self.pending_orders

    def has_uncommitted_changes(self) -> bool:
        return self.dirty_tree

    def kill_switch_available(self) -> bool:
        return self.kill_switch

    def smoke_check(self) -> bool:
        return self.smoke_ok


def test_update_safety_allows_safe_state() -> None:
    result = evaluate_update_safety(StubSafetyCheck())
    assert result.safe
    assert result.blockers == []


def test_update_safety_collects_blockers() -> None:
    result = evaluate_update_safety(
        StubSafetyCheck(
            live=True,
            open_positions=True,
            pending_orders=True,
            dirty_tree=True,
            kill_switch=False,
        )
    )
    assert not result.safe
    assert "live trading is enabled" in result.blockers
    assert "broker has open positions" in result.blockers
    assert "broker has pending orders" in result.blockers
    assert "working tree has uncommitted changes" in result.blockers
    assert "kill switch is not available" in result.blockers
