# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_bootstrap.py
# PURPOSE: The `atlas` console entry point. A thin pre-router that peels off the
#          four configless commands before the heavyweight CLI is ever imported.
# DEPS:    stdlib only at module scope — see the note on deferred imports below.
# ==============================================================================

"""Narrow CLI bootstrap pre-router.

This module is the public console entry point for the ``atlas`` command. It
routes exactly four configless commands through dedicated stdlib-only paths:

    atlas agent submit-conformance
    atlas agent readiness-envelope
    atlas agent operator-approval-gate
    atlas agent bounded-live-readiness

All other commands, including ``atlas --workspace X agent submit-conformance``
and ``atlas --workspace X agent readiness-envelope``, delegate unchanged to the
legacy ``atlas_agent.cli:main`` entry point.
"""

# --- IMPORTS ---
from __future__ import annotations

import sys


# ==============================================================================
# PRE-ROUTER
# ==============================================================================

def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    # The route imports below are deliberately function-local. These four commands
    # are the trust-contract surface: they must run with no config loaded and no
    # third-party import on the path, and a module-level import of the legacy CLI
    # would drag both in before we ever got here.
    #
    # The `--workspace X` form is intentionally NOT matched: any global flag pushes
    # argv[0] off `agent`, so it falls through to the legacy router that knows how
    # to parse it. That is a feature, not a gap.
    if len(args) >= 2 and args[0] == "agent":
        if args[1] == "submit-conformance":
            from atlas_agent.agent.gated_submit_conformance_cli import main as route_main

            return route_main(args[2:])
        if args[1] == "readiness-envelope":
            from atlas_agent.agent.runtime_readiness_envelope_cli import main as route_main

            return route_main(args[2:])
        if args[1] == "operator-approval-gate":
            from atlas_agent.agent.operator_approval_gate_cli import main as route_main

            return route_main(args[2:])
        if args[1] == "bounded-live-readiness":
            from atlas_agent.agent.bounded_live_autonomy_readiness_cli import main as route_main

            return route_main(args[2:])
    from atlas_agent.cli import main as legacy_main

    return legacy_main(args)


if __name__ == "__main__":
    sys.exit(main())
