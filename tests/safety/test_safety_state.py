# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_safety_state.py
# PURPOSE: Verifies safety state behavior and regression expectations.
# DEPS:    json, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path

from atlas_agent.safety.models import KillSwitchStatus
from atlas_agent.safety.state import KillSwitchState


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_state_save_load_roundtrip(tmp_path: Path) -> None:
    mgr = KillSwitchState(tmp_path / "state.json")
    mgr.save("soft_pause", "test reason", actor="user:1")
    status = mgr.load()
    assert status.mode == "soft_pause"
    assert status.reason == "test reason"
    assert status.actor == "user:1"


def test_state_save_repeated(tmp_path: Path) -> None:
    mgr = KillSwitchState(tmp_path / "state.json")
    mgr.save("normal", "first")
    mgr.save("locked_down", "second")
    payload = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert payload["mode"] == "locked_down"
    assert payload["reason"] == "second"


def test_state_corrupt_load_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("not-json", encoding="utf-8")
    mgr = KillSwitchState(target)
    status = mgr.load()
    assert status.mode == "locked_down"


def test_state_serialization_matches_pydantic_model_dump_json() -> None:
    status = KillSwitchStatus(
        mode="soft_pause",
        reason="test",
        actor="user:1",
        updated_at="2026-06-30T08:47:12+00:00",
    )
    pydantic_output = status.model_dump_json(indent=2)
    helper_output = json.dumps(status.model_dump(), indent=2)
    assert json.loads(pydantic_output) == json.loads(helper_output)
    assert pydantic_output == helper_output
