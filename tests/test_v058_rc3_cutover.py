# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_v058_rc3_cutover.py
# PURPOSE: Verifies v058 rc3 cutover behavior and regression expectations.
# DEPS:    json, subprocess, sys, pathlib.
# ==============================================================================

"""Historical tests for the superseded v0.5.8rc3 cutover checker."""

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CUTOVER_SCRIPT = REPO_ROOT / "scripts" / "historical_release_checkers" / "check_v058_rc3_cutover.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_rc3_cutover_checker_fails_against_rc4_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(CUTOVER_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 2, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is False
    assert data["expected_version"] == "0.5.8rc3"
    assert any("0.5.8rc3" in error for error in data["errors"])


def test_rc3_script_source_no_shell_true() -> None:
    source = CUTOVER_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_rc3_script_source_no_network_calls() -> None:
    source = CUTOVER_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket", "requests"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in cutover script"


def test_rc3_script_source_no_github_api() -> None:
    source = CUTOVER_SCRIPT.read_text(encoding="utf-8")
    assert "github.com" not in source
    assert "api.github" not in source
    assert "gh api" not in source
