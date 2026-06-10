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


def test_verify_manifest_detects_interior_event_tampering(tmp_path: Path):
    from atlas_agent.audit.models import AuditEvent
    from atlas_agent.audit.chain import compute_event_hash

    log_path = tmp_path / "audit.jsonl"
    manifest_dir = tmp_path / "manifests"
    writer = AuditWriter(log_path, manifest_dir=manifest_dir)

    run_id = "run_1"
    writer.start_run(run_id)
    e1 = writer.write_event("run_started", run_id)
    e2 = writer.write_event("provider_called", run_id)
    e3 = writer.write_event("run_completed", run_id)
    writer.finish_run("completed")

    # Simulate an attacker replacing the interior event with a different
    # valid event while updating the next event's previous_hash to match.
    # first_event_hash and final_event_hash stay the same, but the
    # rolling root captures the interior change.
    alt = AuditEvent(
        event_type="tool_call_blocked",
        run_id=run_id,
        previous_hash=e1.event_hash,
        payload={"note": "injected"},
    )
    alt.event_hash = compute_event_hash(alt)

    # Patch e3 to chain from alt instead of e2
    e3_patched = AuditEvent(
        event_type=e3.event_type,
        run_id=run_id,
        previous_hash=alt.event_hash,
        payload=e3.payload,
    )
    e3_patched.event_hash = compute_event_hash(e3_patched)

    log_path.write_text(
        "\n".join([
            e1.model_dump_json(),
            alt.model_dump_json(),
            e3_patched.model_dump_json(),
        ]) + "\n"
    )

    manifest_path = manifest_dir / f"{run_id}.json"
    result = verify_run_manifest(manifest_path)
    assert result.valid is False
    assert any("rolling root mismatch" in e.lower() for e in result.errors)


def test_legacy_manifest_without_rolling_root_still_verifies(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    manifest_dir = tmp_path / "manifests"
    writer = AuditWriter(log_path, manifest_dir=manifest_dir)

    run_id = "run_1"
    writer.start_run(run_id)
    writer.write_event("run_started", run_id)
    writer.write_event("run_completed", run_id)
    writer.finish_run("completed")

    manifest_path = manifest_dir / f"{run_id}.json"
    m = json.loads(manifest_path.read_text())
    # Simulate legacy manifest created before rolling root existed
    del m["event_hash_rolling_root"]
    # Recompute root hash without the field for backward-compat
    from atlas_agent.audit.manifest import compute_root_hash
    from atlas_agent.audit.models import AuditManifest
    legacy_manifest = AuditManifest.model_validate(m)
    m["root_hash"] = compute_root_hash(legacy_manifest)
    manifest_path.write_text(json.dumps(m))

    result = verify_run_manifest(manifest_path)
    assert result.valid is True
