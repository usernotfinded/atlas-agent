import json
from pathlib import Path
import pytest

from atlas_agent.providers.provider_evidence_index import (
    generate_provider_evidence_report,
    export_provider_evidence_summary,
    EvidenceIndexError,
    _determine_finding_severity,
)


def create_mock_index(tmp_path: Path, artifacts=None, findings=None, safety_summary=None, valid=True, extra=None) -> Path:
    data = {
        "artifact_type": "provider_evidence_index",
        "schema_version": 1,
        "generated_at": "2026-06-03T00:00:00+00:00",
        "root": "/tmp/mock",
        "summary": {
            "total_files_seen": 1,
            "recognized_artifacts": 1,
            "valid_artifacts": 1 if valid else 0,
            "invalid_artifacts": 0 if valid else 1,
            "malformed_json_files": 0,
            "unknown_json_artifacts": 0,
            "non_json_files": 0,
            "too_large_files": 0,
            "symlink_skipped": 0,
        },
        "artifacts": artifacts or [],
        "findings": findings or [],
        "safety_summary": safety_summary or {
            "provider_call_made": False,
            "network_used": False,
            "credentials_loaded": False,
            "broker_touched": False,
            "live_trading_enabled": False,
            "pending_order_created": False,
            "order_approved": False,
        }
    }
    if extra:
        data.update(extra)
    
    p = tmp_path / "index.json"
    p.write_text(json.dumps(data))
    return p


def test_markdown_report_generated_from_valid_index(tmp_path: Path):
    index_path = create_mock_index(tmp_path)
    output_path = tmp_path / "report.md"
    result = generate_provider_evidence_report(index_path, output=output_path)
    
    assert result["is_valid"] is True
    assert output_path.exists()
    content = output_path.read_text()
    assert "# Provider Evidence Index Report" in content
    assert "## Summary" in content


def test_json_summary_generated_from_valid_index(tmp_path: Path):
    index_path = create_mock_index(tmp_path)
    output_path = tmp_path / "summary.json"
    result = export_provider_evidence_summary(index_path, output=output_path)
    
    assert result["valid"] is True
    assert output_path.exists()
    summary = json.loads(output_path.read_text())
    assert summary["artifact_type"] == "provider_evidence_index_summary"
    assert summary["source_index_sha256"]


def test_markdown_report_includes_summary_table_sections(tmp_path: Path):
    index_path = create_mock_index(tmp_path)
    md = generate_provider_evidence_report(index_path)["markdown"]
    assert "## Summary" in md
    assert "## Safety Summary" in md
    assert "## Artifact Type Distribution" in md
    assert "## Findings" in md
    assert "## Invalid or Unsafe Artifacts" in md
    assert "## Recognized Artifacts" in md


def test_markdown_report_includes_artifact_type_distribution(tmp_path: Path):
    artifacts = [{"artifact_type": "provider_call_plan", "valid": True, "recognized": True, "sha256": "abcdef123"}]
    index_path = create_mock_index(tmp_path, artifacts=artifacts)
    md = generate_provider_evidence_report(index_path)["markdown"]
    assert "provider_call_plan" in md
    assert "| provider_call_plan | 1 |" in md


def test_markdown_report_includes_reviewer_notes(tmp_path: Path):
    index_path = create_mock_index(tmp_path)
    md = generate_provider_evidence_report(index_path)["markdown"]
    assert "## Reviewer Notes" in md
    assert "It does not authorize provider execution." in md


def test_json_summary_includes_source_index_sha256(tmp_path: Path):
    index_path = create_mock_index(tmp_path)
    result = export_provider_evidence_summary(index_path)
    assert "source_index_sha256" in result
    assert len(result["source_index_sha256"]) == 64


def test_invalid_artifacts_produce_valid_false_in_summary(tmp_path: Path):
    findings = [{"validation_errors": ["Some error"], "artifact_type": "unknown_json_artifact"}]
    index_path = create_mock_index(tmp_path, findings=findings, valid=False)
    # The inspect function will return True for the index itself being structurally valid,
    # but let's actually make the safety flags open to trigger an invalid index.
    safety = {
        "provider_call_made": True,
        "network_used": False,
        "credentials_loaded": False,
        "broker_touched": False,
        "live_trading_enabled": False,
        "pending_order_created": False,
        "order_approved": False,
    }
    index_path = create_mock_index(tmp_path, findings=findings, safety_summary=safety, valid=False)
    
    result = export_provider_evidence_summary(index_path)
    assert result["valid"] is False


def test_malformed_index_fails(tmp_path: Path):
    index_path = tmp_path / "bad.json"
    index_path.write_text("{bad json")
    with pytest.raises(EvidenceIndexError):
        generate_provider_evidence_report(index_path)
    with pytest.raises(EvidenceIndexError):
        export_provider_evidence_summary(index_path)


def test_report_never_includes_secret_values_from_findings_artifacts(tmp_path: Path):
    # Mock finding with a secret
    findings = [{"validation_errors": ["Artifact contains secret-like values or absolute paths: Found password=12345"], "artifact_type": "provider_call_plan"}]
    artifacts = [{"artifact_type": "provider_call_plan", "valid": False, "validation_errors": ["Found API_KEY=secret_token"]}]
    index_path = create_mock_index(tmp_path, artifacts=artifacts, findings=findings, valid=False)
    
    md = generate_provider_evidence_report(index_path)["markdown"]
    assert "password=12345" not in md
    assert "API_KEY=secret_token" not in md
    assert "[REDACTED SECRET-LIKE VALUE" in md


def test_report_never_includes_absolute_paths(tmp_path: Path):
    findings = [{"validation_errors": ["Artifact contains absolute paths: /etc/passwd"], "artifact_type": "provider_call_plan"}]
    artifacts = [{"artifact_type": "provider_call_plan", "valid": False, "validation_errors": ["C:\\Windows\\System32 found"]}]
    index_path = create_mock_index(tmp_path, artifacts=artifacts, findings=findings, valid=False)
    
    md = generate_provider_evidence_report(index_path)["markdown"]
    assert "/etc/passwd" not in md
    assert "C:\\Windows\\System32" not in md
    assert "[REDACTED ABSOLUTE PATH" in md


def test_report_uses_relative_paths_only(tmp_path: Path):
    artifacts = [{"artifact_type": "provider_call_plan", "relative_path": "some/path.json", "valid": True, "recognized": True, "sha256": "abcdef12"}]
    index_path = create_mock_index(tmp_path, artifacts=artifacts)
    md = generate_provider_evidence_report(index_path)["markdown"]
    assert "some/path.json" in md


def test_severity_classification_works_for_secret_like_finding():
    assert _determine_finding_severity("unknown", "Contains API_KEY") == "critical"
    assert _determine_finding_severity("provider_call_plan", "credentials_loaded was true") == "critical"
    assert _determine_finding_severity("unknown", "absolute path detected") == "error"
    assert _determine_finding_severity("malformed_json", "Bad parse") == "error"
    assert _determine_finding_severity("unknown_json_artifact", "Did not recognize") == "warning"
    assert _determine_finding_severity("recognized_valid_artifact", "Parsed okay") == "info"

def test_no_provider_sdk_network_imports():
    import sys
    assert "openai" not in sys.modules
    assert "anthropic" not in sys.modules
    assert "requests" not in sys.modules

def test_fake_api_key_env_values_do_not_appear():
    findings = [{"validation_errors": ["Found API_KEY=xyz"], "artifact_type": "test"}]
    index_path = create_mock_index(Path("/tmp"), findings=findings)
    md = generate_provider_evidence_report(index_path)["markdown"]
    assert "xyz" not in md


def test_cli_evidence_index_report_succeeds(tmp_path: Path):
    from atlas_agent.cli import main
    index_path = create_mock_index(tmp_path)
    output_path = tmp_path / "report.md"
    try:
        main(["providers", "evidence-index", "report", str(index_path), "--output", str(output_path)])
    except SystemExit as e:
        assert e.code == 0
    assert output_path.exists()


def test_cli_evidence_index_export_summary_succeeds(tmp_path: Path):
    from atlas_agent.cli import main
    index_path = create_mock_index(tmp_path)
    output_path = tmp_path / "summary.json"
    try:
        main(["providers", "evidence-index", "export-summary", str(index_path), "--output", str(output_path)])
    except SystemExit as e:
        assert e.code == 0
    assert output_path.exists()


def test_cli_report_fails_on_malformed_index(tmp_path: Path):
    from atlas_agent.cli import main
    index_path = tmp_path / "bad.json"
    index_path.write_text("{bad json")
    output_path = tmp_path / "report.md"
    try:
        main(["providers", "evidence-index", "report", str(index_path), "--output", str(output_path)])
    except SystemExit as e:
        assert e.code == 2


def test_no_broker_execution_risk_safety_touched():
    import sys
    # Import our module and see what it brings in
    import atlas_agent.providers.provider_evidence_index
    # The module should not import any of the protected runtime paths for its logic.
    # While they might be in sys.modules if imported by other things in the test runner,
    # we can check its dir() for direct imports.
    mod = atlas_agent.providers.provider_evidence_index
    assert not hasattr(mod, "broker")
    assert not hasattr(mod, "execution")
    assert not hasattr(mod, "live_trading")
