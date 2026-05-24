#!/usr/bin/env python3
"""Verify README quickstart commands are safe, local, and offline.

This script is deterministic and local. It does not:
- load credentials
- create broker connections
- make network calls
- run external commands that mutate state
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"

FORBIDDEN_COMMAND_PATTERNS = (
    r"\blive\s+submit\b",
    r"\bbroker\s+submit\b",
    r"\border\s+create\b",
    r"\bapproval\s+create\b",
    r"\bcredentials\s+load\b",
    r"\bexport\s+api\s+key\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bopen\s+file\b",
    r"\bos\.system\b",
    r"/Users/",
    r"/private/var/",
    r"\bsk-\w+",
    r"\bAPCA-[A-Z0-9]+\b",
    r"\bBearer\s+[A-Za-z0-9._~+/=-]+",
    r"\bAuthorization:\s*Bearer",
)

FORBIDDEN_CLAIM_PHRASES = (
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
)

REQUIRED_SAFE_PHRASES = (
    "sandbox-only",
    "paper-first",
    "offline-safe",
    "live trading disabled by default",
    "not financial advice",
)

REQUIRED_COMMANDS = (
    "pip install",
    "atlas --help",
    "atlas validate",
    "atlas backtest run",
)

FORBIDDEN_FRAGMENTS = (
    "/Users/",
    "/private/var/",
)


def _read_readme() -> str:
    with open(README_PATH, encoding="utf-8") as f:
        return f.read()


def _extract_bash_commands(readme_text: str) -> list[str]:
    """Extract lines from ```bash ... ``` code blocks."""
    commands: list[str] = []
    # Find all ```bash blocks
    for block in re.findall(r"```bash\n(.*?)```", readme_text, re.DOTALL):
        for line in block.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                commands.append(stripped)
    return commands


def _check_forbidden_commands(commands: list[str]) -> list[str]:
    violations: list[str] = []
    for cmd in commands:
        for pattern in FORBIDDEN_COMMAND_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                violations.append(f"Forbidden pattern '{pattern}' in command: {cmd}")
    return violations


def _check_forbidden_claims(text: str) -> list[str]:
    violations: list[str] = []
    lower_text = text.lower()
    for phrase in FORBIDDEN_CLAIM_PHRASES:
        idx = lower_text.find(phrase)
        if idx == -1:
            continue
        window = 120
        start = max(0, idx - window)
        end = min(len(text), idx + len(phrase) + window)
        context = lower_text[start:end]
        negative_indicators = (
            "not ",
            "does not",
            "never",
            "no ",
            "avoid",
            "disclaimer",
            "prohibited",
            "forbidden",
            "must not",
            "cannot",
            "do not",
            "is not",
            "are not",
            "without",
            "fail closed",
            "not yet",
            "not implemented",
            "not enabled",
            "not authorized",
            "not a ",
            "not ready",
        )
        if not any(ind in context for ind in negative_indicators):
            violations.append(f"Forbidden claim '{phrase}' found outside negative context")
    return violations


def _check_required_safe_phrases(text: str) -> list[str]:
    missing: list[str] = []
    lower_text = text.lower()
    for phrase in REQUIRED_SAFE_PHRASES:
        if phrase.lower() not in lower_text:
            missing.append(f"Required safe phrase '{phrase}' missing from README")
    return missing


def _check_required_commands(commands: list[str]) -> list[str]:
    missing: list[str] = []
    joined = "\n".join(commands)
    for req in REQUIRED_COMMANDS:
        if req not in joined:
            missing.append(f"Required safe command '{req}' missing from README quickstart")
    return missing


def _check_forbidden_fragments(text: str) -> list[str]:
    violations: list[str] = []
    for frag in FORBIDDEN_FRAGMENTS:
        if frag in text:
            violations.append(f"Forbidden fragment '{frag}' found in README")
    return violations


def _check_no_secret_placeholders(text: str) -> list[str]:
    violations: list[str] = []
    # Look for secret-looking placeholders in code blocks
    for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
        for line in block.splitlines():
            if re.search(r"\bsk-[A-Za-z0-9]+", line):
                violations.append(f"Secret-like placeholder in bash block: {line.strip()}")
            for token in ("API_KEY", "SECRET", "TOKEN", "PASSWORD"):
                if token in line and "#" not in line:
                    violations.append(f"Credential-like token '{token}' in bash block: {line.strip()}")
    return violations


def main() -> int:
    if not README_PATH.exists():
        print("ERROR: README.md not found")
        return 1

    text = _read_readme()
    commands = _extract_bash_commands(text)

    all_violations: list[str] = []
    all_violations.extend(_check_forbidden_commands(commands))
    all_violations.extend(_check_forbidden_claims(text))
    all_violations.extend(_check_required_safe_phrases(text))
    all_violations.extend(_check_required_commands(commands))
    all_violations.extend(_check_forbidden_fragments(text))
    all_violations.extend(_check_no_secret_placeholders(text))

    if all_violations:
        print("README quickstart verification FAILED")
        for v in all_violations:
            print(f"  - {v}")
        return 1

    print("README quickstart verification PASSED")
    print(f"  Checked {len(commands)} bash command(s)")
    print("  No forbidden patterns, claims, or fragments found")
    print("  All required safe phrases and commands present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
