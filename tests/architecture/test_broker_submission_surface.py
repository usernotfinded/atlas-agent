# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/architecture/test_broker_submission_surface.py
# PURPOSE: Pins which modules may reach a broker, so a new submission path
#         cannot appear without review.
# DEPS:    ast, pathlib, pytest.
# ==============================================================================

"""Structural pin on the set of places that can send an order to a broker.

`safety/policy.py` states that the RiskManager is mandatory before broker
execution, and `order_router.py` cites that rule where it evaluates risk. Both
paths that can reach a real broker do evaluate risk today.

Nothing kept that true. A new `place_order` call somewhere else would be a
second front door: it would not be a change to any gate, so no test of the
gates would notice, and reviewers would have to spot it by eye.

This asserts the call sites themselves rather than the gates behind them. It is
deliberately a small, hostile-to-drift check: adding a submission path fails it,
which is the moment a human should be looking. Removing one fails it too, since
the point is that this set is decided rather than incidental.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlas_agent"

#: Every module allowed to invoke a broker's `place_order`, and why.
#:
#: - `brokers/paper.py` calls its own `place_order` when flattening. Simulated
#:   fills only; no venue exists behind it.
#: - `execution/order_router.py` is the routed path: input sanity, then the
#:   RiskManager, then live locks and human approval, then the broker.
#: - `execution/submit_execution.py` is the gated live-submit path, which
#:   re-validates risk because the approval it acts on was granted earlier.
ALLOWED_SUBMISSION_MODULES = {
    "brokers/paper.py",
    "execution/order_router.py",
    "execution/submit_execution.py",
}

#: The two that can reach a real venue must evaluate risk in the same module.
MUST_EVALUATE_RISK = {
    "execution/order_router.py",
    "execution/submit_execution.py",
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _calls_place_order(path: Path) -> bool:
    """Whether the module invokes `.place_order(...)` on anything."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "place_order"
        ):
            return True
    return False


def _submission_modules() -> set[str]:
    return {
        path.relative_to(SRC_ROOT).as_posix()
        for path in SRC_ROOT.rglob("*.py")
        if _calls_place_order(path)
    }


def test_only_reviewed_modules_can_reach_a_broker() -> None:
    found = _submission_modules()

    unexpected = found - ALLOWED_SUBMISSION_MODULES
    assert unexpected == set(), (
        "A new broker submission path appeared. Every order must reach a broker "
        "through the routed or gated path so the RiskManager, kill switch, and "
        f"approval gates apply. New call sites: {sorted(unexpected)}"
    )

    missing = ALLOWED_SUBMISSION_MODULES - found
    assert missing == set(), (
        "An expected submission path no longer calls place_order. If it moved, "
        f"update this list so the surface stays decided rather than assumed: {sorted(missing)}"
    )


@pytest.mark.parametrize("module", sorted(MUST_EVALUATE_RISK))
def test_a_venue_facing_path_evaluates_risk(module: str) -> None:
    """The two paths that can reach a real venue must consult the RiskManager."""
    source = (SRC_ROOT / module).read_text(encoding="utf-8")

    assert "RiskManager" in source, (
        f"{module} can submit to a broker but does not reference the RiskManager. "
        "safety/policy.py states the RiskManager is mandatory before broker execution."
    )


def test_the_detector_sees_a_new_call_site(tmp_path: Path) -> None:
    """Guard the guard: a surface check that cannot fail pins nothing."""
    sneaky = tmp_path / "sneaky.py"
    sneaky.write_text("def go(broker, order):\n    broker.place_order(order)\n", encoding="utf-8")

    assert _calls_place_order(sneaky) is True


def test_the_detector_ignores_a_mere_mention(tmp_path: Path) -> None:
    """A docstring or string naming the method is not a call site."""
    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        '"""Emitted immediately before broker.place_order."""\n'
        'FORBIDDEN = "place_order("\n',
        encoding="utf-8",
    )

    assert _calls_place_order(innocent) is False
