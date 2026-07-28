# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/audit/test_live_submit_blocked_event_set.py
# PURPOSE: Pins the reason codes the live-submit path audits against the list the
#         release checklist promises.
# DEPS:    ast, re, pathlib, pytest.
# ==============================================================================

"""Structural guard for the documented `live_submit_blocked` reason codes.

`docs/release-checklist.md` enumerates the reason codes for which
`live_submit_blocked` is emitted, and the release gate reads that list. Nothing
compared it to the code, and it had drifted: `hmac_approval_missing`,
`market_quote_unavailable`, and `market_quote_invalid` were emitted by
`submit_execution.py` and absent from the checklist.

A reviewer auditing the live-submit path reads that list to know what a clean
audit log should contain. Codes missing from it are events they will not think
to look for.

This reads the emitters out of the source rather than triggering them. Reaching
every gate needs a broker, a market quote, and a signed approval per case;
a structural check covers gates added tomorrow, which a fixture-driven one
would not.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
import re
from pathlib import Path

# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "atlas_agent" / "execution" / "submit_execution.py"
CHECKLIST = ROOT / "docs" / "release-checklist.md"

EMITTER = "_emit_live_submit_blocked"

#: The emitter's signature is (writer, order_id, client_order_id, broker_id,
#: reason_code, gate), so the reason code is the fifth positional argument.
REASON_ARG_INDEX = 4

CHECKLIST_SENTINEL = "`live_submit_blocked` is emitted for these live-submit gate failures"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _emitted_reason_codes() -> set[str]:
    """Every reason code passed to the blocked-event emitter.

    One call site passes a variable rather than a literal, because the gate
    picks between several codes. Its literal assignments are resolved so the
    set stays complete.
    """
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    literals: set[str] = set()
    variables: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if name != EMITTER or len(node.args) <= REASON_ARG_INDEX:
            continue
        argument = node.args[REASON_ARG_INDEX]
        if isinstance(argument, ast.Constant):
            literals.add(str(argument.value))
        elif isinstance(argument, ast.Name):
            variables.add(argument.id)

    for variable in variables:
        assigned = re.findall(rf'\b{re.escape(variable)}\s*=\s*"([a-z_]+)"', source)
        assert assigned, (
            f"{EMITTER} is called with the variable {variable!r} and no literal "
            "assignment to it could be found, so its reason codes cannot be "
            "checked against the documentation."
        )
        literals.update(assigned)

    return literals


def _documented_reason_codes() -> set[str]:
    """The codes the release checklist promises, read from its own sentence."""
    text = CHECKLIST.read_text(encoding="utf-8")
    start = text.index(CHECKLIST_SENTINEL)
    end = text.index("\n- ", start)
    return set(re.findall(r"`([a-z_]+)`", text[start:end])) - {"live_submit_blocked"}


def test_every_emitted_reason_code_is_documented() -> None:
    """A code the code emits and the checklist omits is an unlooked-for event."""
    undocumented = _emitted_reason_codes() - _documented_reason_codes()

    assert undocumented == set(), (
        f"submit_execution.py emits live_submit_blocked with {sorted(undocumented)}, "
        "which docs/release-checklist.md does not list. A reviewer reading that "
        "list to audit a live-submit log would not know to expect them."
    )


def test_every_documented_reason_code_is_emitted() -> None:
    """The reverse: a promised code nothing emits is a claim about dead ground."""
    unemitted = _documented_reason_codes() - _emitted_reason_codes()

    assert unemitted == set(), (
        f"docs/release-checklist.md promises live_submit_blocked for {sorted(unemitted)}, "
        "which nothing in submit_execution.py emits. Either the gate was removed "
        "and the checklist kept its promise, or the code was renamed."
    )


def test_the_emitted_set_is_not_empty() -> None:
    """Both checks above pass trivially if the scan finds nothing.

    Renaming the emitter, or changing its signature so the reason code moves off
    argument five, would silently empty both sides of the comparison.
    """
    emitted = _emitted_reason_codes()

    assert len(emitted) > 10, (
        f"only {len(emitted)} reason codes were found in {SOURCE.name}; the scan "
        "has probably stopped matching the emitter rather than the gates having "
        "been removed."
    )
