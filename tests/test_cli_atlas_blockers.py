from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def _assert_not_help(output: str) -> None:
    lower = output.lower()
    assert "usage: atlas" not in lower
    assert "positional arguments:" not in lower


def test_atlas_memory_search_returns_matches_without_help(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.memory_dir.mkdir(parents=True)
    (config.memory_dir / "risk_notes.md").write_text(
        "# Risk Notes\n\nRiskManager gates every broker order.\n",
        encoding="utf-8",
    )

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["memory", "search", "risk"]) == 0

    output = capsys.readouterr().out
    _assert_not_help(output)
    assert "risk_notes.md" in output
    assert "RiskManager" in output


def test_atlas_user_show_prints_user_model_without_help(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.memory_dir.mkdir(parents=True)
    (config.memory_dir / "user_profile.md").write_text(
        "# User Profile\n\nPrefers audited risk-first trading.\n",
        encoding="utf-8",
    )
    (config.memory_dir / "preferences.md").write_text(
        "# Preferences\n\nKeep live orders approval-gated.\n",
        encoding="utf-8",
    )

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["user", "show"]) == 0

    output = capsys.readouterr().out
    _assert_not_help(output)
    assert "Atlas User Model" in output
    assert "risk-first trading" in output
    assert "approval-gated" in output


def test_atlas_telegram_test_reports_diagnostics_without_help_or_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    token = "123456:super-secret-telegram-token"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "42")
    monkeypatch.setenv("TELEGRAM_CONTROL_MODE", "disabled")

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["telegram", "test"]) == 0

    output = capsys.readouterr().out
    _assert_not_help(output)
    assert "Telegram" in output
    assert "present" in output
    assert "network: not contacted" in output.lower()
    assert token not in output


@pytest.mark.parametrize(
    ("target", "expected_paths"),
    (
        ("docker", ("deploy/Dockerfile", "deploy/docker-compose.yml")),
        ("systemd", ("deploy/systemd/atlas-agent.service",)),
    ),
)
def test_atlas_deploy_generates_files_and_reports_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    target: str,
    expected_paths: tuple[str, ...],
) -> None:
    config = _config(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["deploy", target]) == 0

    output = capsys.readouterr().out
    _assert_not_help(output)
    for relative_path in expected_paths:
        assert (tmp_path / relative_path).exists()
        assert relative_path in output


def test_atlas_skills_improve_normalizes_proposed_skill_structure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    proposed_dir = tmp_path / "skills" / "proposed"
    proposed_dir.mkdir(parents=True)
    skill_path = proposed_dir / "thin-risk-note.md"
    skill_path.write_text(
        "# Thin risk note\n\nTrade journal says tighten risk checks before market open.\n",
        encoding="utf-8",
    )

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["skills", "improve"]) == 0

    output = capsys.readouterr().out
    _assert_not_help(output)
    assert "improved" in output.lower()

    improved = skill_path.read_text(encoding="utf-8")
    assert "Trade journal says tighten risk checks before market open." in improved
    for section in (
        "## Name",
        "## Purpose",
        "## When to use",
        "## Inputs",
        "## Output format",
        "## Risk constraints",
        "## Failure modes",
        "## Evidence/source journal entries",
        "## Confidence level",
    ):
        assert section in improved
    assert "RiskManager" in improved
    assert "approval gates" in improved
