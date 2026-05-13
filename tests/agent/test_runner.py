from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

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


def test_run_agent_live_mode_returns_sync_deferred_error(live_config: AtlasConfig) -> None:
    env = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret"}
    with patch.dict(os.environ, env, clear=False):
        with patch("atlas_agent.agent.runner.get_provider_from_runtime_config") as mock_provider:
            mock_provider.return_value = object()
            result = run_agent(mode="live", config=live_config, use_loop=True, continuous=False)

    assert isinstance(result, AgentResult)
    assert result.status == "error"
    assert any("live agent runtime sync is deferred" in e for e in result.errors)
    assert result.diagnostics is not None
    assert result.diagnostics.get("broker_status", {}).get("can_sync") is True
    assert result.diagnostics.get("broker_status", {}).get("can_submit") is False
