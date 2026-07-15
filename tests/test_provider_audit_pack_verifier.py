# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_provider_audit_pack_verifier.py
# PURPOSE: Verifies provider audit pack verifier behavior and regression
#         expectations.
# DEPS:    json, os, stat, sys, pathlib, pytest, additional local modules.
# ==============================================================================

# --- IMPORTS ---

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from atlas_agent.providers.provider_audit_pack import (
    AUDIT_PACK_FILES,
    AuditPackVerificationError,
    ProviderAuditPackIOError,
    _CLOSED_SAFETY_SUMMARY,
    verify_provider_audit_pack,
)

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

@pytest.fixture
def valid_audit_pack(tmp_path: Path) -> Path:
    pack_dir = tmp_path / "valid_pack"
    pack_dir.mkdir()
    
    # We must provide valid dummy data that passes all internal verifications.
    # Actually, the simplest is to invoke create_provider_audit_pack itself to get a valid one.
    from atlas_agent.providers.provider_audit_pack import create_provider_audit_pack
    
    # We need to run it in a way that generates a valid pack.
    # The preflight chain takes provider/model/purpose.
    # We can use deterministic/deterministic/test.
    
    res = create_provider_audit_pack(
        provider_id="deterministic",
        model_id="deterministic",
        purpose="test",
        max_context_chars=1000,
        output_dir=pack_dir,
    )
    assert res["valid"] is True
    
    return pack_dir

def test_valid_audit_pack_verifies(valid_audit_pack: Path):
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is True
    assert result["accepted_for_external_review"] is True
    assert not result["findings"]

def test_missing_required_file(valid_audit_pack: Path):
    (valid_audit_pack / "call-plan.json").unlink()
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert result["accepted_for_external_review"] is False
    assert "missing required files: call-plan.json" in result["findings"]

def test_extra_script_file_fails(valid_audit_pack: Path):
    (valid_audit_pack / "extra.sh").write_text("echo hello")
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert any("script/executable extension found: extra.sh" in f for f in result["findings"])

def test_executable_permission_file_fails(valid_audit_pack: Path):
    if os.name == 'nt':
        pytest.skip("chmod not supported on Windows")
    f = valid_audit_pack / "plain.txt"
    f.write_text("text")
    f.chmod(f.stat().st_mode | stat.S_IXUSR)
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert any("executable permission bit set: plain.txt" in f for f in result["findings"])

def test_absolute_path_fails(valid_audit_pack: Path):
    (valid_audit_pack / "bad.txt").write_text("/Users/test/file", encoding="utf-8")
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert any("absolute path found in bad.txt" in f for f in result["findings"])

def test_secret_like_value_fails(valid_audit_pack: Path):
    (valid_audit_pack / "bad2.txt").write_text("sk-ant-1234", encoding="utf-8")
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert any("secret-like value found in bad2.txt" in f for f in result["findings"])

def test_raw_payload_field_fails(valid_audit_pack: Path):
    (valid_audit_pack / "bad3.txt").write_text('raw_prompt: hello', encoding="utf-8")
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert any("raw payload body found in bad3.txt" in f for f in result["findings"])

def test_symlinked_required_file_fails(valid_audit_pack: Path):
    if os.name == 'nt':
        pytest.skip("symlinks may require admin on Windows")
    target = valid_audit_pack.parent / "real.json"
    target.write_text("{}", encoding="utf-8")
    (valid_audit_pack / "call-plan.json").unlink()
    (valid_audit_pack / "call-plan.json").symlink_to(target)
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert any("required file is a symlink: call-plan.json" in f for f in result["findings"])

def test_invalid_call_plan_fails(valid_audit_pack: Path):
    (valid_audit_pack / "call-plan.json").write_text("invalid json", encoding="utf-8")
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert "call-plan.json is invalid" in result["findings"]

def test_manifest_invalid_fails(valid_audit_pack: Path):
    manifest = json.loads((valid_audit_pack / "audit-pack-manifest.json").read_text())
    manifest["valid"] = False
    (valid_audit_pack / "audit-pack-manifest.json").write_text(json.dumps(manifest))
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert "audit-pack-manifest is not valid" in result["findings"]

def test_manifest_safety_not_closed_fails(valid_audit_pack: Path):
    manifest = json.loads((valid_audit_pack / "audit-pack-manifest.json").read_text())
    manifest["safety_summary"]["network_used"] = True
    (valid_audit_pack / "audit-pack-manifest.json").write_text(json.dumps(manifest))
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert "audit-pack-manifest safety_summary is not closed" in result["findings"]

def test_evidence_report_missing_notes_fails(valid_audit_pack: Path):
    (valid_audit_pack / "evidence-report.md").write_text("just some text", encoding="utf-8")
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert "evidence-report.md missing reviewer/non-authorizing notes" in result["findings"]

def test_no_provider_sdk_imports():
    from atlas_agent.providers.provider_audit_pack import verify_provider_audit_pack
    assert "openai" not in sys.modules
    assert "anthropic" not in sys.modules

def test_cli_verify_audit_pack_succeeds(valid_audit_pack: Path):
    import subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    res = subprocess.run(
        ["python3.11", "-m", "atlas_agent.cli", "providers", "verify-audit-pack", str(valid_audit_pack)],
        env=env, capture_output=True, text=True
    )
    assert res.returncode == 0
    assert "Provider audit pack is valid and accepted for external review" in res.stdout

def test_json_mode_returns_accepted(valid_audit_pack: Path):
    import subprocess
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    res = subprocess.run(
        ["python3.11", "-m", "atlas_agent.cli", "providers", "verify-audit-pack", "--json", str(valid_audit_pack)],
        env=env, capture_output=True, text=True
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["accepted_for_external_review"] is True

def test_manifest_stage_false_fails(valid_audit_pack: Path):
    manifest = json.loads((valid_audit_pack / "audit-pack-manifest.json").read_text())
    manifest["stages"]["some_stage"] = False
    (valid_audit_pack / "audit-pack-manifest.json").write_text(json.dumps(manifest))
    from atlas_agent.providers.provider_audit_pack import verify_provider_audit_pack
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert "audit-pack-manifest has false stages" in result["findings"]

def test_unsafe_call_plan_fails(valid_audit_pack: Path):
    plan = json.loads((valid_audit_pack / "call-plan.json").read_text())
    plan["safety_flags"]["network_enabled"] = True
    (valid_audit_pack / "call-plan.json").write_text(json.dumps(plan))
    from atlas_agent.providers.provider_audit_pack import verify_provider_audit_pack
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert "call-plan.json is invalid" in result["findings"]

def test_malformed_evidence_summary(valid_audit_pack: Path):
    (valid_audit_pack / "evidence-summary.json").write_text("not json")
    from atlas_agent.providers.provider_audit_pack import verify_provider_audit_pack
    result = verify_provider_audit_pack(valid_audit_pack)
    assert result["valid"] is False
    assert "evidence-summary.json is malformed" in result["findings"]
