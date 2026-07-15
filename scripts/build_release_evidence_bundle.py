#!/usr/bin/env python3
# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    scripts/build_release_evidence_bundle.py
# PURPOSE: Build a deterministic local release evidence bundle.
# DEPS:    argparse, json, os, subprocess, sys, datetime, additional local
#         modules.
# ==============================================================================

"""Build a deterministic local release evidence bundle.

This script gathers version, git, safety, and check-command evidence into a
single JSON and Markdown report. It does not call providers, brokers, network
endpoints, or load credentials.

Usage:
    python3.11 scripts/build_release_evidence_bundle.py
    python3.11 scripts/build_release_evidence_bundle.py --json
    python3.11 scripts/build_release_evidence_bundle.py --skip-slow
    python3.11 scripts/build_release_evidence_bundle.py --include-quick-check
"""

# --- IMPORTS ---

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# --- CONFIGURATION AND CONSTANTS ---

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON_BIN = os.environ.get("PYTHON_BIN", sys.executable)
# Provide a fallback module path injection for scripts directory imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from release_metadata import load_metadata, ReleaseMetadata
except ImportError:
    from scripts.release_metadata import load_metadata, ReleaseMetadata

_metadata_path = REPO_ROOT / "docs" / "releases" / "release-metadata.json"
_meta = ReleaseMetadata(load_metadata(_metadata_path))

PACKAGE_VERSION = _meta.source_version
PUBLIC_STABLE_TAG = _meta.historical_stable_baseline or "v0.5.8"

DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "release_evidence"

_FAST_CHECKS: list[tuple[str, list[str]]] = [
    ("check_version_consistency", [PYTHON_BIN, "scripts/check_version_consistency.py"]),
    ("check_forbidden_claims", [PYTHON_BIN, "scripts/check_forbidden_claims.py"]),
    ("check_public_docs_consistency", [PYTHON_BIN, "scripts/check_public_docs_consistency.py"]),
    ("check_public_launch_readiness", [PYTHON_BIN, "scripts/check_public_launch_readiness.py"]),
    ("check_stable_release_decision", [PYTHON_BIN, "scripts/check_stable_release_decision.py"]),
    ("check_cli_command_compatibility", [PYTHON_BIN, "scripts/check_cli_command_compatibility.py"]),
]

_SLOW_CHECKS: list[tuple[str, list[str]]] = [
    ("smoke_reviewer_golden_path", [PYTHON_BIN, "scripts/smoke_reviewer_golden_path.py", "--json", "--skip-release-check"]),
]

_OPTIONAL_CHECKS: list[tuple[str, list[str]]] = [
    ("release_check_quick", ["./scripts/release_check.sh", "--quick"]),
]

_PROTECTED_BOUNDARIES = [
    "src/atlas_agent/config",
    "src/atlas_agent/brokers",
    "src/atlas_agent/execution",
    "src/atlas_agent/safety",
    "src/atlas_agent/risk",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ==============================================================================
# ARTIFACT BUILD WORKFLOW
# ==============================================================================

# --- BUILD HELPERS AND ENTRYPOINTS ---

def _redact(text: str) -> str:
    """Redact absolute paths and credential-like strings from text."""
    home = str(Path.home())
    replacements = [
        (str(REPO_ROOT), "<REPO_ROOT>"),
        (home, "<HOME>"),
        ("/Users/", "<HOME>/"),
        ("/private/var/", "<TEMP>/"),
        ("/var/folders/", "<TEMP>/"),
        ("/tmp/", "<TEMP>/"),
        ("/var/tmp/", "<TEMP>/"),
    ]
    redacted = text
    for prefix, replacement in replacements:
        redacted = redacted.replace(prefix, replacement)
    lines = []
    for line in redacted.splitlines(keepends=True):
        lower = line.lower()
        if any(k in lower for k in ("api_key", "apikey", "secret", "password", "token")):
            if ":" in line:
                label, _ = line.rsplit(":", 1)
                lines.append(f"{label}: <REDACTED>\n")
            else:
                lines.append("<REDACTED>\n")
        else:
            lines.append(line)
    return "".join(lines)


def _run(cmd: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env={
            **dict(os.environ),
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "ATLAS_CI": "1",
        },
    )
    return result.returncode, result.stdout, result.stderr


def _git_rev_parse(ref: str) -> str:
    rc, out, _ = _run(["git", "rev-parse", ref])
    return out.strip() if rc == 0 else ""


def _git_branch() -> str:
    rc, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return out.strip() if rc == 0 else ""


def _git_status_short() -> str:
    rc, out, _ = _run(["git", "status", "--short"])
    return out if rc == 0 else ""


def _git_diff_check() -> tuple[int, str]:
    rc, out, err = _run(["git", "diff", "--check"])
    return rc, (out + err)


def _git_diff_name_status_since_tag(tag: str) -> str:
    rc, out, _ = _run(["git", "diff", f"{tag}..HEAD", "--name-status"])
    return out if rc == 0 else ""


def _protected_boundary_diff(tag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for boundary in _PROTECTED_BOUNDARIES:
        rc, out, _ = _run(["git", "diff", f"{tag}..HEAD", "--name-status", "--", boundary])
        result[boundary] = out.strip()
    return result


def _read_pyproject_version() -> str | None:
    try:
        import tomllib
        with open(REPO_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version")
    except Exception:
        return None


def _read_init_version() -> str | None:
    init_path = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"
    try:
        text = init_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------


def _gather_evidence(
    *,
    skip_slow: bool,
    include_quick_check: bool,
) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    current_branch = _git_branch()
    current_commit = _git_rev_parse("HEAD")
    working_tree = _git_status_short()
    working_tree_clean = working_tree.strip() == ""

    diff_check_rc, diff_check_out = _git_diff_check()
    diff_check_clean = diff_check_rc == 0 and diff_check_out.strip() == ""

    changed_since_tag = _git_diff_name_status_since_tag(PUBLIC_STABLE_TAG)
    protected_diffs = _protected_boundary_diff(PUBLIC_STABLE_TAG)
    protected_boundaries_clean = all(d.strip() == "" for d in protected_diffs.values())

    pyproject_version = _read_pyproject_version()
    init_version = _read_init_version()

    checks: list[dict[str, Any]] = []
    all_passed = True

    for name, cmd in _FAST_CHECKS:
        rc, out, err = _run(cmd)
        passed = rc == 0
        if not passed:
            all_passed = False
        checks.append(
            {
                "name": name,
                "command": cmd,
                "exit_code": rc,
                "passed": passed,
                "stdout_redacted": _redact(out),
                "stderr_redacted": _redact(err),
            }
        )

    if not skip_slow:
        for name, cmd in _SLOW_CHECKS:
            rc, out, err = _run(cmd)
            passed = rc == 0
            if not passed:
                all_passed = False
            checks.append(
                {
                    "name": name,
                    "command": cmd,
                    "exit_code": rc,
                    "passed": passed,
                    "stdout_redacted": _redact(out),
                    "stderr_redacted": _redact(err),
                }
            )

    if include_quick_check:
        for name, cmd in _OPTIONAL_CHECKS:
            rc, out, err = _run(cmd)
            passed = rc == 0
            if not passed:
                all_passed = False
            checks.append(
                {
                    "name": name,
                    "command": cmd,
                    "exit_code": rc,
                    "passed": passed,
                    "stdout_redacted": _redact(out),
                    "stderr_redacted": _redact(err),
                }
            )

    return {
        "passed": all_passed and diff_check_clean,
        "generated_at": generated_at,
        "package_version": pyproject_version or init_version or PACKAGE_VERSION,
        "public_stable_tag": PUBLIC_STABLE_TAG,
        "current_branch": current_branch,
        "current_commit": current_commit,
        "working_tree_clean": working_tree_clean,
        "diff_check_clean": diff_check_clean,
        "changed_since_v0_5_7": changed_since_tag.strip().splitlines(),
        "protected_boundaries_clean": protected_boundaries_clean,
        "protected_boundaries": {
            k: v.strip().splitlines() if v.strip() else []
            for k, v in protected_diffs.items()
        },
        "checks": checks,
        "safety_summary": {
            "provider_execution_enabled": False,
            "broker_execution_enabled": False,
            "live_trading_enabled_by_default": False,
            "credentials_loaded": False,
            "network_calls_required": False,
        },
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _build_markdown(evidence: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Release Evidence Bundle")
    lines.append("")
    lines.append("> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    status = "PASSED" if evidence["passed"] else "FAILED"
    lines.append(f"- **Overall status:** {status}")
    lines.append(f"- **Generated at:** {evidence['generated_at']}")
    lines.append(f"- **Package version:** {evidence['package_version']}")
    lines.append(f"- **Public stable tag:** {evidence['public_stable_tag']}")
    lines.append(f"- **Current branch:** {evidence['current_branch']}")
    lines.append(f"- **Current commit:** `{evidence['current_commit']}`")
    lines.append(f"- **Working tree clean:** {evidence['working_tree_clean']}")
    lines.append(f"- **Diff check clean:** {evidence['diff_check_clean']}")
    lines.append(f"- **Protected boundaries clean:** {evidence['protected_boundaries_clean']}")
    lines.append("")
    lines.append("## Evidence Checks")
    lines.append("")
    lines.append("| Check | Exit Code | Passed |")
    lines.append("|-------|-----------|--------|")
    for check in evidence["checks"]:
        icon = "✓" if check["passed"] else "✗"
        lines.append(f"| {check['name']} | {check['exit_code']} | {icon} |")
    lines.append("")

    failed = [c for c in evidence["checks"] if not c["passed"]]
    if failed:
        lines.append("### Failed Checks")
        lines.append("")
        for check in failed:
            lines.append(f"#### {check['name']} (exit {check['exit_code']})")
            lines.append("```")
            if check["stdout_redacted"]:
                lines.append(check["stdout_redacted"])
            if check["stderr_redacted"]:
                lines.append(check["stderr_redacted"])
            lines.append("```")
            lines.append("")

    baseline = evidence.get("public_stable_tag", PUBLIC_STABLE_TAG)
    lines.append(f"## Changed Files Since {baseline}")
    lines.append("")
    changed_since = evidence.get("changed_since_v0_5_7", [])
    if changed_since:
        lines.append("```")
        for line in changed_since:
            lines.append(line)
        lines.append("```")
    else:
        lines.append(f"No changes since {baseline}.")
    lines.append("")

    lines.append("## Protected Boundary Status")
    lines.append("")
    for boundary, changes in evidence["protected_boundaries"].items():
        icon = "✓" if not changes else "✗"
        lines.append(f"- **{boundary}**: {icon}")
        if changes:
            for line in changes:
                lines.append(f"  - `{line}`")
    lines.append("")

    lines.append("## Safety Summary")
    lines.append("")
    ss = evidence["safety_summary"]
    lines.append(f"- Provider execution enabled: {ss['provider_execution_enabled']}")
    lines.append(f"- Broker execution enabled: {ss['broker_execution_enabled']}")
    lines.append(f"- Live trading enabled by default: {ss['live_trading_enabled_by_default']}")
    lines.append(f"- Credentials loaded: {ss['credentials_loaded']}")
    lines.append(f"- Network calls required: {ss['network_calls_required']}")
    lines.append("")

    lines.append("## Reviewer Notes")
    lines.append("")
    lines.append("- This bundle is a local-only snapshot. It does not prove trading safety, profitability, or readiness for unattended deployment.")
    lines.append("- Live trading remains disabled by default.")
    lines.append("- Provider execution remains locked unless explicit manual unlock steps are completed.")
    lines.append("- Broker execution remains blocked unless explicit opt-in gates pass.")
    lines.append("")

    lines.append("## Non-Goals")
    lines.append("")
    lines.append("- This bundle does not replace the full release checklist (`docs/release-checklist.md`).")
    lines.append("- It does not execute provider calls, broker sync, or order submission.")
    lines.append("- It does not load API keys or secrets.")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local release evidence bundle for Atlas Agent"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope to stdout")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write evidence artifacts",
    )
    parser.add_argument(
        "--skip-slow",
        action="store_true",
        help="Skip slow checks (e.g. reviewer golden-path smoke)",
    )
    parser.add_argument(
        "--include-quick-check",
        action="store_true",
        help="Include release_check.sh --quick (slow)",
    )
    args = parser.parse_args()

    evidence = _gather_evidence(
        skip_slow=args.skip_slow,
        include_quick_check=args.include_quick_check,
    )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "evidence.json"
    md_path = output_dir / "evidence.md"

    json_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8"
    )
    md_path.write_text(_build_markdown(evidence), encoding="utf-8")

    if args.json:
        print(json.dumps(evidence, indent=2, sort_keys=True))
    else:
        print("=" * 60)
        print("Release Evidence Bundle")
        print("=" * 60)
        status = "PASSED" if evidence["passed"] else "FAILED"
        print(f"Status: {status}")
        print(f"Version: {evidence['package_version']}")
        print(f"Branch: {evidence['current_branch']}")
        print(f"Commit: {evidence['current_commit']}")
        print(f"Working tree clean: {evidence['working_tree_clean']}")
        print(f"Protected boundaries clean: {evidence['protected_boundaries_clean']}")
        print(f"Checks run: {len(evidence['checks'])}")
        print(f"Artifacts written to: {output_dir}")
        print("=" * 60)

    return 0 if evidence["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
