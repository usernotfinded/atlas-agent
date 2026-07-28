# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/architecture/test_provider_execution_boundary.py
# PURPOSE: Enforces that the AI-facing layers cannot reach execution or broker
#         code, so provider output can never be execution authority.
# DEPS:    ast, pathlib, pytest.
# ==============================================================================

"""Structural enforcement of the provider/execution boundary.

`docs/architecture.md` states that AI providers and models never call broker
adapters or execution modules directly, and the autonomy roadmap repeats it as
a cross-level invariant. The property held when this file was written, but
nothing made it fail if it stopped holding: a single new import inside the
provider layer would have quietly turned model output into a path to an order.

This is asserted over the layers rather than over a list of modules, so a
module added tomorrow is covered without anyone remembering to add it here.
The check reads imports statically, which is what matters — the concern is
whether the edge can exist at all, not whether some particular call runs.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlas_agent"

#: Layers that consume model or provider output.
AI_FACING_PACKAGES = ("providers", "research", "ai")

#: Packages that can place, route, or transmit an order.
EXECUTION_PACKAGES = ("atlas_agent.execution", "atlas_agent.brokers")


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _imported_modules(path: Path) -> set[str]:
    """Return every module name imported by a source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    return imported


def _execution_imports(path: Path) -> set[str]:
    return {
        module
        for module in _imported_modules(path)
        if module.startswith(EXECUTION_PACKAGES)
    }


@pytest.mark.parametrize("package", AI_FACING_PACKAGES)
def test_ai_facing_layer_cannot_reach_execution(package: str) -> None:
    """No module that handles provider output may import an execution path."""
    offenders: dict[str, set[str]] = {}
    for path in sorted((SRC_ROOT / package).rglob("*.py")):
        found = _execution_imports(path)
        if found:
            offenders[str(path.relative_to(SRC_ROOT))] = found

    assert offenders == {}, (
        "AI-facing modules must not import execution or broker code directly. "
        "Route the action through the tool registry so it passes the risk and "
        f"audit gates instead. Offenders: {offenders}"
    )


def test_the_boundary_check_detects_a_violation(tmp_path: Path) -> None:
    """Guard the guard: a check that cannot fail proves nothing."""
    offending = tmp_path / "leaky_provider.py"
    offending.write_text(
        "from atlas_agent.execution.order_router import OrderRouter\n",
        encoding="utf-8",
    )

    assert _execution_imports(offending) == {"atlas_agent.execution.order_router"}


def test_the_boundary_check_accepts_unrelated_imports(tmp_path: Path) -> None:
    """A module named after execution must not be mistaken for one importing it."""
    innocent = tmp_path / "provider_execution_readiness.py"
    innocent.write_text(
        "from atlas_agent.research.session import load_research_artifact\n"
        "import json\n",
        encoding="utf-8",
    )

    assert _execution_imports(innocent) == set()


# ==============================================================================
# THE RETURN DIRECTION
# ==============================================================================

# Blocking the import edge stops the execution layer being *called* from the AI
# side. It does not stop the execution layer *reading* what the AI side wrote.
# A file is an edge too: a submit path that opened a research artifact to take a
# suggested stop-loss or symbol would satisfy every import check above and still
# make provider output execution authority.
#
# That path does not exist today — the execution layer reads kill-switch state
# and pending orders and nothing else — and `research/backtest_bridge.py` is the
# sanctioned crossing, whitelisting the three fields an artifact may influence
# and validating each. This keeps it that way.

#: The layers that may place, route, or transmit an order.
EXECUTION_DIRECTORIES = ("execution", "brokers", "risk")

#: Config attributes naming a directory the AI-facing layers write into.
AI_WRITTEN_LOCATIONS = (
    "reports_dir",
    "artifacts_dir",
    "artifact_store",
    "research_dir",
    "memory_index",
)


@pytest.mark.parametrize("package", EXECUTION_DIRECTORIES)
def test_execution_layer_does_not_read_ai_written_locations(package: str) -> None:
    """The order path must not open anything the provider layer produced."""
    offenders: list[str] = []

    for path in sorted((SRC_ROOT / package).rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr not in AI_WRITTEN_LOCATIONS:
                continue
            offenders.append(
                f"{path.relative_to(SRC_ROOT)}:{node.lineno} reads .{node.attr}"
            )

    assert offenders == [], (
        f"The {package} layer reaches an AI-written location: {offenders}. "
        "Provider output may influence an order only through "
        "research/backtest_bridge.py, which whitelists and validates every field "
        "it carries. Reading an artifact directly restores the path the import "
        "boundary above exists to remove."
    )


def test_the_read_check_detects_a_violation(tmp_path: Path) -> None:
    """Guard the guard: the scan must catch the access it is written to find."""
    module = tmp_path / "leaky.py"
    module.write_text(
        "def load(config):\n"
        "    return (config.reports_dir / 'suggestion.json').read_text()\n",
        encoding="utf-8",
    )

    tree = ast.parse(module.read_text(encoding="utf-8"))
    found = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in AI_WRITTEN_LOCATIONS
    }

    assert found == {"reports_dir"}


def test_the_read_check_does_not_flag_the_order_path_locations(tmp_path: Path) -> None:
    """The directories the execution layer legitimately uses must not trip it."""
    module = tmp_path / "ordinary.py"
    module.write_text(
        "def load(config):\n"
        "    a = config.pending_orders_dir\n"
        "    b = config.memory_dir\n"
        "    c = config.audit_dir\n"
        "    return a, b, c\n",
        encoding="utf-8",
    )

    tree = ast.parse(module.read_text(encoding="utf-8"))
    found = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in AI_WRITTEN_LOCATIONS
    }

    assert found == set()
