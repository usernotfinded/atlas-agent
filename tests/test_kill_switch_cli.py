# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_kill_switch_cli.py
# PURPOSE: Verifies kill switch cli behavior and regression expectations.
# DEPS:    json, pathlib, unittest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.safety import read_deadman_heartbeat
from atlas_agent.safety.totp import generate_totp


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def test_kill_switch_flatten_requires_totp_to_disable(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config = _config(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["kill-switch", "enable", "--mode", "flatten", "--reason", "drill"]) == 0

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["kill-switch", "disable"]) == 2
    output = capsys.readouterr().out
    assert "2FA secret missing" in output

    secret = "JBSWY3DPEHPK3PXP"
    monkeypatch.setenv("ATLAS_TOTP_SECRET", secret)
    code = generate_totp(secret)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["kill-switch", "disable", "--totp", code]) == 0
    output = capsys.readouterr().out
    assert "Kill switch disabled" in output


def test_kill_switch_status_prints_mode_and_actor(
    tmp_path: Path,
    capsys,
) -> None:
    config = _config(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["kill-switch", "enable", "--mode", "cancel", "--reason", "ops"]) == 0
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["kill-switch", "status"]) == 0
    output = capsys.readouterr().out
    assert "enabled=True" in output
    assert "mode=cancel" in output
    assert "actor=cli" in output


def test_heartbeat_command_writes_deadman_heartbeat_file(
    tmp_path: Path,
    capsys,
) -> None:
    config = _config(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(
            ["heartbeat", "--source", "cli-test", "--actor", "user:1"]
        ) == 0
    output = capsys.readouterr().out
    assert "Heartbeat recorded:" in output
    record = read_deadman_heartbeat(config.memory_dir / "deadman_heartbeat.json")
    assert record is not None
    assert record.source == "cli-test"
    assert record.actor == "user:1"


def test_telegram_kill_and_resume_commands_with_totp(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config = _config(tmp_path)
    secret = "JBSWY3DPEHPK3PXP"
    monkeypatch.setenv("ATLAS_TOTP_SECRET", secret)
    code = generate_totp(secret)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["telegram", "kill", "--mode", "flatten", "--reason", "remote"]) == 0
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["telegram", "resume", "--totp", code, "--reason", "ok"]) == 0

    output = capsys.readouterr().out
    assert "Telegram /kill applied" in output
    assert "Telegram /resume applied" in output


def test_kill_switch_cli_writes_audit_transition_records(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["kill-switch", "enable", "--mode", "cancel", "--reason", "ops"]) == 0
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["kill-switch", "disable", "--reason", "done"]) == 0

    audit_path = config.audit_dir / "audit.jsonl"
    assert audit_path.exists()
    records = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event_types = [record.get("event_type") for record in records]
    assert "kill_switch_enabled" in event_types
    assert "kill_switch_disabled" in event_types

    enabled_record = next(
        record for record in records if record.get("event_type") == "kill_switch_enabled"
    )
    assert enabled_record["payload"]["mode"] == "cancel"
    assert enabled_record["payload"]["reason"] == "ops"
    assert enabled_record["payload"]["actor"] == "cli"
