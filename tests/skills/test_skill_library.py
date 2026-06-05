"""Tests for skill library storage."""
from __future__ import annotations

from pathlib import Path

import pytest

from atlas_agent.skills.models import SkillLibraryEntry
from atlas_agent.skills.library import (
    save_skill,
    load_skill,
    list_skills,
    delete_skill,
)


class TestSkillLibraryStorage:
    def test_save_and_load_skill(self, tmp_path: Path) -> None:
        entry = SkillLibraryEntry(title="Test Skill", summary="Summary")
        path = save_skill(entry, workspace=tmp_path)
        assert path.exists()
        loaded = load_skill(entry.skill_id, workspace=tmp_path)
        assert loaded.skill_id == entry.skill_id
        assert loaded.title == entry.title

    def test_list_skills(self, tmp_path: Path) -> None:
        e1 = SkillLibraryEntry(title="One", summary="First")
        e2 = SkillLibraryEntry(title="Two", summary="Second")
        save_skill(e1, workspace=tmp_path)
        save_skill(e2, workspace=tmp_path)
        items = list_skills(workspace=tmp_path)
        assert len(items) == 2
        ids = {i["skill_id"] for i in items}
        assert e1.skill_id in ids
        assert e2.skill_id in ids

    def test_delete_skill(self, tmp_path: Path) -> None:
        entry = SkillLibraryEntry(title="Delete Me", summary="...")
        save_skill(entry, workspace=tmp_path)
        delete_skill(entry.skill_id, workspace=tmp_path)
        with pytest.raises(FileNotFoundError):
            load_skill(entry.skill_id, workspace=tmp_path)

    def test_load_missing_skill_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_skill("nonexistent-id", workspace=tmp_path)

    def test_list_skills_empty(self, tmp_path: Path) -> None:
        assert list_skills(workspace=tmp_path) == []

    def test_list_skills_skips_malformed(self, tmp_path: Path) -> None:
        library_dir = tmp_path / ".atlas" / "skills" / "library"
        library_dir.mkdir(parents=True, exist_ok=True)
        (library_dir / "bad.json").write_text("not json", encoding="utf-8")
        assert list_skills(workspace=tmp_path) == []
