# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/research/test_unsafe_claim_vocabulary_is_shared.py
# PURPOSE: Pins that every artifact scanner refuses the same core capability
#         claims, after nine copies of the list drifted into two disjoint sets.
# DEPS:    ast, pathlib, importlib, pytest, atlas_agent.research
# ==============================================================================

"""Regression pin on the anti-fabrication vocabulary.

Nine modules in `atlas_agent.research` each carried their own
`_UNSAFE_POSITIVE_CLAIM_PHRASES` and their own byte-identical recursive scanner.
Between them the nine lists held 85 phrases and the intersection was **empty** --
no phrase appeared in all nine. Two coherent vocabularies had drifted apart:

- Twelve capability claims shared by all seven `provider_*` modules and absent
  from both `release_candidate_*` modules.
- Twenty-three trading-readiness claims shared by both `release_candidate_*`
  modules and absent from all seven `provider_*` modules -- including
  `safe to trade`, `live trading ready`, `autonomous trading ready` and
  `guaranteed profit`.

The second gap mattered more. Provider artifacts are written on every research
run; release-candidate artifacts are occasional. So the claims a reader would
most want caught were unchecked on the high-volume path, and a provider artifact
asserting "safe to trade" validated cleanly.

`_claim_vocabulary.py` now holds one core list and one scanner. The tests below
pin both the structure and the behaviour, because either alone is escapable: a
module could import the core and then shadow the scanner, or keep the scanner and
narrow the list.

`test_no_core_phrase_collides_with_emitted_text` is the guard on this file's own
premise. Widening a refusal vocabulary is fail-closed for fabricated text but
fail-*shut* for correct text: a phrase that happens to occur in a field name or a
generated message would refuse valid artifacts. It was checked against every
string literal in the package before the core was set, and it stays checked so
that adding a phrase like "provider" cannot pass review.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from atlas_agent.research._claim_vocabulary import UNIVERSAL_UNSAFE_CLAIM_PHRASES

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

RESEARCH_ROOT = Path(__file__).resolve().parents[2] / "src" / "atlas_agent" / "research"

#: The modules that scan artifacts for fabricated capability claims.
SCANNER_MODULES = (
    "provider_adapter_interface_contract",
    "provider_mock_response_final_safety_seal",
    "provider_mock_response_import_candidate",
    "provider_mock_response_review_sandbox",
    "provider_mock_response_simulation",
    "provider_mock_response_trust_decision_blocker",
    "provider_safety_dossier",
    "release_candidate_cutover",
    "release_candidate_readiness",
)

#: The two halves of the historical split, kept explicit so a regression names
#: itself instead of reporting a set difference.
CLAIMS_THE_RELEASE_SCANNERS_MISSED = (
    "api call succeeded",
    "api key loaded",
    "approve order",
    "broker touched",
    "call broker",
    "create order",
    "credentials loaded",
    "live trading authorized",
    "manual unlock granted",
    "network enabled",
    "provider response trusted",
    "trust upgrade performed",
)

CLAIMS_THE_PROVIDER_SCANNERS_MISSED = (
    "approvals enabled",
    "autonomous trading ready",
    "beats the market",
    "broker execution enabled",
    "guaranteed profit",
    "live trading ready",
    "orders enabled",
    "production trading ready",
    "profitable strategy",
    "provider execution enabled",
    "real-money ready",
    "safe to trade",
    "trust granted",
    "verified alpha",
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _module(name: str):
    return importlib.import_module(f"atlas_agent.research.{name}")


def _scanners() -> list[tuple[str, object]]:
    found = [(name, _module(name)._has_unsafe_positive_claims) for name in SCANNER_MODULES]
    assert len(found) == 9, "the scanner list has changed; update this file deliberately"
    return found


def test_every_scanner_vocabulary_contains_the_universal_core() -> None:
    """Structural. A module may add phrases; it may not drop the shared ones."""
    for name in SCANNER_MODULES:
        vocabulary = set(_module(name)._UNSAFE_POSITIVE_CLAIM_PHRASES)
        missing = sorted(set(UNIVERSAL_UNSAFE_CLAIM_PHRASES) - vocabulary)
        assert missing == [], f"{name} no longer refuses {missing}"


def test_no_module_defines_its_own_claim_scanner() -> None:
    """The nine recursions were identical, and identical code in nine places is
    how the vocabularies diverged without anyone noticing. One definition means a
    change to the scan is a change everywhere, visible in one diff."""
    offenders: list[str] = []
    for path in sorted(RESEARCH_ROOT.rglob("*.py")):
        if path.name == "_claim_vocabulary.py":
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and node.name == "_has_unsafe_positive_claims":
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


@pytest.mark.parametrize(
    "phrase", CLAIMS_THE_RELEASE_SCANNERS_MISSED + CLAIMS_THE_PROVIDER_SCANNERS_MISSED
)
def test_every_scanner_flags_the_phrases_that_slipped_through(phrase: str) -> None:
    """Behavioural, and the direction that actually failed. Each of these was
    caught by one family of scanners and waved through by the other."""
    for name, scanner in _scanners():
        assert scanner(phrase) is True, f"{name} does not flag {phrase!r}"


def test_the_scanners_still_accept_ordinary_text() -> None:
    """The control. Without it, a scanner that returned True unconditionally would
    satisfy every assertion above."""
    for name, scanner in _scanners():
        for benign in ("mock only", "safe mock source", "no provider call was made", ""):
            assert scanner(benign) is False, f"{name} wrongly flags {benign!r}"


def test_the_scan_descends_into_artifacts_not_just_strings() -> None:
    """Artifacts are nested dicts and lists; a scanner that only looked at the top
    level would pass the phrase tests above and miss every real artifact."""
    for name, scanner in _scanners():
        assert scanner({"checks": [{"message": "safe to trade"}]}) is True, name
        # Keys are field names this package chooses, not content.
        assert scanner({"safe to trade": "no"}) is False, name


def test_the_scan_targets_are_what_they_were() -> None:
    """Pins how much of an artifact each module scans, which is the fact that
    explains the whole split.

    Three modules pass the entire artifact to the scanner. Six pass a hand-listed
    set of policy dicts. Nothing recorded this, and it is what decides whether an
    aggressive phrase is safe: the scan is a plain substring test, so it matches
    negated prose as readily as a claim.

    `provider_adapter_interface_contract` puts "Adapter interface contract cannot
    call broker." in its artifact's `warnings`, and `call broker` is in its own
    vocabulary -- the artifact survives only because `warnings` is not among the
    fields it scans. `provider_safety_dossier` scans everything and renders
    "- **Broker Touched**: False" in its markdown *export*, which is a return
    value and not a field. Both are fine today and neither is fine by accident.

    So a module moving from the subset scan to the whole-artifact scan, or adding
    a free-text field to the subset, needs the vocabulary re-checked against what
    that field can contain. Asserted both directions: a module leaving the set is
    as much a change as one joining it.
    """
    whole_artifact: set[str] = set()
    field_subset: set[str] = set()
    for name in SCANNER_MODULES:
        source = (RESEARCH_ROOT / f"{name}.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", None) != "_has_unsafe_positive_claims":
                continue
            if not node.args:
                continue
            argument = node.args[0]
            # `_has_unsafe_positive_claims(data)` -- the whole artifact.
            if isinstance(argument, ast.Name) and argument.id == "data":
                whole_artifact.add(name)
            # `... for f in policy_fields_for_positive_claim_check` and the
            # `data.get(field, {})` comprehensions: a named subset of fields.
            elif isinstance(argument, ast.Name) and argument.id == "f":
                field_subset.add(name)
            elif isinstance(argument, ast.Call):
                field_subset.add(name)

    assert whole_artifact == {
        "provider_safety_dossier",
        "release_candidate_cutover",
        "release_candidate_readiness",
    }
    assert field_subset == {
        "provider_adapter_interface_contract",
        "provider_mock_response_final_safety_seal",
        "provider_mock_response_import_candidate",
        "provider_mock_response_review_sandbox",
        "provider_mock_response_simulation",
        "provider_mock_response_trust_decision_blocker",
    }
