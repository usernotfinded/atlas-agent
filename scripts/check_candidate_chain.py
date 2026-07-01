#!/usr/bin/env python3
"""Candidate-chain consistency guard for Atlas Agent release docs.

Deterministic, local, read-only, stdlib-only checker for release candidate-chain
files under docs/releases/.  Exit codes:
  0  pass
  1  operational error (missing metadata, malformed JSON, unreadable file)
  2  validation failure
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

from release_metadata import load_metadata, ReleaseMetadata

# Filename patterns that identify candidate-chain files.
_CANDIDATE_FILENAME_RE = re.compile(
    r"^(v\d+\.\d+\.\d+)-(?:candidates\.json|candidates\.md|candidate-selection\.md|plan\.md)$"
)

# Recognized explicit status-line fields in Markdown.
_STATUS_LINE_RE = re.compile(
    r"^\s*[-*•]?\s*\*?\s*"
    r"(status|release\s+status|candidate\s+status|acceptance\s+status|"
    r"current\s+public\s+release|next\s+planned\s+release|"
    r"pypi(?:\s+published)?|github\s+release|tag\s+created)"
    r"\s*[:=]\s*(.*)$",
    re.IGNORECASE,
)

_VERSION_TOKEN_RE = re.compile(r"v\d+\.\d+\.\d+")

ALLOWED_CANDIDATE_STATUSES = frozenset(
    {
        "proposed",
        "accepted",
        "released",
        "deferred",
        "rejected",
        "superseded",
    }
)

ALLOWED_RELEASE_STATUSES = ALLOWED_CANDIDATE_STATUSES | {
    # Existing historical candidate-chain JSONs use these release-line-level
    # statuses.  They are not valid for individual candidates.
    "planning",
    "planning-only",
    "release-prep",
    "candidate-selection",
    "implemented",
}

ALLOWED_VERDICTS = frozenset(
    {"PASS", "FAIL", "PENDING", "WITHDRAWN", "PASS_WITH_WARNINGS", "DEFERRED"}
)

FORBIDDEN_PHRASES = [
    "live-ready",
    "safe to trade",
    "safe-to-trade",
    "profitable",
    "guaranteed profit",
    "guaranteed returns",
    "broker endorsed",
    "broker-approved",
    "order submission enabled",
    "live submit enabled",
    "submit orders without approval",
    "PyPI published",
    "published to PyPI",
]

NEGATIVE_INDICATORS = (
    "not ",
    "no ",
    "never",
    "does not",
    "do not",
    "is not",
    "are not",
    "was not",
    "unpublished",
    "not created",
    "fail closed",
    "must not",
    "cannot",
    "prohibited",
    "forbidden",
)


def _normalize_status_for_validation(status: str) -> str:
    """Normalize a status string for set membership checks."""
    return status.lower().replace("_", "-")


@dataclasses.dataclass(frozen=True)
class CandidateChainError:
    path: Path | None
    repo_root: Path
    message: str

    def __str__(self) -> str:
        if self.path is None:
            return f"ERROR: {self.message}"
        try:
            rel = self.path.relative_to(self.repo_root)
        except ValueError:
            rel = self.path.name
        return f"ERROR: {rel}: {self.message}"


@dataclasses.dataclass(frozen=True)
class CandidateChainWarning:
    path: Path | None
    repo_root: Path
    message: str

    def __str__(self) -> str:
        if self.path is None:
            return f"WARNING: {self.message}"
        try:
            rel = self.path.relative_to(self.repo_root)
        except ValueError:
            rel = self.path.name
        return f"WARNING: {rel}: {self.message}"


@dataclasses.dataclass
class CandidateChainResult:
    repo_root: Path
    errors: list[CandidateChainError] = dataclasses.field(default_factory=list)
    warnings: list[CandidateChainWarning] = dataclasses.field(default_factory=list)

    def add_error(self, path: Path | None, message: str) -> None:
        self.errors.append(CandidateChainError(path, self.repo_root, message))

    def add_warning(self, path: Path | None, message: str) -> None:
        self.warnings.append(CandidateChainWarning(path, self.repo_root, message))

    @property
    def ok(self) -> bool:
        return not self.errors

    def emit(self) -> None:
        lines = [str(e) for e in self.errors] + [str(w) for w in self.warnings]
        lines.sort()
        for line in lines:
            print(line)


def discover_candidate_files(root: Path) -> list[Path]:
    releases_dir = root / "docs" / "releases"
    if not releases_dir.exists():
        return []
    candidates: list[Path] = []
    for path in releases_dir.iterdir():
        if path.is_file() and _CANDIDATE_FILENAME_RE.match(path.name):
            candidates.append(path)
    candidates.sort()
    return candidates


def parse_candidate_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_status_value(raw: str) -> str:
    """Return the normalized status text, keeping elaborating phrases."""
    return raw.strip().strip("`\"'*!.").lower()


def _normalize_bool(raw: str) -> bool | str:
    """Normalize an explicit boolean value, returning the raw string if unclear."""
    cleaned = re.sub(r"[^a-z0-9]+", "", raw.lower())
    if cleaned in ("true", "yes", "created", "published", "1"):
        return True
    if cleaned in ("false", "no", "notcreated", "notpublished", "unpublished", "0"):
        return False
    if "not" in cleaned or "unpublished" in cleaned:
        return False
    return raw.strip()


def _field_name_to_key(name: str) -> str | None:
    cleaned = re.sub(r"[^a-z0-9]+", "", name.lower())
    mapping = {
        "status": "status",
        "releasestatus": "status",
        "candidatestatus": "candidate_status",
        "acceptancestatus": "acceptance_status",
        "currentpublicrelease": "current_public_release",
        "nextplannedrelease": "next_planned_release",
        "pypi": "pypi_published",
        "pypipublished": "pypi_published",
        "githubrelease": "github_release_created",
        "tagcreated": "tag_created",
    }
    return mapping.get(cleaned)


def _parse_field_value(key: str, raw: str):
    raw = raw.strip()
    if key in ("status", "candidate_status", "acceptance_status"):
        return _normalize_status_value(raw)
    if key in ("current_public_release", "next_planned_release"):
        match = _VERSION_TOKEN_RE.search(raw)
        return match.group(0) if match else raw.strip("`\"'*!.")
    if key in ("pypi_published", "tag_created", "github_release_created"):
        return _normalize_bool(raw)
    return raw


def scan_markdown_status_lines(path: Path) -> tuple[dict[str, object], set[str]]:
    """Return explicit status fields and a set of release-line tokens."""
    fields: dict[str, object] = {}
    release_refs: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                match = _STATUS_LINE_RE.match(line)
                if not match:
                    continue
                key = _field_name_to_key(match.group(1))
                if key is None:
                    continue
                raw_value = match.group(2)
                fields[key] = _parse_field_value(key, raw_value)
                release_refs.update(_VERSION_TOKEN_RE.findall(raw_value))
    except (OSError, UnicodeDecodeError):
        pass
    return fields, release_refs


def derive_release_lines(metadata: ReleaseMetadata) -> tuple[set[str], str]:
    historical = {
        r["tag"]
        for r in metadata.releases
        if r.get("status") == "historical"
    }
    released = historical | {metadata.current_public_release}
    return released, metadata.next_planned_release


def _release_line_category(
    release_line: str, metadata: ReleaseMetadata, released_lines: set[str]
) -> str:
    if release_line == metadata.current_public_release:
        return "current_public"
    if release_line == metadata.next_planned_release:
        return "planning"
    if release_line in released_lines:
        return "historical"
    return "unknown"


def _bool_mismatch(a, b) -> bool:
    return bool(a) != bool(b)


def validate_release_line(
    path: Path,
    data: dict,
    release_line: str,
    metadata: ReleaseMetadata,
    released_lines: set[str],
    result: CandidateChainResult,
) -> str:
    """Validate the release line for a single candidate-chain file.

    Returns the category of the release line.
    """
    category = _release_line_category(release_line, metadata, released_lines)

    status = _normalize_status_for_validation(str(data.get("status", "")))
    pypi_true = data.get("pypi_published") is True
    tag_true = data.get("tag_created") is True
    github_true = data.get("github_release_created") is True

    # Modern schema carries an explicit release_line field.
    if "release_line" in data:
        file_release_line = data["release_line"]
        if file_release_line != release_line:
            result.add_error(
                path,
                f"release_line field ({file_release_line}) does not match filename ({release_line})",
            )
        if status and status not in ALLOWED_RELEASE_STATUSES:
            result.add_error(path, f"unknown release-line status: {status}")
    else:
        # Legacy / unknown schema (e.g. artifact_type, release field).
        legacy_release = data.get("release") or data.get("release_line")
        if legacy_release and legacy_release != release_line:
            result.add_error(
                path,
                f"legacy release field ({legacy_release}) does not match filename ({release_line})",
            )
        if status and status not in ALLOWED_RELEASE_STATUSES:
            result.add_error(path, f"unknown release-line status: {status}")

    # Release-line claim checks.
    if category == "planning" and status == "released":
        result.add_error(
            path,
            f"release line {release_line} is next planned but claims status released",
        )
    if category == "current_public" and status and status != "released":
        result.add_error(
            path,
            f"current public release line {release_line} must have status released, got {status}",
        )
    if category == "historical" and status and status != "released":
        result.add_warning(
            path,
            f"historical release line {release_line} has non-released status {status}",
        )

    # Unknown release lines must not claim released/tag/GitHub Release/PyPI.
    if category == "unknown":
        if status == "released":
            result.add_error(
                path, f"unknown release line {release_line} claims status released"
            )
        if tag_true:
            result.add_error(
                path, f"unknown release line {release_line} claims tag_created:true"
            )
        if github_true:
            result.add_error(
                path, f"unknown release line {release_line} claims github_release_created:true"
            )
        if pypi_true:
            result.add_error(
                path, f"unknown release line {release_line} claims pypi_published:true"
            )
        if not (status == "released" or tag_true or github_true or pypi_true):
            result.add_warning(
                path,
                f"unknown release line {release_line}; skipping strict checks",
            )

    return category


def validate_candidate_ids(
    path: Path, data: dict, result: CandidateChainResult
) -> None:
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        result.add_error(path, "candidates must be a list")
        return
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        cid = candidate.get("id")
        if not cid:
            result.add_error(path, "candidate missing id")
            continue
        if cid in seen:
            result.add_error(path, f"duplicate candidate id: {cid}")
        seen.add(cid)


def validate_candidate_statuses(
    path: Path, data: dict, result: CandidateChainResult
) -> None:
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        return
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        status = _normalize_status_for_validation(str(candidate.get("status", "")))
        if status and status not in ALLOWED_CANDIDATE_STATUSES:
            if status in ALLOWED_RELEASE_STATUSES:
                result.add_warning(
                    path,
                    f"candidate status {status!r} is a release-line status, not a candidate status",
                )
            else:
                result.add_error(path, f"candidate has unknown status: {status}")

        verdict = candidate.get("acceptance_verdict")
        if verdict is not None:
            if str(verdict).upper() not in ALLOWED_VERDICTS:
                result.add_error(path, f"candidate has unknown verdict: {verdict}")

        accepted = candidate.get("accepted")
        if status == "released" and not (accepted is True and verdict == "PASS"):
            result.add_error(
                path,
                f"released candidate {candidate.get('id')} must have accepted=true and acceptance_verdict=PASS",
            )

        is_accepted = accepted is True or status in ("accepted", "released")
        if is_accepted and not str(candidate.get("title", "")).strip():
            cid = candidate.get("id", "<unknown>")
            result.add_error(path, f"accepted candidate {cid} must have a non-empty title")


def validate_pypi_consistency(
    path: Path,
    data: dict,
    release_line: str,
    category: str,
    metadata: ReleaseMetadata,
    result: CandidateChainResult,
) -> None:
    json_pypi = data.get("pypi_published")
    if json_pypi is not None:
        if json_pypi is True and not metadata.pypi_published:
            result.add_error(
                path,
                f"pypi_published:true for {release_line} but metadata says false",
            )
        record = metadata.release_by_tag(release_line)
        if record and "pypi_published" in record:
            if _bool_mismatch(json_pypi, record["pypi_published"]):
                result.add_error(
                    path,
                    f"pypi_published ({json_pypi}) contradicts release record for {release_line}",
                )

    # Compare metadata scalar fields for current and next release lines.
    meta_map = {
        "source_version": metadata.source_version,
        "current_public_release": metadata.current_public_release,
        "next_planned_release": metadata.next_planned_release,
    }
    for field, expected in meta_map.items():
        value = data.get(field)
        if value is None:
            continue
        if str(value).lower() != str(expected).lower():
            message = f"{field} ({value}) does not match metadata ({expected})"
            if category in ("current_public", "planning"):
                result.add_error(path, message)
            else:
                result.add_warning(path, message)


def validate_tag_release_claims(
    path: Path,
    data: dict,
    release_line: str,
    category: str,
    metadata: ReleaseMetadata,
    result: CandidateChainResult,
) -> None:
    record = metadata.release_by_tag(release_line)

    for field in ("tag_created", "github_release_created"):
        value = data.get(field)
        if value is None:
            continue
        if category == "planning" and value is True:
            result.add_error(
                path,
                f"{field}:true for next planned release {release_line}",
            )
            continue
        if category in ("current_public", "historical"):
            record_value = record.get(field) if record and field in record else None
            if record_value is None:
                # Legacy metadata records lack these keys; do not enforce.
                continue
            if _bool_mismatch(value, record_value):
                result.add_error(
                    path,
                    f"{field} ({value}) contradicts release record for {release_line}",
                )


def _markdown_field_expected(
    key: str,
    release_line: str,
    category: str,
    metadata: ReleaseMetadata,
) -> object | None:
    if key == "current_public_release":
        return metadata.current_public_release
    if key == "next_planned_release":
        return metadata.next_planned_release
    if key == "pypi_published":
        return metadata.pypi_published
    if key in ("tag_created", "github_release_created"):
        if category == "planning":
            return False
        record = metadata.release_by_tag(release_line)
        if record and key in record:
            return record[key]
    return None


def _values_equal(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    return str(a).lower() == str(b).lower()


def _status_values_compatible(a, b) -> bool:
    """Allow Markdown status elaborations like 'historical planning-only record'."""
    left = str(a).lower()
    right = str(b).lower()
    if left == right:
        return True
    if left in right or right in left:
        return True
    # Also allow if either value is a phrase used as a modifier.
    for phrase in ("historical", "planning-only", "release-prep"):
        if phrase in left and phrase in right:
            return True
    return False


def validate_markdown_consistency(
    path: Path,
    release_line: str,
    category: str,
    md_fields: dict[str, object],
    md_refs: set[str],
    json_data: dict | None,
    metadata: ReleaseMetadata,
    released_lines: set[str],
    planning_line: str,
    result: CandidateChainResult,
) -> None:
    # Markdown vs JSON contradictions.
    if json_data is not None:
        for key, md_value in md_fields.items():
            json_value = json_data.get(key)
            if json_value is None:
                continue
            if key in ("status", "candidate_status", "acceptance_status"):
                if not _status_values_compatible(md_value, json_value):
                    result.add_error(
                        path,
                        f"Markdown {key} ({md_value}) contradicts JSON ({json_value})",
                    )
            elif not _values_equal(md_value, json_value):
                result.add_error(
                    path,
                    f"Markdown {key} ({md_value}) contradicts JSON ({json_value})",
                )

    # Markdown vs metadata contradictions.
    for key, md_value in md_fields.items():
        expected = _markdown_field_expected(key, release_line, category, metadata)
        if expected is None:
            continue
        if not _values_equal(md_value, expected):
            message = f"Markdown {key} ({md_value}) contradicts metadata ({expected})"
            if category in ("current_public", "planning"):
                result.add_error(path, message)
            else:
                result.add_warning(path, message)

    # Release-line references in explicit status lines.
    known_lines = released_lines | {planning_line}
    for ref in sorted(md_refs):
        if ref == release_line or ref in known_lines:
            continue
        message = f"release_line reference {ref} does not match filename release line or metadata"
        if category in ("current_public", "planning"):
            result.add_error(path, message)
        else:
            result.add_warning(path, message)


def _line_contains_forbidden(line: str) -> list[str]:
    lower = line.lower()
    findings: list[str] = []
    for phrase in FORBIDDEN_PHRASES:
        start = 0
        while True:
            idx = lower.find(phrase, start)
            if idx == -1:
                break
            # Check for a negative indicator before the matched phrase within the
            # same line.  "without" is intentionally NOT a negative indicator so
            # that "submit orders without approval" remains a failure.
            prefix = lower[:idx]
            negated = any(prefix.endswith(indicator) or indicator in prefix for indicator in NEGATIVE_INDICATORS)
            if not negated:
                findings.append(phrase)
            start = idx + 1
    return findings


def validate_forbidden_candidate_claims(
    path: Path, result: CandidateChainResult
) -> None:
    try:
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                for phrase in _line_contains_forbidden(line):
                    result.add_error(
                        path,
                        f"forbidden claim at line {lineno}: {phrase!r}",
                    )
    except (OSError, UnicodeDecodeError):
        result.add_warning(path, "could not read file for forbidden-claim scan")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate release candidate-chain consistency."
    )
    parser.add_argument(
        "repo_root",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="Repository root (defaults to current working directory)",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root.resolve()

    metadata_path = repo_root / "docs" / "releases" / "release-metadata.json"
    try:
        metadata = ReleaseMetadata(load_metadata(metadata_path))
    except FileNotFoundError:
        print(f"ERROR: Release metadata not found: {metadata_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed release metadata: {exc}")
        return 1

    released_lines, planning_line = derive_release_lines(metadata)
    candidate_files = discover_candidate_files(repo_root)
    result = CandidateChainResult(repo_root=repo_root)

    # Group discovered files by release line for cross-file checks.
    files_by_line: dict[str, list[Path]] = {}
    json_by_line: dict[str, dict] = {}
    md_by_line: dict[str, list[tuple[Path, dict, set[str]]]] = {}

    for path in candidate_files:
        match = _CANDIDATE_FILENAME_RE.match(path.name)
        if not match:
            continue
        release_line = match.group(1)
        files_by_line.setdefault(release_line, []).append(path)

        if path.suffix == ".json":
            try:
                data = parse_candidate_json(path)
            except json.JSONDecodeError as exc:
                print(f"ERROR: malformed JSON in {path}: {exc}")
                return 1
            except OSError as exc:
                print(f"ERROR: cannot read {path}: {exc}")
                return 1
            json_by_line[release_line] = data
        else:
            md_fields, md_refs = scan_markdown_status_lines(path)
            md_by_line.setdefault(release_line, []).append((path, md_fields, md_refs))

    # Validate each JSON file.
    for release_line, data in json_by_line.items():
        json_path = repo_root / "docs" / "releases" / f"{release_line}-candidates.json"
        category = validate_release_line(
            json_path, data, release_line, metadata, released_lines, result
        )
        if "release_line" in data:
            validate_candidate_ids(json_path, data, result)
            validate_candidate_statuses(json_path, data, result)
            validate_pypi_consistency(
                json_path, data, release_line, category, metadata, result
            )
            validate_tag_release_claims(
                json_path, data, release_line, category, metadata, result
            )

    # Validate Markdown consistency and forbidden claims.
    for release_line, md_entries in md_by_line.items():
        category = _release_line_category(release_line, metadata, released_lines)
        json_data = json_by_line.get(release_line)
        for path, md_fields, md_refs in md_entries:
            if category == "unknown":
                result.add_warning(
                    path,
                    f"unknown release line {release_line}; skipping strict checks",
                )
            validate_markdown_consistency(
                path,
                release_line,
                category,
                md_fields,
                md_refs,
                json_data,
                metadata,
                released_lines,
                planning_line,
                result,
            )
            # Forbidden-claim scan applies only to candidate-chain Markdown files.
            validate_forbidden_candidate_claims(path, result)

    result.emit()

    if result.ok:
        print("Candidate-chain consistency PASSED")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
