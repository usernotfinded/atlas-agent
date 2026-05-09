from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"


def test_readme_is_research_neutral() -> None:
    content = README.read_text(encoding="utf-8").lower()
    # Should not mention Perplexity in a way that implies it's the only/default option
    # Generic tools description should be neutral
    assert "web research" in content
    assert "perplexity" not in content


def test_contributing_is_research_neutral() -> None:
    content = CONTRIBUTING.read_text(encoding="utf-8").lower()
    assert "web research" in content or "market data" in content
    assert "perplexity" not in content


def test_no_perplexity_as_primary_env_var_in_docs() -> None:
    docs_dir = ROOT / "docs"
    for path in docs_dir.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        # If it mentions an API key, it should prefer ATLAS_RESEARCH_API_KEY
        if "API_KEY" in content:
            assert "PERPLEXITY_API_KEY" not in content or "ATLAS_RESEARCH_API_KEY" in content


def test_docs_do_not_prefer_perplexity() -> None:
    for path in [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]:
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "perplexity api" not in lowered
        assert "default perplexity" not in lowered
        assert "recommended perplexity" not in lowered
        assert "preferred perplexity" not in lowered
