from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from atlas_agent.brokers.resolver import BrokerResolver, BrokerStatus, BrokerResolution
from atlas_agent.config import AtlasConfig


@pytest.fixture
def base_config() -> AtlasConfig:
    return AtlasConfig(
        broker={"provider": "none", "enable_live_trading": False},
    )


def test_paper_status_all_ready(base_config: AtlasConfig) -> None:
    resolver = BrokerResolver(base_config)
    status = resolver.resolve_status("paper")
    assert status == BrokerStatus(
        mode="paper",
        broker_id="paper",
        configured=True,
        credentials_configured=True,
        can_sync=True,
        can_submit=True,
        code="paper_ready",
        message="paper broker is ready",
    )


def test_paper_status_with_none_config() -> None:
    resolver = BrokerResolver(None)
    status = resolver.resolve_status("paper")
    assert status.can_sync is True
    assert status.can_submit is True


def test_paper_sync_resolves_to_paper_adapter(base_config: AtlasConfig) -> None:
    resolver = BrokerResolver(base_config)
    resolution = resolver.resolve_sync_provider("paper")
    assert resolution.sync_provider is not None
    assert resolution.execution_broker is not None
    assert resolution.status.code == "paper_ready"
    from atlas_agent.brokers.paper import PaperBrokerAdapter
    assert isinstance(resolution.sync_provider, PaperBrokerAdapter)


def test_paper_execution_resolves_to_paper_broker(base_config: AtlasConfig) -> None:
    resolver = BrokerResolver(base_config)
    resolution = resolver.resolve_execution_broker("paper")
    assert resolution.execution_broker is not None
    assert resolution.sync_provider is not None
    from atlas_agent.brokers.paper import PaperBroker
    assert isinstance(resolution.execution_broker, PaperBroker)


def test_live_unconfigured_returns_unconfigured(base_config: AtlasConfig) -> None:
    resolver = BrokerResolver(base_config)
    status = resolver.resolve_status("live")
    assert status.configured is False
    assert status.credentials_configured is False
    assert status.can_sync is False
    assert status.can_submit is False
    assert status.code == "live_broker_unconfigured"


def test_live_unconfigured_with_none_config() -> None:
    resolver = BrokerResolver(None)
    status = resolver.resolve_status("live")
    assert status.configured is False
    assert status.credentials_configured is False
    assert status.code == "live_broker_unconfigured"


def test_live_configured_alpaca_with_credentials_reports_sync_ready() -> None:
    config = AtlasConfig(broker={"provider": "alpaca", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    with patch.dict(os.environ, {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}, clear=False):
        status = resolver.resolve_status("live")
    assert status.configured is True
    assert status.credentials_configured is True
    assert status.can_sync is True
    assert status.can_submit is False
    assert status.code == "live_sync_ready"
    assert "submit remains disabled" in status.message


def test_live_configured_binance_with_credentials_reports_deferred() -> None:
    config = AtlasConfig(broker={"provider": "binance", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"BINANCE_API_KEY": "key", "BINANCE_API_SECRET": "secret"}
    with patch.dict(os.environ, env, clear=False):
        status = resolver.resolve_status("live")
    assert status.configured is True
    assert status.credentials_configured is True
    assert status.can_sync is False
    assert status.can_submit is False
    assert status.code == "live_sync_deferred"


def test_live_configured_binance_legacy_secret_alias() -> None:
    config = AtlasConfig(broker={"provider": "binance", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"BINANCE_API_KEY": "key", "BINANCE_SECRET_KEY": "legacy"}
    with patch.dict(os.environ, env, clear=False):
        status = resolver.resolve_status("live")
    assert status.credentials_configured is True
    assert status.code == "live_sync_deferred"


def test_live_missing_credentials_alpaca() -> None:
    config = AtlasConfig(broker={"provider": "alpaca", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    with patch.dict(os.environ, {}, clear=True):
        status = resolver.resolve_status("live")
    assert status.configured is True
    assert status.credentials_configured is False
    assert status.can_sync is False
    assert status.can_submit is False
    assert status.code == "live_credentials_missing"


def test_live_missing_credentials_binance() -> None:
    config = AtlasConfig(broker={"provider": "binance", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"BINANCE_API_KEY": "key"}  # missing secret
    with patch.dict(os.environ, env, clear=True):
        status = resolver.resolve_status("live")
    assert status.credentials_configured is False
    assert status.code == "live_credentials_missing"


def test_live_unknown_broker_fails_safe() -> None:
    config = AtlasConfig(broker={"provider": "unknown_broker", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    status = resolver.resolve_status("live")
    assert status.configured is False
    assert status.credentials_configured is False
    assert status.can_sync is False
    assert status.can_submit is False
    assert status.code == "live_broker_unsupported"
    assert "not supported" in status.message


def test_live_resolve_sync_provider_returns_none_for_binance() -> None:
    config = AtlasConfig(broker={"provider": "binance", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"BINANCE_API_KEY": "key", "BINANCE_API_SECRET": "secret"}
    with patch.dict(os.environ, env, clear=False):
        resolution = resolver.resolve_sync_provider("live")
    assert resolution.sync_provider is None
    assert resolution.execution_broker is None
    assert resolution.status.code == "live_sync_deferred"


def test_live_resolve_sync_provider_returns_alpaca_adapter() -> None:
    config = AtlasConfig(broker={"provider": "alpaca", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        resolution = resolver.resolve_sync_provider("live")
    assert resolution.sync_provider is not None
    assert resolution.execution_broker is None
    assert resolution.status.code == "live_sync_ready"
    from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
    assert isinstance(resolution.sync_provider, AlpacaBrokerAdapter)


def test_live_resolve_execution_broker_returns_none() -> None:
    config = AtlasConfig(broker={"provider": "alpaca", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        resolution = resolver.resolve_execution_broker("live")
    assert resolution.execution_broker is None
    assert resolution.sync_provider is None
    assert resolution.status.code == "live_sync_ready"


def test_live_resolve_sync_provider_never_paper_fallback() -> None:
    config = AtlasConfig(broker={"provider": "alpaca", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    resolution = resolver.resolve_sync_provider("live")
    assert resolution.sync_provider is None
    from atlas_agent.brokers.paper import PaperBrokerAdapter
    assert not isinstance(resolution.sync_provider, PaperBrokerAdapter)


def test_provider_env_vars_do_not_affect_resolver() -> None:
    config = AtlasConfig(broker={"provider": "alpaca", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {
        "OPENAI_API_KEY": "sk-openai",
        "ANTHROPIC_API_KEY": "sk-anthropic",
        "AI_PROVIDER": "openai",
    }
    with patch.dict(os.environ, env, clear=True):
        status = resolver.resolve_status("live")
    assert status.credentials_configured is False
    assert "sk-openai" not in status.message
    assert "sk-anthropic" not in status.message


def test_no_private_values_in_status_dict() -> None:
    config = AtlasConfig(broker={"provider": "binance", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"BINANCE_API_KEY": "secret-key-123", "BINANCE_API_SECRET": "secret-val-456"}
    with patch.dict(os.environ, env, clear=False):
        status = resolver.resolve_status("live")
    d = status.to_dict()
    serialized = str(d)
    assert "secret-key-123" not in serialized
    assert "secret-val-456" not in serialized
    assert "BINANCE_API_KEY" not in serialized
    assert "BINANCE_API_SECRET" not in serialized


def test_unknown_mode_returns_safe_status() -> None:
    resolver = BrokerResolver(None)
    status = resolver.resolve_status("backtest")
    assert status.configured is False
    assert status.can_sync is False
    assert status.can_submit is False
    assert status.code == "unknown_mode"


def test_ccxt_credentials_or_logic() -> None:
    config = AtlasConfig(broker={"provider": "ccxt", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    # Either key is sufficient
    with patch.dict(os.environ, {"CCXT_API_KEY": "key"}, clear=True):
        status = resolver.resolve_status("live")
    assert status.credentials_configured is True
    assert status.code == "live_sync_deferred"

    with patch.dict(os.environ, {"EXCHANGE_API_KEY": "key"}, clear=True):
        status = resolver.resolve_status("live")
    assert status.credentials_configured is True

    with patch.dict(os.environ, {}, clear=True):
        status = resolver.resolve_status("live")
    assert status.credentials_configured is False
