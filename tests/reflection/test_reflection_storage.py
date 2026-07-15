# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/reflection/test_reflection_storage.py
# PURPOSE: Verifies reflection storage behavior and regression expectations.
# DEPS:    tempfile, pathlib, pytest, atlas_agent.
# ==============================================================================

"""Tests for atlas_agent.reflection.storage."""
# --- IMPORTS ---

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from atlas_agent.reflection.models import (
    ProvenanceMetadata,
    ReflectionArtifact,
    ReflectionInput,
    ReflectionStatus,
)
from atlas_agent.reflection.storage import (
    delete_artifact,
    list_artifacts,
    load_artifact,
    save_artifact,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _sample_artifact(path: str = "test.md") -> ReflectionArtifact:
    return ReflectionArtifact(
        provenance=ProvenanceMetadata(
            input_artifact=ReflectionInput(kind="report", path=path)
        )
    )


class TestSaveArtifact:
    def test_creates_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact()
            path = save_artifact(artifact, workspace=tmpdir)
            assert path.exists()
            assert path.name == f"{artifact.reflection_id}.json"

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact()
            path = save_artifact(artifact, workspace=tmpdir)
            assert (Path(tmpdir) / ".atlas" / "reflections").exists()


class TestLoadArtifact:
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact()
            save_artifact(artifact, workspace=tmpdir)
            loaded = load_artifact(artifact.reflection_id, workspace=tmpdir)
            assert loaded.reflection_id == artifact.reflection_id
            assert loaded.status == artifact.status

    def test_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                load_artifact("nonexistent", workspace=tmpdir)


class TestListArtifacts:
    def test_empty_when_no_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert list_artifacts(workspace=tmpdir) == []

    def test_lists_saved_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact()
            save_artifact(artifact, workspace=tmpdir)
            results = list_artifacts(workspace=tmpdir)
            assert len(results) == 1
            assert results[0]["reflection_id"] == artifact.reflection_id
            assert results[0]["status"] == "draft"

    def test_filter_by_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact()
            save_artifact(artifact, workspace=tmpdir)
            artifact.status = ReflectionStatus.approved
            save_artifact(artifact, workspace=tmpdir)
            results = list_artifacts(workspace=tmpdir, status=ReflectionStatus.draft)
            assert len(results) == 0
            results = list_artifacts(workspace=tmpdir, status=ReflectionStatus.approved)
            assert len(results) == 1

    def test_skips_malformed_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reflections_dir = Path(tmpdir) / ".atlas" / "reflections"
            reflections_dir.mkdir(parents=True)
            (reflections_dir / "bad.json").write_text("not json", encoding="utf-8")
            results = list_artifacts(workspace=tmpdir)
            assert results == []


class TestDeleteArtifact:
    def test_deletes_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = _sample_artifact()
            save_artifact(artifact, workspace=tmpdir)
            delete_artifact(artifact.reflection_id, workspace=tmpdir)
            with pytest.raises(FileNotFoundError):
                load_artifact(artifact.reflection_id, workspace=tmpdir)

    def test_delete_missing_is_no_op(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            delete_artifact("nonexistent", workspace=tmpdir)
