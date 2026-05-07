from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas_agent.leaderboard.roster import update_readme_roster


def _write_roster(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": "vals-finance-agent",
                "reference_only": True,
                "runtime_orchestration": False,
                "benchmark": {
                    "name": "Vals AI Finance Agent",
                    "url": "https://www.vals.ai/benchmarks/finance_agent",
                    "updated": "2026-05-04",
                },
                "models": [
                    {
                        "rank": 1,
                        "model_name": "Claude Opus 4.7",
                        "provider": "anthropic",
                        "score": 64.37,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_update_readme_roster_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "# My README\n\n"
        "<!-- ATLAS_MODEL_ROSTER_START -->\n"
        "<!-- ATLAS_MODEL_ROSTER_END -->\n",
        encoding="utf-8",
    )
    _write_roster(tmp_path / "configs" / "model_roster.yaml")
    monkeypatch.chdir(tmp_path)

    update_readme_roster()

    new_content = readme_path.read_text(encoding="utf-8")
    assert "<!-- ATLAS_MODEL_ROSTER_START -->" in new_content
    assert "<!-- ATLAS_MODEL_ROSTER_END -->" in new_content
    assert "| Rank | Model | Score |" in new_content
    assert "Claude Opus 4.7" in new_content


def test_update_readme_roster_missing_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    readme_path = tmp_path / "README.md"
    readme_path.write_text("No markers here.", encoding="utf-8")
    _write_roster(tmp_path / "configs" / "model_roster.yaml")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Missing <!-- ATLAS_MODEL_ROSTER_START -->"):
        update_readme_roster()
