from __future__ import annotations

from omni_trade_ai.config import OmniTradeConfig
from omni_trade_ai.execution.order import Order
from omni_trade_ai.portfolio.state import PortfolioState
from omni_trade_ai.risk.kill_switch import KillSwitch
from omni_trade_ai.risk.manager import RiskManager


def test_kill_switch_file_toggle(tmp_path) -> None:
    switch = KillSwitch(tmp_path / "kill")

    switch.enable()
    assert switch.is_enabled()
    switch.disable()
    assert not switch.is_enabled()


def test_kill_switch_blocks_order() -> None:
    manager = RiskManager.from_config(OmniTradeConfig(kill_switch_enabled=True))
    decision = manager.validate_order(
        Order("BTC-USD", "buy", 1, limit_price=100, confidence=1),
        PortfolioState(cash=10_000),
        mode="paper",
        market_price=100,
    )

    assert not decision.allowed
    assert "kill switch is enabled" in decision.reasons

