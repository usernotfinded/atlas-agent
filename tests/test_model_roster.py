from __future__ import annotations

from pathlib import Path

from atlas_agent.leaderboard import roster
from atlas_agent.leaderboard.model_normalizer import load_model_mappings
from atlas_agent.leaderboard.roster import (
    doctor_roster,
    select_top_models,
    update_model_roster,
)
from atlas_agent.leaderboard.vals_finance_agent import BenchmarkEntry


def _write_sources(path: Path) -> None:
    path.write_text(
        """
vals_finance_agent:
  url: "https://example.invalid/finance_agent"
  top_n: 7
  fallback_cache: true

model_mappings:
  "Claude Opus 4.7":
    provider: "anthropic"
    env_key: "ANTHROPIC_API_KEY"
    model_id: "editable-placeholder"
  "Muse Spark":
    provider: "unsupported"
    env_key: "MINIMAX_API_KEY"
    model_id: "muse-spark"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_update_writes_model_roster_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    _write_sources(tmp_path / "configs" / "model_sources.yaml")
    monkeypatch.setattr(
        roster,
        "fetch_and_parse",
        lambda url: [
            BenchmarkEntry(1, "Claude Opus 4.7", "anthropic", 64.37),
            BenchmarkEntry(2, "Muse Spark", "minimax", 60.59),
        ],
    )

    result = update_model_roster()

    assert result.roster_path == tmp_path / "configs" / "model_roster.yaml"
    assert result.cache_path == tmp_path / ".atlas" / "cache" / "model_roster.json"
    assert "Claude Opus 4.7" in result.roster_path.read_text(encoding="utf-8")


def test_update_falls_back_to_cache_if_fetch_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    _write_sources(tmp_path / "configs" / "model_sources.yaml")
    cache_dir = tmp_path / ".atlas" / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "model_roster.json").write_text(
        """
{
  "models": [
    {
      "rank": 1,
      "model_name": "Cached Model",
      "provider": "anthropic",
      "score": 50.0,
      "benchmark_name": "Vals AI Finance Agent",
      "benchmark_url": "https://example.invalid",
      "benchmark_updated": "2026-05-04"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        roster,
        "fetch_and_parse",
        lambda url: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    result = update_model_roster()

    assert result.source == "cache"
    assert result.entries[0].model_name == "Cached Model"


def test_top_7_are_selected_and_unsupported_marked_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    _write_sources(tmp_path / "configs" / "model_sources.yaml")
    roster.write_roster(
        [
            BenchmarkEntry(1, "Claude Opus 4.7", "anthropic", 64.37),
            BenchmarkEntry(2, "Muse Spark", "minimax", 60.59),
        ]
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "configured-test-value")

    selected = select_top_models(7)

    assert len(selected) == 7
    assert selected[0].enabled is True
    assert selected[1].enabled is False
    assert "provider adapter unavailable" in selected[1].reason


def test_missing_env_vars_do_not_print_secret_values(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    _write_sources(tmp_path / "configs" / "model_sources.yaml")
    roster.write_roster([BenchmarkEntry(1, "Claude Opus 4.7", "anthropic", 64.37)])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-not-print-this-secret")

    output = "\n".join(doctor_roster())

    assert "do-not-print-this-secret" not in output
    assert "ANTHROPIC_API_KEY" not in output


def test_model_mappings_are_user_editable(tmp_path) -> None:
    sources = tmp_path / "model_sources.yaml"
    _write_sources(sources)

    mappings = load_model_mappings(sources)

    assert mappings["Claude Opus 4.7"].model_id == "editable-placeholder"
