from __future__ import annotations

import re
from pathlib import Path


README = Path(__file__).resolve().parents[1] / "README.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_positions_atlas_supervised_workspace() -> None:
    text = _readme()
    lower = text.lower()

    for phrase in (
        "broker-neutral",
        "supervised trading workspace",
        "control layer",
        "deterministic risk gates",
        "approval queues",
        "paper workflows",
        "live trading is disabled by default",
        "not financial advice",
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
        "magic ai trading bot",
        "autonomous profit system",
        "production-grade live",
        "makes money",
        "best broker",
        "recommended broker",
        "self-improving ai trading agent",
        "professional-grade toolset",
    )
    for phrase in forbidden:
        assert phrase not in lower

    assert re.search(r"\b(?:sk-|pplx-|xox[baprs]-|akia)[a-z0-9_-]{10,}", lower) is None


def test_readme_mentions_provider_neutral_model_selection() -> None:
    text = _readme()
    lower = text.lower()

    assert "https://www.vals.ai/benchmarks/finance_agent" in text
    assert "provider-neutral" in lower

    for provider in [
        "openrouter",
        "nvidia nim",
        "z.ai/glm",
        "kimi/moonshot",
        "hugging face",
        "openai",
    ]:
        assert provider in lower

    assert "custom endpoint" in lower or "openai-compatible" in lower

    assert "atlas_model_roster_start" not in lower
    assert "| rank | model | score |" not in lower
