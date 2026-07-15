# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_workspace_init.py
# PURPOSE: Verifies workspace init behavior and regression expectations.
# DEPS:    importlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from importlib import resources

import pytest

from atlas_agent.cli import main
import atlas_agent.workspace as workspace_mod
from atlas_agent.workspace import WorkspaceInitError, init_workspace


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


def test_template_resources_are_packaged() -> None:
    template = resources.files("atlas_agent").joinpath("templates", "routine-trader")

    assert template.is_dir()
    assert template.joinpath("README.md").is_file()
    assert template.joinpath(".env.example").is_file()
    assert template.joinpath("configs", "market.example.yaml").is_file()
    assert template.joinpath("memory", "portfolio.md").is_file()


def test_init_uses_package_resource_template(tmp_path) -> None:
    workspace = tmp_path / "my-trader"

    result = init_workspace(workspace, template="routine-trader")

    assert result.path == workspace
    assert (workspace / "README.md").exists()
    assert (workspace / "configs" / "market.example.yaml").exists()


def test_init_falls_back_to_packaged_template_when_package_resource_unavailable(
    tmp_path, monkeypatch
) -> None:
    class MissingResources:
        def joinpath(self, *parts: str) -> "MissingResources":
            return self

        def is_dir(self) -> bool:
            return False

    monkeypatch.setattr(workspace_mod.resources, "files", lambda package: MissingResources())
    workspace = tmp_path / "my-trader"

    result = init_workspace(workspace, template="routine-trader")

    assert result.path == workspace
    assert (workspace / "README.md").exists()
    assert (workspace / "memory" / "portfolio.md").exists()


def test_generated_workspace_has_no_real_secret_files(tmp_path) -> None:
    workspace = tmp_path / "my-trader"

    init_workspace(workspace, template="routine-trader")

    assert (workspace / ".env.example").exists()
    assert not (workspace / ".env").exists()
    secret_like_files = [
        path
        for path in workspace.rglob("*")
        if path.is_file()
        and path.name != ".env.example"
        and any(marker in path.name.upper() for marker in ("SECRET", "TOKEN", "PASSWORD", "API_KEY"))
    ]
    assert secret_like_files == []


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
