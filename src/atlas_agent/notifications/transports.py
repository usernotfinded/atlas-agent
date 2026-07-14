# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    notifications/transports.py
# PURPOSE: The three ways a notification can be handled: dropped (disabled),
#          rendered but not sent (dry-run), or actually delivered (Slack). Only the
#          third one touches the network.
# DEPS:    notifications.models, notifications.redaction
# ==============================================================================

"""Notification transports.

Disabled, dry-run, and Slack webhook transports.
All transports are testable via dependency injection.
No real network calls in disabled or dry-run modes.
"""

# --- IMPORTS ---
from __future__ import annotations

import json
import os
from typing import Any, Callable

from atlas_agent.notifications.models import (
    NotificationConfig,
    NotificationPayload,
    NotificationResult,
    NotificationTransport,
)
from atlas_agent.notifications.redaction import preview_payload, redact_text


# --- CONFIGURATIONS & CONSTANTS ---

# The HTTP call is INJECTED rather than imported. That is what lets the Slack transport
# be tested end-to-end without a socket — and it means the only code in this module
# that can reach the network is code the caller handed in.
HttpPost = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class NotificationTransportError(RuntimeError):
    pass


# ==============================================================================
# TRANSPORTS
# ==============================================================================

class DisabledTransport:
    """Transport that immediately returns a disabled result without network calls."""

    # Returns a RESULT, not None and not an exception. "Disabled" is a successful,
    # legitimate outcome, and callers must not have to special-case it — otherwise
    # every call site grows an `if notifications_enabled` branch.
    def send(self, payload: NotificationPayload, _config: NotificationConfig) -> NotificationResult:
        return NotificationResult(
            notification_id=payload.notification_id,
            transport=NotificationTransport.disabled,
            status="disabled",
            message="Notifications are disabled",
        )


class DryRunTransport:
    """Transport that returns a dry-run result with a redacted preview. No network calls."""

    def send(self, payload: NotificationPayload, config: NotificationConfig) -> NotificationResult:
        preview = preview_payload(payload) if config.dry_run_emit_preview else ""
        return NotificationResult(
            notification_id=payload.notification_id,
            transport=NotificationTransport.dry_run,
            status="dry_run",
            message="Notification delivered in dry-run mode (no network call)",
            redacted_preview=preview,
        )


class SlackWebhookTransport:
    """Slack incoming webhook transport.

    Sends a JSON POST to a Slack webhook URL.
    Webhook URL is read from an environment variable by default.
    Fails closed if the webhook URL is missing.
    """

    def __init__(self, http_post: HttpPost | None = None) -> None:
        self.http_post = http_post or _default_http_post

    def send(self, payload: NotificationPayload, config: NotificationConfig) -> NotificationResult:
        webhook_url = config.slack_webhook_url or os.getenv(config.slack_webhook_url_env, "")
        if not webhook_url:
            return NotificationResult(
                notification_id=payload.notification_id,
                transport=NotificationTransport.slack,
                status="failed",
                message="Slack webhook URL is not configured",
                error_code="slack_webhook_missing",
                error_detail=f"Set {config.slack_webhook_url_env} environment variable or configure slack_webhook_url",
                retryable=False,
            )

        slack_payload = self._build_slack_payload(payload)
        headers = {"Content-Type": "application/json"}

        try:
            response = self.http_post(webhook_url, headers, slack_payload)
            return NotificationResult(
                notification_id=payload.notification_id,
                transport=NotificationTransport.slack,
                status="delivered",
                message="Slack notification sent",
                redacted_preview=preview_payload(payload),
            )
        except Exception as exc:
            return NotificationResult(
                notification_id=payload.notification_id,
                transport=NotificationTransport.slack,
                status="error",
                message="Slack notification failed",
                error_code="slack_post_error",
                error_detail=str(exc),
                retryable=True,
            )

    @staticmethod
    def _build_slack_payload(payload: NotificationPayload) -> dict[str, Any]:
        severity_emoji = {
            "info": ":information_source:",
            "warning": ":warning:",
            "error": ":x:",
            "critical": ":rotating_light:",
        }
        emoji = severity_emoji.get(payload.severity.value, ":information_source:")
        text = f"{emoji} *{payload.title}*\n{payload.message}"
        if payload.source:
            text += f"\n_Source: {payload.source}_"
        if payload.run_id:
            text += f" | _Run: {payload.run_id}_"
        return {"text": text}


def _default_http_post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8") or "{}")
