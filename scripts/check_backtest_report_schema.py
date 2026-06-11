#!/usr/bin/env python3
"""Check existing backtest reports for schema contract compliance.

Scans .atlas/backtests/*/result.json and validates each against the
backtest report schema contract. Exits non-zero if any report fails
validation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from atlas_agent.backtest.report_schema import collect_backtest_report_schema_errors


def main() -> int:
    reports_dir = Path(".atlas/backtests")
    if not reports_dir.exists():
        print("No .atlas/backtests directory found; skipping.")
        return 0

    report_paths = sorted(reports_dir.glob("*/result.json"))
    if not report_paths:
        print("No backtest reports found; skipping.")
        return 0

    errors = []
    skipped = 0
    for path in report_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"FAIL {path}: {exc}")
            errors.append((path, exc))
            continue

        # Skip legacy reports that predate the schema contract
        if "schema_version" not in data:
            skipped += 1
            continue

        report_errors = collect_backtest_report_schema_errors(data)
        if not report_errors:
            print(f"OK   {path}")
        else:
            print(f"FAIL {path}: {report_errors[0]}")
            if len(report_errors) > 1:
                for err in report_errors[1:]:
                    print(f"      {err}")
            errors.append((path, report_errors))

    if errors:
        print(f"\n{len(errors)} report(s) failed schema validation.")
        return 1

    checked = len(report_paths) - skipped
    print(f"\nAll {checked} report(s) passed schema validation ({skipped} legacy report(s) skipped).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
