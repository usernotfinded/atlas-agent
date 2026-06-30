from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_SCRIPT = REPO_ROOT / "scripts" / "check_operator_approval_gate_contract.py"


def test_contract_checker_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CONTRACT_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"Contract check failed:\n{result.stdout}\n{result.stderr}"
    assert "PASSED" in result.stdout


def test_contract_checker_json_mode() -> None:
    result = subprocess.run(
        [sys.executable, str(CONTRACT_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    import json

    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["errors"] == []


def test_contract_checker_module_api() -> None:
    # Importing as a module must not execute side effects.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_operator_approval_gate_contract", CONTRACT_SCRIPT
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    result = module.check_all()
    assert result["passed"] is True
    assert result["errors"] == []
