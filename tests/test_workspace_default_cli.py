from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas_agent.cli import main
from atlas_agent.workspace import get_default_workspace


def test_init_set_default_writes_safe_workspace_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    assert main(["init", "ws", "--template", "routine-trader", "--set-default"]) == 0

    config_path = home / ".atlas" / "config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"default_workspace"}
    assert Path(data["default_workspace"]).resolve() == (tmp_path / "ws").resolve()
    assert get_default_workspace() == (tmp_path / "ws").resolve()


def test_workspace_show_set_clear_and_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    assert main(["init", "ws", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    assert main(["workspace", "set", "ws"]) == 0
    set_output = capsys.readouterr().out
    assert "Default workspace set to" in set_output

    assert main(["workspace", "show"]) == 0
    show_output = capsys.readouterr().out
    assert "Resolved workspace:" in show_output
    assert "Default workspace:" in show_output

    assert main(["workspace", "doctor"]) == 0
    doctor_output = capsys.readouterr().out
    assert "Workspace structure looks valid." in doctor_output

    assert main(["workspace", "doctor", "--json"]) == 0
    doctor_json = capsys.readouterr().out
    assert '"command": "atlas workspace doctor"' in doctor_json
    assert '"ok": true' in doctor_json

    assert main(["workspace", "clear"]) == 0
    clear_output = capsys.readouterr().out
    assert "Default workspace cleared." in clear_output
    assert (tmp_path / "ws").exists()


def test_bare_atlas_outside_workspace_uses_default_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_complete_setup_config,
) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    assert main(["init", "ws", "--template", "routine-trader", "--set-default"]) == 0
    ws_path = tmp_path / "ws"
    write_complete_setup_config(ws_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    monkeypatch.chdir(outside)
    capsys.readouterr()

    assert main([]) == 0
    output = capsys.readouterr().out
    assert "- workspace configured: yes" in output
    assert "Bare `atlas` no longer starts autonomous execution." in output


def test_bare_atlas_outside_workspace_without_default_does_not_create_runtime_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    monkeypatch.chdir(outside)

    # Incomplete setup (no config at all) -> exit 2 in non-interactive
    assert main([]) == 2
    output = capsys.readouterr().out
    assert "Atlas provider credentials are missing" in output
    assert not (outside / "memory").exists()
    assert not (outside / "events").exists()
    assert not (outside / "reports").exists()
