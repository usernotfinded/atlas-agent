"""Tests for the local v0.6.15 GitHub-only post-release hygiene gate."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts import check_v0615_post_release_hygiene as checker


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_v0615_post_release_hygiene.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _copy_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    files = set(checker.REQUIRED_FILES + checker.PUBLIC_STATE_DOCS + checker.GATE_FILES)
    files.update({checker.METADATA, "pyproject.toml", "src/atlas_agent/__init__.py"})
    for rel in sorted(files):
        source = ROOT / rel
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
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


def test_checker_passes_on_current_repo() -> None:
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_checker_json_parses() -> None:
    result = _run("--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["valid"] is True
    assert data["current_public_release"] == "v0.6.15"
    assert data["source_version"] == "0.6.15"
    assert data["next_planned_release"] == "v0.6.16"
    assert data["pypi_published"] is False


def test_fails_on_wrong_source_version(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    path = repo / "pyproject.toml"
    path.write_text(path.read_text(encoding="utf-8").replace('version = "0.6.15"', 'version = "0.6.16"'), encoding="utf-8")
    result = checker.check(repo)
    assert result["valid"] is False
    assert any("project.version" in error for error in result["errors"])


def test_fails_if_metadata_marks_pypi_published(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    _mutate_json(repo, checker.METADATA, lambda data: data.update({"pypi_published": True}))
    result = checker.check(repo)
    assert any("pypi_published" in error for error in result["errors"])


def test_fails_if_evidence_marks_pypi_published(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    _mutate_json(repo, checker.EVIDENCE_JSON, lambda data: data.update({"pypi_published": True}))
    result = checker.check(repo)
    assert any("post-release evidence pypi_published" in error for error in result["errors"])


def test_fails_if_previous_release_is_not_historical(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)

    def mutate(data: dict) -> None:
        for release in data["releases"]:
            if release.get("tag") == "v0.6.14":
                release["status"] = "current_public"

    _mutate_json(repo, checker.METADATA, mutate)
    result = checker.check(repo)
    assert any("v0.6.14 release record must be historical" in error for error in result["errors"])


def test_fails_if_required_release_record_is_missing(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    (repo / checker.TRUST_STATUS).unlink()
    result = checker.check(repo)
    assert any(checker.TRUST_STATUS in error for error in result["errors"])


def test_fails_if_pre_cutover_doc_is_not_historical(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    path = repo / "docs/releases/v0.6.15-plan.md"
    path.write_text("# v0.6.15 Release Plan\n", encoding="utf-8")
    result = checker.check(repo)
    assert any("not marked historical" in error for error in result["errors"])


def test_fails_on_stale_public_release_posture(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    path = repo / "README.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nCurrent public release is v0.6.14.\n", encoding="utf-8")
    result = checker.check(repo)
    assert any("stale release posture" in error for error in result["errors"])


def test_fails_on_unsafe_claim(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    path = repo / "README.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nGuaranteed profit.\n", encoding="utf-8")
    result = checker.check(repo)
    assert any("unsafe or publication claim" in error for error in result["errors"])


def test_fails_if_gate_integration_is_missing(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    path = repo / "scripts/dev_check.sh"
    path.write_text(path.read_text(encoding="utf-8").replace("scripts/check_v0615_post_release_hygiene.py", "scripts/removed.py"), encoding="utf-8")
    result = checker.check(repo)
    assert any("dev_check.sh missing" in error for error in result["errors"])


def test_checker_does_not_mutate_files(tmp_path: Path) -> None:
    repo = _copy_repo(tmp_path)
    before = _digest(repo)
    checker.check(repo)
    assert _digest(repo) == before
