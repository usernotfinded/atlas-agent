# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_shadow_live_readonly_contract.py
# PURPOSE: Verifies shadow live readonly contract behavior and regression
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

import scripts.check_shadow_live_readonly_contract as _checker
from scripts.check_shadow_live_readonly_contract import check_all

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
SHADOW_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "autonomous_paper_shadow_live.py"
)
DOC = REPO_ROOT / "docs" / "shadow-live-readonly-comparison.md"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_checker_passes_on_real_repo() -> None:
    result = check_all()
    assert result["passed"], result["errors"]


def test_checker_json_output() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/check_shadow_live_readonly_contract.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["passed"] is True
    assert data["errors"] == []


def test_checker_fails_when_forbidden_doc_claim_present(
    mutated_copy, monkeypatch: pytest.MonkeyPatch
) -> None:
    temp_doc = mutated_copy(
        DOC,
        append="\nThis strategy is guaranteed profit.\n",
    )
    monkeypatch.setattr(_checker, "DOC", temp_doc)

    result = check_all()
    assert not result["passed"]


def test_checker_fails_on_forbidden_import(
    mutated_copy, monkeypatch: pytest.MonkeyPatch
) -> None:
    temp_module = mutated_copy(
        SHADOW_MODULE,
        append="\nfrom atlas_agent.brokers.alpaca import AlpacaBroker\n",
    )
    monkeypatch.setattr(_checker, "SHADOW_MODULE", temp_module)

    result = check_all()
    assert not result["passed"]


@pytest.mark.parametrize(
    "pattern",
    [
        "broker.submit_order(order)",
        "OrderRouter(portfolio)",
        "live_trading_enabled=True",
        "can_submit = True",
        "api_key = 'leaked'",
    ],
)
def test_checker_fails_on_forbidden_pattern(
    pattern: str, mutated_copy, monkeypatch: pytest.MonkeyPatch
) -> None:
    temp_module = mutated_copy(SHADOW_MODULE, append=f"\n{pattern}\n")
    monkeypatch.setattr(_checker, "SHADOW_MODULE", temp_module)

    result = check_all()
    assert not result["passed"], f"Expected failure for pattern: {pattern}"


def test_checker_imports_no_network_or_credentials() -> None:
    from scripts import check_shadow_live_readonly_contract as checker

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


def test_checker_fails_when_shadow_live_cli_option_removed(tmp_path: Path) -> None:
    original_cli = _checker.CLI_MODULE
    temp_cli = tmp_path / "cli.py"
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


def test_checker_fails_when_shadow_live_help_phrase_removed(tmp_path: Path) -> None:
    original_cli = _checker.CLI_MODULE
    temp_cli = tmp_path / "cli.py"
    temp_cli.write_text(original_cli.read_text(encoding="utf-8"), encoding="utf-8")
    text = temp_cli.read_text(encoding="utf-8")
    text = text.replace(
        "does not submit orders or call broker APIs",
        "may submit orders and call broker APIs",
    )
    temp_cli.write_text(text, encoding="utf-8")
    try:
        _checker.CLI_MODULE = temp_cli
        result = _checker.check_all()
        assert not result["passed"], result["errors"]
    finally:
        _checker.CLI_MODULE = original_cli
