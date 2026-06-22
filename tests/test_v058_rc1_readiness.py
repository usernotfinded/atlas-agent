"""Tests for the v0.5.8 RC1 readiness dry-run gate.

These tests verify that:
- The checker passes on the current repo state.
- JSON output works.
- Wrong current version fails.
- Missing v0.5.8 gap prioritization fails.
- Missing capability inventory fails.
- Unsafe live/profit wording fails.
- Missing safety posture in docs fails.
- Staged generated evidence artifact fails.
- Script source does not contain shell=True.
- Script source does not contain network/GitHub API calls.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
READINESS_SCRIPT = REPO_ROOT / "scripts" / "historical_release_checkers" / "check_v058_rc1_readiness.py"


def _load_readiness_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_v058_rc1_readiness", READINESS_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v058_rc1_readiness"] = mod
    spec.loader.exec_module(mod)
    return mod


READINESS_MOD = _load_readiness_module()


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


def test_readiness_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(READINESS_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_readiness_script_json_output() -> None:
    result = subprocess.run(
        [sys.executable, str(READINESS_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["errors"] == []
    assert data["current_dev_version"] == "0.6.14"
    assert data["stable_tag"] == "v0.5.7"


# ---------------------------------------------------------------------------
# Negative tests (mocked / patched)
# ---------------------------------------------------------------------------


def test_wrong_current_version_fails() -> None:
    original = READINESS_MOD.CURRENT_DEV_VERSION
    try:
        READINESS_MOD.CURRENT_DEV_VERSION = "0.5.8.1"
        result = READINESS_MOD._gather()
        assert result["passed"] is False
        assert any("0.5.8.1" in e for e in result["errors"])
    finally:
        READINESS_MOD.CURRENT_DEV_VERSION = original


def test_missing_gap_prioritization_fails() -> None:
    original = READINESS_MOD.GAP_FILE
    try:
        READINESS_MOD.GAP_FILE = Path("/nonexistent/gap.json")
        result = READINESS_MOD._gather()
        assert result["passed"] is False
        assert any("gap prioritization" in e.lower() for e in result["errors"])
    finally:
        READINESS_MOD.GAP_FILE = original


def test_missing_capability_inventory_fails() -> None:
    original = READINESS_MOD.INVENTORY_FILE
    try:
        READINESS_MOD.INVENTORY_FILE = Path("/nonexistent/inventory.json")
        result = READINESS_MOD._gather()
        assert result["passed"] is False
        assert any("capability inventory" in e.lower() for e in result["errors"])
    finally:
        READINESS_MOD.INVENTORY_FILE = original


def test_unsafe_live_profit_wording_fails() -> None:
    def _patched_scan(text: str, rel_path: str) -> list[str]:
        return [f"[{rel_path}] Forbidden positive claim 'live trading ready'"]

    with patch.object(READINESS_MOD, "_scan_text", _patched_scan):
        result = READINESS_MOD._gather()
    assert result["passed"] is False
    assert any("live trading ready" in e for e in result["errors"])


def test_missing_safety_posture_in_docs_fails() -> None:
    def _patched_check() -> list[str]:
        return ["product-capability-inventory.md missing safety phrase: 'not financial advice'"]

    with patch.object(READINESS_MOD, "_check_safety_posture_in_docs", _patched_check):
        result = READINESS_MOD._gather()
    assert result["passed"] is False
    assert any("missing safety phrase" in e for e in result["errors"])


def test_staged_generated_evidence_artifact_fails() -> None:
    def _patched_check() -> list[str]:
        return ["Generated evidence artifact staged: artifacts/release_evidence/evidence.json"]

    with patch.object(READINESS_MOD, "_check_no_generated_artifacts_staged", _patched_check):
        result = READINESS_MOD._gather()
    assert result["passed"] is False
    assert any("Generated evidence artifact staged" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Source safety checks
# ---------------------------------------------------------------------------


def test_script_source_no_shell_true() -> None:
    source = READINESS_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_script_source_no_network_calls() -> None:
    source = READINESS_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket", "requests"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in readiness script"


def test_script_source_no_github_api() -> None:
    source = READINESS_SCRIPT.read_text(encoding="utf-8")
    assert "github.com" not in source
    assert "api.github" not in source
    assert "gh api" not in source
