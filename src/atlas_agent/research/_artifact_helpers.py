# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/_artifact_helpers.py
# PURPOSE: The small helpers every per-artifact module in this package had
#          written out for itself.
# DEPS:    pathlib
# ==============================================================================

"""Shared building blocks for the per-artifact research modules.

`src/atlas_agent/research/` holds roughly thirty modules, one per artifact type,
and each was written by copying its predecessor. Measured by comparing the
unparsed source of every module-level function, 83 definitions were byte-identical
to another module's. `CAND-037` in
[v0.6.27 Release Candidates](../../../docs/releases/v0.6.27-candidates.md) records
the full inventory.

The three below are the ones with nothing to decide: a single variant each, no
error codes, no per-artifact wording. Everything they touch is either a constant
or an argument, so absorbing them changes no behaviour anywhere.

Two of them are load-bearing despite their size, which is the reason to have one
copy rather than eight:

- `check` builds the `{name, passed, message}` payload that goes into an
  artifact's `checks` list and is covered by the artifact hash. Twenty-four
  modules agreed on the shape; a twenty-fifth spelling it differently would
  produce artifacts that validate but do not compare.
- `broker_separation_policy` is five invariants asserting that an artifact's
  pipeline stage cannot reach a broker, route an order, or touch the approval or
  risk managers. Eight copies all said `False` to all five. Nothing compared them,
  and a single copy flipped would have an artifact claim broker access is
  permitted at that stage.

Neither had drifted. That is the finding, not the absence of one: the same
measurement that produced this module also found `_UNSAFE_POSITIVE_CLAIM_PHRASES`
duplicated nine times *with* drift, and the difference between the two cases is
only that nobody had compared either.

What deliberately does **not** live here is `validate_provider_id`. Its 21 copies
look like the same function and are not — they carry three disjoint admission
rules under one name (see CAND-037), so unifying them would be a policy change
wearing a refactor's clothes.
"""

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path
from typing import Any


# ==============================================================================
# ARTIFACT BUILDING BLOCKS
# ==============================================================================

def check(name: str, passed: bool, message: str) -> dict[str, Any]:
    """One entry in an artifact's `checks` list.

    Key order is not incidental: these dicts are serialised into artifacts whose
    hash is recomputed on load, so the shape is part of the contract rather than
    a formatting choice.
    """
    return {"name": name, "passed": passed, "message": message}


def is_inside_workspace(path: Path, workspace: Path) -> bool:
    """Whether `path` resolves to somewhere under `workspace`.

    Both sides are resolved before comparing, so a symlink pointing out of the
    workspace is rejected rather than accepted on its literal prefix. `ValueError`
    is what `relative_to` raises for a path outside the root; it is caught here
    and reported as `False` rather than propagating, because every caller is
    asking a yes/no containment question.
    """
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def broker_separation_policy() -> dict[str, Any]:
    """The five things a research artifact's stage may not do.

    All five are `False` and none is configurable. This is a statement about the
    research pipeline's position in the system — it produces artifacts for a human
    to read, and no stage of it reaches execution — not a setting.
    """
    return {
        "broker_live_bridge_allowed": False,
        "broker_adapter_access_allowed": False,
        "order_routing_allowed": False,
        "approval_manager_access_allowed": False,
        "risk_manager_access_allowed": False,
    }
