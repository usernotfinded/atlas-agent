#!/usr/bin/env python3
"""Scan public docs for unsafe claims, stale versions, missing safety wording.

Deterministic and local. Does not:
- load credentials
- make network calls
- run external commands that mutate state
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# Public docs to scan. Old release notes are scanned only for unsafe current-state claims,
# not for stale historical descriptions.
PUBLIC_DOC_PATHS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "docs" / "provider-safety-dossier.md",
    REPO_ROOT / "docs" / "examples" / "provider-safety-dossier-workflow.md",
    REPO_ROOT / "docs" / "release-checklist.md",
    REPO_ROOT / "docs" / "release-candidate-readiness.md",
    REPO_ROOT / "docs" / "release-candidate-cutover.md",
    REPO_ROOT / "docs" / "package-distribution-verification.md",
    REPO_ROOT / "docs" / "public-repo-hygiene.md",
    REPO_ROOT / "docs" / "public-launch-readiness.md",
    REPO_ROOT / "docs" / "github-repo-settings.md",
    REPO_ROOT / "docs" / "external-reviewer-walkthrough.md",
    REPO_ROOT / "docs" / "reviewer-checklist.md",
    REPO_ROOT / "docs" / "public-launch-messaging.md",
    REPO_ROOT / "docs" / "feedback-request-guide.md",
    REPO_ROOT / "docs" / "public-faq.md",
    REPO_ROOT / "docs" / "final-rc-audit.md",
    REPO_ROOT / "docs" / "final-release-candidate-checklist.md",
    REPO_ROOT / "docs" / "stable-release-decision.md",
    REPO_ROOT / "docs" / "stable-release-checklist.md",
]

# Forbidden positive claims about live trading / provider execution / broker execution / trust.
FORBIDDEN_POSITIVE_CLAIMS = [
    "live trading ready",
    "production trading ready",
    "safe to trade",
    "trust granted",
    "provider execution enabled",
    "broker execution enabled",
    "orders enabled",
    "approvals enabled",
    "autonomous trading ready",
    "guaranteed profit",
    "profitable strategy",
    "verified alpha",
    "beats the market",
    "real-money ready",
]

# Fragments that should not appear in public docs.
FORBIDDEN_FRAGMENTS = [
    "/Users/",
    "/private/var/",
]

# Secret-like patterns.
SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9]{10,}",
    r"\bAPCA-[A-Z0-9]{10,}",
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}",
    r"\bAuthorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]+",
]

# Required core safety wording (case-insensitive, must appear across all scanned docs).
REQUIRED_SAFETY_WORDING = [
    "not financial advice",
]

# Required safe wording that must appear in README specifically.
README_REQUIRED_SAFE = [
    "sandbox-only",
    "paper-first",
    "offline-safe",
    "live trading disabled by default",
]

# Forbidden command patterns in bash blocks.
FORBIDDEN_COMMAND_PATTERNS = [
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
]

# Stale version pattern: any reference to an older dev tag that looks like a current-status claim.
# We allow old release notes to mention their own version, but flag "Current Status (v0.5.7.dev46)"
# when the current version is dev49.
STALE_VERSION_PATTERNS = [
    r"Current Status \(v0\.5\.7\.dev[1-5][0-9]\)",
    r"Current Status \(0\.5\.7\.dev[1-5][0-9]\)",
    r"Current Status \(0\.5\.9\.dev[0-9]\)",
    r"Current Status \(v0\.5\.7-rc\d+\)",
    r"Current Status \(0\.5\.7rc\d+\)",
    r"Current Status \(v0\.5\.8-rc\d+\)",
    r"Current Status \(0\.5\.8rc\d+\)",
    r"v0\.5\.7\.dev[1-5][0-9](?!\d)",
    r"0\.5\.7\.dev[1-5][0-9](?!\d)",
]

# Current version string that public docs should reference as current.
CURRENT_VERSION = "v0.6.0"


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_bash_commands(text: str) -> list[str]:
    commands: list[str] = []
    for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
        for line in block.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                commands.append(stripped)
    return commands


def _sentence_around(text: str, start: int, end: int) -> str:
    """Extract the sentence/paragraph containing the match."""
    # Look backwards for sentence boundaries
    boundary_chars = {'.', '!', '?', '\n'}
    s = start
    while s > 0 and text[s - 1] not in boundary_chars:
        s -= 1
    # Look forwards for sentence boundaries
    e = end
    while e < len(text) and text[e] not in boundary_chars:
        e += 1
    return text[s:e]


def _check_forbidden_positive_claims(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    lower_text = text.lower()
    for phrase in FORBIDDEN_POSITIVE_CLAIMS:
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
                    f"[{rel_path}] Forbidden positive claim '{phrase}' outside negative context"
                )
    return violations


def _check_forbidden_fragments(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    for frag in FORBIDDEN_FRAGMENTS:
        if frag in text:
            violations.append(f"[{rel_path}] Forbidden fragment '{frag}' found")
    return violations


def _check_secrets(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    for pattern in SECRET_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            violations.append(
                f"[{rel_path}] Secret-like pattern '{pattern}' matched: {m.group(0)[:40]}"
            )
    return violations


def _check_forbidden_commands(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    commands = _extract_bash_commands(text)
    for cmd in commands:
        for pattern in FORBIDDEN_COMMAND_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                violations.append(
                    f"[{rel_path}] Forbidden command pattern '{pattern}' in: {cmd}"
                )
    return violations


def _check_required_safety_wording(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    lower = text.lower()
    for phrase in REQUIRED_SAFETY_WORDING:
        if phrase.lower() not in lower:
            violations.append(
                f"[{rel_path}] Required safety wording '{phrase}' missing"
            )
    return violations


def _check_readme_required_safe(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    if rel_path != "README.md":
        return violations
    lower = text.lower()
    for phrase in README_REQUIRED_SAFE:
        if phrase.lower() not in lower:
            violations.append(
                f"[{rel_path}] Required README safe phrase '{phrase}' missing"
            )
    return violations


# Patterns that indicate a doc claims the project is still a release candidate.
_STALE_RC_STATUS_PATTERNS = [
    re.compile(r"this is a release candidate, not a final release", re.IGNORECASE),
    re.compile(r"atlas agent is a .*release candidate", re.IGNORECASE),
]

# Historical doc names where RC references are expected and allowed.
_HISTORICAL_RC_DOC_INDICATORS = [
    "final-rc-audit",
    "final-release-candidate-checklist",
    "release-candidate-readiness",
    "release-candidate-cutover",
    "v0.5.7-rc",
    "changelog",
]


def _check_stale_version_refs(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    for pattern in STALE_VERSION_PATTERNS:
        for m in re.finditer(pattern, text):
            # Skip if this is inside an old release note filename or historical description
            context_start = max(0, m.start() - 60)
            context_end = min(len(text), m.end() + 60)
            context = text[context_start:context_end].lower()
            if "release note" in context or "changelog" in context or "history" in context:
                continue
            violations.append(
                f"[{rel_path}] Stale version reference looks like current-status claim: {m.group(0)}"
            )
    return violations


def _check_stale_rc_status_claims(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    lower = text.lower()
    # Skip historical docs that are expected to discuss RC history
    if any(ind.lower() in rel_path.lower() for ind in _HISTORICAL_RC_DOC_INDICATORS):
        return violations
    for pattern in _STALE_RC_STATUS_PATTERNS:
        for m in pattern.finditer(text):
            context_start = max(0, m.start() - 60)
            context_end = min(len(text), m.end() + 60)
            context = text[context_start:context_end].lower()
            # Allow if clearly historical (past tense)
            if "was a" in context or "were" in context:
                continue
            violations.append(
                f"[{rel_path}] Stale RC status claim: {m.group(0)}"
            )
    return violations


def main() -> int:
    all_violations: list[str] = []

    for path in PUBLIC_DOC_PATHS:
        if not path.exists():
            print(f"WARNING: Public doc not found: {path}")
            continue
        rel = path.relative_to(REPO_ROOT)
        text = _read(path)
        all_violations.extend(_check_forbidden_positive_claims(text, str(rel)))
        all_violations.extend(_check_forbidden_fragments(text, str(rel)))
        all_violations.extend(_check_secrets(text, str(rel)))
        all_violations.extend(_check_forbidden_commands(text, str(rel)))
        all_violations.extend(_check_required_safety_wording(text, str(rel)))
        all_violations.extend(_check_readme_required_safe(text, str(rel)))
        all_violations.extend(_check_stale_version_refs(text, str(rel)))
        all_violations.extend(_check_stale_rc_status_claims(text, str(rel)))

    if all_violations:
        print("Public docs consistency check FAILED")
        for v in all_violations:
            print(f"  - {v}")
        return 1

    print("Public docs consistency check PASSED")
    print(f"  Scanned {len(PUBLIC_DOC_PATHS)} public doc file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
