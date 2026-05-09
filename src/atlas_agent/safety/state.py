from __future__ import annotations

import json
from pathlib import Path
from datetime import UTC, datetime

from atlas_agent.safety.models import KillSwitchStatus, KillSwitchMode


class KillSwitchState:
    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)

    def load(self) -> KillSwitchStatus:
        if not self.state_path.exists():
            return KillSwitchStatus()
            
        try:
            content = self.state_path.read_text(encoding="utf-8")
            return KillSwitchStatus.model_validate_json(content)
        except Exception:
            # Corrupt state fails closed
            return KillSwitchStatus(
                mode="locked_down",
                reason="Corrupt safety state file detected; failing closed.",
                updated_at=datetime.now(UTC).isoformat()
            )

    def save(self, mode: KillSwitchMode, reason: str, actor: str = "system"):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        
        status = KillSwitchStatus(
            mode=mode,
            reason=reason,
            actor=actor,
            updated_at=datetime.now(UTC).isoformat()
        )
        
        self.state_path.write_text(status.model_dump_json(indent=2), encoding="utf-8")
        return status
