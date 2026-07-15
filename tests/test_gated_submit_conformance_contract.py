# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_gated_submit_conformance_contract.py
# PURPOSE: Verifies gated submit conformance contract behavior and regression
#         expectations.
# DEPS:    ast, json, subprocess, sys, pathlib, pytest, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.check_gated_submit_conformance_contract as _checker
from scripts.check_gated_submit_conformance_contract import check_all

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "gated_submit_conformance.py"
)
DOC = REPO_ROOT / "docs" / "gated-submit-conformance.md"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_checker_passes_on_real_repo() -> None:
    result = check_all()
    assert result["passed"], result["errors"]


def test_checker_json_output() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/check_gated_submit_conformance_contract.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["passed"] is True
    assert data["errors"] == []


def test_checker_fails_when_forbidden_doc_claim_present(tmp_path: Path) -> None:
    doc_path = DOC
    original_text = doc_path.read_text(encoding="utf-8")
    try:
        doc_path.write_text(
            original_text + "\nThis strategy is guaranteed profit.\n",
            encoding="utf-8",
        )
        result = check_all()
        assert not result["passed"]
    finally:
        doc_path.write_text(original_text, encoding="utf-8")


def test_checker_fails_on_forbidden_import() -> None:
    module = ENGINE_MODULE
    original_text = module.read_text(encoding="utf-8")
    try:
        module.write_text(
            original_text + "\nfrom atlas_agent.brokers.alpaca import AlpacaBroker\n",
            encoding="utf-8",
        )
        result = check_all()
        assert not result["passed"]
    finally:
        module.write_text(original_text, encoding="utf-8")


@pytest.mark.parametrize(
    "pattern",
    [
        "broker.submit_order(order)",
        "OrderRouter(portfolio)",
        "live_trading_enabled=True",
        "can_submit = True",
        "api_key = 'leaked'",
        "requests.get(url)",
    ],
)
def test_checker_fails_on_forbidden_pattern(pattern: str) -> None:
    module = ENGINE_MODULE
    original_text = module.read_text(encoding="utf-8")
    try:
        module.write_text(original_text + "\n" + pattern + "\n", encoding="utf-8")
        result = check_all()
        assert not result["passed"], f"Expected failure for pattern: {pattern}"
    finally:
        module.write_text(original_text, encoding="utf-8")


def test_checker_imports_no_network_or_credentials() -> None:
    from scripts import check_gated_submit_conformance_contract as checker

    source = Path(checker.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert "requests" not in imports
    assert "urllib" not in imports
    assert not any("get_secret" in imp for imp in imports)


def test_checker_fails_when_cli_option_removed(tmp_path: Path) -> None:
    original_cli = _checker.CLI_MODULE
    temp_cli = tmp_path / "gated_submit_conformance_cli.py"
    temp_cli.write_text(original_cli.read_text(encoding="utf-8"), encoding="utf-8")
    text = temp_cli.read_text(encoding="utf-8")
    text = text.replace('"--quality-gate"', '"--quality-removed"')
    temp_cli.write_text(text, encoding="utf-8")
    try:
        _checker.CLI_MODULE = temp_cli
        result = _checker.check_all()
        assert not result["passed"], result["errors"]
    finally:
        _checker.CLI_MODULE = original_cli


def test_checker_fails_when_bootstrap_routing_removed(tmp_path: Path) -> None:
    original_bootstrap = _checker.BOOTSTRAP_MODULE
    temp_bootstrap = tmp_path / "cli_bootstrap.py"
    temp_bootstrap.write_text(
        original_bootstrap.read_text(encoding="utf-8"), encoding="utf-8"
    )
    text = temp_bootstrap.read_text(encoding="utf-8")
    text = text.replace("submit-conformance", "cand006-submit")
    temp_bootstrap.write_text(text, encoding="utf-8")
    try:
        _checker.BOOTSTRAP_MODULE = temp_bootstrap
        result = _checker.check_all()
        assert not result["passed"], result["errors"]
    finally:
        _checker.BOOTSTRAP_MODULE = original_bootstrap
