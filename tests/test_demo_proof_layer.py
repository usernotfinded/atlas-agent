# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_demo_proof_layer.py
# PURPOSE: Verifies demo proof layer behavior and regression expectations.
# DEPS:    os, re, pathlib.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import os
import re
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[1]
DEMO_SCRIPT = ROOT / "scripts" / "demo_paper_workflow.sh"
DEMO_GIF = ROOT / "assets" / "atlas-demo.gif"
DEMO_SURFACES = [
    ROOT / "README.md",
    ROOT / "docs" / "demo-paper-workflow.md",
    ROOT / "docs" / "archive" / "legacy-demos" / "demo-recording-guide.md",
    ROOT / "docs" / "demo-audit.md",
    DEMO_SCRIPT,
]


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _combined_demo_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DEMO_SURFACES)


def test_demo_script_exists_and_is_non_destructive() -> None:
    assert DEMO_SCRIPT.exists()
    assert os.access(DEMO_SCRIPT, os.X_OK)

    text = DEMO_SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n")
    assert "mktemp -d" in text
    assert "ATLAS-DEMO" in text
    assert "DEMO-SYMBOL" in text
    assert "discipline setup --manual --yes" in text
    assert "validate" in text
    assert "run --mode paper --dry-run" in text
    assert "backtest run" in text
    assert "audit verify --all" in text

    forbidden = (
        "rm -rf",
        "set_secret",
        ".env.atlas",
        "enable_live_trading",
        "--mode live",
        "curl ",
        "git ",
    )
    for phrase in forbidden:
        assert phrase not in text


def test_demo_script_uses_standardized_comment_structure() -> None:
    text = DEMO_SCRIPT.read_text(encoding="utf-8")

    # Require intentional documentation blocks so future edits cannot regress to
    # unstructured copy-paste comments while preserving the safe shell preamble.
    assert text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n")
    assert "# PROJECT: Atlas Agent" in text
    assert "# FILE:    scripts/demo_paper_workflow.sh" in text
    assert "# PURPOSE:" in text
    assert "# DEPS:" in text
    assert "# SCRIPT WORKFLOW" in text
    assert "# --- ENVIRONMENT, SAFETY, AND EXECUTION ---" in text


def test_demo_docs_and_script_avoid_unsafe_or_stale_examples() -> None:
    lower = _combined_demo_text().lower()
    forbidden_phrases = (
        "btc-usd",
        "local_command",
        "enable_live_trading = true",
        "atlas run --mode live",
        "--mode live",
        "best broker",
        "recommended broker",
        "guaranteed profit",
        "profit bot",
        "autonomous money",
        "will make money",
        "makes money",
        "production-grade live",
    )
    for phrase in forbidden_phrases:
        assert phrase not in lower


def test_demo_docs_and_script_do_not_embed_private_values() -> None:
    text = _combined_demo_text()

    secret_patterns = (
        r"\b[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\s*=\s*(?!\[REDACTED\])\S+",
        r"\bYOUR_[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\b",
        r"\b(?:sk-|pplx-|xox[baprs]-|AKIA)[A-Za-z0-9_-]{10,}\b",
    )
    for pattern in secret_patterns:
        assert re.search(pattern, text) is None


def test_readme_demo_points_to_script_not_missing_gif() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "[Paper Workflow Script](scripts/demo_paper_workflow.sh)" in readme
    assert "./scripts/demo_paper_workflow.sh" in readme
    assert "![Atlas Demo]" not in readme

    if not DEMO_GIF.exists():
        assert "No `assets/atlas-demo.gif` recording is checked in yet" in readme
