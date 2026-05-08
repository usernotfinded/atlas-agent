from __future__ import annotations

from pathlib import Path

from atlas_agent.safety.kill_switch import KillSwitchController


class KillSwitch:
    def __init__(self, path: str | Path = "memory/kill_switch.enabled") -> None:
        self.path = Path(path)
        self.controller = KillSwitchController(
            state_path=self.path.parent / "kill_switch_state.json",
            enabled_flag_path=self.path,
        )

    def enable(self) -> None:
        self.controller.enable(mode="soft", reason="legacy enable", actor="legacy")

    def disable(self) -> None:
        self.controller.disable(reason="legacy disable", actor="legacy")

    def is_enabled(self) -> bool:
        return self.controller.is_enabled()
