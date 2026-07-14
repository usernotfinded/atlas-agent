# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    routines/context_loader.py
# PURPOSE: Gathers the memory context a routine needs before it runs.
# DEPS:    stdlib only
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


MEMORY_FILES = (
    "portfolio.md",
    "watchlist.md",
    "open_positions.md",
    "trade_journal.md",
    "strategy_rules.md",
    "daily_notes.md",
    "weekly_review.md",
)


@dataclass(frozen=True)
class RoutineContext:
    memory: dict[str, str]
    latest_pre_market_report: str | None = None


def load_routine_context(
    *,
    memory_dir: str | Path = "memory",
    reports_dir: str | Path = "reports",
) -> RoutineContext:
    memory_path = Path(memory_dir)
    memory_path.mkdir(parents=True, exist_ok=True)
    memory: dict[str, str] = {}
    for name in MEMORY_FILES:
        path = memory_path / name
        if not path.exists():
            title = name.replace("_", " ").replace(".md", "").title()
            path.write_text(f"# {title}\n\n", encoding="utf-8")
        memory[name] = path.read_text(encoding="utf-8")
    return RoutineContext(
        memory=memory,
        latest_pre_market_report=_latest_report(Path(reports_dir), "pre-market"),
    )


def _latest_report(reports_dir: Path, marker: str) -> str | None:
    daily_dir = reports_dir / "daily"
    if not daily_dir.exists():
        return None
    candidates = sorted(daily_dir.glob(f"*-{marker}.md"))
    if not candidates:
        return None
    return candidates[-1].read_text(encoding="utf-8")

