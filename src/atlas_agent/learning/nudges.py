# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    learning/nudges.py
# PURPOSE: Placeholder. NOT implemented.
# DEPS:    stdlib only
#
# WARNING: `generate_memory_nudge` ignores its `memory_dir` argument entirely and
#          returns a hardcoded string. It performs no analysis of recent activity.
#          The suggestion it produces is identical on every call, for every
#          workspace, regardless of what the agent has actually been doing.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path


# ==============================================================================
# MEMORY NUDGE (STUB — see the warning above)
# ==============================================================================

def generate_memory_nudge(memory_dir: Path) -> str | None:
    """Proposes an update to memory based on recent activity."""
    # Placeholder
    return "Nudge: Consider updating user_profile.md with recent strategy preferences."
