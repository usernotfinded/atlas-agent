# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_v0613_final_reviewer_index.py
# PURPOSE: Verifies v0613 final reviewer index behavior and regression
#         expectations.
# DEPS:    json, subprocess, sys, pathlib, pytest, scripts.
# ==============================================================================

# --- IMPORTS ---

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_v0613_final_reviewer_index import check

# --- CONFIGURATION AND CONSTANTS ---

ARTIFACT_TYPE = "v0613_final_reviewer_index_check"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    docs = repo / "docs"
    releases = docs / "releases"
    releases.mkdir(parents=True)
    
    # Create required referenced files
    for ref in [
        "docs/releases/v0.6.13-paper-autonomy-evidence.md",
        "docs/releases/v0.6.13-paper-autonomy-evidence.json",
        "docs/releases/v0.6.13-candidates.md",
        "docs/releases/v0.6.13-candidates.json",
        "docs/releases/v0.6.13-plan.md",
        "docs/public-launch-readiness.md",
        "docs/reviewer-checklist.md",
    ]:
        (repo / ref).touch()
        
    trust = docs / "trust"
    trust.mkdir(parents=True, exist_ok=True)
    (trust / "README.md").touch()
    
    # Create valid markdown
    md_content = """# v0.6.13 Final Reviewer Index
    
    This is planning-only.
    
    ## Context
    Covers CAND-021 through CAND-030.
    Included candidates: CAND-021, CAND-022, CAND-023, CAND-024, CAND-025, CAND-026, CAND-027, CAND-028, CAND-029, CAND-030.
    
    ## References
    - docs/releases/v0.6.13-paper-autonomy-evidence.md
    - docs/releases/v0.6.13-paper-autonomy-evidence.json
    - docs/releases/v0.6.13-candidates.md
    - docs/releases/v0.6.13-candidates.json
    - docs/releases/v0.6.13-plan.md
    - docs/public-launch-readiness.md
    - docs/reviewer-checklist.md
    - docs/trust/README.md
    
    ## Owner Decision States
    - owner approval: pending
    - release tag authorization: pending
    - github release authorization: pending
    - pypi authorization: disabled
    - live-trading promotion: prohibited
    
    ## Owner-Approval Checklist
    - [ ] I have reviewed the v0.6.13 paper autonomy evidence bundle.
    """
    (releases / "v0.6.13-final-reviewer-index.md").write_text(md_content, encoding="utf-8")
    
    # Create valid json
    json_content = {
        "schema_version": "atlas-final-reviewer-index/1.0",
        "planning_only": True,
        "release_version": "v0.6.13",
        "owner_decision_states": {
            "owner_approval": "pending",
            "release_tag_authorization": "pending",
            "github_release_authorization": "pending",
            "pypi_authorization": "disabled",
            "live_trading_promotion": "prohibited"
        },
        "safety_invariants": {
            "version_bump": False,
            "tag_created": False,
            "github_release": False,
            "pypi_publish": False,
            "live_trading_enabled": False,
            "live_submit_enabled": False,
            "provider_execution_enabled": False,
            "broker_execution_enabled": False,
            "credentials_exposed": False,
            "profit_claims": False,
            "live_readiness_claims": False,
            "autonomous_live_readiness_claims": False
        },
        "evidence_bundle": {
            "evidence_md": "docs/releases/v0.6.13-paper-autonomy-evidence.md",
            "evidence_json": "docs/releases/v0.6.13-paper-autonomy-evidence.json",
            "candidates_md": "docs/releases/v0.6.13-candidates.md",
            "candidates_json": "docs/releases/v0.6.13-candidates.json",
            "plan_md": "docs/releases/v0.6.13-plan.md",
            "public_launch_readiness": "docs/public-launch-readiness.md",
            "reviewer_checklist": "docs/reviewer-checklist.md",
            "trust_center": "docs/trust/README.md"
        }
    }
    (releases / "v0.6.13-final-reviewer-index.json").write_text(json.dumps(json_content), encoding="utf-8")
    
    return repo


def test_happy_path(temp_repo: Path) -> None:
    result = check(temp_repo)
    assert result["valid"] is True
    assert not result["errors"]


def test_json_mode_output_shape(temp_repo: Path) -> None:
    script = Path("scripts/check_v0613_final_reviewer_index.py").resolve()
    proc = subprocess.run(
        [sys.executable, str(script), "--json", "--root", str(temp_repo)],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["artifact_type"] == ARTIFACT_TYPE
    assert data["valid"] is True


def test_missing_final_reviewer_index_fails(temp_repo: Path) -> None:
    (temp_repo / "docs/releases/v0.6.13-final-reviewer-index.md").unlink()
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("Missing required file" in err for err in result["errors"])


def test_missing_cand030_evidence_link_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-final-reviewer-index.md"
    text = md.read_text()
    md.write_text(text.replace("v0.6.13-paper-autonomy-evidence.md", "something-else.md"))
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("missing reference to docs/releases/v0.6.13-paper-autonomy-evidence.md" in err.lower() for err in result["errors"])


def test_missing_owner_approval_pending_state_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-final-reviewer-index.md"
    text = md.read_text()
    md.write_text(text.replace("owner approval: pending", "owner approval: complete"))
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("missing required phrase: owner approval: pending" in err for err in result["errors"])


def test_release_tag_approval_claim_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-final-reviewer-index.md"
    text = md.read_text()
    md.write_text(text + "\nI authorize the v0.6.13 tag created.\n")
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("unsafe claim without negation: tag created" in err for err in result["errors"])


def test_live_readiness_claim_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-final-reviewer-index.md"
    text = md.read_text()
    md.write_text(text + "\nThis release is live ready.\n")
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("unsafe claim without negation: live ready" in err for err in result["errors"])


def test_missing_cand_coverage_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-final-reviewer-index.md"
    text = md.read_text()
    md.write_text(text.replace("CAND-021", "REDACTED"))
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("missing coverage reference to CAND-021" in err for err in result["errors"])


def test_markdown_json_drift_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-final-reviewer-index.md"
    text = md.read_text()
    # Remove a required JSON evidence link from Markdown
    md.write_text(text.replace("docs/releases/v0.6.13-plan.md", "REMOVED"))
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("missing evidence bundle reference from JSON: docs/releases/v0.6.13-plan.md" in err for err in result["errors"])


def test_integration_command_can_be_called_from_tests(temp_repo: Path) -> None:
    script = Path("scripts/check_v0613_final_reviewer_index.py").resolve()
    proc = subprocess.run(
        [sys.executable, str(script), "--root", str(temp_repo)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "PASSED" in proc.stdout
