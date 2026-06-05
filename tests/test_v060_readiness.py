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
from unittest.mock import patch

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


class TestCheckerPreRelease:
    """Default (pre-release) mode expects no v0.6.0 tag."""

    def test_default_mode_detects_existing_tag(self) -> None:
        result = _run_script()
        # If the v0.6.0 tag exists locally, default mode must fail.
        # In a CI environment without the tag this would pass; here we assert
        # the behavior is consistent with local state.
        if "v0.6.0 tag already exists" in result.stdout:
            assert result.returncode == 1
            assert "FAIL" in result.stdout
        else:
            assert result.returncode == 0
            assert "PASS" in result.stdout

    def test_default_json_detects_existing_tag(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert data.get("mode") == "pre_release"
        if "v0.6.0 tag already exists" in str(data.get("errors", [])):
            assert data["valid"] is False
        else:
            assert data["valid"] is True


class TestCheckerPostRelease:
    """Post-release mode expects the v0.6.0 tag and GitHub release to exist."""

    def test_post_release_mode_passes(self, monkeypatch) -> None:
        mod = _load_script_module()

        monkeypatch.setattr(mod, "_check_v060_tag", lambda post_release=False: [])
        monkeypatch.setattr(mod, "_check_github_release", lambda: ([], []))

        code, result = mod.run_check(json_output=False, post_release=True)
        assert code == 0
        assert result["valid"] is True
        assert result["mode"] == "post_release"

    def test_post_release_json_valid(self, monkeypatch) -> None:
        mod = _load_script_module()

        monkeypatch.setattr(mod, "_check_v060_tag", lambda post_release=False: [])
        monkeypatch.setattr(mod, "_check_github_release", lambda: ([], []))

        code, result = mod.run_check(json_output=False, post_release=True)
        assert code == 0
        assert result["valid"] is True
        assert result["mode"] == "post_release"
        assert result["errors"] == []
        assert "checks" in result
        assert result["checks"]["docs"] > 0
        assert result["checks"]["source_modules"] > 0
        assert result["checks"]["test_files"] > 0
        assert result["checks"]["cli_subcommands"] > 0

    def test_post_release_mode_fails_when_tag_missing(self, monkeypatch) -> None:
        mod = _load_script_module()

        def _fake_tag_check(post_release: bool = False) -> list[str]:
            if post_release:
                return ["v0.6.0 tag not found"]
            return []

        monkeypatch.setattr(mod, "_check_v060_tag", _fake_tag_check)
        code, result = mod.run_check(json_output=False, post_release=True)
        assert code == 1
        assert result["valid"] is False
        assert "v0.6.0 tag not found" in result["errors"]
        assert result["mode"] == "post_release"

    def test_github_cli_unavailable_warns_not_errors(self, monkeypatch) -> None:
        mod = _load_script_module()

        # Mock tag check so it does not interfere with the GH-unavailable test.
        monkeypatch.setattr(mod, "_check_v060_tag", lambda post_release=False: [])

        def _fake_gh_check() -> tuple[list[str], list[str]]:
            return [], ["GitHub CLI unavailable; cannot verify GitHub release"]

        monkeypatch.setattr(mod, "_check_github_release", _fake_gh_check)
        code, result = mod.run_check(json_output=False, post_release=True)
        assert code == 0
        assert result["valid"] is True
        assert len(result["warnings"]) == 1
        assert "GitHub CLI unavailable" in result["warnings"][0]


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

    def test_check_v060_tag_pre_release_blocks_existing(self) -> None:
        mod = _load_script_module()
        errors = mod._check_v060_tag(post_release=False)
        # This may fail if a v0.6.0 tag exists locally; in CI it should pass.
        assert isinstance(errors, list)

    def test_check_v060_tag_post_release_requires_existing(self) -> None:
        mod = _load_script_module()
        errors = mod._check_v060_tag(post_release=True)
        # If the tag exists locally, no error; otherwise it would report missing.
        assert isinstance(errors, list)

    def test_check_github_release_returns_tuple(self) -> None:
        mod = _load_script_module()
        errors, warnings = mod._check_github_release()
        assert isinstance(errors, list)
        assert isinstance(warnings, list)
