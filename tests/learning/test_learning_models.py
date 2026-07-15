# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/learning/test_learning_models.py
# PURPOSE: Verifies learning models behavior and regression expectations.
# DEPS:    json, pytest, atlas_agent.
# ==============================================================================

"""Tests for learning suggestion models."""
# --- IMPORTS ---

from __future__ import annotations

import json

import pytest

from atlas_agent.learning.models import (
    LearningSuggestion,
    SuggestionStatus,
    SuggestionProvenance,
    SuggestionAudit,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestLearningSuggestionSchema:
    def test_default_status_is_draft(self) -> None:
        s = LearningSuggestion()
        assert s.status == SuggestionStatus.draft
        assert s.execution_policy == "advisory_only"

    def test_artifact_type_and_schema(self) -> None:
        s = LearningSuggestion()
        assert s.artifact_type == "learning_suggestion"
        assert s.schema_version == "1.0.0"

    def test_disclaimer_present(self) -> None:
        s = LearningSuggestion()
        assert "not financial advice" in s.disclaimer.lower()
        assert "not automatically executable" in s.disclaimer.lower()

    def test_serialization_roundtrip(self) -> None:
        s = LearningSuggestion(
            title="Test",
            summary="Summary",
            kind="reflection",
            provenance=SuggestionProvenance(source_kind="reflection"),
        )
        data = s.model_dump(mode="json")
        restored = LearningSuggestion.model_validate(data)
        assert restored.title == "Test"
        assert restored.status == SuggestionStatus.draft

    def test_json_serializable(self) -> None:
        s = LearningSuggestion()
        data = s.model_dump(mode="json")
        text = json.dumps(data)
        assert "learning_suggestion" in text


class TestStatusTransitions:
    def test_submit_transition(self) -> None:
        s = LearningSuggestion()
        s.record_transition(SuggestionStatus.pending_review, actor="cli:user")
        assert s.status == SuggestionStatus.pending_review
        assert s.audit.submitted_for_review_at is not None
        assert len(s.audit.status_transitions) == 1
        assert s.audit.status_transitions[0]["to"] == "pending_review"

    def test_accept_transition(self) -> None:
        s = LearningSuggestion()
        s.record_transition(SuggestionStatus.pending_review)
        s.record_transition(SuggestionStatus.accepted, actor="cli:user", reason="good")
        assert s.status == SuggestionStatus.accepted
        assert s.audit.reviewed_by == "cli:user"
        assert s.audit.review_reason == "good"

    def test_reject_transition(self) -> None:
        s = LearningSuggestion()
        s.record_transition(SuggestionStatus.pending_review)
        s.record_transition(SuggestionStatus.rejected, actor="cli:user", reason="incomplete")
        assert s.status == SuggestionStatus.rejected
        assert s.audit.review_reason == "incomplete"

    def test_archive_transition(self) -> None:
        s = LearningSuggestion()
        s.record_transition(SuggestionStatus.pending_review)
        s.record_transition(SuggestionStatus.accepted)
        s.record_transition(SuggestionStatus.archived, reason="stale")
        assert s.status == SuggestionStatus.archived
        assert s.audit.archived_at is not None

    def test_multiple_transitions(self) -> None:
        s = LearningSuggestion()
        s.record_transition(SuggestionStatus.pending_review)
        s.record_transition(SuggestionStatus.accepted)
        s.record_transition(SuggestionStatus.archived)
        assert len(s.audit.status_transitions) == 3
        assert s.audit.status_transitions[0]["from"] == "draft"
        assert s.audit.status_transitions[0]["to"] == "pending_review"
        assert s.audit.status_transitions[1]["from"] == "pending_review"
        assert s.audit.status_transitions[1]["to"] == "accepted"

    def test_execution_policy_default(self) -> None:
        s = LearningSuggestion()
        assert s.execution_policy == "advisory_only"

    def test_provider_execution_disabled_in_provenance(self) -> None:
        s = LearningSuggestion()
        assert s.provenance.provider_execution_disabled is True
        assert s.provenance.static_fallback is True
