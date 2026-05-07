from __future__ import annotations

import re
from pathlib import Path


SECRET_NAME_RE = re.compile(
    r"^(?:export\s+)?"
    r"(?P<name>[A-Z0-9_]*(?:API_KEY|API_SECRET|SECRET_KEY|TOKEN|PASSWORD)[A-Z0-9_]*)"
    r"\s*=\s*(?P<value>.*)$"
)


def scan_text_for_secrets(text: str) -> list[str]:
    findings: list[str] = []
    for line in text.splitlines():
        match = SECRET_NAME_RE.match(line.strip())
        if not match:
            continue
        value = match.group("value").strip().strip('"').strip("'")
        if value:
            findings.append(match.group("name"))
    return findings


def scan_file(path: str | Path) -> list[str]:
    return scan_text_for_secrets(Path(path).read_text(encoding="utf-8"))
