from __future__ import annotations

import warnings

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


# Batch 5.9: Pydantic V2 ConfigDict cleanup tests

def test_atlas_config_does_not_emit_pydantic_config_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        AtlasConfig()
    messages = [str(w.message) for w in caught]
    assert not any("Support for class-based `config` is deprecated" in msg for msg in messages)


def test_atlas_config_defaults_still_work() -> None:
    config = AtlasConfig()
    assert config.trading_mode == "paper"
    assert config.broker.provider == "none"
    assert config.broker.enable_live_trading is False
    assert config.broker.enable_live_submit is False
    assert config.risk.max_order_notional == 100.0
    assert config.audit.audit_dir.name == "audit"


def test_atlas_config_legacy_mapping_enable_live_trading() -> None:
    config = AtlasConfig(enable_live_trading=True)
    assert config.broker.enable_live_trading is True
    assert config.enable_live_trading is True


def test_atlas_config_legacy_mapping_live_broker() -> None:
    config = AtlasConfig(live_broker="alpaca")
    assert config.broker.provider == "alpaca"
    assert config.live_broker == "alpaca"


def test_atlas_config_legacy_mapping_max_order_notional() -> None:
    config = AtlasConfig(max_order_notional=500.0)
    assert config.risk.max_order_notional == 500.0
    assert config.max_order_notional == 500.0


def test_atlas_config_legacy_mapping_audit_dir() -> None:
    from pathlib import Path
    config = AtlasConfig(audit_dir=Path("custom_audit"))
    assert config.audit.audit_dir.name == "custom_audit"
    assert config.audit_dir.name == "custom_audit"


def test_atlas_config_compatibility_properties_work() -> None:
    config = AtlasConfig(
        broker={"enable_live_trading": True, "enable_live_submit": True, "provider": "alpaca"},
        risk={"max_order_notional": 250.0},
        audit={"audit_dir": "my_audit"},
    )
    assert config.enable_live_trading is True
    assert config.enable_live_submit is True
    assert config.live_broker == "alpaca"
    assert config.max_order_notional == 250.0
    assert config.audit_dir.name == "my_audit"
