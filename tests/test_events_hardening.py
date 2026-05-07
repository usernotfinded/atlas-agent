from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from atlas_agent.cli import main, run_once
from atlas_agent.config import AtlasConfig
from atlas_agent.events import EventLogger, generate_run_id
from atlas_agent.events.schema import KNOWN_EVENT_TYPES, REQUIRED_EVENT_FIELDS


def _config(tmp_path: Path, **overrides) -> AtlasConfig:
    values = {
        "memory_dir": tmp_path / "memory",
        "audit_dir": tmp_path / "audit",
        "pending_orders_dir": tmp_path / "pending_orders",
        "reports_dir": tmp_path / "reports",
        "events_dir": tmp_path / "events",
        "data_path": tmp_path / "data" / "ohlcv.csv",
    }
    values.update(overrides)
    return AtlasConfig(**values)


def _read_events(events_dir: Path) -> list[dict]:
    files = sorted(events_dir.glob("*.jsonl"))
    assert files
    return [
        json.loads(line)
        for line in files[-1].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_event_logger_redacts_secret_values(tmp_path: Path) -> None:
    logger = EventLogger(tmp_path / "events")
    logger.write(
        "agent_started",
        run_id=generate_run_id(),
        command="atlas test",
        mode="paper",
        payload={"ALPACA_API_KEY": "secret", "safe": "ok"},
    )
    text = (tmp_path / "events").glob("*.jsonl")
    event_file = sorted(text)[-1]
    content = event_file.read_text(encoding="utf-8")
    assert "secret" not in content
    parsed = json.loads(content.strip())
    assert parsed["payload"]["ALPACA_API_KEY"] == "[REDACTED]"


def test_agent_run_once_writes_valid_event_schema(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["run-once", "--mode", "paper"]) == 0

    events = _read_events(config.events_dir)
    assert events
    event_types = {event["event_type"] for event in events}
    assert "agent_started" in event_types
    assert "agent_completed" in event_types
    for event in events:
        for field in REQUIRED_EVENT_FIELDS:
            assert field in event
        assert event["event_type"] in KNOWN_EVENT_TYPES


def test_risk_rejection_writes_risk_event(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        max_order_notional=1.0,
        max_position_size=1.0,
        minimum_confidence=1.1,
    )
    logger = EventLogger(config.events_dir)
    run_id = generate_run_id()
    result = run_once(
        mode="paper",
        config=config,
        event_logger=logger,
        run_id=run_id,
        command="atlas test run-once",
    )

    assert result.status == "rejected"
    events = _read_events(config.events_dir)
    event_types = [event["event_type"] for event in events]
    assert "risk_rejected" in event_types
    assert "order_rejected" in event_types
