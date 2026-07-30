# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/_claim_vocabulary.py
# PURPOSE: The one list of capability claims no Atlas artifact may make, and the
#          one scanner that looks for them.
# DEPS:    none
# ==============================================================================

"""Shared vocabulary for the anti-fabrication scan over research artifacts.

Nine modules in this package carried their own `_UNSAFE_POSITIVE_CLAIM_PHRASES`
tuple and their own identical `_has_unsafe_positive_claims` recursion. The nine
lists held 85 distinct phrases between them and **no phrase appeared in all
nine** — the intersection was empty. That is not tailoring, it is two disjoint
vocabularies that had drifted apart:

- Twelve capability claims (`credentials loaded`, `call broker`, `network
  enabled`, `api key loaded`, ...) were shared by all seven `provider_*` modules
  and absent from both `release_candidate_*` modules.
- Twenty-three trading-readiness claims (`safe to trade`, `live trading ready`,
  `autonomous trading ready`, `guaranteed profit`, `real-money ready`, ...) were
  shared by both `release_candidate_*` modules and absent from all seven
  `provider_*` modules.

Both gaps were demonstrated by running the scanners rather than by reading them,
each against a control phrase from the scanner's own list to prove the probe was
not vacuous:

    provider_safety_dossier    "mock response trusted" -> flagged
    provider_safety_dossier    "safe to trade"         -> NOT flagged
    provider_safety_dossier    "guaranteed profit"     -> NOT flagged

    release_candidate_readiness  "safe to trade"       -> refused
    release_candidate_readiness  "credentials loaded"  -> ACCEPTED into a
                                                          validated artifact

The second gap is the more consequential of the two. Provider artifacts are
produced on every research run, while release-candidate artifacts are occasional;
so the claims a reader would most want caught -- "safe to trade", "live trading
ready" -- were unchecked on the high-volume path.

`FORBIDDEN_FRAGMENTS` does not cover the gap. It holds eleven secret-shaped
tokens (`API_KEY`, `Bearer`, `sk-`, `/Users/`, ...) and matches none of the
thirty-five phrases.

Reachability is not hypothetical. `release_candidate_readiness` puts the *stdout*
of `scripts/check_version_consistency.py` and `scripts/check_forbidden_claims.py`
into the `message` field of its checks, so an artifact carries text this package
did not generate.

## What belongs here

A phrase belongs in `UNIVERSAL_UNSAFE_CLAIM_PHRASES` when it would be false in
any Atlas artifact whatever produced it. Anything specific to one pipeline stage
-- `seal authorizes`, `sandbox review trusted` -- stays in that module, appended
to this core.

The line was drawn where the evidence drew it: a phrase is universal if it was
already shared across one whole family. That is the thirty-five above, plus four
snake_case twins of phrases already in the list (`beats_the_market`,
`profitable_strategy`, `real_money_ready`, `verified_alpha`) that one module of a
pair had and the other did not.

Widening a refusal vocabulary can only refuse more, never less, so the direction
is fail-closed. It is still a behaviour change: an artifact containing one of
these phrases stops validating in modules that previously accepted it.

The risk that runs the other way is a phrase colliding with text these modules
emit -- a field name, a check name, a generated message -- which would refuse
correct artifacts. Before the widening, the thirty-five cross-family phrases were
checked against the 8,101 string literals in the nine modules, and the four
snake_case twins against all 25,844 in the package; none collided.
`tests/research/test_unsafe_claim_vocabulary_is_shared.py` now holds the stronger
form of that check -- all thirty-nine against every literal in the package -- so a
phrase added to this list later cannot skip it.
"""

# --- IMPORTS ---
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

# --- CONFIGURATION AND CONSTANTS ---

#: Claims that are false for every artifact this package writes, in every stage.
#: Both spellings of each are listed where both were in use: the scan is a plain
#: substring test, so `safe_to_trade` does not match `safe to trade`.
UNIVERSAL_UNSAFE_CLAIM_PHRASES: tuple[str, ...] = (
    "api call succeeded",
    "api key loaded",
    "approvals enabled",
    "approvals_enabled",
    "approve order",
    "autonomous trading ready",
    "autonomous_trading_ready",
    "beats the market",
    "beats_the_market",
    "broker execution enabled",
    "broker touched",
    "broker_execution_enabled",
    "call broker",
    "create order",
    "credentials loaded",
    "guaranteed profit",
    "live trading authorized",
    "live trading ready",
    "live_trading_ready",
    "manual unlock granted",
    "network enabled",
    "orders enabled",
    "orders_enabled",
    "production trading ready",
    "production_trading_ready",
    "profitable strategy",
    "profitable_strategy",
    "provider execution enabled",
    "provider response trusted",
    "provider_execution_enabled",
    "real-money ready",
    "real_money_ready",
    "safe to trade",
    "safe_to_trade",
    "trust granted",
    "trust upgrade performed",
    "trust_granted",
    "verified alpha",
    "verified_alpha",
)


# ==============================================================================
# THE SCANNER
# ==============================================================================

def claim_phrases(*extra: str) -> tuple[str, ...]:
    """The universal core plus a module's own phrases, deduplicated and sorted.

    Sorted so that two modules declaring the same extras produce the same tuple,
    which makes the vocabularies comparable in a test instead of only by eye.
    """
    return tuple(sorted(set(UNIVERSAL_UNSAFE_CLAIM_PHRASES) | set(extra)))


def make_claim_scanner(phrases: Iterable[str]) -> Callable[[Any], bool]:
    """Build the recursive scanner the nine modules each defined identically.

    Returns a plain `bool`, not a truthy value: callers assert `is True` and
    `is False`, and the artifact validators put the result straight into a check
    payload that is hashed.
    """
    vocabulary = tuple(phrases)

    def has_unsafe_positive_claims(value: Any) -> bool:
        """Recursively scan value for unsafe positive-claim phrases in strings."""
        if isinstance(value, str):
            lower = value.lower()
            return any(phrase in lower for phrase in vocabulary)
        if isinstance(value, dict):
            # Keys are field names this package chooses, not content; scanning
            # them would refuse artifacts for being correctly labelled.
            return any(has_unsafe_positive_claims(item) for item in value.values())
        if isinstance(value, list):
            # `list` and not `(list, tuple)`, matching the nine originals
            # exactly. A tuple is not descended into, so a phrase inside one
            # escapes the scan. Artifacts are JSON, where no tuple survives, so
            # this is only reachable for a dict built in memory and scanned
            # before serialisation. Left as-is deliberately: this change is about
            # the vocabulary, and widening the recursion at the same time would
            # make a suite failure ambiguous between the two.
            return any(has_unsafe_positive_claims(item) for item in value)
        return False

    return has_unsafe_positive_claims
