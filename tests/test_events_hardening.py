from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from atlas_agent.cli import main, run_once
from atlas_agent.config import AtlasConfig, MarketConfig
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
        "market": MarketConfig(symbol="DEMO-SYMBOL"),
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


def test_event_logger_final_pass_redacts_auth_headers_and_secret_tokens(tmp_path: Path) -> None:
    logger = EventLogger(tmp_path / "events")
    raw_value = "Bearer demoSuperSecretToken1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    auth_header = "Authorization: demoAuthorizationToken1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    logger.write(
        "agent_started",
        run_id=generate_run_id(),
        command="atlas test",
        mode="paper",
        payload={
            "OPENAI_COMPATIBLE_API_KEY": "demo-openai-credential-1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "note": f"{raw_value} {auth_header}",
        },
    )

    event_file = sorted((tmp_path / "events").glob("*.jsonl"))[-1]
    content = event_file.read_text(encoding="utf-8")
    assert "demoSuperSecretToken" not in content
    assert "demoAuthorizationToken" not in content
    assert "demo-openai-credential" not in content
    parsed = json.loads(content.strip())
    assert parsed["payload"]["OPENAI_COMPATIBLE_API_KEY"] == "[REDACTED]"
    assert "[REDACTED]" in parsed["payload"]["note"]


def test_agent_run_once_writes_valid_event_schema(tmp_path: Path) -> None:
    from atlas_agent.ai.discipline import write_user_discipline

    config = _config(tmp_path)
    profile = (
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
    write_user_discipline(tmp_path, profile)
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
    from atlas_agent.ai.discipline import write_user_discipline

    profile = (
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
    write_user_discipline(tmp_path, profile)
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
