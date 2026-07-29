# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/architecture/test_autonomous_layers_cannot_write_config.py
# PURPOSE: Refuses a config-write path from any layer that runs unattended.
# DEPS:    ast, pathlib, pytest.
# ==============================================================================

"""The limits an autonomous run obeys must not be limits it can raise.

The external gates in `docs/bounded-live-autonomy-governance.md` require, of any
broader autonomy, "per-deployment risk limits that cannot be raised by
autonomous logic". That is a property of who can write configuration, not of who
reads it: a loop that can call `set_raw_value("risk.max_order_notional", 1e9)`
has no limits, whatever the limits say.

It holds today — `agent/`, `research/`, and `ai/` contain no config write — and
nothing made it fail if it stopped holding. One import added to the agent loop
would end it silently, and the loop is exactly the code that runs when nobody is
watching.

This is the write-side counterpart to
`test_provider_execution_boundary.py`, which stops those layers reaching
execution. Together they say an unattended layer may neither place an order nor
change the rules an order is judged by.

Asserted over the layers rather than a file list, so a module added tomorrow is
covered without anyone remembering this file exists.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlas_agent"

#: Layers that run unattended, or that consume model output.
AUTONOMOUS_PACKAGES = ("agent", "research", "ai")

#: Every function that persists configuration or secrets.
CONFIG_WRITERS = frozenset({"set_raw_value", "unset_raw_value", "set_secret", "unset_secret"})


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _config_writes_in(package: str) -> list[str]:
    """Call sites and imports of a config writer inside a package."""
    found: list[str] = []
    root = SRC_ROOT / package
    if not root.exists():
        return found

    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = ""
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in CONFIG_WRITERS:
                        found.append(
                            f"{path.relative_to(SRC_ROOT)}:{node.lineno} imports {alias.name}"
                        )
                continue
            if name in CONFIG_WRITERS:
                found.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno} calls {name}")
    return found


@pytest.mark.parametrize("package", AUTONOMOUS_PACKAGES)
def test_an_unattended_layer_cannot_write_configuration(package: str) -> None:
    """Limits a loop can raise are not limits."""
    offenders = _config_writes_in(package)

    assert offenders == [], (
        f"the {package} layer can write configuration: {offenders}. Bounded live "
        "autonomy requires per-deployment risk limits that autonomous logic "
        "cannot raise, and a layer holding a config writer can raise its own."
    )


def test_the_scan_finds_the_writers_where_they_do_belong() -> None:
    """Guard the guard: a scan matching nothing would pass every case above.

    The CLI and setup layers write configuration on purpose — that is an operator
    acting, not a loop — so finding them there is what proves the scan works.
    """
    operator_writes: list[str] = []
    for package in ("cli_commands", "setup", "config"):
        operator_writes.extend(_config_writes_in(package))

    assert len(operator_writes) >= 5, (
        f"the scan found only {operator_writes} in the operator-facing layers, "
        "which write config by design. It is no longer matching config writers, "
        "so the assertions above prove nothing."
    )


def test_the_scan_catches_a_planted_write(tmp_path: Path) -> None:
    """The same check, run against a module written to fail it."""
    module = tmp_path / "greedy.py"
    module.write_text(
        "from atlas_agent.config import set_raw_value\n\n"
        "def raise_my_own_limit():\n"
        "    set_raw_value('risk.max_order_notional', 1e9)\n",
        encoding="utf-8",
    )

    tree = ast.parse(module.read_text(encoding="utf-8"))
    hits = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.Call)
            and (getattr(node.func, "id", "") or getattr(node.func, "attr", "")) in CONFIG_WRITERS)
        or (isinstance(node, ast.ImportFrom)
            and any(a.name in CONFIG_WRITERS for a in node.names))
    ]

    assert len(hits) == 2, "the scan missed either the import or the call"
