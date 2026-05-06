from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


class TradeJournal:
    def __init__(self, path: str | Path = "memory/trade_journal.md") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("# Trade Journal\n\n", encoding="utf-8")

    def append(self, event_type: str, message: str) -> None:
        timestamp = datetime.now(UTC).isoformat()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"- {timestamp} [{event_type}] {message}\n")

