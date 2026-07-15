#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/check_docs_archive_hygiene.py
# PURPOSE: Validate historical docs archive hygiene and reference integrity.
# DEPS:    argparse, json, re, sys, pathlib, typing.
# ==============================================================================

"""Validate historical docs archive hygiene and reference integrity.

Static, local-only, and read-only. Does not load credentials, make network calls,
enable live trading, or delete files.

Exit codes:
  0 = archive hygiene OK
  1 = blocking findings
  2 = operational error
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"
ARCHIVE_README = ARCHIVE_DIR / "README.md"

ARCHIVE_SUBDIRS = [
    ARCHIVE_DIR / "legacy-plans",
    ARCHIVE_DIR / "release-candidates",
    ARCHIVE_DIR / "legacy-demos",
]

# Docs that were candidates for archival and must now be either active (still in
# docs/) or archived (in docs/archive/). This is the CAND-005 candidate list.
CANDIDATE_FILES = {
    "batch-4.4-reconciliation.md",
    "batch-4.6-plan.md",
    "batch-4.7-plan.md",
    "design-batch-4.0-live-submit.md",
    "final-rc-audit.md",
    "release-candidate-audit-v0.5.7.dev2.md",
    "v0.5.8-gap-prioritization.md",
    "v0.5.8-rc1-cutover.md",
    "v0.5.8-rc1-readiness.md",
    "release-candidate-cutover.md",
    "release-candidate-readiness.md",
    "final-release-candidate-checklist.md",
    "demo-artifact-index.md",
    "demo-audit.md",
    "demo-paper-workflow.md",
    "demo-recording-guide.md",
    "demo-risk-rejection.md",
    "controlled-reviewer-outreach.md",
    "reviewer-outreach-checklist.md",
    "reviewer-targets-template.md",
}

# Files that are allowed to be active even though they look historical. These
# are still referenced by active checkers, tests, release notes, or source code.
EXPECTED_ACTIVE_HISTORICAL_FILES = {
    "final-rc-audit.md",
    "release-candidate-cutover.md",
    "release-candidate-readiness.md",
    "final-release-candidate-checklist.md",
    "demo-artifact-index.md",
    "demo-audit.md",
    "demo-paper-workflow.md",
    "demo-risk-rejection.md",
    "controlled-reviewer-outreach.md",
    "reviewer-outreach-checklist.md",
    "reviewer-targets-template.md",
}

# Active docs to scan for broken links and stale historical claims.
ACTIVE_DOC_ROOTS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "SECURITY.md",
    REPO_ROOT / "CONTRIBUTING.md",
    REPO_ROOT / "CHANGELOG.md",
    DOCS_DIR,
]

# Scan scope: Markdown files under the active roots that are not archived.
EXCLUDED_ACTIVE_DIRS = {
    ARCHIVE_DIR,
}

# Forbidden claims that must not appear in active public docs outside explicit
# historical context. Same intent as check_forbidden_claims.py but scoped to
# archive-hygiene concerns.
FORBIDDEN_CLAIMS = [
    "safe live trading",
    "production trading ready",
    "production-ready trading",
    "autonomous trading ready",
    "guaranteed profit",
    "guaranteed returns",
    "no risk trading",
    "risk-free trading",
    "risk free trading",
    "zero risk trading",
]

# Paths that are historical evidence by nature and may mention archived files
# or old releases without being flagged as presenting them as current.
HISTORICAL_EVIDENCE_PATHS = {
    "CHANGELOG.md",
}


# ==============================================================================
# VALIDATION WORKFLOW
# ==============================================================================

# --- VALIDATION HELPERS AND ENTRYPOINTS ---

def _is_historical_evidence(doc: Path, repo_root: Path | None = None) -> bool:
    repo_root = repo_root or REPO_ROOT
    try:
        rel = doc.relative_to(repo_root).as_posix()
    except ValueError:
        return False
    if rel in HISTORICAL_EVIDENCE_PATHS:
        return True
    if rel.startswith("docs/releases/"):
        return True
    return False


# Phrases that wrongly describe archived content as current.
STALE_ARCHIVED_AS_CURRENT_PATTERNS = [
    re.compile(r"\bcurrent\s+(?:public\s+)?release\s+(?:is\s+|:)\s*v0\.5\.\d+", re.IGNORECASE),
    re.compile(r"\blatest\s+(?:public\s+)?release\s+(?:is\s+|:)\s*v0\.5\.\d+", re.IGNORECASE),
    re.compile(r"\bcurrent\s+(?:public\s+)?release\s+(?:is\s+|:)\s*v0\.6\.0", re.IGNORECASE),
]

# Negative-context indicators for forbidden claims, matching the intent of
# check_public_docs_consistency.py.
NEGATIVE_CONTEXT_INDICATORS = (
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
    "out of scope",
    "does not prove",
    "disabled by default",
    "assertions of",
    "claims of",
    "categories of unsafe wording",
)

# Markdown link pattern: [text](path)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# Markdown reference-style link: [text][ref] or [ref]:
MD_REF_LINK_RE = re.compile(r"\[([^\]]+)\](?:\[([^\]]*)\])?")
MD_REF_DEF_RE = re.compile(r"^\[([^\]]+)\]:\s*(\S+)", re.MULTILINE)


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _collect_active_docs(
    active_doc_roots: list[Path], excluded_dirs: set[Path]
) -> list[Path]:
    docs: list[Path] = []
    for root in active_doc_roots:
        if root.is_file() and root.suffix in {".md", ".markdown"}:
            docs.append(root)
        elif root.is_dir():
            for path in sorted(root.rglob("*.md")):
                if any(path.is_relative_to(excluded) for excluded in excluded_dirs):
                    continue
                docs.append(path)
    return sorted(set(docs))


def _collect_archived_docs(archive_subdirs: list[Path]) -> list[Path]:
    docs: list[Path] = []
    for subdir in archive_subdirs:
        if subdir.exists():
            docs.extend(sorted(subdir.rglob("*.md")))
    return docs


def _extract_md_links(text: str) -> list[tuple[str, str, int]]:
    """Return list of (link_text, target, line_no) for inline Markdown links."""
    links: list[tuple[str, str, int]] = []
    for m in MD_LINK_RE.finditer(text):
        line_no = text[: m.start()].count("\n") + 1
        links.append((m.group(1), m.group(2), line_no))
    return links


def _resolve_link(source: Path, target: str, repo_root: Path | None = None) -> Path | None:
    """Resolve a Markdown link target relative to the source file."""
    repo_root = repo_root or REPO_ROOT
    docs_dir = repo_root / "docs"
    # Skip anchors, URLs, and absolute paths.
    if not target or target.startswith(("http://", "https://", "mailto:", "#", "/")):
        return None
    if target.startswith("./") or target.startswith("../") or "/" in target:
        resolved = (source.parent / target).resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            return None
        return resolved
    # Bare filename: resolve relative to source parent, then docs root.
    candidate = source.parent / target
    if candidate.exists():
        return candidate.resolve()
    candidate = docs_dir / target
    if candidate.exists():
        return candidate.resolve()
    # Return the source-parent candidate even if missing so broken links are detected.
    return candidate.resolve()


def _check_archive_readme_exists(archive_readme: Path) -> list[str]:
    errors: list[str] = []
    if not archive_readme.exists():
        try:
            rel = archive_readme.relative_to(REPO_ROOT)
        except ValueError:
            rel = archive_readme
        errors.append(f"Archive README missing: {rel}")
    return errors


def _check_archive_readme_inventory(
    archived_docs: list[Path], archive_readme: Path, archive_dir: Path
) -> list[str]:
    errors: list[str] = []
    if not archive_readme.exists():
        return errors
    text = _read(archive_readme)
    for doc in archived_docs:
        if doc == archive_readme:
            continue
        rel = doc.relative_to(archive_dir).as_posix()
        name = doc.name
        if name not in text and rel not in text:
            errors.append(f"Archive README does not mention archived doc: {rel}")
    return errors


def _check_candidate_disposition(
    repo_root: Path, docs_dir: Path, archive_dir: Path
) -> list[str]:
    errors: list[str] = []
    for name in CANDIDATE_FILES:
        active_path = docs_dir / name
        archived_paths = list(archive_dir.rglob(name))
        is_active = active_path.exists()
        is_archived = bool(archived_paths)
        if not is_active and not is_archived:
            errors.append(f"Candidate doc '{name}' is neither active nor archived (was it deleted without tracking?)")
        elif is_active and name not in EXPECTED_ACTIVE_HISTORICAL_FILES:
            errors.append(
                f"Candidate doc '{name}' is still active but not in EXPECTED_ACTIVE_HISTORICAL_FILES; "
                "either archive it or add it to the expected-active set with a reason"
            )
    return errors


def _check_active_links(active_docs: list[Path], repo_root: Path) -> list[str]:
    errors: list[str] = []
    for doc in active_docs:
        text = _read(doc)
        try:
            rel_doc = doc.relative_to(repo_root)
        except ValueError:
            rel_doc = doc
        for link_text, target, line_no in _extract_md_links(text):
            resolved = _resolve_link(doc, target, repo_root)
            if resolved is None:
                continue
            if not resolved.exists():
                try:
                    resolved_rel = resolved.relative_to(repo_root)
                except ValueError:
                    resolved_rel = resolved
                errors.append(
                    f"[{rel_doc}:{line_no}] Broken link to '{target}' (resolved to {resolved_rel})"
                )
    return errors


def _sentence_around(text: str, start: int, end: int) -> str:
    boundary_chars = {".", "!", "?", "\n"}
    s = start
    while s > 0 and text[s - 1] not in boundary_chars:
        s -= 1
    e = end
    while e < len(text) and text[e] not in boundary_chars:
        e += 1
    return text[s:e]


def _check_archived_not_presented_as_current(
    active_docs: list[Path], archived_docs: list[Path], archive_dir: Path, repo_root: Path
) -> list[str]:
    errors: list[str] = []
    archived_names = {p.name for p in archived_docs}
    archive_readme = archive_dir / "README.md"
    for doc in active_docs:
        if _is_historical_evidence(doc, repo_root):
            continue
        text = _read(doc)
        try:
            rel_doc = doc.relative_to(repo_root)
        except ValueError:
            rel_doc = doc
        # Check for links to archived docs without historical context.
        for link_text, target, line_no in _extract_md_links(text):
            resolved = _resolve_link(doc, target, repo_root)
            if resolved is None:
                continue
            try:
                resolved.relative_to(archive_dir)
            except ValueError:
                continue
            lower_text = link_text.lower()
            if "archive" not in lower_text and "historical" not in lower_text and "old" not in lower_text:
                errors.append(
                    f"[{rel_doc}:{line_no}] Link to archived doc '{target}' uses present-tense label "
                    f"'{link_text}' without historical context"
                )
        # Check for stale current-release claims.
        for pattern in STALE_ARCHIVED_AS_CURRENT_PATTERNS:
            for m in pattern.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                errors.append(
                    f"[{rel_doc}:{line_no}] Active doc contains stale current-release claim: {m.group(0)}"
                )
        # Check for bare mentions of archived doc names that might imply currency.
        for name in archived_names:
            # Skip if the doc is the archive README (it should mention them).
            if doc == archive_readme:
                continue
            if name in text:
                # Only flag if the mention is not inside an archive/legacy/historical sentence.
                for m in re.finditer(re.escape(name), text):
                    sentence = _sentence_around(text, m.start(), m.end()).lower()
                    if (
                        "archive" not in sentence
                        and "historical" not in sentence
                        and "legacy" not in sentence
                    ):
                        line_no = text[: m.start()].count("\n") + 1
                        errors.append(
                            f"[{rel_doc}:{line_no}] Active doc mentions archived file '{name}' without "
                            f"archive/historical context"
                        )
                        break
    return errors


def _check_forbidden_claims(active_docs: list[Path], repo_root: Path) -> list[str]:
    errors: list[str] = []
    for doc in active_docs:
        if _is_historical_evidence(doc, repo_root):
            continue
        text = _read(doc).lower()
        try:
            rel_doc = doc.relative_to(repo_root)
        except ValueError:
            rel_doc = doc
        for claim in FORBIDDEN_CLAIMS:
            for m in re.finditer(re.escape(claim.lower()), text):
                sentence = _sentence_around(text, m.start(), m.end()).lower()
                if any(ind in sentence for ind in NEGATIVE_CONTEXT_INDICATORS):
                    continue
                line_no = text[: m.start()].count("\n") + 1
                errors.append(f"[{rel_doc}:{line_no}] Forbidden claim '{claim}' in active doc")
    return errors


def _check_no_active_docs_in_archive(
    archive_subdirs: list[Path], archive_readme: Path
) -> list[str]:
    """Archive should only contain intentionally archived files."""
    errors: list[str] = []
    for subdir in archive_subdirs:
        if not subdir.exists():
            continue
        for path in subdir.rglob("*.md"):
            if path == archive_readme:
                continue
            name = path.name
            if name not in CANDIDATE_FILES:
                errors.append(
                    f"Archive contains file not in the CAND-005 candidate list: {path}"
                )
    return errors


def check_archive_hygiene(
    *,
    repo_root: Path | None = None,
    docs_dir: Path | None = None,
    archive_dir: Path | None = None,
    archive_readme: Path | None = None,
    archive_subdirs: list[Path] | None = None,
    active_doc_roots: list[Path] | None = None,
) -> dict[str, Any]:
    repo_root = (repo_root or REPO_ROOT).resolve()
    docs_dir = (docs_dir or repo_root / "docs").resolve()
    archive_dir = (archive_dir or docs_dir / "archive").resolve()
    archive_readme = (archive_readme or archive_dir / "README.md").resolve()
    archive_subdirs = archive_subdirs or [
        archive_dir / "legacy-plans",
        archive_dir / "release-candidates",
        archive_dir / "legacy-demos",
    ]
    active_doc_roots = active_doc_roots or [
        repo_root / "README.md",
        repo_root / "SECURITY.md",
        repo_root / "CONTRIBUTING.md",
        repo_root / "CHANGELOG.md",
        docs_dir,
    ]
    excluded_dirs = {archive_dir}

    errors: list[str] = []
    warnings: list[str] = []

    active_docs = _collect_active_docs(active_doc_roots, excluded_dirs)
    archived_docs = _collect_archived_docs(archive_subdirs)

    errors.extend(_check_archive_readme_exists(archive_readme))
    errors.extend(_check_archive_readme_inventory(archived_docs, archive_readme, archive_dir))
    errors.extend(_check_candidate_disposition(repo_root, docs_dir, archive_dir))
    errors.extend(_check_active_links(active_docs, repo_root))
    errors.extend(_check_archived_not_presented_as_current(active_docs, archived_docs, archive_dir, repo_root))
    errors.extend(_check_forbidden_claims(active_docs, repo_root))
    errors.extend(_check_no_active_docs_in_archive(archive_subdirs, archive_readme))

    if not archived_docs and archive_dir.exists():
        warnings.append("Archive directory exists but contains no archived docs")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "active_docs_scanned": len(active_docs),
        "archived_docs_scanned": len(archived_docs),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate historical docs archive hygiene and reference integrity."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root to validate. Defaults to the current repository.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    result = check_archive_hygiene(repo_root=args.repo_root)

    if args.json:
        summary = (
            "Docs archive hygiene check PASSED"
            if result["passed"]
            else "Docs archive hygiene check FAILED"
        )
        print(
            json.dumps(
                {
                    "passed": result["passed"],
                    "summary": summary,
                    "active_docs_scanned": result["active_docs_scanned"],
                    "archived_docs_scanned": result["archived_docs_scanned"],
                    "errors": result["errors"],
                    "warnings": result["warnings"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result["passed"] else 1

    if result["errors"]:
        print("Docs archive hygiene check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")
    else:
        print("Docs archive hygiene check PASSED")
        print(f"  Active docs scanned: {result['active_docs_scanned']}")
        print(f"  Archived docs scanned: {result['archived_docs_scanned']}")

    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  WARN: {warning}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
