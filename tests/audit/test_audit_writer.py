from __future__ import annotations

from pathlib import Path
from atlas_agent.audit.writer import AuditWriter
from atlas_agent.audit.verify import verify_audit_log


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
