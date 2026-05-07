from __future__ import annotations

from atlas_agent.cli import main, run_once
from atlas_agent.ai.committee import AICommittee, COMMITTEE_ROLES
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order_router import OrderRouter
from atlas_agent.leaderboard import roster
from atlas_agent.leaderboard.roster import assign_committee_roles
from atlas_agent.leaderboard.vals_finance_agent import BenchmarkEntry


def _write_sources(tmp_path) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "model_sources.yaml").write_text(
        """
vals_finance_agent:
  url: "https://example.invalid/finance_agent"
  top_n: 7
  fallback_cache: true

model_mappings:
  "Claude Opus 4.7":
    provider: "anthropic"
    env_key: "ANTHROPIC_API_KEY"
    model_id: "claude-opus-4-7"
  "DeepSeek V4":
    provider: "openai_compatible"
    env_key: "DEEPSEEK_API_KEY"
    model_id: "deepseek-v4"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_models_auto_loads_roster_and_assigns_roles(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_sources(tmp_path)
    roster.write_roster(
        [
            BenchmarkEntry(1, "Claude Opus 4.7", "anthropic", 64.37),
            BenchmarkEntry(2, "DeepSeek V4", "deepseek", 60.39),
        ]
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    assignment = assign_committee_roles()

    assert len(assignment.roles) == 7
    assert COMMITTEE_ROLES[0] == "Lead Financial Analyst"
    assert AICommittee.assign_roles_from_roster().roles[0].role == COMMITTEE_ROLES[0]
    assert assignment.roles[0].role == "Lead Financial Analyst"
    assert assignment.fallback_used is True
    assert assignment.roles[0].model_name == "Claude Opus 4.7"


def test_fewer_than_7_configured_models_uses_fallback_assignment(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_sources(tmp_path)
    roster.write_roster([BenchmarkEntry(1, "Claude Opus 4.7", "anthropic", 64.37)])

    assignment = assign_committee_roles()

    assert assignment.fallback_used is True
    assert "fallback role assignment used" in assignment.message
    assert all(role.enabled is False for role in assignment.roles)


def test_run_once_models_auto_does_not_bypass_order_router(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_sources(tmp_path)
    calls = {"count": 0}
    original_route = OrderRouter.route

    def spy_route(self, *args, **kwargs):
        calls["count"] += 1
        return original_route(self, *args, **kwargs)

    monkeypatch.setattr(OrderRouter, "route", spy_route)

    result = run_once(
        "paper",
        config=AtlasConfig(
            data_path=tmp_path / "data" / "sample" / "ohlcv.csv",
            memory_dir=tmp_path / "memory",
            audit_dir=tmp_path / "audit",
            pending_orders_dir=tmp_path / "pending_orders",
            reports_dir=tmp_path / "reports",
        ),
        models="auto",
    )

    assert result.status == "filled"
    assert calls["count"] == 1


def test_routine_models_auto_cli_reports_fallback(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _write_sources(tmp_path)

    assert main(["routine", "run", "pre_market", "--mode", "paper", "--models", "auto"]) == 0

    assert "fallback role assignment used" in capsys.readouterr().out
