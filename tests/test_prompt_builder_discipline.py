# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_prompt_builder_discipline.py
# PURPOSE: Verifies prompt builder discipline behavior and regression
#         expectations.
# DEPS:    pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_agent.ai.prompt_builder import build_system_prompt, build_agent_system_prompt
from atlas_agent.ai.discipline import (
    default_discipline_text,
    _REQUIRED_SAFETY_SENTENCE,
    write_user_discipline,
    DisciplineNotConfiguredError,
)


# --- CONFIGURATION AND CONSTANTS ---

GOOD_PROFILE = (
    "# Profile\n\n"
    "## Decision temperament\n\nCautious.\n\n"
    "## Reasoning style\n\nStep-by-step.\n\n"
    "## Communication style\n\nConcise.\n\n"
    "## Risk posture\n\nConservative.\n\n"
    "## Uncertainty handling\n\nExplicit.\n\n"
    "## No-trade bias\n\nDefault to hold.\n\n"
    "## Forbidden overrides\n\n"
    f"{_REQUIRED_SAFETY_SENTENCE}\n"
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_build_system_prompt_without_user_discipline(tmp_path: Path) -> None:
    """build_system_prompt is for non-agentic contexts and may include the default template."""
    prompt = build_system_prompt(tmp_path)
    assert "AI trading analyst" in prompt
    assert "# Discipline Profile" in prompt
    assert default_discipline_text() in prompt
    assert "# User Overrides" not in prompt


def test_build_system_prompt_with_user_discipline(tmp_path: Path) -> None:
    write_user_discipline(tmp_path, GOOD_PROFILE)
    prompt = build_system_prompt(tmp_path)
    assert "AI trading analyst" in prompt
    assert "# Discipline Profile" in prompt
    assert default_discipline_text() in prompt
    assert "# User Overrides" in prompt
    assert GOOD_PROFILE in prompt


def test_build_agent_system_prompt_without_user_discipline_fails(tmp_path: Path) -> None:
    """build_agent_system_prompt is for agentic workflows and must fail closed."""
    with pytest.raises(DisciplineNotConfiguredError):
        build_agent_system_prompt(tmp_path)


def test_build_agent_system_prompt_with_user_discipline_succeeds(tmp_path: Path) -> None:
    write_user_discipline(tmp_path, GOOD_PROFILE)
    prompt = build_agent_system_prompt(tmp_path)
    assert "AI trading analyst" in prompt
    assert "# Discipline Profile" in prompt
    assert GOOD_PROFILE in prompt
    assert default_discipline_text() not in prompt


def test_build_agent_system_prompt_invalid_user_discipline_fails(tmp_path: Path) -> None:
    bad = GOOD_PROFILE.replace(_REQUIRED_SAFETY_SENTENCE, "")
    write_user_discipline(tmp_path, bad)
    from atlas_agent.ai.discipline import InvalidDisciplineProfileError
    with pytest.raises(InvalidDisciplineProfileError):
        build_agent_system_prompt(tmp_path)
