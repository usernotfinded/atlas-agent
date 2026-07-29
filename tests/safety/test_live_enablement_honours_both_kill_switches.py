# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_live_enablement_honours_both_kill_switches.py
# PURPOSE: Pins that granting and reporting live-submit authority sees both
#         kill switches, not only the one that gate happens to read.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""Granting live authority while an emergency stop is armed.

`_cmd_broker_opt_in` writes the record that authorises live order submission. It
checks the kill switch first and refuses when one is armed — which makes its
intent unambiguous — but it read only `KillSwitchController`, the `memory/`
switch. An operator who armed the runbook's own strongest command got:

    $ atlas kill flatten-all
    Kill switch mode set to: flatten_all
    $ atlas broker opt-in
    Live submit opt-in recorded for broker 'alpaca'.

`_display_live_status` had the same blind spot, reporting the live path's
readiness from one switch.

Neither was exploitable into a live order: `_resolve_can_submit` reads both
switches, so a submission would still have been refused. What was granted was
authority that could not be used while the stop held — and a status line that
disagreed with the resolver about whether the path was open. Both are gates that
plainly meant to refuse.

These are the third and fourth consumers found reading one of two kill switches,
after the resolver and the agent loop. The root cause is recorded in
[safety-invariant-audit-followups.md](../../docs/development/safety-invariant-audit-followups.md);
this file is the part that stays true afterwards.
"""

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

#: Every `atlas kill` mode that means stop. None may leave live authority
#: grantable.
ADVANCED_STOP_MODES = ("soft_pause", "cancel_all", "flatten_all", "locked_down")


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def ready_to_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A workspace where the opt-in would otherwise succeed.

    Every prerequisite the command checks ahead of the kill switch is satisfied
    on purpose. Without that it refuses for an earlier reason and these cases
    would pass while proving nothing about either switch.
    """
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    main(["init", "."])
    for key, value in (
        ("trading_mode", "live"),
        ("broker.provider", "alpaca"),
        ("broker.enable_live_trading", "true"),
        ("broker.enable_live_submit", "true"),
    ):
        main(["config", "set", key, value])
    # Typed confirmation is mandatory and `--yes` is refused outright, so the
    # command is driven the way an operator drives it.
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: "alpaca")
    return tmp_path


def _opt_in_record(workspace: Path) -> Path:
    return workspace / "audit" / "live_submit_opt_in.jsonl"


def _arm_advanced(mode: str) -> None:
    from atlas_agent.cli import main

    main(["kill", {"soft_pause": "soft-pause", "cancel_all": "cancel-all",
                   "flatten_all": "flatten-all", "locked_down": "lock"}[mode]])


def test_the_opt_in_is_granted_when_nothing_is_armed(ready_to_opt_in) -> None:
    """The negative control.

    Without it, a command that refused unconditionally would satisfy every case
    below — and the point is that this opt-in still works normally.
    """
    from atlas_agent.cli import main

    assert main(["broker", "opt-in"]) == 0
    assert _opt_in_record(ready_to_opt_in).exists()


@pytest.mark.parametrize("mode", ADVANCED_STOP_MODES)
def test_the_opt_in_is_refused_while_atlas_kill_is_armed(
    ready_to_opt_in, mode: str
) -> None:
    """`atlas kill <mode>` has to block the grant of live authority."""
    from atlas_agent.cli import main

    _arm_advanced(mode)

    assert main(["broker", "opt-in"]) != 0
    # The refusal has to actually withhold the authority, not merely report a
    # non-zero status while writing the record anyway.
    assert not _opt_in_record(ready_to_opt_in).exists()


def test_the_opt_in_is_refused_while_the_controller_is_armed(ready_to_opt_in) -> None:
    """The switch this gate already read keeps working."""
    from atlas_agent.cli import main
    from atlas_agent.cli_safety import _kill_switch_controller
    from atlas_agent.config.builder import get_effective_config

    _kill_switch_controller(get_effective_config()).enable(
        mode="soft", reason="emergency", actor="cli", broker=None
    )

    assert main(["broker", "opt-in"]) != 0
    assert not _opt_in_record(ready_to_opt_in).exists()


def test_live_status_does_not_report_ready_while_atlas_kill_is_armed(
    ready_to_opt_in,
) -> None:
    """The status display must not disagree with the resolver.

    An operator reading "live submit possible: yes" while `_resolve_can_submit`
    would refuse has been told the opposite of what the system will do.

    Called directly rather than through the onboarding screen it feeds. That
    screen sits behind a provider-credentials check, so driving it would mean
    configuring a provider to reach a line about brokers — and a first version of
    this case that went via `atlas broker status` passed on the phrase "kill
    switch normal" appearing in an adapter's *description text*, proving nothing.
    """
    from atlas_agent.brokers.resolver import BrokerResolver
    from atlas_agent.cli import _display_live_status
    from atlas_agent.config.builder import get_effective_config

    _arm_advanced("flatten_all")
    config = get_effective_config()

    allowed, _reason, _message = BrokerResolver(config)._resolve_can_submit("alpaca")
    assert allowed is False, "premise: the resolver refuses while this switch is armed"

    _creds, can_submit, message = _display_live_status(config)

    assert can_submit is False
    assert "kill switch" in message.lower()
