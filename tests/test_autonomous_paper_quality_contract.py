# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_autonomous_paper_quality_contract.py
# PURPOSE: Verifies autonomous paper quality contract behavior and regression
#         expectations.
# DEPS:    json, subprocess, sys, pathlib, pytest, scripts.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.check_autonomous_paper_quality_contract as _checker
from scripts.check_autonomous_paper_quality_contract import check_all

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_checker_passes_on_real_repo():
    result = check_all()
    assert result["passed"], result["errors"]


def test_checker_json_output():
    proc = subprocess.run(
        [sys.executable, "scripts/check_autonomous_paper_quality_contract.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["passed"] is True
    assert data["errors"] == []


def test_checker_fails_when_forbidden_phrase_present(
    mutated_copy, monkeypatch: pytest.MonkeyPatch
):
    doc_path = REPO_ROOT / "docs" / "autonomous-paper-quality-gate.md"
    temp_doc = mutated_copy(
        doc_path,
        append="\nThis strategy is guaranteed profit.\n",
    )
    monkeypatch.setattr(_checker, "DOC", temp_doc)

    result = check_all()
    assert not result["passed"]


def test_checker_fails_on_forbidden_import(
    mutated_copy, monkeypatch: pytest.MonkeyPatch
):
    module = REPO_ROOT / "src" / "atlas_agent" / "agent" / "autonomous_paper_quality.py"
    temp_module = mutated_copy(module, append="\nimport atlas_agent.brokers\n")
    monkeypatch.setattr(_checker, "MODULES", [temp_module])

    result = check_all()
    assert not result["passed"]


def test_checker_imports_no_network_or_credentials():
    from scripts import check_autonomous_paper_quality_contract as checker
    import ast
    source = Path(checker.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert "requests" not in imports
    assert "urllib" not in imports
    assert not any("get_secret" in imp for imp in imports)
