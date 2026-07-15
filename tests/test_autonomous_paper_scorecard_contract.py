#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_autonomous_paper_scorecard_contract.py
# PURPOSE: Verifies autonomous paper scorecard contract behavior and regression
#         expectations.
# DEPS:    json, shutil, subprocess, sys, pathlib, pytest.
# ==============================================================================

"""Tests for scripts/check_autonomous_paper_scorecard_contract.py."""

# --- IMPORTS ---

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_autonomous_paper_scorecard_contract.py"
DOC = REPO_ROOT / "docs" / "autonomous-paper-scorecard.md"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not DOC.exists(), reason="Autonomous paper scorecard doc missing")
def test_checker_passes_on_real_repo() -> None:
    """The contract checker must pass against the real repository."""
    result = _run_checker()
    assert result.returncode == 0, f"Checker failed:\n{result.stdout}\n{result.stderr}"
    assert "PASSED" in result.stdout


@pytest.mark.skipif(not DOC.exists(), reason="Autonomous paper scorecard doc missing")
def test_checker_json_output() -> None:
    """The --json flag must emit a structured result."""
    result = _run_checker("--json")
    assert result.returncode == 0, f"Checker failed:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["errors"] == []


def test_checker_fails_when_forbidden_phrase_present(tmp_path: Path) -> None:
    """A temporary copy of the doc containing a forbidden phrase must fail."""
    if not DOC.exists():
        pytest.skip("Autonomous paper scorecard doc missing")

    fake_repo = tmp_path / "fake_repo"
    fake_docs = fake_repo / "docs"
    fake_docs.mkdir(parents=True)

    fake_doc = fake_docs / "autonomous-paper-scorecard.md"
    fake_doc.write_text(
        DOC.read_text(encoding="utf-8") + "\nThis strategy is guaranteed profit.\n"
    )

    # Create minimal dependent docs so required-file checks do not mask the
    # forbidden-phrase finding.
    (fake_docs / "autonomous-paper-loop.md").write_text("placeholder\n")
    (fake_docs / "bounded-live-autonomy-governance.md").write_text("placeholder\n")
    (fake_docs / "shadow-live-readiness-contract.md").write_text("placeholder\n")

    # Create the module and test placeholders so the checker has the files it
    # expects but they do not contain the forbidden phrase.
    fake_src = fake_repo / "src" / "atlas_agent" / "agent"
    fake_src.mkdir(parents=True)
    (fake_src / "autonomous_paper_scorecard.py").write_text("# placeholder\n")
    (fake_repo / "src" / "atlas_agent" / "cli.py").write_text(
        '"autonomous-scorecard"\n'
    )
    (fake_repo / "tests").mkdir(parents=True, exist_ok=True)
    (fake_repo / "tests" / "test_autonomous_paper_scorecard.py").write_text(
        "# placeholder\n"
    )

    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_scorecard_contract.py"
    fake_checker.parent.mkdir(parents=True)
    shutil.copy2(CHECKER, fake_checker)

    result = subprocess.run(
        [sys.executable, str(fake_checker), "--json"],
        cwd=fake_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, f"Expected failure, got:\n{result.stdout}\n{result.stderr}"

    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("guaranteed profit" in err.lower() for err in payload["errors"])


def test_checker_imports_no_network_or_credentials() -> None:
    """The checker module must not import broker/provider/credential modules."""
    source = CHECKER.read_text(encoding="utf-8")
    forbidden = ["requests", "urllib", "alpaca", "openai", "boto", "paramiko"]
    assert not any(name in source.lower() for name in forbidden)
