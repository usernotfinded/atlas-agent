from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.routines.routine_result import RoutineResult
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
) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    assert main(["init", "ws", "--template", "routine-trader", "--set-default"]) == 0
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    monkeypatch.chdir(outside)
    capsys.readouterr()

    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        mock_run.return_value = RoutineResult(
            name="pre_market",
            mode="paper",
            status="complete",
            report_path=tmp_path / "ws" / "reports" / "daily" / "ok.md",
            memory_files_updated=(),
        )
        assert main([]) == 0
        called_config = mock_run.call_args.kwargs["config"]
        assert called_config.memory_dir.resolve() == (tmp_path / "ws" / "memory").resolve()


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

    assert main([]) == 2
    _ = capsys.readouterr()
    assert not (outside / "memory").exists()
    assert not (outside / "events").exists()
    assert not (outside / "reports").exists()
