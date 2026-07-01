"""Tests for the candidate-chain consistency checker."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECKER_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_candidate_chain.py"


def _run(repo: Path):
    return subprocess.run(
        [sys.executable, str(CHECKER_SCRIPT), str(repo)],
        capture_output=True,
        text=True,
        cwd=str(repo),
    )


def _write_metadata(repo: Path):
    releases_dir = repo / "docs" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": 1,
        "source_version": "0.6.19",
        "current_public_release": "v0.6.19",
        "next_planned_release": "v0.6.20",
        "historical_stable_baseline": "v0.5.8",
        "pypi_published": False,
        "releases": [
            {
                "tag": "v0.6.19",
                "version": "0.6.19",
                "status": "current_public",
                "release_notes": "docs/releases/v0.6.19.md",
                "github_release": True,
                "pypi_published": False,
                "release_authorized": True,
                "release_type": "github_only",
                "tag_created": True,
                "github_release_created": True,
            },
            {
                "tag": "v0.6.18",
                "version": "0.6.18",
                "status": "historical",
                "release_notes": "docs/releases/v0.6.18.md",
                "github_release": True,
                "pypi_published": False,
                "release_authorized": True,
                "release_type": "github_only",
                "tag_created": True,
                "github_release_created": True,
            },
        ],
    }
    (releases_dir / "release-metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


def _write_json(repo: Path, release_line: str, data: dict):
    releases_dir = repo / "docs" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    path = releases_dir / f"{release_line}-candidates.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _write_md(repo: Path, release_line: str, stem: str, text: str):
    releases_dir = repo / "docs" / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)
    path = releases_dir / f"{release_line}-{stem}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _candidate(cid: str, status: str, accepted: bool = False, verdict: str | None = None, title: str = "Title"):
    c = {
        "id": cid,
        "status": status,
        "title": title,
    }
    if accepted is not None:
        c["accepted"] = accepted
    if verdict is not None:
        c["acceptance_verdict"] = verdict
    return c


def _modern_chain(release_line: str, candidate_status: str = "proposed", accepted: bool = False, verdict: str | None = None):
    return {
        "release_line": release_line,
        "status": "planning" if candidate_status != "released" else "released",
        "source_version": "0.6.19",
        "current_public_release": "v0.6.19",
        "next_planned_release": "v0.6.20",
        "pypi_published": False,
        "tag_created": release_line == "v0.6.19",
        "github_release_created": release_line == "v0.6.19",
        "candidates": [
            _candidate("CAND-001", candidate_status, accepted=accepted, verdict=verdict),
        ],
    }


# -----------------------------------------------------------------------------
# Current-repo smoke test
# -----------------------------------------------------------------------------


def test_checker_passes_on_current_repo():
    repo = Path(__file__).resolve().parent.parent
    result = _run(repo)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Candidate-chain consistency PASSED" in result.stdout


# -----------------------------------------------------------------------------
# Positive cases
# -----------------------------------------------------------------------------


def test_valid_planning_chain_passes(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(repo, "v0.6.20", _modern_chain("v0.6.20", candidate_status="proposed"))
    result = _run(repo)
    assert result.returncode == 0, result.stdout
    assert "Candidate-chain consistency PASSED" in result.stdout


def test_valid_released_chain_passes(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(
        repo,
        "v0.6.19",
        _modern_chain("v0.6.19", candidate_status="released", accepted=True, verdict="PASS"),
    )
    result = _run(repo)
    assert result.returncode == 0, result.stdout
    assert "Candidate-chain consistency PASSED" in result.stdout


def test_accepted_candidate_in_next_release_passes(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(
        repo,
        "v0.6.20",
        _modern_chain("v0.6.20", candidate_status="accepted", accepted=True, verdict="PASS"),
    )
    result = _run(repo)
    assert result.returncode == 0, result.stdout


def test_historical_released_candidate_passes(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(
        repo,
        "v0.6.18",
        {
            "release_line": "v0.6.18",
            "status": "released",
            "source_version": "0.6.18",
            "current_public_release": "v0.6.18",
            "next_planned_release": "v0.6.19",
            "pypi_published": False,
            "tag_created": True,
            "github_release_created": True,
            "candidates": [
                _candidate("CAND-010", "released", accepted=True, verdict="PASS"),
            ],
        },
    )
    result = _run(repo)
    assert result.returncode == 0, result.stdout


def test_missing_optional_selection_doc_passes(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(repo, "v0.6.20", _modern_chain("v0.6.20"))
    # No candidate-selection.md exists.
    result = _run(repo)
    assert result.returncode == 0, result.stdout


def test_unknown_schema_extra_keys_passes_or_warns(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    legacy = {
        "artifact_type": "patch_candidate_inventory",
        "release": "v0.6.1",
        "extra_field": "should be ignored",
        "candidates": [],
    }
    _write_json(repo, "v0.6.1", legacy)
    result = _run(repo)
    assert result.returncode == 0, result.stdout
    if "WARNING:" in result.stdout:
        assert "v0.6.1" in result.stdout


# -----------------------------------------------------------------------------
# Negative cases
# -----------------------------------------------------------------------------


def test_mismatched_md_json_release_line_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(repo, "v0.6.20", _modern_chain("v0.6.20"))
    _write_md(
        repo,
        "v0.6.20",
        "candidates",
        "# v0.6.20 Candidates\n\nStatus: **planning** for `v0.6.21`.\n",
    )
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout
    assert "release_line" in result.stdout


def test_duplicate_candidate_id_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    data = _modern_chain("v0.6.20")
    data["candidates"].append(_candidate("CAND-001", "proposed"))
    _write_json(repo, "v0.6.20", data)
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout
    assert "duplicate" in result.stdout.lower()


def test_unknown_candidate_status_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(
        repo,
        "v0.6.20",
        _modern_chain("v0.6.20", candidate_status="unknown_status"),
    )
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout
    assert "unknown status" in result.stdout.lower()


def test_unknown_acceptance_verdict_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(
        repo,
        "v0.6.20",
        _modern_chain("v0.6.20", candidate_status="accepted", accepted=True, verdict="MAYBE"),
    )
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout
    assert "unknown verdict" in result.stdout.lower()


def test_next_planned_release_claiming_released_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    data = _modern_chain("v0.6.20", candidate_status="proposed")
    data["status"] = "released"
    _write_json(repo, "v0.6.20", data)
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout


def test_next_planned_release_tag_created_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    data = _modern_chain("v0.6.20")
    data["tag_created"] = True
    _write_json(repo, "v0.6.20", data)
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout
    assert "tag_created" in result.stdout


def test_next_planned_release_github_release_created_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    data = _modern_chain("v0.6.20")
    data["github_release_created"] = True
    _write_json(repo, "v0.6.20", data)
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout
    assert "github_release_created" in result.stdout


def test_pypi_mismatch_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    data = _modern_chain("v0.6.20")
    data["pypi_published"] = True
    _write_json(repo, "v0.6.20", data)
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout
    assert "pypi" in result.stdout.lower()


def test_forbidden_live_trading_claim_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(repo, "v0.6.20", _modern_chain("v0.6.20"))
    _write_md(
        repo,
        "v0.6.20",
        "candidates",
        "# v0.6.20 Candidates\n\nThis candidate is safe to trade live.\n",
    )
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout


def test_forbidden_order_submission_without_approval_fails(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(repo, "v0.6.20", _modern_chain("v0.6.20"))
    _write_md(
        repo,
        "v0.6.20",
        "candidate-selection",
        "# Selection\n\nUsers may submit orders without approval.\n",
    )
    result = _run(repo)
    assert result.returncode == 2, result.stdout
    assert "ERROR:" in result.stdout
    assert "submit orders without approval" in result.stdout.lower()


# -----------------------------------------------------------------------------
# Negative-context positive cases
# -----------------------------------------------------------------------------


def test_negative_context_forbidden_phrases_pass(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    _write_json(repo, "v0.6.20", _modern_chain("v0.6.20"))
    text = """
# v0.6.20 Candidates

- This is not live-ready.
- It is not safe to trade.
- It is not profitable.
- PyPI is not published.
- No order submission enabled.
"""
    _write_md(repo, "v0.6.20", "candidates", text)
    result = _run(repo)
    assert result.returncode == 0, result.stdout


# -----------------------------------------------------------------------------
# Operational-error cases
# -----------------------------------------------------------------------------


def test_exit_1_for_missing_metadata(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "docs" / "releases").mkdir(parents=True, exist_ok=True)
    result = _run(repo)
    assert result.returncode == 1, result.stdout


def test_exit_1_for_malformed_json(tmp_path: Path):
    repo = tmp_path / "repo"
    _write_metadata(repo)
    releases_dir = repo / "docs" / "releases"
    (releases_dir / "v0.6.20-candidates.json").write_text("{not json", encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 1, result.stdout


# -----------------------------------------------------------------------------
# Static source constraints
# -----------------------------------------------------------------------------


def test_no_network_calls_in_checker():
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    for name in ("requests", "urllib", "httpx", "socket"):
        assert name not in source, f"checker imports/network mention: {name}"


def test_no_credential_loading_in_checker():
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    for name in ("load_dotenv", "os.environ", "getenv"):
        assert name not in source, f"checker may load credentials: {name}"


def test_no_private_imports_from_check_forbidden_claims():
    source = CHECKER_SCRIPT.read_text(encoding="utf-8")
    for name in ("_FORBIDDEN_PHRASES", "_collect_paths"):
        assert name not in source, f"checker imports private symbol: {name}"
