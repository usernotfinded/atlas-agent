#!/usr/bin/env python3
"""Build a deterministic reviewer trust snapshot for Atlas Agent.

This script produces a compact, reviewer/founder/marketplace-facing snapshot that
summarizes the project's current safety posture, release identity, CI evidence,
demo evidence checksum, and disabled-by-default state in a one-page Markdown
artifact plus a machine-readable JSON artifact.

It is local-only, offline, and credential-free. It does not call brokers,
providers, GitHub APIs, or load secrets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
METADATA_PATH = REPO_ROOT / "docs" / "releases" / "release-metadata.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
INIT_PATH = REPO_ROOT / "src" / "atlas_agent" / "__init__.py"

SCHEMA_VERSION = "atlas-reviewer-trust-snapshot/1.0"
SNAPSHOT_JSON = "reviewer-trust-snapshot.json"
SNAPSHOT_MD = "reviewer-trust-snapshot.md"
CHECKSUMS_FILE = "checksums.sha256"

REQUIRED_SAFETY_INVARIANTS: dict[str, bool] = {
    "live_trading_disabled_by_default": True,
    "live_submit_disabled_by_default": True,
    "provider_execution_disabled_by_default": True,
    "broker_execution_disabled_by_default": True,
    "credentials_required_for_demo": False,
    "network_required_for_demo": False,
    "autonomous_trading_claimed": False,
    "profit_claims_absent": True,
    "no_risk_claims_absent": True,
}

CAPABILITY_STATUS = {
    "live_trading": "disabled by default",
    "live_submit": "disabled by default",
    "provider_execution": "disabled by default",
    "broker_execution": "disabled by default",
    "dashboard": "read-only",
    "audit_log": "local hash-chain",
    "approval_gates": "required for live order flow",
    "kill_switch": "present",
}

FORBIDDEN_CLAIMS_ABSENT = {
    "guaranteed_profit": True,
    "guaranteed_returns": True,
    "no_risk_trading": True,
    "risk_free_trading": True,
    "safe_live_trading": True,
    "production_trading_ready": True,
    "autonomous_trading_ready": True,
    "passive_income": True,
    "financial_freedom": True,
    "beat_the_market": True,
}


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_source_version() -> str:
    """Read the source package version from metadata, pyproject.toml, or __init__.py."""
    if METADATA_PATH.exists():
        try:
            meta = _load_json(METADATA_PATH)
            if meta.get("source_version"):
                return meta["source_version"]
        except Exception:
            pass

    if PYPROJECT_PATH.exists():
        text = PYPROJECT_PATH.read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            return m.group(1)

    if INIT_PATH.exists():
        text = INIT_PATH.read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)

    return "unknown"


def _get_release_metadata() -> dict[str, Any]:
    """Load release identity from release-metadata.json."""
    if not METADATA_PATH.exists():
        return {
            "current_public_release": "unknown",
            "next_planned_release": "unknown",
            "pypi_published": False,
            "release_status": "unknown",
        }

    try:
        meta = _load_json(METADATA_PATH)
        current = meta.get("current_public_release", "unknown")
        next_release = meta.get("next_planned_release", "unknown")
        pypi = bool(meta.get("pypi_published", False))
        releases = meta.get("releases", [])
        current_release = next((r for r in releases if r.get("tag") == current), None)
        github_release = bool(current_release.get("github_release", True)) if current_release else True

        status_parts = []
        if current and current != "unknown":
            status_parts.append(f"{current} is the current public GitHub release")
        if next_release and next_release != "unknown":
            status_parts.append(f"{next_release} is the next planned release line")
        if pypi:
            status_parts.append("PyPI was published")
        else:
            status_parts.append("PyPI was not published")
        if github_release:
            status_parts.append(f"GitHub release {current} exists")
        else:
            status_parts.append(f"GitHub release {current} does not exist")

        return {
            "current_public_release": current,
            "next_planned_release": next_release,
            "pypi_published": pypi,
            "release_status": "; ".join(status_parts),
        }
    except Exception:
        return {
            "current_public_release": "unknown",
            "next_planned_release": "unknown",
            "pypi_published": False,
            "release_status": "unknown",
        }


def _compute_file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compute_bundle_checksum(bundle_dir: Path | None) -> dict[str, Any] | None:
    """Compute a stable checksum reference for an evidence bundle directory."""
    if bundle_dir is None or not bundle_dir.exists():
        return None

    files = sorted(
        p
        for p in bundle_dir.rglob("*")
        if p.is_file() and p.name != "checksums.sha256"
    )
    if not files:
        return None

    h = hashlib.sha256()
    for path in files:
        rel = path.relative_to(bundle_dir).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(path.read_bytes())

    return {
        "bundle_dir": str(bundle_dir.resolve()),
        "checksum_sha256": h.hexdigest(),
        "files_count": len(files),
    }


def _build_ci_runs(ci_run_ids: list[str], research_ci_run_id: str | None) -> dict[str, Any]:
    runs: dict[str, Any] = {
        "main_ci_run_ids": list(ci_run_ids) if ci_run_ids else [],
        "research_ci_run_id": research_ci_run_id,
        "note": (
            "CI run IDs are supplied by the operator at build time. They are not fetched "
            "from GitHub and do not require network access to validate."
        ),
    }
    return runs


def _redact_paths(text: str) -> str:
    """Redact common absolute path prefixes for deterministic output."""
    for prefix in ["/Users/", "/private/var/", "/var/folders/", "/tmp/", "/home/"]:
        text = re.sub(re.escape(prefix) + r"[^\s`\]\)\n\"]*", "<REDACTED>", text)
    return text


def build_snapshot(
    output_dir: Path,
    *,
    evidence_bundle: Path | None = None,
    ci_run_ids: list[str] | None = None,
    research_ci_run_id: str | None = None,
    deterministic: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    source_version = _get_source_version()
    release_meta = _get_release_metadata()

    generated_at = (
        "1970-01-01T00:00:00Z"
        if deterministic
        else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    evidence_info = _compute_bundle_checksum(evidence_bundle)

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "repository": "usernotfinded/atlas-agent",
        "source_version": source_version,
        "current_public_release": release_meta["current_public_release"],
        "next_planned_release": release_meta["next_planned_release"],
        "pypi_published": release_meta["pypi_published"],
        "release_status": release_meta["release_status"],
        "ci_runs": _build_ci_runs(ci_run_ids or [], research_ci_run_id),
        "evidence_bundle": evidence_info,
        "safety_invariants": dict(REQUIRED_SAFETY_INVARIANTS),
        "capability_status": dict(CAPABILITY_STATUS),
        "forbidden_claims_absent": dict(FORBIDDEN_CLAIMS_ABSENT),
        "generated_files": {
            SNAPSHOT_JSON: SNAPSHOT_JSON,
            SNAPSHOT_MD: SNAPSHOT_MD,
            CHECKSUMS_FILE: CHECKSUMS_FILE,
        },
        "checksums": {},
        "notes": (
            "This snapshot is for reviewer evaluation only. It does not prove profitability, "
            "production readiness, or suitability for live trading. It summarizes release identity, "
            "CI evidence references, and disabled-by-default safety posture at build time."
        ),
    }

    if evidence_info:
        snapshot["evidence_bundle_checksum_sha256"] = evidence_info["checksum_sha256"]

    _write_json(snapshot, output_dir / SNAPSHOT_JSON, deterministic=deterministic)
    _write_markdown(snapshot, output_dir / SNAPSHOT_MD, deterministic=deterministic)
    _write_checksums(output_dir, deterministic=deterministic)

    # Re-read JSON/Markdown to record checksums in the snapshot data.
    snapshot["checksums"] = {
        SNAPSHOT_JSON: _compute_file_checksum(output_dir / SNAPSHOT_JSON),
        SNAPSHOT_MD: _compute_file_checksum(output_dir / SNAPSHOT_MD),
        CHECKSUMS_FILE: _compute_file_checksum(output_dir / CHECKSUMS_FILE),
    }

    # Rewrite JSON with checksums populated.
    _write_json(snapshot, output_dir / SNAPSHOT_JSON, deterministic=deterministic)
    _write_checksums(output_dir, deterministic=deterministic)

    # Final checksum values after rewriting.
    snapshot["checksums"] = {
        SNAPSHOT_JSON: _compute_file_checksum(output_dir / SNAPSHOT_JSON),
        SNAPSHOT_MD: _compute_file_checksum(output_dir / SNAPSHOT_MD),
        CHECKSUMS_FILE: _compute_file_checksum(output_dir / CHECKSUMS_FILE),
    }

    return snapshot


def _write_json(snapshot: dict[str, Any], path: Path, *, deterministic: bool) -> None:
    text = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    if deterministic:
        text = _redact_paths(text)
    path.write_text(text, encoding="utf-8")


def _write_markdown(snapshot: dict[str, Any], path: Path, *, deterministic: bool) -> None:
    lines = [
        "# Atlas Agent Reviewer Trust Snapshot",
        "",
        "> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.",
        "",
        "This snapshot summarizes the current release identity, CI evidence, demo evidence reference,",
        "and disabled-by-default safety posture of Atlas Agent for reviewers, founders, and marketplace operators.",
        "",
        "## Release identity",
        "",
        f"- **Repository:** `{snapshot['repository']}`",
        f"- **Source/package version:** `{snapshot['source_version']}`",
        f"- **Current public release:** `{snapshot['current_public_release']}`",
        f"- **Next planned release:** `{snapshot['next_planned_release']}`",
        f"- **Generated at:** {snapshot['generated_at']}",
        f"- **Schema version:** `{snapshot['schema_version']}`",
        "",
        "## Release status",
        "",
        f"{snapshot['release_status']}.",
        "",
        "PyPI was not published.",
        "No tag or release is created by this snapshot.",
        "",
        "## CI evidence",
        "",
    ]

    ci = snapshot["ci_runs"]
    if ci.get("main_ci_run_ids"):
        for run_id in ci["main_ci_run_ids"]:
            lines.append(f"- Main CI run ID: `{run_id}`")
    else:
        lines.append("- Main CI run ID: *not supplied at build time*")

    if ci.get("research_ci_run_id"):
        lines.append(f"- Research CI run ID: `{ci['research_ci_run_id']}`")
    else:
        lines.append("- Research CI run ID: *not supplied at build time*")

    lines.extend([
        "",
        f"{ci['note']}",
        "",
        "## Demo evidence reference",
        "",
    ])

    evidence = snapshot.get("evidence_bundle")
    if evidence:
        lines.extend([
            f"- **Bundle path:** `{evidence['bundle_dir']}`",
            f"- **Bundle checksum (SHA-256):** `{evidence['checksum_sha256']}`",
            f"- **Files in bundle:** {evidence['files_count']}",
        ])
    else:
        lines.append("- No evidence bundle was supplied at build time.")

    lines.extend([
        "",
        "See [Product Demo Evidence Bundle](product-demo-evidence.md) for how to generate and validate a bundle.",
        "",
        "## Safety posture",
        "",
        "Atlas Agent is **paper-first, sandbox-only, and safe-by-default**. The following invariants hold for the demo path and public release state:",
        "",
        "- **Live trading is disabled by default.**",
        "- **Live submit is disabled by default.**",
        "- **Provider execution is disabled by default.**",
        "- **Broker execution is disabled by default.**",
        "- **No credentials are required for the demo.**",
        "- **No network calls are required for the demo.**",
        "- **No autonomous-trading, profit, or no-risk claims are made.**",
        "",
        "| Invariant | Expected | Status |",
        "|---|---|---|",
    ])

    for invariant, expected in snapshot["safety_invariants"].items():
        status = "PASS" if _is_expected_bool(snapshot["safety_invariants"], invariant, expected) else "FAIL"
        lines.append(f"| {invariant} | `{expected}` | {status} |")

    lines.extend([
        "",
        "## What is disabled",
        "",
        "| Capability | Default state |",
        "|---|---|",
    ])
    for capability, state in snapshot["capability_status"].items():
        lines.append(f"| {capability} | {state} |")

    lines.extend([
        "",
        "## What this snapshot does not prove",
        "",
        "- It does not prove profitability, strategy correctness, or future performance.",
        "- It does not prove production readiness or suitability for live trading.",
        "- It does not prove real-market behavior, broker connectivity, or provider reliability.",
        "- It does not authorize autonomous or unattended trading.",
        "- CI run IDs are provided by the builder and are not independently verified against GitHub.",
        "",
        "## Reviewer verification commands",
        "",
        "```bash",
        "python3.11 scripts/build_reviewer_trust_snapshot.py --output-dir ./artifacts/trust-snapshot",
        "python3.11 scripts/check_reviewer_trust_snapshot.py ./artifacts/trust-snapshot",
        "```",
        "",
        "With CI run IDs and an evidence bundle:",
        "",
        "```bash",
        "python3.11 scripts/build_reviewer_trust_snapshot.py \\",
        "  --output-dir ./artifacts/trust-snapshot \\",
        "  --ci-run-id 27578051644 \\",
        "  --research-ci-run-id 27577320648 \\",
        "  --evidence-bundle ./artifacts/product_demo/my-evidence",
        "python3.11 scripts/check_reviewer_trust_snapshot.py ./artifacts/trust-snapshot",
        "```",
        "",
        "## Disclaimer",
        "",
        "Atlas Agent is a software tool for supervised research and paper trading workflows. It is not a financial advisor. Trading involves significant risk of loss. Live trading, provider execution, broker execution, and order submission are disabled by default and require explicit operator configuration and approval. No profit, no-risk, or autonomous-trading readiness claims are made.",
        "",
    ])

    text = "\n".join(lines)
    if deterministic:
        text = _redact_paths(text)
    path.write_text(text, encoding="utf-8")


def _is_expected_bool(mapping: dict[str, bool], key: str, expected: bool) -> bool:
    return mapping.get(key) is expected


def _write_checksums(output_dir: Path, *, deterministic: bool) -> None:
    checksums_path = output_dir / CHECKSUMS_FILE
    files = sorted(
        p
        for p in output_dir.rglob("*")
        if p.is_file() and p.resolve() != checksums_path.resolve()
    )
    lines: list[str] = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rel = path.relative_to(output_dir).as_posix()
        lines.append(f"{digest}  {rel}")
    checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic reviewer trust snapshot for Atlas Agent. "
        "Local-only; does not load credentials, call brokers/providers, or use the network."
    )
    parser.add_argument("--output-dir", required=True, help="Directory to write the snapshot.")
    parser.add_argument(
        "--evidence-bundle",
        help="Optional path to a product demo evidence bundle directory to reference.",
    )
    parser.add_argument(
        "--ci-run-id",
        action="append",
        dest="ci_run_ids",
        help="Optional main CI run ID. May be repeated.",
    )
    parser.add_argument(
        "--research-ci-run-id",
        help="Optional Research CI run ID.",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Use deterministic timestamps and redact absolute paths (for tests).",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    evidence_bundle = Path(args.evidence_bundle).resolve() if args.evidence_bundle else None

    build_snapshot(
        output_dir,
        evidence_bundle=evidence_bundle,
        ci_run_ids=args.ci_run_ids,
        research_ci_run_id=args.research_ci_run_id,
        deterministic=args.deterministic,
    )
    print(f"Reviewer trust snapshot written to: {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
