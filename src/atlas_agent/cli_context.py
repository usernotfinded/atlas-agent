# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_context.py
# PURPOSE: The immutable bundle every CLI command handler receives. One argument
#          instead of four, so adding a new piece of ambient state does not mean
#          editing every handler signature in the project.
# DEPS:    atlas_agent.config (AtlasConfig), atlas_agent.workspace (resolution)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable

from atlas_agent.config import AtlasConfig
from atlas_agent.workspace import WorkspaceResolution


# ==============================================================================
# COMMAND CONTEXT
# ==============================================================================

@dataclass(frozen=True)
class CLIContext:
    args: argparse.Namespace
    config: AtlasConfig
    resolution: WorkspaceResolution

    # Injected rather than called directly so that tests, and the offline/configless
    # paths, can run without ever reaching for the network.
    update_checker: Callable[[], str | None] | None = None
