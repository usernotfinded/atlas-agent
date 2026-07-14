# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    safety/secrets.py
# PURPOSE: Detects credentials that have leaked into files that should not hold
#          them — memory notes, journals, reports. Detection only; the scrubbing
#          engine lives in atlas_agent.redaction.
# DEPS:    stdlib only (re)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import re
from pathlib import Path


# --- CONFIGURATIONS & CONSTANTS ---

# Matches NAME=value assignment lines only, which is what a pasted .env fragment
# looks like — the overwhelmingly common way a key ends up somewhere it should not.
# A bare token floating in prose is deliberately NOT matched here: that job belongs
# to the entropy sweep in atlas_agent.redaction, and duplicating it would give two
# heuristics to keep in sync.
SECRET_NAME_RE = re.compile(
    r"^(?:export\s+)?"
    r"(?P<name>[A-Z0-9_]*(?:API_KEY|API_SECRET|SECRET_KEY|TOKEN|PASSWORD)[A-Z0-9_]*)"
    r"\s*=\s*(?P<value>.*)$"
)


# ==============================================================================
# SCANNING
# ==============================================================================

def scan_text_for_secrets(text: str) -> list[str]:
    """Return the NAMES of secret-looking assignments found in *text*.

    Returns:
        Variable names only — never the values. Callers put these straight into
        warnings and audit records, so returning the value would leak the very
        secret this scan exists to catch.
    """
    findings: list[str] = []
    for line in text.splitlines():
        match = SECRET_NAME_RE.match(line.strip())
        if not match:
            continue
        # An empty right-hand side (`API_KEY=`) is a placeholder, not a leak. Flagging
        # it would train people to ignore the warning.
        value = match.group("value").strip().strip('"').strip("'")
        if value:
            findings.append(match.group("name"))
    return findings


def scan_file(path: str | Path) -> list[str]:
    return scan_text_for_secrets(Path(path).read_text(encoding="utf-8"))
