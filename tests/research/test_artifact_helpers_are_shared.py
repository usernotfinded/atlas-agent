# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_artifact_helpers_are_shared.py
# PURPOSE: Keeps the three absorbed per-artifact helpers on one definition, and
#         pins what the two load-bearing ones actually do.
# DEPS:    ast, pathlib, pytest, atlas_agent.research
# ==============================================================================

"""Structural and behavioural pin on `research/_artifact_helpers.py`.

Roughly thirty modules in `atlas_agent.research` are one-per-artifact-type and
each was written by copying its predecessor, which left 83 byte-identical
function definitions across the package. Three of them had a single variant and
nothing to decide, so they were absorbed: 41 copies became one each.

Absorbing duplication is only worth it if the duplication cannot come back, and
the next artifact type will be written the same way the last thirty were.

The behavioural half is not ceremony. `broker_separation_policy` is five
invariants asserting the research pipeline cannot reach a broker, route an order,
or touch the approval or risk managers, and it went into artifacts from eight
separate copies that nothing compared. `check` builds the payload that goes into
an artifact's `checks` list and is covered by the artifact hash, so its key set is
a contract rather than a formatting choice.

`is_inside_workspace` gets a real containment test rather than a prefix one,
because its docstring claims resolution defeats a symlink escape and a claim in a
docstring is exactly the kind this project keeps finding to be untrue.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from atlas_agent.research._artifact_helpers import (
    broker_separation_policy,
    check,
    is_inside_workspace,
)

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

RESEARCH_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlas_agent" / "research"

#: The names that used to be defined once per module. Kept as the private names
#: the call sites still use, since that is what a copied module would reintroduce.
ABSORBED = ("_check_name", "_is_inside_workspace", "_build_broker_separation_policy")


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_no_module_redefines_an_absorbed_helper() -> None:
    """One definition each. A module defining its own is a copy that will drift
    on its own schedule, which is how nine copies of the unsafe-claim vocabulary
    ended up with an empty intersection."""
    offenders: list[str] = []
    modules = sorted(RESEARCH_ROOT.rglob("*.py"))
    assert len(modules) > 20, "the module scan found too little to be meaningful"
    for path in modules:
        if path.name == "_artifact_helpers.py":
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and node.name in ABSORBED:
                offenders.append(f"{path.name}:{node.lineno} redefines {node.name}")
    assert offenders == []


def test_the_check_payload_keeps_its_shape() -> None:
    """The key set is covered by the artifact hash, so a fourth key or a renamed
    one changes every artifact that contains a check."""
    payload = check("no_network", True, "No network call was made.")
    assert payload == {"name": "no_network", "passed": True, "message": "No network call was made."}
    assert list(payload) == ["name", "passed", "message"]


def test_the_broker_separation_policy_denies_all_five() -> None:
    """Both directions: every flag present, and every one of them False.

    Asserted as an exact dict rather than a loop over `.values()`, so dropping a
    flag fails here instead of passing vacuously.
    """
    assert broker_separation_policy() == {
        "broker_live_bridge_allowed": False,
        "broker_adapter_access_allowed": False,
        "order_routing_allowed": False,
        "approval_manager_access_allowed": False,
        "risk_manager_access_allowed": False,
    }


def test_the_policy_is_a_fresh_dict_each_call() -> None:
    """Eight modules put the result straight into an artifact they then mutate. A
    shared module-level dict would let one artifact's edit reach another's."""
    first = broker_separation_policy()
    first["broker_live_bridge_allowed"] = True
    assert broker_separation_policy()["broker_live_bridge_allowed"] is False


class TestWorkspaceContainment:
    def test_accepts_a_path_inside(self, tmp_path: Path) -> None:
        inside = tmp_path / "research" / "artifact.json"
        inside.parent.mkdir(parents=True)
        inside.write_text("{}", encoding="utf-8")
        assert is_inside_workspace(inside, tmp_path) is True

    def test_rejects_a_sibling_directory(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "elsewhere" / "artifact.json"
        outside.parent.mkdir(parents=True)
        outside.write_text("{}", encoding="utf-8")
        assert is_inside_workspace(outside, workspace) is False

    def test_rejects_a_traversal(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (tmp_path / "secret.json").write_text("{}", encoding="utf-8")
        assert is_inside_workspace(workspace / ".." / "secret.json", workspace) is False

    def test_rejects_a_symlink_pointing_out(self, tmp_path: Path) -> None:
        """The claim the docstring makes. A containment check on the literal path
        would accept this, because the link itself lives inside the workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target = tmp_path / "outside.json"
        target.write_text("{}", encoding="utf-8")
        link = workspace / "looks-inside.json"
        link.symlink_to(target)

        # The premise: without resolution this path is inside the workspace.
        assert str(link).startswith(str(workspace))
        assert is_inside_workspace(link, workspace) is False
