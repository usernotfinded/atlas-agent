"""Notification payload and result models.

Safe, serializable models for notification payloads, severities,
transport modes, and delivery results. Contains no secrets.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class NotificationSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class NotificationTransport(str, Enum):
    disabled = "disabled"
    dry_run = "dry_run"
    slack = "slack"


class NotificationPayload(BaseModel):
    """Structured notification payload.

    Safe to serialize. No secrets. No trading instructions.
    """

    notification_id: str = Field(default_factory=lambda: str(uuid4()))
    severity: NotificationSeverity = NotificationSeverity.info
    title: str = ""
    message: str = ""
    source: str = "atlas-agent"
    source_command: str = ""
    run_id: str = ""
    mode: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    disclaimer: str = (
        "This notification is informational only. It is not a trading instruction, "
        "not financial advice, and does not trigger provider execution, broker execution, "
        "skill activation, or learning execution."
    )


class NotificationResult(BaseModel):
    """Result of a notification delivery attempt.

    Structured, auditable, safe to log.
    """

    notification_id: str
    transport: NotificationTransport
    status: Literal["delivered", "dry_run", "disabled", "failed", "error"]
    message: str = ""
    redacted_preview: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    error_code: str | None = None
    error_detail: str | None = None
    retryable: bool = False


class NotificationConfig(BaseModel):
    """Runtime notification configuration.

    Does not store secret values directly — only references to env vars.
    """

    enabled: bool = False
    transport: NotificationTransport = NotificationTransport.disabled
    slack_webhook_url_env: str = "SLACK_WEBHOOK_URL"
    slack_webhook_url: str = ""  # May be populated at runtime from env; never log
    dry_run_emit_preview: bool = True
