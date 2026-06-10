from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_INDEX = ROOT / "docs" / "demo-artifact-index.md"
CANDIDATES_MD = ROOT / "docs" / "releases" / "v0.6.8-candidates.md"
CANDIDATES_JSON = ROOT / "docs" / "releases" / "v0.6.8-candidates.json"
LINKING_DOCS = [
    ROOT / "README.md",
    ROOT / "docs" / "demo-paper-workflow.md",
    ROOT / "docs" / "external-reviewer-walkthrough.md",
]


def test_artifact_index_exists() -> None:
    assert ARTIFACT_INDEX.exists()
    text = ARTIFACT_INDEX.read_text(encoding="utf-8")
    assert len(text) > 500


def test_artifact_index_contains_required_sections() -> None:
    text = ARTIFACT_INDEX.read_text(encoding="utf-8")
    required_sections = (
        "## Purpose",
        "## Safety Scope",
        "## Demo Command",
        "## Artifact Summary",
        "## Artifact Details",
        "## Success Criteria",
        "## Troubleshooting",
        "## Related Docs",
    )
    for section in required_sections:
        assert section in text


def test_artifact_index_contains_safety_claims() -> None:
    text = ARTIFACT_INDEX.read_text(encoding="utf-8")
    assert "Paper/local only" in text or "paper/local" in text.lower()
    assert "No live broker credentials required" in text
    assert "No provider API keys required" in text
    assert "No live orders submitted" in text
    assert "No financial advice" in text


def test_artifact_index_does_not_claim_live_trading() -> None:
    lower = ARTIFACT_INDEX.read_text(encoding="utf-8").lower()
    forbidden = (
        "live trading ready",
        "production trading ready",
        "safe to trade",
        "trust granted",
        "provider execution enabled",
        "broker execution enabled",
        "orders enabled",
        "approvals enabled",
        "autonomous trading ready",
        "guaranteed profit",
        "profitable strategy",
        "verified alpha",
        "beats the market",
        "real-money ready",
    )
    for phrase in forbidden:
        assert phrase not in lower


def test_artifact_index_links_to_related_docs() -> None:
    text = ARTIFACT_INDEX.read_text(encoding="utf-8")
    assert "[Demo: Paper Workflow](demo-paper-workflow.md)" in text
    assert "[External Reviewer Walkthrough](external-reviewer-walkthrough.md)" in text
    assert "[Demo Risk Rejection](demo-risk-rejection.md)" in text
    assert "[Demo Audit](demo-audit.md)" in text


def test_linking_docs_reference_artifact_index() -> None:
    for path in LINKING_DOCS:
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "demo-artifact-index.md" in text


def test_candidates_md_marks_cand_001_implemented() -> None:
    text = CANDIDATES_MD.read_text(encoding="utf-8")
    assert "CAND-001" in text
    assert "implemented" in text.lower()
    # Check the Accepted Candidates section specifically
    in_accepted = False
    for line in text.splitlines():
        if "## Accepted Candidates" in line:
            in_accepted = True
        elif line.startswith("## "):
            in_accepted = False
        if in_accepted:
            if "CAND-001" in line:
                assert "implemented" in line.lower()
            if "CAND-002" in line or "CAND-003" in line or "CAND-004" in line:
                assert "not yet implemented" in line.lower()


def test_candidates_json_marks_cand_001_implemented() -> None:
    data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    candidates = {c["id"]: c for c in data.get("candidates", [])}
    assert candidates["CAND-001"].get("implemented") is True
    assert candidates["CAND-002"].get("implemented") is False
    assert candidates["CAND-003"].get("implemented") is False
    assert candidates["CAND-004"].get("implemented") is False


def test_artifact_index_describes_expected_artifacts() -> None:
    text = ARTIFACT_INDEX.read_text(encoding="utf-8")
    assert ".atlas/config.toml" in text
    assert ".atlas/discipline.md" in text
    assert "result.json" in text
    assert "report.md" in text
    assert "audit/" in text
    assert "pending_orders/" in text
