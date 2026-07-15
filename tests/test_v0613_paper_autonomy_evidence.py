# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_v0613_paper_autonomy_evidence.py
# PURPOSE: Verifies v0613 paper autonomy evidence behavior and regression
#         expectations.
# DEPS:    hashlib, json, shutil, subprocess, sys, pathlib.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_v0613_paper_autonomy_evidence.py"
EVIDENCE_JSON = ROOT / "docs" / "releases" / "v0.6.13-paper-autonomy-evidence.json"
EVIDENCE_MD = ROOT / "docs" / "releases" / "v0.6.13-paper-autonomy-evidence.md"

EXPECTED_IDS = [
    "CAND-021",
    "CAND-022",
    "CAND-023",
    "CAND-024",
    "CAND-025",
    "CAND-026",
    "CAND-027",
    "CAND-028",
    "CAND-029",
]

REQUIRED_COPY_FILES = {
    "README.md",
    "pyproject.toml",
    "src/atlas_agent/__init__.py",
    "docs/releases/release-metadata.json",
    "docs/releases/v0.6.13-paper-autonomy-evidence.md",
    "docs/releases/v0.6.13-paper-autonomy-evidence.json",
    "docs/releases/v0.6.13-candidate-selection.md",
    "docs/releases/v0.6.13-candidates.md",
    "docs/releases/v0.6.13-candidates.json",
    "docs/releases/v0.6.13-plan.md",
    "docs/trust/README.md",
    "docs/public-launch-readiness.md",
    "docs/reviewer-checklist.md",
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def run_checker(*args: str, root: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(CHECKER)]
    if root is not None:
        command.extend(["--root", str(root)])
    command.extend(args)
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def load_bundle() -> dict:
    return json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))


def copy_minimal_repo(tmp_path: Path) -> Path:
    bundle = load_bundle()
    files = set(REQUIRED_COPY_FILES)
    for candidate in bundle["candidates"]:
        for key in ["primary_docs", "primary_scripts", "primary_tests", "primary_checkers"]:
            files.update(candidate.get(key, []))

    for rel in sorted(files):
        src = ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return tmp_path


def hash_tree(root: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def test_checker_passes_on_real_repo() -> None:
    result = run_checker()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_checker_json_parses() -> None:
    result = run_checker("--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["artifact_type"] == "v0613_paper_autonomy_evidence_check"
    assert payload["valid"] is True
    assert payload["errors"] == []


def test_json_bundle_schema_and_candidate_ids() -> None:
    bundle = load_bundle()
    assert bundle["artifact_type"] == "v0613_paper_autonomy_evidence"
    assert bundle["schema_version"] == 1
    assert bundle["release_line"] == "v0.6.13"
    assert bundle["status"] == "planning_only"
    assert [candidate["id"] for candidate in bundle["candidates"]] == EXPECTED_IDS
    assert all(candidate["status"] == "implemented" for candidate in bundle["candidates"])


def test_referenced_files_exist() -> None:
    bundle = load_bundle()
    for candidate in bundle["candidates"]:
        for key in ["primary_docs", "primary_scripts", "primary_tests", "primary_checkers"]:
            for rel in candidate[key]:
                assert (ROOT / rel).exists(), rel


def test_release_identity_remains_planning_only() -> None:
    bundle = load_bundle()
    assert bundle["source_version"] == "0.6.12"
    assert bundle["current_public_release"] == "v0.6.12"
    assert bundle["next_planned_release"] == "v0.6.13"
    assert bundle["pypi_published"] is False
    assert bundle["v0613_tag_created"] is False
    assert bundle["v0613_github_release_created"] is False
    assert bundle["safety"]["live_trading_enabled"] is False
    assert bundle["safety"]["profit_claims"] is False
    assert bundle["safety"]["live_readiness_claims"] is False


def test_no_v0613_release_tag_or_pypi_claims() -> None:
    text = EVIDENCE_MD.read_text(encoding="utf-8").lower()
    bundle = load_bundle()
    assert "no `v0.6.13` tag has been created" in text
    assert "no `v0.6.13` github release has been created" in text
    assert "no `v0.6.13` pypi publication has occurred" in text
    assert bundle["v0613_tag_created"] is False
    assert bundle["v0613_github_release_created"] is False
    assert bundle["pypi_published"] is False


def test_unsafe_claims_fail_when_injected(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    target = repo / "docs" / "releases" / "v0.6.13-paper-autonomy-evidence.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nThis bundle proves guaranteed profit and is live ready.\n",
        encoding="utf-8",
    )

    result = run_checker(root=repo)
    assert result.returncode == 1
    assert "guaranteed profit" in result.stdout.lower()
    assert "live ready" in result.stdout.lower()


def test_release_claim_fails_when_injected(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    target = repo / "docs" / "releases" / "v0.6.13-paper-autonomy-evidence.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nv0.6.13 is released.\n",
        encoding="utf-8",
    )

    result = run_checker(root=repo)
    assert result.returncode == 1
    assert "v0.6.13 is released" in result.stdout.lower()


def test_missing_candidate_fails(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    target = repo / "docs" / "releases" / "v0.6.13-paper-autonomy-evidence.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["candidates"] = [candidate for candidate in data["candidates"] if candidate["id"] != "CAND-029"]
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")

    result = run_checker(root=repo)
    assert result.returncode == 1
    assert "candidates must exactly list" in result.stdout


def test_missing_referenced_file_fails(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    (repo / "tests" / "test_paper_strategy_scorecard.py").unlink()

    result = run_checker(root=repo)
    assert result.returncode == 1
    assert "tests/test_paper_strategy_scorecard.py" in result.stdout


def test_checker_does_not_mutate_files(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    before = hash_tree(repo)

    result = run_checker(root=repo)

    assert result.returncode == 0, result.stdout + result.stderr
    assert hash_tree(repo) == before
