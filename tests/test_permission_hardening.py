"""Regression tests for PermissionError hardening in sandboxed environments.

Verifies that config loading, workspace resolution, and secret loading
gracefully handle unreadable user-global paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Config store PermissionError hardening
# ---------------------------------------------------------------------------


def test_load_raw_config_returns_empty_on_permission_error(monkeypatch, tmp_path: Path) -> None:
    """If config.toml exists but is unreadable, load_raw_config returns {}."""
    from atlas_agent.config.store import load_raw_config
    from atlas_agent.config.paths import get_config_toml_path

    # Point config to a temp file that we will make unreadable
    config_file = tmp_path / "config.toml"
    config_file.write_text("[market]\nsymbol = 'AAPL'\n", encoding="utf-8")
    config_file.chmod(0o000)

    with patch("atlas_agent.config.store.get_config_toml_path", return_value=config_file):
        result = load_raw_config()
        assert result == {}, f"Expected empty dict on PermissionError, got {result}"

    config_file.chmod(0o644)


def test_load_raw_config_reads_when_readable(tmp_path: Path) -> None:
    """Normal readable config is loaded correctly."""
    from atlas_agent.config.store import load_raw_config

    config_file = tmp_path / "config.toml"
    config_file.write_text("[market]\nsymbol = 'AAPL'\n", encoding="utf-8")

    with patch("atlas_agent.config.store.get_config_toml_path", return_value=config_file):
        result = load_raw_config()
        assert result.get("market", {}).get("symbol") == "AAPL"


# ---------------------------------------------------------------------------
# Secrets PermissionError hardening
# ---------------------------------------------------------------------------


def test_load_atlas_secrets_skips_on_permission_error(monkeypatch, tmp_path: Path) -> None:
    """If .env.atlas exists but is unreadable, load_atlas_secrets does not raise."""
    from atlas_agent.config.secrets import load_atlas_secrets

    env_file = tmp_path / ".env.atlas"
    env_file.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    env_file.chmod(0o000)

    with patch("atlas_agent.config.secrets.get_env_atlas_path", return_value=env_file):
        # Must not raise
        load_atlas_secrets()

    env_file.chmod(0o600)


# ---------------------------------------------------------------------------
# Workspace root PermissionError hardening
# ---------------------------------------------------------------------------


def test_get_workspace_root_handles_permission_error(tmp_path: Path) -> None:
    """If a parent directory is unreadable, traversal continues safely."""
    from atlas_agent.config.paths import get_workspace_root

    # Create a nested structure
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (tmp_path / "a" / ".atlas").mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(nested)

        # Mock is_dir to raise PermissionError on the workspace parent,
        # simulating a sandboxed environment where that directory is unreadable
        real_is_dir = Path.is_dir

        def _mock_is_dir(self: Path) -> bool:
            if str(self) == str(tmp_path / "a" / ".atlas"):
                raise PermissionError("Permission denied")
            return real_is_dir(self)

        with patch.object(Path, "is_dir", _mock_is_dir):
            root = get_workspace_root()
            # Should fallback to cwd since parent traversal was blocked
            assert root == nested
    finally:
        os.chdir(original_cwd)


def test_get_workspace_root_finds_atlas_when_readable(tmp_path: Path) -> None:
    """Normal workspace discovery works when directories are readable."""
    from atlas_agent.config.paths import get_workspace_root

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".atlas").mkdir()
    subdir = workspace / "subdir"
    subdir.mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(subdir)
        root = get_workspace_root()
        assert root == workspace
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# CLI isolation: sandboxed HOME prevents global config leakage
# ---------------------------------------------------------------------------


def test_cli_validate_runs_with_sandboxed_home(tmp_path: Path, monkeypatch) -> None:
    """atlas validate must work when HOME points to a temp directory."""
    from atlas_agent.cli import main

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    atlas_dir = home_dir / ".atlas"
    atlas_dir.mkdir()

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.chdir(tmp_path)

    # Create a minimal workspace
    (tmp_path / ".atlas").mkdir()
    (tmp_path / "memory").mkdir()
    (tmp_path / "events").mkdir()

    # Must not raise PermissionError or AtlasConfigError
    ret = main(["validate"])
    assert ret == 0


# ---------------------------------------------------------------------------
# Subprocess isolation pattern
# ---------------------------------------------------------------------------


def test_subprocess_atlas_uses_isolated_env(tmp_path: Path) -> None:
    """Subprocess invocations of atlas should not leak user-global paths."""
    import subprocess

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    (home_dir / ".atlas").mkdir()

    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    env["ATLAS_HOME"] = str(home_dir / ".atlas")
    env["PYTHONNOUSERSITE"] = "1"

    # Just verify python can import atlas_agent with isolated HOME
    result = subprocess.run(
        [sys.executable, "-c", "import atlas_agent; print(atlas_agent.__version__)"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, f"Subprocess failed: {result.stderr}"
    assert "0.5.8" in result.stdout


# ---------------------------------------------------------------------------
# No dependency on user-global pyvenv.cfg or ~/.atlas/config.toml
# ---------------------------------------------------------------------------


def test_no_pyvenv_cfg_required_for_config_loading() -> None:
    """Config loading must not depend on any pyvenv.cfg file."""
    from atlas_agent.config.store import load_raw_config
    from atlas_agent.config.paths import get_config_toml_path

    # Point to a non-existent path
    with patch("atlas_agent.config.store.get_config_toml_path", return_value=Path("/nonexistent/config.toml")):
        result = load_raw_config()
        assert result == {}


def test_no_user_atlas_required_when_workspace_exists(tmp_path: Path) -> None:
    """When a workspace .atlas exists, user-global ~/.atlas must not be accessed."""
    from atlas_agent.config.paths import get_config_dir

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".atlas").mkdir()

    original_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        config_dir = get_config_dir()
        assert config_dir == workspace / ".atlas"
    finally:
        os.chdir(original_cwd)


# ---------------------------------------------------------------------------
# Source-level regression: no hardcoded /tmp in test_runner.py
# ---------------------------------------------------------------------------


def test_runner_no_hardcoded_tmp() -> None:
    """test_runner.py must not hardcode /tmp paths."""
    test_runner = Path(__file__).resolve().parents[1] / "tests" / "agent" / "test_runner.py"
    text = test_runner.read_text(encoding="utf-8")
    assert 'Path("/tmp/' not in text, "test_runner.py contains hardcoded /tmp path"
    assert "Path('/tmp/" not in text, "test_runner.py contains hardcoded /tmp path"


# ---------------------------------------------------------------------------
# Source-level regression: demo subprocess tests must set PYTHONNOUSERSITE
# ---------------------------------------------------------------------------


def test_demo_research_subprocess_sets_pythonno_usersite() -> None:
    """test_demo_research_workflow_script.py subprocess tests must include PYTHONNOUSERSITE."""
    demo_test = Path(__file__).resolve().parents[1] / "tests" / "test_demo_research_workflow_script.py"
    text = demo_test.read_text(encoding="utf-8")
    assert "PYTHONNOUSERSITE" in text, "demo research workflow tests missing PYTHONNOUSERSITE isolation"


# ---------------------------------------------------------------------------
# Source-level regression: CLI fixtures set isolated HOME/ATLAS_HOME
# ---------------------------------------------------------------------------


def test_cli_fixtures_set_isolated_home() -> None:
    """test_cli.py must set HOME and ATLAS_HOME to temp dirs in tests that call main()."""
    cli_test = Path(__file__).resolve().parents[1] / "tests" / "test_cli.py"
    text = cli_test.read_text(encoding="utf-8")
    assert 'monkeypatch.setenv("HOME"' in text, "test_cli.py missing HOME isolation"
    assert 'monkeypatch.setenv("ATLAS_HOME"' in text, "test_cli.py missing ATLAS_HOME isolation"
    assert 'monkeypatch.setenv("PYTHONNOUSERSITE"' in text, "test_cli.py missing PYTHONNOUSERSITE"


def test_cli_top_level_fixtures_set_isolated_home() -> None:
    """test_cli_top_level.py fixtures must set HOME and ATLAS_HOME to temp dirs."""
    cli_test = Path(__file__).resolve().parents[1] / "tests" / "test_cli_top_level.py"
    text = cli_test.read_text(encoding="utf-8")
    assert 'monkeypatch.setenv("HOME"' in text, "test_cli_top_level.py fixtures missing HOME isolation"
    assert 'monkeypatch.setenv("ATLAS_HOME"' in text, "test_cli_top_level.py fixtures missing ATLAS_HOME isolation"
    assert 'monkeypatch.setenv("PYTHONNOUSERSITE"' in text, "test_cli_top_level.py fixtures missing PYTHONNOUSERSITE"


# ---------------------------------------------------------------------------
# Integration: key tests run without PermissionError in restricted env
# ---------------------------------------------------------------------------


def test_key_tests_pass_with_restricted_home(tmp_path: Path) -> None:
    """Run isolated CLI and runner tests with a temp HOME to prove no PermissionError."""
    import subprocess

    home = tmp_path / "home"
    atlas_home = tmp_path / "atlas-home"
    home.mkdir()
    atlas_home.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["ATLAS_HOME"] = str(atlas_home)
    env["PYTHONNOUSERSITE"] = "1"
    # Remove any user-global Python path leakage
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_cli.py::test_submit_approved_order_execution_invalid_order_id",
            "tests/test_cli.py::test_submit_approved_order_execution_invalid_order_id_json",
            "tests/test_cli.py::test_submit_approved_order_execution_fake_secret_not_leaked",
            "tests/test_cli_top_level.py::test_help_no_agent_start",
            "tests/agent/test_runner.py::test_run_agent_live_not_enabled_fails_closed",
            "-v",
            "--tb=short",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, (
        f"Isolated test run failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "PermissionError" not in result.stdout
    assert "PermissionError" not in result.stderr
