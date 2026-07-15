# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/update/test_update_cli.py
# PURPOSE: Verifies update cli behavior and regression expectations.
# DEPS:    os, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import os
from pathlib import Path

from atlas_agent.cli import main


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _init_workspace(path: Path) -> None:
    original = Path.cwd()
    os.chdir(path)
    try:
        assert main(["init", "."]) == 0
    finally:
        os.chdir(original)


def test_cli_update_status_works_without_network(tmp_path: Path, monkeypatch, capsys) -> None:
    _init_workspace(tmp_path)
    original = Path.cwd()
    os.chdir(tmp_path)
    try:
        def _forbidden(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("network should not be used for `atlas update status`")

        monkeypatch.setattr("urllib.request.urlopen", _forbidden)
        code = main(["update", "status"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Atlas Update Status" in out
    finally:
        os.chdir(original)


def test_cli_update_config_round_trip(tmp_path: Path, capsys) -> None:
    _init_workspace(tmp_path)
    original = Path.cwd()
    os.chdir(tmp_path)
    try:
        code = main(["update", "config", "--auto-check", "daily", "--auto-apply", "on"])
        assert code == 0
        output = capsys.readouterr().out
        assert "auto-check: daily" in output
        assert "auto-apply: on" in output

        code = main(["update", "status"])
        assert code == 0
        status_output = capsys.readouterr().out
        assert "Auto-apply enabled: yes" in status_output
        assert "Auto-check schedule: daily" in status_output
    finally:
        os.chdir(original)


def test_cli_update_rollback_requires_confirmation(tmp_path: Path, capsys) -> None:
    _init_workspace(tmp_path)
    original = Path.cwd()
    os.chdir(tmp_path)
    try:
        code = main(["update", "rollback"])
        assert code == 2
        output = capsys.readouterr().out
        assert "Rollback refused" in output
    finally:
        os.chdir(original)
