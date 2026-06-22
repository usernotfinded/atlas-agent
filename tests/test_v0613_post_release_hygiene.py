"""Tests for v0.6.13 post-release hygiene checker.

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
SCRIPT = ROOT / "scripts" / "check_v0613_post_release_hygiene.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v0613_post_release_hygiene", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0613_post_release_hygiene"] = mod
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


def _make_release_metadata(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "release-metadata.json"
    data = {
        "schema_version": 1,
        "source_version": "0.6.13",
        "current_public_release": "v0.6.13",
        "next_planned_release": "v0.6.14",
        "pypi_published": False,
        "releases": [],
    }
    data.update(overrides)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _make_evidence_json(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "v0.6.13-post-release-evidence.json"
    data = {
        "schema_version": 1,
        "release": "v0.6.13",
        "source_version": "0.6.13",
        "main_commit": "c6f4ddc572902bbc04d8f8b4b262b626999a7abd",
        "tag": "v0.6.13",
        "github_release": "v0.6.13",
        "push_ci_run_id": "27696853914",
        "current_public_release": "v0.6.13",
        "next_planned_release": "v0.6.14",
        "pypi_published": False,
        "release_notes_path": "docs/releases/v0.6.13.md",
        "trust_status_path": "docs/trust/v0.6.13-status.md",
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


def _make_selection_doc(tmp_path: Path, safe: bool = True) -> Path:
    path = tmp_path / "v0.6.14-candidate-selection.md"
    if safe:
        path.write_text(
            "# v0.6.14 Candidate Selection\n\n"
            "Status: planning only. `v0.6.14` is not released.\n\n"
            "Current public release: `v0.6.13`.\n\n"
            "PyPI was not published.\n",
            encoding="utf-8",
        )
    else:
        path.write_text(
            "# v0.6.14 Candidate Selection\n\n"
            "`v0.6.14` is released and is the current public release.\n",
            encoding="utf-8",
        )
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
        assert data["artifact_type"] == "v0613_post_release_hygiene_report"
        assert data["schema_version"] == 1
        assert data["expected_current_public_release"] == "v0.6.13"
        assert data["expected_source_version"] == "0.6.13"
        assert data["next_planned_release"] == "v0.6.14"
        assert "checks" in data
        assert "errors" in data
        assert "warnings" in data


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
    def test_wrong_current_public_release_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = _make_release_metadata(
                tmp_path, current_public_release="v0.6.12"
            )
            code, result = mod.run_check()
            assert code == 1
            assert any("current_public_release mismatch" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original

    def test_wrong_next_planned_release_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = _make_release_metadata(
                tmp_path, next_planned_release="v0.6.15"
            )
            code, result = mod.run_check()
            assert code == 1
            assert any("next_planned_release mismatch" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original

    def test_source_version_bumped_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_pyproject = mod.PYPROJECT
        original_init = mod.INIT_PY
        try:
            fake_pyproject = tmp_path / "pyproject.toml"
            fake_pyproject.write_text('version = "0.6.15"\n', encoding="utf-8")
            fake_init = tmp_path / "__init__.py"
            fake_init.write_text('__version__ = "0.6.15"\n', encoding="utf-8")
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            code, result = mod.run_check()
            assert code == 1
            assert any("0.6.14" in e and "pyproject.toml" in e.lower() for e in result["errors"])
            assert any("0.6.14" in e and "__init__.py" in e.lower() for e in result["errors"])
        finally:
            mod.PYPROJECT = original_pyproject
            mod.INIT_PY = original_init

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

    def test_missing_candidate_selection_doc_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.V0613_SELECTION
        try:
            mod.V0613_SELECTION = tmp_path / "missing.md"
            code, result = mod.run_check()
            assert code == 1
            assert any("v0.6.14 candidate-selection doc" in e for e in result["errors"])
        finally:
            mod.V0613_SELECTION = original

    def test_v0614_release_claim_is_allowed_after_successor_cutover(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_readme = mod.README
        try:
            fake_readme = tmp_path / "README.md"
            fake_readme.write_text(
                "# README\n\nv0.6.14 is released and is the current public release.\n",
                encoding="utf-8",
            )
            mod.README = fake_readme
            code, result = mod.run_check()
            assert code == 0
            assert result["errors"] == []
        finally:
            mod.README = original_readme

    def test_stale_current_public_v0612_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_readme = mod.README
        try:
            fake_readme = tmp_path / "README.md"
            fake_readme.write_text(
                "# README\n\nThe current public release is v0.6.12.\n",
                encoding="utf-8",
            )
            mod.README = fake_readme
            code, result = mod.run_check()
            assert code == 1
            assert any("Stale current-public v0.6.12" in e for e in result["errors"])
        finally:
            mod.README = original_readme

    def test_pypi_publish_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_readme = mod.README
        try:
            fake_readme = tmp_path / "README.md"
            fake_readme.write_text(
                "# README\n\nPyPI published for v0.6.13.\n",
                encoding="utf-8",
            )
            mod.README = fake_readme
            code, result = mod.run_check()
            assert code == 1
            assert any("pypi published" in e.lower() for e in result["errors"])
        finally:
            mod.README = original_readme

    def test_forbidden_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_readme = mod.README
        try:
            fake_readme = tmp_path / "README.md"
            fake_readme.write_text(
                "# README\n\nThis software provides guaranteed profit.\n",
                encoding="utf-8",
            )
            mod.README = fake_readme
            code, result = mod.run_check()
            assert code == 1
            assert any("guaranteed profit" in e.lower() for e in result["errors"])
        finally:
            mod.README = original_readme

    def test_historical_doc_not_marked_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original = mod.EXPECTED_HISTORICAL_MARKED_DOCS
        try:
            fake_historical = tmp_path / "v0.6.13-candidate-readiness.md"
            fake_historical.write_text(
                "# v0.6.13 Candidate Readiness\n\nThis doc is still active.\n",
                encoding="utf-8",
            )
            mod.EXPECTED_HISTORICAL_MARKED_DOCS = [fake_historical]
            code, result = mod.run_check()
            assert code == 1
            assert any("not marked" in e and "historical" in e for e in result["errors"])
        finally:
            mod.EXPECTED_HISTORICAL_MARKED_DOCS = original
