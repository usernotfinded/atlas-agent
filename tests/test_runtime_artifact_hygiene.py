# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_runtime_artifact_hygiene.py
# PURPOSE: Verifies runtime artifact hygiene behavior and regression
#         expectations.
# DEPS:    pathlib.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

from pathlib import Path


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_gitignore_covers_runtime_artifacts() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    for pattern in (
        "events/*.jsonl",
        "pending_orders/*.json",
        "audit/*.jsonl",
        "reports/**/*.md",
        "reports/*.json",
        "reports/*.csv",
        "demo-workspace/",
        ".atlas/cache/",
        "*.egg-info/",
        ".env",
    ):
        assert pattern in gitignore
