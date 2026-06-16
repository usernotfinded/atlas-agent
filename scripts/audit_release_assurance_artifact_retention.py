#!/usr/bin/env python3
"""Read-only audit of GitHub Actions artifact retention for release assurance.

Queries artifact metadata (never downloading or deleting artifacts) either from
the live GitHub API via ``gh api`` or from a local JSON fixture. Produces a JSON
report and a Markdown summary describing availability, age, and expiry status.

Safety note:
  - This script is read-only.
  - It never downloads, uploads, modifies, or deletes artifacts.
  - It never makes network calls in fixture mode.
  - It does not load credentials, enable live trading, or execute any workflow.

Exit codes:
  0 = audit completed successfully
  1 = validation or configuration error (bad arguments, malformed fixture, etc.)
  2 = operational error (subprocess failure, I/O error, etc.)
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_REPO = "usernotfinded/atlas-agent"
DEFAULT_WATCHED_NAMES: tuple[str, ...] = (
    "release-assurance-diagnostics",
    "release-assurance-diagnostics-validation",
    "release-assurance-bundle-demo",
    "reviewer-trust-snapshot",
)

GH_API_PER_PAGE = 100
GH_API_MAX_PAGES = 1000  # Guardrail; never loop indefinitely.

REPORT_BASENAME_JSON = "release-assurance-artifact-retention-report.json"
REPORT_BASENAME_MD = "release-assurance-artifact-retention-report.md"


def _utcnow() -> datetime.datetime:
    """Return the current UTC time with timezone awareness."""
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_iso8601(value: str) -> datetime.datetime:
    """Parse an ISO 8601 timestamp to a timezone-aware UTC datetime."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.datetime.fromisoformat(text)


def _days_between(earlier: datetime.datetime, later: datetime.datetime) -> int:
    """Return the integer number of days between two datetimes."""
    return (later.date() - earlier.date()).days


def _parse_repo(raw: str) -> tuple[str, str]:
    """Parse ``owner/name`` into a tuple."""
    parts = raw.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid repo format '{raw}'; expected owner/name")
    return parts[0], parts[1]


def _parse_artifact_names(values: list[str] | None) -> list[str]:
    """Normalize repeatable or comma-separated artifact name arguments."""
    names: list[str] = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part:
                names.append(part)
    if not names:
        names.extend(DEFAULT_WATCHED_NAMES)
    return names


def _load_fixture_json(path: Path) -> dict[str, Any]:
    """Load a JSON fixture matching the GitHub artifacts list API shape."""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Fixture JSON root must be an object")
    if "artifacts" not in data:
        raise ValueError("Fixture JSON must contain an 'artifacts' array")
    if not isinstance(data["artifacts"], list):
        raise ValueError("Fixture JSON 'artifacts' must be an array")
    return data


def _fetch_artifacts_page(owner: str, repo: str, page: int) -> dict[str, Any]:
    """Fetch a single page of artifact metadata via ``gh api``."""
    url = f"repos/{owner}/{repo}/actions/artifacts?per_page={GH_API_PER_PAGE}&page={page}"
    result = subprocess.run(
        ["gh", "api", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"gh api failed: {stderr}")
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("GitHub API response root must be an object")
    return data


def _fetch_artifacts_live(owner: str, repo: str) -> list[dict[str, Any]]:
    """Fetch all artifact metadata pages from the GitHub API."""
    artifacts: list[dict[str, Any]] = []
    for page in range(1, GH_API_MAX_PAGES + 1):
        data = _fetch_artifacts_page(owner, repo, page)
        page_artifacts = data.get("artifacts", [])
        if not isinstance(page_artifacts, list):
            raise ValueError("GitHub API 'artifacts' must be an array")
        if not page_artifacts:
            break
        artifacts.extend(page_artifacts)
        if len(page_artifacts) < GH_API_PER_PAGE:
            break
    return artifacts


def _build_artifact_record(
    artifact: dict[str, Any],
    watched_names: list[str],
    near_expiry_days: int,
    reference_time: datetime.datetime,
) -> dict[str, Any]:
    """Transform a GitHub artifact object into an audit record."""
    name = artifact.get("name", "")
    artifact_id = artifact.get("id")
    workflow_run = artifact.get("workflow_run") or {}
    source_run_id = workflow_run.get("id")
    created_at_raw = artifact.get("created_at")
    expires_at_raw = artifact.get("expires_at")
    expired = bool(artifact.get("expired", False))

    matches_watched = name in watched_names

    age_days: int | None = None
    days_until_expiry: int | None = None
    retention_status = "unknown"

    if created_at_raw and expires_at_raw:
        try:
            created_at = _parse_iso8601(str(created_at_raw))
            expires_at = _parse_iso8601(str(expires_at_raw))
            age_days = _days_between(created_at, reference_time)
            days_until_expiry = _days_between(reference_time, expires_at)
        except (ValueError, TypeError):
            retention_status = "unknown"
        else:
            if expired:
                retention_status = "expired"
            elif days_until_expiry <= near_expiry_days:
                retention_status = "near_expiry"
            else:
                retention_status = "available"

    return {
        "name": name,
        "id": artifact_id,
        "source_run_id": source_run_id,
        "created_at": created_at_raw,
        "expires_at": expires_at_raw,
        "expired": expired,
        "age_days": age_days,
        "days_until_expiry": days_until_expiry,
        "matches_watched_names": matches_watched,
        "retention_status": retention_status,
    }


def _build_report(
    artifacts: list[dict[str, Any]],
    repo: str,
    watched_names: list[str],
    older_than_days: int,
    near_expiry_days: int,
    reference_time: datetime.datetime,
) -> dict[str, Any]:
    """Build the full audit report from raw artifact metadata."""
    records = [
        _build_artifact_record(
            artifact, watched_names, near_expiry_days, reference_time
        )
        for artifact in artifacts
    ]

    watched_records = [r for r in records if r["matches_watched_names"]]
    watched_older_than = [
        r for r in watched_records
        if r["age_days"] is not None and r["age_days"] >= older_than_days
    ]

    status_counts: dict[str, int] = {
        "available": 0,
        "near_expiry": 0,
        "expired": 0,
        "unknown": 0,
    }
    for record in records:
        status = record["retention_status"]
        if status in status_counts:
            status_counts[status] += 1

    return {
        "repo": repo,
        "watched_names": watched_names,
        "older_than_days": older_than_days,
        "near_expiry_days": near_expiry_days,
        "generated_at": reference_time.isoformat(),
        "total_count": len(records),
        "artifacts": records,
        "summary": {
            "total": len(records),
            "watched": len(watched_records),
            "watched_older_than_days": len(watched_older_than),
            "available": status_counts["available"],
            "near_expiry": status_counts["near_expiry"],
            "expired": status_counts["expired"],
            "unknown": status_counts["unknown"],
        },
    }


def _write_json_report(report: dict[str, Any], output_dir: Path) -> Path:
    """Write the JSON report to the output directory."""
    path = output_dir / REPORT_BASENAME_JSON
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_markdown_report(report: dict[str, Any], output_dir: Path) -> Path:
    """Write a human-readable Markdown report to the output directory."""
    path = output_dir / REPORT_BASENAME_MD
    summary = report["summary"]

    lines: list[str] = [
        "# Release Assurance Artifact Retention Report",
        "",
        f"- **Repository:** `{report['repo']}`",
        f"- **Generated at:** {report['generated_at']}",
        f"- **Watched names:** {', '.join(report['watched_names'])}",
        f"- **Older-than threshold:** {report['older_than_days']} days",
        f"- **Near-expiry threshold:** {report['near_expiry_days']} days",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | --- |",
        f"| Total artifacts | {summary['total']} |",
        f"| Watched artifacts | {summary['watched']} |",
        f"| Watched artifacts older than {report['older_than_days']} days | {summary['watched_older_than_days']} |",
        f"| Available | {summary['available']} |",
        f"| Near expiry | {summary['near_expiry']} |",
        f"| Expired | {summary['expired']} |",
        f"| Unknown status | {summary['unknown']} |",
        "",
        "## Artifacts",
        "",
        "| Name | ID | Source run | Created | Expires | Age (days) | Days until expiry | Status | Watched |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    status_to_emoji = {
        "available": "🟢",
        "near_expiry": "🟡",
        "expired": "🔴",
        "unknown": "⚪",
    }

    for record in report["artifacts"]:
        age = record["age_days"] if record["age_days"] is not None else "-"
        days_left = (
            record["days_until_expiry"]
            if record["days_until_expiry"] is not None
            else "-"
        )
        status = record["retention_status"]
        emoji = status_to_emoji.get(status, "⚪")
        watched = "Yes" if record["matches_watched_names"] else "No"
        source_run = record["source_run_id"] if record["source_run_id"] is not None else "-"
        created = record["created_at"] or "-"
        expires = record["expires_at"] or "-"
        lines.append(
            f"| {record['name']} | {record['id']} | {source_run} | "
            f"{created} | {expires} | {age} | {days_left} | "
            f"{emoji} {status} | {watched} |"
        )

    lines.append("")
    lines.append(
        "_This report is read-only. It does not download, delete, or modify artifacts._"
    )
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _print_human_summary(report: dict[str, Any]) -> None:
    """Print a short human-readable summary to stdout."""
    summary = report["summary"]
    print("Release assurance artifact retention audit completed")
    print(f"  Repository: {report['repo']}")
    print(f"  Total artifacts: {summary['total']}")
    print(f"  Watched artifacts: {summary['watched']}")
    print(f"  Watched artifacts older than {report['older_than_days']} days: {summary['watched_older_than_days']}")
    print(f"  Available: {summary['available']}")
    print(f"  Near expiry: {summary['near_expiry']}")
    print(f"  Expired: {summary['expired']}")
    print(f"  Unknown status: {summary['unknown']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit of GitHub Actions artifact retention for release assurance. "
            "Queries artifact metadata only; never downloads or deletes artifacts."
        )
    )
    parser.add_argument(
        "--repo",
        default=None,
        help=(
            "Repository in owner/name format. Defaults to the GITHUB_REPOSITORY "
            "environment variable or usernotfinded/atlas-agent."
        ),
    )
    parser.add_argument(
        "--artifact-name",
        action="append",
        dest="artifact_names",
        help=(
            "Artifact name to watch. Repeatable or comma-separated. "
            f"Defaults to: {', '.join(DEFAULT_WATCHED_NAMES)}."
        ),
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=7,
        help="Age threshold in days for highlighting watched artifacts (default: 7).",
    )
    parser.add_argument(
        "--near-expiry-days",
        type=int,
        default=3,
        help="Threshold for flagging artifacts as near expiry (default: 3).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory where JSON and Markdown reports are written (default: current directory).",
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        default=None,
        help="Path to a local JSON fixture matching the gh api artifacts list shape.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output to stdout instead of a human summary.",
    )
    parser.add_argument(
        "--reference-time",
        default=None,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.repo is None:
        args.repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO)

    try:
        owner, repo = _parse_repo(args.repo)
    except ValueError as e:
        if args.json:
            print(
                json.dumps(
                    {"passed": False, "error": str(e)},
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    watched_names = _parse_artifact_names(args.artifact_names)

    if args.older_than_days < 0 or args.near_expiry_days < 0:
        msg = "--older-than-days and --near-expiry-days must be non-negative"
        if args.json:
            print(
                json.dumps({"passed": False, "error": msg}, indent=2, sort_keys=True)
            )
        else:
            print(f"Configuration error: {msg}", file=sys.stderr)
        return 1

    try:
        if args.reference_time is not None:
            reference_time = _parse_iso8601(args.reference_time)
        else:
            reference_time = _utcnow()
    except ValueError as e:
        if args.json:
            print(
                json.dumps(
                    {"passed": False, "error": f"Invalid --reference-time: {e}"},
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"Configuration error: invalid --reference-time: {e}", file=sys.stderr)
        return 1

    try:
        if args.input_json is not None:
            if not args.input_json.exists():
                raise FileNotFoundError(f"Fixture not found: {args.input_json}")
            data = _load_fixture_json(args.input_json)
            raw_artifacts = data.get("artifacts", [])
        else:
            raw_artifacts = _fetch_artifacts_live(owner, repo)

        report = _build_report(
            raw_artifacts,
            f"{owner}/{repo}",
            watched_names,
            args.older_than_days,
            args.near_expiry_days,
            reference_time,
        )

        if not args.output_dir.exists():
            args.output_dir.mkdir(parents=True, exist_ok=True)

        json_path = _write_json_report(report, args.output_dir)
        md_path = _write_markdown_report(report, args.output_dir)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        if args.json:
            print(
                json.dumps(
                    {"passed": False, "error": str(e)},
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"Validation error: {e}", file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError, RuntimeError) as e:
        if args.json:
            print(
                json.dumps(
                    {"passed": False, "error": str(e)},
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"Operational error: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "passed": True,
                    "repo": report["repo"],
                    "summary": report["summary"],
                    "json_report": str(json_path),
                    "markdown_report": str(md_path),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        _print_human_summary(report)
        print(f"  JSON report: {json_path}")
        print(f"  Markdown report: {md_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
