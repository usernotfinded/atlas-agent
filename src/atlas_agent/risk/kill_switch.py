# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    risk/kill_switch.py
# PURPOSE: Legacy compatibility shim over KillSwitchController. Keeps the old
#          three-method API (enable/disable/is_enabled) alive while the real
#          logic lives in atlas_agent.safety.kill_switch.
# DEPS:    atlas_agent.safety.kill_switch (authoritative implementation)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from pathlib import Path

from atlas_agent.safety.kill_switch import KillSwitchController


# ==============================================================================
# LEGACY COMPATIBILITY SHIM
# ==============================================================================

class KillSwitch:
    """
    Legacy facade over the kill switch.

    New code should use KillSwitchController directly, which exposes mode
    (soft/hard), reason and actor. This class fills those in with fixed "legacy"
    values because the old call sites have no concept of them.
    """

    def __init__(self, path: str | Path = "memory/kill_switch.enabled") -> None:
        self.path = Path(path)

        # The controller separates the state file (JSON, with metadata) from the
        # flag file (presence/absence = on/off). The old contract only knew about
        # the flag, so the state path is derived by placing it next to the flag.
        self.controller = KillSwitchController(
            state_path=self.path.parent / "kill_switch_state.json",
            enabled_flag_path=self.path,
        )

    # --- Commands ---

    def enable(self) -> None:
        # "soft" halts new orders but does not force liquidation. It is the safe
        # default for a legacy caller that cannot express its intent.
        self.controller.enable(mode="soft", reason="legacy enable", actor="legacy")

    def disable(self) -> None:
        self.controller.disable(reason="legacy disable", actor="legacy")

    # --- Queries ---

    def is_enabled(self) -> bool:
        return self.controller.is_enabled()
