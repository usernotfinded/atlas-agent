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
