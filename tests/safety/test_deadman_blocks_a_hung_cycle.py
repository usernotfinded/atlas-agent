# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_deadman_blocks_a_hung_cycle.py
# PURPOSE: Pins the composition that makes the deadman work — recorded by the
#         runner, evaluated by the loop it drives.
# DEPS:    datetime, json, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Active operator oversight, which bounded live autonomy requires.

The deadman only works as a composition, and the two halves live in different
modules. `agent/runner.py` records a heartbeat at the start of each cycle and
never calls `evaluate`; `agent/loop.py` calls `evaluate` on every tool call and
never records. Reading either alone suggests the mechanism is broken. Together
they are the design: the cycle refreshes the heartbeat, and if a cycle hangs past
the timeout the loop's next evaluation blocks.

Nothing tested the composition, and it is fragile in a specific way. An absent
heartbeat reads as *fresh*, not expired — a deliberate asymmetry so a first run
has no dead agent to detect, documented in `docs/kill-switch.md`. That means the
deadman is inert on any path that evaluates without ever recording: there is no
stale file to age out. So the safety of this mechanism rests on the recording and
the evaluation staying wired to each other, which is exactly the kind of thing a
refactor separates without noticing.

Any future path that evaluates the kill switch under autonomy has to record a
heartbeat too, or it inherits a deadman that cannot fire.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _kill_switch(tmp_path: Path):
    from atlas_agent.safety.kill_switch import AdvancedKillSwitch

    return AdvancedKillSwitch(
        state_path=tmp_path / "kill_switch.json",
        heartbeat_path=tmp_path / "heartbeat.json",
    )


def _age_the_heartbeat(tmp_path: Path, *, hours: int) -> None:
    """Backdate the recorded heartbeat, as a hung cycle would leave it."""
    path = tmp_path / "heartbeat.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    stamp_key = "timestamp" if "timestamp" in payload else next(iter(payload))
    payload[stamp_key] = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_a_fresh_heartbeat_lets_the_loop_run(tmp_path: Path) -> None:
    """The baseline. Without it, a deadman that blocks everything would pass."""
    kill_switch = _kill_switch(tmp_path)
    kill_switch.heartbeat_manager.record(source="test")

    assert kill_switch.evaluate().allowed is True


def test_a_hung_cycle_is_blocked(tmp_path: Path) -> None:
    """The property the whole mechanism exists for."""
    kill_switch = _kill_switch(tmp_path)
    kill_switch.heartbeat_manager.record(source="test")
    _age_the_heartbeat(tmp_path, hours=6)

    decision = kill_switch.evaluate()

    assert decision.allowed is False, (
        "a cycle whose heartbeat went stale was still allowed to act. The deadman "
        "is the only thing that notices an agent that stopped making progress."
    )
    assert decision.status == "blocked"


def test_the_runner_records_where_the_loop_evaluates(tmp_path: Path) -> None:
    """The wiring the two halves depend on, asserted structurally.

    `runner.py` records the heartbeat and hands its kill switch to the loop, which
    evaluates it. Separating those — recording on one switch and evaluating
    another — would leave the deadman with nothing to age out, and every
    behavioural test above would still pass, because each builds its own switch.
    """
    import ast

    src_root = Path(__file__).resolve().parents[2] / "src" / "atlas_agent" / "agent"
    runner = (src_root / "runner.py").read_text(encoding="utf-8")

    assert "heartbeat_manager.record(" in runner, (
        "agent/runner.py no longer records a heartbeat. The loop it drives "
        "evaluates one, and an absent heartbeat reads as fresh, so the deadman "
        "would never fire."
    )

    tree = ast.parse(runner)
    passes_switch = any(
        isinstance(node, ast.keyword) and node.arg == "kill_switch"
        for node in ast.walk(tree)
    )
    assert passes_switch, (
        "agent/runner.py no longer hands its kill switch to the loop, so the "
        "switch it records a heartbeat on is not the switch being evaluated."
    )
