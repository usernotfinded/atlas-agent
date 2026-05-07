from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from atlas_agent.cli import main


@pytest.fixture
def workspace():
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        # Initialize workspace
        main(["init", "."])
        yield Path(temp_dir)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


@pytest.fixture
def non_workspace():
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        yield Path(temp_dir)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


from unittest.mock import patch, ANY


def test_help_no_agent_start(non_workspace, capsys):
    code = main(["--help"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Atlas Agent is a self-improving AI trading agent" in captured.out
    assert "Starting autonomous cycle..." not in captured.out


def test_bare_atlas_in_workspace(workspace, capsys):
    # This might take a while if it actually runs the agent
    # We can mock run_agent if needed, but let's see if it runs paper mode safely
    # For testing, we might want to mock run_agent to avoid hitting APIs or taking too long
    from unittest.mock import patch
    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        from atlas_agent.routines.routine_result import RoutineResult
        mock_run.return_value = RoutineResult(
            name="pre_market", mode="paper", status="complete", 
            report_path=Path("reports/daily/test.md"), memory_files_updated=()
        )
        code = main([])
        assert code == 0
        mock_run.assert_called_once()
        captured = capsys.readouterr()
        assert "Starting autonomous cycle..." in captured.out


def test_bare_atlas_outside_workspace(non_workspace, capsys):
    code = main([])
    assert code == 2
    captured = capsys.readouterr()
    assert "Atlas Agent needs a workspace before it can run" in captured.out
    # Verify no runtime files were created
    assert not (non_workspace / "memory").exists()
    assert not (non_workspace / "events").exists()


def test_status_alias(workspace):
    from unittest.mock import patch
    with patch("atlas_agent.agent.status.get_agent_status") as mock_status:
        mock_status.return_value = "Mock Status"
        code = main(["status"])
        assert code == 0
        mock_status.assert_called_once()


def test_plan_alias(workspace):
    from unittest.mock import patch
    with patch("atlas_agent.agent.planner.get_agent_plan") as mock_plan:
        mock_plan.return_value = "Mock Plan"
        code = main(["plan"])
        assert code == 0
        mock_plan.assert_called_once()


def test_run_alias(workspace):
    from unittest.mock import patch
    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        from atlas_agent.routines.routine_result import RoutineResult
        mock_run.return_value = RoutineResult(
            name="pre_market", mode="paper", status="complete", 
            report_path=Path("reports/daily/test.md"), memory_files_updated=()
        )
        code = main(["run"])
        assert code == 0
        mock_run.assert_called_with(
            mode="auto", config=ANY, continuous=False, interval=60, max_cycles=None
        )


def test_run_continuous_alias(workspace):
    from unittest.mock import patch
    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        from atlas_agent.routines.routine_result import RoutineResult
        mock_run.return_value = RoutineResult(
            name="pre_market", mode="paper", status="complete", 
            report_path=Path("reports/daily/test.md"), memory_files_updated=()
        )
        code = main(["run", "--continuous"])
        assert code == 0
        mock_run.assert_called_with(
            mode="auto", config=ANY, continuous=True, interval=60, max_cycles=None
        )


def test_run_dry_run_alias(workspace):
    from unittest.mock import patch
    with patch("atlas_agent.agent.planner.get_agent_plan") as mock_plan:
        mock_plan.return_value = "Mock Plan"
        code = main(["run", "--dry-run"])
        assert code == 0
        mock_plan.assert_called_once()


def test_existing_agent_commands_still_work(workspace):
    from unittest.mock import patch
    with patch("atlas_agent.agent.runner.run_agent") as mock_run:
        from atlas_agent.routines.routine_result import RoutineResult
        mock_run.return_value = RoutineResult(
            name="pre_market", mode="paper", status="complete", 
            report_path=Path("reports/daily/test.md"), memory_files_updated=()
        )
        code = main(["agent", "run", "--once"])
        assert code == 0
        mock_run.assert_called()
