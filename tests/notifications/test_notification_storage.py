"""Tests for notification local storage."""
from __future__ import annotations

from pathlib import Path

from atlas_agent.notifications.models import NotificationResult, NotificationTransport
from atlas_agent.notifications.storage import save_result, list_results, load_result


def test_save_and_list_results(tmp_path: Path) -> None:
    result = NotificationResult(
        notification_id="n1",
        transport=NotificationTransport.dry_run,
        status="dry_run",
        message="OK",
    )
    path = save_result(result, tmp_path)
    assert path.exists()
    assert path.name == "n1.json"

    results = list_results(tmp_path)
    assert len(results) == 1
    assert results[0]["notification_id"] == "n1"
    assert results[0]["status"] == "dry_run"


def test_load_result(tmp_path: Path) -> None:
    result = NotificationResult(
        notification_id="n2",
        transport=NotificationTransport.disabled,
        status="disabled",
    )
    save_result(result, tmp_path)
    loaded = load_result("n2", tmp_path)
    assert loaded is not None
    assert loaded["notification_id"] == "n2"


def test_load_result_missing(tmp_path: Path) -> None:
    assert load_result("missing", tmp_path) is None


def test_list_results_empty(tmp_path: Path) -> None:
    assert list_results(tmp_path) == []


def test_save_result_redacts_secrets(tmp_path: Path) -> None:
    result = NotificationResult(
        notification_id="n3",
        transport=NotificationTransport.slack,
        status="error",
        error_detail="Webhook: https://hooks.slack.com/services/T00/B00/XXXX failed",
    )
    path = save_result(result, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "[REDACTED]" in text
    assert "hooks.slack.com" not in text
