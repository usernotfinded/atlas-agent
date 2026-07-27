# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/audit/test_audit_tamper_detection.py
# PURPOSE: Pins which kinds of tampering the chain catches on its own and which
#         need the run manifest.
# DEPS:    json, pathlib, atlas_agent.
# ==============================================================================

"""Tamper-detection boundaries of the audit log.

The governance document calls the audit hash-chain tamper-evident. That holds,
but the chain and the manifest catch different things, and the difference is
worth pinning: an edited or deleted event breaks the chain, while events cut
from the end leave a valid chain and are caught only by the manifest's event
count.
"""

# --- IMPORTS ---

from __future__ import annotations

import json
from pathlib import Path

from atlas_agent.audit.verify import verify_audit_log, verify_run_manifest
from atlas_agent.audit.writer import AuditWriter


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _write_run(audit_dir: Path, *, events: int = 4, seal: bool = True) -> Path:
    """Write a small completed run and return the log path."""
    log_path = audit_dir / "events.jsonl"
    writer = AuditWriter(audit_path=log_path)
    writer.start_run("run-1")
    for index in range(events):
        writer.write_event(
            "tool_call_requested",
            run_id="run-1",
            iteration=index,
            payload={"index": index},
        )
    if seal:
        writer.finish_run("completed")
    return log_path


def _manifest_for(audit_dir: Path) -> Path:
    return next((audit_dir / "manifests").glob("*.json"))


class TestChainCatchesEditsAndDeletions:
    def test_untampered_log_verifies(self, tmp_path: Path) -> None:
        log_path = _write_run(tmp_path)
        assert verify_audit_log(log_path).valid is True

    def test_edited_event_is_detected(self, tmp_path: Path) -> None:
        log_path = _write_run(tmp_path)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        edited = json.loads(lines[2])
        edited["payload"] = {"index": 999}
        lines[2] = json.dumps(edited)
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert verify_audit_log(log_path).valid is False

    def test_deleted_middle_event_is_detected(self, tmp_path: Path) -> None:
        log_path = _write_run(tmp_path)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        log_path.write_text("\n".join(lines[:2] + lines[3:]) + "\n", encoding="utf-8")

        assert verify_audit_log(log_path).valid is False


class TestTruncationNeedsTheManifest:
    """Cutting the tail leaves a valid chain — the count is what gives it away."""

    def test_chain_alone_does_not_detect_a_truncated_tail(self, tmp_path: Path) -> None:
        log_path = _write_run(tmp_path)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        log_path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")

        # Every remaining event still links correctly to the one before it.
        assert verify_audit_log(log_path).valid is True

    def test_expected_event_count_detects_a_truncated_tail(self, tmp_path: Path) -> None:
        log_path = _write_run(tmp_path)
        original_count = len(log_path.read_text(encoding="utf-8").splitlines())
        lines = log_path.read_text(encoding="utf-8").splitlines()
        log_path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")

        result = verify_audit_log(log_path, expected_event_count=original_count)
        assert result.valid is False

    def test_manifest_detects_a_truncated_tail(self, tmp_path: Path) -> None:
        log_path = _write_run(tmp_path)
        manifest_path = _manifest_for(tmp_path)
        assert verify_run_manifest(manifest_path).valid is True

        lines = log_path.read_text(encoding="utf-8").splitlines()
        log_path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")

        assert verify_run_manifest(manifest_path).valid is False
