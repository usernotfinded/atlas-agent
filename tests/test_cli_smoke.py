from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import json

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
        workspace_root=tmp_path,
    )


def test_cli_dashboard_json(tmp_path: Path, capsys, monkeypatch):
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["dashboard", "--json"]) == 0
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "provider_summary" in data


def test_cli_broker_sync_json(tmp_path: Path, capsys, monkeypatch):
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["broker", "sync", "--json"]) == 0
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "status" in data
    assert "positions" in data


def test_cli_broker_sync_json_sanitizes_broker_errors(tmp_path: Path, capsys, monkeypatch):
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)

    def _raise_secret(*_args, **_kwargs):
        raise RuntimeError("api_key=raw-secret token=raw-secret")

    monkeypatch.setattr("atlas_agent.brokers.paper.PaperBrokerAdapter.get_positions", _raise_secret)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["broker", "sync", "--json"]) == 0

    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["status"] == "partial"
    assert "raw-secret" not in out
    assert data["errors"] == [
        "sync_positions failed [broker_operation_failed]: broker operation failed"
    ]
    assert data["diagnostics"]["broker_errors"] == [
        {
            "code": "broker_operation_failed",
            "operation": "sync_positions",
            "broker": "paper",
            "message": "broker operation failed",
        }
    ]


def test_cli_broker_sync_live_unconfigured_returns_controlled_failure(tmp_path: Path, capsys, monkeypatch):
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        code = main(["broker", "sync", "--mode", "live", "--json"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["status"] == "failed"
    assert "live broker is not configured" in data["errors"][0]
    assert data["diagnostics"]["broker_status"]["can_sync"] is False
    assert data["diagnostics"]["broker_status"]["can_submit"] is False


def test_cli_broker_sync_live_configured_returns_controlled_failure_no_paper_fallback(
    tmp_path: Path, capsys, monkeypatch
):
    config = AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
        workspace_root=tmp_path,
        broker={"provider": "binance", "enable_live_trading": True},
    )
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", "demo-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "demo-secret")
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        code = main(["broker", "sync", "--mode", "live", "--json"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["status"] == "failed"
    assert "deferred" in data["errors"][0]
    assert data["diagnostics"]["broker_status"]["can_sync"] is False
    assert data["diagnostics"]["broker_status"]["can_submit"] is False
    assert data["diagnostics"]["broker_status"]["broker_id"] == "binance"
    # Must not silently use paper fallback
    assert data["positions"] == []
    assert "demo-key" not in out
    assert "demo-secret" not in out


def test_cli_broker_sync_live_missing_credentials_returns_controlled_failure(
    tmp_path: Path, capsys, monkeypatch
):
    config = AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
        workspace_root=tmp_path,
        broker={"provider": "alpaca", "enable_live_trading": True},
    )
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        code = main(["broker", "sync", "--mode", "live", "--json"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["status"] == "failed"
    assert "credentials are missing" in data["errors"][0]
    assert data["diagnostics"]["broker_status"]["credentials_configured"] is False


def test_cli_audit_verify_all(tmp_path: Path, capsys, monkeypatch):
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["audit", "verify", "--all"]) == 0
    out = capsys.readouterr().out.strip()
    assert "No manifests found" in out or "Verifying" in out


def test_cli_kill_status(tmp_path: Path, capsys, monkeypatch):
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["kill", "status"]) == 0
    out = capsys.readouterr().out.strip()
    assert "Kill Switch Status:" in out


def test_cli_risk_status(tmp_path: Path, capsys, monkeypatch):
    config = _config(tmp_path)
    config.ensure_dirs()
    monkeypatch.chdir(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["risk", "status"]) == 0
    out = capsys.readouterr().out.strip()
    assert "Risk Management Status:" in out
