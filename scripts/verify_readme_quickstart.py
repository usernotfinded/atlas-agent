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
    "safe by default",
    "live trading is disabled by default",
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


def _sentence_around(text: str, start: int, end: int) -> str:
    """Extract the sentence/paragraph containing the match."""
    boundary_chars = {'.', '!', '?', '\n'}
    s = start
    while s > 0 and text[s - 1] not in boundary_chars:
        s -= 1
    e = end
    while e < len(text) and text[e] not in boundary_chars:
        e += 1
    return text[s:e]


def _check_forbidden_claims(text: str) -> list[str]:
    violations: list[str] = []
    lower_text = text.lower()
    for phrase in FORBIDDEN_CLAIM_PHRASES:
        for m in re.finditer(re.escape(phrase), lower_text):
            sentence = _sentence_around(lower_text, m.start(), m.end()).lower()
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
                "remains disabled",
                "remains locked",
                "remains blocked",
            )
            if not any(ind in sentence for ind in negative_indicators):
                violations.append(
                    f"Forbidden claim '{phrase}' found outside negative context"
                )
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
    for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
        for line in block.splitlines():
            # Skip pure comment lines
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Check for secret-looking values even if there's a trailing comment
            if re.search(r"\bsk-[A-Za-z0-9]+", line):
                violations.append(f"Secret-like placeholder in bash block: {line.strip()}")
            for token in ("API_KEY", "SECRET", "TOKEN", "PASSWORD"):
                # Token must appear as a value (after = or space), not just in a comment
                if re.search(rf"\b{token}\b", line):
                    # Allow if the only occurrence is inside a comment
                    comment_pos = line.find("#")
                    if comment_pos != -1:
                        before_comment = line[:comment_pos]
                        if re.search(rf"\b{token}\b", before_comment):
                            violations.append(
                                f"Credential-like token '{token}' in bash block: {line.strip()}"
                            )
                    else:
                        violations.append(
                            f"Credential-like token '{token}' in bash block: {line.strip()}"
                        )
    return violations


def _check_profitability_limitation(text: str) -> list[str]:
    missing: list[str] = []
    lower = text.lower()
    # Accept any of the equivalent forms used across README revisions.
    has_profitability = (
        "safety validation does not imply profitability" in lower
        or "no profitability" in lower
        or "does not predict profit" in lower
    )
    if not has_profitability:
        missing.append(
            "Required limitation phrase about profitability missing"
        )
    has_trading_correctness = (
        "safety validation does not imply trading correctness" in lower
        or "does not imply profitability or trading correctness" in lower
        or "no profitability or trading correctness claims" in lower
    )
    if not has_trading_correctness:
        missing.append(
            "Required limitation phrase about trading correctness missing"
        )
    return missing


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
    all_violations.extend(_check_profitability_limitation(text))

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
