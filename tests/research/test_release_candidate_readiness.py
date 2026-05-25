"""Tests for release candidate readiness report — Batch 10.1.

No execution code, no network calls, no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent import __version__
from atlas_agent.research.release_candidate_readiness import (
    RELEASE_CANDIDATE_READINESS_VERSION,
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    _compute_expected_readiness_core,
    _find_mismatched_derived_fields,
    build_release_candidate_readiness_dict,
    create_release_candidate_readiness,
    doctor_release_candidate_readiness,
    find_release_candidate_readiness_by_id,
    iter_release_candidate_readiness_artifacts,
    load_release_candidate_readiness,
    release_candidate_readiness_sha256,
    replay_release_candidate_readiness,
    safe_validate_release_candidate_readiness_data,
    summarize_release_candidate_readiness,
    validate_release_candidate_readiness_artifact,
)
from atlas_agent.research.session import ResearchSessionError


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# Creation / build
# ---------------------------------------------------------------------------


class TestCreate:
    def test_create_happy_path(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        assert result["ok"] is True
        assert result["status"] == "research_release_candidate_readiness_created"
        assert "release_candidate_readiness_report_id" in result
        assert result["symbol"] == "ATLAS-DEMO"
        assert result["version"] == __version__

    def test_artifact_persisted(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        report_id = result["release_candidate_readiness_report_id"]
        artifact_path = workspace / ".atlas" / "research" / "ATLAS-DEMO" / "release_candidate_readiness_reports" / f"{report_id}.json"
        assert artifact_path.exists()

    def test_readiness_score_range(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        assert 0 <= result["readiness_score"] <= 100

    def test_status_is_safe(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        assert result["readiness_status"] in ("sandbox_release_candidate_ready", "sandbox_release_candidate_blocked")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidate:
    def test_validate_blocked_report_not_release_ready(self, workspace: Path) -> None:
        # In a fresh tmp_path, required files are missing so the report is blocked.
        # Structural validity should still be true; readiness_valid should be false.
        create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        items = iter_release_candidate_readiness_artifacts(workspace)
        assert len(items) == 1
        path = workspace / items[0]["artifact_path"]
        result = validate_release_candidate_readiness_artifact(path, workspace)
        assert result.valid is False
        assert result.structurally_valid is True
        assert result.readiness_valid is False
        assert result.passed_checks > 0
        assert result.failed_checks >= 1
        assert result.recommendation == "fix_readiness_blockers"

    def test_validate_rejects_hard_false_invariant(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-001", __version__)
        report["provider_execution_unlocked"] = True
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        path = workspace / report["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        result = validate_release_candidate_readiness_artifact(path, workspace)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_validate_rejects_unsafe_claim(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-002", __version__)
        report["readiness_status"] = "live trading ready"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        path = workspace / report["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        result = validate_release_candidate_readiness_artifact(path, workspace)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_validate_rejects_forbidden_fragment(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-003", __version__)
        report["checks"][0]["message"] = "path /Users/natan/dev"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        path = workspace / report["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        result = validate_release_candidate_readiness_artifact(path, workspace)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_validate_rejects_hash_mismatch(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-004", __version__)
        report["artifact_hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
        path = workspace / report["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        result = validate_release_candidate_readiness_artifact(path, workspace)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_validate_rejects_unsafe_status(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-005", __version__)
        report["readiness_status"] = "live_trading_ready"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        path = workspace / report["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        result = validate_release_candidate_readiness_artifact(path, workspace)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_doctor_blocked_report_reports_safe_blockers(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-doctor-blocked", __version__)
        assert report["readiness_status"] == "sandbox_release_candidate_blocked"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        path = workspace / report["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        doctor = doctor_release_candidate_readiness(path, workspace)
        assert doctor["valid"] is False
        assert doctor["structurally_valid"] is True
        assert doctor["readiness_valid"] is False
        assert doctor["readiness_status"] == "sandbox_release_candidate_blocked"
        assert doctor["blockers"]

    def test_validate_missing_release_note_blocks_readiness(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-no-note", __version__)
        # Manually set release_note_present to false and recompute status
        for c in report["checks"]:
            if c["name"] == "release_note_present":
                c["passed"] = False
                c["message"] = "missing docs/releases/v" + __version__ + ".md"
        report["readiness_status"] = "sandbox_release_candidate_blocked"
        report["blockers"] = ["release_note_present"]
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        path = workspace / report["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        result = validate_release_candidate_readiness_artifact(path, workspace)
        assert result.valid is False
        assert result.readiness_valid is False
        assert "readiness_blocked" in result.warnings
        assert "release_note_present" in result.blockers


# ---------------------------------------------------------------------------
# Safe validation
# ---------------------------------------------------------------------------


class TestSafeValidate:
    def test_passes_valid_artifact(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-006", __version__)
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == ""
        assert cleaned is not None

    def test_rejects_wrong_artifact_type(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-007", __version__)
        report["artifact_type"] = "wrong_type"
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == "wrong_artifact_type"

    def test_rejects_missing_version(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-008", __version__)
        del report["version"]
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == "missing_version"

    def test_rejects_hard_false_true(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-009", __version__)
        report["broker_touched"] = True
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == "hard_false_invariant_violated:broker_touched"

    def test_rejects_unsafe_claim_in_data(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-010", __version__)
        report["readiness_status"] = "trust granted"
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == "unsafe_positive_claim_detected"

    def test_rejects_forbidden_fragment(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-011", __version__)
        report["checks"][0]["message"] = "path /Users/natan/dev"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == "forbidden_fragment_detected"

    def test_rejects_sandbox_only_false(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-sandbox", __version__)
        report["sandbox_only"] = False
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == "sandbox_only_not_true"

    def test_rejects_paper_first_false(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-paper", __version__)
        report["paper_first"] = False
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == "paper_first_not_true"

    def test_rejects_offline_safe_false(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-offline", __version__)
        report["offline_safe"] = False
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == "offline_safe_not_true"

    def test_rejects_version_mismatch(self, workspace: Path) -> None:
        # Version mismatch is now caught in validate_artifact, not safe_validate
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-ver", __version__)
        report["version"] = "0.0.0.fake"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        # safe_validate no longer checks version; validate_artifact does
        cleaned, err = safe_validate_release_candidate_readiness_data(report, workspace)
        assert err == ""


# ---------------------------------------------------------------------------
# Derived field recomputation / tamper resistance
# ---------------------------------------------------------------------------


class TestDerivedFieldTamper:
    def _save_and_validate(self, workspace: Path, report: dict[str, Any]) -> Any:
        path = workspace / report["artifact_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return validate_release_candidate_readiness_artifact(path, workspace)

    def test_freshly_created_report_validates(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-fresh", __version__)
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        # Fresh tmp_path produces blocked report, but structurally valid
        assert result.structurally_valid is True
        assert result.readiness_valid is False
        assert result.mismatched_fields == []

    def test_rejects_readiness_score_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-rs", __version__)
        report["readiness_score"] = 999
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert "readiness_score" in result.mismatched_fields
        assert any(c["name"] == "derived_readiness_match" and not c["passed"] for c in result.checks)

    def test_rejects_readiness_status_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-st", __version__)
        # Force a ready status when it should be blocked
        report["readiness_status"] = "sandbox_release_candidate_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert "readiness_status" in result.mismatched_fields

    def test_rejects_release_note_present_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-rn", __version__)
        report["release_note_present"] = True
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert "release_note_present" in result.mismatched_fields

    def test_rejects_quickstart_verified_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-qv", __version__)
        report["quickstart_verified"] = True
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert "quickstart_verified" in result.mismatched_fields

    def test_rejects_public_docs_consistent_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-pdc", __version__)
        report["public_docs_consistent"] = True
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert "public_docs_consistent" in result.mismatched_fields

    def test_rejects_sandbox_only_tamper_recalculated_hash(self, workspace: Path) -> None:
        # sandbox_only is checked by safe_validate, so load fails before derived field check
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-sb", __version__)
        report["sandbox_only"] = False
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_paper_first_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-pf", __version__)
        report["paper_first"] = False
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_offline_safe_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-os", __version__)
        report["offline_safe"] = False
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_version_tamper_recalculated_hash(self, workspace: Path) -> None:
        # Version mismatch passes safe_validate but is caught by validate_artifact version_current check
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-ver", __version__)
        report["version"] = "0.0.0.fake"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.readiness_valid is False
        assert "version" in result.mismatched_fields
        assert any(c["name"] == "version_current" and not c["passed"] for c in result.checks)

    def test_rejects_hard_false_invariant_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-inv", __version__)
        report["broker_touched"] = True
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_unsafe_claim_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-claim", __version__)
        report["readiness_status"] = "safe to trade"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_forbidden_fragment_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-frag", __version__)
        report["checks"][0]["message"] = "path /Users/natan/dev"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_absolute_path_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-path", __version__)
        report["artifact_path"] = "/Users/natan/dev/.atlas/reports/x.json"
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        # Save to the ORIGINAL path, not the tampered absolute path
        original_path = workspace / ".atlas" / "research" / "ATLAS-DEMO" / "release_candidate_readiness_reports" / "rcr-tamper-path.json"
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        result = validate_release_candidate_readiness_artifact(original_path, workspace)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_mismatch_fields_safe_no_raw_values(self, workspace: Path) -> None:
        # Tamper with derived fields that safe_validate does NOT check
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-tamper-safe", __version__)
        report["readiness_score"] = 999
        report["readiness_status"] = "sandbox_release_candidate_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_readiness_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        # mismatched_fields should contain static field names, not raw values
        assert "readiness_score" in result.mismatched_fields
        assert "readiness_status" in result.mismatched_fields
        assert "blockers" in result.mismatched_fields
        # Ensure no raw tampered values leak into check messages
        derived_check = next(c for c in result.checks if c["name"] == "derived_readiness_match")
        assert "999" not in derived_check["message"]


# ---------------------------------------------------------------------------
# Load / find / list
# ---------------------------------------------------------------------------


class TestFindAndList:
    def test_find_by_id(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        report_id = result["release_candidate_readiness_report_id"]
        path = find_release_candidate_readiness_by_id(workspace, report_id)
        assert path is not None
        assert path.exists()

    def test_find_missing_returns_none(self, workspace: Path) -> None:
        assert find_release_candidate_readiness_by_id(workspace, "nonexistent") is None

    def test_list_returns_items(self, workspace: Path) -> None:
        create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        items = iter_release_candidate_readiness_artifacts(workspace)
        assert len(items) >= 1
        assert items[0]["safe_status"] == "safe"

    def test_list_filter_by_symbol(self, workspace: Path) -> None:
        create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        create_release_candidate_readiness(workspace, "OTHER", __version__)
        items = iter_release_candidate_readiness_artifacts(workspace, symbol="ATLAS-DEMO")
        assert all(i["symbol"] == "ATLAS-DEMO" for i in items)


# ---------------------------------------------------------------------------
# Replay / summary / doctor
# ---------------------------------------------------------------------------


class TestReplaySummaryDoctor:
    def test_replay(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        report_id = result["release_candidate_readiness_report_id"]
        path = find_release_candidate_readiness_by_id(workspace, report_id)
        replay = replay_release_candidate_readiness(path, workspace)
        assert replay["ok"] is True
        assert replay["status"] == "research_release_candidate_readiness_replayed"
        assert replay["sandbox_only"] is True
        assert replay["paper_first"] is True
        assert replay["offline_safe"] is True

    def test_summary(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        report_id = result["release_candidate_readiness_report_id"]
        path = find_release_candidate_readiness_by_id(workspace, report_id)
        summary = summarize_release_candidate_readiness(path, workspace)
        assert summary["ok"] is True
        assert summary["status"] == "research_release_candidate_readiness_summarized"
        assert summary["total_checks"] > 0

    def test_doctor_happy_path(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        report_id = result["release_candidate_readiness_report_id"]
        path = find_release_candidate_readiness_by_id(workspace, report_id)
        doctor = doctor_release_candidate_readiness(path, workspace)
        assert doctor["ok"] is True
        assert doctor["status"] == "research_release_candidate_readiness_doctored"
        # In a fresh tmp_path, required files are missing so the report is blocked.
        assert doctor["valid"] is False
        assert doctor["structurally_valid"] is True
        assert doctor["readiness_valid"] is False


# ---------------------------------------------------------------------------
# Missing docs produce blocked status
# ---------------------------------------------------------------------------


class TestMissingDocsBlocked:
    def test_missing_readme_produces_blocked(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-missing", __version__)
        readme_check = next((c for c in report["checks"] if c["name"] == "doc_present:README.md"), None)
        assert readme_check is not None
        assert readme_check["passed"] is False

    def test_missing_release_note_produces_blocked(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-missing2", __version__)
        note_check = next((c for c in report["checks"] if c["name"] == "release_note_present"), None)
        assert note_check is not None
        assert note_check["passed"] is False

    def test_release_note_uses_v_prefix(self, workspace: Path) -> None:
        # Regression test: release note path must use v-prefix
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-vprefix", __version__)
        note_check = next((c for c in report["checks"] if c["name"] == "release_note_present"), None)
        assert note_check is not None
        assert "v" + __version__ + ".md" in note_check["message"]


# ---------------------------------------------------------------------------
# No raw invalid fields / no absolute paths
# ---------------------------------------------------------------------------


class TestOutputSafety:
    def test_json_output_no_absolute_paths(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        json_str = json.dumps(result)
        assert "/Users/" not in json_str
        assert "/private/var/" not in json_str

    def test_artifact_path_is_relative(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-rel", __version__)
        artifact_path = report["artifact_path"]
        assert not artifact_path.startswith("/")
        assert ".atlas" in artifact_path

    def test_no_secrets_in_output(self, workspace: Path) -> None:
        result = create_release_candidate_readiness(workspace, "ATLAS-DEMO", __version__)
        json_str = json.dumps(result)
        assert "sk-" not in json_str
        assert "API_KEY" not in json_str
        assert "Bearer" not in json_str


# ---------------------------------------------------------------------------
# Schema / contract version
# ---------------------------------------------------------------------------


class TestSchema:
    def test_schema_version_correct(self, workspace: Path) -> None:
        report = build_release_candidate_readiness_dict(workspace, "ATLAS-DEMO", "rcr-schema", __version__)
        assert report["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION
        assert report["contract_version"] == RELEASE_CANDIDATE_READINESS_VERSION
        assert report["artifact_type"] == "release_candidate_readiness_report"
