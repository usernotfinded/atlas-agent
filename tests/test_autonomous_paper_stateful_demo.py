# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_autonomous_paper_stateful_demo.py
# PURPOSE: Verifies autonomous paper stateful demo behavior and regression
#         expectations.
# DEPS:    subprocess, sys, pathlib, pytest.
# ==============================================================================

"""Test for the CAND-003 stateful autonomous paper demo script."""

# --- IMPORTS ---

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_autonomous_paper_stateful.sh"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.mark.slow
def test_stateful_paper_demo_succeeds() -> None:
    result = subprocess.run(
        ["bash", str(DEMO_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CAND-003 stateful autonomous paper demo PASS" in result.stdout
