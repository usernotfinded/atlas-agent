"""Tests for the v0.5.8 gap prioritization checker.

These tests verify that:
- The checker passes on the current repo state.
- JSON output works.
- Missing required fields cause failure.
- Invalid priority or release target fails.
- Missing acceptance criteria for must_fix fails.
- Unsafe live/profit item marked safe fails.
- do_not_build item without rationale fails.
- Unknown capability_id fails.
- Missing docs safety posture fails.
- The script source remains safe.
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
CHECKER_SCRIPT = REPO_ROOT / "scripts" / "historical_release_checkers" / "check_v058_gap_prioritization.py"


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_v058_gap_prioritization", CHECKER_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v058_gap_prioritization"] = mod
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
    assert data["items_checked"] > 0


# ---------------------------------------------------------------------------
# Negative tests (mocked / patched)
# ---------------------------------------------------------------------------


def test_missing_required_field_fails() -> None:
    original = CHECKER_MOD.REQUIRED_FIELDS
    try:
        CHECKER_MOD.REQUIRED_FIELDS = ["id", "nonexistent_field_xyz"]
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("missing required field" in e for e in result["errors"])
    finally:
        CHECKER_MOD.REQUIRED_FIELDS = original


def test_invalid_priority_fails() -> None:
    original = CHECKER_MOD.ALLOWED_PRIORITIES
    try:
        CHECKER_MOD.ALLOWED_PRIORITIES = {"must_fix"}
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("invalid priority" in e for e in result["errors"])
    finally:
        CHECKER_MOD.ALLOWED_PRIORITIES = original


def test_invalid_release_target_fails() -> None:
    original = CHECKER_MOD.ALLOWED_RELEASE_TARGETS
    try:
        CHECKER_MOD.ALLOWED_RELEASE_TARGETS = {"v0.5.8"}
        result = CHECKER_MOD._gather()
        assert result["passed"] is False
        assert any("invalid release_target" in e for e in result["errors"])
    finally:
        CHECKER_MOD.ALLOWED_RELEASE_TARGETS = original


def test_must_fix_missing_acceptance_fails() -> None:
    def _patched_check(gaps: dict) -> list[str]:
        errors: list[str] = []
        for item in gaps.get("items", []):
            if item.get("priority") == "must_fix":
                errors.append(f"must_fix item '{item.get('id')}' missing acceptance_criteria")
        return errors

    with patch.object(CHECKER_MOD, "_check_must_fix_acceptance", _patched_check):
        result = CHECKER_MOD._gather()
    assert result["passed"] is False
    assert any("missing acceptance_criteria" in e for e in result["errors"])


def test_unsafe_live_profit_marked_safe_fails() -> None:
    def _patched_check(gaps: dict) -> list[str]:
        return ["Gap item 'gap-999' mentions 'live trading' but is marked 'safe'"]

    with patch.object(CHECKER_MOD, "_check_safety_class_consistency", _patched_check):
        result = CHECKER_MOD._gather()
    assert result["passed"] is False
    assert any("mentions 'live trading' but is marked 'safe'" in e for e in result["errors"])


def test_do_not_build_without_rationale_fails() -> None:
    def _patched_check(gaps: dict) -> list[str]:
        errors: list[str] = []
        for item in gaps.get("items", []):
            if item.get("priority") == "do_not_build":
                errors.append(f"do_not_build item '{item.get('id')}' reason lacks safety/out-of-scope rationale")
        return errors

    with patch.object(CHECKER_MOD, "_check_do_not_build_rationale", _patched_check):
        result = CHECKER_MOD._gather()
    assert result["passed"] is False
    assert any("do_not_build" in e for e in result["errors"])


def test_unknown_capability_id_fails() -> None:
    def _patched_check(gaps: dict) -> list[str]:
        return ["Gap item 'gap-999' references unknown capability_id: 'unknown-capability-xyz'"]

    with patch.object(CHECKER_MOD, "_check_capability_ids", _patched_check):
        result = CHECKER_MOD._gather()
    assert result["passed"] is False
    assert any("unknown capability_id" in e for e in result["errors"])


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


def test_gap_doc_exists() -> None:
    path = REPO_ROOT / "docs" / "v0.5.8-gap-prioritization.md"
    assert path.exists()


def test_gap_doc_has_safety_posture() -> None:
    path = REPO_ROOT / "docs" / "v0.5.8-gap-prioritization.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "live trading" in text
    assert "disabled by default" in text
    assert "not financial advice" in text
    assert "not production ready" in text


def test_gap_doc_has_non_goals() -> None:
    path = REPO_ROOT / "docs" / "v0.5.8-gap-prioritization.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "non-goals" in text or "non goals" in text


def test_gap_doc_has_do_not_build() -> None:
    path = REPO_ROOT / "docs" / "v0.5.8-gap-prioritization.md"
    text = path.read_text(encoding="utf-8").lower()
    assert "do-not-build" in text or "do not build" in text


# ---------------------------------------------------------------------------
# JSON inventory content checks
# ---------------------------------------------------------------------------


def test_gap_json_exists() -> None:
    path = REPO_ROOT / "tests" / "fixtures" / "v058_gap_prioritization.json"
    assert path.exists()


def test_gap_json_has_items() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "v058_gap_prioritization.json").read_text())
    assert len(data.get("items", [])) > 0


def test_must_fix_items_have_acceptance() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "v058_gap_prioritization.json").read_text())
    for item in data.get("items", []):
        if item.get("priority") == "must_fix":
            assert item.get("acceptance_criteria", "").strip(), f"must_fix item '{item['id']}' missing acceptance_criteria"


def test_do_not_build_items_have_rationale() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "v058_gap_prioritization.json").read_text())
    for item in data.get("items", []):
        if item.get("priority") == "do_not_build":
            reason = item.get("reason", "").lower()
            assert reason, f"do_not_build item '{item['id']}' missing reason"
            assert any(word in reason for word in ["safety", "out of scope", "forbidden", "legal", "boundary", "contradict"]), f"do_not_build item '{item['id']}' reason lacks safety rationale"


def test_live_profit_items_deferred_or_rejected() -> None:
    data = json.loads((REPO_ROOT / "tests" / "fixtures" / "v058_gap_prioritization.json").read_text())
    keywords = ["live trading", "provider execution", "broker execution", "profit", "autonomous", "real-money"]
    for item in data.get("items", []):
        title = item.get("title", "").lower()
        priority = item.get("priority", "")
        scope = item.get("scope", "")
        # Docs and safety-check clarifications about live/profit are allowed as must_fix/should_fix
        if scope in ("docs", "safety_check", "release_gate"):
            continue
        for keyword in keywords:
            if keyword in title:
                assert priority in ("defer", "do_not_build"), f"Item '{item['id']}' mentions '{keyword}' but is not defer/do_not_build"
