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
