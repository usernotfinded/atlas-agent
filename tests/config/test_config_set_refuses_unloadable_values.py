# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/config/test_config_set_refuses_unloadable_values.py
# PURPOSE: Refuses a config write the schema could never load back, while keeping
#         an already-broken config repairable.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""`atlas config set` must not brick the workspace and call it success.

It used to write anything. `atlas config set risk.max_order_notional
not_a_number` printed "Updated risk.max_order_notional in config.toml" and
returned 0, and every command afterwards failed with "Invalid Atlas config
schema" — including the ones an operator would reach for to find out what was
wrong.

The secret branch of the same handler already refused bad input and returned 2.
This gives the plain branch the same manners.

Validation is per field, never over the whole document. That distinction is the
point: `atlas config set` is the tool you use to repair a broken config, so
validating everything would make an already-broken config unrepairable.
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
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> Path:
    from atlas_agent.cli import main

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    return tmp_path


def test_a_value_the_schema_cannot_load_is_refused(workspace: Path, capsys) -> None:
    """The whole point: the write does not happen and the exit code says so."""
    from atlas_agent.cli import main
    from atlas_agent.config import AtlasConfig

    code = main(["config", "set", "risk.max_order_notional", "not_a_number"])
    captured = capsys.readouterr()

    assert code == 2, "a refused write must not report success"
    assert "not_a_number" in captured.out
    # And the config is still loadable, which is what was actually at stake.
    AtlasConfig.from_env()


def test_a_valid_value_is_still_written(workspace: Path, capsys) -> None:
    """Without this, refusing everything would pass the test above."""
    from atlas_agent.cli import main
    from atlas_agent.config import AtlasConfig

    assert main(["config", "set", "risk.max_order_notional", "250.5"]) == 0
    capsys.readouterr()

    assert AtlasConfig.from_env().risk.max_order_notional == 250.5


def test_an_undeclared_key_is_still_accepted(workspace: Path, capsys) -> None:
    """Unmapped legacy keys land at the top level by design; do not break that."""
    from atlas_agent.cli import main

    assert main(["config", "set", "some.unknown.key", "whatever"]) == 0
    capsys.readouterr()


def test_an_already_broken_config_can_still_be_repaired(
    workspace: Path, capsys
) -> None:
    """Validating the whole document would trap a user in a broken workspace.

    `atlas config set` is what you reach for to fix a bad value, so it has to
    keep working when the file it is fixing does not load.
    """
    from atlas_agent.cli import main
    from atlas_agent.config import AtlasConfig

    # `config.toml` is created on first write, so seed it before breaking it.
    assert main(["config", "set", "risk.max_order_notional", "100"]) == 0
    capsys.readouterr()

    toml_path = workspace / ".atlas" / "config.toml"
    toml_path.write_text(
        toml_path.read_text(encoding="utf-8").replace(
            "max_order_notional = 100", 'max_order_notional = "broken"'
        ).replace(
            'max_order_notional = "100"', 'max_order_notional = "broken"'
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        AtlasConfig.from_env()

    assert main(["config", "set", "risk.max_order_notional", "500"]) == 0
    capsys.readouterr()

    assert AtlasConfig.from_env().risk.max_order_notional == 500
