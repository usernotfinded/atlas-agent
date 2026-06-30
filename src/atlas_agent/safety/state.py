from __future__ import annotations

import logging
from pathlib import Path
from datetime import UTC, datetime

from atlas_agent.safety.atomic_write import atomic_write_json
from atlas_agent.safety.models import KillSwitchStatus, KillSwitchMode

logger = logging.getLogger(__name__)


class KillSwitchState:
    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)

    def load(self) -> KillSwitchStatus:
        if not self.state_path.exists():
            return KillSwitchStatus()

        try:
            content = self.state_path.read_text(encoding="utf-8")
            return KillSwitchStatus.model_validate_json(content)
        except Exception as exc:
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

        atomic_write_json(
            self.state_path,
            status.model_dump(),
            indent=2,
            chmod=0o600,
        )

        return status
