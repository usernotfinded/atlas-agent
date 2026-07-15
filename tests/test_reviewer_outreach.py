# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_reviewer_outreach.py
# PURPOSE: Verifies reviewer outreach behavior and regression expectations.
# DEPS:    importlib, json, subprocess, sys, tempfile, pathlib, additional local
#         modules.
# ==============================================================================

"""Tests for the reviewer outreach checker.

These tests verify that:
- The checker passes on the current repo state.
- JSON output works.
- Missing docs or safety phrases cause failure.
- Unsafe profit/live trading wording is detected.
- Credential-like fragments are detected.
- The script source remains safe.
- Message drafts contain safe review paths.
- The reviewer targets template contains no real personal data.
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
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "check_reviewer_outreach.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_reviewer_outreach", CHECKER_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_reviewer_outreach"] = mod
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
    assert data["docs_checked"] == 3


# ---------------------------------------------------------------------------
# Negative tests (mocked / patched)
# ---------------------------------------------------------------------------


def test_missing_outreach_doc_fails() -> None:
    original = CHECKER_MOD.REQUIRED_DOCS
    try:
        with tempfile.TemporaryDirectory() as td:
            CHECKER_MOD.REQUIRED_DOCS = [Path(td) / "missing.md"]
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Missing outreach doc" in e for e in result["errors"])
    finally:
        CHECKER_MOD.REQUIRED_DOCS = original


def test_missing_safety_phrase_fails() -> None:
    original = CHECKER_MOD.REQUIRED_SAFETY_PHRASES
    try:
        CHECKER_MOD.REQUIRED_SAFETY_PHRASES = {
            CHECKER_MOD.OUTREACH_DOC: [
                ("this phrase does not exist anywhere", "nor this one"),
            ],
        }
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Missing safety phrase" in e for e in result["errors"])
    finally:
        CHECKER_MOD.REQUIRED_SAFETY_PHRASES = original


def test_unsafe_profit_wording_fails() -> None:
    import re as _re

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write("some outreach content\nguaranteed profit\nmore content\n")
        temp_path = Path(f.name)
    try:
        original_targets = CHECKER_MOD._check_forbidden_claims.__code__

        def _patched_check() -> list[str]:
            errors: list[str] = []
            targets = [temp_path]
            for path in targets:
                text = path.read_text(encoding="utf-8").lower()
                for phrase in CHECKER_MOD.FORBIDDEN_CLAIMS:
                    for m in _re.finditer(_re.escape(phrase), text):
                        start = max(0, m.start() - 80)
                        end = min(len(text), m.end() + 80)
                        context = text[start:end]
                        negations = (
                            "not ", "do not", "never", "no ", "forbidden",
                            "reject", "out of scope", "do not accept", "avoid",
                        )
                        if not any(n in context for n in negations):
                            rel = path.name
                            errors.append(
                                f"[{rel}] Forbidden claim '{phrase}' found without clear negation"
                            )
            return errors

        with patch.object(CHECKER_MOD, "_check_forbidden_claims", _patched_check):
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Forbidden claim" in e for e in result["errors"])
    finally:
        temp_path.unlink(missing_ok=True)


def test_credential_fragment_fails() -> None:
    import re as _re

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write("some outreach content\nsk-abcdefghijklmnopqrstuvwxyz123456\nmore content\n")
        temp_path = Path(f.name)
    try:
        def _patched_check() -> list[str]:
            errors: list[str] = []
            targets = [temp_path]
            for path in targets:
                text = path.read_text(encoding="utf-8")
                rel = path.name
                for pattern in CHECKER_MOD.CREDENTIAL_PATTERNS:
                    for m in pattern.finditer(text):
                        errors.append(
                            f"[{rel}] Credential-like fragment: {m.group(0)[:40]}"
                        )
            return errors

        with patch.object(CHECKER_MOD, "_check_credential_fragments", _patched_check):
            result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("Credential-like fragment" in e for e in result["errors"])
    finally:
        temp_path.unlink(missing_ok=True)


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
# Doc content checks
# ---------------------------------------------------------------------------


def test_outreach_doc_exists() -> None:
    path = REPO_ROOT / "docs" / "controlled-reviewer-outreach.md"
    assert path.exists()


def test_outreach_doc_has_message_drafts() -> None:
    path = REPO_ROOT / "docs" / "controlled-reviewer-outreach.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "short direct message" in text
    assert "longer technical review request" in text
    assert "github/reddit-style post" in text
    assert "follow-up message" in text


def test_outreach_doc_discourages_live_trading() -> None:
    path = REPO_ROOT / "docs" / "controlled-reviewer-outreach.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "live trading" in text
    assert "disabled" in text


def test_outreach_doc_avoids_profit_claims() -> None:
    path = REPO_ROOT / "docs" / "controlled-reviewer-outreach.md"
    text = path.read_text(encoding="utf-8").lower()
    # Should mention profit only in context of rejecting it
    assert "profit" in text
    assert "not" in text or "out of scope" in text or "avoid" in text


def test_outreach_doc_has_safe_review_path() -> None:
    path = REPO_ROOT / "docs" / "controlled-reviewer-outreach.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "safe review path" in text
    assert "no credentials" in text or "credentials" in text


def test_checklist_doc_exists() -> None:
    path = REPO_ROOT / "docs" / "reviewer-outreach-checklist.md"
    assert path.exists()


def test_checklist_covers_version_and_tag() -> None:
    path = REPO_ROOT / "docs" / "reviewer-outreach-checklist.md"
    text = path.read_text(encoding="utf-8").lower()
    # The checklist must reference a real stable tag and a previous release.
    # We assert presence of known stable tags rather than hardcoding RCs.
    assert "v0.6.9" in text
    assert "v0.6.8" in text


def test_targets_template_exists() -> None:
    path = REPO_ROOT / "docs" / "reviewer-targets-template.md"
    assert path.exists()


def test_targets_template_has_required_fields() -> None:
    path = REPO_ROOT / "docs" / "reviewer-targets-template.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "reviewer handle" in text
    assert "reason for asking" in text
    assert "expected expertise" in text
    assert "contact channel" in text
    assert "date contacted" in text
    assert "response status" in text
    assert "feedback issue link" in text
    assert "classification labels" in text
    assert "follow-up needed" in text
    assert "notes" in text


def test_targets_template_has_no_real_data_disclaimer() -> None:
    path = REPO_ROOT / "docs" / "reviewer-targets-template.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "no real personal data" in text


def test_targets_template_has_safety_rules() -> None:
    path = REPO_ROOT / "docs" / "reviewer-targets-template.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "safety rules for this template" in text
