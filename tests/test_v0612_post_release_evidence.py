"""Tests for v0.6.12 post-release evidence checker.

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

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_v0612_post_release_evidence.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v0612_post_release_evidence", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0612_post_release_evidence"] = mod
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


def _make_evidence_json(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "v0.6.12-post-release-evidence.json"
    data = {
        "schema_version": 1,
        "release": "v0.6.12",
        "source_version": "0.6.12",
        "main_commit": "c6f4ddc572902bbc04d8f8b4b262b626999a7abd",
        "tag": "v0.6.12",
        "github_release": "v0.6.12",
        "push_ci_run_id": "27696853914",
        "current_public_release": "v0.6.12",
        "next_planned_release": "v0.6.13",
        "pypi_published": False,
        "release_notes_path": "docs/releases/v0.6.12.md",
        "trust_status_path": "docs/trust/v0.6.12-status.md",
        "live_trading_enabled": False,
        "provider_execution_enabled": False,
        "broker_execution_enabled": False,
        "protected_runtime_boundaries_changed": False,
        "forbidden_claims_check": True,
        "release_check_quick": True,
        "created_after_cutover": True,
    }
    data.update(overrides)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _make_evidence_md(tmp_path: Path) -> Path:
    path = tmp_path / "v0.6.12-post-release-evidence.md"
    path.write_text(
        "# v0.6.12 Post-Release Evidence\n\n"
        "Release `v0.6.12` is the current public release.\n\n"
        "PyPI was not published for `v0.6.12`.\n",
        encoding="utf-8",
    )
    return path


def _make_v0613_plan(tmp_path: Path, safe: bool = True) -> Path:
    path = tmp_path / "v0.6.13-plan.md"
    if safe:
        path.write_text(
            "# v0.6.13 Planning Seed\n\n"
            "`v0.6.13` is planning only and is not released.\n\n"
            "No tag, GitHub Release, or PyPI publication has occurred.\n",
            encoding="utf-8",
        )
    else:
        path.write_text(
            "# v0.6.13 Planning Seed\n\n"
            "v0.6.13 is released and is the current public release.\n",
            encoding="utf-8",
        )
    return path


def _make_release_notes(tmp_path: Path, text: str | None = None) -> Path:
    path = tmp_path / "v0.6.12.md"
    if text is None:
        text = (
            "# Atlas Agent v0.6.12 Release Notes\n\n"
            "> **Status:** current public release\n\n"
            "## Summary\n\n"
            "v0.6.12 is a docs/checker/test release.\n\n"
            "## Non-Goals\n\n"
            "- **PyPI was not published** for `v0.6.12`.\n"
        )
    path.write_text(text, encoding="utf-8")
    return path


def _make_trust_status(tmp_path: Path, text: str | None = None) -> Path:
    path = tmp_path / "v0.6.12-status.md"
    if text is None:
        text = (
            "# v0.6.12 Trust and Release Status\n\n"
            "- Release: `v0.6.12` (current public release)\n"
            "- PyPI: not published for `v0.6.12`\n\n"
            "## Safety Defaults\n\n"
            "- Live trading is disabled by default.\n"
        )
    path.write_text(text, encoding="utf-8")
    return path


def _make_release_metadata(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "release-metadata.json"
    data = {
        "schema_version": 1,
        "source_version": "0.6.12",
        "current_public_release": "v0.6.12",
        "next_planned_release": "v0.6.13",
        "pypi_published": False,
        "releases": [],
    }
    data.update(overrides)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestPassOnRealRepo:
    def test_passes_on_real_repo(self) -> None:
        result = _run_script()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS" in result.stdout

    def test_json_passes_on_real_repo(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["artifact_type"] == "v0612_post_release_evidence_report"
        assert data["schema_version"] == 1
        assert "checks" in data
        assert "errors" in data
        assert "warnings" in data
        assert "evidence" in data

    def test_json_has_expected_evidence_values(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        evidence = data["evidence"]
        assert evidence["release"] == "v0.6.12"
        assert evidence["source_version"] == "0.6.12"
        assert evidence["tag"] == "v0.6.12"
        assert evidence["github_release"] == "v0.6.12"
        assert evidence["current_public_release"] == "v0.6.12"
        assert evidence["next_planned_release"] == "v0.6.13"
        assert evidence["pypi_published"] is False
        assert evidence["live_trading_enabled"] is False
        assert evidence["provider_execution_enabled"] is False
        assert evidence["broker_execution_enabled"] is False


class TestDeterminism:
    def test_json_output_is_deterministic(self) -> None:
        result1 = _run_script("--json")
        result2 = _run_script("--json")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout

    def test_json_keys_are_sorted(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert list(data.keys()) == sorted(data.keys())


class TestFailures:
    def test_missing_evidence_json_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.EVIDENCE_JSON
        try:
            mod.EVIDENCE_JSON = tmp_path / "missing.json"
            code, result = mod.run_check()
            assert code == 1
            assert any("Evidence JSON missing" in e for e in result["errors"])
        finally:
            mod.EVIDENCE_JSON = original

    def test_wrong_release_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.EVIDENCE_JSON
        try:
            mod.EVIDENCE_JSON = _make_evidence_json(tmp_path, release="v0.6.11")
            code, result = mod.run_check()
            assert code == 1
            assert any("release'" in e and "v0.6.12" in e for e in result["errors"])
        finally:
            mod.EVIDENCE_JSON = original

    def test_wrong_source_version_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.EVIDENCE_JSON
        try:
            mod.EVIDENCE_JSON = _make_evidence_json(tmp_path, source_version="0.6.11")
            code, result = mod.run_check()
            assert code == 1
            assert any("source_version'" in e for e in result["errors"])
        finally:
            mod.EVIDENCE_JSON = original

    def test_bad_main_commit_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.EVIDENCE_JSON
        try:
            mod.EVIDENCE_JSON = _make_evidence_json(tmp_path, main_commit="deadbeef")
            code, result = mod.run_check()
            assert code == 1
            assert any("main_commit" in e for e in result["errors"])
        finally:
            mod.EVIDENCE_JSON = original

    def test_missing_evidence_md_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_md = mod.EVIDENCE_MD
        original_json = mod.EVIDENCE_JSON
        try:
            mod.EVIDENCE_MD = tmp_path / "missing.md"
            mod.EVIDENCE_JSON = _make_evidence_json(tmp_path)
            code, result = mod.run_check()
            assert code == 1
            assert any("Post-release evidence markdown missing" in e for e in result["errors"])
        finally:
            mod.EVIDENCE_MD = original_md
            mod.EVIDENCE_JSON = original_json

    def test_v0613_plan_release_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.V0613_PLAN
        try:
            mod.V0613_PLAN = _make_v0613_plan(tmp_path, safe=False)
            code, result = mod.run_check()
            assert code == 1
            assert any("v0.6.13 plan has positive release claim" in e for e in result["errors"])
        finally:
            mod.V0613_PLAN = original

    def test_forbidden_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_json = mod.EVIDENCE_JSON
        original_md = mod.EVIDENCE_MD
        original_scanned = mod.SCANNED_DOC_PATHS
        try:
            mod.EVIDENCE_JSON = _make_evidence_json(tmp_path)
            mod.EVIDENCE_MD = tmp_path / "v0.6.12-post-release-evidence.md"
            mod.EVIDENCE_MD.write_text(
                "This release provides guaranteed profit.", encoding="utf-8"
            )
            mod.SCANNED_DOC_PATHS = [
                mod.EVIDENCE_MD,
                mod.EVIDENCE_JSON,
                mod.V0613_PLAN,
                mod.RELEASE_NOTES,
                mod.TRUST_STATUS,
            ]
            code, result = mod.run_check()
            assert code == 1
            assert any("guaranteed profit" in e.lower() for e in result["errors"])
        finally:
            mod.EVIDENCE_JSON = original_json
            mod.EVIDENCE_MD = original_md
            mod.SCANNED_DOC_PATHS = original_scanned

    def test_pypi_publish_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_json = mod.EVIDENCE_JSON
        original_md = mod.EVIDENCE_MD
        original_scanned = mod.SCANNED_DOC_PATHS
        try:
            mod.EVIDENCE_JSON = _make_evidence_json(tmp_path)
            mod.EVIDENCE_MD = tmp_path / "v0.6.12-post-release-evidence.md"
            mod.EVIDENCE_MD.write_text(
                "PyPI published for v0.6.12.", encoding="utf-8"
            )
            mod.SCANNED_DOC_PATHS = [
                mod.EVIDENCE_MD,
                mod.EVIDENCE_JSON,
                mod.V0613_PLAN,
                mod.RELEASE_NOTES,
                mod.TRUST_STATUS,
            ]
            code, result = mod.run_check()
            assert code == 1
            assert any("pypi published" in e.lower() for e in result["errors"])
        finally:
            mod.EVIDENCE_JSON = original_json
            mod.EVIDENCE_MD = original_md
            mod.SCANNED_DOC_PATHS = original_scanned

    def test_wrong_source_version_in_pyproject_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_pyproject = mod.PYPROJECT
        try:
            fake_pyproject = tmp_path / "pyproject.toml"
            fake_pyproject.write_text('version = "0.6.11"\n', encoding="utf-8")
            mod.PYPROJECT = fake_pyproject
            code, result = mod.run_check()
            assert code == 1
            assert any("0.6.12" in e and "pyproject.toml" in e.lower() for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject

    def test_wrong_release_metadata_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = _make_release_metadata(
                tmp_path, current_public_release="v0.6.11"
            )
            code, result = mod.run_check()
            assert code == 1
            assert any("current_public_release mismatch" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original

    def test_release_metadata_next_planned_wrong_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = _make_release_metadata(
                tmp_path, next_planned_release="v0.6.14"
            )
            code, result = mod.run_check()
            assert code == 1
            assert any("next_planned_release mismatch" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original

    def test_pypi_published_in_metadata_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = _make_release_metadata(tmp_path, pypi_published=True)
            code, result = mod.run_check()
            assert code == 1
            assert any("pypi_published must be false" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original
