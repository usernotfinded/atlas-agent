# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_v0613_release_cutover_preflight.py
# PURPOSE: Verifies v0613 release cutover preflight behavior and regression
#         expectations.
# DEPS:    json, subprocess, sys, pathlib, pytest, scripts.
# ==============================================================================

# --- IMPORTS ---

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_v0613_release_cutover_preflight import check

# --- CONFIGURATION AND CONSTANTS ---

ARTIFACT_TYPE = "v0613_release_cutover_preflight_check"


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
        "docs/releases/v0.6.13-final-reviewer-index.md",
        "docs/releases/v0.6.13-final-reviewer-index.json",
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
    md_content = """# v0.6.13 Release Cutover Preflight

    This is planning-only. It is a release cutover preflight blocker.

    ## Context
    Covers CAND-021 through CAND-032.
    Included candidates: CAND-021, CAND-022, CAND-023, CAND-024, CAND-025, CAND-026, CAND-027, CAND-028, CAND-029, CAND-030, CAND-031, CAND-032.

    ## References
    - docs/releases/v0.6.13-final-reviewer-index.md
    - docs/releases/v0.6.13-final-reviewer-index.json
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
    - release tag authorization: blocked
    - github release authorization: blocked
    - pypi authorization: disabled
    - package version bump authorization: blocked
    - live-trading promotion: prohibited
    - provider execution enablement: prohibited
    - broker execution enablement: prohibited
    """
    (releases / "v0.6.13-release-cutover-preflight.md").write_text(md_content, encoding="utf-8")

    # Create valid json
    json_content = {
        "schema_version": "atlas-release-cutover-preflight/1.0",
        "planning_only": True,
        "release_blocking": True,
        "release_version": "v0.6.13",
        "owner_decision_states": {
            "owner_approval": "pending",
            "release_tag_authorization": "blocked",
            "github_release_authorization": "blocked",
            "pypi_publish_authorization": "disabled",
            "package_version_bump_authorization": "blocked",
            "live_trading_promotion": "prohibited",
            "provider_execution_enablement": "prohibited",
            "broker_execution_enablement": "prohibited"
        },
        "references": {
            "final_reviewer_index_md": "docs/releases/v0.6.13-final-reviewer-index.md",
            "final_reviewer_index_json": "docs/releases/v0.6.13-final-reviewer-index.json",
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
    (releases / "v0.6.13-release-cutover-preflight.json").write_text(json.dumps(json_content), encoding="utf-8")

    return repo


def test_happy_path(temp_repo: Path) -> None:
    result = check(temp_repo)
    assert result["valid"] is True
    assert not result["errors"]


def test_json_mode_output_shape(temp_repo: Path) -> None:
    script = Path("scripts/check_v0613_release_cutover_preflight.py").resolve()
    proc = subprocess.run(
        [sys.executable, str(script), "--json", "--root", str(temp_repo)],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["artifact_type"] == ARTIFACT_TYPE
    assert data["valid"] is True


def test_missing_markdown_fails(temp_repo: Path) -> None:
    (temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md").unlink()
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("Missing required file" in err for err in result["errors"])


def test_missing_json_fails(temp_repo: Path) -> None:
    (temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.json").unlink()
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("Missing required file" in err for err in result["errors"])


def test_missing_final_reviewer_index_link_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md"
    text = md.read_text()
    md.write_text(text.replace("v0.6.13-final-reviewer-index.md", "something-else.md"))
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("missing reference to docs/releases/v0.6.13-final-reviewer-index.md" in err.lower() for err in result["errors"])


def test_missing_paper_autonomy_evidence_link_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md"
    text = md.read_text()
    md.write_text(text.replace("v0.6.13-paper-autonomy-evidence.md", "something-else.md"))
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("missing reference to docs/releases/v0.6.13-paper-autonomy-evidence.md" in err.lower() for err in result["errors"])









def test_live_trading_promotion_allowed_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md"
    text = md.read_text()
    md.write_text(text.replace("live-trading promotion: prohibited", "live-trading promotion: allowed"))
    result = check(temp_repo)
    assert result["valid"] is False


def test_provider_execution_enablement_allowed_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md"
    text = md.read_text()
    md.write_text(text.replace("provider execution enablement: prohibited", "provider execution enablement: allowed"))
    result = check(temp_repo)
    assert result["valid"] is False


def test_profit_claim_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md"
    text = md.read_text()
    md.write_text(text + "\n" * 100 + "We provide guaranteed profit.\n")
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("unsafe claim without negation: guaranteed profit" in err for err in result["errors"])


def test_autonomous_live_readiness_claim_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md"
    text = md.read_text()
    md.write_text(text + "\n" * 100 + "This is autonomous-live-ready.\n")
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("unsafe claim without negation: autonomous-live-ready" in err for err in result["errors"])


def test_missing_cand032_tracking_reference_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md"
    text = md.read_text()
    md.write_text(text.replace("CAND-032", "REDACTED"))
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("missing coverage reference to CAND-032" in err for err in result["errors"])


def test_markdown_json_drift_fails(temp_repo: Path) -> None:
    md = temp_repo / "docs/releases/v0.6.13-release-cutover-preflight.md"
    text = md.read_text()
    # Remove a required JSON evidence link from Markdown
    md.write_text(text.replace("docs/releases/v0.6.13-plan.md", "REMOVED"))
    result = check(temp_repo)
    assert result["valid"] is False
    assert any("missing reference from JSON: docs/releases/v0.6.13-plan.md" in err for err in result["errors"])


def test_integration_command_can_be_called_from_tests(temp_repo: Path) -> None:
    script = Path("scripts/check_v0613_release_cutover_preflight.py").resolve()
    proc = subprocess.run(
        [sys.executable, str(script), "--root", str(temp_repo)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "PASSED" in proc.stdout
