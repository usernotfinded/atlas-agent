# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/state.py
# PURPOSE: Persistence for the kill switch mode. Small file, large consequences:
#          this is the one piece of state that decides whether orders may flow.
# DEPS:    safety.atomic_write (never a torn write), safety.models (status shape)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import logging
from pathlib import Path
from datetime import UTC, datetime

from atlas_agent.safety.atomic_write import atomic_write_json
from atlas_agent.safety.models import KillSwitchStatus, KillSwitchMode

logger = logging.getLogger(__name__)


# ==============================================================================
# KILL SWITCH STATE FILE
# ==============================================================================

class KillSwitchState:
    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)

    def load(self) -> KillSwitchStatus:
        # Absent file → "normal". A workspace that has never tripped the switch is
        # not in a suspicious state, and refusing to trade on a fresh install would
        # be absurd.
        if not self.state_path.exists():
            return KillSwitchStatus()

        try:
            content = self.state_path.read_text(encoding="utf-8")
            return KillSwitchStatus.model_validate_json(content)
        except Exception as exc:
            # A file that EXISTS but cannot be parsed is a different story: someone or
            # something wrote to it, and we cannot tell whether it said "stop". The
            # only safe reading of an unreadable kill switch is the most restrictive
            # one, so we escalate to locked_down rather than fall back to "normal".
            logger.warning(
                "KillSwitchState: corrupt or unreadable state file (%s: %s). "
                "Failing closed to locked_down.",
                type(exc).__name__,
                exc,
            )
            return KillSwitchStatus(
                mode="locked_down",
                reason="Corrupt safety state file detected; failing closed.",
                updated_at=datetime.now(UTC).isoformat()
            )

    def save(self, mode: KillSwitchMode, reason: str, actor: str = "system"):
        status = KillSwitchStatus(
            mode=mode,
            reason=reason,
            actor=actor,
            updated_at=datetime.now(UTC).isoformat(),
        )

        # Atomic + 0600. A half-written kill switch file would be read back as
        # corrupt and, by the rule in load(), lock the system down — technically safe,
        # but a self-inflicted outage. Getting the write right avoids the question.
        atomic_write_json(
            self.state_path,
            status.model_dump(),
            indent=2,
            chmod=0o600,
        )

        return status
