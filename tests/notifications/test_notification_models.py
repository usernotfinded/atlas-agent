"""Tests for notification models."""
from __future__ import annotations

import json

from atlas_agent.notifications.models import (
    NotificationConfig,
    NotificationPayload,
    NotificationResult,
    NotificationSeverity,
    NotificationTransport,
)


def test_notification_payload_defaults() -> None:
    p = NotificationPayload(title="Test", message="Hello")
    assert p.severity == NotificationSeverity.info
    assert p.title == "Test"
    assert p.message == "Hello"
    assert p.source == "atlas-agent"
    assert p.notification_id
    assert p.created_at
    assert "not a trading instruction" in p.disclaimer


def test_notification_payload_serialization() -> None:
    p = NotificationPayload(
        severity=NotificationSeverity.critical,
        title="Alert",
        message="Something happened",
        source="test",
        source_command="test_cmd",
        run_id="r1",
        mode="paper",
    )
    data = p.model_dump(mode="json")
    assert data["severity"] == "critical"
    assert data["title"] == "Alert"
    assert data["message"] == "Something happened"
    assert data["run_id"] == "r1"


def test_notification_result_fields() -> None:
    r = NotificationResult(
        notification_id="n1",
        transport=NotificationTransport.dry_run,
        status="dry_run",
        message="OK",
    )
    assert r.notification_id == "n1"
    assert r.transport == NotificationTransport.dry_run
    assert r.status == "dry_run"
    assert r.timestamp


def test_notification_config_safe_defaults() -> None:
    c = NotificationConfig()
    assert c.enabled is False
    assert c.transport == NotificationTransport.disabled
    assert c.slack_webhook_url_env == "SLACK_WEBHOOK_URL"
    assert c.slack_webhook_url == ""


def test_notification_severity_enum() -> None:
    assert NotificationSeverity.info.value == "info"
    assert NotificationSeverity.warning.value == "warning"
    assert NotificationSeverity.error.value == "error"
    assert NotificationSeverity.critical.value == "critical"


def test_notification_transport_enum() -> None:
    assert NotificationTransport.disabled.value == "disabled"
    assert NotificationTransport.dry_run.value == "dry_run"
    assert NotificationTransport.slack.value == "slack"


def test_notification_payload_json_roundtrip() -> None:
    p = NotificationPayload(title="T", message="M")
    text = p.model_dump_json()
    restored = NotificationPayload.model_validate_json(text)
    assert restored.title == "T"
    assert restored.message == "M"


def test_notification_result_json_roundtrip() -> None:
    r = NotificationResult(
        notification_id="n1",
        transport=NotificationTransport.slack,
        status="failed",
        error_code="slack_webhook_missing",
    )
    text = r.model_dump_json()
    restored = NotificationResult.model_validate_json(text)
    assert restored.error_code == "slack_webhook_missing"
