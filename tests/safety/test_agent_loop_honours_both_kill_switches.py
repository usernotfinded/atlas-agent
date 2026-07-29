# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_agent_loop_honours_both_kill_switches.py
# PURPOSE: Pins that arming either kill switch stops the autonomous loop.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""The operator said stop. The loop has to stop, whichever stop they reached for.

`agent/loop.py` re-evaluates the kill switch on every tool call, and the switch
it evaluates is `AdvancedKillSwitch` — the `.atlas/safety/` one. It never
consulted `KillSwitchController`, the `memory/` one behind `atlas kill-switch`
and `atlas telegram kill`. So:

    operator armed kill-switch flatten : True
    loop allowed after arming          : True

The strongest mode on that surface, and the loop kept going.

This is the mirror of the resolver defect fixed alongside it, and the pair is
the whole argument for reading both everywhere: each subsystem was wired to one
switch, and which one differed by file. Live submit is blocked by the resolver
now, so the loop could not have placed a live order — but it kept iterating,
kept spending model calls, and never built the cancel or flatten plan its own
escalation path exists to produce.

Direction matters here and it is worth being precise. Consulting a second switch
can only ever turn `allowed=True` into `allowed=False`; there is no input that
makes the system stop less readily. That is what separates this from the
escalation gap recorded in
[safety-invariant-audit-followups.md](../../docs/development/safety-invariant-audit-followups.md),
which would have opened a path and is left for external review.

A failure here means an operator can arm a kill switch and watch the agent keep
trading.
"""

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

#: Controller mode -> the decision the loop must receive.
#:
#: The statuses are the ones `agent/loop.py` branches on: it builds a safety plan
#: for `cancel_required` and `flatten_required`, and merely refuses otherwise. A
#: controller `flatten` that arrived as a bare `blocked` would stop the loop but
#: silently drop the flatten the operator asked for.
CONTROLLER_MODE_TO_STATUS = {
    "soft": "blocked",
    "cancel": "cancel_required",
    "flatten": "flatten_required",
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def wired_switches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Both switches, built the way `agent/runner.py` builds them."""
    from atlas_agent.cli import main
    from atlas_agent.config.builder import get_effective_config
    from atlas_agent.config.paths import get_safety_dir_for
    from atlas_agent.safety.kill_switch import AdvancedKillSwitch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    config = get_effective_config()

    safety_dir = get_safety_dir_for(config)
    safety_dir.mkdir(parents=True, exist_ok=True)
    advanced = AdvancedKillSwitch(
        state_path=safety_dir / "kill_switch.json",
        heartbeat_path=safety_dir / "heartbeat.json",
        companion_state_path=Path(config.memory_dir) / "kill_switch_state.json",
    )
    # The runner records one at the start of every cycle. Without it the deadman
    # fires and every case below would pass for that reason instead.
    advanced.heartbeat_manager.record(source="agent_runner")
    return config, advanced


def _controller(config):
    from atlas_agent.cli_safety import _kill_switch_controller

    return _kill_switch_controller(config)


def test_the_loop_runs_when_neither_switch_is_armed(wired_switches) -> None:
    """The negative control. Without it a gate that always refused would pass
    every case below."""
    _config, advanced = wired_switches

    assert advanced.evaluate().allowed is True


@pytest.mark.parametrize("mode,expected_status", sorted(CONTROLLER_MODE_TO_STATUS.items()))
def test_arming_the_controller_stops_the_loop(
    wired_switches, mode: str, expected_status: str
) -> None:
    """`atlas kill-switch enable --mode X` has to reach the loop."""
    config, advanced = wired_switches

    _controller(config).enable(mode=mode, reason="emergency", actor="cli", broker=None)
    decision = advanced.evaluate()

    assert decision.allowed is False
    assert decision.status == expected_status


def test_arming_the_advanced_switch_still_stops_the_loop(wired_switches) -> None:
    """Reading a second switch must not become a replacement for the first."""
    _config, advanced = wired_switches

    advanced.set_mode("soft_pause", reason="runbook", actor="user")

    assert advanced.evaluate().allowed is False


def test_the_advanced_switch_wins_when_both_are_armed(wired_switches) -> None:
    """Severity is not averaged.

    An advanced `locked_down` outranks anything the controller says, and must not
    be softened into a milder status by consulting a second source.
    """
    config, advanced = wired_switches

    advanced.set_mode("locked_down", reason="post-flatten", actor="user")
    _controller(config).enable(mode="soft", reason="emergency", actor="cli", broker=None)

    decision = advanced.evaluate()

    assert decision.allowed is False
    assert decision.mode == "locked_down"


def test_an_unreadable_controller_state_stops_the_loop(wired_switches) -> None:
    """Someone wrote that file. Not being able to read it is not permission.

    The block comes from `KillSwitchController.status()` failing closed on its
    own — it answers `enabled=True, mode="soft"` for an unparseable file — rather
    than from any handling on this side. Asserted anyway: the property the loop
    depends on is the outcome, and it should not quietly change if that
    controller's corrupt-state doctrine ever does.
    """
    config, advanced = wired_switches

    state_path = Path(config.memory_dir) / "kill_switch_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{ not json", encoding="utf-8")

    assert advanced.evaluate().allowed is False


def test_every_construction_in_src_passes_the_companion_path() -> None:
    """The mechanism is useless at any site that forgets to wire it.

    Every case above builds the switch itself, so all of them would keep passing
    while `agent/runner.py` quietly dropped the argument and the loop went back
    to honouring one switch. `companion_state_path` defaults to None because some
    constructions have no config to derive it from — which is exactly why the
    ones that do need pinning here.
    """
    import ast

    src_root = Path(__file__).resolve().parents[2] / "src" / "atlas_agent"
    unwired: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", None) != "AdvancedKillSwitch":
                continue
            if "companion_state_path" not in {kw.arg for kw in node.keywords}:
                unwired.append(f"{path.relative_to(src_root).as_posix()}:{node.lineno}")

    assert not unwired, f"AdvancedKillSwitch built without a companion path: {unwired}"


def test_an_absent_controller_state_is_not_treated_as_armed(wired_switches) -> None:
    """The file only exists once someone has used `atlas kill-switch`.

    Treating its absence as armed would refuse every workspace that has never
    touched that command, which is most of them.
    """
    config, advanced = wired_switches

    assert not (Path(config.memory_dir) / "kill_switch_state.json").exists()
    assert advanced.evaluate().allowed is True
