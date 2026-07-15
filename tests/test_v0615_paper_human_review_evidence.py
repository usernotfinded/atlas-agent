# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_v0615_paper_human_review_evidence.py
# PURPOSE: Verifies v0615 paper human review evidence behavior and regression
#         expectations.
# DEPS:    hashlib, json, subprocess, sys, pathlib, scripts.
# ==============================================================================

# --- IMPORTS ---

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.check_v0615_paper_human_review_evidence import check


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_v0615_paper_human_review_evidence.py"
JSON_FILE = ROOT / "docs" / "releases" / "v0.6.15-paper-human-review-evidence.json"
MD_FILE = ROOT / "docs" / "releases" / "v0.6.15-paper-human-review-evidence.md"

REQUIRED_DOCS = [
    "docs/paper-human-review-pack.md",
    "docs/paper-human-review-ledger.md",
    "docs/paper-human-review-policy.md",
    "docs/paper-human-review-replay.md",
    "docs/releases/v0.6.15-paper-human-review-evidence.md",
]

REQUIRED_DEMOS = [
    "scripts/demo_paper_human_review_pack.sh",
    "scripts/demo_paper_human_review_ledger.sh",
    "scripts/demo_paper_human_review_policy.sh",
    "scripts/demo_paper_human_review_replay.sh",
]

REQUIRED_CHECKERS = [
    "scripts/check_paper_human_review_pack.py",
    "scripts/check_paper_human_review_ledger.py",
    "scripts/check_paper_human_review_policy.py",
    "scripts/check_paper_human_review_replay.py",
    "scripts/check_v0615_paper_human_review_evidence.py",
]

REQUIRED_TESTS = [
    "tests/test_paper_human_review_pack.py",
    "tests/test_paper_human_review_ledger.py",
    "tests/test_paper_human_review_policy.py",
    "tests/test_paper_human_review_replay.py",
    "tests/test_v0615_paper_human_review_evidence.py",
]

GATE_FILES = [
    "scripts/dev_check.sh",
    "scripts/ci_check.sh",
    "scripts/release_check.sh",
    ".github/workflows/ci.yml",
]


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
        "docs/releases/v0.6.15-paper-human-review-evidence.md",
        "docs/releases/v0.6.15-paper-human-review-evidence.json",
        "docs/releases/release-metadata.json",
        "pyproject.toml",
        "src/atlas_agent/__init__.py",
    ]:
        src = ROOT / rel
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    for rel in REQUIRED_DOCS + REQUIRED_DEMOS + REQUIRED_CHECKERS + REQUIRED_TESTS:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(f"placeholder for {rel}\n", encoding="utf-8")

    gate_refs = "\n".join(REQUIRED_CHECKERS + REQUIRED_TESTS)
    for rel in GATE_FILES:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# gate references\n{gate_refs}\n", encoding="utf-8")

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
    assert data["artifact_type"] == "v0615_paper_human_review_evidence_check"
    assert data["valid"] is True
    assert data["errors"] == []


def test_fails_if_json_omits_candidate(tmp_path):
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


def test_fails_if_source_version_wrong(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(repo, lambda data: data.update({"source_version": "0.6.15"}))

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "source_version must be '0.6.14'" in result.stdout


def test_fails_if_current_public_release_wrong(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(repo, lambda data: data.update({"current_public_release": "v0.6.15"}))

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "current_public_release must be 'v0.6.14'" in result.stdout


def test_fails_if_evidence_claims_released(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "v0.6.15 is released.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "v0.6.15 is released" in result.stdout.lower()


def test_fails_if_pypi_published(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(repo, lambda data: data.update({"pypi_published": True}))

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "pypi_published must be False" in result.stdout


def test_fails_if_tag_or_release_created(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(
        repo,
        lambda data: data.update({"tag_created": True, "github_release_created": True}),
    )

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "tag_created must be False" in result.stdout
    assert "github_release_created must be False" in result.stdout


def test_fails_on_live_ready_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "The chain is live ready.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "unsafe claim" in result.stdout.lower()


def test_fails_on_guaranteed_profit_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "This evidence claims guaranteed profit.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "guaranteed profit" in result.stdout.lower()


def test_fails_on_absolute_safety_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "This evidence claims absolute safety.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "absolute safety" in result.stdout.lower()


def test_fails_on_zero_risk_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "This evidence claims zero risk.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "zero risk" in result.stdout.lower()


def test_fails_on_risk_free_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "This evidence claims risk-free trading.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "risk-free" in result.stdout.lower()


def test_fails_on_order_submission_wording(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _append_markdown(repo, "Orders were submitted to the broker.")

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "orders were submitted" in result.stdout.lower()


def test_fails_if_required_command_missing(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    _mutate_json(
        repo,
        lambda data: data.update(
            {
                "required_commands": [
                    "atlas backtest portfolio-review-pack",
                    "atlas backtest portfolio-review-ledger",
                    "atlas backtest portfolio-review-policy",
                ]
            }
        ),
    )

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "required_commands must exactly list" in result.stdout


def test_fails_if_required_checker_missing_from_gates(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    path = repo / "scripts" / "dev_check.sh"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("scripts/check_v0615_paper_human_review_evidence.py", ""),
        encoding="utf-8",
    )

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "check_v0615_paper_human_review_evidence.py" in result.stdout


def test_fails_if_required_test_missing_from_gates(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    path = repo / ".github" / "workflows" / "ci.yml"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("tests/test_v0615_paper_human_review_evidence.py", ""),
        encoding="utf-8",
    )

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "test_v0615_paper_human_review_evidence.py" in result.stdout


def test_fails_if_required_test_file_missing(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    (repo / "tests" / "test_v0615_paper_human_review_evidence.py").unlink()

    result = _run_temp(repo)
    assert result.returncode == 1
    assert "references missing file" in result.stdout


def test_checker_does_not_mutate_files(tmp_path):
    repo = _copy_minimal_repo(tmp_path)
    before = _tree_digest(repo)

    result = check(repo)

    after = _tree_digest(repo)
    assert result["valid"] is True
    assert before == after
