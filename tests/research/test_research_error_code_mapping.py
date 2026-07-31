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
*literal* codes and the table maps 69 of them, so at least 136 land on the
generic message — including plain not-found cases like
`provider_safety_dossier_source_seal_missing`. Measured over the CLI, 30 of the
175 `atlas research` subcommands answer a nonexistent id with "Research command
failed." while the reason was known, static, and safe to show.

Only that direction is measurable here. A literal code absent from the table
certainly hits the fallback, so the count is a sound lower bound. The reverse —
concluding an entry is dead because no literal raise matches it — is not sound:
33 raise sites build their code at runtime, and
`artifact_store.py` raises `f"ambiguous_{kind.name}_id"`, which is where the
table's `ambiguous_run_id`, `ambiguous_plan_id`, and `ambiguous_research_id`
entries are reached. A scan that reads literals cannot see them, so this file
does not ratchet unused entries.

Nothing made that visible. Adding `ResearchSessionError("my_specific_code")`
silently produces a generic message forever, and there is no failing test to
say so.

This does not require the backlog to be empty — that is 136 user-facing messages
to word, which is a contract decision and is proposed as `CAND-034`. It requires
the backlog not to grow. A new code without a table entry pushes the count over
the ratchet and fails here, with the fix in the failure message.

The scan reads string literals passed to `raise ResearchSessionError(...)`, and
also those passed as the error-code argument of a validator that raises on the
caller's behalf. A computed code cannot be safely mapped in advance and is out of
scope.

That second source was added because a refactor made this ratchet's own
measurement go blind. CAND-037 collapsed twenty copies of `validate_model_id`
into one `validate_contract_model_id(value, error_code)`, which moved thirteen
codes out of `raise ResearchSessionError('literal')` and into an argument at the
call site. The codes are still raised and the CLI is unchanged, but the literal
scan stopped seeing them: the unmapped count fell from 136 to 126 with nothing
fixed. `test_the_ratchets_are_not_slack` caught it, which is what that test is
for — and the fix is to teach the scan the new shape, not to lower the budget to
match a number that had become a fiction.

The general hazard is worth stating, because it will recur: a helper that takes
an error code as a parameter hides its callers' vocabulary from any scan that
looks for literals at the raise site. `ERROR_CODE_ARGUMENT_SITES` below is the
list of such helpers, and it has to grow whenever another one is introduced.

It recurred within one release. CAND-038 split `validate_provider_id` into
`validate_contract_external_provider_id` and `validate_contract_mock_provider_id`,
both taking their caller's code, and this file's anti-slack test failed again on
the same mechanism. That is the note above working as intended rather than a
second oversight: the list is the fix, and it is meant to be extended.
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
#:
#: CAND-034 took this from 136 to 0. Every literal code the source raises now has
#: a vetted status and message. The budget stays as a ratchet rather than being
#: deleted: a new code added without an entry pushes it above zero and fails here,
#: which is the whole point.
UNMAPPED_CODE_BUDGET = 0

#: Validators that raise `ResearchSessionError` with a code their caller supplies,
#: as {function name: index of the error-code argument}. Their call sites are the
#: real raise sites, so the scan has to read them too.
#:
#: Only helpers whose argument is the *whole* code belong here.
#: `validate_contract_lineage_id` takes a `field_name` and raises
#: `f"invalid_{field_name}"` — a fragment, not a code — so it stays out, and its
#: codes remain in the computed set this file deliberately does not ratchet.
ERROR_CODE_ARGUMENT_SITES = {
    "validate_contract_model_id": 1,
    "validate_contract_external_provider_id": 1,
    "validate_contract_mock_provider_id": 1,
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _literal_codes_raised() -> dict[str, str]:
    """Every string literal that reaches `ResearchSessionError` as a whole code.

    Two shapes: raised directly, or handed to a validator from
    `ERROR_CODE_ARGUMENT_SITES` that raises it for the caller.
    """
    found: dict[str, str] = {}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                name = getattr(node.exc.func, "id", "") or getattr(node.exc.func, "attr", "")
                if name != "ResearchSessionError" or not node.exc.args:
                    continue
                argument = node.exc.args[0]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    found.setdefault(
                        argument.value, f"{path.relative_to(SRC_ROOT)}:{node.lineno}"
                    )
            elif isinstance(node, ast.Call):
                name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
                index = ERROR_CODE_ARGUMENT_SITES.get(name)
                if index is None or len(node.args) <= index:
                    continue
                argument = node.args[index]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    found.setdefault(
                        argument.value, f"{path.relative_to(SRC_ROOT)}:{node.lineno}"
                    )
    return found


def test_the_scan_reads_the_parameterised_validators() -> None:
    """Guards against the blindness that prompted this addition.

    A helper taking an error code as an argument moves its callers' codes out of
    the raise-site scan. If this returns nothing, the wrapper branch above has
    stopped matching and the backlog count is quietly understated again.
    """
    raised = _literal_codes_raised()
    via_wrapper = [code for code in raised if code.endswith("_model") or code == "invalid_model_id"]

    assert len(via_wrapper) >= 13, (
        f"only {len(via_wrapper)} model-id codes found; the scan of "
        f"{sorted(ERROR_CODE_ARGUMENT_SITES)} has probably stopped matching."
    )


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



def test_the_ratchets_are_not_slack() -> None:
    """A budget well above the real count would let the backlog grow unnoticed.

    This is what stops the ratchet above from being decoration: it has to stay
    tight against the real number to mean anything.
    """
    raised = _literal_codes_raised()
    unmapped = len(set(raised) - set(RESEARCH_SESSION_ERROR_CODES))

    assert UNMAPPED_CODE_BUDGET - unmapped <= 5, (
        f"UNMAPPED_CODE_BUDGET is {UNMAPPED_CODE_BUDGET} and only {unmapped} codes "
        "are unmapped. Lower the budget to the real count so it keeps catching the "
        "next one."
    )
