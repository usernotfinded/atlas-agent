# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_feedback_taxonomy.py
# PURPOSE: Verifies feedback taxonomy behavior and regression expectations.
# DEPS:    importlib, json, subprocess, sys, tempfile, pathlib, additional local
#         modules.
# ==============================================================================

"""Tests for the feedback taxonomy checker.

These tests verify that:
- The checker passes on the current repo state.
- JSON output works.
- Missing labels file, groups, or labels cause failure.
- Missing label descriptions cause failure.
- Unsafe risk label wording is detected.
- Missing triage docs cause failure.
- Issue template category mismatches are detected.
- The script source remains safe.
- The triage docs include required guidance.
"""

# --- IMPORTS ---

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_feedback_taxonomy.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_feedback_taxonomy", CHECKER_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_feedback_taxonomy"] = mod
    spec.loader.exec_module(mod)
    return mod


CHECKER_MOD = _load_checker_module()


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


def test_checker_passes_on_current_repo() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_checker_json_output() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["errors"] == []
    assert data["groups_checked"] == 5
    assert data["labels_checked"] == 30


# ---------------------------------------------------------------------------
# Negative tests (mocked / patched)
# ---------------------------------------------------------------------------


def test_missing_labels_file_fails() -> None:
    original = CHECKER_MOD.LABELS_FILE
    try:
        with tempfile.TemporaryDirectory() as td:
            CHECKER_MOD.LABELS_FILE = Path(td) / "labels.yml"
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Missing labels file" in e for e in result["errors"])
    finally:
        CHECKER_MOD.LABELS_FILE = original


def test_missing_required_label_fails() -> None:
    original = CHECKER_MOD.REQUIRED_LABELS
    try:
        CHECKER_MOD.REQUIRED_LABELS = {
            "type": ["type: bug", "type: nonexistent-label"],
        }
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Missing required label" in e for e in result["errors"])
    finally:
        CHECKER_MOD.REQUIRED_LABELS = original


def test_missing_label_description_fails() -> None:
    original = CHECKER_MOD._parse_labels_yml
    try:
        def _fake_parse(path: Path) -> dict[str, list[dict[str, str]]]:
            return {
                "type": [
                    {"name": "type: bug", "color": "d73a4a"},  # missing description
                ],
            }

        with patch.object(CHECKER_MOD, "_parse_labels_yml", _fake_parse):
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("missing description" in e for e in result["errors"])
    finally:
        pass


def test_unsafe_risk_label_wording_fails() -> None:
    original = CHECKER_MOD._parse_labels_yml
    try:
        def _fake_parse(path: Path) -> dict[str, list[dict[str, str]]]:
            return {
                "risk": [
                    {
                        "name": "risk: live-trading",
                        "color": "b60205",
                        "description": "Enables live trading immediately.",
                    },
                ],
            }

        with patch.object(CHECKER_MOD, "_parse_labels_yml", _fake_parse):
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("conservative safety wording" in e for e in result["errors"])
    finally:
        pass


def test_missing_triage_doc_fails() -> None:
    original = CHECKER_MOD.TRIAGE_DOC
    try:
        with tempfile.TemporaryDirectory() as td:
            CHECKER_MOD.TRIAGE_DOC = Path(td) / "missing.md"
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Missing triage doc" in e for e in result["errors"])
    finally:
        CHECKER_MOD.TRIAGE_DOC = original


def test_template_category_mismatch_fails() -> None:
    original = CHECKER_MOD.TEMPLATE_COMPATIBLE_CATEGORIES
    try:
        CHECKER_MOD.TEMPLATE_COMPATIBLE_CATEGORIES = ["nonexistent-category-xyz"]
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("lacks recognizable category" in e for e in result["errors"])
    finally:
        CHECKER_MOD.TEMPLATE_COMPATIBLE_CATEGORIES = original


# ---------------------------------------------------------------------------
# Source safety checks
# ---------------------------------------------------------------------------


def test_script_source_no_shell_true() -> None:
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_script_source_no_network_calls() -> None:
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket", "requests"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in checker script"


def test_script_source_no_github_api() -> None:
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    assert "github.com" not in source
    assert "api.github" not in source
    assert "gh api" not in source


# ---------------------------------------------------------------------------
# Docs content checks
# ---------------------------------------------------------------------------


def test_triage_doc_exists() -> None:
    path = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
    assert path.exists()


def test_triage_doc_explains_blocker_vs_non_blocker() -> None:
    path = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "blocker" in text
    assert "non-blocker" in text


def test_triage_doc_explains_out_of_scope() -> None:
    path = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "out of scope" in text


def test_triage_doc_explains_safety_bypass() -> None:
    path = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "bypass" in text
    assert "safety" in text


def test_triage_doc_covers_live_trading() -> None:
    path = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "live trading" in text


def test_triage_doc_covers_provider_execution() -> None:
    path = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "provider execution" in text


def test_triage_doc_covers_broker_execution() -> None:
    path = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "broker execution" in text


def test_triage_doc_avoids_profit_claims() -> None:
    path = REPO_ROOT / "docs" / "feedback-triage-taxonomy.md"
    text = path.read_text(encoding="utf-8").lower()
    # Doc should mention profit only in the context of rejecting it
    assert "profit" in text
    assert "does not imply profitability" in text or "not accept" in text or "out of scope" in text


# ---------------------------------------------------------------------------
# Labels file content checks
# ---------------------------------------------------------------------------


def test_labels_file_exists() -> None:
    path = REPO_ROOT / ".github" / "labels.yml"
    assert path.exists()


def test_labels_file_has_all_groups() -> None:
    groups = CHECKER_MOD._parse_labels_yml(REPO_ROOT / ".github" / "labels.yml")
    for group in CHECKER_MOD.REQUIRED_GROUPS:
        assert group in groups, f"Missing group: {group}"


def test_labels_file_has_all_required_labels() -> None:
    groups = CHECKER_MOD._parse_labels_yml(REPO_ROOT / ".github" / "labels.yml")
    for group, expected in CHECKER_MOD.REQUIRED_LABELS.items():
        actual = {item["name"] for item in groups.get(group, [])}
        for name in expected:
            assert name in actual, f"Missing label: {name}"


def test_risk_labels_have_conservative_descriptions() -> None:
    groups = CHECKER_MOD._parse_labels_yml(REPO_ROOT / ".github" / "labels.yml")
    for item in groups.get("risk", []):
        desc = item.get("description", "").lower()
        assert "does not" in desc, f"Risk label '{item['name']}' lacks conservative wording"
