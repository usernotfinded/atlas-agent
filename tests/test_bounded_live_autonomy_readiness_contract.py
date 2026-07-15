# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_bounded_live_autonomy_readiness_contract.py
# PURPOSE: Verifies bounded live autonomy readiness contract behavior and
#         regression expectations.
# DEPS:    json, subprocess, sys, pathlib, typing, pytest.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_SCRIPT = REPO_ROOT / "scripts" / "check_bounded_live_autonomy_readiness_contract.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["errors"] == []


def test_contract_checker_module_api() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_bounded_live_autonomy_readiness_contract", CONTRACT_SCRIPT
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    result = module.check_all()
    assert result["passed"] is True
    assert result["errors"] == []


def test_checker_fails_if_input_paths_reintroduced(monkeypatch: Any) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_bounded_live_autonomy_readiness_contract", CONTRACT_SCRIPT
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    bad_source = '\n    def to_dict(self):\n        return {"input_paths": {}}\n    '
    monkeypatch.setattr(
        module, "_get_class_method_source", lambda _text, _cls, _meth: bad_source
    )
    errors = module._check_no_input_paths_in_serialization()
    assert any("forbidden 'input_paths' key" in e for e in errors)


def test_checker_fails_if_path_strings_serialized(monkeypatch: Any) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_bounded_live_autonomy_readiness_contract", CONTRACT_SCRIPT
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    bad_source = '\n    def to_dict(self):\n        return {"input_paths": {label: str(path) for label, path in self.input_paths.items()}}\n    '
    monkeypatch.setattr(
        module, "_get_class_method_source", lambda _text, _cls, _meth: bad_source
    )
    errors = module._check_no_path_string_serialization()
    assert any("str(path)" in e for e in errors)


def test_checker_passes_with_safe_basename_fingerprint_behavior() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_bounded_live_autonomy_readiness_contract", CONTRACT_SCRIPT
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    errors = module._check_output_uses_safe_identifiers()
    assert errors == []
    errors = module._check_no_input_paths_in_serialization()
    assert errors == []
    errors = module._check_no_path_string_serialization()
    assert errors == []
