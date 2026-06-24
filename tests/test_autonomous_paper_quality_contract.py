from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_autonomous_paper_quality_contract import check_all

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def test_checker_fails_when_forbidden_phrase_present(tmp_path: Path):
    checker_path = REPO_ROOT / "scripts" / "check_autonomous_paper_quality_contract.py"
    original_text = checker_path.read_text(encoding="utf-8")
    try:
        checker_path.write_text(original_text.replace('"risk-free"', '"paper-only"'), encoding="utf-8")
        result = check_all()
        assert not result["passed"]
    finally:
        checker_path.write_text(original_text, encoding="utf-8")


def test_checker_fails_on_forbidden_import(tmp_path: Path):
    module = REPO_ROOT / "src" / "atlas_agent" / "agent" / "autonomous_paper_quality.py"
    original_text = module.read_text(encoding="utf-8")
    try:
        module.write_text(original_text + "\nimport atlas_agent.brokers\n", encoding="utf-8")
        result = check_all()
        assert not result["passed"]
    finally:
        module.write_text(original_text, encoding="utf-8")


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
