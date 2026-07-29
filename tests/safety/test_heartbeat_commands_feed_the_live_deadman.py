# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_heartbeat_commands_feed_the_live_deadman.py
# PURPOSE: Pins which heartbeat commands actually reach the deadman that blocks.
# DEPS:    json, datetime, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Three commands record a heartbeat. One of them reaches the deadman.

Atlas has two heartbeat files, and they are not the same signal:

- `.atlas/safety/heartbeat.json`, via `HeartbeatManager`. Read by
  `AdvancedKillSwitch.evaluate()`, which `agent/loop.py` calls on every tool
  call. **This is the deadman that stops a hung agent.** Written by `atlas kill
  heartbeat` and by `agent/runner.py`.
- `memory/deadman_heartbeat.json`, via `deadman_heartbeat_path`. Read only by
  `DeadmanSwitch.tick`, an async supervisor with market-session awareness,
  notifiers and escalation — and `DeadmanSwitch` is never constructed anywhere
  in `src/`. Written by `atlas heartbeat` and `atlas telegram heartbeat`.

So the two operator-facing keep-alive commands feed a supervisor that does not
run. Both print the path and exit 0, which is why nothing surfaced it:

    $ atlas heartbeat
    Heartbeat recorded: memory/deadman_heartbeat.json     # deadman still blocked
    $ atlas kill heartbeat
    Heartbeat recorded.                                   # deadman cleared

This direction is fail-closed — the agent stops when it should keep running,
rather than running when it should stop — so it is a false-confidence and
availability problem, not an open live path. That is the opposite of the
kill-switch split found alongside it, where the runbook's own command left live
submit open.

The two failing cases are `xfail(strict=True)` rather than deleted. They state
behaviour an operator already believes they have, and if the wiring is ever
fixed the XPASS forces the marker off rather than letting the case rot.

Whether it *should* be fixed by simply writing both files is a real question and
not one to settle here: a remote `/heartbeat` from a phone that silences an
agent-liveness deadman lets a human mask a hung agent. Recorded in
`docs/development/safety-invariant-audit-followups.md`.
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

@pytest.fixture
def stale_deadman(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A workspace whose live deadman has already tripped.

    Seeded and then backdated rather than left absent, because an absent
    heartbeat reads as fresh — a case built on a missing file would pass without
    any command doing anything.
    """
    from atlas_agent.cli import main
    from atlas_agent.safety.kill_switch import AdvancedKillSwitch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])

    safety_dir = tmp_path / ".atlas" / "safety"
    safety_dir.mkdir(parents=True, exist_ok=True)
    kill_switch = AdvancedKillSwitch(
        state_path=safety_dir / "kill_switch.json",
        heartbeat_path=safety_dir / "heartbeat.json",
    )
    kill_switch.heartbeat_manager.record(source="seed")

    beat = safety_dir / "heartbeat.json"
    payload = json.loads(beat.read_text(encoding="utf-8"))
    key = "timestamp" if "timestamp" in payload else next(iter(payload))
    payload[key] = (datetime.now(UTC) - timedelta(hours=6)).isoformat()
    beat.write_text(json.dumps(payload), encoding="utf-8")

    # The premise. Without it the assertions below prove nothing.
    assert kill_switch.evaluate().allowed is False
    return kill_switch


def test_atlas_kill_heartbeat_clears_the_deadman(stale_deadman) -> None:
    """The one command that works, and the control for the two that do not."""
    from atlas_agent.cli import main

    assert main(["kill", "heartbeat"]) == 0

    assert stale_deadman.evaluate().allowed is True


@pytest.mark.xfail(
    strict=True,
    reason="`atlas heartbeat` writes memory/deadman_heartbeat.json, which no "
    "running decision path reads; DeadmanSwitch is never constructed in src/",
)
def test_atlas_heartbeat_clears_the_deadman(stale_deadman) -> None:
    """An operator keeping the agent alive from the terminal."""
    from atlas_agent.cli import main

    assert main(["heartbeat"]) == 0

    assert stale_deadman.evaluate().allowed is True


@pytest.mark.xfail(
    strict=True,
    reason="`atlas telegram heartbeat` writes memory/deadman_heartbeat.json, "
    "which no running decision path reads",
)
def test_atlas_telegram_heartbeat_clears_the_deadman(stale_deadman) -> None:
    """The same, from a phone — the case where nobody can check the file."""
    from atlas_agent.cli import main

    assert main(["telegram", "heartbeat"]) == 0

    assert stale_deadman.evaluate().allowed is True


def test_the_unwired_supervisor_is_still_the_only_reader_of_its_file() -> None:
    """Pins why the two cases above fail, so a fix is not mistaken for a flake.

    If `DeadmanSwitch` ever gains a constructor call in `src/`, the commands
    above may start mattering, and this list is where someone should look first.
    """
    import ast

    src_root = Path(__file__).resolve().parents[2] / "src" / "atlas_agent"
    constructors: set[str] = set()
    for path in sorted(src_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "DeadmanSwitch":
                constructors.add(path.relative_to(src_root).as_posix())

    assert constructors == set()
