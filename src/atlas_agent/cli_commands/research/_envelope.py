# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/research/_envelope.py
# PURPOSE: The one copy of the scaffolding every research handler repeats —
#          workspace resolution and the fail-closed error envelope.
# DEPS:    cli_context, research.errors, research.session, workspace
# ==============================================================================

"""The shared envelope for `atlas research` subcommand handlers.

Measured across `cli_commands/research/`, 170 handlers repeat the same opening
and closing: a dispatch guard, `resolve_workspace_path()` with an identical
`no_workspace` branch, an `except ResearchSessionError` mapping through
`safe_research_session_error`, and an `except Exception` emitting
`research_error`. That scaffolding is 4,147 lines of 11,196 — 123 handlers carry
exactly 25 such lines and 34 carry exactly 24.

`CAND-035` in [v0.6.27 Release Candidates](../../../../docs/releases/v0.6.27-candidates.md)
records the measurement and the migration this module exists to serve.

Two properties of the original make the scaffolding safe to absorb, and both were
checked rather than assumed.

The dispatch guard is unreachable code. `dispatch_research` looks each handler up
in a `HANDLERS` dict keyed by the very name the guard compares against, and
`cli.py` only calls it under `args.command == "research"`. All 170 guards match
their own registry key exactly, so the branch can never be false and the trailing
`return None` can never run.

The specific `except` clauses that 24 handlers put *before* the canonical pair are
load-bearing, not redundant, so this wrapper must not absorb them.
`safe_research_session_error` is an exact dict lookup on `str(exc)` against
snake_case keys, while `sanitize_symbol` raises
`InvalidResearchSymbolError("Invalid research symbol.")` — prose, which misses:

    'Invalid research symbol.'  -> ('research_error', 'Research command failed.')
    'invalid_research_symbol'   -> ('invalid_research_symbol', 'Invalid research symbol.')

A handler that let such an exception reach the generic path would silently
downgrade its status code. Those handlers keep their own `try` inside the body
below; because the wrapper's handlers sit outside, ordering is preserved and
`InvalidResearchSymbolError` — a `ResearchSessionError` subclass — is still caught
by the inner clause first.

What this module deliberately does NOT unify is the success branch. Three
divergences are known and must survive the migration:
`provider-safety-dossier-show` and `release-candidate-readiness-show` print the
artifact with no `ok`/`status` envelope at all, and `provider-safety-dossier-replay`
reports `replay_hash_match` where its sandbox counterpart reports `match`.
`print_json` exists only to write the serialisation options once, not to impose a
shape.
"""

# --- IMPORTS ---
from __future__ import annotations

import functools
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from atlas_agent.cli_context import CLIContext
from atlas_agent.cli_commands.research._shared import (
    _research_error_json,
    _research_error_text,
)


# ==============================================================================
# THE ENVELOPE
# ==============================================================================

def research_envelope(
    command: str,
) -> Callable[[Callable[[CLIContext, Path], int]], Callable[[CLIContext], int | None]]:
    """Wrap a research handler body in the shared workspace and error envelope.

    The wrapped function receives the resolved workspace as a second argument, so
    it never repeats the `no_workspace` branch, and returns the exit status for
    the success path only.
    """

    def decorate(body: Callable[[CLIContext, Path], int]) -> Callable[[CLIContext], int | None]:
        prefix = f"research {command}"

        @functools.wraps(body)
        def handler(context: CLIContext) -> int | None:
            args = context.args
            # Imported before the `try`, not inside it. The original handlers
            # import `ResearchSessionError` within the body they are guarding,
            # which leaves the `except` clause referencing a name that does not
            # exist yet if anything raises above that line.
            from atlas_agent.research.errors import safe_research_session_error
            from atlas_agent.research.session import ResearchSessionError
            from atlas_agent.workspace import resolve_workspace_path

            try:
                workspace = resolve_workspace_path()
                if workspace is None:
                    if args.json:
                        print(json.dumps({"ok": False, "status": "no_workspace"}, indent=2, sort_keys=True))
                    else:
                        print(f"{prefix} skipped safely: no workspace found")
                    return 1
                return body(context, workspace)
            except ResearchSessionError as exc:
                status, message = safe_research_session_error(exc)
                if args.json:
                    _research_error_json(status, message)
                else:
                    _research_error_text(prefix, message.lower().rstrip("."))
                return 1
            except Exception:
                # Deliberately generic and deliberately last. An unmapped
                # exception string may carry a path or user data, so the operator
                # sees a fixed message and never the exception.
                if args.json:
                    _research_error_json("research_error", "Research command failed.")
                else:
                    _research_error_text(prefix, "research command failed")
                return 1

        return handler

    return decorate


def print_json(payload: Any) -> None:
    """Emit a payload with the serialisation the handwritten handlers use.

    `indent=2, sort_keys=True` is the shape `check_cli_command_compatibility.py`
    and the trust-contract envelopes are pinned against, so it is written once
    here rather than repeated at every success branch. It imposes no envelope
    shape: callers that print a bare artifact pass one.
    """
    print(json.dumps(payload, indent=2, sort_keys=True))
