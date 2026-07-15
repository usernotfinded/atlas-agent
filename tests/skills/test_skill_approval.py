# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/skills/test_skill_approval.py
# PURPOSE: Verifies skill approval behavior and regression expectations.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""Tests for skill candidate approval workflow."""
# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_agent.skills.models import SkillCandidate, SkillCandidateStatus
from atlas_agent.skills.storage import save_candidate, load_candidate
from atlas_agent.skills.approval import (
    submit_for_review,
    approve,
    reject,
    archive,
    promote_to_library,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestSkillCandidateApproval:
    def test_submit_for_review(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S")
        save_candidate(candidate, workspace=tmp_path)
        submit_for_review(candidate, workspace=tmp_path)
        assert candidate.status == SkillCandidateStatus.pending_review
        loaded = load_candidate(candidate.candidate_id, workspace=tmp_path)
        assert loaded.status == SkillCandidateStatus.pending_review

    def test_submit_for_review_only_from_draft(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.approved)
        with pytest.raises(ValueError, match="Only 'draft' candidates"):
            submit_for_review(candidate, workspace=tmp_path)

    def test_approve(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.pending_review)
        save_candidate(candidate, workspace=tmp_path)
        approve(candidate, reason="good", workspace=tmp_path)
        assert candidate.status == SkillCandidateStatus.approved
        assert candidate.audit.review_reason == "good"

    def test_approve_only_from_pending_review(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.draft)
        with pytest.raises(ValueError, match="Only 'pending_review' candidates"):
            approve(candidate, workspace=tmp_path)

    def test_reject(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.pending_review)
        save_candidate(candidate, workspace=tmp_path)
        reject(candidate, reason="incomplete", workspace=tmp_path)
        assert candidate.status == SkillCandidateStatus.rejected
        assert candidate.audit.review_reason == "incomplete"

    def test_reject_only_from_pending_review(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.draft)
        with pytest.raises(ValueError, match="Only 'pending_review' candidates"):
            reject(candidate, reason="incomplete", workspace=tmp_path)

    def test_archive_from_approved(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.approved)
        save_candidate(candidate, workspace=tmp_path)
        archive(candidate, reason="stale", workspace=tmp_path)
        assert candidate.status == SkillCandidateStatus.archived

    def test_archive_from_rejected(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.rejected)
        save_candidate(candidate, workspace=tmp_path)
        archive(candidate, workspace=tmp_path)
        assert candidate.status == SkillCandidateStatus.archived

    def test_archive_not_from_draft(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.draft)
        with pytest.raises(ValueError, match="Only 'approved' or 'rejected' candidates"):
            archive(candidate, workspace=tmp_path)

    def test_promote_to_library(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(
            title="T",
            summary="S",
            status=SkillCandidateStatus.approved,
            kind="report",
        )
        save_candidate(candidate, workspace=tmp_path)
        entry = promote_to_library(candidate, workspace=tmp_path)
        assert candidate.status == SkillCandidateStatus.promoted
        assert entry.title == candidate.title
        assert entry.source_candidate_id == candidate.candidate_id
        assert entry.activation_policy == "manual_only"
        loaded = load_candidate(candidate.candidate_id, workspace=tmp_path)
        assert loaded.status == SkillCandidateStatus.promoted

    def test_promote_to_library_only_from_approved(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="T", summary="S", status=SkillCandidateStatus.draft)
        with pytest.raises(ValueError, match="Only 'approved' candidates"):
            promote_to_library(candidate, workspace=tmp_path)
