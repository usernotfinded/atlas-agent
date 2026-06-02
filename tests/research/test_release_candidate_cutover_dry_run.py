"""Tests for release candidate cutover dry run - Batch 10.2.

No execution code, no network calls, no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from atlas_agent import __version__
from atlas_agent.research.release_candidate_cutover import (
    RELEASE_CANDIDATE_CUTOVER_VERSION,
    RESEARCH_ARTIFACT_SCHEMA_VERSION,
    _compute_expected_cutover_core,
    _find_mismatched_derived_fields,
    _package_version_to_tag,
    build_release_candidate_cutover_dict,
    create_release_candidate_cutover_dry_run,
    doctor_release_candidate_cutover,
    find_release_candidate_cutover_by_id,
    iter_release_candidate_cutover_artifacts,
    load_release_candidate_cutover,
    release_candidate_cutover_sha256,
    safe_validate_release_candidate_cutover_data,
    summarize_release_candidate_cutover,
    validate_release_candidate_cutover_artifact,
    validate_target_version,
)
from atlas_agent.research.session import ResearchSessionError


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CURRENT_DEV_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)\.dev\d+$")
_CURRENT_RC_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)rc[1-9]\d*$")
_CURRENT_STABLE_RE = re.compile(r"^\d+\.\d+\.\d+(?:\.\d+)?$")


def _current_version_state(
    version: str = __version__,
) -> tuple[bool, bool, bool, tuple[str, str, str] | None]:
    dev_match = _CURRENT_DEV_RE.fullmatch(version)
    if dev_match is not None:
        return (
            True,
            False,
            False,
            (dev_match.group("major"), dev_match.group("minor"), dev_match.group("patch")),
        )

    rc_match = _CURRENT_RC_RE.fullmatch(version)
    if rc_match is not None:
        return (
            False,
            True,
            False,
            (rc_match.group("major"), rc_match.group("minor"), rc_match.group("patch")),
        )

    return False, False, bool(_CURRENT_STABLE_RE.fullmatch(version)), None


def _expected_dev_to_rc_transition(
    target_version: str,
    current_version: str = __version__,
) -> bool:
    current_is_dev, current_is_rc, _current_is_stable, current_tuple = _current_version_state(current_version)
    target = validate_target_version(target_version)
    return (
        target.target_version_valid
        and current_tuple is not None
        and current_tuple == target.target_tuple
        and (current_is_dev or current_is_rc)
    )


def _current_release_note_exists(current_version: str = __version__) -> bool:
    return (REPO_ROOT / "docs" / "releases" / f"{_package_version_to_tag(current_version)}.md").exists()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# Target version validation
# ---------------------------------------------------------------------------


class TestValidateTargetVersion:
    def test_accepts_v0_5_7_rc1(self) -> None:
        facts = validate_target_version("v0.5.7-rc1")
        assert facts.target_version_valid is True
        assert facts.target_is_rc is True
        assert facts.target_is_not_dev is True
        assert facts.target_is_not_final_release is True
        assert facts.target_tuple == ("0", "5", "7")
        assert facts.blockers == []

    def test_accepts_v1_2_3_rc1(self) -> None:
        facts = validate_target_version("v1.2.3-rc1")
        assert facts.target_version_valid is True
        assert facts.target_is_rc is True

    def test_accepts_v0_5_7_rc2(self) -> None:
        facts = validate_target_version("v0.5.7-rc2")
        assert facts.target_version_valid is True

    def test_rejects_missing_v_prefix(self) -> None:
        facts = validate_target_version("0.5.7-rc1")
        assert facts.target_version_valid is False
        assert facts.target_is_rc is False
        assert "invalid_target_version" in facts.blockers

    def test_rejects_dev_target(self) -> None:
        facts = validate_target_version("v0.5.7.dev49")
        assert facts.target_version_valid is False
        assert facts.target_is_not_dev is False
        assert "target_is_dev" in facts.blockers

    def test_rejects_final_release_target(self) -> None:
        facts = validate_target_version("v0.5.7")
        assert facts.target_version_valid is False
        assert facts.target_is_not_final_release is False
        assert "target_is_final_release" in facts.blockers

    def test_rejects_malformed_rc_target(self) -> None:
        facts = validate_target_version("v0.5.7-rc")
        assert facts.target_version_valid is False
        assert facts.target_is_rc is False

    def test_rejects_alpha_target(self) -> None:
        facts = validate_target_version("v0.5.7-alpha1")
        assert facts.target_version_valid is False

    def test_rejects_beta_target(self) -> None:
        facts = validate_target_version("v0.5.7-beta1")
        assert facts.target_version_valid is False

    def test_rejects_spaces(self) -> None:
        facts = validate_target_version("v0.5.7 rc1")
        assert facts.target_version_valid is False
        assert "invalid_target_version" in facts.blockers

    def test_rejects_shell_metacharacters(self) -> None:
        facts = validate_target_version("v0.5.7-rc1;rm -rf")
        assert facts.target_version_valid is False
        assert "invalid_target_version" in facts.blockers

    def test_rejects_absolute_paths(self) -> None:
        facts = validate_target_version("v0.5.7-rc1/Users/natan")
        assert facts.target_version_valid is False
        assert "invalid_target_version" in facts.blockers

    def test_rejects_secret_like_fragments(self) -> None:
        facts = validate_target_version("v0.5.7-rc1-sk-abc123")
        assert facts.target_version_valid is False
        assert "invalid_target_version" in facts.blockers

    def test_safe_invalid_output(self) -> None:
        facts = validate_target_version("bad-target")
        assert facts.output_target == "<invalid>"


# ---------------------------------------------------------------------------
# Creation / build
# ---------------------------------------------------------------------------


class TestCreate:
    def test_create_happy_path(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        assert result["ok"] is True
        assert result["status"] == "research_release_candidate_cutover_dry_run_created"
        assert result["target_version"] == "v0.5.7-rc1"
        assert result["current_version"] == __version__

    def test_create_invalid_target_blocked(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7.dev49")
        assert result["ok"] is False
        assert result["status"] == "research_release_candidate_cutover_dry_run_blocked"
        assert "target_is_dev" in result["blockers"]

    def test_artifact_persisted_for_valid_target(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        report_id = result["release_candidate_cutover_dry_run_id"]
        artifact_path = (
            workspace
            / ".atlas"
            / "research"
            / "release_candidate_cutover_dry_runs"
            / f"{report_id}__v0.5.7-rc1.json"
        )
        assert artifact_path.exists()

    def test_artifact_not_persisted_for_invalid_target(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "bad-target")
        report_id = result["release_candidate_cutover_dry_run_id"]
        # Should be empty because target was invalid
        assert report_id == ""
        assert not (workspace / ".atlas" / "research" / "release_candidate_cutover_dry_runs").exists()

    def test_cutover_score_range(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        assert 0 <= result["cutover_score"] <= 100

    def test_status_is_safe(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        assert result["cutover_status"] in ("rc_dry_run_ready", "rc_dry_run_blocked")

    def test_tag_push_publish_false(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        assert result["tag_executed"] is False
        assert result["push_executed"] is False
        assert result["publish_executed"] is False


# ---------------------------------------------------------------------------
# Safe validation
# ---------------------------------------------------------------------------


class TestSafeValidate:
    def test_passes_valid_artifact(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-001")
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == ""
        assert cleaned is not None

    def test_rejects_wrong_artifact_type(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-002")
        report["artifact_type"] = "wrong_type"
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == "wrong_artifact_type"

    def test_rejects_hard_false_true(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-003")
        report["broker_touched"] = True
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == "hard_false_invariant_violation"

    def test_rejects_unsafe_claim_in_data(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-004")
        report["cutover_status"] = "live trading ready"
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == "unsafe_claim_detected"

    def test_rejects_forbidden_fragment(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-005")
        report["blockers"] = ["path /Users/natan/dev"]
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == "forbidden_fragment_detected"

    def test_rejects_sandbox_only_false(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sb")
        report["sandbox_only"] = False
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == "sandbox_only_not_true"

    def test_rejects_paper_first_false(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-pf")
        report["paper_first"] = False
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == "paper_first_not_true"

    def test_rejects_offline_safe_false(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-off")
        report["offline_safe"] = False
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == "offline_safe_not_true"

    def test_rejects_dry_run_only_false(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-dry")
        report["dry_run_only"] = False
        cleaned, err = safe_validate_release_candidate_cutover_data(report, workspace)
        assert err == "dry_run_only_not_true"


# ---------------------------------------------------------------------------
# Derived field recomputation / tamper resistance
# ---------------------------------------------------------------------------


class TestDerivedFieldTamper:
    def _save_and_validate(self, workspace: Path, report: dict[str, Any]) -> Any:
        filename = f"{report['release_candidate_cutover_dry_run_id']}__{report['target_version']}.json"
        path = workspace / ".atlas" / "research" / "release_candidate_cutover_dry_runs" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return validate_release_candidate_cutover_artifact(path, workspace)

    def test_freshly_created_report_validates_structurally(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-fresh")
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        # Fresh tmp_path produces blocked report, but structurally valid
        assert result.structurally_valid is True
        assert result.cutover_valid is False
        assert result.mismatched_fields == []

    def test_rejects_cutover_score_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-cs")
        report["cutover_score"] = 999
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert "cutover_score" in result.mismatched_fields
        assert any(c["name"] == "derived_cutover_match" and not c["passed"] for c in result.checks)

    def test_rejects_cutover_status_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-st")
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert "cutover_status" in result.mismatched_fields
        assert "blockers" in result.mismatched_fields

    def test_rejects_target_version_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-tv")
        report["target_version"] = "v0.5.7-rc2"
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        # Keep original filename so path_target mismatch is detected
        filename = "rcc-tamper-tv__v0.5.7-rc1.json"
        path = workspace / ".atlas" / "research" / "release_candidate_cutover_dry_runs" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        result = validate_release_candidate_cutover_artifact(path, workspace)
        assert result.valid is False
        assert result.structurally_valid is False
        assert "target_version" in result.mismatched_fields

    def test_rejects_sandbox_only_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-sb")
        report["sandbox_only"] = False
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_paper_first_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-pf")
        report["paper_first"] = False
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_offline_safe_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-os")
        report["offline_safe"] = False
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_hard_false_invariant_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-inv")
        report["broker_touched"] = True
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_unsafe_claim_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-claim")
        report["cutover_status"] = "safe to trade"
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_rejects_forbidden_fragment_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-frag")
        report["blockers"] = ["path /Users/natan/dev"]
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert result.structurally_valid is False
        assert any(c["name"] == "artifact_loadable" and not c["passed"] for c in result.checks)

    def test_mismatch_fields_safe_no_raw_values(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-tamper-safe")
        report["cutover_score"] = 999
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        result = self._save_and_validate(workspace, report)
        assert result.valid is False
        assert "cutover_score" in result.mismatched_fields
        assert "cutover_status" in result.mismatched_fields
        assert "blockers" in result.mismatched_fields
        derived_check = next(c for c in result.checks if c["name"] == "derived_cutover_match")
        assert "999" not in derived_check["message"]


# ---------------------------------------------------------------------------
# Load / find / list
# ---------------------------------------------------------------------------


class TestFindAndList:
    def test_find_by_id(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        report_id = result["release_candidate_cutover_dry_run_id"]
        path = find_release_candidate_cutover_by_id(workspace, report_id)
        assert path is not None
        assert path.exists()

    def test_find_missing_returns_none(self, workspace: Path) -> None:
        assert find_release_candidate_cutover_by_id(workspace, "nonexistent") is None

    def test_list_returns_items(self, workspace: Path) -> None:
        create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        items = iter_release_candidate_cutover_artifacts(workspace)
        assert len(items) >= 1
        assert items[0]["safe_status"] == "safe"

    def test_list_invalid_item_marked(self, workspace: Path) -> None:
        bad_path = workspace / ".atlas" / "research" / "release_candidate_cutover_dry_runs" / "bad__invalid-target.json"
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_text('{"artifact_type": "bad"}', encoding="utf-8")
        items = iter_release_candidate_cutover_artifacts(workspace)
        invalid_items = [i for i in items if i["safe_status"] == "invalid"]
        assert len(invalid_items) >= 1


# ---------------------------------------------------------------------------
# Summary / doctor
# ---------------------------------------------------------------------------


class TestSummaryDoctor:
    def test_summary(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        report_id = result["release_candidate_cutover_dry_run_id"]
        path = find_release_candidate_cutover_by_id(workspace, report_id)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is True
        assert summary["status"] == "research_release_candidate_cutover_dry_run_summarized"
        assert summary["cutover_status"] in ("rc_dry_run_ready", "rc_dry_run_blocked")

    def test_doctor_blocked_report_reports_safe_blockers(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-doctor-blocked")
        assert report["cutover_status"] == "rc_dry_run_blocked"
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        filename = f"{report['release_candidate_cutover_dry_run_id']}__{report['target_version']}.json"
        path = workspace / ".atlas" / "research" / "release_candidate_cutover_dry_runs" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        doctor = doctor_release_candidate_cutover(path, workspace)
        assert doctor["valid"] is False
        assert doctor["structurally_valid"] is True
        assert doctor["cutover_valid"] is False
        assert doctor["cutover_status"] == "rc_dry_run_blocked"
        assert doctor["blockers"]


# ---------------------------------------------------------------------------
# Missing docs produce blocked status
# ---------------------------------------------------------------------------


class TestMissingDocsBlocked:
    def test_missing_release_note_produces_blocked(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-missing")
        assert report["release_note_present"] is False
        assert report["cutover_status"] == "rc_dry_run_blocked"
        assert "missing_release_note" in report["blockers"]

    def test_missing_quickstart_produces_blocked(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-missing2")
        assert report["readme_quickstart_verified"] is False
        assert "quickstart_verification_missing" in report["blockers"]


# ---------------------------------------------------------------------------
# Hard-false invariants
# ---------------------------------------------------------------------------


class TestHardFalseInvariants:
    def test_all_hard_false_invariants_are_false(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-inv")
        invariants = (
            "provider_call_allowed",
            "actual_provider_call_made",
            "provider_response_trusted",
            "mock_response_trusted",
            "trading_signal_generated",
            "approval_created",
            "pending_order_created",
            "broker_touched",
            "network_enabled",
            "credentials_loaded",
            "trust_upgrade_performed",
            "trust_decision_granted",
            "provider_execution_unlocked",
            "real_provider_response_imported",
            "live_trading_path_enabled",
            "broker_order_path_enabled",
        )
        for inv in invariants:
            assert report.get(inv) is False, f"Expected {inv} to be False"


# ---------------------------------------------------------------------------
# Output safety
# ---------------------------------------------------------------------------


class TestOutputSafety:
    def test_json_output_no_absolute_paths(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        json_str = json.dumps(result)
        assert "/Users/" not in json_str
        assert "/private/var/" not in json_str

    def test_no_secrets_in_output(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        json_str = json.dumps(result)
        assert "sk-" not in json_str
        assert "API_KEY" not in json_str
        assert "Bearer" not in json_str
        assert "SECRET" not in json_str
        assert "TOKEN" not in json_str
        assert "PASSWORD" not in json_str

    def test_no_forbidden_fragments_in_output(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7-rc1")
        json_str = json.dumps(result)
        assert "Authorization" not in json_str
        assert "APCA" not in json_str

    def test_no_raw_invalid_target_echoed(self, workspace: Path) -> None:
        result = create_release_candidate_cutover_dry_run(workspace, "v0.5.7.dev49")
        json_str = json.dumps(result)
        assert "v0.5.7.dev49" not in json_str
        assert result["target_version"] == "<invalid>"


# ---------------------------------------------------------------------------
# Schema / contract version
# ---------------------------------------------------------------------------


class TestSchema:
    def test_schema_version_correct(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-schema")
        assert report["schema_version"] == RESEARCH_ARTIFACT_SCHEMA_VERSION
        assert report["contract_version"] == RELEASE_CANDIDATE_CUTOVER_VERSION
        assert report["artifact_type"] == "release_candidate_cutover_dry_run"


# ---------------------------------------------------------------------------
# Real repo integration
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_real_repo_target_v0_5_7_rc1(self) -> None:
        report = build_release_candidate_cutover_dict(REPO_ROOT, "v0.5.7-rc1", "rcc-real")
        assert report["target_version_valid"] is True
        assert report["target_is_rc"] is True
        current_is_dev, current_is_rc, current_is_stable, _current_tuple = _current_version_state()
        assert sum((current_is_dev, current_is_rc, current_is_stable)) == 1
        assert report["current_version_is_dev"] is current_is_dev
        assert report["dev_to_rc_transition_valid"] is _expected_dev_to_rc_transition("v0.5.7-rc1")

    def test_real_repo_rc_state(self) -> None:
        report = build_release_candidate_cutover_dict(REPO_ROOT, "v0.5.7-rc1", "rcc-real-dev")
        current_is_dev, current_is_rc, current_is_stable, _current_tuple = _current_version_state()
        assert sum((current_is_dev, current_is_rc, current_is_stable)) == 1
        assert report["current_version_is_dev"] is current_is_dev
        assert report["dev_to_rc_transition_valid"] is _expected_dev_to_rc_transition("v0.5.7-rc1")
        assert report["release_note_present"] is _current_release_note_exists()
        if current_is_dev:
            assert "missing_release_note" in report["blockers"]
        else:
            assert report["release_note_present"] is True
        # Safety invariants should hold
        assert report["live_trading_disabled_by_default"] is True
        assert report["provider_execution_locked"] is True
        assert report["trust_blocked"] is True
        assert report["broker_order_path_disabled"] is True

    def test_synthetic_dev_to_rc_transition_valid(self) -> None:
        # Verify dev-to-RC transition logic still works with a dev current version
        report = build_release_candidate_cutover_dict(
            REPO_ROOT, "v0.5.7-rc1", "rcc-synthetic-dev",
            current_version="0.5.7.dev50"
        )
        assert report["target_version_valid"] is True
        assert report["current_version_is_dev"] is True
        assert report["dev_to_rc_transition_valid"] is True

    def test_synthetic_rc_to_rc_transition_valid(self) -> None:
        # Verify rc-to-same-rc transition logic still works with an rc current version
        report = build_release_candidate_cutover_dict(
            REPO_ROOT, "v0.5.7-rc1", "rcc-synthetic-rc",
            current_version="0.5.7rc1"
        )
        assert report["target_version_valid"] is True
        assert report["current_version_is_dev"] is False
        assert report["dev_to_rc_transition_valid"] is True

    def test_real_repo_release_note_state(self) -> None:
        report = build_release_candidate_cutover_dict(REPO_ROOT, "v0.5.7-rc1", "rcc-real-note")
        current_is_dev, _current_is_rc, _current_is_stable, _current_tuple = _current_version_state()
        assert report["release_note_present"] is _current_release_note_exists()
        if current_is_dev:
            assert "missing_release_note" in report["blockers"]
        else:
            assert report["release_note_present"] is True

    def test_historical_stable_release_note_present(self) -> None:
        # Historical stable v0.5.7 release note should still exist
        from atlas_agent.research.release_candidate_cutover import _file_exists
        assert _file_exists(REPO_ROOT, "docs/releases/v0.5.7.md") is True

    def test_real_repo_readiness_available(self) -> None:
        report = build_release_candidate_cutover_dict(REPO_ROOT, "v0.5.7-rc1", "rcc-real-ready")
        assert report["release_candidate_readiness_available"] is True

    def test_real_repo_checklist_present(self) -> None:
        report = build_release_candidate_cutover_dict(REPO_ROOT, "v0.5.7-rc1", "rcc-real-check")
        assert report["release_checklist_present"] is True

    def test_real_repo_safety_invariants(self) -> None:
        report = build_release_candidate_cutover_dict(REPO_ROOT, "v0.5.7-rc1", "rcc-real-safe")
        assert report["live_trading_disabled_by_default"] is True
        assert report["provider_execution_locked"] is True
        assert report["trust_blocked"] is True
        assert report["broker_order_path_disabled"] is True


# ---------------------------------------------------------------------------
# Batch 10.2 regression — summary/list tamper resistance
# ---------------------------------------------------------------------------


class TestSummaryListTamperResistance:
    def _save_tampered(self, workspace: Path, report: dict[str, Any]) -> Path:
        filename = f"{report['release_candidate_cutover_dry_run_id']}__{report['target_version']}.json"
        path = workspace / ".atlas" / "research" / "release_candidate_cutover_dry_runs" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def test_summary_rejects_cutover_status_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-status")
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is False
        assert summary.get("valid") is False
        assert summary.get("safe_status") == "tampered"
        assert summary.get("reason") == "derived_cutover_mismatch"

    def test_summary_rejects_cutover_score_tamper_recalculated_hash(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-score")
        report["cutover_score"] = 100
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is False
        assert summary.get("valid") is False
        assert summary.get("safe_status") == "tampered"
        assert summary.get("reason") == "derived_cutover_mismatch"

    def test_summary_does_not_expose_tampered_cutover_status(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-no-status")
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["cutover_status"] == ""
        assert summary["ok"] is False

    def test_summary_does_not_expose_tampered_cutover_score(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-no-score")
        report["cutover_score"] = 100
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["cutover_score"] == 0
        assert summary["ok"] is False

    def test_summary_returns_derived_cutover_mismatch_reason(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-reason")
        report["cutover_status"] = "rc_dry_run_ready"
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary.get("reason") == "derived_cutover_mismatch"

    def test_list_rejects_tampered_artifact(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-list-tamper")
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        self._save_tampered(workspace, report)
        items = iter_release_candidate_cutover_artifacts(workspace)
        tampered_items = [i for i in items if i.get("release_candidate_cutover_dry_run_id") == "rcc-list-tamper"]
        assert len(tampered_items) == 1
        assert tampered_items[0]["safe_status"] == "tampered"
        assert tampered_items[0]["safe_status_reason"] == "derived_cutover_mismatch"

    def test_list_does_not_expose_tampered_cutover_status(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-list-no-status")
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        self._save_tampered(workspace, report)
        items = iter_release_candidate_cutover_artifacts(workspace)
        tampered_items = [i for i in items if i.get("release_candidate_cutover_dry_run_id") == "rcc-list-no-status"]
        assert len(tampered_items) == 1
        assert tampered_items[0]["cutover_status"] == ""

    def test_list_does_not_expose_tampered_cutover_score(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-list-no-score")
        report["cutover_score"] = 100
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        self._save_tampered(workspace, report)
        items = iter_release_candidate_cutover_artifacts(workspace)
        tampered_items = [i for i in items if i.get("release_candidate_cutover_dry_run_id") == "rcc-list-no-score"]
        assert len(tampered_items) == 1
        assert tampered_items[0]["cutover_score"] == 0

    def test_list_does_not_use_replay_mode_validation(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-list-no-replay")
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        self._save_tampered(workspace, report)
        items = iter_release_candidate_cutover_artifacts(workspace)
        tampered_items = [i for i in items if i.get("release_candidate_cutover_dry_run_id") == "rcc-list-no-replay"]
        assert len(tampered_items) == 1
        assert tampered_items[0]["safe_status"] == "tampered"

    def test_validate_and_summary_agree_on_tampered(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-agree-sum")
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        validate_result = validate_release_candidate_cutover_artifact(path, workspace)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert validate_result.structurally_valid is False
        assert summary["ok"] is False
        assert summary.get("valid") is False

    def test_validate_and_list_agree_on_tampered(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-agree-list")
        report["cutover_status"] = "rc_dry_run_ready"
        report["blockers"] = []
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        validate_result = validate_release_candidate_cutover_artifact(path, workspace)
        items = iter_release_candidate_cutover_artifacts(workspace)
        list_item = next((i for i in items if i.get("release_candidate_cutover_dry_run_id") == "rcc-agree-list"), None)
        assert validate_result.structurally_valid is False
        assert list_item is not None
        assert list_item["safe_status"] == "tampered"

    def test_summary_rejects_blockers_tamper(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-blockers")
        report["blockers"] = ["fake_blocker"]
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is False
        assert summary.get("reason") == "derived_cutover_mismatch"
        assert summary["blockers"] == []

    def test_summary_rejects_target_version_tamper(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-tv")
        report["target_version"] = "v0.5.7-rc2"
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        filename = "rcc-sum-tv__v0.5.7-rc1.json"
        path = workspace / ".atlas" / "research" / "release_candidate_cutover_dry_runs" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is False
        assert summary.get("valid") is False

    def test_summary_rejects_target_version_valid_tamper(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-tvv")
        report["target_version_valid"] = False
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is False
        assert summary.get("reason") == "derived_cutover_mismatch"

    def test_summary_rejects_dry_run_only_false_tamper(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-dry")
        report["dry_run_only"] = False
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is False
        assert summary.get("safe_status") == "invalid"
        assert summary.get("reason") == "dry_run_only_not_true"

    def test_summary_rejects_sandbox_only_false_tamper(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-sb")
        report["sandbox_only"] = False
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is False
        assert summary.get("safe_status") == "invalid"
        assert summary.get("reason") == "sandbox_only_not_true"

    def test_summary_rejects_hard_false_invariant_tamper(self, workspace: Path) -> None:
        report = build_release_candidate_cutover_dict(workspace, "v0.5.7-rc1", "rcc-sum-inv")
        report["broker_touched"] = True
        report["artifact_hash"] = release_candidate_cutover_sha256(report)
        path = self._save_tampered(workspace, report)
        summary = summarize_release_candidate_cutover(path, workspace)
        assert summary["ok"] is False
        assert summary.get("safe_status") == "invalid"
        assert summary.get("reason") == "hard_false_invariant_violation"
