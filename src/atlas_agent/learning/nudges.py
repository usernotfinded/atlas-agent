# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    learning/nudges.py
# PURPOSE: Suggests memory updates based on recent activity — or, today, honestly
#          reports that it has nothing to suggest.
# DEPS:    stdlib only
#
# NOT IMPLEMENTED: analysing recent activity to produce a genuine nudge is not built
#          yet. generate_memory_nudge() therefore returns None rather than a canned
#          string. A hardcoded suggestion is worse than silence: it reads as though
#          the agent noticed something about YOUR workspace when it noticed nothing,
#          and a user who acts on it is acting on a fabrication.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path


# ==============================================================================
# MEMORY NUDGE
# ==============================================================================

def generate_memory_nudge(memory_dir: Path) -> str | None:
    """Propose a memory update based on recent activity.

    Args:
        memory_dir: the workspace memory directory.

    Returns:
        Always None: nudge generation is not implemented (see the module header).
        The caller already handles this — `atlas memory nudge` reports
        "No memory nudge available yet.", which is the truth.
    """
    return None
