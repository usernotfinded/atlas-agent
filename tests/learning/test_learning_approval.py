"""Tests for learning suggestion approval workflow."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlas_agent.learning.models import LearningSuggestion, SuggestionStatus
from atlas_agent.learning.storage import load_suggestion
from atlas_agent.learning.approval import (
    submit_for_review,
    accept,
    reject,
    archive,
)


class TestApprovalWorkflow:
    def test_submit_for_review(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        result = submit_for_review(s, workspace=tmp_path)
        assert result.status == SuggestionStatus.pending_review
        loaded = load_suggestion(s.suggestion_id, workspace=tmp_path)
        assert loaded.status == SuggestionStatus.pending_review

    def test_submit_non_draft_fails(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        s.status = SuggestionStatus.pending_review
        with pytest.raises(ValueError):
            submit_for_review(s, workspace=tmp_path)

    def test_accept(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        submit_for_review(s, workspace=tmp_path)
        result = accept(s, reason="looks good", workspace=tmp_path)
        assert result.status == SuggestionStatus.accepted
        assert result.audit.review_reason == "looks good"
        loaded = load_suggestion(s.suggestion_id, workspace=tmp_path)
        assert loaded.status == SuggestionStatus.accepted

    def test_accept_non_pending_fails(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        with pytest.raises(ValueError):
            accept(s, workspace=tmp_path)

    def test_reject(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        submit_for_review(s, workspace=tmp_path)
        result = reject(s, reason="incomplete", workspace=tmp_path)
        assert result.status == SuggestionStatus.rejected
        assert result.audit.review_reason == "incomplete"

    def test_reject_non_pending_fails(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        with pytest.raises(ValueError):
            reject(s, workspace=tmp_path)

    def test_archive_accepted(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        submit_for_review(s, workspace=tmp_path)
        accept(s, workspace=tmp_path)
        result = archive(s, reason="stale", workspace=tmp_path)
        assert result.status == SuggestionStatus.archived
        assert result.audit.archived_at is not None

    def test_archive_rejected(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        submit_for_review(s, workspace=tmp_path)
        reject(s, workspace=tmp_path)
        result = archive(s, workspace=tmp_path)
        assert result.status == SuggestionStatus.archived

    def test_archive_non_accepted_rejected_fails(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        with pytest.raises(ValueError):
            archive(s, workspace=tmp_path)

    def test_full_lifecycle(self, tmp_path: Path) -> None:
        s = LearningSuggestion(title="Test")
        submit_for_review(s, workspace=tmp_path)
        accept(s, reason="approved", workspace=tmp_path)
        archive(s, reason="done", workspace=tmp_path)
        assert len(s.audit.status_transitions) == 3
        assert s.status == SuggestionStatus.archived
