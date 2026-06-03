"""Tests for provider evidence registry and audit index."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atlas_agent.providers.provider_evidence_index import (
    EvidenceIndexError,
    build_provider_evidence_index,
    inspect_provider_evidence_index,
)
from atlas_agent.providers.provider_preflight import generate_call_plan_artifact


def test_build_empty_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    idx = build_provider_evidence_index(Path("."))
    assert idx["summary"]["total_files_seen"] == 0
    assert len(idx["artifacts"]) == 0


def test_build_with_call_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 2. build index with generated call-plan recognizes provider_call_plan
    # 3. valid call-plan is marked valid
    # 8. index uses relative paths only
    # 9. index contains SHA-256 hashes
    cp = generate_call_plan_artifact(provider_id="openrouter", model_id="openrouter/auto", purpose="test", max_context_chars=4000)
    cp_path = tmp_path / "plan.json"
    cp_path.write_text(json.dumps(cp))

    idx = build_provider_evidence_index(tmp_path)
    assert idx["summary"]["total_files_seen"] == 1
    assert idx["summary"]["recognized_artifacts"] == 1
    assert idx["summary"]["valid_artifacts"] == 1

    art = idx["artifacts"][0]
    assert art["artifact_type"] == "provider_call_plan"
    assert art["valid"] is True
    assert art["relative_path"] == "plan.json"
    assert "sha256" in art
    assert art["recognized"] is True


def test_unsafe_call_plan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 4. unsafe call-plan is marked invalid
    cp = generate_call_plan_artifact(provider_id="openrouter", model_id="openrouter/auto", purpose="test", max_context_chars=4000)
    cp["safety_flags"]["provider_enabled"] = True
    cp_path = tmp_path / "unsafe.json"
    cp_path.write_text(json.dumps(cp))

    idx = build_provider_evidence_index(tmp_path)
    assert idx["summary"]["valid_artifacts"] == 0
    assert idx["summary"]["invalid_artifacts"] == 1
    assert idx["artifacts"][0]["valid"] is False


def test_malformed_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 5. malformed JSON file is counted as malformed_json
    p = tmp_path / "bad.json"
    p.write_text("{bad_json")

    idx = build_provider_evidence_index(tmp_path)
    assert idx["summary"]["malformed_json_files"] == 1
    assert idx["artifacts"][0]["artifact_type"] == "malformed_json"


def test_unknown_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 6. unknown JSON artifact is counted as unknown_json_artifact
    p = tmp_path / "unknown.json"
    p.write_text('{"hello": "world"}')

    idx = build_provider_evidence_index(tmp_path)
    assert idx["summary"]["unknown_json_artifacts"] == 1
    assert idx["artifacts"][0]["artifact_type"] == "unknown_json_artifact"


def test_non_json_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 7. non-JSON file is counted as non_json_file
    p = tmp_path / "text.txt"
    p.write_text("Hello World")

    idx = build_provider_evidence_index(tmp_path)
    assert idx["summary"]["non_json_files"] == 1
    assert idx["artifacts"][0]["artifact_type"] == "non_json_file"


def test_secret_detection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 10. secret-looking artifact value is detected but not copied into findings
    p = tmp_path / "secret.json"
    p.write_text(json.dumps({"some_key": "api_key_12345"}))

    idx = build_provider_evidence_index(tmp_path)
    assert idx["artifacts"][0]["valid"] is False
    assert "Artifact contains secret-like values" in idx["artifacts"][0]["validation_errors"][0]
    
    idx_str = json.dumps(idx)
    assert "api_key_12345" not in idx_str


def test_absolute_path_detection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 11. absolute path artifact value is detected
    p = tmp_path / "abs.json"
    p.write_text(json.dumps({"path": "/etc/passwd"}))

    idx = build_provider_evidence_index(tmp_path)
    assert idx["artifacts"][0]["valid"] is False
    assert "Artifact contains secret-like values or absolute paths" in idx["artifacts"][0]["validation_errors"][0]


def test_inspect_valid_index(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 12. inspect valid index succeeds
    idx = build_provider_evidence_index(Path("."))
    p = tmp_path / "index.json"
    p.write_text(json.dumps(idx))

    res = inspect_provider_evidence_index(p)
    assert res["artifact_type"] == "provider_evidence_index"


def test_inspect_malformed_index(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 13. inspect malformed index fails
    p = tmp_path / "bad.json"
    p.write_text("{")
    
    with pytest.raises(EvidenceIndexError):
        inspect_provider_evidence_index(p)


def test_cli_build(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 14. CLI build succeeds
    out_file = tmp_path / "index.json"
    cmd = [
        sys.executable,
        "-m",
        "atlas_agent.cli",
        "providers",
        "evidence-index",
        "build",
        "--root",
        str(tmp_path),
        "--output",
        str(out_file),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0
    assert out_file.exists()


def test_cli_inspect(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 15. CLI inspect succeeds
    idx = build_provider_evidence_index(Path("."))
    p = tmp_path / "index.json"
    p.write_text(json.dumps(idx))

    cmd = [
        sys.executable,
        "-m",
        "atlas_agent.cli",
        "providers",
        "evidence-index",
        "inspect",
        str(p),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 0


def test_cli_build_unsafe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 16. CLI build with unsafe artifact reports finding
    cp = generate_call_plan_artifact(provider_id="openrouter", model_id="openrouter/auto", purpose="test", max_context_chars=4000)
    cp["safety_flags"]["provider_enabled"] = True
    (tmp_path / "unsafe.json").write_text(json.dumps(cp))

    out_file = tmp_path / "index.json"
    cmd = [
        sys.executable,
        "-m",
        "atlas_agent.cli",
        "providers",
        "evidence-index",
        "build",
        "--root",
        str(tmp_path),
        "--output",
        str(out_file),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode == 1
    assert "contains invalid artifacts" in res.stdout


def test_fake_api_key_exclusion(monkeypatch, tmp_path):
    # 17. fake API key env values do not appear in index output
    monkeypatch.setenv("ATLAS_OPENROUTER_API_KEY", "sk-fake-key-12345")
    
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "secret.json"
    p.write_text(json.dumps({"some_key": "sk-fake-key-12345"}))

    out_file = tmp_path / "index.json"
    build_provider_evidence_index(Path("."), out_file)
    
    idx_str = out_file.read_text()
    assert "sk-fake-key" not in idx_str


def test_no_sdk_imports():
    # 18. no provider SDK/network imports
    import sys
    import atlas_agent.providers.provider_evidence_index
    assert "openai" not in sys.modules
    assert "requests" not in sys.modules


def test_symlink_skipped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "actual.json"
    p.write_text('{"artifact_type": "unknown"}')
    link = tmp_path / "link.json"
    link.symlink_to(p)
    
    idx = build_provider_evidence_index(Path("."))
    
    assert idx["summary"]["symlinks_skipped"] == 1
    # One normal file, one symlink
    assert len(idx["artifacts"]) == 2
    types = [a["artifact_type"] for a in idx["artifacts"]]
    assert "symlink_skipped" in types


def test_too_large(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "huge.json"
    p.write_bytes(b"0" * 1_000_001)
    
    idx = build_provider_evidence_index(Path("."))
    assert idx["summary"]["too_large_files"] == 1
    assert idx["artifacts"][0]["artifact_type"] == "too_large"


def test_max_depth(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # create depth 13
    d = tmp_path
    for _ in range(13):
        d = d / "dir"
    d.mkdir(parents=True)
    (d / "file.json").write_text("{}")
    
    idx = build_provider_evidence_index(Path("."))
    # It should not find the file because it's beyond depth 12
    assert idx["summary"]["total_files_seen"] == 0


def test_max_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for i in range(5005):
        (tmp_path / f"{i}.txt").write_text("")
    
    idx = build_provider_evidence_index(Path("."))
    assert idx["summary"]["total_files_seen"] == 5000


def test_unreadable_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "unreadable.json"
    p.write_text("{}")
    
    def mock_read_bytes(self):
        raise PermissionError("Access denied")
        
    monkeypatch.setattr(Path, "read_bytes", mock_read_bytes)
    
    idx = build_provider_evidence_index(Path("."))
    assert idx["summary"]["unreadable_files"] == 1
    assert idx["artifacts"][0]["artifact_type"] == "unreadable_file"
    assert "Cannot read file contents" in idx["artifacts"][0]["validation_errors"][0]
