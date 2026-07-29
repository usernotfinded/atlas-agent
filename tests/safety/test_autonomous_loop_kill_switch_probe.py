# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_autonomous_loop_kill_switch_probe.py
# PURPOSE: Pins that the autonomous paper loop halts when the kill-switch state
#         cannot be read.
# DEPS:    pathlib, tempfile, pytest, atlas_agent.
# ==============================================================================

"""The autonomous loop's kill-switch probe, tested by behaviour not shape.

`autonomous_paper_runner._kill_switch_enabled` is duck-typed. It tries
`is_enabled()`, then `status()`, then `evaluate()`, and every fallback ends in
`return False` — "not armed, keep going". Two other order paths do the opposite
on the same condition: `BrokerResolver` answers `kill_switch_unreadable` and
`submit_execution` says in a comment that it fails closed.

With `KillSwitchController` the probe was already safe, and doubly so: it exposes
`is_enabled`, and `_read_state` fails closed on corruption, so an unreadable
state file yields an armed switch through either that branch or `status()`.
Removing the short-circuit changes nothing, which is worth knowing — the first
version of this file claimed otherwise and the mutation proved it wrong.

What did fail open was any other kill-switch-like object whose accessor *raises*:
both handlers swallowed the exception and fell through to `return False`. The
loop accepts any duck-typed switch, so that shape is reachable. Those handlers
now return True, matching `_read_state`'s own doctrine and the two order paths
that already answer that way.

The cases below assert outcomes rather than interface shape: what a fresh
workspace does, what an unreadable state does, what an armed switch does, and
what an accessor that raises does.
"""

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _controller(tmp_path: Path):
    from atlas_agent.safety.kill_switch import KillSwitchController

    return KillSwitchController(
        state_path=tmp_path / "kill_switch_state.json",
        enabled_flag_path=tmp_path / "kill_switch.enabled",
    )


def test_a_fresh_workspace_does_not_halt(tmp_path: Path) -> None:
    """No state file means the switch was never armed, not that it is unreadable.

    Without this the corrupt case below would pass on a probe that always halts.
    """
    from atlas_agent.agent.autonomous_paper_runner import _kill_switch_enabled

    assert _kill_switch_enabled(_controller(tmp_path)) is False


def test_an_unreadable_state_halts_the_loop(tmp_path: Path) -> None:
    """Someone wrote that file. Not being able to read it is not permission."""
    from atlas_agent.agent.autonomous_paper_runner import _kill_switch_enabled

    controller = _controller(tmp_path)
    (tmp_path / "kill_switch_state.json").write_text("{ not json", encoding="utf-8")

    assert _kill_switch_enabled(controller) is True, (
        "the autonomous loop kept running with an unreadable kill-switch state. "
        "Every fallback in _kill_switch_enabled returns False, so a probe that "
        "misses the is_enabled short-circuit fails open here."
    )


def test_an_armed_switch_halts_the_loop(tmp_path: Path) -> None:
    """The ordinary case, so the test above cannot pass by way of corruption alone."""
    from atlas_agent.agent.autonomous_paper_runner import _kill_switch_enabled

    controller = _controller(tmp_path)
    controller.enable(mode="soft", reason="test", actor="test")

    assert _kill_switch_enabled(controller) is True


class _RaisesOnStatus:
    """A kill switch whose state cannot be read. Not one that says "off"."""

    def status(self):
        raise RuntimeError("state unreadable")


class _RaisesOnEvaluate:
    def evaluate(self):
        raise RuntimeError("state unreadable")


class _NoAccessors:
    """Not a kill switch at all — nothing to ask, so nothing is armed."""


@pytest.mark.parametrize("probe", [_RaisesOnStatus(), _RaisesOnEvaluate()])
def test_an_accessor_that_raises_halts_the_loop(probe) -> None:
    """"I cannot read the kill switch" must not be read as "the switch is off"."""
    from atlas_agent.agent.autonomous_paper_runner import _kill_switch_enabled

    assert _kill_switch_enabled(probe) is True


@pytest.mark.parametrize("probe", [None, _NoAccessors()])
def test_the_absence_of_a_kill_switch_is_not_an_armed_one(probe) -> None:
    """The other direction, so failing closed cannot become halting always."""
    from atlas_agent.agent.autonomous_paper_runner import _kill_switch_enabled

    assert _kill_switch_enabled(probe) is False
