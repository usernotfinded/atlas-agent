"""Tests for the historical v0.6.15 GitHub-only post-release hygiene gate.

The checker is archived under scripts/historical_release_checkers/ because it
validates the v0.6.15 post-cutover posture. It remains syntactically correct and
is exercised against temporary fixtures, not the current repo.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "historical_release_checkers" / "check_v0615_post_release_hygiene.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_v0615_post_release_hygiene", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_v0615_post_release_hygiene"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _copy_v0615_repo(tmp_path: Path) -> Path:
    mod = _load_script_module()
    repo = tmp_path / "repo"

    # Required release records and planning documents.
    for rel in mod.REQUIRED_FILES:
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        source = ROOT / rel
        if source.exists():
            shutil.copy2(source, target)
        else:
            target.write_text("", encoding="utf-8")

    # Metadata rewritten to the v0.6.15 post-cutover posture.
    metadata_path = repo / mod.METADATA
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((ROOT / mod.METADATA).read_text(encoding="utf-8"))
    metadata["source_version"] = "0.6.15"
    metadata["current_public_release"] = "v0.6.15"
    metadata["next_planned_release"] = "v0.6.16"
    for release in metadata.get("releases", []):
        tag = release.get("tag")
        if tag == "v0.6.15":
            release["status"] = "current_public"
        elif tag in ("v0.6.14", "v0.6.16", "v0.6.17"):
            release["status"] = "historical"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Source version files.
    pyproject_path = repo / "pyproject.toml"
    pyproject_path.parent.mkdir(parents=True, exist_ok=True)
    pyproject_path.write_text('version = "0.6.15"\n', encoding="utf-8")
    init_path = repo / "src" / "atlas_agent" / "__init__.py"
    init_path.parent.mkdir(parents=True, exist_ok=True)
    init_path.write_text('__version__ = "0.6.15"\n', encoding="utf-8")

    # Public-facing state docs are stubbed so the fixture is self-contained and
    # does not depend on the current repo's (post-v0.6.16) wording.
    for rel in mod.PUBLIC_STATE_DOCS:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel == "README.md":
            path.write_text(
                "# Atlas Agent\n\n"
                "Current Status (v0.6.15)\n\n"
                "`v0.6.15` is the current public GitHub release.\n\n"
                "`v0.6.16` is the next planning line.\n\n"
                "package/source version is `0.6.15`\n",
                encoding="utf-8",
            )
        else:
            path.write_text(
                f"# {rel}\n\n"
                "v0.6.15 is the current public release. "
                "v0.6.16 is the next planning line.\n",
                encoding="utf-8",
            )

    # Gate integration stubs.
    for rel in mod.GATE_FILES:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "scripts/check_v0615_post_release_hygiene.py\n"
        if rel != "scripts/release_check.sh":
            content += "tests/test_v0615_post_release_hygiene.py\n"
        path.write_text(content, encoding="utf-8")

    return repo


def _mutate_json(repo: Path, rel: str, mutator) -> None:
    path = repo / rel
    data = json.loads(path.read_text(encoding="utf-8"))
    mutator(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_script_exists() -> None:
    assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


def test_checker_fails_on_current_repo() -> None:
    """The historical checker correctly fails on the post-v0.6.17 repo."""
    result = _run_script()
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL" in result.stdout


def test_checker_passes_on_v0615_fixture(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    result = mod.check(repo)
    assert result["valid"] is True, result["errors"]


def test_checker_json_parses(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--root", str(repo)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["valid"] is True
    assert data["current_public_release"] == "v0.6.15"
    assert data["source_version"] == "0.6.15"
    assert data["next_planned_release"] == "v0.6.16"
    assert data["pypi_published"] is False


def test_fails_on_wrong_source_version(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    path = repo / "pyproject.toml"
    path.write_text(path.read_text(encoding="utf-8").replace('version = "0.6.15"', 'version = "0.6.16"'), encoding="utf-8")
    mod = _load_script_module()
    result = mod.check(repo)
    assert result["valid"] is False
    assert any("project.version" in error for error in result["errors"])


def test_fails_if_metadata_marks_pypi_published(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    _mutate_json(repo, mod.METADATA, lambda data: data.update({"pypi_published": True}))
    result = mod.check(repo)
    assert any("pypi_published" in error for error in result["errors"])


def test_fails_if_evidence_marks_pypi_published(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    _mutate_json(repo, mod.EVIDENCE_JSON, lambda data: data.update({"pypi_published": True}))
    result = mod.check(repo)
    assert any("post-release evidence pypi_published" in error for error in result["errors"])


def test_fails_if_previous_release_is_not_historical(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()

    def mutate(data: dict) -> None:
        for release in data["releases"]:
            if release.get("tag") == "v0.6.14":
                release["status"] = "current_public"

    _mutate_json(repo, mod.METADATA, mutate)
    result = mod.check(repo)
    assert any("v0.6.14 release record must be historical" in error for error in result["errors"])


def test_fails_if_required_release_record_is_missing(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    (repo / mod.TRUST_STATUS).unlink()
    result = mod.check(repo)
    assert any(mod.TRUST_STATUS in error for error in result["errors"])


def test_fails_if_pre_cutover_doc_is_not_historical(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    path = repo / "docs/releases/v0.6.15-plan.md"
    path.write_text("# v0.6.15 Release Plan\n", encoding="utf-8")
    result = mod.check(repo)
    assert any("not marked historical" in error for error in result["errors"])


def test_fails_on_stale_public_release_posture(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    path = repo / "README.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nCurrent public release is v0.6.14.\n", encoding="utf-8")
    result = mod.check(repo)
    assert any("stale release posture" in error for error in result["errors"])


def test_fails_on_unsafe_claim(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    path = repo / "README.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nGuaranteed profit.\n", encoding="utf-8")
    result = mod.check(repo)
    assert any("unsafe or publication claim" in error for error in result["errors"])


def test_fails_if_gate_integration_is_missing(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    path = repo / "scripts/dev_check.sh"
    path.write_text(path.read_text(encoding="utf-8").replace("scripts/check_v0615_post_release_hygiene.py", "scripts/removed.py"), encoding="utf-8")
    result = mod.check(repo)
    assert any("dev_check.sh missing" in error for error in result["errors"])


def test_checker_does_not_mutate_files(tmp_path: Path) -> None:
    repo = _copy_v0615_repo(tmp_path)
    mod = _load_script_module()
    before = _digest(repo)
    mod.check(repo)
    assert _digest(repo) == before
