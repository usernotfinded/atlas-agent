# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/safety/test_revert_to_paper.py
# PURPOSE: Pins that returning to paper mode closes live submit and keeps the
#         operator's configuration intact.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""The escape hatch bounded live autonomy is required to keep.

`docs/bounded-live-autonomy-governance.md` lists, among the properties any
broader autonomy must preserve, "a clear 'revert to paper' path that disables
execution without deleting configuration".

Both halves matter and they pull against each other. Disabling execution is easy
if you are willing to erase the broker settings; keeping the settings is easy if
you leave execution open. An operator pulling back to paper in a hurry needs
both: the live path shut now, and their configuration still there afterwards so
that going back is a decision rather than a re-setup.

It works today, and nothing said so. `trading_mode = "paper"` is the whole
gesture: `_resolve_can_submit` requires live mode, so the live branch is never
reached, while `enable_live_trading` and the broker id stay in `config.toml`
untouched.
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

@pytest.fixture
def live_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> Path:
    """A workspace configured for live, as an operator would leave it."""
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    # Credentials present on purpose. Without them the resolver stops at
    # `live_credentials_missing` and the assertion below would hold for a reason
    # that has nothing to do with the trading mode — which is exactly what the
    # first version of this test did, until a mutation removing the mode gate
    # failed to break it.
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    main(["init", "."])
    for key, value in (
        ("trading_mode", "live"),
        ("broker.provider", "alpaca"),
        ("broker.enable_live_trading", "true"),
        # Every gate ahead of the trading-mode check is satisfied on purpose, so
        # that reverting to paper makes the mode the *first* reason live submit
        # closes. Otherwise an earlier gate answers first and the assertion says
        # nothing about reverting.
        ("broker.enable_live_submit", "true"),
    ):
        assert main(["config", "set", key, value]) == 0
    capsys.readouterr()
    return tmp_path


def test_reverting_to_paper_closes_live_submit(live_configured: Path, capsys) -> None:
    """The half that has to happen immediately."""
    from atlas_agent.brokers.resolver import BrokerResolver
    from atlas_agent.cli import main
    from atlas_agent.config import AtlasConfig

    assert main(["config", "set", "trading_mode", "paper"]) == 0
    capsys.readouterr()

    config = AtlasConfig.from_env()
    assert config.trading_mode == "paper"

    # The live branch is not reached at all, so live submit cannot resolve ready.
    resolver = BrokerResolver(config)
    assert resolver.resolve_status("live").can_submit is False, (
        "live submit still resolves ready after reverting to paper"
    )

    # And the mode must be what closed it. The status code folds the submit reason
    # into its message, so the reason is read from the gate chain directly — the
    # same way tests/brokers/test_live_submit_gate_chain.py reads it. Any other
    # reason would mean this workspace was never live-capable and the assertion
    # above proves nothing about reverting.
    allowed, reason, _message = resolver._resolve_can_submit("alpaca")
    assert allowed is False
    assert reason == "trading_mode_not_live", (
        f"live submit is closed by {reason!r} rather than by the paper mode"
    )


def test_reverting_to_paper_keeps_the_configuration(
    live_configured: Path, capsys
) -> None:
    """The half that makes it a revert rather than a re-setup."""
    from atlas_agent.cli import main
    from atlas_agent.config import AtlasConfig

    assert main(["config", "set", "trading_mode", "paper"]) == 0
    capsys.readouterr()

    config = AtlasConfig.from_env()
    assert config.broker.provider == "alpaca", "the broker choice was discarded"
    assert config.broker.enable_live_trading is True, (
        "reverting to paper cleared enable_live_trading. Disabling execution must "
        "not erase the settings the operator would need to go back."
    )


def test_paper_mode_still_works_after_the_revert(
    live_configured: Path, capsys
) -> None:
    """Reverting must leave a usable paper workspace, not a dead one.

    Without this, a revert that disabled everything would satisfy the test above.
    """
    from atlas_agent.brokers.resolver import BrokerResolver
    from atlas_agent.cli import main
    from atlas_agent.config import AtlasConfig

    assert main(["config", "set", "trading_mode", "paper"]) == 0
    capsys.readouterr()

    status = BrokerResolver(AtlasConfig.from_env()).resolve_status("paper")
    assert status.can_submit is True
    assert status.broker_id == "paper"
