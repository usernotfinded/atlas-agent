from __future__ import annotations

import re
from pathlib import Path


README = Path(__file__).resolve().parents[1] / "README.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_positions_hermes_self_improving_agent() -> None:
    text = _readme()
    lower = text.lower()

    for phrase in (
        "self-improving ai trading agent",
        "built by natan mucelli",
        "learning loop",
    ):
        assert phrase in lower

    assert re.search(r"^##\s+.*telegram", text, flags=re.IGNORECASE | re.MULTILINE)
    assert re.search(
        r"^##\s+.*(?:deployment|cloud)",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    for phrase in ("market-open", "broker adapters", "risk gates"):
        assert phrase in lower

    for phrase in ("closed-market", "learning", "simulation"):
        assert phrase in lower


def test_readme_avoids_forbidden_positioning_and_profit_claims() -> None:
    lower = _readme().lower()

    forbidden = (
        "experi" + "mental",
        "paper" + "-first",
        "guaranteed " + "profit",
        "profit " + "guarantee",
        "guaranteed " + "returns",
        "risk" + "-free",
        "risk " + "free",
        "will make " + "money",
        "sure " + "profit",
        "passive " + "income",
        "beat " + "the market",
    )
    for phrase in forbidden:
        assert phrase not in lower

    assert re.search(r"\b(?:sk-|pplx-|xox[baprs]-|akia)[a-z0-9_-]{10,}", lower) is None


def test_readme_model_roster_is_visible_guidance_not_runtime_orchestration() -> None:
    text = _readme()
    lower = text.lower()

    assert "<!-- ATLAS_MODEL_ROSTER_START -->" in text
    assert "<!-- ATLAS_MODEL_ROSTER_END -->" in text
    assert "| Rank | Model | Score |" in text
    assert "Vals AI Finance Agent" in text
    assert "model-selection guidance" in lower or "model selection guidance" in lower
    assert "recommended-model table in this README" in text
    assert re.search(
        r"not (?:a )?mandatory runtime orchestration",
        lower,
    )
