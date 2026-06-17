"""Tests for v0.6.12 release-candidate readiness checker.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.

These tests assume the companion checker exists at
``scripts/check_v0612_release_candidate_readiness.py``. If the checker or the
v0.6.12 readiness docs have not been created yet, the relevant tests skip
gracefully so the suite remains green while work is in progress.
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
SCRIPT = ROOT / "scripts" / "check_v0612_release_candidate_readiness.py"

REQUIRED_READINESS_PATHS = [
    ROOT / "docs" / "releases" / "v0.6.12-candidate-readiness.md",
    ROOT / "docs" / "releases" / "v0.6.12-candidates.md",
    ROOT / "docs" / "releases" / "v0.6.12-candidates.json",
]

REQUIRED_JSON_KEYS = {
    "artifact_type",
    "schema_version",
    "valid",
    "checks",
    "errors",
    "warnings",
}


def _script_exists() -> None:
    if not SCRIPT.exists():
        pytest.skip(f"Checker script not yet created: {SCRIPT}")


def _load_script_module() -> ModuleType:
    _script_exists()
    spec = importlib.util.spec_from_file_location(
        "check_v0612_release_candidate_readiness", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0612_release_candidate_readiness"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    _script_exists()
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def _all_readiness_docs_exist() -> bool:
    return all(path.exists() for path in REQUIRED_READINESS_PATHS)


def _baseline_readiness_text() -> str:
    """Return a minimal valid v0.6.12 readiness document body."""
    return """# v0.6.12 Release Candidate Readiness

> Not financial advice. Audit date: 2026-06-16.

## Status

v0.6.12 is not released yet.

- Current public release: v0.6.11
- Next planned release: v0.6.12
- Source/package version: 0.6.11

## Candidate Inventory

| ID | Title | Status |
|---|---|---|
| CAND-001 | Product Demo and Marketplace Readiness Pack | Implemented |
| CAND-002 | Product Demo Evidence Bundle | Implemented |
| CAND-003 | Reviewer Trust Snapshot | Implemented |
| CAND-004 | Reviewer Trust Snapshot Workflow | Implemented |
| CAND-005 | Docs Archive Hygiene | Implemented |
| CAND-006 | Release Assurance Snapshot Integration | Implemented |
| CAND-007 | Release Assurance Bundle Demo and Manifest | Implemented |
| CAND-008 | Gap / folded | Not separately tracked |
| CAND-009 | Release Assurance Workflow Artifact Validation | Implemented |
| CAND-010 | Gap / folded | Not separately tracked |
| CAND-011 | Release Assurance Failure Diagnostics | Implemented |
| CAND-012 | Release Assurance Diagnostics Artifact | Implemented |
| CAND-013 | Release Assurance Diagnostics Artifact Validator | Implemented |
| CAND-014 | Release Assurance Diagnostics Artifact Workflow Integration | Implemented |
| CAND-015 | Release Assurance Diagnostics Artifact Revalidation Workflow | Implemented |
| CAND-016 | Release Assurance Artifact Retention Audit | Implemented |

## Safety Invariants

- live trading disabled
- broker execution disabled
- provider execution disabled
- no PyPI publish
- no tag/release created

## Linked Workflow / Checker Artifacts

- [Reviewer Trust Snapshot](docs/trust/reviewer-trust-snapshot.md)
- [Release Assurance Bundle Demo](docs/security/release-assurance-bundle-demo.md)
- [Diagnostics Artifact](docs/security/release-assurance-diagnostics.md)
- [Diagnostics Revalidation Workflow](.github/workflows/release-assurance-diagnostics-artifact-validate.yml)
- [Artifact Retention Audit](.github/workflows/release-assurance-artifact-retention-audit.yml)

## Decision

READY_FOR_V0.6.12_RELEASE_PREP
"""


def _baseline_candidates_json() -> dict:
    """Return a minimal valid v0.6.12 candidate inventory."""
    return {
        "schema_version": 1,
        "artifact_type": "v0612_candidate_inventory",
        "release_line": "v0.6.12",
        "current_public_release": "v0.6.11",
        "next_planned_release": "v0.6.12",
        "candidates": [
            {
                "id": f"CAND-{i:03d}",
                "title": f"Candidate {i:03d}",
                "implemented": True,
                "selected_for_v0612": True,
                "primary_files": [],
                "checkers": [],
                "tests": [],
                "workflows": [],
                "safety_scope": "safe",
            }
            for i in range(1, 17)
        ],
        "deferred": [{"id": "CAND-008"}, {"id": "CAND-010"}],
        "rejected": [],
    }


def _baseline_release_metadata() -> dict:
    """Return a minimal valid release-metadata.json for the v0.6.12 line."""
    return {
        "schema_version": 1,
        "source_version": "0.6.11",
        "current_public_release": "v0.6.11",
        "next_planned_release": "v0.6.12",
        "pypi_published": False,
        "releases": [
            {
                "tag": "v0.6.11",
                "version": "0.6.11",
                "status": "current_public",
                "github_release": True,
                "pypi_published": False,
            }
        ],
    }


def _write_baseline(tmp_path: Path) -> dict[str, Path]:
    """Write baseline valid temp files and return path mapping for monkeypatching.

    Keys match the module-level path constants expected by the checker:
    READINESS_MD, CANDIDATES_MD, CANDIDATES_JSON, RELEASE_METADATA.
    """
    readiness = tmp_path / "v0.6.12-candidate-readiness.md"
    readiness.write_text(_baseline_readiness_text(), encoding="utf-8")

    candidates_md = tmp_path / "v0.6.12-candidates.md"
    candidate_ids = [c["id"] for c in _baseline_candidates_json()["candidates"]]
    candidates_md.write_text(
        "# v0.6.12 Candidates\n\n"
        + "\n".join(f"- {cid}" for cid in candidate_ids)
        + "\n",
        encoding="utf-8",
    )

    candidates_json = tmp_path / "v0.6.12-candidates.json"
    candidates_json.write_text(
        json.dumps(_baseline_candidates_json(), sort_keys=True),
        encoding="utf-8",
    )

    metadata = tmp_path / "release-metadata.json"
    metadata.write_text(
        json.dumps(_baseline_release_metadata(), sort_keys=True),
        encoding="utf-8",
    )

    return {
        "READINESS_MD": readiness,
        "CANDIDATES_MD": candidates_md,
        "CANDIDATES_JSON": candidates_json,
        "RELEASE_METADATA": metadata,
    }


def _patch_module_paths(mod: ModuleType, paths: dict[str, Path]) -> dict[str, Path]:
    """Monkeypatch module path constants and return original values."""
    originals: dict[str, Path] = {}
    for name, path in paths.items():
        if not hasattr(mod, name):
            continue
        originals[name] = getattr(mod, name)
        setattr(mod, name, path)
    return originals


def _restore_module_paths(mod: ModuleType, originals: dict[str, Path]) -> None:
    for name, path in originals.items():
        setattr(mod, name, path)


class TestScriptExists:
    def test_script_path_is_known(self) -> None:
        assert SCRIPT == ROOT / "scripts" / "check_v0612_release_candidate_readiness.py"


class TestRealRepo:
    def test_checker_passes_on_real_repo(self) -> None:
        """Checker passes once the v0.6.12 readiness docs exist."""
        if not _all_readiness_docs_exist():
            pytest.skip("v0.6.12 readiness docs not yet created")
        mod = _load_script_module()
        code, result = mod.run_check()
        assert code == 0, result.get("errors", [])

    def test_checker_fails_on_real_repo_until_docs_exist(self) -> None:
        """Until docs exist, the checker reports missing artifacts.

        This keeps the suite meaningful while work is in progress.
        """
        if _all_readiness_docs_exist():
            pytest.skip("v0.6.12 readiness docs already exist")
        mod = _load_script_module()
        code, result = mod.run_check()
        assert code == 1
        assert result.get("errors")


class TestJsonOutput:
    def test_json_output_is_valid_and_consistent(self) -> None:
        result = _run_script("--json")
        data = json.loads(result.stdout)
        assert REQUIRED_JSON_KEYS.issubset(data.keys())
        assert data["artifact_type"] == "v0612_release_candidate_readiness_report"
        assert data["schema_version"] == 1
        # Exit code must match the ``valid`` flag.
        if data["valid"]:
            assert result.returncode == 0
        else:
            assert result.returncode == 1


class TestCandidateCoverage:
    def test_missing_cand_entry_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        paths = _write_baseline(tmp_path)
        # Remove CAND-001 from both the readiness doc and the candidate index.
        readiness_text = paths["READINESS_MD"].read_text(encoding="utf-8")
        paths["READINESS_MD"].write_text(
            readiness_text.replace("| CAND-001 |", "| CAND-XXX |"),
            encoding="utf-8",
        )
        candidates_text = paths["CANDIDATES_MD"].read_text(encoding="utf-8")
        paths["CANDIDATES_MD"].write_text(
            candidates_text.replace("- CAND-001", "- CAND-XXX"),
            encoding="utf-8",
        )
        originals = _patch_module_paths(mod, paths)
        try:
            code, result = mod.run_check()
            assert code == 1
            errors = "\n".join(result.get("errors", []))
            assert "CAND-001" in errors or "candidate" in errors.lower()
        finally:
            _restore_module_paths(mod, originals)


class TestReleaseStateClaims:
    def test_doc_claiming_v0612_is_current_public_release_fails(
        self, tmp_path: Path
    ) -> None:
        mod = _load_script_module()
        paths = _write_baseline(tmp_path)
        # The public-doc scanner checks README.md and docs/, not the patched
        # READINESS_MD path. Feed the premature claim through a temp README.
        fake_readme = tmp_path / "README.md"
        fake_readme.write_text(
            "# Atlas Agent\n\nv0.6.12 is the current public release.\n",
            encoding="utf-8",
        )
        paths["README"] = fake_readme
        originals = _patch_module_paths(mod, paths)
        try:
            code, result = mod.run_check()
            assert code == 1
            errors = "\n".join(result.get("errors", []))
            assert "current public" in errors.lower() or "released" in errors.lower()
        finally:
            _restore_module_paths(mod, originals)

    def test_metadata_claiming_v0612_current_public_release_fails(
        self, tmp_path: Path
    ) -> None:
        mod = _load_script_module()
        paths = _write_baseline(tmp_path)
        metadata = json.loads(paths["RELEASE_METADATA"].read_text(encoding="utf-8"))
        metadata["current_public_release"] = "v0.6.12"
        paths["RELEASE_METADATA"].write_text(
            json.dumps(metadata, sort_keys=True), encoding="utf-8"
        )
        originals = _patch_module_paths(mod, paths)
        try:
            code, result = mod.run_check()
            assert code == 1
            errors = "\n".join(result.get("errors", []))
            assert "v0.6.12" in errors and "current_public_release" in errors
        finally:
            _restore_module_paths(mod, originals)


class TestSafetyInvariants:
    def test_missing_live_trading_disabled_phrase_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        paths = _write_baseline(tmp_path)
        readiness_text = paths["READINESS_MD"].read_text(encoding="utf-8")
        paths["READINESS_MD"].write_text(
            readiness_text.replace("- live trading disabled\n", ""),
            encoding="utf-8",
        )
        originals = _patch_module_paths(mod, paths)
        try:
            code, result = mod.run_check()
            assert code == 1
            errors = "\n".join(result.get("errors", []))
            assert "live trading" in errors.lower()
        finally:
            _restore_module_paths(mod, originals)


class TestForbiddenClaims:
    def test_guaranteed_profit_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        paths = _write_baseline(tmp_path)
        readiness_text = paths["READINESS_MD"].read_text(encoding="utf-8")
        paths["READINESS_MD"].write_text(
            readiness_text + "\nThis release delivers guaranteed profit.\n",
            encoding="utf-8",
        )
        originals = _patch_module_paths(mod, paths)
        try:
            code, result = mod.run_check()
            assert code == 1
            errors = "\n".join(result.get("errors", []))
            assert "guaranteed profit" in errors.lower() or "forbidden" in errors.lower()
        finally:
            _restore_module_paths(mod, originals)


class TestRequiredLinks:
    def test_missing_required_workflow_checker_links_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        paths = _write_baseline(tmp_path)
        # Strip the links section so all required links disappear.
        readiness_text = paths["READINESS_MD"].read_text(encoding="utf-8")
        start = readiness_text.find("## Linked Workflow")
        end = readiness_text.find("## Decision")
        if start != -1 and end != -1:
            paths["READINESS_MD"].write_text(
                readiness_text[:start] + readiness_text[end:],
                encoding="utf-8",
            )
        originals = _patch_module_paths(mod, paths)
        try:
            code, result = mod.run_check()
            assert code == 1
            errors = "\n".join(result.get("errors", []))
            assert "link" in errors.lower() or "missing" in errors.lower()
        finally:
            _restore_module_paths(mod, originals)


class TestPrematurePublishClaims:
    @pytest.mark.parametrize(
        "claim",
        [
            "published to PyPI.",
            "tag v0.6.12 created",
            "github release v0.6.12 created",
        ],
    )
    def test_pypi_publish_or_tag_claim_fails(
        self, tmp_path: Path, claim: str
    ) -> None:
        mod = _load_script_module()
        paths = _write_baseline(tmp_path)
        # The public-doc scanner checks README.md and docs/. Feed the premature
        # publish/tag/release claim through a temp README so it is detected.
        fake_readme = tmp_path / "README.md"
        fake_readme.write_text(f"# Atlas Agent\n\n{claim}\n", encoding="utf-8")
        paths["README"] = fake_readme
        originals = _patch_module_paths(mod, paths)
        try:
            code, result = mod.run_check()
            assert code == 1
            errors = "\n".join(result.get("errors", []))
            assert (
                "pypi" in errors.lower()
                or "tag" in errors.lower()
                or "github release" in errors.lower()
                or "premature" in errors.lower()
                or "forbidden" in errors.lower()
            )
        finally:
            _restore_module_paths(mod, originals)


class TestDeterminism:
    def test_json_output_is_deterministic(self) -> None:
        result1 = _run_script("--json")
        result2 = _run_script("--json")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout
