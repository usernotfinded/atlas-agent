#!/usr/bin/env python3
"""Check existing backtest reports for schema contract compliance.

Scans <root>/*/result.json (default: .atlas/backtests) and validates each
against the backtest report schema contract. Exits non-zero if any report
fails validation, or if --fail-on-legacy is set and legacy reports are found.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from atlas_agent.backtest.report_schema import (
    get_schema_validation_result,
    unreadable_schema_result,
)


STATUS_COUNTS = {"valid": 0, "invalid": 0, "legacy": 0, "unreadable": 0}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check backtest report schema compliance."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary.",
    )
    parser.add_argument(
        "--fail-on-legacy",
        action="store_true",
        help="Treat legacy reports as failures.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(".atlas/backtests"),
        help="Root directory to scan (default: .atlas/backtests).",
    )
    return parser


def check_reports(root: Path) -> dict:
    report_paths = sorted(root.glob("*/result.json")) if root.exists() else []
    reports = []
    counts = dict(STATUS_COUNTS)

    for path in report_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            result = unreadable_schema_result(f"unreadable: {exc}")
        else:
            result = get_schema_validation_result(data)

        status = result.status
        if status == "valid":
            counts["valid"] += 1
        elif status == "legacy":
            counts["legacy"] += 1
        elif status == "unreadable":
            counts["unreadable"] += 1
        elif status.startswith("invalid"):
            counts["invalid"] += 1

        reports.append({
            "path": str(path),
            "status": status,
            "schema_version": result.schema_version,
            "valid": result.valid,
            "error": result.error,
            "errors": result.errors,
        })

    errors = [
        r
        for r in reports
        if r["status"].startswith("invalid") or r["status"] == "unreadable"
    ]
    return {
        "ok": counts["invalid"] == 0 and counts["unreadable"] == 0,
        "root": str(root),
        "total": len(report_paths),
        "counts": counts,
        "reports": reports,
        "errors": errors,
    }


def print_text_summary(result: dict, fail_on_legacy: bool) -> None:
    counts = result["counts"]
    for report in result["reports"]:
        status = report["status"]
        path = report["path"]
        if status == "valid":
            print(f"OK   {path}")
        elif status.startswith("invalid"):
            print(f"FAIL {path}: {report['error']}")
            errors = report.get("errors") or []
            for err in errors[1:]:
                print(f"      {err}")
        elif status == "unreadable":
            print(f"UNREADABLE {path}: {report['error']}")

    overall = "passed" if result["ok"] and not (fail_on_legacy and counts["legacy"] > 0) else "failed"
    print(
        f"\nSchema check {overall}: "
        f"total={result['total']} "
        f"valid={counts['valid']} "
        f"invalid={counts['invalid']} "
        f"legacy={counts['legacy']} "
        f"unreadable={counts['unreadable']}"
    )


def build_json_output(result: dict, root: Path, ok: bool) -> dict:
    return {
        "ok": ok,
        "root": str(root),
        "total": result["total"],
        "counts": result["counts"],
        "reports": sorted(result["reports"], key=lambda r: r["path"]),
        "errors": sorted(result["errors"], key=lambda r: r["path"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = check_reports(args.root)
    counts = result["counts"]
    ok = result["ok"] and not (args.fail_on_legacy and counts["legacy"] > 0)

    if args.json:
        output = build_json_output(result, args.root, ok)
        print(json.dumps(output, sort_keys=True, indent=2))
    else:
        print_text_summary(result, args.fail_on_legacy)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
