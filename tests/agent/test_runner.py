from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from atlas_agent.agent.result import AgentResult
from atlas_agent.agent.runner import run_agent
from atlas_agent.ai.discipline import write_user_discipline
from atlas_agent.config import AtlasConfig


from atlas_agent.ai.discipline import _REQUIRED_SAFETY_SENTENCE

GOOD_PROFILE = (
    "# Profile\n\n"
    "## Decision temperament\n\nCautious.\n\n"
    "## Reasoning style\n\nStep-by-step.\n\n"
    "## Communication style\n\nConcise.\n\n"
    "## Risk posture\n\nConservative.\n\n"
    "## Uncertainty handling\n\nExplicit.\n\n"
    "## No-trade bias\n\nDefault to hold.\n\n"
    "## Forbidden overrides\n\n"
    f"{_REQUIRED_SAFETY_SENTENCE}\n"
)


@pytest.fixture
def live_config(tmp_path: Path) -> AtlasConfig:
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
        market={"symbol": "AAPL"},
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
        workspace_root=tmp_path,
    )
    config.ensure_dirs()
    write_user_discipline(tmp_path, GOOD_PROFILE)
    return config


def _fake_alpaca_request(_self, _method: str, path: str):
    if path == "/v2/account":
        return {
            "cash": "50000.00",
            "portfolio_value": "75000.00",
            "buying_power": "100000.00",
        }
    if path == "/v2/positions":
        return [
            {
                "symbol": "AAPL",
                "qty": "10",
                "avg_entry_price": "150.0",
                "current_price": "155.0",
            },
        ]
    if path == "/v2/orders?status=open":
        return [
            {
                "id": "ord-live-1",
                "symbol": "TSLA",
                "side": "buy",
                "qty": "5",
                "filled_qty": "0",
                "limit_price": "200.0",
            },
        ]
    raise ValueError(f"unexpected path: {path}")


class MockProvider:
    def complete(self, **kwargs):
        from atlas_agent.tools.spec import LLMResponse
        return LLMResponse(text="Analysis complete. No action needed.", tool_calls=[], is_final=True)

    def capabilities(self):
        from atlas_agent.tools.spec import ModelCapabilities
        return ModelCapabilities(context_window=128000, supports_native_tools=True)


# ---------------------------------------------------------------------------
# Live mode opt-in and sync consumption
# ---------------------------------------------------------------------------

def test_run_agent_live_not_enabled_fails_closed() -> None:
    tmp_path = Path("/tmp/test_runner_live_not_enabled")
    tmp_path.mkdir(exist_ok=True)
    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": False},
        market={"symbol": "AAPL"},
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
        workspace_root=tmp_path,
    )
    config.ensure_dirs()
    write_user_discipline(tmp_path, GOOD_PROFILE)

    with patch("atlas_agent.agent.runner.get_provider_from_runtime_config"):
        result = run_agent(mode="live", config=config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "Live trading is not enabled" in result.errors[0]


def test_run_agent_live_sync_success_uses_real_portfolio(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "complete"


def test_run_agent_live_sync_account_failure_fails_closed(live_config: AtlasConfig) -> None:
    def _fail_account(_self, _method, path):
        if path == "/v2/account":
            raise ConnectionError("network down")
        return _fake_alpaca_request(_self, _method, path)

    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fail_account):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config"):
                result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "sync_account_state" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["sync_account_state"]


def test_run_agent_live_sync_positions_failure_fails_closed(live_config: AtlasConfig) -> None:
    def _fail_positions(_self, _method, path):
        if path == "/v2/positions":
            raise ConnectionError("network down")
        return _fake_alpaca_request(_self, _method, path)

    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fail_positions):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config"):
                result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "sync_positions" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["sync_positions"]


def test_run_agent_live_sync_open_orders_failure_fails_closed(live_config: AtlasConfig) -> None:
    def _fail_orders(_self, _method, path):
        if path == "/v2/orders?status=open":
            raise ConnectionError("network down")
        return _fake_alpaca_request(_self, _method, path)

    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fail_orders):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config"):
                result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "sync_open_orders" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["sync_open_orders"]


def test_run_agent_live_sync_balances_failure_proceeds(live_config: AtlasConfig) -> None:
    def _fail_balances(_self, _method, path):
        if path == "/v2/account":
            return {
                "cash": "50000.00",
                "portfolio_value": "75000.00",
                "buying_power": "100000.00",
            }
        if path == "/v2/positions":
            return []
        if path == "/v2/orders?status=open":
            return []
        raise ValueError(f"unexpected path: {path}")

    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fail_balances):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "complete"


def test_run_agent_live_sync_multiple_critical_failures(live_config: AtlasConfig) -> None:
    def _fail_critical(_self, _method, path):
        if path == "/v2/account":
            raise ConnectionError("network down")
        if path == "/v2/positions":
            raise ConnectionError("network down")
        if path == "/v2/orders?status=open":
            return []
        raise ValueError(f"unexpected path: {path}")

    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fail_critical):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config"):
                result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    failed_ops = result.diagnostics.get("failed_operations", [])
    assert "sync_account_state" in failed_ops
    assert "sync_positions" in failed_ops


def test_run_agent_live_unconfigured_still_blocked(live_config: AtlasConfig) -> None:
    with patch.dict(os.environ, {}, clear=True):
        with patch("atlas_agent.agent.runner.get_provider_from_runtime_config"):
            result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert result.diagnostics is not None
    assert result.diagnostics.get("broker_status", {}).get("can_sync") is False


def test_run_agent_live_malformed_diagnostics_fails_closed(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                with patch("atlas_agent.brokers.sync.BrokerSyncService.sync") as mock_sync:
                    mock_sync.return_value = MagicMock(
                        status="partial",
                        account=MagicMock(cash=100, equity=100),
                        positions=[],
                        open_orders=[],
                        diagnostics={"broker_errors": "not-a-list"},  # malformed
                    )
                    result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "malformed diagnostics" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["malformed_broker_errors"]


def _mock_sync_result_with_errors(broker_errors):
    return MagicMock(
        status="partial",
        synced_at="2026-05-13T12:00:00Z",
        account=MagicMock(cash=100, equity=100),
        positions=[],
        open_orders=[],
        diagnostics={"broker_errors": broker_errors},
    )


def test_run_agent_live_broker_errors_list_with_non_dict_fails_closed(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                with patch("atlas_agent.brokers.sync.BrokerSyncService.sync") as mock_sync:
                    mock_sync.return_value = _mock_sync_result_with_errors(
                        ["bad-entry"]
                    )
                    result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "malformed diagnostics" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["malformed_broker_errors"]


def test_run_agent_live_broker_errors_list_dict_missing_operation_fails_closed(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                with patch("atlas_agent.brokers.sync.BrokerSyncService.sync") as mock_sync:
                    mock_sync.return_value = _mock_sync_result_with_errors(
                        [{"code": "broker_operation_failed", "broker": "alpaca", "message": "fail"}]
                    )
                    result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "malformed diagnostics" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["malformed_broker_errors"]


def test_run_agent_live_broker_errors_list_dict_missing_code_broker_message_fails_closed(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                with patch("atlas_agent.brokers.sync.BrokerSyncService.sync") as mock_sync:
                    mock_sync.return_value = _mock_sync_result_with_errors(
                        [{"operation": "sync_positions"}]
                    )
                    result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "malformed diagnostics" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["malformed_broker_errors"]


def test_run_agent_live_broker_errors_list_dict_non_string_operation_fails_closed(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                with patch("atlas_agent.brokers.sync.BrokerSyncService.sync") as mock_sync:
                    mock_sync.return_value = _mock_sync_result_with_errors(
                        [{"code": "x", "operation": 123, "broker": "alpaca", "message": "fail"}]
                    )
                    result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "malformed diagnostics" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["malformed_broker_errors"]


def test_run_agent_live_valid_broker_errors_sync_balances_only_proceeds(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                with patch("atlas_agent.brokers.sync.BrokerSyncService.sync") as mock_sync:
                    mock_sync.return_value = _mock_sync_result_with_errors(
                        [{"code": "broker_operation_failed", "operation": "sync_balances", "broker": "alpaca", "message": "timeout"}]
                    )
                    result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "complete"


def test_run_agent_live_valid_broker_errors_sync_positions_still_fails_closed(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                with patch("atlas_agent.brokers.sync.BrokerSyncService.sync") as mock_sync:
                    mock_sync.return_value = _mock_sync_result_with_errors(
                        [{"code": "broker_operation_failed", "operation": "sync_positions", "broker": "alpaca", "message": "timeout"}]
                    )
                    result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "sync_positions" in result.errors[0]
    assert result.diagnostics.get("failed_operations") == ["sync_positions"]


def test_run_agent_live_malformed_no_private_values_leaked(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.brokers.alpaca.AlpacaBrokerAdapter._request", _fake_alpaca_request):
            with patch("atlas_agent.agent.runner.get_provider_from_runtime_config", return_value=MockProvider()):
                with patch("atlas_agent.brokers.sync.BrokerSyncService.sync") as mock_sync:
                    mock_sync.return_value = _mock_sync_result_with_errors(
                        [{"secret_api_key": "sk-live-abc123", "password": "hunter2"}]
                    )
                    result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert "malformed diagnostics" in result.errors[0]
    error_text = " ".join(result.errors)
    diagnostics_text = str(result.diagnostics)
    assert "sk-live-abc123" not in error_text
    assert "hunter2" not in error_text
    assert "sk-live-abc123" not in diagnostics_text
    assert "hunter2" not in diagnostics_text
