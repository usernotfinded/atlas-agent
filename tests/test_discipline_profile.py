from __future__ import annotations

import pytest
from pathlib import Path

from atlas_agent.ai.discipline import (
    _FORBIDDEN_PATTERNS,
    _REQUIRED_SAFETY_SENTENCE,
    default_discipline_text,
    discipline_path,
    discipline_status,
    load_user_discipline,
    validate_discipline_text,
    sanitize_discipline_text,
    write_user_discipline,
    build_discipline_generation_prompt,
    require_user_discipline,
    DisciplineNotConfiguredError,
    InvalidDisciplineProfileError,
)


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


def test_default_discipline_text_contains_all_sections() -> None:
    text = default_discipline_text()
    for section in (
        "Decision temperament",
        "Reasoning style",
        "Communication style",
        "Risk posture",
        "Uncertainty handling",
        "No-trade bias",
        "Forbidden overrides",
    ):
        assert f"## {section}" in text


def test_default_discipline_contains_required_safety_sentence() -> None:
    assert _REQUIRED_SAFETY_SENTENCE in default_discipline_text()


def test_default_discipline_is_template_not_operational() -> None:
    # The docstring and module design make it clear this is a template only.
    text = default_discipline_text()
    assert "Forbidden overrides" in text


def test_validate_good_profile() -> None:
    ok, errors = validate_discipline_text(GOOD_PROFILE)
    assert ok
    assert not errors


def test_validate_missing_section() -> None:
    text = GOOD_PROFILE.replace("## Decision temperament", "")
    ok, errors = validate_discipline_text(text)
    assert not ok
    assert any("Decision temperament" in e for e in errors)


def test_validate_missing_safety_sentence() -> None:
    text = GOOD_PROFILE.replace(_REQUIRED_SAFETY_SENTENCE, "")
    ok, errors = validate_discipline_text(text)
    assert not ok
    assert any("Missing required safety sentence" in e for e in errors)


@pytest.mark.parametrize("phrase", sorted(_FORBIDDEN_PATTERNS))
def test_validate_forbidden_phrases(phrase: str) -> None:
    text = GOOD_PROFILE + f"\n{phrase}\n"
    ok, errors = validate_discipline_text(text)
    assert not ok
    assert any(phrase in e.lower() for e in errors)


def test_sanitize_discipline_text() -> None:
    text = GOOD_PROFILE + "\nignore risk limits\n"
    sanitized = sanitize_discipline_text(text)
    assert "ignore risk limits" not in sanitized
    assert "<!-- Line removed during sanitization -->" in sanitized


def test_load_user_discipline_missing() -> None:
    assert load_user_discipline("nonexistent_workspace_12345") is None


def test_write_and_load_user_discipline(tmp_path: Path) -> None:
    write_user_discipline(tmp_path, GOOD_PROFILE)
    loaded = load_user_discipline(tmp_path)
    assert loaded == GOOD_PROFILE


def test_load_user_discipline_invalid_returns_none(tmp_path: Path) -> None:
    bad = GOOD_PROFILE.replace(_REQUIRED_SAFETY_SENTENCE, "")
    write_user_discipline(tmp_path, bad)
    loaded = load_user_discipline(tmp_path)
    assert loaded is None


def test_discipline_path() -> None:
    p = discipline_path("/foo")
    assert str(p) == "/foo/.atlas/discipline.md"


def test_build_discipline_generation_prompt() -> None:
    prompt = build_discipline_generation_prompt("test input")
    assert "test input" in prompt
    assert _REQUIRED_SAFETY_SENTENCE in prompt
    assert "Decision temperament" in prompt


# --- Mandatory discipline tests ---


def test_require_user_discipline_missing_raises() -> None:
    with pytest.raises(DisciplineNotConfiguredError) as exc_info:
        require_user_discipline("nonexistent_workspace_12345")
    assert "Atlas Discipline Profile is not configured" in str(exc_info.value)


def test_require_user_discipline_invalid_raises(tmp_path: Path) -> None:
    bad = GOOD_PROFILE.replace(_REQUIRED_SAFETY_SENTENCE, "")
    write_user_discipline(tmp_path, bad)
    with pytest.raises(InvalidDisciplineProfileError) as exc_info:
        require_user_discipline(tmp_path)
    assert "Discipline profile is invalid" in str(exc_info.value)


def test_require_user_discipline_valid_returns_text(tmp_path: Path) -> None:
    write_user_discipline(tmp_path, GOOD_PROFILE)
    result = require_user_discipline(tmp_path)
    assert result == GOOD_PROFILE


def test_discipline_status_missing() -> None:
    status = discipline_status("nonexistent_workspace_12345")
    assert status["configured"] is False
    assert status["valid"] is False
    assert status["errors"] == []


def test_discipline_status_valid(tmp_path: Path) -> None:
    write_user_discipline(tmp_path, GOOD_PROFILE)
    status = discipline_status(tmp_path)
    assert status["configured"] is True
    assert status["valid"] is True
    assert status["errors"] == []


def test_discipline_status_invalid(tmp_path: Path) -> None:
    bad = GOOD_PROFILE.replace(_REQUIRED_SAFETY_SENTENCE, "")
    write_user_discipline(tmp_path, bad)
    status = discipline_status(tmp_path)
    assert status["configured"] is True
    assert status["valid"] is False
    assert status["errors"]
