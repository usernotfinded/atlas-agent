# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_memory_update_contract.py
# PURPOSE: Verifies memory update contract behavior and regression expectations.
# DEPS:    atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from atlas_agent.routines.memory_writer import append_memory


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_memory_update_appends_without_erasing_history(tmp_path) -> None:
    memory_dir = tmp_path / "memory"
    path = memory_dir / "daily_notes.md"
    path.parent.mkdir()
    path.write_text("# Daily Notes\n\nold note\n", encoding="utf-8")

    append_memory(memory_dir, "daily_notes.md", "test", "new note")

    text = path.read_text(encoding="utf-8")
    assert "old note" in text
    assert "new note" in text
