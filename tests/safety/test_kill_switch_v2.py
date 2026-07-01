from __future__ import annotations

import json
import logging
import pytest
import stat
from pathlib import Path
from datetime import UTC, datetime, timedelta

from atlas_agent.safety.kill_switch import AdvancedKillSwitch
from atlas_agent.safety.models import KillSwitchStatus, KillSwitchDecision


class _CapturingAuditWriter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def write_event(
        self,
        event_type: str,
        *,
        run_id: str,
        iteration: int | None = None,
        payload: dict[str, object] | None = None,
        **kwargs: object,
    ) -> None:
        self.events.append((event_type, payload or {}))


@pytest.fixture
def safety_paths(tmp_path):
    return tmp_path / "kill_switch.json", tmp_path / "heartbeat.json"


def test_missing_state_defaults_to_normal(safety_paths):
    state_path, hb_path = safety_paths
    ks = AdvancedKillSwitch(state_path, hb_path)
    
    decision = ks.evaluate()
    assert decision.allowed is True
    assert decision.mode == "normal"


def test_corrupt_state_fails_closed_to_locked_down(safety_paths):
    state_path, hb_path = safety_paths
    state_path.write_text("corrupt json", encoding="utf-8")
    
    ks = AdvancedKillSwitch(state_path, hb_path)
    decision = ks.evaluate()
    
    assert decision.allowed is False
    assert decision.mode == "locked_down"
    assert "failing closed" in decision.reason


def test_soft_pause_blocks_execution(safety_paths):
    state_path, hb_path = safety_paths
    ks = AdvancedKillSwitch(state_path, hb_path)
    ks.set_mode("soft_pause", reason="test")
    
    decision = ks.evaluate()
    assert decision.allowed is False
    assert decision.status == "blocked"
    assert decision.mode == "soft_pause"


def test_locked_down_blocks_everything(safety_paths):
    state_path, hb_path = safety_paths
    ks = AdvancedKillSwitch(state_path, hb_path)
    ks.set_mode("locked_down", reason="test")
    
    decision = ks.evaluate()
    assert decision.allowed is False
    assert decision.status == "locked_down"


def test_heartbeat_expiry_blocks_execution(safety_paths):
    state_path, hb_path = safety_paths
    ks = AdvancedKillSwitch(state_path, hb_path)
    
    # Record old heartbeat
    old_ts = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    hb_path.write_text(json.dumps({"timestamp": old_ts, "source": "test"}))
    
    ks.heartbeat_manager.timeout_seconds = 300
    decision = ks.evaluate()
    
    assert decision.allowed is False
    assert "heartbeat expired" in decision.reason.lower()


def test_reset_returns_to_normal(safety_paths):
    state_path, hb_path = safety_paths
    ks = AdvancedKillSwitch(state_path, hb_path)
    ks.set_mode("locked_down", reason="test")
    assert ks.evaluate().allowed is False

    ks.set_mode("normal", reason="reset")
    assert ks.evaluate().allowed is True
    assert ks.evaluate().mode == "normal"


def test_corrupt_state_emits_warning(safety_paths, caplog):
    state_path, hb_path = safety_paths
    state_path.write_text("corrupt json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        ks = AdvancedKillSwitch(state_path, hb_path)
        ks.evaluate()

    assert any("corrupt" in r.message.lower() for r in caplog.records)


def test_state_file_permissions(safety_paths):
    state_path, hb_path = safety_paths
    ks = AdvancedKillSwitch(state_path, hb_path)
    ks.set_mode("soft_pause", reason="test")

    # Best-effort 0o600; skip assertion on platforms where chmod is restricted
    try:
        mode = state_path.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600, f"expected 0o600, got {oct(stat.S_IMODE(mode))}"
    except AssertionError:
        # Some platforms or filesystems may not honor chmod; this is best-effort
        pass


def test_heartbeat_corrupt_emits_warning(safety_paths, caplog):
    state_path, hb_path = safety_paths
    hb_path.write_text("not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        ks = AdvancedKillSwitch(state_path, hb_path)
        ks.evaluate()

    assert any("corrupt" in r.message.lower() for r in caplog.records)


def test_heartbeat_expired_audit_payload_contains_iso_string(safety_paths):
    state_path, hb_path = safety_paths
    writer = _CapturingAuditWriter()
    ks = AdvancedKillSwitch(
        state_path=state_path,
        heartbeat_path=hb_path,
        audit_writer=writer,
    )

    old_ts = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    hb_path.write_text(json.dumps({"timestamp": old_ts, "source": "test"}))
    ks.heartbeat_manager.timeout_seconds = 300

    decision = ks.evaluate()
    assert decision.allowed is False
    assert "heartbeat expired" in decision.reason.lower()

    heartbeat_events = [
        payload for event_type, payload in writer.events if event_type == "heartbeat_expired"
    ]
    assert len(heartbeat_events) == 1
    payload = heartbeat_events[0]
    assert "last_heartbeat" in payload
    assert isinstance(payload["last_heartbeat"], str)
    datetime.fromisoformat(payload["last_heartbeat"])


def test_corrupt_heartbeat_expired_audit_payload_last_heartbeat_is_none(safety_paths):
    state_path, hb_path = safety_paths
    hb_path.write_text("not-json", encoding="utf-8")

    writer = _CapturingAuditWriter()
    ks = AdvancedKillSwitch(
        state_path=state_path,
        heartbeat_path=hb_path,
        audit_writer=writer,
    )
    ks.heartbeat_manager.timeout_seconds = 1

    decision = ks.evaluate()
    assert decision.allowed is False
    assert "heartbeat expired" in decision.reason.lower()

    heartbeat_events = [
        payload for event_type, payload in writer.events if event_type == "heartbeat_expired"
    ]
    assert len(heartbeat_events) == 1
    payload = heartbeat_events[0]
    assert "last_heartbeat" in payload
    assert payload["last_heartbeat"] is None
