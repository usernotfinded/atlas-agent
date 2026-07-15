# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_runtime_readiness_envelope_contract.py
# PURPOSE: Verifies runtime readiness envelope contract behavior and regression
#         expectations.
# DEPS:    ast, json, subprocess, sys, pathlib, pytest, additional local modules.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.check_runtime_readiness_envelope_contract as _checker
from scripts.check_runtime_readiness_envelope_contract import check_all

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "runtime_readiness_envelope.py"
)
BOOTSTRAP_MODULE = REPO_ROOT / "src" / "atlas_agent" / "cli_bootstrap.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_checker_passes_on_real_repo() -> None:
    result = check_all()
    assert result["passed"], result["errors"]


def test_checker_json_output() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/check_runtime_readiness_envelope_contract.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["passed"] is True
    assert data["errors"] == []


def test_checker_fails_when_forbidden_doc_claim_present(tmp_path: Path) -> None:
    temp_doc = tmp_path / "runtime-readiness-envelope-design.md"
    temp_doc.write_text(
        "# Runtime readiness envelope\n\nThis feature is guaranteed profit.\n",
        encoding="utf-8",
    )
    original_doc = _checker.DOC
    try:
        _checker.DOC = temp_doc
        result = check_all()
        assert not result["passed"]
    finally:
        _checker.DOC = original_doc


def test_checker_cli_returns_two_on_failure(
    mutated_copy, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    temp_doc = mutated_copy(
        _checker.DOC,
        append="\nThis feature is guaranteed profit.\n",
    )
    monkeypatch.setattr(_checker, "DOC", temp_doc)
    monkeypatch.setattr(sys, "argv", ["check_runtime_readiness_envelope_contract.py"])

    assert _checker.main() == 2
    assert "FAILED" in capsys.readouterr().out


def test_checker_fails_on_forbidden_import(tmp_path: Path) -> None:
    temp_engine = tmp_path / "runtime_readiness_envelope.py"
    temp_engine.write_text(
        ENGINE_MODULE.read_text(encoding="utf-8")
        + "\nfrom atlas_agent.brokers.alpaca import AlpacaBroker\n",
        encoding="utf-8",
    )
    original_engine = _checker.ENGINE_MODULE
    try:
        _checker.ENGINE_MODULE = temp_engine
        result = check_all()
        assert not result["passed"], result["errors"]
    finally:
        _checker.ENGINE_MODULE = original_engine


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
def test_checker_fails_on_forbidden_pattern(pattern: str, tmp_path: Path) -> None:
    temp_engine = tmp_path / "runtime_readiness_envelope.py"
    temp_engine.write_text(
        ENGINE_MODULE.read_text(encoding="utf-8") + "\n" + pattern + "\n",
        encoding="utf-8",
    )
    original_engine = _checker.ENGINE_MODULE
    try:
        _checker.ENGINE_MODULE = temp_engine
        result = check_all()
        assert not result["passed"], f"Expected failure for pattern: {pattern}"
    finally:
        _checker.ENGINE_MODULE = original_engine


def test_checker_enforces_canonical_blockers_field(tmp_path: Path) -> None:
    original_text = ENGINE_MODULE.read_text(encoding="utf-8")
    temp_engine = tmp_path / "runtime_readiness_envelope.py"
    temp_engine.write_text(
        original_text.replace('"blockers": self.blockers', '"legacy_blockers": self.blockers'),
        encoding="utf-8",
    )
    original_engine = _checker.ENGINE_MODULE
    try:
        _checker.ENGINE_MODULE = temp_engine
        result = check_all()
        assert not result["passed"], result["errors"]
        assert any("blockers" in e for e in result["errors"]), result["errors"]
    finally:
        _checker.ENGINE_MODULE = original_engine


def test_checker_fails_if_blocked_reasons_reintroduced(tmp_path: Path) -> None:
    original_text = ENGINE_MODULE.read_text(encoding="utf-8")
    temp_engine = tmp_path / "runtime_readiness_envelope.py"
    temp_engine.write_text(
        original_text + "\n# Legacy field reference\nblocked_reasons: list[str]\n",
        encoding="utf-8",
    )
    original_engine = _checker.ENGINE_MODULE
    try:
        _checker.ENGINE_MODULE = temp_engine
        result = check_all()
        assert not result["passed"], result["errors"]
        assert any("blocked_reasons" in e for e in result["errors"]), result["errors"]
    finally:
        _checker.ENGINE_MODULE = original_engine


def test_checker_allows_archived_blocked_reasons_reference(tmp_path: Path) -> None:
    archived_doc = REPO_ROOT / "_test_archived_blocked_reasons_note.md"
    archived_doc.write_text(
        "# Archived note\n\n> Status: superseded / archived.\n\n"
        "Earlier drafts used `blocked_reasons`.\n",
        encoding="utf-8",
    )
    try:
        result = check_all()
        assert result["passed"], result["errors"]
    finally:
        archived_doc.unlink(missing_ok=True)


def test_checker_imports_no_network_or_credentials() -> None:
    source = Path(_checker.__file__).read_text(encoding="utf-8")
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


def test_checker_fails_when_bootstrap_routing_removed(tmp_path: Path) -> None:
    temp_bootstrap = tmp_path / "cli_bootstrap.py"
    temp_bootstrap.write_text(
        BOOTSTRAP_MODULE.read_text(encoding="utf-8").replace(
            "readiness-envelope", "readiness-envelope-removed"
        ),
        encoding="utf-8",
    )
    original_bootstrap = _checker.BOOTSTRAP_MODULE
    try:
        _checker.BOOTSTRAP_MODULE = temp_bootstrap
        result = check_all()
        assert not result["passed"], result["errors"]
    finally:
        _checker.BOOTSTRAP_MODULE = original_bootstrap
