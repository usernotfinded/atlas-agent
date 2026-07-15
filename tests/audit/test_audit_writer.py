# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/audit/test_audit_writer.py
# PURPOSE: Verifies audit writer behavior and regression expectations.
# DEPS:    json, logging, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import logging
from pathlib import Path
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.audit.verify import verify_audit_log


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_writer_appends_and_chains_events(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    writer = AuditWriter(path)
    
    e1 = writer.write_event("run_started", "run_1")
    e2 = writer.write_event("provider_called", "run_1")
    
    assert e1.previous_hash is None
    assert e2.previous_hash == e1.event_hash
    
    # Verify file content
    lines = path.read_text().splitlines()
    assert len(lines) == 2


def test_writer_recovers_last_hash_on_init(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    writer1 = AuditWriter(path)
    e1 = writer1.write_event("run_started", "run_1")
    
    # New writer instance
    writer2 = AuditWriter(path)
    e2 = writer2.write_event("provider_called", "run_1")
    
    assert e2.previous_hash == e1.event_hash


def test_verify_audit_log_detects_tampering(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    writer = AuditWriter(path)
    writer.write_event("run_started", "run_1")
    writer.write_event("run_completed", "run_1")

    # Clean check
    assert verify_audit_log(path).valid is True

    # Tamper with file
    content = path.read_text()
    tampered = content.replace("run_completed", "run_failed")
    path.write_text(tampered)

    result = verify_audit_log(path)
    assert result.valid is False
    assert "Hash chain broken" in result.errors[0]


def test_recovery_warns_on_corrupt_tail(tmp_path: Path, caplog):
    path = tmp_path / "audit.jsonl"
    # Seed with a valid event then corrupt the tail
    writer1 = AuditWriter(path)
    writer1.write_event("run_started", "run_1")
    content = path.read_text()
    path.write_text(content + "this is not json\n")

    with caplog.at_level(logging.WARNING):
        writer2 = AuditWriter(path)
        writer2.write_event("provider_called", "run_1")

    assert any("recovery failed" in r.message.lower() for r in caplog.records)
    # Because recovery failed, the new event starts a fresh chain
    assert writer2.last_hash is not None
    lines = path.read_text().splitlines()
    last_event = json.loads(lines[-1])
    assert last_event["previous_hash"] is None


def test_manifest_includes_rolling_root(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    manifest_dir = tmp_path / "manifests"
    writer = AuditWriter(log_path, manifest_dir=manifest_dir)

    run_id = "run_1"
    writer.start_run(run_id)
    e1 = writer.write_event("run_started", run_id)
    e2 = writer.write_event("provider_called", run_id)
    writer.finish_run("completed")

    manifest_path = manifest_dir / f"{run_id}.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["event_hash_rolling_root"] is not None
    # The rolling root should change between events
    assert manifest["event_hash_rolling_root"] != e1.event_hash
    assert manifest["event_hash_rolling_root"] != e2.event_hash
