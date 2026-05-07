from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.events import EventLogger


def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def test_workspace_guard_blocks_bare_atlas_without_workspace_or_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(outside)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ATLAS_WORKSPACE", raising=False)

    assert main([]) == 2
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "Atlas Agent needs a workspace before it can run." in output
    assert not (outside / "memory").exists()
    assert not (outside / "events").exists()


def test_workspace_guard_allows_patched_config_context_for_required_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(outside)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ATLAS_WORKSPACE", raising=False)

    config = _config(tmp_path / "workspace")
    config.ensure_dirs()
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["agent", "status", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["command"] == "atlas agent status"


def test_events_doctor_runs_with_patched_config_even_outside_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(outside)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ATLAS_WORKSPACE", raising=False)

    config = _config(tmp_path / "workspace")
    config.ensure_dirs()
    logger = EventLogger(config.events_dir)
    logger.write(
        "agent_started",
        run_id="run-1",
        command="atlas test",
        mode="paper",
        payload={"source": "test"},
    )
    bad = config.events_dir / "2026-01-01.jsonl"
    bad.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "event_type": "unknown_type",
                "run_id": "run-bad",
                "command": "atlas test",
                "mode": "paper",
                "payload": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["events", "doctor"]) == 2

    output = capsys.readouterr().out
    assert "unknown event_type" in output
