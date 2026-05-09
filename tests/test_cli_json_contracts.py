from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.events import EventLogger, generate_run_id


def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def _assert_json_envelope(output: str) -> dict:
    parsed = json.loads(output)
    assert isinstance(parsed, dict)
    assert parsed["ok"] is True
    assert isinstance(parsed["command"], str)
    assert isinstance(parsed["generated_at"], str)
    assert "data" in parsed
    return parsed


@pytest.mark.parametrize(
    "argv",
    [
        ["agent", "status", "--json"],
        ["agent", "plan", "--json"],
        ["events", "list", "--json"],
        ["portfolio", "show", "--json"],
        ["skills", "list", "--json"],
        ["memory", "search", "risk", "--json"],
        ["memory", "doctor", "--json"],
    ],
)
def test_json_contract_commands_emit_single_parseable_json_object(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    (config.memory_dir / "trade_journal.md").write_text("# Journal\n\nrisk note\n", encoding="utf-8")
    skills_dir = config.memory_dir.parent / "skills" / "proposed"
    skills_dir.mkdir(parents=True, exist_ok=True)

    logger = EventLogger(config.events_dir)
    logger.write(
        "agent_started",
        run_id=generate_run_id(),
        command="atlas test",
        mode="paper",
        payload={"source": "test"},
    )

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(argv) == 0

    output = capsys.readouterr().out.strip()
    payload = _assert_json_envelope(output)
    assert payload["command"].startswith("atlas")
