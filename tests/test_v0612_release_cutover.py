"""Tests for v0.6.12 public release cutover checker.

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
SCRIPT = ROOT / "scripts" / "check_v0612_release_cutover.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v0612_release_cutover", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0612_release_cutover"] = mod
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


def _make_owner_approval(tmp_path: Path, public_approved: bool = True) -> Path:
    path = tmp_path / "v0.6.12-owner-approval.md"
    approval = "yes" if public_approved else "no"
    text = f"""# Owner Approval

## Public cutover approval

Cutover approval may only be granted when:

- [x] Release-prep artifacts are present and valid.

## Approval record

| Gate | Approved | Approver | Date | Commit / basis |
|---|---|---|---|---|
| Release-prep | yes | Owner | 2026-06-17 | CAND-018 |
| Public cutover | {approval} | Owner | 2026-06-17 | basis |

### Approved public-cutover actions

The owner approval authorizes **only**:

- Creating the annotated Git tag `v0.6.12`.
- Pushing the tag `v0.6.12` to `origin`.
- Creating the GitHub Release `v0.6.12`.

It does **not** authorize any of the following:

- Publishing to PyPI or running `twine upload`.
- Enabling live trading.
"""
    path.write_text(text, encoding="utf-8")
    return path


def _make_release_notes(tmp_path: Path) -> Path:
    path = tmp_path / "v0.6.12.md"
    path.write_text(
        "# Atlas Agent v0.6.12 Release Notes\n\n"
        "> **Status:** current public release\n\n"
        "## Summary\n\n"
        "v0.6.12 is a docs/checker/test release cutover.\n\n"
        "## Safety Boundaries\n\n"
        "- **Live trading** remains disabled by default.\n"
        "- **Provider execution** remains disabled by default.\n\n"
        "## Non-Goals\n\n"
        "- **PyPI was not published** for `v0.6.12`.\n",
        encoding="utf-8",
    )
    return path


def _make_trust_status(tmp_path: Path, public: bool = True) -> Path:
    path = tmp_path / "v0.6.12-status.md"
    status_text = "current public release" if public else "prepared, not yet tagged or released"
    path.write_text(
        f"# v0.6.12 Trust and Release Status\n\n"
        f"- Release: `v0.6.12` ({status_text})\n"
        f"- Current public release: `v0.6.12`\n"
        f"- Previous public release: `v0.6.11`\n"
        f"- GitHub release: created for `v0.6.12`\n"
        f"- Tag: created for `v0.6.12`\n"
        f"- PyPI: not published for `v0.6.12`\n\n"
        "## Safety Defaults\n\n"
        "- Live trading is disabled by default.\n"
        "- Provider execution is disabled by default.\n"
        "- Broker execution is disabled by default.\n",
        encoding="utf-8",
    )
    return path


def _make_changelog(tmp_path: Path) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text("# Changelog\n\n## [0.6.12] - 2026-06-17\n\n### Added\n- Cutover.\n", encoding="utf-8")
    return path


def _make_metadata(tmp_path: Path, current_public: str = "v0.6.12") -> Path:
    path = tmp_path / "release-metadata.json"
    data = {
        "schema_version": 1,
        "source_version": "0.6.12",
        "current_public_release": current_public,
        "next_planned_release": "v0.6.13",
        "pypi_published": False,
        "releases": [
            {
                "tag": "v0.6.12",
                "version": "0.6.12",
                "status": "current_public" if current_public == "v0.6.12" else "prepared",
                "release_notes": "docs/releases/v0.6.12.md",
                "trust_status": "docs/trust/v0.6.12-status.md",
                "github_release": current_public == "v0.6.12",
                "pypi_published": False,
            },
            {
                "tag": "v0.6.11",
                "version": "0.6.11",
                "status": "historical" if current_public == "v0.6.12" else "current_public",
                "release_notes": "docs/releases/v0.6.11.md",
                "trust_status": "docs/trust/v0.6.11-status.md",
                "github_release": True,
                "pypi_published": False,
            },
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestCutoverPass:
    def test_public_release_state_passes(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_paths = {
            "PYPROJECT": mod.PYPROJECT,
            "INIT_PY": mod.INIT_PY,
            "CHANGELOG": mod.CHANGELOG,
            "RELEASE_NOTES": mod.RELEASE_NOTES,
            "TRUST_STATUS": mod.TRUST_STATUS,
            "OWNER_APPROVAL": mod.OWNER_APPROVAL,
            "RELEASE_METADATA": mod.RELEASE_METADATA,
        }
        fake_pyproject = tmp_path / "pyproject.toml"
        fake_init = tmp_path / "__init__.py"
        fake_pyproject.write_text('version = "0.6.12"\n', encoding="utf-8")
        fake_init.write_text('__version__ = "0.6.12"\n', encoding="utf-8")
        try:
            mod.PYPROJECT = fake_pyproject
            mod.INIT_PY = fake_init
            mod.CHANGELOG = _make_changelog(tmp_path)
            mod.RELEASE_NOTES = _make_release_notes(tmp_path)
            mod.TRUST_STATUS = _make_trust_status(tmp_path, public=True)
            mod.OWNER_APPROVAL = _make_owner_approval(tmp_path, public_approved=True)
            mod.RELEASE_METADATA = _make_metadata(tmp_path, current_public="v0.6.12")
            code, result = mod.run_check()
            assert code == 0, result["errors"]
            assert result["valid"] is True
        finally:
            for name, val in original_paths.items():
                setattr(mod, name, val)

    def test_json_output_shape_on_real_repo(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_metadata = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = _make_metadata(tmp_path, current_public="v0.6.12")
            result = _run_script("--json")
            # Real repo is not public yet; expect fail but JSON shape is valid.
            data = json.loads(result.stdout)
            assert data["artifact_type"] == "v0612_release_cutover_report"
            assert "checks" in data
            assert "errors" in data
        finally:
            mod.RELEASE_METADATA = original_metadata


class TestCutoverFailures:
    def test_wrong_current_public_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_metadata = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = _make_metadata(tmp_path, current_public="v0.6.11")
            code, result = mod.run_check()
            assert code == 1
            assert any("current_public_release mismatch" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original_metadata

    def test_next_planned_not_v0613_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        path = _make_metadata(tmp_path, current_public="v0.6.12")
        text = path.read_text(encoding="utf-8").replace('"next_planned_release": "v0.6.13"', '"next_planned_release": "v0.6.14"')
        path.write_text(text, encoding="utf-8")
        original_metadata = mod.RELEASE_METADATA
        try:
            mod.RELEASE_METADATA = path
            code, result = mod.run_check()
            assert code == 1
            assert any("next_planned_release mismatch" in e for e in result["errors"])
        finally:
            mod.RELEASE_METADATA = original_metadata

    def test_trust_status_not_released_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_status = mod.TRUST_STATUS
        original_metadata = mod.RELEASE_METADATA
        try:
            mod.TRUST_STATUS = _make_trust_status(tmp_path, public=False)
            mod.RELEASE_METADATA = _make_metadata(tmp_path, current_public="v0.6.12")
            code, result = mod.run_check()
            assert code == 1
            assert any("not yet tagged" in e or "not released" in e for e in result["errors"])
        finally:
            mod.TRUST_STATUS = original_status
            mod.RELEASE_METADATA = original_metadata

    def test_pypi_publish_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_notes = mod.RELEASE_NOTES
        original_metadata = mod.RELEASE_METADATA
        try:
            notes = tmp_path / "v0.6.12.md"
            notes.write_text("# v0.6.12\n\nPyPI published for v0.6.12.\n", encoding="utf-8")
            mod.RELEASE_NOTES = notes
            mod.RELEASE_METADATA = _make_metadata(tmp_path, current_public="v0.6.12")
            code, result = mod.run_check()
            assert code == 1
            assert any("pypi published" in e.lower() for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original_notes
            mod.RELEASE_METADATA = original_metadata

    def test_forbidden_claim_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_notes = mod.RELEASE_NOTES
        original_metadata = mod.RELEASE_METADATA
        try:
            notes = tmp_path / "v0.6.12.md"
            notes.write_text("# v0.6.12\n\nThis release provides guaranteed profit.\n", encoding="utf-8")
            mod.RELEASE_NOTES = notes
            mod.RELEASE_METADATA = _make_metadata(tmp_path, current_public="v0.6.12")
            code, result = mod.run_check()
            assert code == 1
            assert any("guaranteed profit" in e.lower() for e in result["errors"])
        finally:
            mod.RELEASE_NOTES = original_notes
            mod.RELEASE_METADATA = original_metadata

    def test_owner_approval_missing_fails(self, tmp_path: Path) -> None:
        mod = _load_script_module()
        original_approval = mod.OWNER_APPROVAL
        original_metadata = mod.RELEASE_METADATA
        try:
            mod.OWNER_APPROVAL = tmp_path / "missing-owner-approval.md"
            mod.RELEASE_METADATA = _make_metadata(tmp_path, current_public="v0.6.12")
            code, result = mod.run_check()
            assert code == 1
            assert any("owner" in e.lower() for e in result["errors"])
        finally:
            mod.OWNER_APPROVAL = original_approval
            mod.RELEASE_METADATA = original_metadata


class TestCutoverOnRealRepo:
    def test_cutover_passes_on_real_repo(self) -> None:
        """Cutover checker passes on real repo after tag/GitHub Release creation."""
        result = _run_script()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS" in result.stdout

    def test_cutover_json_passes_on_real_repo(self) -> None:
        result = _run_script("--json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert data["public_tag"] == "v0.6.12"
        assert data["previous_public_tag"] == "v0.6.11"
        assert data["next_planned_tag"] == "v0.6.13"


class TestDeterminism:
    def test_json_output_is_deterministic(self) -> None:
        result1 = _run_script("--json")
        result2 = _run_script("--json")
        assert result1.returncode == result2.returncode
        assert result1.stdout == result2.stdout
