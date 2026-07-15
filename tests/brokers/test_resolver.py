# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/brokers/test_resolver.py
# PURPOSE: Verifies resolver behavior and regression expectations.
# DEPS:    json, os, datetime, pathlib, unittest, pytest, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas_agent.brokers.resolver import BrokerResolver, BrokerStatus, BrokerResolution
from atlas_agent.config import AtlasConfig


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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
    assert "submit" in status.message


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


# ---------------------------------------------------------------------------
# Batch 5.0: Live-submit conditional can_submit
# ---------------------------------------------------------------------------

def _make_all_valid_config(**overrides) -> AtlasConfig:
    """Return a config that passes all can_submit conditions."""
    kwargs = {
        "trading_mode": "live",
        "broker": {
            "provider": "alpaca",
            "enable_live_trading": True,
            "enable_live_submit": True,
        },
        "safety": {"order_approval_mode": "manual_live"},
        "risk": {"allow_leverage": False},
    }
    kwargs.update(overrides)
    return AtlasConfig(**kwargs)


def _write_opt_in(path: Path, config: AtlasConfig, **overrides) -> None:
    """Write a valid opt-in record to the audit file."""
    from atlas_agent.brokers.resolver import _compute_live_submit_fingerprint
    record = {
        "event_type": "live_submit_opt_in_enabled",
        "opt_in": True,
        "broker_id": config.broker.provider,
        "config_fingerprint": _compute_live_submit_fingerprint(config),
        "created_at": datetime.now(UTC).isoformat(),
        "expiry_hours": 24,
    }
    record.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_alpaca_can_submit_false_when_enable_live_submit_false() -> None:
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True, "enable_live_submit": False},
    )
    resolver = BrokerResolver(config)
    with patch.dict(os.environ, {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}, clear=False):
        status = resolver.resolve_status("live")
    assert status.can_submit is False
    assert status.code == "live_sync_ready"


def test_alpaca_can_submit_false_when_enable_live_trading_false() -> None:
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": False, "enable_live_submit": True},
    )
    resolver = BrokerResolver(config)
    with patch.dict(os.environ, {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}, clear=False):
        status = resolver.resolve_status("live")
    assert status.can_submit is False
    assert status.code == "live_sync_ready"


def test_alpaca_can_submit_false_when_kill_switch_active(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.memory_dir = tmp_path / "memory"
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.safety.kill_switch.KillSwitchController") as mock_cls:
            mock_ks = MagicMock()
            mock_ks.status.return_value = MagicMock(enabled=True, mode="soft_pause")
            mock_cls.return_value = mock_ks
            status = resolver.resolve_status("live")
    assert status.can_submit is False
    assert status.code == "live_sync_ready"


def test_alpaca_can_submit_false_when_trading_mode_not_live(tmp_path: Path) -> None:
    config = _make_all_valid_config(trading_mode="paper")
    config.memory_dir = tmp_path / "memory"
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.safety.kill_switch.KillSwitchController") as mock_cls:
            mock_ks = MagicMock()
            mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
            mock_cls.return_value = mock_ks
            status = resolver.resolve_status("live")
    assert status.can_submit is False
    assert status.code == "live_sync_ready"


def test_alpaca_can_submit_false_when_order_approval_disabled_live(tmp_path: Path) -> None:
    config = _make_all_valid_config(safety={"order_approval_mode": "disabled_live"})
    config.memory_dir = tmp_path / "memory"
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.safety.kill_switch.KillSwitchController") as mock_cls:
            mock_ks = MagicMock()
            mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
            mock_cls.return_value = mock_ks
            status = resolver.resolve_status("live")
    assert status.can_submit is False
    assert status.code == "live_sync_ready"


def test_alpaca_can_submit_false_when_allow_leverage_true(tmp_path: Path) -> None:
    config = _make_all_valid_config(risk={"allow_leverage": True})
    config.memory_dir = tmp_path / "memory"
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.safety.kill_switch.KillSwitchController") as mock_cls:
            mock_ks = MagicMock()
            mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
            mock_cls.return_value = mock_ks
            status = resolver.resolve_status("live")
    assert status.can_submit is False
    assert status.code == "live_sync_ready"


def test_alpaca_can_submit_false_when_credentials_missing(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.memory_dir = tmp_path / "memory"
    resolver = BrokerResolver(config)
    with patch.dict(os.environ, {}, clear=True):
        with patch("atlas_agent.safety.kill_switch.KillSwitchController") as mock_cls:
            mock_ks = MagicMock()
            mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
            mock_cls.return_value = mock_ks
            status = resolver.resolve_status("live")
    assert status.can_submit is False
    assert status.code == "live_credentials_missing"


def test_alpaca_can_submit_false_when_opt_in_not_recorded(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.memory_dir = tmp_path / "memory"
    config.audit.audit_dir = tmp_path / "audit"
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.safety.kill_switch.KillSwitchController") as mock_cls:
            mock_ks = MagicMock()
            mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
            mock_cls.return_value = mock_ks
            status = resolver.resolve_status("live")
    assert status.can_submit is False
    assert status.code == "live_sync_ready"


def test_alpaca_can_submit_true_when_all_conditions_met(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.memory_dir = tmp_path / "memory"
    config.audit.audit_dir = tmp_path / "audit"
    _write_opt_in(tmp_path / "audit" / "live_submit_opt_in.jsonl", config)
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.safety.kill_switch.KillSwitchController") as mock_cls:
            mock_ks = MagicMock()
            mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
            mock_cls.return_value = mock_ks
            status = resolver.resolve_status("live")
    assert status.can_submit is True
    assert status.code == "live_ready"
    assert "live Alpaca sync and submit are ready" == status.message


def test_resolve_execution_broker_returns_none_when_can_submit_false() -> None:
    config = AtlasConfig(broker={"provider": "alpaca", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        resolution = resolver.resolve_execution_broker("live")
    assert resolution.execution_broker is None
    assert resolution.status.can_submit is False


def test_resolve_execution_broker_returns_alpaca_when_can_submit_true(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.memory_dir = tmp_path / "memory"
    config.audit.audit_dir = tmp_path / "audit"
    _write_opt_in(tmp_path / "audit" / "live_submit_opt_in.jsonl", config)
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.safety.kill_switch.KillSwitchController") as mock_cls:
            mock_ks = MagicMock()
            mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
            mock_cls.return_value = mock_ks
            resolution = resolver.resolve_execution_broker("live")
    assert resolution.execution_broker is not None
    from atlas_agent.brokers.alpaca import AlpacaBroker
    assert isinstance(resolution.execution_broker, AlpacaBroker)


def test_resolve_execution_broker_does_not_instantiate_broker_when_can_submit_false() -> None:
    config = AtlasConfig(broker={"provider": "alpaca", "enable_live_trading": True})
    resolver = BrokerResolver(config)
    env = {"ALPACA_API_KEY": "key", "ALPACA_SECRET_KEY": "secret"}
    from atlas_agent.brokers.alpaca import AlpacaBroker
    with patch.dict(os.environ, env, clear=False):
        with patch.object(AlpacaBroker, "__init__", side_effect=AssertionError("AlpacaBroker must not be instantiated when can_submit=false")) as mock_init:
            resolution = resolver.resolve_execution_broker("live")
    assert resolution.execution_broker is None
    mock_init.assert_not_called()


# ---------------------------------------------------------------------------
# Batch 5.0: Opt-in record validation
# ---------------------------------------------------------------------------

def test_opt_in_record_valid_when_all_conditions_met(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.audit.audit_dir = tmp_path / "audit"
    _write_opt_in(tmp_path / "audit" / "live_submit_opt_in.jsonl", config)
    from atlas_agent.brokers.resolver import _live_submit_opt_in_status
    result = _live_submit_opt_in_status(config)
    assert result.valid is True
    assert result.code == "opt_in_valid"


def test_opt_in_record_invalid_when_file_missing(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.audit.audit_dir = tmp_path / "audit"
    from atlas_agent.brokers.resolver import _live_submit_opt_in_status
    result = _live_submit_opt_in_status(config)
    assert result.valid is False
    assert result.code == "opt_in_file_missing"


def test_opt_in_record_invalid_when_disabled_after_enabled(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.audit.audit_dir = tmp_path / "audit"
    opt_in_path = tmp_path / "audit" / "live_submit_opt_in.jsonl"
    _write_opt_in(opt_in_path, config)
    # Append a disable record
    disable_record = {
        "event_type": "live_submit_opt_in_disabled",
        "created_at": datetime.now(UTC).isoformat(),
    }
    with open(opt_in_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(disable_record) + "\n")
    from atlas_agent.brokers.resolver import _live_submit_opt_in_status
    result = _live_submit_opt_in_status(config)
    assert result.valid is False
    assert result.code == "opt_in_disabled"


def test_opt_in_record_invalid_when_broker_mismatch(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.audit.audit_dir = tmp_path / "audit"
    _write_opt_in(tmp_path / "audit" / "live_submit_opt_in.jsonl", config, broker_id="wrong_broker")
    from atlas_agent.brokers.resolver import _live_submit_opt_in_status
    result = _live_submit_opt_in_status(config)
    assert result.valid is False
    assert result.code == "opt_in_broker_mismatch"


def test_opt_in_record_invalid_when_config_changed(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.audit.audit_dir = tmp_path / "audit"
    _write_opt_in(tmp_path / "audit" / "live_submit_opt_in.jsonl", config)
    # Change config after opt-in
    config.risk.live_submit_max_order_notional = 999.0
    from atlas_agent.brokers.resolver import _live_submit_opt_in_status
    result = _live_submit_opt_in_status(config)
    assert result.valid is False
    assert result.code == "opt_in_config_changed"


def test_opt_in_record_invalid_when_expired(tmp_path: Path) -> None:
    config = _make_all_valid_config()
    config.audit.audit_dir = tmp_path / "audit"
    past = datetime.now(UTC) - timedelta(hours=25)
    _write_opt_in(tmp_path / "audit" / "live_submit_opt_in.jsonl", config, created_at=past.isoformat())
    from atlas_agent.brokers.resolver import _live_submit_opt_in_status
    result = _live_submit_opt_in_status(config)
    assert result.valid is False
    assert result.code == "opt_in_expired"
