from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from atlas_agent.audit import AuditWriter
from atlas_agent.audit.redaction import redact_payload, refresh_redaction_secrets
from atlas_agent.events import EventLogger, generate_run_id


class PayloadModel(BaseModel):
    note: str
    created_at: datetime


@dataclass
class PayloadData:
    api_token: str
    nested: PayloadModel


def test_shared_redaction_engine_handles_structured_payloads(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_TEST_API_KEY", "env-secret-value")
    refresh_redaction_secrets()

    payload = PayloadData(
        api_token="raw-token",
        nested=PayloadModel(
            note="contains env-secret-value and Authorization: abcdefghijklmnopqrstuvwxyz123456",
            created_at=datetime(2026, 5, 16, tzinfo=UTC),
        ),
    )

    redacted = redact_payload(payload)

    assert redacted["api_token"] == "[REDACTED]"
    assert "env-secret-value" not in redacted["nested"]["note"]
    assert "Authorization: [REDACTED]" in redacted["nested"]["note"]
    assert redacted["nested"]["created_at"] == "2026-05-16T00:00:00+00:00"


def test_event_logger_and_audit_writer_share_redaction(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATLAS_TEST_API_KEY", "writer-secret-value")
    refresh_redaction_secrets()

    EventLogger(tmp_path / "events").write(
        "agent_started",
        run_id=generate_run_id(),
        command="atlas test",
        mode="paper",
        payload={"message": "writer-secret-value"},
    )
    AuditWriter(tmp_path / "audit" / "events.jsonl").write_event(
        "run_started",
        run_id="run_1",
        payload={"message": "writer-secret-value"},
    )

    serialized = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.jsonl"))
    assert "writer-secret-value" not in serialized
    assert "[REDACTED]" in serialized
