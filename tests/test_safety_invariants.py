from __future__ import annotations

from pathlib import Path
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order import Order
from atlas_agent.execution.order_router import OrderRouter
from atlas_agent.risk.manager import RiskManager
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.execution.approval import ApprovalManager
from atlas_agent.execution.audit import AuditLogger
from unittest.mock import MagicMock

def test_config_defaults_are_safe() -> None:
    config = AtlasConfig()
    assert config.trading_mode == "paper"
    assert config.enable_live_trading is False
    assert config.live_broker == "none"
    assert config.allow_leverage is False
    assert config.require_order_approval is True
    assert config.order_approval_mode == "manual_live"

def test_model_roster_is_present_in_readme() -> None:
    readme_path = Path("README.md")
    assert readme_path.exists()
    content = readme_path.read_text(encoding="utf-8")
    assert "<!-- ATLAS_MODEL_ROSTER_START -->" in content
    assert "<!-- ATLAS_MODEL_ROSTER_END -->" in content
    assert "| Rank | Model | Score |" in content

def test_live_trading_disabled_reasons_work() -> None:
    # Default config
    config = AtlasConfig()
    reasons = config.live_disabled_reasons()
    assert "TRADING_MODE must be live" in reasons
    assert "ENABLE_LIVE_TRADING must be true" in reasons
    assert "LIVE_BROKER must name a supported live broker" in reasons

def test_order_router_enforces_risk_manager_before_live_gates(tmp_path) -> None:
    config = AtlasConfig(trading_mode="live", enable_live_trading=True, live_broker="alpaca")
    risk_manager = MagicMock(spec=RiskManager)
    risk_manager.validate_order.return_value = MagicMock(allowed=False, reasons=["risky"])
    
    audit = AuditLogger(tmp_path / "audit")
    router = OrderRouter(
        config=config,
        risk_manager=risk_manager,
        approval_manager=MagicMock(spec=ApprovalManager),
        audit=audit
    )
    
    order = Order("BTC-USD", "buy", 1, limit_price=100)
    result = router.route(
        order,
        mode="live",
        broker=MagicMock(),
        portfolio=PortfolioState(),
        market_price=100
    )
    
    assert result.status == "rejected"
    assert "risk manager rejected order" in result.message
    assert "risky" in result.reasons
    # Verify it stopped at risk manager and didn't check live gates or broker
    risk_manager.validate_order.assert_called_once()

def test_kill_switch_blocks_live_trading() -> None:
    config = AtlasConfig(
        trading_mode="live", 
        enable_live_trading=True, 
        live_broker="alpaca",
        kill_switch_enabled=True
    )
    assert "KILL_SWITCH_ENABLED is true" in config.live_disabled_reasons()
