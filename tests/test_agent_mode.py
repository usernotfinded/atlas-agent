import pytest
from unittest.mock import patch
from atlas_agent.config import AtlasConfig, MarketConfig
from atlas_agent.cli import main
from atlas_agent.ai.discipline import write_user_discipline

GOOD_PROFILE = (
    "# Profile\n\n"
    "## Decision temperament\n\nCautious.\n\n"
    "## Reasoning style\n\nStep-by-step.\n\n"
    "## Communication style\n\nConcise.\n\n"
    "## Risk posture\n\nConservative.\n\n"
    "## Uncertainty handling\n\nExplicit.\n\n"
    "## No-trade bias\n\nDefault to hold.\n\n"
    "## Forbidden overrides\n\n"
    "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
    "audit logging, broker sync checks, reference price requirements, or live-trading safeguards.\n"
)

@pytest.fixture
def base_config(tmp_path):
    config = AtlasConfig(
        memory_dir=tmp_path / "memory",
        pending_orders_dir=tmp_path / "pending_orders",
        audit_dir=tmp_path / "audit",
        reports_dir=tmp_path / "reports",
        data_path=tmp_path / "data",
        market=MarketConfig(symbol="TEST-SYMBOL"),
    )
    config.ensure_dirs()
    return config

def test_agent_status_command(base_config, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "paper")
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=base_config):
        ret = main(["agent", "status"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Atlas Agent Status" in captured.out
    assert "Trading Mode: paper" in captured.out

def test_agent_plan_command(base_config, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "paper")
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=base_config):
        ret = main(["agent", "plan"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Atlas Agent Plan" in captured.out

def test_agent_run_paper_mode(base_config, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "paper")
    write_user_discipline(base_config.memory_dir.parent, GOOD_PROFILE)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=base_config):
        with patch("atlas_agent.agent.runner.MarketSessionDetector.get_state", return_value="closed"):
            ret = main(["agent", "run", "--mode", "paper"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "agent run paper:" in captured.out

def test_agent_run_without_discipline_is_blocked(base_config, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "paper")
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=base_config):
        with pytest.raises(SystemExit) as exc_info:
            main(["agent", "run", "--mode", "paper"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Atlas Discipline Profile is not configured" in captured.err

def test_agent_run_auto_open_market(base_config, monkeypatch, capsys):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    write_user_discipline(base_config.memory_dir.parent, GOOD_PROFILE)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=base_config):
        with patch("atlas_agent.agent.runner.MarketSessionDetector.get_state", return_value="open"):
            from unittest.mock import MagicMock
            mock_result = MagicMock()
            mock_result.name = "market_open"
            mock_result.mode = "live"
            mock_result.status = "complete"
            mock_result.report_path = "dummy"
            mock_result.order_status = "filled"
            mock_result.notification_status = "none"
            mock_result.git_status = "none"
            mock_result.lock_status = None
            mock_result.model_status = None
            with patch("atlas_agent.agent.runner.run_open_market_cycle", return_value=mock_result):
                ret = main(["agent", "run", "--mode", "auto"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "agent run auto: complete" in captured.out

def test_agent_run_auto_unknown_market(base_config, monkeypatch, capsys):
    write_user_discipline(base_config.memory_dir.parent, GOOD_PROFILE)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=base_config):
        with patch("atlas_agent.agent.runner.MarketSessionDetector.get_state", return_value="unknown"):
            from unittest.mock import MagicMock
            mock_result = MagicMock()
            mock_result.name = "pre_market"
            mock_result.mode = "paper"
            mock_result.status = "complete"
            mock_result.report_path = "dummy"
            mock_result.order_status = "filled"
            mock_result.notification_status = "none"
            mock_result.git_status = "none"
            mock_result.lock_status = None
            mock_result.model_status = None
            with patch("atlas_agent.agent.runner.run_closed_market_cycle", return_value=mock_result):
                ret = main(["agent", "run", "--mode", "auto"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "agent run auto: complete" in captured.out
