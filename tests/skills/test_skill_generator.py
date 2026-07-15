# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/skills/test_skill_generator.py
# PURPOSE: Verifies skill generator behavior and regression expectations.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

"""Tests for skill candidate generator."""
# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_agent.reflection.models import (
    ReflectionArtifact,
    ReflectionInput,
    ReflectionOutput,
    ProvenanceMetadata,
)
from atlas_agent.skills.generator import (
    generate_candidate_from_reflection,
    generate_candidate_from_input,
)
from atlas_agent.skills.models import SkillCandidateStatus


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class TestSkillCandidateGenerator:
    def test_generate_from_reflection(self) -> None:
        reflection = ReflectionArtifact(
            provenance=ProvenanceMetadata(
                input_artifact=ReflectionInput(
                    kind="report",
                    path="/tmp/report.md",
                    description="Test report",
                ),
            ),
            output=ReflectionOutput(summary="Test reflection"),
        )
        candidate = generate_candidate_from_reflection(reflection)
        assert candidate.status == SkillCandidateStatus.draft
        assert candidate.provenance.source_reflection_id == reflection.reflection_id
        assert candidate.provenance.source_kind == "report"
        assert candidate.provenance.provider_execution_disabled is True
        assert candidate.activation_policy == "manual_only"
        assert "not financial advice" in candidate.disclaimer.lower()

    def test_generate_from_reflection_preserves_provider_disabled(self) -> None:
        reflection = ReflectionArtifact(
            provenance=ProvenanceMetadata(
                input_artifact=ReflectionInput(kind="backtest", path="/tmp/bt.md"),
            ),
            output=ReflectionOutput(
                summary="Backtest reflection",
                provider_execution_disabled=True,
            ),
        )
        candidate = generate_candidate_from_reflection(reflection)
        assert candidate.provenance.provider_execution_disabled is True
        assert candidate.provenance.static_fallback is True

    def test_generate_from_input_file(self, tmp_path: Path) -> None:
        input_file = tmp_path / "report.md"
        input_file.write_text("# Report\n\nSome data.\n", encoding="utf-8")
        candidate = generate_candidate_from_input(input_file, kind="report")
        assert candidate.status == SkillCandidateStatus.draft
        assert candidate.provenance.source_path == str(input_file)
        assert candidate.provenance.source_kind == "report"
        assert candidate.title == "Report"
        assert candidate.activation_policy == "manual_only"

    def test_generate_from_input_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.md"
        candidate = generate_candidate_from_input(missing, kind="note")
        assert candidate.title == "Untitled note skill candidate"
        assert "No input data available" in candidate.summary
        assert any("No input data was available" in lim for lim in candidate.limitations)

    def test_generate_from_input_detects_kind_from_path(self, tmp_path: Path) -> None:
        backtest_file = tmp_path / "backtest_result.md"
        backtest_file.write_text("# Backtest\n", encoding="utf-8")
        candidate = generate_candidate_from_input(backtest_file)
        assert candidate.provenance.source_kind == "backtest"

    def test_generate_from_input_no_auto_activation(self, tmp_path: Path) -> None:
        input_file = tmp_path / "note.md"
        input_file.write_text("Note", encoding="utf-8")
        candidate = generate_candidate_from_input(input_file)
        assert candidate.activation_policy == "manual_only"
        assert any("not automatically active" in note.lower() for note in candidate.safety_notes)
