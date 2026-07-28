# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/policy.py
# PURPOSE: The project's non-negotiable safety invariants, stated in one place and
#          in plain English, so code that enforces one can quote the wording rather
#          than paraphrase it — see the gate 2 comment in execution/order_router.py.
# DEPS:    none
#
# WARNING: NOTHING READS THIS. `HARD_RULES` has no callers: it is a citation point
#          for comments and reviewers, not a check. Each rule is enforced somewhere
#          else entirely — the risk gate in `execution/order_router.py`, the
#          fail-closed guards in `brokers/guards.py`, the gate chain in
#          `brokers/resolver.py`, `safety/kill_switch.py`, and the credential-path
#          tests in `tests/architecture/`. Editing this tuple changes no behaviour
#          and will not make any gate appear or disappear.
#
#          This header used to claim the rules were "surfaced in the CLI and
#          asserted against by the trust checkers, so the promises made to users
#          and the promises made in code cannot silently diverge". Neither half was
#          true: no CLI command reads them, no checker asserts them, and the module
#          is not exported from `safety/__init__.py`. A safety file that overstates
#          its own enforcement is worse than one that claims nothing, because it
#          reads like a gate to the next person looking for one.
#
#          The full enforced set is the ten hard invariants in
#          docs/bounded-live-autonomy-governance.md. These six are the subset short
#          enough to quote.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations


# --- CONFIGURATIONS & CONSTANTS ---

HARD_RULES = (
    "No API keys in git.",
    "No live trading by default.",
    "No AI direct-to-broker execution.",
    "RiskManager is mandatory before broker execution.",
    "Kill switch overrides every order path.",
    "Manual approval is default for live mode.",
)

