# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_heartbeat.py
# PURPOSE: Verifies heartbeat behavior and regression expectations.
# DEPS:    json, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path

from atlas_agent.safety.heartbeat import HeartbeatManager


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


def test_heartbeat_missing_file_is_not_expired(tmp_path: Path) -> None:
    """A heartbeat that was never written reads as fresh, unlike a corrupt one.

    This asymmetry is deliberate — a first run has no dead agent to detect — but
    it is the one case where an unreadable heartbeat does not fail closed, so it
    is pinned here rather than left implicit.
    """
    mgr = HeartbeatManager(tmp_path / "heartbeat.json", timeout_seconds=1)
    assert mgr.is_expired() is False
    assert mgr.last_heartbeat() is None


def test_heartbeat_deleted_after_recording_is_not_expired(tmp_path: Path) -> None:
    """Deleting a recorded heartbeat reads the same as never having one.

    `HeartbeatManager` cannot tell "never started" from "started and lost its
    state", so a deleted file disarms the expiry check while a corrupt file
    trips it. On the order path the runner records a heartbeat at the start of
    every cycle, which is what keeps this from being reachable there.
    """
    target = tmp_path / "heartbeat.json"
    mgr = HeartbeatManager(target, timeout_seconds=1)
    mgr.record(source="test")
    assert target.exists()

    target.unlink()

    assert mgr.is_expired() is False
