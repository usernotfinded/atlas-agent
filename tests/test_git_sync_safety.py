from __future__ import annotations

import subprocess

import pytest

from omni_trade_ai.routines.git_sync import GitSync, GitSyncError


def _git(repo, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )


def _init_repo(tmp_path):
    _git(tmp_path, "init")
    return tmp_path


def test_git_push_is_disabled_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_GIT_PUSH", raising=False)
    repo = _init_repo(tmp_path)

    sync = GitSync.from_env(repo)

    assert sync.allow_push is False
    assert sync.push() == "push skipped: ALLOW_GIT_PUSH is not true"


def test_git_commit_is_disabled_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_GIT_COMMIT", raising=False)
    repo = _init_repo(tmp_path)
    (repo / "memory").mkdir()
    (repo / "memory" / "daily_notes.md").write_text("notes", encoding="utf-8")

    sync = GitSync.from_env(repo)

    assert sync.allow_commit is False
    assert sync.commit("routine: test") == "commit skipped: ALLOW_GIT_COMMIT is not true"


def test_git_commit_is_created_when_enabled(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "memory").mkdir()
    (repo / "memory" / "daily_notes.md").write_text("notes", encoding="utf-8")
    sync = GitSync(repo_dir=repo, allow_commit=True)

    assert sync.commit("routine: test") == "commit created"
    assert "routine: test" in _git(repo, "log", "--oneline").stdout


def test_git_commit_never_adds_env_file(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "memory").mkdir()
    (repo / "memory" / "daily_notes.md").write_text("notes", encoding="utf-8")
    (repo / ".env").write_text("ALPACA_API_KEY=not-for-git", encoding="utf-8")
    sync = GitSync(repo_dir=repo, allow_commit=True)

    assert sync.commit("routine: test") == "commit created"
    assert _git(repo, "ls-files", ".env").stdout == ""


def test_git_commit_refuses_secret_values(tmp_path) -> None:
    _init_repo(tmp_path)
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "daily_notes.md").write_text(
        "ALPACA_API_KEY=" + "accidentally-committed\n",
        encoding="utf-8",
    )
    sync = GitSync(repo_dir=tmp_path, allow_commit=True)

    with pytest.raises(GitSyncError, match="possible secrets"):
        sync.commit("routine: test")


def test_git_status_output_does_not_expose_secret_values(tmp_path) -> None:
    repo = _init_repo(tmp_path)
    (repo / ".env").write_text("ALPACA_API_KEY=not-for-output", encoding="utf-8")
    sync = GitSync(repo_dir=repo)

    output = sync.status()

    assert "not-for-output" not in output
    assert ".env" not in output
    assert "[sensitive file hidden]" in output
