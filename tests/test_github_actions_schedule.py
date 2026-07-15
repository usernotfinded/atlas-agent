# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_github_actions_schedule.py
# PURPOSE: Verifies github actions schedule behavior and regression
#         expectations.
# DEPS:    atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from atlas_agent.safety.secrets import scan_text_for_secrets
from atlas_agent.scheduler.github_actions import (
    SCHEDULED_ROUTINES,
    write_github_actions_workflow,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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


def test_github_actions_workflow_configures_symbol_before_routines(tmp_path) -> None:
    """CI workflows must explicitly set a demo symbol before running agentic routines."""
    path = write_github_actions_workflow(
        template="routine-trader",
        workspace_dir=tmp_path,
    )
    text = path.read_text(encoding="utf-8")

    assert "atlas config set market.symbol DEMO-SYMBOL" in text
    for routine in SCHEDULED_ROUTINES:
        # Each job block is rendered independently by _render_job.
        # Verify that within the full workflow, every routine run line is preceded
        # by a symbol config line earlier in the same job block.
        routine_line = f"atlas routine run {routine} --mode paper"
        routine_idx = text.find(routine_line)
        assert routine_idx != -1, f"Missing routine run for {routine}"

        # Walk backwards from the routine line to find the job header,
        # then confirm a symbol config exists between header and routine.
        block_start = text.rfind(f"  {routine}:", 0, routine_idx)
        assert block_start != -1, f"Could not find job block for {routine}"
        block = text[block_start:routine_idx]
        assert "atlas config set market.symbol DEMO-SYMBOL" in block, (
            f"Missing symbol config before {routine} routine run"
        )
