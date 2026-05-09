from __future__ import annotations

from pathlib import Path

from atlas_agent.agent.context import ContextComposer
from atlas_agent.agent.session import Session


def _prepare_workspace(root: Path) -> None:
    (root / "memory").mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "active").mkdir(parents=True, exist_ok=True)


def test_missing_memory_files_do_not_crash(tmp_path: Path) -> None:
    _prepare_workspace(tmp_path)
    composer = ContextComposer(tmp_path)

    composed = composer.compose(trust_mode="manual")

    assert composed.system_prompt
    assert composed.auto_loaded_context["user_profile"] == "No user profile loaded."
    assert composed.auto_loaded_context["trading_style"] == "No trading style loaded."
    assert composed.auto_loaded_context["risk_limits"].startswith("risk_limits.yaml missing")


def test_context_includes_safety_risk_and_trading_style(tmp_path: Path) -> None:
    _prepare_workspace(tmp_path)
    (tmp_path / "memory" / "user_profile.md").write_text(
        "User prefers conservative setups.",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "trading_style.md").write_text(
        "Breakout entries only with stop-loss.",
        encoding="utf-8",
    )
    (tmp_path / "configs" / "risk_limits.yaml").write_text(
        "max_daily_loss_pct: 1.0\nmax_position_risk_pct: 0.5\n",
        encoding="utf-8",
    )
    (tmp_path / "configs" / "safety.yaml").write_text(
        "kill_switch_enabled: false\napproval_required: true\n",
        encoding="utf-8",
    )
    (tmp_path / "skills" / "active" / "risk_review.md").write_text(
        "# Risk review\nUse defensive sizing.\n",
        encoding="utf-8",
    )

    composer = ContextComposer(tmp_path)
    composed = composer.compose(trust_mode="supervised")

    assert "Breakout entries only with stop-loss." in composed.auto_loaded_context["trading_style"]
    assert "max_daily_loss_pct: 1.0" in composed.auto_loaded_context["risk_limits"]
    assert "kill_switch_enabled: false" in composed.auto_loaded_context["safety_config"]
    assert "state=" in composed.auto_loaded_context["market_status"]
    assert "risk_review" in composed.auto_loaded_context["active_skills_summary"]
    assert composed.on_demand_tools
    assert "notify_user" in composed.on_demand_tools


def test_full_auto_loaded_context_sections_present(tmp_path: Path) -> None:
    _prepare_workspace(tmp_path)
    (tmp_path / "memory" / "user_profile.md").write_text(
        "Risk-averse user profile text.",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "trading_style.md").write_text(
        "Swing style with strict invalidation.",
        encoding="utf-8",
    )
    (tmp_path / "configs" / "risk_limits.yaml").write_text(
        "max_daily_loss_pct: 1.2\nmax_exposure_pct: 25\n",
        encoding="utf-8",
    )
    (tmp_path / "configs" / "safety.yaml").write_text(
        "approval_required: true\nkill_switch_enabled: false\n",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "trade_journal.md").write_text(
        "Entry A\n\nEntry B\n\nEntry C\n",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "lessons_learned.md").write_text(
        "Lesson A\n\nLesson B\n",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "mistakes.md").write_text(
        "Mistake A\n\nMistake B\n",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "open_positions.md").write_text(
        "AAPL long 10 shares\n",
        encoding="utf-8",
    )
    (tmp_path / "skills" / "active" / "breakout_guard.md").write_text(
        "# Breakout Guard\nCheck volume confirmation.\n",
        encoding="utf-8",
    )

    composer = ContextComposer(tmp_path)
    composed = composer.compose(
        trust_mode="supervised",
        market_status="state=afterhours; timezone=America/New_York",
    )

    auto = composed.auto_loaded_context
    expected_keys = {
        "user_profile",
        "trading_style",
        "risk_limits",
        "safety_config",
        "recent_journal_entries",
        "recent_lessons",
        "recent_mistakes",
        "active_skills_summary",
        "open_positions_snapshot",
        "market_status",
    }
    assert expected_keys.issubset(set(auto.keys()))
    assert "Risk-averse user profile text." in auto["user_profile"]
    assert "Swing style with strict invalidation." in auto["trading_style"]
    assert "max_daily_loss_pct: 1.2" in auto["risk_limits"]
    assert "approval_required: true" in auto["safety_config"]
    assert "Entry A" in auto["recent_journal_entries"]
    assert "Lesson A" in auto["recent_lessons"]
    assert "Mistake A" in auto["recent_mistakes"]
    assert "breakout_guard" in auto["active_skills_summary"]
    assert "AAPL long 10 shares" in auto["open_positions_snapshot"]
    assert auto["market_status"] == "state=afterhours; timezone=America/New_York"


def test_context_pruning_preserves_safety_and_risk(tmp_path: Path) -> None:
    _prepare_workspace(tmp_path)
    (tmp_path / "memory" / "trading_style.md").write_text("Scalping style.", encoding="utf-8")
    (tmp_path / "configs" / "risk_limits.yaml").write_text(
        "max_daily_loss_pct: 0.8\n",
        encoding="utf-8",
    )
    (tmp_path / "configs" / "safety.yaml").write_text(
        "kill_switch_enabled: true\n",
        encoding="utf-8",
    )
    (tmp_path / "memory" / "trade_journal.md").write_text(
        "\n\n".join(f"journal entry {idx} " + ("x" * 400) for idx in range(30)),
        encoding="utf-8",
    )
    (tmp_path / "memory" / "lessons_learned.md").write_text(
        "\n\n".join(f"lesson {idx} " + ("y" * 220) for idx in range(20)),
        encoding="utf-8",
    )
    (tmp_path / "memory" / "mistakes.md").write_text(
        "\n\n".join(f"mistake {idx} " + ("z" * 220) for idx in range(20)),
        encoding="utf-8",
    )

    composer = ContextComposer(tmp_path, token_budget=700)
    composed = composer.compose(trust_mode="manual")

    assert composed.auto_loaded_context["risk_limits"] == "max_daily_loss_pct: 0.8"
    assert composed.auto_loaded_context["safety_config"] == "kill_switch_enabled: true"
    assert "system_note" in composed.auto_loaded_context
    assert "Context pruned to fit token budget." in composed.auto_loaded_context["system_note"]
    assert composed.pruned_counts["journal"] > 0


def test_session_can_be_created() -> None:
    session = Session(
        trigger="scheduler",
        trust_mode="supervised",
        context_snapshot={"market_status": "open"},
    )

    assert session.id.startswith("sess_")
    assert session.started_at
    assert session.turn_count == 0
    assert session.has_summarized is False
