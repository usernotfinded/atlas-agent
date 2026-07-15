# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_jsonl_tail_events.py
# PURPOSE: Verifies jsonl tail events behavior and regression expectations.
# DEPS:    json, datetime, pathlib, pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from atlas_agent.events.log import EventLogger, read_recent_events
from atlas_agent.jsonl import tail_jsonl, tail_lines


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_tail_lines_reads_only_recent_non_empty_lines(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("a\n\nb\nc\n", encoding="utf-8")

    assert tail_lines(path, 2) == ["b", "c"]


def test_read_recent_events_preserves_oldest_to_newest_order(tmp_path: Path) -> None:
    logger = EventLogger(tmp_path / "events")
    path = logger.path_for_day(date(2026, 5, 16))
    path.parent.mkdir(parents=True, exist_ok=True)
    for index in range(5):
        path.write_text(
            path.read_text(encoding="utf-8") if path.exists() else "",
            encoding="utf-8",
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"index": index}) + "\n")

    assert [event["index"] for event in read_recent_events(tmp_path / "events", limit=3)] == [2, 3, 4]


def test_tail_jsonl_reports_invalid_recent_json(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text('{"ok": true}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON in tailed JSONL"):
        tail_jsonl(path, 1)
