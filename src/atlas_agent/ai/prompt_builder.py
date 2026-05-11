from __future__ import annotations

from pathlib import Path

from atlas_agent.ai.discipline import (
    default_discipline_text,
    load_user_discipline,
    require_user_discipline,
)


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


def build_system_prompt(workspace_root: str | Path = ".") -> str:
    """Build a system prompt for non-agentic contexts (safe display, docs, etc.).

    This includes the default discipline as non-operational safety framing.
    It does NOT require a user discipline profile.
    """
    default = default_discipline_text()
    user = load_user_discipline(workspace_root)
    parts = [
        "You are an AI trading analyst. Propose decisions only. "
        "Never call broker APIs. All execution goes through deterministic risk controls.",
        "\n# Discipline Profile\n",
        default,
    ]
    if user:
        parts.append("\n# User Overrides\n")
        parts.append(user)
    return "\n".join(parts)


def build_agent_system_prompt(workspace_root: str | Path = ".") -> str:
    """Build the system prompt for agentic trading/research workflows.

    Requires a valid user discipline profile. Fails closed if missing or invalid.
    Never silently falls back to default_discipline_text().
    """
    user = require_user_discipline(workspace_root)
    parts = [
        "You are an AI trading analyst. Propose decisions only. "
        "Never call broker APIs. All execution goes through deterministic risk controls.",
        "\n# Discipline Profile\n",
        user,
    ]
    return "\n".join(parts)


# Legacy global constant preserved for callers that do not yet support workspace-aware prompts.
# New agentic code should use build_agent_system_prompt() and handle DisciplineNotConfiguredError.
SYSTEM_PROMPT = (
    "You are an AI trading analyst. Propose decisions only. "
    "Never call broker APIs. All execution goes through deterministic risk controls."
)
