"""Dispatch for `atlas research` subcommands."""
from __future__ import annotations

from collections.abc import Callable

from atlas_agent.cli_context import CLIContext

ResearchHandler = Callable[[CLIContext], int | None]

_REGISTRY: dict[str, ResearchHandler] | None = None


def _load_registry() -> dict[str, ResearchHandler]:
    global _REGISTRY
    if _REGISTRY is None:
        from atlas_agent.cli_commands.research import (
            adapter,
            credential,
            execution,
            misc,
            mock_response,
            opt_in,
            preflight,
            provider_misc,
            release_candidate,
            request,
            response,
            safety_dossier,
            sandbox,
        )

        registry: dict[str, ResearchHandler] = {}
        registry.update(adapter.HANDLERS)
        registry.update(credential.HANDLERS)
        registry.update(execution.HANDLERS)
        registry.update(misc.HANDLERS)
        registry.update(mock_response.HANDLERS)
        registry.update(opt_in.HANDLERS)
        registry.update(preflight.HANDLERS)
        registry.update(provider_misc.HANDLERS)
        registry.update(release_candidate.HANDLERS)
        registry.update(request.HANDLERS)
        registry.update(response.HANDLERS)
        registry.update(safety_dossier.HANDLERS)
        registry.update(sandbox.HANDLERS)
        _REGISTRY = registry
    return _REGISTRY


def dispatch_research(context: CLIContext) -> int | None:
    handler = _load_registry().get(getattr(context.args, "research_command", None))
    if handler is None:
        return None
    return handler(context)
