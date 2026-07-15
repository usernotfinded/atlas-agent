# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_submit_execution_safety_check.py
# PURPOSE: Verifies submit execution safety check behavior and regression
#         expectations.
# DEPS:    json, subprocess, sys, pathlib.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    script = _repo_root() / "scripts" / "check_submit_execution_safety.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
    )


def test_submit_execution_safety_check_passes_current_repo() -> None:
    result = _run_checker()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_submit_execution_safety_check_json_passes_current_repo() -> None:
    result = _run_checker("--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["checks"]
    assert all(check["ok"] for check in payload["checks"])


def test_submit_execution_safety_check_fails_when_contract_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src" / "atlas_agent" / "execution").mkdir(parents=True)
    (repo / "src" / "atlas_agent" / "brokers").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "tests" / "execution").mkdir(parents=True)

    (repo / "src" / "atlas_agent" / "execution" / "submit_execution.py").write_text(
        "def run_submit_execution():\n    pass\n",
        encoding="utf-8",
    )
    (repo / "src" / "atlas_agent" / "brokers" / "resolver.py").write_text(
        "class BrokerResolver:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "src" / "atlas_agent" / "execution" / "approval.py").write_text(
        "approval_hash = ''\n",
        encoding="utf-8",
    )
    (repo / "docs" / "live-submit-safety-contract.md").write_text(
        "# Live-Submit Safety Contract\n",
        encoding="utf-8",
    )
    (repo / "tests" / "execution" / "test_submit_execution.py").write_text(
        "def test_placeholder():\n    pass\n",
        encoding="utf-8",
    )

    result = _run_checker(str(repo), "--json")
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    failed = {check["name"] for check in payload["checks"] if not check["ok"]}
    assert "doc_gate:explicit_live_submit_opt_in" in failed
    assert "submit_symbol:place_order" in failed
