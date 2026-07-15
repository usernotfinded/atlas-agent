# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/learning/test_learning_renderers.py
# PURPOSE: Verifies learning renderers behavior and regression expectations.
# DEPS:    json, atlas_agent.
# ==============================================================================

"""Tests for learning suggestion renderers."""
# --- IMPORTS ---

from __future__ import annotations

import json

from atlas_agent.learning.models import LearningSuggestion, SuggestionStatus
from atlas_agent.learning.renderers import render_markdown, render_json_string


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestRenderers:
    def test_render_markdown_contains_title(self) -> None:
        s = LearningSuggestion(title="Test Title")
        text = render_markdown(s)
        assert "# Learning Suggestion: Test Title" in text
        assert "advisory_only" in text

    def test_render_markdown_contains_provenance(self) -> None:
        s = LearningSuggestion(title="Test")
        text = render_markdown(s)
        assert "Provider Execution Disabled" in text

    def test_render_markdown_with_transitions(self) -> None:
        s = LearningSuggestion(title="Test")
        s.record_transition(SuggestionStatus.pending_review)
        s.record_transition(SuggestionStatus.accepted)
        text = render_markdown(s)
        assert "Submitted For Review At" in text
        assert "Reviewed At" in text

    def test_render_json_string(self) -> None:
        s = LearningSuggestion(title="Test")
        text = render_json_string(s)
        data = json.loads(text)
        assert data["artifact_type"] == "learning_suggestion"
        assert data["title"] == "Test"
