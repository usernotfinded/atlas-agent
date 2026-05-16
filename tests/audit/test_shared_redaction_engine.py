from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from atlas_agent.audit import AuditWriter
from atlas_agent.audit.redaction import redact_payload, refresh_redaction_secrets
from atlas_agent import redaction as shared_redaction
from atlas_agent.audit import redaction as audit_redaction
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


def test_audit_secret_markers_is_shared_reference() -> None:
    """Prove SECRET_MARKERS is the same object in both modules (single source of truth)."""
    assert audit_redaction.SECRET_MARKERS is shared_redaction.SECRET_MARKERS


def test_audit_secret_markers_reflects_shared_changes() -> None:
    """Prove changing the shared constant automatically affects the audit wrapper import."""
    # SECRET_MARKERS is a tuple; verify audit wrapper sees the same tuple contents.
    assert audit_redaction.SECRET_MARKERS == shared_redaction.SECRET_MARKERS
    # Spot-check expected markers to ensure no drift.
    expected_markers = {"KEY", "API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTHORIZATION", "AUTH", "BEARER", "COOKIE", "PRIVATE_KEY"}
    assert set(audit_redaction.SECRET_MARKERS) == expected_markers
    assert set(shared_redaction.SECRET_MARKERS) == expected_markers


def test_redaction_behavior_unchanged_after_cleanup() -> None:
    """Existing redaction behavior remains unchanged after SECRET_MARKERS single-source cleanup."""
    payload = {
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz123456",
        "password": "super_secret_password",
        "token": "ghp_abcdefghijklmnopqrstuvwxyz1234",
        "safe": "public data",
        "nested": {
            "secret": "hidden",
            "Authorization": "Bearer abc123",
        },
    }
    redacted = redact_payload(payload)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["safe"] == "public data"
    assert redacted["nested"]["secret"] == "[REDACTED]"
    assert redacted["nested"]["Authorization"] == "[REDACTED]"
