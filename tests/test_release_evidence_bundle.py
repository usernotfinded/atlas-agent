# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_release_evidence_bundle.py
# PURPOSE: Verifies release evidence bundle behavior and regression
#         expectations.
# DEPS:    importlib, json, os, subprocess, sys, pathlib, additional local
#         modules.
# ==============================================================================

"""Tests for the release evidence bundle generator.

These tests verify that:
- The bundle script remains safe (no shell=True, no suspicious imports).
- JSON and Markdown reports are generated correctly.
- Failed commands cause passed: false.
- Protected boundary diffs are detected.
- Path redaction works.
- CLI flags (--skip-slow, --include-quick-check) behave correctly.
- Safety summary remains conservative.
"""

# --- IMPORTS ---

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_SCRIPT = REPO_ROOT / "scripts" / "build_release_evidence_bundle.py"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _load_bundle_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_release_evidence_bundle", BUNDLE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_release_evidence_bundle"] = mod
    spec.loader.exec_module(mod)
    return mod


BUNDLE_MOD = _load_bundle_module()


# ---------------------------------------------------------------------------
# Source safety checks
# ---------------------------------------------------------------------------


def test_script_source_no_shell_true() -> None:
    source = BUNDLE_SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in source


def test_script_source_no_unsafe_network_calls() -> None:
    source = BUNDLE_SCRIPT.read_text(encoding="utf-8")
    suspicious = ["urllib.request", "urllib.parse", "http.client", "socket"]
    for name in suspicious:
        assert name not in source, f"Suspicious import '{name}' found in bundle script"


# ---------------------------------------------------------------------------
# Unit tests via mocked gather
# ---------------------------------------------------------------------------


def _fake_run(cmd: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str, str]:
    """Fake runner that makes all checks pass."""
    # git diff --check must have empty stdout to be considered clean
    if cmd[:2] == ["git", "diff"] and "--check" in cmd:
        return 0, "", ""
    return 0, "ok", ""


def _failing_run(cmd: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str, str]:
    """Fake runner that makes the first check fail."""
    if "check_version_consistency" in str(cmd):
        return 2, "", "version mismatch"
    if cmd[:2] == ["git", "diff"] and "--check" in cmd:
        return 0, "", ""
    return 0, "ok", ""


def test_gather_all_passed() -> None:
    with patch.object(BUNDLE_MOD, "_run", _fake_run):
        evidence = BUNDLE_MOD._gather_evidence(skip_slow=True, include_quick_check=False)
    assert evidence["passed"] is True
    assert len(evidence["checks"]) == len(BUNDLE_MOD._FAST_CHECKS)
    for check in evidence["checks"]:
        assert check["passed"] is True


def test_gather_failed_check_causes_failure() -> None:
    with patch.object(BUNDLE_MOD, "_run", _failing_run):
        evidence = BUNDLE_MOD._gather_evidence(skip_slow=True, include_quick_check=False)
    assert evidence["passed"] is False
    assert any(c["name"] == "check_version_consistency" and not c["passed"] for c in evidence["checks"])


def test_gather_skip_slow_excludes_smoke() -> None:
    with patch.object(BUNDLE_MOD, "_run", _fake_run):
        evidence = BUNDLE_MOD._gather_evidence(skip_slow=True, include_quick_check=False)
    names = [c["name"] for c in evidence["checks"]]
    assert "smoke_reviewer_golden_path" not in names


def test_gather_include_quick_check() -> None:
    with patch.object(BUNDLE_MOD, "_run", _fake_run):
        evidence = BUNDLE_MOD._gather_evidence(skip_slow=True, include_quick_check=True)
    names = [c["name"] for c in evidence["checks"]]
    assert "release_check_quick" in names


def test_gather_default_includes_slow() -> None:
    with patch.object(BUNDLE_MOD, "_run", _fake_run):
        evidence = BUNDLE_MOD._gather_evidence(skip_slow=False, include_quick_check=False)
    names = [c["name"] for c in evidence["checks"]]
    assert "smoke_reviewer_golden_path" in names


def test_protected_boundary_diff_detected() -> None:
    original_protected_diff = BUNDLE_MOD._protected_boundary_diff

    def _fake_protected_diff(tag: str) -> dict[str, str]:
        return {
            "src/atlas_agent/config": "M\tsrc/atlas_agent/config/foo.py",
            "src/atlas_agent/brokers": "",
            "src/atlas_agent/execution": "",
            "src/atlas_agent/safety": "",
            "src/atlas_agent/risk": "",
        }

    with patch.object(BUNDLE_MOD, "_protected_boundary_diff", _fake_protected_diff):
        with patch.object(BUNDLE_MOD, "_run", _fake_run):
            evidence = BUNDLE_MOD._gather_evidence(skip_slow=True, include_quick_check=False)
    assert evidence["protected_boundaries_clean"] is False
    assert evidence["protected_boundaries"]["src/atlas_agent/config"] == ["M\tsrc/atlas_agent/config/foo.py"]


def test_protected_boundary_clean() -> None:
    with patch.object(BUNDLE_MOD, "_run", _fake_run):
        evidence = BUNDLE_MOD._gather_evidence(skip_slow=True, include_quick_check=False)
    # The real repo may or may not have protected boundary changes since v0.5.7.
    # We just verify the field exists and is a boolean.
    assert isinstance(evidence["protected_boundaries_clean"], bool)


def test_safety_summary_conservative() -> None:
    with patch.object(BUNDLE_MOD, "_run", _fake_run):
        evidence = BUNDLE_MOD._gather_evidence(skip_slow=True, include_quick_check=False)
    ss = evidence["safety_summary"]
    assert ss["provider_execution_enabled"] is False
    assert ss["broker_execution_enabled"] is False
    assert ss["live_trading_enabled_by_default"] is False
    assert ss["credentials_loaded"] is False
    assert ss["network_calls_required"] is False


# ---------------------------------------------------------------------------
# Redaction tests
# ---------------------------------------------------------------------------


def test_redact_replaces_repo_root() -> None:
    text = str(REPO_ROOT / "scripts" / "foo.py")
    redacted = BUNDLE_MOD._redact(text)
    assert "<REPO_ROOT>" in redacted
    assert str(REPO_ROOT) not in redacted


def test_redact_replaces_home() -> None:
    home = str(Path.home())
    text = f"{home}/.config/atlas"
    redacted = BUNDLE_MOD._redact(text)
    assert "<HOME>" in redacted
    assert home not in redacted


def test_redact_strips_api_keys() -> None:
    text = "api_key: sk-secret12345\n"
    redacted = BUNDLE_MOD._redact(text)
    assert "<REDACTED>" in redacted
    assert "sk-secret12345" not in redacted


# ---------------------------------------------------------------------------
# Markdown generation test
# ---------------------------------------------------------------------------


def test_markdown_contains_key_sections() -> None:
    with patch.object(BUNDLE_MOD, "_run", _fake_run):
        evidence = BUNDLE_MOD._gather_evidence(skip_slow=True, include_quick_check=False)
    md = BUNDLE_MOD._build_markdown(evidence)
    assert "# Release Evidence Bundle" in md
    assert "## Summary" in md
    assert "## Evidence Checks" in md
    assert "## Safety Summary" in md
    assert "not financial advice" in md.lower()
    assert "live trading remains disabled by default" in md.lower()


# ---------------------------------------------------------------------------
# Integration smoke: script runs without crashing
# ---------------------------------------------------------------------------


def test_script_runs_and_produces_artifacts() -> None:
    result = subprocess.run(
        [sys.executable, str(BUNDLE_SCRIPT), "--skip-slow"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode in (0, 2), result.stderr
    json_path = REPO_ROOT / "artifacts" / "release_evidence" / "evidence.json"
    md_path = REPO_ROOT / "artifacts" / "release_evidence" / "evidence.md"
    assert json_path.exists()
    assert md_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "passed" in data
    assert "checks" in data
