from __future__ import annotations

from pathlib import Path


class KillSwitch:
    def __init__(self, path: str | Path = "memory/kill_switch.enabled") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def enable(self) -> None:
        self.path.write_text("enabled\n", encoding="utf-8")

    def disable(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def is_enabled(self) -> bool:
        return self.path.exists()

