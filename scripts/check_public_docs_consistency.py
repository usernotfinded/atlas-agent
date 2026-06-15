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
    REPO_ROOT / "docs" / "reviewer-golden-path.md",
    REPO_ROOT / "docs" / "reviewer-outreach-checklist.md",
    REPO_ROOT / "docs" / "public-launch-messaging.md",
    REPO_ROOT / "docs" / "feedback-request-guide.md",
    REPO_ROOT / "docs" / "public-faq.md",
    REPO_ROOT / "docs" / "final-rc-audit.md",
    REPO_ROOT / "docs" / "final-release-candidate-checklist.md",
    REPO_ROOT / "docs" / "stable-release-decision.md",
    REPO_ROOT / "docs" / "stable-release-checklist.md",
    REPO_ROOT / "docs" / "trust" / "README.md",
    REPO_ROOT / "docs" / "demo-artifact-index.md",
    REPO_ROOT / "docs" / "demo-paper-workflow.md",
    REPO_ROOT / "docs" / "demo-audit.md",
    REPO_ROOT / "docs" / "demo-risk-rejection.md",
    REPO_ROOT / "docs" / "demo" / "provider-preflight-demo.md",
    REPO_ROOT / "docs" / "product-demo-pack.md",
    REPO_ROOT / "docs" / "marketplace-listing.md",
    REPO_ROOT / "docs" / "autonomy-roadmap.md",
    REPO_ROOT / "docs" / "safety.md",
    REPO_ROOT / "docs" / "kill-switch.md",
    REPO_ROOT / "docs" / "live-trading.md",
    REPO_ROOT / "docs" / "providers.md",
    REPO_ROOT / "docs" / "brokers.md",
    REPO_ROOT / "docs" / "model-providers.md",
    REPO_ROOT / "docs" / "product-capability-inventory.md",
    REPO_ROOT / "docs" / "v0.6-capability-inventory.md",
    REPO_ROOT / "docs" / "research-workflow.md",
]

RELEASE_STATUS_DOC_PATHS = [
    REPO_ROOT / "docs" / "public-feedback-checklist.md",
    REPO_ROOT / "docs" / "security" / "release-readiness.md",
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
    "safe by default",
    "live trading is disabled by default",
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
    r"Current Status \(v0\.6\.0\)",
    r"Current Status \(v0\.6\.[1-9]\)",
    r"Current Status \(v0\.6\.10\)",
    r"Current Status \(v0\.6\.11\)",
    r"Current Status \(0\.6\.[1-9]\)",
    r"Current Status \(0\.6\.10\)",
    r"Current Status \(0\.6\.11\)",
    r"v0\.5\.7\.dev[1-5][0-9](?!\d)",
    r"0\.5\.7\.dev[1-5][0-9](?!\d)",
]

# Provide a fallback module path injection for scripts directory imports
sys.path.insert(0, str(REPO_ROOT / "scripts"))
try:
    from release_metadata import load_metadata, ReleaseMetadata
except ImportError:
    # Handle the case where the script is executed from a weird directory
    load_metadata = None
    ReleaseMetadata = None

def _get_current_version(repo_root: Path) -> str:
    """Read the current version from release-metadata.json dynamically."""
    if load_metadata is None or ReleaseMetadata is None:
        raise RuntimeError("Failed to import release_metadata module")

    metadata_path = repo_root / "docs" / "releases" / "release-metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Release metadata not found at {metadata_path}")

    try:
        meta = ReleaseMetadata(load_metadata(metadata_path))
        if not meta.source_version:
            raise ValueError("source_version is empty in metadata")
        return "v" + meta.source_version
    except Exception as e:
        raise RuntimeError(f"Invalid release metadata: {e}")


def _get_current_public_release(repo_root: Path) -> str:
    """Read the current public release tag from release-metadata.json dynamically."""
    if load_metadata is None or ReleaseMetadata is None:
        raise RuntimeError("Failed to import release_metadata module")

    metadata_path = repo_root / "docs" / "releases" / "release-metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Release metadata not found at {metadata_path}")

    try:
        meta = ReleaseMetadata(load_metadata(metadata_path))
        current = meta.current_public_release
        if not current:
            raise ValueError("current_public_release is empty in metadata")
        return current
    except Exception as e:
        raise RuntimeError(f"Invalid release metadata: {e}")


# Release notes directory.
RELEASES_DIR = REPO_ROOT / "docs" / "releases"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

# Semantic-version release note pattern: vX.Y.Z.md (and vX.Y.Z.W.md).
_RELEASE_NOTE_PATTERN = re.compile(r"^v\d+\.\d+\.\d+([.-]\d+)?\.md$")


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


def _sentence_around(text: str, start: int, end: int) -> tuple[str, int]:
    """Extract the sentence/paragraph containing the match and its start index."""
    # Look backwards for sentence boundaries (.!? or newline, followed by whitespace/start)
    s = start
    while s > 0:
        prev = text[s - 1]
        if prev in {'.', '!', '?'}:
            # Avoid stopping inside version numbers like v0.6.8
            if s == len(text) or text[s].isspace() or text[s] == '\n':
                break
        if prev == '\n':
            break
        s -= 1
    # Look forwards for sentence boundaries
    e = end
    while e < len(text):
        ch = text[e]
        if ch in {'.', '!', '?'}:
            # Include the boundary char if it ends the sentence
            e += 1
            break
        if ch == '\n':
            break
        e += 1
    return text[s:e], s


def _check_forbidden_positive_claims(text: str, rel_path: str) -> list[str]:
    violations: list[str] = []
    lower_text = text.lower()
    for phrase in FORBIDDEN_POSITIVE_CLAIMS:
        for m in re.finditer(re.escape(phrase), lower_text):
            sentence, _ = _sentence_around(lower_text, m.start(), m.end())
            sentence = sentence.lower()
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


def _check_stale_version_refs(text: str, rel_path: str, current_version: str) -> list[str]:
    violations: list[str] = []
    for pattern in STALE_VERSION_PATTERNS:
        for m in re.finditer(pattern, text):
            matched = m.group(0)
            # Skip the actual current version (e.g., Current Status (v0.6.9))
            if current_version in matched:
                continue
            # Skip if this is inside an old release note filename or historical description
            context_start = max(0, m.start() - 60)
            context_end = min(len(text), m.end() + 60)
            context = text[context_start:context_end].lower()
            if "release note" in context or "changelog" in context or "history" in context:
                continue
            violations.append(
                f"[{rel_path}] Stale version reference looks like current-status claim: {matched}"
            )
    return violations


# Patterns that flag a public-release current-status claim for any vX.Y.Z release.
_STALE_PUBLIC_RELEASE_CLAIM_PATTERNS = [
    re.compile(r"is the current stable version", re.IGNORECASE),
    re.compile(r"is the latest stable public", re.IGNORECASE),
    re.compile(r"is the latest tagged public", re.IGNORECASE),
    re.compile(r"is current\.?$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"is current[;:,]", re.IGNORECASE),
]

# Historical doc names where old public-release claims are expected.
_HISTORICAL_PUBLIC_RELEASE_DOC_INDICATORS = [
    "changelog",
    "releases/v0.",
    "trust/v0.",
    "final-release-candidate-checklist",
    "stable-release-checklist",
]


def _check_stale_public_release_claims(
    text: str, rel_path: str, current_public_release: str
) -> list[str]:
    """Flag claims that an older release is the current/latest public release."""
    violations: list[str] = []
    if any(ind.lower() in rel_path.lower() for ind in _HISTORICAL_PUBLIC_RELEASE_DOC_INDICATORS):
        return violations

    tag_pattern = re.compile(r"v\d+\.\d+\.\d+(?:[.-]\d+)?")
    for pattern in _STALE_PUBLIC_RELEASE_CLAIM_PATTERNS:
        for m in pattern.finditer(text):
            # Examine only the sentence containing the claim.
            sentence, sentence_start = _sentence_around(text, m.start(), m.end())
            lower_sentence = sentence.lower()
            # Allow clearly historical contexts.
            if "historical" in lower_sentence or "release note" in lower_sentence:
                continue

            # Determine the subject of the claim: the version nearest the claim phrase.
            # Prefer a tag immediately before the claim (e.g., "v0.6.9 is the latest stable public").
            subject_tag: str | None = None
            match_start_in_sentence = m.start() - sentence_start
            match_end_in_sentence = m.end() - sentence_start
            prefix = sentence[:match_start_in_sentence]
            for tag_m in tag_pattern.finditer(prefix):
                subject_tag = tag_m.group(0)
            # If no tag before the claim, use the first tag after it.
            if subject_tag is None:
                suffix = sentence[match_end_in_sentence:]
                for tag_m in tag_pattern.finditer(suffix):
                    subject_tag = tag_m.group(0)
                    break

            if subject_tag is None:
                continue
            if subject_tag != current_public_release:
                violations.append(
                    f"[{rel_path}] Stale public-release claim: '{subject_tag}' is called current/latest "
                    f"(expected {current_public_release})"
                )
    return violations


def _check_stale_release_status_lines(
    text: str, rel_path: str, current_public_release: str
) -> list[str]:
    """Flag stale release labels and mixed source/public status shorthand."""
    violations: list[str] = []
    if any(ind.lower() in rel_path.lower() for ind in _HISTORICAL_PUBLIC_RELEASE_DOC_INDICATORS):
        return violations

    normalized = re.sub(r"[`*_]", "", text)
    tag = r"v\d+\.\d+\.\d+(?:[.-]\d+)?"
    labeled_claim = re.compile(
        rf"\b(?:current public(?: github)? release|latest public tag)\s*:\s*(?P<tag>{tag})",
        re.IGNORECASE,
    )
    inline_public_claim = re.compile(
        rf"(?P<tag>{tag})\s+public(?:\s+(?:github\s+)?release|\s+status)?\b",
        re.IGNORECASE,
    )
    stale_state_pattern = re.compile(r"\b(?:prepared|not yet tagged|not tagged)\b", re.IGNORECASE)
    tag_pattern = re.compile(tag, re.IGNORECASE)

    seen: set[tuple[int, str]] = set()
    for line_number, line in enumerate(normalized.splitlines(), start=1):
        lower_line = line.lower()
        historical_context = "historical" in lower_line or "previous public" in lower_line

        for pattern in (labeled_claim, inline_public_claim):
            for match in pattern.finditer(line):
                claimed_tag = match.group("tag")
                key = (line_number, claimed_tag)
                if historical_context or claimed_tag == current_public_release or key in seen:
                    continue
                seen.add(key)
                violations.append(
                    f"[{rel_path}] Stale public-release status on line {line_number}: "
                    f"'{claimed_tag}' (expected {current_public_release})"
                )

        for state_match in stale_state_pattern.finditer(line):
            subject_tag: str | None = None
            for tag_match in tag_pattern.finditer(line[:state_match.start()]):
                subject_tag = tag_match.group(0)
            if subject_tag is None:
                suffix_match = tag_pattern.search(line[state_match.end():])
                if suffix_match is not None:
                    subject_tag = suffix_match.group(0)
            if subject_tag == current_public_release:
                violations.append(
                    f"[{rel_path}] Current public release {current_public_release} is described as "
                    f"prepared or untagged on line {line_number}"
                )
                break

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


def _check_readme_current_version(text: str, rel_path: str, current_version: str) -> list[str]:
    """Verify README references CURRENT_VERSION in a status line."""
    violations: list[str] = []
    if rel_path != "README.md":
        return violations
    if f"Current Status ({current_version})" not in text:
        violations.append(
            f"[{rel_path}] README missing 'Current Status ({current_version})' status line"
        )
    return violations


def _check_stale_current_status_in_readme(text: str, rel_path: str, current_version: str) -> list[str]:
    """Flag stale Current Status (vX.Y.Z) claims in README that don't match CURRENT_VERSION."""
    violations: list[str] = []
    if rel_path != "README.md":
        return violations
    for m in re.finditer(r"Current Status \(v(\d+\.\d+\.\d+(?:[.-]\d+)?)\)", text):
        found_version = m.group(1)
        if f"v{found_version}" != current_version:
            violations.append(
                f"[{rel_path}] Stale current-status claim: {m.group(0)} (expected {current_version})"
            )
    return violations


def _check_changelog_references_release_notes() -> list[str]:
    """Warn on orphaned release notes (vX.Y.Z.md) not referenced in CHANGELOG."""
    warnings: list[str] = []
    if not CHANGELOG_PATH.exists():
        warnings.append("CHANGELOG.md not found; cannot check release-note references")
        return warnings
    if not RELEASES_DIR.exists():
        return warnings
    changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8")
    for path in sorted(RELEASES_DIR.glob("v*.md")):
        if not _RELEASE_NOTE_PATTERN.match(path.name):
            continue
        name = path.name.replace(".md", "")
        if name not in changelog_text:
            warnings.append(
                f"Release note {path.name} not referenced in CHANGELOG.md"
            )
    return warnings


def main() -> int:
    try:
        current_version = _get_current_version(REPO_ROOT)
        current_public_release = _get_current_public_release(REPO_ROOT)
    except Exception as e:
        print("Public docs consistency check FAILED")
        print(f"  - Metadata Error: {e}")
        return 1

    all_violations: list[str] = []
    all_warnings: list[str] = []

    for path in PUBLIC_DOC_PATHS:
        if not path.exists():
            all_warnings.append(f"Public doc not found: {path}")
            continue
        rel = path.relative_to(REPO_ROOT)
        text = _read(path)
        all_violations.extend(_check_forbidden_positive_claims(text, str(rel)))
        all_violations.extend(_check_forbidden_fragments(text, str(rel)))
        all_violations.extend(_check_secrets(text, str(rel)))
        all_violations.extend(_check_forbidden_commands(text, str(rel)))
        all_violations.extend(_check_required_safety_wording(text, str(rel)))
        all_violations.extend(_check_readme_required_safe(text, str(rel)))
        all_violations.extend(_check_stale_version_refs(text, str(rel), current_version))
        all_violations.extend(_check_stale_public_release_claims(text, str(rel), current_public_release))
        all_violations.extend(_check_stale_release_status_lines(text, str(rel), current_public_release))
        all_violations.extend(_check_stale_rc_status_claims(text, str(rel)))
        all_violations.extend(_check_readme_current_version(text, str(rel), current_version))
        all_violations.extend(_check_stale_current_status_in_readme(text, str(rel), current_version))

    for path in RELEASE_STATUS_DOC_PATHS:
        if not path.exists():
            all_warnings.append(f"Release-status doc not found: {path}")
            continue
        rel = path.relative_to(REPO_ROOT)
        text = _read(path)
        all_violations.extend(_check_stale_public_release_claims(text, str(rel), current_public_release))
        all_violations.extend(_check_stale_release_status_lines(text, str(rel), current_public_release))

    all_warnings.extend(_check_changelog_references_release_notes())

    if all_violations:
        print("Public docs consistency check FAILED")
        for v in all_violations:
            print(f"  - {v}")
        if all_warnings:
            for w in all_warnings:
                print(f"  WARN: {w}")
        return 1

    print("Public docs consistency check PASSED")
    print(f"  Scanned {len(PUBLIC_DOC_PATHS)} public doc file(s)")
    print(f"  Scanned {len(RELEASE_STATUS_DOC_PATHS)} release-status doc file(s)")
    if all_warnings:
        for w in all_warnings:
            print(f"  WARN: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
