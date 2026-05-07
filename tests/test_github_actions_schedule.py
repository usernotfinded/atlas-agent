from __future__ import annotations

from atlas_agent.safety.secrets import scan_text_for_secrets
from atlas_agent.scheduler.github_actions import (
    SCHEDULED_ROUTINES,
    write_github_actions_workflow,
)


def test_github_actions_workflow_file_is_generated(tmp_path) -> None:
    path = write_github_actions_workflow(
        template="routine-trader",
        workspace_dir=tmp_path,
    )

    assert path.exists()
    assert path == tmp_path / ".github" / "workflows" / "atlas-routines.yml"


def test_github_actions_workflow_contains_all_five_routines(tmp_path) -> None:
    path = write_github_actions_workflow(
        template="routine-trader",
        workspace_dir=tmp_path,
    )
    text = path.read_text(encoding="utf-8")

    for routine in SCHEDULED_ROUTINES:
        assert f"atlas routine run {routine} --mode paper" in text


def test_github_actions_workflow_has_safe_defaults(tmp_path) -> None:
    path = write_github_actions_workflow(
        template="routine-trader",
        workspace_dir=tmp_path,
    )
    text = path.read_text(encoding="utf-8")

    assert scan_text_for_secrets(text) == []
    assert "TRADING_MODE: paper" in text
    assert "--mode paper" in text
    assert "TRADING_MODE: live" not in text
    assert "--mode live" not in text

