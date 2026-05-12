from __future__ import annotations

import pytest

from atlas_agent.cli import main
from atlas_agent.workspace import WorkspaceInitError, init_workspace


def test_init_creates_expected_workspace(tmp_path) -> None:
    workspace = tmp_path / "my-trader"

    result = init_workspace(workspace, template="routine-trader")

    assert result.path == workspace
    assert (workspace / "memory" / "portfolio.md").exists()
    assert (workspace / "memory" / "trade_journal.md").exists()
    assert (workspace / "routines" / "prompts" / "pre_market.md").exists()
    assert (workspace / "skills" / "risk_review.md").exists()
    assert (workspace / ".env.example").exists()
    assert (workspace / ".gitignore").exists()
    assert (workspace / "reports" / "daily" / ".gitkeep").exists()
    assert (workspace / "reports" / "weekly" / ".gitkeep").exists()
    assert (workspace / "pending_orders" / ".gitkeep").exists()
    assert (workspace / "audit" / ".gitkeep").exists()
    assert not list((workspace / "reports" / "daily").glob("*.md"))
    assert not list((workspace / "pending_orders").glob("*.json"))


def test_init_refuses_existing_non_empty_folder(tmp_path) -> None:
    workspace = tmp_path / "my-trader"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(WorkspaceInitError, match="not empty"):
        init_workspace(workspace, template="routine-trader")


def test_init_force_overwrites_managed_paths_safely(tmp_path) -> None:
    workspace = tmp_path / "my-trader"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "memory" / "watchlist.md").write_text("old", encoding="utf-8")
    (workspace / "keep.txt").write_text("preserve", encoding="utf-8")

    result = init_workspace(workspace, template="routine-trader", force=True)

    assert result.overwritten is True
    assert "# Watchlist" in (workspace / "memory" / "watchlist.md").read_text(
        encoding="utf-8"
    )
    assert (workspace / "keep.txt").read_text(encoding="utf-8") == "preserve"


def test_generated_workspace_validates(tmp_path, monkeypatch, capsys) -> None:
    workspace = tmp_path / "my-trader"
    init_workspace(workspace, template="routine-trader")
    monkeypatch.chdir(workspace)

    assert main(["validate"]) == 0
    assert "Workspace initialized" in capsys.readouterr().out

