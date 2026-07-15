#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_bounded_autonomy_governance.py
# PURPOSE: Static check for bounded autonomy governance and roadmap alignment.
# DEPS:    argparse, json, re, subprocess, sys, pathlib.
# ==============================================================================

"""Static check for bounded autonomy governance and roadmap alignment.

Deterministic and local. Does not:
- call network
- call GitHub API
- publish
- upload
- tag
- push
- require credentials
- run live trading
- call brokers/providers
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from release_metadata import load_metadata, ReleaseMetadata
except ImportError:
    from scripts.release_metadata import load_metadata, ReleaseMetadata

_metadata_path = REPO_ROOT / "docs" / "releases" / "release-metadata.json"
_meta = ReleaseMetadata(load_metadata(_metadata_path))

PACKAGE_VERSION = _meta.source_version
CURRENT_PUBLIC_TAG = _meta.current_public_release
NEXT_PLANNED_TAG = _meta.next_planned_release

GOVERNANCE_DOC = REPO_ROOT / "docs" / "bounded-live-autonomy-governance.md"
ROADMAP_DOC = REPO_ROOT / "docs" / "autonomy-roadmap.md"
CANDIDATE_SELECTION_DOC = REPO_ROOT / "docs" / "releases" / "v0.6.16-candidate-selection.md"

# Public-facing locations that must not make positive autonomy claims.
_SCAN_TARGETS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "docs",
    REPO_ROOT / ".github" / "pull_request_template.md",
]

# Forbidden positive claims about autonomous live trading. The scan allows these
# phrases when they appear inside a negative/disclaimer context.
_FORBIDDEN_AUTONOMY_CLAIMS = [
    "autonomous live trading ready",
    "autonomous trading ready",
    "autonomous live trading is implemented",
    "autonomous live trading is supported",
    "unattended live trading",
    "safe live trading",
    "real-money autonomy ready",
    "production-ready for unattended",
    "unsupervised real-money trading is supported",
    "direct ai-to-broker execution is supported",
]

_NEGATIVE_INDICATORS = (
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
    "do not assume",
    "out of scope",
    "not a current",
)


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _normalize(text: str) -> str:
    """Strip common Markdown formatting and collapse whitespace so phrase checks
    survive emphasis, tables, blockquotes, and line wrapping.
    """
    cleaned = (
        text.replace(">", " ")
        .replace("*", "")
        .replace("_", "")
        .replace("`", "")
        .replace("|", " ")
        .lower()
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def _redact(text: str) -> str:
    """Redact user-specific absolute paths from output."""
    home = str(Path.home())
    repo = str(REPO_ROOT)
    replacements = [
        (home, "~"),
        (repo, "<repo>"),
        ("/Users/", "<home>/"),
        ("/private/var/", "<temp>/"),
        ("/var/folders/", "<temp>/"),
        ("/tmp/", "<temp>/"),
        ("/var/tmp/", "<temp>/"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _check_required_files() -> list[str]:
    errors: list[str] = []
    for path in (GOVERNANCE_DOC, ROADMAP_DOC, CANDIDATE_SELECTION_DOC):
        if not path.exists():
            try:
                rel = path.relative_to(REPO_ROOT)
            except ValueError:
                rel = path.name
            errors.append(f"Required governance file missing: {rel}")
    return errors


def _check_governance_doc() -> list[str]:
    errors: list[str] = []
    if not GOVERNANCE_DOC.exists():
        return errors

    text = _read(GOVERNANCE_DOC)
    lower = text.lower()
    norm = _normalize(text)

    required_phrases = [
        ("status: planning and governance only", "planning-only status"),
        ("does not authorize", "non-authorization statement"),
        ("autonomous live trading is not implemented", "current-implementation truth"),
        ("live trading is disabled by default", "default-disabled live trading"),
        ("provider output is never execution authority", "provider-execution boundary"),
        ("l4 is not a current goal", "L4 non-goal statement"),
        ("hard invariants", "hard invariants section"),
        ("external gates before any l4-like path", "external gates section"),
    ]
    for phrase, description in required_phrases:
        if phrase not in norm:
            errors.append(
                f"bounded-live-autonomy-governance.md missing {description}: {phrase!r}"
            )

    # Ensure L4 wording is cautious; accept either phrasing.
    if (
        "not a current capability or milestone" not in norm
        and "not a current goal" not in norm
    ):
        errors.append(
            "bounded-live-autonomy-governance.md missing L4 non-capability statement"
        )

    # Hard invariants must enumerate at least 10 numbered items.
    match = re.search(r"##\s+hard invariants.*?(?=##|$)", norm, re.DOTALL)
    if match:
        numbered = re.findall(r"\b\d+\.\s+", match.group(0))
        if len(numbered) < 10:
            errors.append(
                f"bounded-live-autonomy-governance.md hard invariants under-count: {len(numbered)}"
            )
    else:
        errors.append("bounded-live-autonomy-governance.md hard invariants section not found")

    return errors


def _check_roadmap_doc() -> list[str]:
    errors: list[str] = []
    if not ROADMAP_DOC.exists():
        return errors

    text = _read(ROADMAP_DOC)
    lower = text.lower()
    norm = _normalize(text)

    if "bounded autonomy is a long-term product/research direction, not a current capability" not in norm:
        errors.append(
            "autonomy-roadmap.md missing bounded-autonomy status statement"
        )

    if "bounded-live-autonomy-governance.md" not in lower:
        errors.append(
            "autonomy-roadmap.md missing link to bounded-live-autonomy-governance.md"
        )

    required_phrases = [
        ("out of scope", "out-of-scope section"),
        ("not a current capability or milestone", "L4 non-capability statement"),
        ("deterministic risk gates", "deterministic risk gates reference"),
        ("approval queues", "approval queues reference"),
        ("kill switch", "kill-switch reference"),
    ]
    for phrase, description in required_phrases:
        if phrase not in norm:
            errors.append(f"autonomy-roadmap.md missing {description}: {phrase!r}")

    return errors


def _check_candidate_selection() -> list[str]:
    errors: list[str] = []
    if not CANDIDATE_SELECTION_DOC.exists():
        return errors

    text = _read(CANDIDATE_SELECTION_DOC)
    lower = text.lower()

    if "planning only" not in lower and "planning-only" not in lower:
        errors.append(
            "v0.6.16-candidate-selection.md missing planning-only statement"
        )

    return errors


def _collect_scan_paths() -> list[Path]:
    paths: list[Path] = []
    for target in _SCAN_TARGETS:
        if not target.exists():
            continue
        if target.is_dir():
            for child in target.rglob("*"):
                if child.is_file() and not _is_binary(child):
                    paths.append(child)
        elif target.is_file():
            paths.append(target)
    return paths


def _is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        if b"\x00" in chunk:
            return True
    except OSError:
        return True
    return False


def _check_public_autonomy_claims() -> list[str]:
    errors: list[str] = []
    for path in _collect_scan_paths():
        try:
            with open(path, "r", encoding="utf-8") as f:
                for lineno, raw_line in enumerate(f, start=1):
                    line_lower = raw_line.lower()
                    for claim in _FORBIDDEN_AUTONOMY_CLAIMS:
                        if claim not in line_lower:
                            continue
                        idx = line_lower.index(claim)
                        context_start = max(0, idx - 120)
                        context_end = min(len(line_lower), idx + len(claim) + 120)
                        context = line_lower[context_start:context_end]
                        if not any(ind in context for ind in _NEGATIVE_INDICATORS):
                            try:
                                rel = path.relative_to(REPO_ROOT)
                            except ValueError:
                                rel = path.name
                            errors.append(
                                f"[{rel}:{lineno}] Forbidden autonomy claim: {claim}"
                            )
        except (OSError, UnicodeDecodeError):
            continue
    return errors


def _check_version_planning_only() -> list[str]:
    errors: list[str] = []
    # Version identity is metadata-driven (see CAND-016). The meaningful
    # governance check here is that the next planned release line has not been
    # tagged locally yet.
    result = subprocess.run(
        ["git", "tag", "--list", NEXT_PLANNED_TAG],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        errors.append(f"Local git tag {NEXT_PLANNED_TAG} already exists")

    return errors


def _check_public_launch_readiness_link() -> list[str]:
    errors: list[str] = []
    path = REPO_ROOT / "docs" / "public-launch-readiness.md"
    if path.exists():
        text = _read(path).lower()
        if "bounded-live-autonomy-governance.md" not in text:
            errors.append(
                "public-launch-readiness.md missing link to bounded-live-autonomy-governance.md"
            )
    return errors


def _run_checks() -> dict:
    all_errors: list[str] = []
    all_errors.extend(_check_required_files())
    all_errors.extend(_check_governance_doc())
    all_errors.extend(_check_roadmap_doc())
    all_errors.extend(_check_candidate_selection())
    all_errors.extend(_check_public_autonomy_claims())
    all_errors.extend(_check_version_planning_only())
    all_errors.extend(_check_public_launch_readiness_link())

    return {
        "passed": len(all_errors) == 0,
        "package_version": PACKAGE_VERSION,
        "current_public_tag": CURRENT_PUBLIC_TAG,
        "next_planned_tag": NEXT_PLANNED_TAG,
        "errors": all_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bounded autonomy governance check for Atlas Agent."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (redacted).",
    )
    args = parser.parse_args()

    result = _run_checks()

    if args.json:
        output = {
            "passed": result["passed"],
            "package_version": result["package_version"],
            "current_public_tag": result["current_public_tag"],
            "next_planned_tag": result["next_planned_tag"],
            "errors": [_redact(e) for e in result["errors"]],
        }
        print(json.dumps(output, indent=2))
        return 0 if result["passed"] else 2

    if result["errors"]:
        print("Bounded autonomy governance check FAILED")
        for e in result["errors"]:
            print(f"  - {_redact(e)}")
        return 2

    print("Bounded autonomy governance check PASSED")
    print(f"  Package version: {result['package_version']}")
    print(f"  Current public tag: {result['current_public_tag']}")
    print(f"  Next planned tag: {result['next_planned_tag']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
