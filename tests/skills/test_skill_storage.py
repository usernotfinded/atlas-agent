"""Tests for skill candidate storage."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlas_agent.skills.models import SkillCandidate, SkillCandidateStatus
from atlas_agent.skills.storage import (
    save_candidate,
    load_candidate,
    list_candidates,
    delete_candidate,
)


class TestSkillCandidateStorage:
    def test_save_and_load_candidate(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="Test", summary="Summary")
        path = save_candidate(candidate, workspace=tmp_path)
        assert path.exists()
        loaded = load_candidate(candidate.candidate_id, workspace=tmp_path)
        assert loaded.candidate_id == candidate.candidate_id
        assert loaded.title == candidate.title

    def test_list_candidates(self, tmp_path: Path) -> None:
        c1 = SkillCandidate(title="One", summary="First")
        c2 = SkillCandidate(title="Two", summary="Second")
        save_candidate(c1, workspace=tmp_path)
        save_candidate(c2, workspace=tmp_path)
        items = list_candidates(workspace=tmp_path)
        assert len(items) == 2
        ids = {i["candidate_id"] for i in items}
        assert c1.candidate_id in ids
        assert c2.candidate_id in ids

    def test_list_candidates_with_status_filter(self, tmp_path: Path) -> None:
        c1 = SkillCandidate(title="Draft", summary="Draft", status=SkillCandidateStatus.draft)
        c2 = SkillCandidate(title="Approved", summary="Approved", status=SkillCandidateStatus.approved)
        save_candidate(c1, workspace=tmp_path)
        save_candidate(c2, workspace=tmp_path)
        items = list_candidates(workspace=tmp_path, status=SkillCandidateStatus.approved)
        assert len(items) == 1
        assert items[0]["status"] == "approved"

    def test_delete_candidate(self, tmp_path: Path) -> None:
        candidate = SkillCandidate(title="Delete Me", summary="...")
        save_candidate(candidate, workspace=tmp_path)
        delete_candidate(candidate.candidate_id, workspace=tmp_path)
        with pytest.raises(FileNotFoundError):
            load_candidate(candidate.candidate_id, workspace=tmp_path)

    def test_load_missing_candidate_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_candidate("nonexistent-id", workspace=tmp_path)

    def test_list_candidates_empty(self, tmp_path: Path) -> None:
        assert list_candidates(workspace=tmp_path) == []

    def test_list_candidates_skips_malformed(self, tmp_path: Path) -> None:
        candidates_dir = tmp_path / ".atlas" / "skill_candidates"
        candidates_dir.mkdir(parents=True, exist_ok=True)
        (candidates_dir / "bad.json").write_text("not json", encoding="utf-8")
        assert list_candidates(workspace=tmp_path) == []
