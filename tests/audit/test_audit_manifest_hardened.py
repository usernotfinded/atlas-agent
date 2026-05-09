from __future__ import annotations

import json
import pytest
from pathlib import Path
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.audit.verify import verify_run_manifest


def test_manifest_lifecycle(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    manifest_dir = tmp_path / "manifests"
    writer = AuditWriter(log_path, manifest_dir=manifest_dir)
    
    run_id = "run_1"
    writer.start_run(run_id)
    
    manifest_path = manifest_dir / f"{run_id}.json"
    assert manifest_path.exists()
    
    m1 = json.loads(manifest_path.read_text())
    assert m1["status"] == "running"
    assert m1["event_count"] == 0
    
    # Write events
    writer.write_event("run_started", run_id)
    writer.write_event("run_completed", run_id)
    
    writer.finish_run("completed", "Success")
    
    m2 = json.loads(manifest_path.read_text())
    assert m2["status"] == "completed"
    assert m2["event_count"] == 2
    assert m2["first_event_hash"] is not None
    assert m2["final_event_hash"] is not None
    assert m2["root_hash"] is not None
    assert m2["final_status"] == "Success"


def test_verify_manifest_detects_tail_deletion(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    manifest_dir = tmp_path / "manifests"
    writer = AuditWriter(log_path, manifest_dir=manifest_dir)
    
    run_id = "run_1"
    writer.start_run(run_id)
    writer.write_event("run_started", run_id)
    writer.write_event("provider_called", run_id)
    writer.write_event("run_completed", run_id)
    writer.finish_run("completed")
    
    manifest_path = manifest_dir / f"{run_id}.json"
    
    # Clean check
    assert verify_run_manifest(manifest_path).valid is True
    
    # Delete last event from log
    lines = log_path.read_text().splitlines()
    log_path.write_text("\n".join(lines[:-1]) + "\n")
    
    result = verify_run_manifest(manifest_path)
    assert result.valid is False
    assert any("Tail deletion detected" in e for e in result.errors)


def test_verify_manifest_detects_tampering(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    manifest_dir = tmp_path / "manifests"
    writer = AuditWriter(log_path, manifest_dir=manifest_dir)
    
    run_id = "run_1"
    writer.start_run(run_id)
    writer.write_event("run_started", run_id)
    writer.finish_run("completed")
    
    manifest_path = manifest_dir / f"{run_id}.json"
    
    # Tamper with manifest root hash
    m = json.loads(manifest_path.read_text())
    m["root_hash"] = "invalid"
    manifest_path.write_text(json.dumps(m))
    
    result = verify_run_manifest(manifest_path)
    assert result.valid is False
    assert "root hash mismatch" in result.errors[0]
