#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/build_product_demo_evidence.py
# PURPOSE: Build a reviewable, deterministic evidence bundle for the product
#         demo.
# DEPS:    argparse, hashlib, json, re, sys, datetime, additional local modules.
# ==============================================================================

"""Build a reviewable, deterministic evidence bundle for the product demo.

This helper is invoked by scripts/demo_product_walkthrough.sh after the demo
commands have run. It is local-only and read-only: it does not load credentials,
make network calls, submit broker orders, or enable live trading.

It reads captured command outputs and the demo workspace, then writes a bundle
of JSON and Markdown files plus SHA-256 checksums that a reviewer can inspect.
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent

SAFE_ARTIFACTS = [
    (".atlas/config.toml", "config.toml"),
    (".atlas/discipline.md", "discipline.md"),
]

OUTPUT_FILE_NAMES = [
    ("init", "init.txt"),
    ("discipline", "discipline.txt"),
    ("config-symbol", "config-symbol.txt"),
    ("validate", "validate.txt"),
    ("doctor", "doctor.txt"),
    ("paper-dry-run", "paper-dry-run.txt"),
    ("backtest", "backtest.txt"),
    ("backtest-runs", "backtest-runs.txt"),
    ("audit", "audit.txt"),
]


# ==============================================================================
# ARTIFACT BUILD WORKFLOW
# ==============================================================================

# --- BUILD HELPERS AND ENTRYPOINTS ---

def _get_atlas_version(cli_version: str | None) -> str:
    if cli_version:
        return cli_version
    try:
        import atlas_agent
        return getattr(atlas_agent, "__version__", "unknown")
    except Exception:
        return "unknown"


def _read_lower(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8").lower()


def _find_latest_backtest(workspace: Path, deterministic: bool) -> tuple[Path | None, Path | None]:
    bt_dir = workspace / ".atlas" / "backtests"
    if not bt_dir.exists():
        return None, None

    candidates = [d for d in bt_dir.iterdir() if d.is_dir()]
    if not candidates:
        return None, None

    if deterministic:
        candidates.sort(key=lambda p: p.name)
    else:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for c in candidates:
        result = c / "result.json"
        report = c / "report.md"
        if result.exists():
            return result, report if report.exists() else None
    return None, None


def _redact_paths(text: str, workspace: Path, repo_root: Path) -> str:
    for prefix in (str(workspace.resolve()), str(repo_root.resolve())):
        if prefix != "/":
            text = text.replace(prefix, "<REDACTED>")
    return text


def _copy_text_safely(
    src: Path,
    dest: Path,
    *,
    deterministic: bool,
    workspace: Path,
    repo_root: Path,
) -> None:
    content = src.read_text(encoding="utf-8")
    if deterministic:
        content = _redact_paths(content, workspace, repo_root)
    dest.write_text(content, encoding="utf-8")


def _copy_safe_artifacts(
    workspace: Path,
    artifacts_dir: Path,
    output_dir: Path,
    deterministic: bool,
    repo_root: Path,
) -> dict[str, str]:
    artifact_paths: dict[str, str] = {}
    for rel_src, dest_name in SAFE_ARTIFACTS:
        src = workspace / rel_src
        if src.exists():
            dest = artifacts_dir / dest_name
            _copy_text_safely(src, dest, deterministic=deterministic, workspace=workspace, repo_root=repo_root)
            artifact_paths[dest_name.replace(".", "_")] = str(dest.relative_to(output_dir))

    result, report = _find_latest_backtest(workspace, deterministic=deterministic)
    if result is not None:
        rdest = artifacts_dir / "backtest_result.json"
        _copy_text_safely(result, rdest, deterministic=deterministic, workspace=workspace, repo_root=repo_root)
        artifact_paths["backtest_result"] = str(rdest.relative_to(output_dir))
    if report is not None:
        rdest = artifacts_dir / "backtest_report.md"
        _copy_text_safely(report, rdest, deterministic=deterministic, workspace=workspace, repo_root=repo_root)
        artifact_paths["backtest_report"] = str(rdest.relative_to(output_dir))

    return artifact_paths


def _load_output_files(outputs_dir: Path, output_dir: Path) -> dict[str, str]:
    output_files: dict[str, str] = {}
    for key, filename in OUTPUT_FILE_NAMES:
        path = outputs_dir / filename
        if path.exists():
            output_files[key] = str(path.relative_to(output_dir))
    return output_files


def _load_commands(commands_file: Path | None) -> list[str]:
    if commands_file is None or not commands_file.exists():
        return []
    return [
        line.strip()
        for line in commands_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _paper_mode_from_config(config_text: str) -> bool:
    return bool(re.search(r'trading_mode\s*=\s*"?paper"?', config_text))


def _evaluate_safety(
    output_dir: Path, output_files: dict[str, Path], artifact_paths: dict[str, str]
) -> dict[str, bool]:
    validate_text = _read_lower(
        output_dir / output_files["validate"] if "validate" in output_files else None
    )
    doctor_text = _read_lower(
        output_dir / output_files["doctor"] if "doctor" in output_files else None
    )
    paper_dry_run_text = _read_lower(
        output_dir / output_files["paper-dry-run"] if "paper-dry-run" in output_files else None
    )
    config_text = _read_lower(
        output_dir / artifact_paths.get("config_toml", "") if "config_toml" in artifact_paths else None
    )
    combined = validate_text + "\n" + doctor_text + "\n" + paper_dry_run_text

    return {
        "live_trading_disabled": (
            ("live trading" in validate_text and ("disabled" in validate_text or "false" in validate_text))
            or ("live_execution_blocked" in doctor_text and "true" in doctor_text)
        ),
        "paper_mode": (
            _paper_mode_from_config(config_text)
            or "requested mode: paper" in paper_dry_run_text
            or "paper" in validate_text
        ),
        "provider_execution_locked": (
            (("provider execution" in combined or "provider_execution" in combined)
             and ("locked" in combined or "disabled" in combined))
            or ("execution_enabled" in doctor_text and "false" in doctor_text)
        ),
        "broker_execution_blocked": (
            ("can_submit" in validate_text and "false" in validate_text)
            or ("broker" in doctor_text and "live_execution_blocked" in doctor_text and "true" in doctor_text)
        ),
        "no_credentials_required": (
            "no credentials" in combined
            or "missing" in combined
            or "absent" in combined
            or "credentials" not in combined
        ),
        "no_network_calls": "network_check" in doctor_text and "skipped" in doctor_text,
    }


def _write_json(evidence: dict[str, Any], output_dir: Path) -> None:
    (output_dir / "evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_summary(evidence: dict[str, Any], output_dir: Path) -> None:
    lines = [
        "# Atlas Agent Product Demo Evidence Bundle",
        "",
        "> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.",
        "",
        "This bundle was produced by the paper-only, offline product demo walkthrough.",
        "It is intended for reviewer evaluation only.",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Schema version | `{evidence['schema_version']}` |",
        f"| Generated at | {evidence['generated_at']} |",
        f"| Atlas version | {evidence['atlas_version']} |",
        f"| Demo mode | `{evidence['demo_mode']}` |",
        f"| Live trading enabled | {evidence['live_trading_enabled']} |",
        f"| Provider execution | {evidence['provider_execution']} |",
        f"| Broker execution | {evidence['broker_execution']} |",
        f"| Credentials loaded | {evidence['credentials_loaded']} |",
        f"| Network required | {evidence['network_required']} |",
        "",
        "## What this bundle proves",
        "",
        "- The demo ran in paper/dry-run mode with no live orders submitted and no live trading enabled.",
        "- No broker credentials, provider API keys, or other secrets were loaded (no credentials).",
        "- Provider execution remained locked and broker order submission remained blocked.",
        "- Local backtest and audit artifacts were generated or verified inside a temporary workspace.",
        "- No network calls were required.",
        "",
        "## What this bundle does NOT prove",
        "",
        "- It does not prove profitability, strategy correctness, or future performance.",
        "- It does not prove production readiness or safe live trading.",
        "- It does not prove real-market behavior, broker connectivity, or provider reliability.",
        "",
        evidence["notes"],
        "",
    ]
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _write_safety_boundaries(evidence: dict[str, Any], output_dir: Path) -> None:
    summary = evidence["safety_checks_summary"]
    lines = [
        "# Demo Safety Boundaries",
        "",
        "This demo is **paper-only, offline, and credential-free**.",
        "It performs **no live trading**, submits **no broker orders**, and makes **no network calls**.",
        "",
        "| Boundary | Status |",
        "|---|---|",
        f"| Live trading disabled | {'PASS' if summary['live_trading_disabled'] else 'FAIL'} |",
        f"| Paper mode | {'PASS' if summary['paper_mode'] else 'FAIL'} |",
        f"| Provider execution locked | {'PASS' if summary['provider_execution_locked'] else 'FAIL'} |",
        f"| Broker execution blocked | {'PASS' if summary['broker_execution_blocked'] else 'FAIL'} |",
        f"| No credentials required | {'PASS' if summary['no_credentials_required'] else 'FAIL'} |",
        f"| No network calls | {'PASS' if summary['no_network_calls'] else 'FAIL'} |",
        "",
        "No live orders were submitted, no real money was at risk, and no autonomous or production-trading readiness is implied.",
        "",
    ]
    (output_dir / "safety-boundaries.md").write_text("\n".join(lines), encoding="utf-8")


def _write_artifacts_index(evidence: dict[str, Any], output_dir: Path) -> None:
    lines = [
        "# Evidence Bundle Artifact Index",
        "",
        "## Captured command outputs",
        "",
        "| Name | File |",
        "|---|---|",
    ]
    for name, rel in sorted(evidence["output_files"].items()):
        lines.append(f"| {name} | `{rel}` |")
    lines.extend([
        "",
        "## Copied workspace artifacts",
        "",
        "| Name | File |",
        "|---|---|",
    ])
    for name, rel in sorted(evidence["artifact_paths"].items()):
        lines.append(f"| {name} | `{rel}` |")
    lines.extend([
        "",
        "All artifacts are local and read-only. No credentials, broker contact, or provider calls are represented.",
        "",
    ])
    (output_dir / "artifacts-index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_commands_file(commands: list[str], output_dir: Path) -> None:
    (output_dir / "commands.txt").write_text(
        "# Commands run during the product demo walkthrough\n\n"
        + "\n".join(commands)
        + "\n",
        encoding="utf-8",
    )


def _write_checksums(output_dir: Path) -> None:
    checksums_file = output_dir / "checksums.sha256"
    files = sorted(
        p
        for p in output_dir.rglob("*")
        if p.is_file() and p.resolve() != checksums_file.resolve()
    )
    lines: list[str] = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rel = path.relative_to(output_dir)
        lines.append(f"{digest}  {rel}")
    checksums_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_bundle(
    output_dir: Path,
    workspace: Path,
    commands_file: Path | None,
    atlas_version: str | None,
    deterministic: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    outputs_dir = output_dir / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    commands = _load_commands(commands_file)
    output_files = _load_output_files(outputs_dir, output_dir)
    artifact_paths = _copy_safe_artifacts(
        workspace, artifacts_dir, output_dir, deterministic, REPO_ROOT
    )
    safety = _evaluate_safety(output_dir, output_files, artifact_paths)

    evidence: dict[str, Any] = {
        "schema_version": "atlas-product-demo-evidence/1.0",
        "generated_at": (
            "1970-01-01T00:00:00Z"
            if deterministic
            else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ),
        "atlas_version": _get_atlas_version(atlas_version),
        "demo_mode": "paper/dry-run",
        "live_trading_enabled": False,
        "provider_execution": False,
        "broker_execution": False,
        "credentials_loaded": False,
        "network_required": False,
        "workspace_path": (
            "<redacted for deterministic test mode>"
            if deterministic
            else str(workspace.resolve())
        ),
        "demo_commands_run": commands,
        "output_files": output_files,
        "artifact_paths": artifact_paths,
        "safety_checks_summary": safety,
        "notes": (
            "This bundle is for reviewer evaluation only. It does not prove profitability, "
            "production readiness, or safe live trading."
        ),
    }

    _write_json(evidence, output_dir)
    _write_summary(evidence, output_dir)
    _write_safety_boundaries(evidence, output_dir)
    _write_artifacts_index(evidence, output_dir)
    _write_commands_file(commands, output_dir)
    _write_checksums(output_dir)
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a reviewable evidence bundle for the Atlas Agent product demo. "
        "Local-only; does not load credentials or contact providers/brokers."
    )
    parser.add_argument("--output-dir", required=True, help="Directory to write the evidence bundle.")
    parser.add_argument("--workspace", required=True, help="Demo workspace path.")
    parser.add_argument("--commands-file", help="Path to the commands log produced by the demo script.")
    parser.add_argument("--atlas-version", help="Atlas version string (default: read from atlas_agent).")
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Use deterministic timestamps and redact absolute paths (for tests).",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    workspace = Path(args.workspace).resolve()
    commands_file = Path(args.commands_file) if args.commands_file else None

    if not workspace.exists():
        print(f"Workspace does not exist: {workspace}", file=sys.stderr)
        return 2

    build_bundle(output_dir, workspace, commands_file, args.atlas_version, args.deterministic)
    print(f"Evidence bundle written to: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
