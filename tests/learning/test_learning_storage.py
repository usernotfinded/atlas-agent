# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/learning/test_learning_storage.py
# PURPOSE: Verifies learning storage behavior and regression expectations.
# DEPS:    json, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Tests for learning suggestion storage."""
# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas_agent.learning.models import LearningSuggestion, SuggestionStatus
from atlas_agent.learning.storage import (
    save_suggestion,
    load_suggestion,
    list_suggestions,
    delete_suggestion,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestLearningStorage:
    def test_save_and_load(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test", summary="Summary")
        path = save_suggestion(s, workspace=tmp_path)
        assert path.exists()

        loaded = load_suggestion(s.suggestion_id, workspace=tmp_path)
        assert loaded.suggestion_id == s.suggestion_id
        assert loaded.title == "Test"

    def test_load_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_suggestion("nonexistent", workspace=tmp_path)

    def test_list_empty(self, tmp_path: Path) -> None:
        items = list_suggestions(workspace=tmp_path)
        assert items == []

    def test_list_with_items(self, tmp_path: Path) -> None:
        s1 = LearningSuggestion(title="A")
        s2 = LearningSuggestion(title="B")
        save_suggestion(s1, workspace=tmp_path)
        save_suggestion(s2, workspace=tmp_path)
        items = list_suggestions(workspace=tmp_path)
        assert len(items) == 2
        ids = {i["suggestion_id"] for i in items}
        assert s1.suggestion_id in ids
        assert s2.suggestion_id in ids

    def test_list_filter_by_status(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        s.status = SuggestionStatus.pending_review
        save_suggestion(s, workspace=tmp_path)

        draft_items = list_suggestions(workspace=tmp_path, status=SuggestionStatus.draft)
        pending_items = list_suggestions(workspace=tmp_path, status=SuggestionStatus.pending_review)
        assert len(draft_items) == 0
        assert len(pending_items) == 1

    def test_list_skips_malformed(self, tmp_path: Path) -> None:
        suggestions_dir = tmp_path / ".atlas" / "learning" / "suggestions"
        suggestions_dir.mkdir(parents=True)
        (suggestions_dir / "bad.json").write_text("not json", encoding="utf-8")
        items = list_suggestions(workspace=tmp_path)
        assert items == []

    def test_delete(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        save_suggestion(s, workspace=tmp_path)
        delete_suggestion(s.suggestion_id, workspace=tmp_path)
        with pytest.raises(FileNotFoundError):
            load_suggestion(s.suggestion_id, workspace=tmp_path)

    def test_delete_missing_no_error(self, tmp_path: Path) -> None:
        delete_suggestion("nonexistent", workspace=tmp_path)
