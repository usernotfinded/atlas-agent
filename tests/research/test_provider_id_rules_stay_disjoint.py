# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_provider_id_rules_stay_disjoint.py
# PURPOSE: Pins the two provider-id admission rules and the sets they accept,
#         after 21 copies of one name were found to carry three of them.
# DEPS:    ast, pathlib, pytest, atlas_agent.research
# ==============================================================================

"""What `validate_provider_id` meant, and why it had to stop being one name.

Twenty-one modules in `atlas_agent.research` defined a function called
`validate_provider_id`. They looked like copies. Normalising the error code away
left **three disjoint admission rules**:

| Rule | Copies | Admitted |
|---|---|---|
| `value in _get_disabled_provider_ids()` | 15 | the four disabled external ids, **not** `mock` |
| `value == "mock"` | 5 | `mock` only, **not** the external ids |
| either | 1 | all five |

`mock` is not a member of the disabled-target registry, so the first two accept
strictly different sets rather than one containing the other. The union belonged
to `provider_mock_response_simulation`, which validates two different fields —
the upstream preview's provider, which is external, and its own artifact's, which
must be `mock` — and defended the union by re-checking `!= "mock"` immediately
after. A permissive validator guarded by a separate strict test is the shape that
breaks the moment someone deletes the line that looks redundant, which is what
made this worth splitting rather than leaving alone.

CAND-038 gave the two policies names. The one hard constraint was that **no
admitted set may change**: a change there would be a policy decision wearing a
rename's clothes. `test_no_module_admits_more_than_its_rule` is that constraint,
asserted per module over the whole provider universe rather than by argument.

A fourth same-named function lives in `providers/provider_preflight.py`. It is
not a copy: it is a bounded-string check raising `PreflightValidationError`, in a
different package for a different purpose. It is out of scope here and left
alone — but it is the reason this file asserts on the research modules by name
rather than on every `validate_provider_id` in the tree.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from atlas_agent.research.provider_call_plan import list_disabled_provider_call_targets
from atlas_agent.research.sandbox_contracts import (
    MOCK_PROVIDER_ID,
    validate_contract_external_provider_id,
    validate_contract_mock_provider_id,
)
from atlas_agent.research.session import ResearchSessionError

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

RESEARCH_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlas_agent" / "research"

#: Every module carrying a wrapper, and which policy it delegates to. The one
#: module needing both is listed under the field it validates rather than under a
#: single rule, which is the distinction the split exists to make.
EXTERNAL_RULE_MODULES = {
    "provider_call_plan",
    "provider_credential_boundary",
    "provider_execution_audit_packet",
    "provider_execution_dry_run",
    "provider_execution_readiness_report",
    "provider_execution_state",
    "provider_opt_in_policy",
    "provider_preflight_freeze",
    "provider_adapter_interface_contract",
    "provider_execution_unlock_state",
    "provider_outbound_payload_preview",
    "provider_request_response_pairing",
    "provider_response_intake_policy",
    "provider_response_review_result",
    "provider_response_schema_contract",
}

MOCK_RULE_MODULES = {
    "provider_mock_response_final_safety_seal",
    "provider_mock_response_import_candidate",
    "provider_mock_response_review_sandbox",
    "provider_mock_response_trust_decision_blocker",
    "provider_safety_dossier",
}

#: Validates both, one per field.
BOTH_RULES_MODULE = "provider_mock_response_simulation"


def _universe() -> list[str]:
    """Every provider id worth testing, plus two that no rule may accept."""
    disabled = sorted({target["provider_id"] for target in list_disabled_provider_call_targets()})
    assert disabled, "the disabled-target registry is empty; this test would be vacuous"
    return [*disabled, MOCK_PROVIDER_ID, "alpaca", ""]


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_the_two_rules_are_disjoint() -> None:
    """The property that makes one name for both wrong.

    Neither rule is a relaxation of the other: each accepts something the other
    refuses. Asserted in both directions so a future change making one a superset
    of the other fails here rather than silently widening a caller.
    """
    accepts: dict[str, set[str]] = {"external": set(), "mock": set()}
    for value in _universe():
        for label, policy in (
            ("external", validate_contract_external_provider_id),
            ("mock", validate_contract_mock_provider_id),
        ):
            try:
                policy(value, "code")
                accepts[label].add(value)
            except ResearchSessionError:
                pass

    assert accepts["external"], "the external rule accepts nothing; the test is vacuous"
    assert accepts["mock"] == {MOCK_PROVIDER_ID}
    assert accepts["external"] & accepts["mock"] == set(), "the rules are no longer disjoint"
    assert accepts["external"] - accepts["mock"], "the external rule accepts nothing extra"
    assert accepts["mock"] - accepts["external"], "the mock rule accepts nothing extra"


def test_neither_rule_accepts_an_unknown_provider() -> None:
    """`alpaca` is a broker Atlas knows and is not a research provider target;
    the empty string is the fail-closed case. Neither rule may admit either."""
    for value in ("alpaca", ""):
        for policy in (validate_contract_external_provider_id, validate_contract_mock_provider_id):
            with pytest.raises(ResearchSessionError):
                policy(value, "code")


@pytest.mark.parametrize("module_name", sorted(EXTERNAL_RULE_MODULES | MOCK_RULE_MODULES))
def test_no_module_admits_more_than_its_rule(module_name: str) -> None:
    """The constraint CAND-038 was accepted under: the rename changed no admitted
    set. Checked per module against the whole universe, not by argument."""
    module = importlib.import_module(f"atlas_agent.research.{module_name}")
    expected_external = module_name in EXTERNAL_RULE_MODULES
    wrapper = getattr(
        module,
        "validate_external_provider_id" if expected_external else "validate_mock_provider_id",
    )

    for value in _universe():
        try:
            wrapper(value)
            admitted = True
        except ResearchSessionError:
            admitted = False

        if expected_external:
            should = value in {t["provider_id"] for t in list_disabled_provider_call_targets()}
        else:
            should = value == MOCK_PROVIDER_ID
        assert admitted is should, f"{module_name} admits {value!r}: {admitted}, expected {should}"


def test_the_module_needing_both_names_which_at_each_call_site() -> None:
    """The union is gone, and each of the two fields says which rule it means."""
    module = importlib.import_module(f"atlas_agent.research.{BOTH_RULES_MODULE}")
    assert not hasattr(module, "validate_provider_id"), "the union survived the split"
    assert module.validate_source_provider_id("custom-openai-compatible")
    assert module.validate_mock_provider_id(MOCK_PROVIDER_ID) == MOCK_PROVIDER_ID
    with pytest.raises(ResearchSessionError):
        module.validate_source_provider_id(MOCK_PROVIDER_ID)
    with pytest.raises(ResearchSessionError):
        module.validate_mock_provider_id("custom-openai-compatible")


def test_no_research_module_still_defines_the_overloaded_name() -> None:
    """One name meaning three things is what this was. A module reintroducing it
    is reintroducing the ambiguity, whichever rule it picks."""
    offenders: list[str] = []
    modules = sorted(RESEARCH_ROOT.rglob("*.py"))
    assert len(modules) > 20, "the module scan found too little to be meaningful"
    for path in modules:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and node.name == "validate_provider_id":
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
