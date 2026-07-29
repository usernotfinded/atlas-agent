# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_setup_wizard_cannot_enable_live.py
# PURPOSE: Pins what the setup wizard writes to the runtime config — that live
#         mode does not grant execution, and that answers land in fields that mean
#         what they hold.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""Hard invariant 1, on the path a new user actually takes.

`setup/wizard_ui.py` says of its own trading-mode step: "it is where a user can
move themselves from paper to live." That is the wizard's most consequential
screen, and the existing wizard tests assert only that `WizardState` round-trips
through its own JSON file. Nothing asserted what choosing live does to the
runtime posture.

It does the safe thing today. `WizardState.save()` writes `trading_mode = "live"`
and nothing else: `broker.enable_live_trading` and `broker.enable_live_submit`
stay false, and `BrokerResolver` answers `can_submit=False`. Selecting a mode and
authorising execution are two decisions, and the wizard only makes the first.

Making the wizard "work properly" by having it set the opt-in flags too is a
plausible, well-meant change that would collapse the two into one screen. These
tests are what makes that change fail out loud instead of shipping.

The last case covers a different failure in the same `save()`: an answer written
into a field that means something else. The wizard put `update_channel`
("stable" or "beta") into `update.auto_check`, a check frequency documented as
"daily", "weekly", or "never". Nothing read it, so it left a wrong value in every
configured workspace with no symptom to notice.
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

def _finish_wizard(trust_mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Run the wizard's save step in an isolated workspace and load the result."""
    from atlas_agent.config import AtlasConfig
    from atlas_agent.setup.state import WizardState

    monkeypatch.chdir(tmp_path)
    # `save()` reads the environment for provider credentials; keep the workspace
    # from inheriting any that happen to be set on the runner.
    for name in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    WizardState(
        setup_mode="full",
        provider="anthropic",
        model="claude-opus-4-7",
        messaging="cli",
        workspace_path=".",
        trust_mode=trust_mode,
        broker_mode="alpaca",
        update_channel="stable",
    ).save(tmp_path / "wizard.json")

    return AtlasConfig.from_env()


def test_choosing_live_records_the_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The baseline: without this, the two tests below could pass on a no-op save."""
    config = _finish_wizard("live", tmp_path, monkeypatch)

    assert config.trading_mode == "live"


def test_choosing_live_does_not_switch_on_live_trading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selecting the mode is one decision; authorising execution is another."""
    config = _finish_wizard("live", tmp_path, monkeypatch)

    assert config.broker.enable_live_trading is False, (
        "the setup wizard switched on broker.enable_live_trading. Choosing a "
        "trading mode must not also grant execution — that is the separation hard "
        "invariant 1 rests on."
    )
    assert config.broker.enable_live_submit is False, (
        "the setup wizard switched on broker.enable_live_submit."
    )


def test_a_wizard_configured_workspace_still_cannot_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flags are the mechanism; this is the outcome that matters."""
    from atlas_agent.brokers.resolver import BrokerResolver

    config = _finish_wizard("live", tmp_path, monkeypatch)
    status = BrokerResolver(config).resolve_status(config.trading_mode)

    assert status.can_submit is False, (
        f"a workspace configured by the setup wizard reports can_submit=True "
        f"(code={status.code}). Finishing the wizard must never be sufficient to "
        "submit a live order."
    )


def test_choosing_paper_is_unaffected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The safe path keeps working, so the tests above cannot pass by refusing everything."""
    config = _finish_wizard("paper", tmp_path, monkeypatch)

    assert config.trading_mode == "paper"
    assert config.broker.enable_live_trading is False


@pytest.mark.parametrize("channel", ["stable", "beta"])
def test_the_update_channel_does_not_land_in_the_check_schedule(
    channel: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A release channel is not a check frequency.

    `update_channel` holds "stable" or "beta"; `update.auto_check` is documented
    as "daily", "weekly", or "never". The wizard used to write the first into the
    second, leaving `update.auto_check = "stable"` in every configured workspace.
    Nothing read it — that write was the field's only reference in the codebase —
    so it corrupted a typed setting with no visible symptom.
    """
    from atlas_agent.setup.state import WizardState

    monkeypatch.chdir(tmp_path)
    WizardState(
        setup_mode="full",
        provider="anthropic",
        model="claude-opus-4-7",
        messaging="cli",
        workspace_path=".",
        trust_mode="paper",
        broker_mode="paper",
        update_channel=channel,
    ).save(tmp_path / "wizard.json")

    from atlas_agent.config import AtlasConfig

    config = AtlasConfig.from_env()

    assert config.update.auto_check in {"daily", "weekly", "never"}, (
        f"the wizard left update.auto_check={config.update.auto_check!r}, which is "
        "a release channel rather than a check frequency."
    )
