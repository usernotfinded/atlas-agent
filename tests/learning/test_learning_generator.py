# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/learning/test_learning_generator.py
# PURPOSE: Verifies learning generator behavior and regression expectations.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""Tests for learning suggestion generator."""
# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_agent.learning.generator import (
    generate_suggestion_from_input,
    generate_suggestion_from_reflection,
    generate_suggestion_from_skill,
)
from atlas_agent.learning.models import LearningSuggestion, SuggestionStatus


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestGenerateFromInput:
    def test_from_existing_file(self, tmp_path: Path) -> None:
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n\nSome data.\n", encoding="utf-8")
        s = generate_suggestion_from_input(input_file, workspace=tmp_path)
        assert isinstance(s, LearningSuggestion)
        assert s.status == SuggestionStatus.draft
        assert s.provenance.provider_execution_disabled is True
        assert s.execution_policy == "advisory_only"
        assert "Report" in s.title

    def test_missing_input(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.md"
        s = generate_suggestion_from_input(missing, workspace=tmp_path)
        assert "No input data available" in s.summary
        assert s.provenance.provider_execution_disabled is True

    def test_kind_override(self, tmp_path: Path) -> None:
        input_file = tmp_path / "note.md"
        input_file.write_text("Note content", encoding="utf-8")
        s = generate_suggestion_from_input(input_file, kind="backtest", workspace=tmp_path)
        assert s.kind == "backtest"

    def test_dry_run_default(self, tmp_path: Path) -> None:
        input_file = tmp_path / "note.md"
        input_file.write_text("Note content", encoding="utf-8")
        s = generate_suggestion_from_input(input_file, workspace=tmp_path)
        assert s.provenance.static_fallback is True

    def test_safety_notes_present(self, tmp_path: Path) -> None:
        input_file = tmp_path / "note.md"
        input_file.write_text("Note content", encoding="utf-8")
        s = generate_suggestion_from_input(input_file, workspace=tmp_path)
        assert any("Not financial advice" in note for note in s.safety_notes)
        assert any("Not automatically executable" in note for note in s.safety_notes)


class TestGenerateFromReflection:
    def test_from_reflection(self, tmp_path: Path) -> None:
        s = generate_suggestion_from_reflection(
            reflection_id="ref-123",
            reflection_path=str(tmp_path / "reflection.md"),
            reflection_text="# Reflection\n\nObservations.\n",
            workspace=tmp_path,
        )
        assert s.kind == "reflection"
        assert s.provenance.source_reflection_id == "ref-123"
        assert s.execution_policy == "advisory_only"
        assert s.provenance.provider_execution_disabled is True

    def test_missing_reflection_text(self, tmp_path: Path) -> None:
        s = generate_suggestion_from_reflection(
            reflection_id="ref-123",
            reflection_path=str(tmp_path / "reflection.md"),
            reflection_text="",
            workspace=tmp_path,
        )
        assert "No input data available" in s.summary


class TestGenerateFromSkill:
    def test_from_skill(self, tmp_path: Path) -> None:
        s = generate_suggestion_from_skill(
            skill_id="skill-123",
            skill_path=str(tmp_path / "skill.md"),
            skill_text="# Skill\n\nLimitations.\n",
            workspace=tmp_path,
        )
        assert s.kind == "skill"
        assert s.provenance.source_skill_id == "skill-123"
        assert s.execution_policy == "advisory_only"
        assert s.provenance.provider_execution_disabled is True

    def test_missing_skill_text(self, tmp_path: Path) -> None:
        s = generate_suggestion_from_skill(
            skill_id="skill-123",
            skill_path=str(tmp_path / "skill.md"),
            skill_text="",
            workspace=tmp_path,
        )
        assert "No input data available" in s.summary
