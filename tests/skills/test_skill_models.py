# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/skills/test_skill_models.py
# PURPOSE: Verifies skill models behavior and regression expectations.
# DEPS:    json, pytest, atlas_agent.
# ==============================================================================

"""Tests for skill candidate models."""
# --- IMPORTS ---

from __future__ import annotations

import json

import pytest

from atlas_agent.skills.models import (
    SkillCandidate,
    SkillCandidateStatus,
    SkillLibraryEntry,
    SkillProvenance,
    SkillAudit,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestSkillCandidateSchema:
    def test_candidate_defaults(self) -> None:
        candidate = SkillCandidate()
        assert candidate.artifact_type == "skill_candidate"
        assert candidate.schema_version == "1.0.0"
        assert candidate.status == SkillCandidateStatus.draft
        assert candidate.activation_policy == "manual_only"
        assert candidate.provenance.provider_execution_disabled is True
        assert candidate.provenance.static_fallback is True
        assert candidate.candidate_id

    def test_candidate_serialization_roundtrip(self) -> None:
        candidate = SkillCandidate(
            title="Test Skill",
            summary="A test skill candidate.",
            kind="report",
            provenance=SkillProvenance(
                source_reflection_id="ref-123",
                source_path="/tmp/test.md",
                source_kind="report",
            ),
            limitations=["limitation 1"],
            safety_notes=["safety 1"],
        )
        data = candidate.model_dump(mode="json")
        restored = SkillCandidate.model_validate(data)
        assert restored.title == candidate.title
        assert restored.summary == candidate.summary
        assert restored.kind == candidate.kind

    def test_record_transition_draft_to_pending(self) -> None:
        candidate = SkillCandidate()
        candidate.record_transition(SkillCandidateStatus.pending_review, actor="test")
        assert candidate.status == SkillCandidateStatus.pending_review
        assert candidate.audit.submitted_for_review_at is not None
        assert len(candidate.audit.status_transitions) == 1

    def test_record_transition_pending_to_approved(self) -> None:
        candidate = SkillCandidate(status=SkillCandidateStatus.pending_review)
        candidate.record_transition(SkillCandidateStatus.approved, actor="test", reason="looks good")
        assert candidate.status == SkillCandidateStatus.approved
        assert candidate.audit.reviewed_at is not None
        assert candidate.audit.reviewed_by == "test"
        assert candidate.audit.review_reason == "looks good"

    def test_record_transition_pending_to_rejected(self) -> None:
        candidate = SkillCandidate(status=SkillCandidateStatus.pending_review)
        candidate.record_transition(SkillCandidateStatus.rejected, actor="test", reason="incomplete")
        assert candidate.status == SkillCandidateStatus.rejected
        assert candidate.audit.review_reason == "incomplete"

    def test_record_transition_approved_to_archived(self) -> None:
        candidate = SkillCandidate(status=SkillCandidateStatus.approved)
        candidate.record_transition(SkillCandidateStatus.archived, actor="test")
        assert candidate.status == SkillCandidateStatus.archived
        assert candidate.audit.archived_at is not None

    def test_record_transition_approved_to_promoted(self) -> None:
        candidate = SkillCandidate(status=SkillCandidateStatus.approved)
        candidate.record_transition(SkillCandidateStatus.promoted, actor="test")
        assert candidate.status == SkillCandidateStatus.promoted
        assert candidate.audit.promoted_at is not None

    def test_disclaimer_present(self) -> None:
        candidate = SkillCandidate()
        assert "not financial advice" in candidate.disclaimer.lower()
        assert "not automatically active" in candidate.disclaimer.lower()


class TestSkillLibraryEntrySchema:
    def test_library_entry_defaults(self) -> None:
        entry = SkillLibraryEntry()
        assert entry.artifact_type == "skill_library_entry"
        assert entry.schema_version == "1.0.0"
        assert entry.activation_policy == "manual_only"
        assert entry.skill_id

    def test_library_entry_serialization_roundtrip(self) -> None:
        entry = SkillLibraryEntry(
            title="Promoted Skill",
            summary="A promoted skill.",
            kind="backtest",
            source_candidate_id="cand-123",
        )
        data = entry.model_dump(mode="json")
        restored = SkillLibraryEntry.model_validate(data)
        assert restored.title == entry.title
        assert restored.source_candidate_id == entry.source_candidate_id

    def test_library_entry_disclaimer(self) -> None:
        entry = SkillLibraryEntry()
        assert "not financial advice" in entry.disclaimer.lower()
        assert "not automatically active" in entry.disclaimer.lower()
