import json
import shutil
from pathlib import Path

from scripts.check_v0613_final_readiness_audit import check, main

MD_FILE = "docs/releases/v0.6.13-final-readiness-audit.md"
JSON_FILE = "docs/releases/v0.6.13-final-readiness-audit.json"


def test_checker_passes_on_real_repo():
    root = Path(".")
    result = check(root)
    assert result["valid"] is True, f"Errors: {result.get('errors')}"


def test_checker_main_json_flag(capsys):
    root = Path(".")
    exit_code = main(["--json", "--root", str(root)])
    assert exit_code == 0
    out, _ = capsys.readouterr()
    data = json.loads(out)
    assert data["valid"] is True


def test_json_audit_properties():
    root = Path(".")
    data = json.loads((root / JSON_FILE).read_text(encoding="utf-8"))
    
    assert data["artifact_type"] == "v0613_final_readiness_audit"
    assert data["schema_version"] == 1
    assert data["release_line"] == "v0.6.13"
    assert data["status"] == "planning_only"
    assert data["owner_authorization_required"] is True
    assert data["release_authorized"] is False
    assert data["cutover_allowed"] is False
    assert data["current_public_release"] == "v0.6.12"
    assert data["next_planned_release"] == "v0.6.13"
    assert data["source_version"] == "0.6.12"
    assert data["pypi_published"] is False
    assert data["v0613_tag_created"] is False
    assert data["v0613_github_release_created"] is False
    
    cands = data["candidates_covered"]
    for i in range(21, 33):
        assert f"CAND-0{i}" in cands


def test_unsafe_claim_fails(tmp_path):
    root = Path(".")
    shutil.copytree(root / "docs", tmp_path / "docs", dirs_exist_ok=True)
    shutil.copytree(root / "scripts", tmp_path / "scripts", dirs_exist_ok=True)
    shutil.copytree(root / "tests", tmp_path / "tests", dirs_exist_ok=True)
    
    md_path = tmp_path / MD_FILE
    md_path.write_text(md_path.read_text(encoding="utf-8") + "\n" * 100 + "This is a guaranteed profit.", encoding="utf-8")
    
    result = check(tmp_path)
    assert result["valid"] is False
    assert any("guaranteed profit" in e for e in result["errors"])


def test_missing_candidate_in_json_fails(tmp_path):
    root = Path(".")
    shutil.copytree(root / "docs", tmp_path / "docs", dirs_exist_ok=True)
    
    json_path = tmp_path / JSON_FILE
    data = json.loads(json_path.read_text(encoding="utf-8"))
    data["candidates_covered"].remove("CAND-025")
    json_path.write_text(json.dumps(data), encoding="utf-8")
    
    result = check(tmp_path)
    assert result["valid"] is False
    assert any("Missing CAND-025" in e for e in result["errors"])


def test_missing_preflight_reference_fails(tmp_path):
    root = Path(".")
    shutil.copytree(root / "docs", tmp_path / "docs", dirs_exist_ok=True)
    
    md_path = tmp_path / MD_FILE
    text = md_path.read_text(encoding="utf-8")
    text = text.replace("v0.6.13-release-cutover-preflight.json", "removed_ref")
    md_path.write_text(text, encoding="utf-8")
    
    result = check(tmp_path)
    assert result["valid"] is False
    assert any("Missing reference to" in e for e in result["errors"])

def test_checker_does_not_mutate_files(tmp_path):
    root = Path(".")
    shutil.copytree(root / "docs", tmp_path / "docs", dirs_exist_ok=True)
    
    md_path = tmp_path / MD_FILE
    before_stat = md_path.stat().st_mtime
    
    check(tmp_path)
    
    after_stat = md_path.stat().st_mtime
    assert before_stat == after_stat
