"""Tests for v0.6.0 readiness checker.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_v060_readiness.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v060_readiness", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v060_readiness"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result


class TestScriptAndDocsExist:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

    def test_readiness_doc_exists(self) -> None:
        assert (ROOT / "docs" / "releases" / "v0.6.0-readiness.md").exists()

    def test_capability_inventory_doc_exists(self) -> None:
        assert (ROOT / "docs" / "v0.6-capability-inventory.md").exists()

    def test_roadmap_doc_exists(self) -> None:
        assert (ROOT / "docs" / "v0.6-roadmap.md").exists()


class TestCheckerPass:
    def test_script_runs_successfully(self) -> None:
        result = _run_script()
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_json_output_valid(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["errors"] == []
        assert data["checks"]["docs"] > 0
        assert data["checks"]["source_modules"] > 0
        assert data["checks"]["test_files"] > 0
        assert data["checks"]["cli_subcommands"] > 0


class TestModuleFunctions:
    def test_check_required_files_detects_missing(self) -> None:
        mod = _load_script_module()
        missing = ROOT / "nonexistent" / "file.md"
        errors = mod._check_required_files([missing], "doc")
        assert len(errors) == 1
        assert "Missing doc" in errors[0]

    def test_check_changelog_unreleased(self) -> None:
        mod = _load_script_module()
        errors = mod._check_changelog_unreleased()
        assert "CHANGELOG.md missing [Unreleased]" not in errors
        assert "premature v0.6.0 release section" not in errors

    def test_check_version_identity(self) -> None:
        mod = _load_script_module()
        errors = mod._check_version_identity()
        assert len(errors) == 0, f"Version check errors: {errors}"

    def test_check_cli_contract(self) -> None:
        mod = _load_script_module()
        errors = mod._check_cli_contract()
        assert len(errors) == 0, f"CLI contract errors: {errors}"

    def test_check_no_v060_tag(self) -> None:
        mod = _load_script_module()
        errors = mod._check_no_v060_tag()
        # This may fail if a v0.6.0 tag exists locally; in CI it should pass.
        assert "v0.6.0 tag already exists" not in errors
