# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_skills_workflow_hardening.py
# PURPOSE: Verifies skills workflow hardening behavior and regression
#         expectations.
# DEPS:    pathlib, unittest, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def _write_skill(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_skills_improve_adds_required_metadata_without_auto_approval(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    proposed = tmp_path / "skills" / "proposed" / "avoid_overtrading.md"
    _write_skill(proposed, "# Skill: avoid_overtrading\n\nShort note.\n")

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["skills", "improve"]) == 0

    output = capsys.readouterr().out
    assert "Improved proposed skill drafts" in output
    assert proposed.exists()
    assert not (tmp_path / "skills" / "active" / "avoid_overtrading.md").exists()
    text = proposed.read_text(encoding="utf-8")
    for required in (
        "- status:",
        "- confidence:",
        "- risk_level:",
        "- evidence:",
        "- last_updated:",
    ):
        assert required in text


def test_skills_show_diff_approve_archive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(tmp_path)
    proposed = tmp_path / "skills" / "proposed" / "avoid_overtrading.md"
    active = tmp_path / "skills" / "active" / "avoid_overtrading.md"
    _write_skill(
        proposed,
        "# Skill: avoid_overtrading\n\n## Purpose\nProposed text.\n\n## Metadata\n- status: proposed\n",
    )
    _write_skill(
        active,
        "# Skill: avoid_overtrading\n\n## Purpose\nActive text.\n\n## Metadata\n- status: active\n",
    )

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["skills", "show", "avoid_overtrading"]) == 0
        show_out = capsys.readouterr().out
        assert "Metadata:" in show_out

        assert main(["skills", "diff", "avoid_overtrading"]) == 0
        diff_out = capsys.readouterr().out
        assert "--- " in diff_out and "+++ " in diff_out

    # Approval path (fresh proposed file)
    fresh_proposed = tmp_path / "skills" / "proposed" / "approve_me.md"
    _write_skill(fresh_proposed, "# Skill: approve_me\n")
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["skills", "approve", "approve_me"]) == 0
    approved = tmp_path / "skills" / "active" / "approve_me.md"
    assert approved.exists()
    assert "- status: active" in approved.read_text(encoding="utf-8")

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["skills", "archive", "approve_me"]) == 0
    archived = tmp_path / "skills" / "archived" / "approve_me.md"
    assert archived.exists()
    assert "- status: archived" in archived.read_text(encoding="utf-8")
