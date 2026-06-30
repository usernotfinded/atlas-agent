from __future__ import annotations

import json
from pathlib import Path

from atlas_agent.safety.heartbeat import HeartbeatManager


def test_heartbeat_record_repeated(tmp_path: Path) -> None:
    mgr = HeartbeatManager(tmp_path / "heartbeat.json")
    mgr.record(source="test")
    mgr.record(source="test")
    payload = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert payload["source"] == "test"
    assert "timestamp" in payload
    assert not (tmp_path / "heartbeat.json.tmp").exists()


def test_heartbeat_corrupt_file_still_expired(tmp_path: Path) -> None:
    target = tmp_path / "heartbeat.json"
    target.write_text("not-json", encoding="utf-8")
    mgr = HeartbeatManager(target, timeout_seconds=1)
    assert mgr.is_expired() is True
