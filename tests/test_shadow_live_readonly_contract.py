from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_shadow_live_readonly_contract import check_all

REPO_ROOT = Path(__file__).resolve().parent.parent
SHADOW_MODULE = (
    REPO_ROOT / "src" / "atlas_agent" / "agent" / "autonomous_paper_shadow_live.py"
)
DOC = REPO_ROOT / "docs" / "shadow-live-readonly-comparison.md"


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
    module = SHADOW_MODULE
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
    ],
)
def test_checker_fails_on_forbidden_pattern(pattern: str) -> None:
    module = SHADOW_MODULE
    original_text = module.read_text(encoding="utf-8")
    try:
        module.write_text(original_text + "\n" + pattern + "\n", encoding="utf-8")
        result = check_all()
        assert not result["passed"], f"Expected failure for pattern: {pattern}"
    finally:
        module.write_text(original_text, encoding="utf-8")


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
