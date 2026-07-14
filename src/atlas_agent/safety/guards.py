# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/guards.py
# PURPOSE: The live-mode gate, as a one-line predicate over the config.
# DEPS:    atlas_agent.config (AtlasConfig.live_disabled_reasons)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.config import AtlasConfig


# ==============================================================================
# LIVE MODE GUARD
# ==============================================================================

def live_mode_guard(config: AtlasConfig) -> tuple[bool, tuple[str, ...]]:
    """Return (live_allowed, reasons_it_is_not).

    Returns:
        (True, ()) only when nothing blocks live trading. Otherwise (False, reasons).
    """
    # Live is allowed only when the blocker list is EMPTY — an allowlist, not a
    # blocklist. Adding a new lock in live_disabled_reasons() therefore tightens this
    # gate automatically; no code here has to learn about it.
    reasons = config.live_disabled_reasons()
    return (not reasons, reasons)

