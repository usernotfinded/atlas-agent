# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_research_error_code_mapping.py
# PURPOSE: Stops the research error-code allowlist drifting further from the
#         codes the source actually raises.
# DEPS:    ast, pathlib, atlas_agent.research.errors.
# ==============================================================================

"""A ratchet on the `RESEARCH_SESSION_ERROR_CODES` backlog.

`safe_research_session_error` maps a `ResearchSessionError` to a vetted status
and message, falling back to `("research_error", "Research command failed.")`
for anything it does not recognise. The fallback is right: an unmapped exception
string must never be echoed to the operator, because in general it could carry a
path or user data.

What is wrong is how much it fires. `src/atlas_agent` raises 205 distinct
*literal* codes and the table maps 69 of them, so 136 land on the generic
message — including plain not-found cases like
`provider_safety_dossier_source_seal_missing`. Measured over the CLI, 30 of the
175 `atlas research` subcommands answer a nonexistent id with "Research command
failed." while the reason was known, static, and safe to show.

Nothing made that visible. Adding `ResearchSessionError("my_specific_code")`
silently produces a generic message forever, and there is no failing test to
say so.

This does not require the backlog to be empty — that is 136 user-facing messages
to word, which is a contract decision and is proposed as `CAND-034`. It requires
the backlog not to grow. A new code without a table entry pushes the count over
the ratchet and fails here, with the fix in the failure message.

The scan reads only string literals passed to `raise ResearchSessionError(...)`.
A computed code cannot be safely mapped in advance and is out of scope.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
from pathlib import Path

from atlas_agent.research.errors import RESEARCH_SESSION_ERROR_CODES

# --- CONFIGURATION AND CONSTANTS ---

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlas_agent"

#: Codes raised with no entry in the table, counted when this ratchet was set.
#: Lower it when entries are added; it must never be raised.
UNMAPPED_CODE_BUDGET = 136

#: Entries whose code nothing raises any more. Also a ratchet: dead rows make the
#: table look more complete than it is, which is how it drifted this far.
UNRAISED_ENTRY_BUDGET = 79


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _literal_codes_raised() -> dict[str, str]:
    """Every string literal passed to `raise ResearchSessionError(...)`."""
    found: dict[str, str] = {}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            name = getattr(node.exc.func, "id", "") or getattr(node.exc.func, "attr", "")
            if name != "ResearchSessionError" or not node.exc.args:
                continue
            argument = node.exc.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.setdefault(
                    argument.value, f"{path.relative_to(SRC_ROOT)}:{node.lineno}"
                )
    return found


def test_the_scan_still_finds_the_raises() -> None:
    """Both ratchets pass trivially if the scan stops matching anything."""
    raised = _literal_codes_raised()

    assert len(raised) > 150, (
        f"the scan found only {len(raised)} literal ResearchSessionError codes; it "
        "has probably stopped matching the raise sites rather than them having "
        "been removed."
    )


def test_the_unmapped_backlog_does_not_grow() -> None:
    """A new code with no table entry means a new generic error message."""
    raised = _literal_codes_raised()
    unmapped = sorted(set(raised) - set(RESEARCH_SESSION_ERROR_CODES))

    assert len(unmapped) <= UNMAPPED_CODE_BUDGET, (
        f"{len(unmapped)} raised codes have no entry in RESEARCH_SESSION_ERROR_CODES, "
        f"above the ratchet of {UNMAPPED_CODE_BUDGET}. Codes added since:\n"
        + "\n".join(
            f"  {code}  ({raised[code]})"
            for code in unmapped[: UNMAPPED_CODE_BUDGET + 5]
        )[-1200:]
        + "\n\nAdd an entry to RESEARCH_SESSION_ERROR_CODES in "
        "src/atlas_agent/research/errors.py, or the CLI will answer "
        '"Research command failed." for it. Lower the ratchet when you do.'
    )


def test_the_dead_entry_backlog_does_not_grow() -> None:
    """An entry for a code nothing raises makes the table look complete."""
    raised = _literal_codes_raised()
    unraised = sorted(set(RESEARCH_SESSION_ERROR_CODES) - set(raised))

    assert len(unraised) <= UNRAISED_ENTRY_BUDGET, (
        f"{len(unraised)} entries in RESEARCH_SESSION_ERROR_CODES map codes that "
        f"nothing raises, above the ratchet of {UNRAISED_ENTRY_BUDGET}. Either the "
        "raise was removed and the entry should go with it, or the code was "
        "renamed and the entry should follow."
    )


def test_the_ratchets_are_not_slack() -> None:
    """A budget well above the real count would let the backlog grow unnoticed.

    This is what stops the two ratchets above from being decoration: they have to
    stay tight against the real numbers to mean anything.
    """
    raised = _literal_codes_raised()
    unmapped = len(set(raised) - set(RESEARCH_SESSION_ERROR_CODES))
    unraised = len(set(RESEARCH_SESSION_ERROR_CODES) - set(raised))

    assert UNMAPPED_CODE_BUDGET - unmapped <= 5, (
        f"UNMAPPED_CODE_BUDGET is {UNMAPPED_CODE_BUDGET} and only {unmapped} codes "
        "are unmapped. Lower the budget to the real count so it keeps catching the "
        "next one."
    )
    assert UNRAISED_ENTRY_BUDGET - unraised <= 5, (
        f"UNRAISED_ENTRY_BUDGET is {UNRAISED_ENTRY_BUDGET} and only {unraised} "
        "entries are dead. Lower the budget to the real count."
    )
