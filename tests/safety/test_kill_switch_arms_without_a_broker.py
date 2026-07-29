# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_kill_switch_arms_without_a_broker.py
# PURPOSE: Pins that arming the kill switch never depends on reaching a broker.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""The emergency stop has to work on the day the broker does not.

`docs/bounded-live-autonomy-governance.md` lists a "human-enablable kill switch"
among the properties any broader autonomy must preserve. A switch that only arms
while the broker is reachable does not satisfy that, because an unreachable
broker is one of the situations you reach for the switch in.

`KillSwitchController.enable` was written for this and says so: state is
persisted before the broker side effects run, so the process "can crash while
braking, but never crash back into 'not braking'", and `_run_flatten` returns a
failed result rather than raising when handed no broker at all. The parameter is
`broker: Broker | None = None` precisely so a caller with nothing to pass can
still arm.

Both CLI callers defeated that. `atlas kill-switch enable` and `atlas telegram
kill` each built the broker *eagerly*, before calling `enable()`, so in a
workspace with `trading_mode = "live"` and no credentials — the default
fail-closed state after switching to live — `_broker_for_mode` raised and the
exception escaped `main()` as a traceback with the switch still disarmed. All
three modes, including `soft`, which needs no broker at all.

The controller's guarantee was intact the whole time. It was never reached.

These cases assert the outcome an operator needs rather than the mechanism: the
switch is ON afterwards. A failure here is not a broken test, it is an emergency
stop that a missing credential can veto.
"""

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

# Every mode the CLI accepts. `soft` needs no broker to do its job at all; the
# other two need one to act, but not to arm.
ENABLE_MODES = ("soft", "cancel", "flatten")


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def live_without_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A live-mode workspace whose broker cannot be built.

    Credentials are deliberately absent, and cleared from the environment in case
    the host running the suite has real ones exported. This is the state a
    workspace is in between `trading_mode = "live"` and finishing setup, and the
    state it returns to whenever a credential is rotated or revoked.
    """
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    for variable in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
        monkeypatch.delenv(variable, raising=False)
    main(["init", "."])
    main(["config", "set", "trading_mode", "live"])
    main(["config", "set", "broker.provider", "alpaca"])
    return tmp_path


def _switch_is_armed(workspace: Path) -> bool:
    from atlas_agent.cli_safety import _kill_switch_controller
    from atlas_agent.config.builder import get_effective_config

    return _kill_switch_controller(get_effective_config()).is_enabled()


@pytest.mark.parametrize("mode", ENABLE_MODES)
def test_kill_switch_enable_arms_when_the_broker_cannot_be_built(
    live_without_credentials: Path, mode: str
) -> None:
    """The operator ran the emergency stop. It has to be on afterwards."""
    from atlas_agent.cli import main

    # Not pytest.raises: the point is that nothing escapes. A traceback out of
    # main() is the defect, so calling it plainly is the assertion.
    exit_code = main(["kill-switch", "enable", "--mode", mode, "--reason", "emergency"])

    assert _switch_is_armed(live_without_credentials) is True
    assert isinstance(exit_code, int)


@pytest.mark.parametrize("mode", ENABLE_MODES)
def test_telegram_kill_arms_when_the_broker_cannot_be_built(
    live_without_credentials: Path, mode: str
) -> None:
    """The same stop reached from the remote control plane.

    This path matters more, not less: an operator sending /kill from a phone is
    by definition not at the terminal to read a traceback.
    """
    from atlas_agent.cli import main

    exit_code = main(["telegram", "kill", "--mode", mode, "--reason", "emergency"])

    assert _switch_is_armed(live_without_credentials) is True
    assert isinstance(exit_code, int)


def test_a_requested_flatten_that_could_not_run_is_reported(
    live_without_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Arming is not the whole promise when the operator asked to be flat.

    The switch is on, but no position was closed and none could be. Reporting
    success here would tell someone with open exposure that it had been dealt
    with, so the command has to say otherwise in both channels an operator or a
    script reads: the output and the exit status.
    """
    from atlas_agent.cli import main

    exit_code = main(
        ["kill-switch", "enable", "--mode", "flatten", "--reason", "emergency"]
    )

    assert _switch_is_armed(live_without_credentials) is True
    assert exit_code != 0
    assert "broker" in capsys.readouterr().out.lower()
