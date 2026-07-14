# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    portfolio/journal.py
# PURPOSE: The human-readable trade diary. Markdown, not JSONL, because this file
#          is read BY THE AGENT — it is fed back into the prompt as memory, and it
#          is what the learning loop mines for lessons.
# DEPS:    stdlib only
#
# NOTE:    Because it reaches the model prompt, memory_doctor.py scans this file for
#          leaked secrets and treats a hit as an error, not a warning.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


# ==============================================================================
# TRADE JOURNAL
# ==============================================================================

class TradeJournal:
    def __init__(self, path: str | Path = "memory/trade_journal.md") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("# Trade Journal\n\n", encoding="utf-8")

    def append(self, event_type: str, message: str) -> None:
        # Append-only, one line per event. This is a diary, not a database: it is never
        # rewritten, so the record of what the agent believed at the time survives even
        # when that belief turns out to have been wrong.
        timestamp = datetime.now(UTC).isoformat()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"- {timestamp} [{event_type}] {message}\n")

