# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_v0615_final_readiness_audit.py
# PURPOSE: Verifies v0615 final readiness audit behavior and regression
#         expectations.
# DEPS:    hashlib, json, shutil, subprocess, sys, pathlib, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.check_v0615_final_readiness_audit import check


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_v0615_final_readiness_audit.py"
JSON_FILE = ROOT / "docs" / "releases" / "v0.6.15-final-readiness-audit.json"
MD_FILE = ROOT / "docs" / "releases" / "v0.6.15-final-readiness-audit.md"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def _copy_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "releases").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "tests").mkdir()
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "src" / "atlas_agent").mkdir(parents=True)

    for rel in [
        "docs/releases/v0.6.15-final-readiness-audit.md",
        "docs/releases/v0.6.15-final-readiness-audit.json",
        "docs/releases/release-metadata.json",
        "pyproject.toml",
        "src/atlas_agent/__init__.py",
        "scripts/dev_check.sh",
        "scripts/ci_check.sh",
        "scripts/release_check.sh",
        ".github/workflows/ci.yml",
    ]:
        src = ROOT / rel
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    data = json.loads((repo / JSON_FILE.relative_to(ROOT)).read_text(encoding="utf-8"))
    for candidate in data["candidates"]:
        for key in ["docs", "checkers", "tests", "demos"]:
            for rel in candidate.get(key, []):
                if rel == "not_applicable":
                    continue
                path = repo / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_text(f"placeholder for {rel}\n", encoding="utf-8")

    return repo


def _run_temp(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(repo)],
        capture_output=True,
        text=True,
    )


def _mutate_json(repo: Path, mutator) -> None:
    path = repo / JSON_FILE.relative_to(ROOT)
    data = json.loads(path.read_text(encoding="utf-8"))
    mutator(data)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _mutate_metadata(repo: Path, mutator) -> None:
    path = repo / "docs" / "releases" / "release-metadata.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutator(data)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _append_markdown(repo: Path, text: str) -> None:
    path = repo / MD_FILE.relative_to(ROOT)
    path.write_text(path.read_text(encoding="utf-8") + "\n" * 200 + text, encoding="utf-8")


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_checker_passes_on_current_repo():
    result = _run_script()
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "PASSED" in result.stdout


def test_checker_json_parses():
    result = _run_script("--json")
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    data = json.loads(result.stdout)
    assert data["artifact_type"] == "v0615_final_readiness_audit_check"
    assert data["valid"] is True
    assert data["errors"] == []


def test_checker_fails_if_required_candidate_is_missing(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(
        repo,
        lambda data: data.update(
            {"candidates": [c for c in data["candidates"] if c["id"] != "CAND-005"]}
        ),
    )

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "candidates must exactly list" in result.stdout
    assert "CAND-005" in result.stdout


def test_checker_fails_if_source_version_is_wrong(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(repo, lambda data: data.update({"source_version": "0.6.15"}))

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "source_version must be '0.6.14'" in result.stdout


def test_checker_fails_if_current_public_release_is_wrong(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(repo, lambda data: data.update({"current_public_release": "v0.6.15"}))
    _mutate_metadata(repo, lambda data: data.update({"current_public_release": "v0.6.15"}))

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "current_public_release" in result.stdout


def test_checker_fails_if_next_planned_release_is_wrong(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(repo, lambda data: data.update({"next_planned_release": "v0.6.16"}))
    _mutate_metadata(repo, lambda data: data.update({"next_planned_release": "v0.6.16"}))

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "next_planned_release" in result.stdout


def test_checker_fails_if_v0615_is_marked_released(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "v0.6.15 is released.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "v0.6.15 is released" in result.stdout.lower()


def test_checker_fails_if_pypi_is_marked_published(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(repo, lambda data: data.update({"pypi_published": True}))
    _mutate_metadata(repo, lambda data: data.update({"pypi_published": True}))

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "pypi_published must be False" in result.stdout


def test_checker_fails_if_tag_or_release_claimed_created(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(
        repo,
        lambda data: data.update({"tag_created": True, "github_release_created": True}),
    )

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "tag_created must be False" in result.stdout
    assert "github_release_created must be False" in result.stdout


def test_checker_fails_if_owner_release_authorization_implied(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "Owner authorization granted for release cutover.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "owner authorization granted" in result.stdout.lower()


def test_checker_fails_on_live_readiness_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "The portfolio is live ready.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "live ready" in result.stdout.lower()


def test_checker_fails_on_profit_guarantee_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "This audit claims guaranteed profit.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "guaranteed profit" in result.stdout.lower()


def test_checker_fails_on_absolute_safety_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "This audit claims zero risk.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "zero risk" in result.stdout.lower()


def test_checker_fails_on_order_submission_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "Orders were submitted to market.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "orders were submitted" in result.stdout.lower()


def test_checker_fails_if_required_commands_checkers_tests_are_missing(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(repo, lambda data: data.update({"required_checks": []}))

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "required_checks missing" in result.stdout


def test_checker_fails_if_required_evidence_checker_missing_from_gates(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    for rel in [
        "scripts/dev_check.sh",
        "scripts/ci_check.sh",
        "scripts/release_check.sh",
        ".github/workflows/ci.yml",
    ]:
        path = repo / rel
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                "scripts/check_v0615_paper_human_review_evidence.py",
                "scripts/removed_v0615_paper_human_review_evidence.py",
            ),
            encoding="utf-8",
        )

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "check_v0615_paper_human_review_evidence.py" in result.stdout


def test_checker_does_not_mutate_files(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    before = _tree_digest(repo)

    result = check(repo)

    after = _tree_digest(repo)
    assert result["valid"] is True
    assert before == after
