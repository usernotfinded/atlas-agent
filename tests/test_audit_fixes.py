# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_audit_fixes.py
# PURPOSE: Verifies audit fixes behavior and regression expectations.
# DEPS:    json, os, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from atlas_agent.events.log import EventLogger
from atlas_agent.workspace import (
    init_workspace,
    resolve_workspace_path,
    set_default_workspace,
    clear_default_workspace,
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_workspace_resolution_priority(tmp_path, monkeypatch) -> None:
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws3 = tmp_path / "ws3"
    ws4 = tmp_path / "ws4"

    for ws in (ws1, ws2, ws3, ws4):
        init_workspace(ws)

    # 1. Flag priority
    assert resolve_workspace_path(str(ws1)) == ws1

    # 2. Env priority
    monkeypatch.setenv("ATLAS_WORKSPACE", str(ws2))
    assert resolve_workspace_path() == ws2

    # 3. Current dir priority (if it's a workspace)
    monkeypatch.delenv("ATLAS_WORKSPACE")
    monkeypatch.chdir(ws3)
    assert resolve_workspace_path() == ws3

    # 4. Default workspace priority
    monkeypatch.chdir(tmp_path) # Move out of ws3
    monkeypatch.setenv("HOME", str(tmp_path))
    set_default_workspace(ws4)
    assert resolve_workspace_path() == ws4


def test_event_logger_hardened_redaction(tmp_path) -> None:
    logger = EventLogger(tmp_path)
    
    # Fake secrets
    openai_key = "demo_openai_secret_abcdefghijklmnopqrstuvwxyz012345"
    github_token = "demo_github_token_1234567890abcdefghijklmnopqrstuvwxyzABCD"
    
    logger.write(
        "agent_started",
        run_id="run1",
        command="test",
        mode="paper",
        payload={
            "msg": f"Leaking {openai_key} here",
            "metadata": {"token": github_token, "safe": "value"}
        }
    )
    
    from datetime import UTC, datetime
    log_file = tmp_path / f"{datetime.now(UTC).date().isoformat()}.jsonl"
    
    content = log_file.read_text(encoding="utf-8")
    assert "[REDACTED]" in content
    assert openai_key not in content
    assert github_token not in content
    
    event = json.loads(content)
    assert event["payload"]["metadata"]["token"] == "[REDACTED]"
    assert event["payload"]["msg"] == "Leaking [REDACTED] here"


def test_workspace_clear(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ws = tmp_path / "my-ws"
    init_workspace(ws)
    set_default_workspace(ws)
    
    from atlas_agent.workspace import get_default_workspace
    assert get_default_workspace() == ws
    
    clear_default_workspace()
    assert get_default_workspace() is None
    assert ws.exists() # Directory should NOT be deleted
