from __future__ import annotations

from pathlib import Path


def build_market_prompt(symbol: str, memory_dir: str | Path = "memory") -> str:
    memory_path = Path(memory_dir)
    sections: list[str] = [f"Analyze symbol: {symbol}"]
    for name in (
        "portfolio.md",
        "watchlist.md",
        "open_positions.md",
        "trade_journal.md",
        "strategy_rules.md",
        "daily_notes.md",
        "weekly_review.md",
    ):
        path = memory_path / name
        if path.exists():
            sections.append(f"\n## {name}\n{path.read_text(encoding='utf-8')}")
    return "\n".join(sections)


SYSTEM_PROMPT = (
    "You are an AI trading analyst. Propose decisions only. "
    "Never call broker APIs. All execution goes through deterministic risk controls."
)

