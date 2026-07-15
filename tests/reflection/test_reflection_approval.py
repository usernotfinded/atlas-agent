# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/reflection/test_reflection_approval.py
# PURPOSE: Verifies reflection approval behavior and regression expectations.
# DEPS:    tempfile, pytest, atlas_agent.
# ==============================================================================

"""Tests for atlas_agent.reflection.approval."""
# --- IMPORTS ---

from __future__ import annotations

import tempfile

import pytest

from atlas_agent.reflection.approval import approve, archive, reject, submit_for_review
from atlas_agent.reflection.models import (
    ProvenanceMetadata,
    ReflectionArtifact,
    ReflectionInput,
    ReflectionStatus,
)
from atlas_agent.reflection.storage import load_artifact, save_artifact


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _sample_artifact(tmpdir: str) -> ReflectionArtifact:
    artifact = ReflectionArtifact(
        provenance=ProvenanceMetadata(
            input_artifact=ReflectionInput(kind="report", path="test.md")
        )
    )
    save_artifact(artifact, workspace=tmpdir)
    return artifact


class TestSubmitForReview:
    def test_submits_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            submit_for_review(artifact, workspace=tmpdir)
            assert artifact.status == ReflectionStatus.pending_review
            loaded = load_artifact(artifact.reflection_id, workspace=tmpdir)
            assert loaded.status == ReflectionStatus.pending_review

    def test_rejects_non_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            submit_for_review(artifact, workspace=tmpdir)
            with pytest.raises(ValueError):
                submit_for_review(artifact, workspace=tmpdir)


class TestApprove:
    def test_approves_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            submit_for_review(artifact, workspace=tmpdir)
            approve(artifact, reason="good", workspace=tmpdir)
            assert artifact.status == ReflectionStatus.approved
            assert artifact.audit.review_reason == "good"

    def test_rejects_non_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            with pytest.raises(ValueError):
                approve(artifact, workspace=tmpdir)


class TestReject:
    def test_rejects_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            submit_for_review(artifact, workspace=tmpdir)
            reject(artifact, reason="incomplete", workspace=tmpdir)
            assert artifact.status == ReflectionStatus.rejected
            assert artifact.audit.review_reason == "incomplete"

    def test_rejects_non_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            with pytest.raises(ValueError):
                reject(artifact, reason="bad", workspace=tmpdir)


class TestArchive:
    def test_archives_approved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            submit_for_review(artifact, workspace=tmpdir)
            approve(artifact, workspace=tmpdir)
            archive(artifact, reason="old", workspace=tmpdir)
            assert artifact.status == ReflectionStatus.archived
            assert artifact.audit.archived_at is not None

    def test_archives_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            submit_for_review(artifact, workspace=tmpdir)
            reject(artifact, reason="bad", workspace=tmpdir)
            archive(artifact, workspace=tmpdir)
            assert artifact.status == ReflectionStatus.archived

    def test_rejects_archiving_draft(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact(tmpdir)
            with pytest.raises(ValueError):
                archive(artifact, workspace=tmpdir)
