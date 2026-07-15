# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_feedback_intake.py
# PURPOSE: Verifies feedback intake behavior and regression expectations.
# DEPS:    importlib, json, subprocess, sys, pathlib, types, additional local
#         modules.
# ==============================================================================

"""Tests for the public feedback intake checker.

These tests verify that:
- The checker passes on the current repo state.
- JSON output works.
- Missing templates or safety warnings cause failure.
- Unsafe phrases are detected.
- The script source remains safe.
"""

# --- IMPORTS ---

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_feedback_intake.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_feedback_intake", CHECKER_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_feedback_intake"] = mod
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
    assert data["templates_checked"] == 6
    assert data["docs_checked"] == 3


# ---------------------------------------------------------------------------
# Negative tests (mocked)
# ---------------------------------------------------------------------------


def test_missing_template_fails() -> None:
    original = CHECKER_MOD.REQUIRED_TEMPLATES
    try:
        CHECKER_MOD.REQUIRED_TEMPLATES = [
            ".github/ISSUE_TEMPLATE/reviewer_feedback.yml",
            ".github/ISSUE_TEMPLATE/nonexistent_template.yml",
        ]
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Missing template" in e for e in result["errors"])
    finally:
        CHECKER_MOD.REQUIRED_TEMPLATES = original


def test_missing_safety_warning_fails() -> None:
    original = CHECKER_MOD.REQUIRED_SAFETY_WARNINGS
    try:
        CHECKER_MOD.REQUIRED_SAFETY_WARNINGS = [
            ("this warning does not exist", "nor this"),
        ]
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("missing safety warning" in e for e in result["errors"])
    finally:
        CHECKER_MOD.REQUIRED_SAFETY_WARNINGS = original


def test_unsafe_phrase_detected() -> None:
    # Use a temporary target file with an unsafe phrase and no negations
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("some doc content\nguaranteed profit\nmore content\n")
        temp_path = Path(f.name)
    try:
        original_targets = CHECKER_MOD._check_unsafe_phrases.__code__
        # Patch the targets inside _check_unsafe_phrases by replacing the function
        def _patched_check_unsafe() -> list[str]:
            import re as _re
            errors: list[str] = []
            targets = [temp_path]
            for path in targets:
                text = path.read_text(encoding="utf-8").lower()
                for phrase in CHECKER_MOD.UNSAFE_PHRASES:
                    for m in _re.finditer(_re.escape(phrase), text):
                        start = max(0, m.start() - 80)
                        end = min(len(text), m.end() + 80)
                        context = text[start:end]
                        negations = ("not ", "do not", "never", "no ", "forbidden", "reject", "out of scope", "do not accept")
                        if not any(n in context for n in negations):
                            rel = path.name
                            errors.append(f"[{rel}] Unsafe phrase '{phrase}' found without clear negation")
            return errors

        with patch.object(CHECKER_MOD, "_check_unsafe_phrases", _patched_check_unsafe):
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Unsafe phrase" in e for e in result["errors"])
    finally:
        temp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Source safety checks
# ---------------------------------------------------------------------------


def test_script_source_no_shell_true() -> None:
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_script_source_no_unsafe_network_calls() -> None:
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in checker script"


# ---------------------------------------------------------------------------
# Template content tests
# ---------------------------------------------------------------------------


def test_reviewer_feedback_template_exists() -> None:
    path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
    assert path.exists()


def test_reviewer_feedback_contains_no_paste_credentials() -> None:
    path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
    text = path.read_text(encoding="utf-8").lower()
    assert "paste" in text
    assert "credentials" in text or "secrets" in text


def test_reviewer_feedback_blocks_real_money_broker() -> None:
    path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
    text = path.read_text(encoding="utf-8").lower()
    assert "real-money" in text or "real money" in text
    assert "broker" in text


def test_reviewer_feedback_blocks_profit_requests() -> None:
    path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
    text = path.read_text(encoding="utf-8").lower()
    assert "profit" in text


def test_reviewer_feedback_blocks_safety_bypass() -> None:
    path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
    text = path.read_text(encoding="utf-8").lower()
    assert "bypass" in text
    assert "safety" in text


def test_reviewer_feedback_blocks_live_trading_enablement() -> None:
    path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
    text = path.read_text(encoding="utf-8").lower()
    assert "live trading" in text


def test_reviewer_feedback_has_disclaimer() -> None:
    path = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "reviewer_feedback.yml"
    text = path.read_text(encoding="utf-8").lower()
    assert "not financial advice" in text


# ---------------------------------------------------------------------------
# Docs content tests
# ---------------------------------------------------------------------------


def test_feedback_intake_process_exists() -> None:
    path = REPO_ROOT / "docs" / "feedback-intake-process.md"
    assert path.exists()


def test_feedback_intake_explains_blocker_vs_non_blocker() -> None:
    path = REPO_ROOT / "docs" / "feedback-intake-process.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "blocker" in text
    assert "non-blocker" in text
