"""Honesty tests for learning.reflections.generate_reflection.

The function has no automated analysis behind it. It must therefore NOT emit
plausible-looking, invented insights (which read as if derived from the session),
and must instead state plainly that no analysis was performed — mirroring the
project's "No fake insights are invented" rule already implemented in
reflection/generator.py.
"""

from pathlib import Path

from atlas_agent.learning.reflections import generate_reflection


# Specific insights the pre-fix stub fabricated and presented as if derived from data.
_FABRICATED_INSIGHTS = (
    "Stick to daily position size limits",
    "Consider improving pre-market research depth",
    "Strategy execution followed risk gates",
    "No specific failures detected in latest session",
)


def _run(tmp_path: Path) -> str:
    reports_dir = tmp_path / "reports"
    path = generate_reflection(tmp_path / "memory", reports_dir)
    assert path.exists()
    return path.read_text(encoding="utf-8")


def test_reflection_does_not_fabricate_insights(tmp_path: Path) -> None:
    content = _run(tmp_path)
    for phrase in _FABRICATED_INSIGHTS:
        assert phrase not in content, f"reflection fabricated an insight: {phrase!r}"


def test_reflection_declares_no_automated_analysis(tmp_path: Path) -> None:
    content = _run(tmp_path).lower()
    assert "no automated analysis" in content
