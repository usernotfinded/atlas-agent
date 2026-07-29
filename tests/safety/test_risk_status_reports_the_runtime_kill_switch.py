# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_risk_status_reports_the_runtime_kill_switch.py
# PURPOSE: Pins that `atlas risk status` and `atlas risk check` agree about
#         whether the kill switch is armed.
# DEPS:    contextlib, io, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Two branches of one command disagreed about the emergency stop.

`atlas kill-switch enable` writes on-disk state and leaves
`config.safety.kill_switch_enabled` false, so any reader of the config field
alone sees nothing. `cli_safety._effective_config_with_runtime_kill_switch`
exists to OR the two, and `cli_commands/risk.py` imports it — but only the
`check` branch called it. The `status` branch built its `RiskManager` from the
raw field:

    $ atlas kill-switch enable --mode flatten
    $ atlas risk status
      Kill Switch: Inactive          # armed at the strongest mode
    $ atlas risk check
      kill_switch=True

Nothing was gated on the wrong answer — `status` only prints — so this is false
confidence rather than an open path. It is still the report an operator reads
during an incident, and it said the stop was off.

The assertion here is that the two branches *agree*, rather than that `status`
prints a particular word. Pinning agreement catches a future divergence in either
direction, and it is the property that was actually broken: the codebase already
knew the right answer and one branch did not ask for it.
"""

# --- IMPORTS ---

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        main(["init", "."])
    return tmp_path


def _output(argv: list[str]) -> str:
    from atlas_agent.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main(argv)
    return buffer.getvalue()


def _arm_on_disk() -> None:
    from atlas_agent.cli_safety import _kill_switch_controller
    from atlas_agent.config.builder import get_effective_config

    _kill_switch_controller(get_effective_config()).enable(
        mode="flatten", reason="emergency", actor="cli", broker=None
    )


def test_status_reports_the_switch_armed_on_disk(workspace: Path) -> None:
    """The report an operator reads during an incident."""
    from atlas_agent.config.builder import get_effective_config

    _arm_on_disk()
    # The premise: only the on-disk state is armed. A consumer reading the config
    # field alone sees nothing, which is the whole point.
    assert get_effective_config().safety.kill_switch_enabled is False

    assert "Kill Switch: ACTIVE" in _output(["risk", "status"])


def test_status_and_check_agree_when_armed(workspace: Path) -> None:
    """The property that was broken: one branch knew, the other did not."""
    _arm_on_disk()

    status = _output(["risk", "status"])
    check = _output(["risk", "check"])

    assert "Kill Switch: ACTIVE" in status
    assert "kill_switch=True" in check


def test_status_and_check_agree_when_nothing_is_armed(workspace: Path) -> None:
    """The negative control.

    Without it, a `status` branch hard-coded to ACTIVE would satisfy both cases
    above.
    """
    status = _output(["risk", "status"])
    check = _output(["risk", "check"])

    assert "Kill Switch: Inactive" in status
    assert "kill_switch=True" not in check
