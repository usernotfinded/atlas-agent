#!/usr/bin/env python3
"""Tests for scripts/check_autonomous_paper_loop_contract.py."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_autonomous_paper_loop_contract.py"
DOC = REPO_ROOT / "docs" / "autonomous-paper-loop.md"


def _run_checker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not DOC.exists(), reason="Autonomous paper loop doc missing")
def test_checker_passes_on_real_repo() -> None:
    """The contract checker must pass against the real repository."""
    result = _run_checker()
    assert result.returncode == 0, f"Checker failed:\n{result.stdout}\n{result.stderr}"
    assert "PASSED" in result.stdout


@pytest.mark.skipif(not DOC.exists(), reason="Autonomous paper loop doc missing")
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
        pytest.skip("Autonomous paper loop doc missing")

    fake_repo = tmp_path / "fake_repo"
    fake_docs = fake_repo / "docs"
    fake_docs.mkdir(parents=True)

    fake_doc = fake_docs / "autonomous-paper-loop.md"
    fake_doc.write_text(DOC.read_text(encoding="utf-8") + "\nThis is guaranteed profit.\n")

    # The checker only examines its own doc and the shadow contract doc. We
    # create a minimal shadow doc so the required-file check does not mask the
    # forbidden-phrase finding.
    (fake_docs / "shadow-live-readiness-contract.md").write_text("placeholder\n")

    # Copy the checker into the fake repo and run it there.
    fake_checker = fake_repo / "scripts" / "check_autonomous_paper_loop_contract.py"
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
