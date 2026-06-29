"""Narrow CLI bootstrap pre-router.

This module is the public console entry point for the ``atlas`` command. It
routes exactly one configless command through a dedicated stdlib-only path:

    atlas agent submit-conformance

All other commands, including ``atlas --workspace X agent submit-conformance``,
delegate unchanged to the legacy ``atlas_agent.cli:main`` entry point.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "agent" and args[1] == "submit-conformance":
        from atlas_agent.agent.gated_submit_conformance_cli import main as route_main

        return route_main(args[2:])
    from atlas_agent.cli import main as legacy_main

    return legacy_main(args)


if __name__ == "__main__":
    sys.exit(main())
