# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/reflection/test_reflection_models.py
# PURPOSE: Verifies reflection models behavior and regression expectations.
# DEPS:    pytest, atlas_agent.
# ==============================================================================

"""Tests for atlas_agent.reflection.models."""
# --- IMPORTS ---

from __future__ import annotations

import pytest

from atlas_agent.reflection.models import (
    AuditMetadata,
    ProvenanceMetadata,
    ReflectionArtifact,
    ReflectionInput,
    ReflectionOutput,
    ReflectionStatus,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestReflectionStatus:
    def test_enum_values(self):
        assert ReflectionStatus.draft.value == "draft"
        assert ReflectionStatus.pending_review.value == "pending_review"
        assert ReflectionStatus.approved.value == "approved"
        assert ReflectionStatus.rejected.value == "rejected"
        assert ReflectionStatus.archived.value == "archived"


class TestReflectionArtifact:
    def test_default_status_is_draft(self):
        artifact = ReflectionArtifact(
            provenance=ProvenanceMetadata(input_artifact=ReflectionInput(kind="report", path="test.md"))
        )
        assert artifact.status == ReflectionStatus.draft
        assert artifact.reflection_id
        assert artifact.artifact_type == "reflection"

    def test_record_transition_to_pending_review(self):
        artifact = ReflectionArtifact(
            provenance=ProvenanceMetadata(input_artifact=ReflectionInput(kind="report", path="test.md"))
        )
        artifact.record_transition(ReflectionStatus.pending_review, actor="test")
        assert artifact.status == ReflectionStatus.pending_review
        assert artifact.audit.submitted_for_review_at is not None
        assert len(artifact.audit.status_transitions) == 1

    def test_record_transition_to_approved(self):
        artifact = ReflectionArtifact(
            provenance=ProvenanceMetadata(input_artifact=ReflectionInput(kind="report", path="test.md"))
        )
        artifact.record_transition(ReflectionStatus.pending_review, actor="test")
        artifact.record_transition(ReflectionStatus.approved, actor="reviewer", reason="good")
        assert artifact.status == ReflectionStatus.approved
        assert artifact.audit.reviewed_by == "reviewer"
        assert artifact.audit.review_reason == "good"

    def test_record_transition_to_rejected(self):
        artifact = ReflectionArtifact(
            provenance=ProvenanceMetadata(input_artifact=ReflectionInput(kind="report", path="test.md"))
        )
        artifact.record_transition(ReflectionStatus.pending_review, actor="test")
        artifact.record_transition(ReflectionStatus.rejected, actor="reviewer", reason="bad")
        assert artifact.status == ReflectionStatus.rejected
        assert artifact.audit.review_reason == "bad"

    def test_record_transition_to_archived(self):
        artifact = ReflectionArtifact(
            provenance=ProvenanceMetadata(input_artifact=ReflectionInput(kind="report", path="test.md"))
        )
        artifact.record_transition(ReflectionStatus.pending_review, actor="test")
        artifact.record_transition(ReflectionStatus.approved, actor="reviewer")
        artifact.record_transition(ReflectionStatus.archived, actor="system")
        assert artifact.status == ReflectionStatus.archived
        assert artifact.audit.archived_at is not None

    def test_json_serializable(self):
        artifact = ReflectionArtifact(
            provenance=ProvenanceMetadata(input_artifact=ReflectionInput(kind="report", path="test.md"))
        )
        data = artifact.model_dump(mode="json")
        assert data["status"] == "draft"
        assert data["artifact_type"] == "reflection"

    def test_disclaimer_present(self):
        artifact = ReflectionArtifact(
            provenance=ProvenanceMetadata(input_artifact=ReflectionInput(kind="report", path="test.md"))
        )
        assert "not financial advice" in artifact.disclaimer.lower()
        assert "operator review" in artifact.disclaimer.lower()

    def test_no_secrets_in_default_artifact(self):
        artifact = ReflectionArtifact(
            provenance=ProvenanceMetadata(input_artifact=ReflectionInput(kind="report", path="test.md"))
        )
        dumped = str(artifact.model_dump())
        assert "sk-" not in dumped.lower()
        assert "api_key" not in dumped.lower()
        assert "token" not in dumped.lower()
