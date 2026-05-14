from __future__ import annotations

import pytest

from atlas_agent.config import AtlasConfig
from atlas_agent.config.schema import BrokerConfig, RiskConfig


def test_broker_config_has_enable_live_submit_default_false() -> None:
    config = BrokerConfig()
    assert config.enable_live_submit is False


def test_risk_config_has_live_submit_limits_defaults() -> None:
    config = RiskConfig()
    assert config.live_submit_max_order_notional == 0.0
    assert config.live_submit_allowed_symbols is None
    assert config.live_submit_allowed_sides is None


def test_atlas_config_legacy_mapping_enable_live_submit() -> None:
    config = AtlasConfig(enable_live_submit=True)
    assert config.broker.enable_live_submit is True


def test_atlas_config_enable_live_submit_property() -> None:
    config = AtlasConfig(broker={"enable_live_submit": True})
    assert config.enable_live_submit is True


def test_atlas_config_live_submit_max_order_notional_property() -> None:
    config = AtlasConfig(risk={"live_submit_max_order_notional": 500.0})
    assert config.live_submit_max_order_notional == 500.0
    assert config.risk.live_submit_max_order_notional == 500.0


def test_atlas_config_live_submit_allowed_symbols_property() -> None:
    config = AtlasConfig(risk={"live_submit_allowed_symbols": {"AAPL", "TSLA"}})
    assert config.live_submit_allowed_symbols == {"AAPL", "TSLA"}


def test_atlas_config_live_submit_allowed_sides_property() -> None:
    config = AtlasConfig(risk={"live_submit_allowed_sides": {"buy"}})
    assert config.live_submit_allowed_sides == {"buy"}


def test_broker_config_enable_live_submit_isolation() -> None:
    """enable_live_trading and enable_live_submit are independent."""
    config = AtlasConfig(
        broker={"enable_live_trading": True, "enable_live_submit": False}
    )
    assert config.enable_live_trading is True
    assert config.enable_live_submit is False

    config2 = AtlasConfig(
        broker={"enable_live_trading": False, "enable_live_submit": True}
    )
    assert config2.enable_live_trading is False
    assert config2.enable_live_submit is True
