#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


ALLOWED_REVIEW_LEDGER_STATUSES = {
    "paper_review_ledger_open",
    "paper_review_ledger_follow_up",
    "paper_review_ledger_rejected",
}
ALLOWED_DECISION_STATUSES = {
    "paper_follow_up_allowed",
    "needs_more_paper_evidence",
    "rejected_from_paper_follow_up",
    "manual_review_required",
    "blocked_by_missing_evidence",
}
FORBIDDEN_DOC_CLAIMS = (
    "guaranteed profit",
    "risk-free",
    "zero-risk",
    "live ready",
    "live-ready",
    "safe live trading",
    "production-ready trading",
    "approved for live",
    "outperform",
    "execute now",
    "submit order",
    "place order",
    "trade now",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    try:
        issues = check_all(Path(args.root))
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "error", "issues": [str(exc)]}, indent=2))
        else:
            print(f"Operational error: {exc}", file=sys.stderr)
        return 2

    if issues:
        if args.json:
            print(json.dumps({"status": "fail", "issues": issues}, indent=2))
        else:
            print("Paper human review ledger check FAILED")
            for issue in issues:
                print(f"  - {issue}")
        return 1

    if args.json:
        print(json.dumps({"status": "pass", "issues": []}, indent=2))
    else:
        print("Paper human review ledger check PASSED")
    return 0


def check_all(root: Path) -> list[str]:
    root = root.resolve()
    issues: list[str] = []
    issues.extend(_check_required_files(root))
    issues.extend(_check_demo_script(root))
    issues.extend(_check_docs(root))
    issues.extend(_check_release_metadata(root))
    issues.extend(_check_candidate_docs(root))
    issues.extend(_check_cli_command(root))
    return issues


def _check_required_files(root: Path) -> list[str]:
    required = [
        "docs/paper-human-review-ledger.md",
        "scripts/demo_paper_human_review_ledger.sh",
        "scripts/check_paper_human_review_ledger.py",
        "tests/test_paper_human_review_ledger.py",
    ]
    return [f"Required file missing: {item}" for item in required if not (root / item).exists()]


def _check_demo_script(root: Path) -> list[str]:
    issues: list[str] = []
    path = root / "scripts/demo_paper_human_review_ledger.sh"
    if not path.exists():
        return issues
    content = path.read_text(encoding="utf-8")
    mode = path.stat().st_mode
    if not mode & 0o111:
        issues.append("Demo script must be executable")
    if "portfolio-review-ledger" not in content:
        issues.append("Demo script must use the paper human review ledger command")
    if "--mode live" in content:
        issues.append("Demo script must not use live mode")
    if re.search(r"\b(broker sync|submit-order|approve-order)\b", content):
        issues.append("Demo script must not call broker/order commands")
    if re.search(r"\b(research run|simulate-provider|review-response)\b", content):
        issues.append("Demo script must not call provider workflows")
    if re.search(r"(API_KEY|SECRET|TOKEN|PASSWORD|ACCOUNT_ID)", content):
        issues.append("Demo script must not reference credential-like names")
    if "git tag" in content or "gh release create" in content:
        issues.append("Demo script must not create tags or releases")
    if "twine" + " upload" in content or re.search(r"\bpip\s+publish\b", content):
        issues.append("Demo script must not publish distributions")
    if "network calls" not in content.lower():
        issues.append("Demo script must state no network calls")
    if re.search(r"\b(gmail|slack|telegram|calendar)\b", content, re.IGNORECASE):
        issues.append("Demo script must not reference notification services")
    if "non-executable" not in content.lower():
        issues.append("Demo script must state output is non-executable")
    if "no real human approval" not in content.lower():
        issues.append("Demo script must state no real human approval")
    return issues


def _check_docs(root: Path) -> list[str]:
    issues: list[str] = []
    path = root / "docs/paper-human-review-ledger.md"
    if not path.exists():
        return issues
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    required_phrases = [
        "v0.6.15 planning line",
        "paper-only",
        "offline/no-provider/no-broker/no-network",
        "not financial advice",
        "not live ready",
        "not a profit guarantee",
        "no broker submission",
        "no provider calls",
        "no real notifications",
        "no orders generated",
        "no account-specific instructions",
        "no absolute safety",
        "no claims that risk is eliminated",
        "no live-readiness claim",
        "no autonomous live trading readiness",
        "human review is required",
        "non-executable",
        "no real human approval",
        "paper-human-review-ledger.json",
        "paper-human-review-ledger.md",
        "simulated",
    ]
    for phrase in required_phrases:
        if phrase not in lower:
            issues.append(f"Docs missing required phrase: {phrase}")
    for status in ALLOWED_REVIEW_LEDGER_STATUSES:
        if status not in text:
            issues.append(f"Docs missing allowed review ledger status: {status}")
    for status in ALLOWED_DECISION_STATUSES:
        if status not in text:
            issues.append(f"Docs missing allowed decision status: {status}")
    for claim in FORBIDDEN_DOC_CLAIMS:
        if claim in lower and f"not {claim}" not in lower and f"no {claim}" not in lower:
            issues.append(f"Docs must not claim {claim}")
    return issues


def _check_release_metadata(root: Path) -> list[str]:
    issues: list[str] = []
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    init_file = (root / "src/atlas_agent/__init__.py").read_text(encoding="utf-8")
    if 'version = "0.6.16"' not in pyproject and 'version = "0.6.17"' not in pyproject and 'version = "0.6.18"' not in pyproject and 'version = "0.6.19"' not in pyproject:
        issues.append("pyproject.toml source/package version must be 0.6.16, 0.6.17, 0.6.18, or 0.6.19")
    if '__version__ = "0.6.16"' not in init_file and '__version__ = "0.6.17"' not in init_file and '__version__ = "0.6.18"' not in init_file and '__version__ = "0.6.19"' not in init_file:
        issues.append("src/atlas_agent/__init__.py version must be 0.6.16, 0.6.17, 0.6.18, or 0.6.19")
    release_metadata = (root / "docs/release-status.md").read_text(encoding="utf-8") if (root / "docs/release-status.md").exists() else ""
    combined = "\n".join([
        pyproject,
        init_file,
        release_metadata,
        _read_if_exists(root / "docs/releases/v0.6.15-plan.md"),
        _read_if_exists(root / "docs/releases/v0.6.15-candidates.md"),
    ]).lower()
    if "v0.6.15 is released" in combined:
        issues.append("Docs must not claim v0.6.15 is released")
    if "pypi published: true" in combined:
        issues.append("Docs must not claim PyPI publication")
    return issues


def _check_candidate_docs(root: Path) -> list[str]:
    issues: list[str] = []
    plan_paths = [
        root / "docs/releases/v0.6.15-plan.md",
        root / "docs/releases/v0.6.15-candidates.md",
        root / "docs/releases/v0.6.15-candidates.json",
    ]
    for path in plan_paths:
        if not path.exists():
            issues.append(f"Candidate planning file missing: {path.relative_to(root)}")
            continue
        content = path.read_text(encoding="utf-8")
        lower = content.lower()
        if "cand-001" not in lower:
            issues.append(f"CAND-001 missing from {path.relative_to(root)}")
        if "cand-002" not in lower:
            issues.append(f"CAND-002 missing from {path.relative_to(root)}")
        if "planning-only" not in lower:
            issues.append(f"Planning-only status missing from {path.relative_to(root)}")
        if "v0.6.15 is released" in lower:
            issues.append(f"Must not claim v0.6.15 is released in {path.relative_to(root)}")

    json_path = root / "docs/releases/v0.6.15-candidates.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        candidates = data.get("candidates", [])
        for candidate_id in ("CAND-001", "CAND-002"):
            cand = next((item for item in candidates if item.get("id") == candidate_id), None)
            if not cand:
                issues.append(f"{candidate_id} missing from v0.6.15 candidates JSON")
            elif cand.get("status") not in {"proposed", "implemented"}:
                issues.append(f"{candidate_id} must be listed as proposed/implemented in candidates JSON")
    return issues


def _check_cli_command(root: Path) -> list[str]:
    issues: list[str] = []
    cli_path = root / "src/atlas_agent/cli.py"
    if not cli_path.exists():
        issues.append("CLI source missing")
        return issues
    content = cli_path.read_text(encoding="utf-8")
    if "portfolio-review-ledger" not in content:
        issues.append("CLI must register portfolio-review-ledger command")
    if "build_paper_portfolio_review_ledger" not in content:
        issues.append("CLI must import build_paper_portfolio_review_ledger")
    if "write_portfolio_review_ledger_reports" not in content:
        issues.append("CLI must import write_portfolio_review_ledger_reports")
    return issues


def _read_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


if __name__ == "__main__":
    sys.exit(main())
