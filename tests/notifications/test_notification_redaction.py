"""Tests for notification redaction."""
from __future__ import annotations

from atlas_agent.notifications.models import NotificationPayload, NotificationResult, NotificationTransport
from atlas_agent.notifications.redaction import (
    redact_text,
    redact_payload,
    redact_result,
    preview_payload,
)


def test_redact_text_leaves_plain_text() -> None:
    assert redact_text("Hello world") == "Hello world"


def test_redact_text_masks_slack_webhook() -> None:
    url = "https://hooks.slack.com/services/T00/B00/XXXXXXXX"
    assert "[REDACTED]" in redact_text(url)
    assert "hooks.slack.com" not in redact_text(url)


def test_redact_text_masks_api_key() -> None:
    text = "MY_API_KEY=secret123"
    result = redact_text(text)
    assert "[REDACTED]" in result
    assert "secret123" not in result


def test_redact_text_masks_token() -> None:
    text = "SLACK_TOKEN=xoxb-1234567890-abc"
    result = redact_text(text)
    assert "[REDACTED]" in result
    assert "xoxb-1234567890-abc" not in result


def test_redact_payload_masks_message() -> None:
    p = NotificationPayload(
        title="Alert",
        message="Webhook: https://hooks.slack.com/services/T00/B00/XXXX",
    )
    redacted = redact_payload(p)
    assert "[REDACTED]" in redacted["message"]


def test_redact_result_masks_error_detail() -> None:
    r = NotificationResult(
        notification_id="n1",
        transport=NotificationTransport.slack,
        status="error",
        error_detail="Webhook: https://hooks.slack.com/services/T00/B00/XXXX failed",
    )
    redacted = redact_result(r)
    assert "[REDACTED]" in redacted["error_detail"]


def test_preview_payload_is_redacted() -> None:
    p = NotificationPayload(
        title="Alert",
        message="See https://hooks.slack.com/services/T00/B00/XXXX",
    )
    preview = preview_payload(p)
    assert "[REDACTED]" in preview
    assert "Alert" in preview
