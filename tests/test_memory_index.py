# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_memory_index.py
# PURPOSE: Verifies memory index behavior and regression expectations.
# DEPS:    os, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import os
from pathlib import Path

from atlas_agent.learning import rebuild_search_index, search_memory


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_search_memory_uses_markdown_without_index(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "trade_journal.md").write_text(
        "AAPL thesis ALPACA_API_KEY=secret-value\n",
        encoding="utf-8",
    )

    results = search_memory(memory_dir, "AAPL thesis")

    assert len(results) == 1
    assert results[0][0].name == "trade_journal.md"
    assert "secret-value" not in results[0][1]


def test_rebuild_search_index_preserves_search_memory_contract(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "trade_journal.md").write_text("AAPL breakout note\n", encoding="utf-8")
    (memory_dir / "daily_notes.md").write_text("MSFT mean reversion\n", encoding="utf-8")

    assert rebuild_search_index(memory_dir) == 2
    results = search_memory(memory_dir, "breakout")

    assert (memory_dir / "memory.sqlite").exists()
    assert [(path.name, snippet) for path, snippet in results] == [
        ("trade_journal.md", "AAPL breakout note")
    ]


def test_search_memory_falls_back_when_index_is_stale(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    note = memory_dir / "trade_journal.md"
    note.write_text("initial note\n", encoding="utf-8")
    rebuild_search_index(memory_dir)

    note.write_text("new catalyst note\n", encoding="utf-8")
    stat = note.stat()
    os.utime(note, ns=(stat.st_atime_ns + 1_000_000_000, stat.st_mtime_ns + 1_000_000_000))

    results = search_memory(memory_dir, "catalyst")
    assert [(path.name, snippet) for path, snippet in results] == [
        ("trade_journal.md", "new catalyst note")
    ]
