#!/usr/bin/env python3
"""Update post-release assurance dossiers with GitHub Actions CI run IDs.

Deterministic helper. Dry-run by default; pass --write to mutate files.
Uses the authenticated gh CLI. Does not load credentials, call brokers,
providers, or trading code.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CORE_WORKFLOWS = [
    "CI",
    "Release Gate",
    "Atlas Agent Paper Routines",
]

CI_SECTION_HEADER = "## GitHub Actions / CI Status"


def run_gh(args: list[str]) -> str:
    """Run gh with the given args and return stdout as string."""
    cmd = ["gh"] + args
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def release_exists(tag: str) -> bool:
    try:
        run_gh(["release", "view", tag, "--json", "url"])
        return True
    except subprocess.CalledProcessError:
        return False


def fetch_runs(tag: str) -> list[dict]:
    fields = [
        "name",
        "displayTitle",
        "headBranch",
        "event",
        "status",
        "conclusion",
        "url",
        "createdAt",
        "databaseId",
    ]
    stdout = run_gh(
        [
            "run",
            "list",
            "--branch",
            tag,
            "--limit",
            "100",
            "--json",
            ",".join(fields),
        ]
    )
    return json.loads(stdout)


def filter_core_runs(runs: list[dict]) -> list[dict]:
    """Keep the most recent run for each core workflow name."""
    seen: set[str] = set()
    filtered: list[dict] = []
    for run in runs:
        name = run.get("name", "")
        if name in CORE_WORKFLOWS and name not in seen:
            seen.add(name)
            filtered.append(run)
    return filtered


def format_md_table(runs: list[dict]) -> str:
    lines = [
        "| Workflow | Run | Conclusion |",
        "|---|---|---|",
    ]
    for run in runs:
        name = run.get("name", "")
        run_id = run.get("databaseId", "")
        url = run.get("url", "")
        conclusion = run.get("conclusion", run.get("status", ""))
        if url:
            link = f"[{run_id}]({url})"
        else:
            link = str(run_id)
        lines.append(f"| {name} | {link} | {conclusion} |")
    return "\n".join(lines)


def format_json_runs(runs: list[dict]) -> list[dict]:
    return [
        {
            "name": run.get("name", ""),
            "run_id": run.get("databaseId"),
            "url": run.get("url", ""),
            "conclusion": run.get("conclusion", run.get("status", "")),
            "created_at": run.get("createdAt", ""),
        }
        for run in runs
    ]


def update_md_file(path: Path, table: str) -> None:
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^({re.escape(CI_SECTION_HEADER)}\n\n).*?(?=\n## |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    replacement = rf"\1{table}\n\n"
    new_content, count = pattern.subn(replacement, content)
    if count == 0:
        raise ValueError(f"Could not find section {CI_SECTION_HEADER!r} in {path}")
    path.write_text(new_content, encoding="utf-8")


def update_json_file(path: Path, runs: list[dict]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["ci_status"] = {
        "status": "recorded",
        "note": "Runs captured by scripts/update_release_assurance_ci.py",
        "runs": format_json_runs(runs),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update post-release assurance dossiers with CI run IDs."
    )
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v0.6.23")
    parser.add_argument("--md", required=True, help="Path to markdown assurance file")
    parser.add_argument("--json", required=True, help="Path to JSON assurance file")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually update the files (default is dry-run)",
    )
    args = parser.parse_args(argv)

    if not release_exists(args.tag):
        print(f"GitHub Release {args.tag} not found.", file=sys.stderr)
        return 1

    runs = filter_core_runs(fetch_runs(args.tag))
    table = format_md_table(runs)
    json_runs = format_json_runs(runs)

    md_path = Path(args.md)
    json_path = Path(args.json)

    if args.write:
        update_md_file(md_path, table)
        update_json_file(json_path, runs)
        print(f"Updated {md_path} and {json_path}")
    else:
        print("Dry run. Proposed markdown update:")
        print(table)
        print("\nProposed JSON runs:")
        print(json.dumps(json_runs, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
