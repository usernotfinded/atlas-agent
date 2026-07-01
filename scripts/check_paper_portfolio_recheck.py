#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


ALLOWED_DECISIONS = {
    "paper_review_clear",
    "paper_review_watchlist",
    "paper_recheck_required",
    "paper_rejected",
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
            print("Paper portfolio recheck ledger check FAILED")
            for issue in issues:
                print(f"  - {issue}")
        return 1

    if args.json:
        print(json.dumps({"status": "pass", "issues": []}, indent=2))
    else:
        print("Paper portfolio recheck ledger check PASSED")
    return 0


def check_all(root: Path) -> list[str]:
    root = root.resolve()
    issues: list[str] = []
    issues.extend(_check_required_files(root))
    issues.extend(_check_demo_script(root))
    issues.extend(_check_docs(root))
    issues.extend(_check_release_metadata(root))
    issues.extend(_check_candidate_docs(root))
    return issues


def _check_required_files(root: Path) -> list[str]:
    required = [
        "docs/paper-portfolio-recheck-ledger.md",
        "scripts/demo_paper_portfolio_recheck.sh",
        "scripts/check_paper_portfolio_recheck.py",
        "tests/test_paper_portfolio_recheck.py",
        "docs/paper-portfolio-monitoring.md",
        "scripts/demo_paper_portfolio_monitoring.sh",
        "scripts/check_paper_portfolio_monitoring.py",
        "tests/test_paper_portfolio_monitoring.py",
    ]
    return [f"Required file missing: {item}" for item in required if not (root / item).exists()]


def _check_demo_script(root: Path) -> list[str]:
    issues: list[str] = []
    path = root / "scripts/demo_paper_portfolio_recheck.sh"
    if not path.exists():
        return issues
    content = path.read_text(encoding="utf-8")
    mode = path.stat().st_mode
    if not mode & 0o111:
        issues.append("Demo script must be executable")
    if "portfolio-recheck" not in content:
        issues.append("Demo script must use the paper portfolio recheck command")
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
    return issues


def _check_docs(root: Path) -> list[str]:
    issues: list[str] = []
    path = root / "docs/paper-portfolio-recheck-ledger.md"
    if not path.exists():
        return issues
    text = path.read_text(encoding="utf-8")
    lower = text.lower()
    required_phrases = [
        "v0.6.14 planning line",
        "paper-only",
        "offline/no-provider/no-broker/no-network",
        "not financial advice",
        "not live readiness",
        "not a profit guarantee",
        "paper-portfolio-recheck-ledger.json",
        "paper-portfolio-review-queue.md",
        "no provider calls",
        "no broker calls",
        "no credentials",
        "no live trading",
        "no notifications sent",
        "no autonomous live trading readiness",
    ]
    for phrase in required_phrases:
        if phrase not in lower:
            issues.append(f"Docs missing required phrase: {phrase}")
    for decision in ALLOWED_DECISIONS:
        if decision not in text:
            issues.append(f"Docs missing allowed recheck decision: {decision}")
    for claim in FORBIDDEN_DOC_CLAIMS:
        if claim in lower and f"not {claim}" not in lower and f"no {claim}" not in lower:
            issues.append(f"Docs must not claim {claim}")
    return issues


def _check_release_metadata(root: Path) -> list[str]:
    issues: list[str] = []
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    init_file = (root / "src/atlas_agent/__init__.py").read_text(encoding="utf-8")
    if 'version = "0.6.16"' not in pyproject and 'version = "0.6.17"' not in pyproject and 'version = "0.6.18"' not in pyproject:
        issues.append("pyproject.toml source/package version must be 0.6.16, 0.6.17, or 0.6.18")
    if '__version__ = "0.6.16"' not in init_file and '__version__ = "0.6.17"' not in init_file and '__version__ = "0.6.18"' not in init_file:
        issues.append("src/atlas_agent/__init__.py version must be 0.6.16, 0.6.17, or 0.6.18")
    release_metadata = (root / "docs/release-status.md").read_text(encoding="utf-8") if (root / "docs/release-status.md").exists() else ""
    combined = "\n".join([
        pyproject,
        init_file,
        release_metadata,
        _read_if_exists(root / "docs/releases/v0.6.14-plan.md"),
        _read_if_exists(root / "docs/releases/v0.6.14-candidates.md"),
    ]).lower()
    if "v0.6.14 is released" in combined:
        issues.append("Docs must not claim v0.6.14 is released")
    if "pypi published: true" in combined:
        issues.append("Docs must not claim PyPI publication")
    return issues


def _check_candidate_docs(root: Path) -> list[str]:
    issues: list[str] = []
    plan_paths = [
        root / "docs/releases/v0.6.14-plan.md",
        root / "docs/releases/v0.6.14-candidates.md",
        root / "docs/releases/v0.6.14-candidates.json",
    ]
    for path in plan_paths:
        if not path.exists():
            issues.append(f"Candidate planning file missing: {path.relative_to(root)}")
            continue
        content = path.read_text(encoding="utf-8")
        lower = content.lower()
        if "cand-004" not in lower:
            issues.append(f"CAND-004 missing from {path.relative_to(root)}")
        if "planning-only" not in lower:
            issues.append(f"Planning-only status missing from {path.relative_to(root)}")
        if "v0.6.14 is released" in lower:
            issues.append(f"Must not claim v0.6.14 is released in {path.relative_to(root)}")

    json_path = root / "docs/releases/v0.6.14-candidates.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        candidates = data.get("candidates", [])
        cand = next((item for item in candidates if item.get("id") == "CAND-004"), None)
        if not cand:
            issues.append("CAND-004 missing from v0.6.14 candidates JSON")
        elif cand.get("status") not in {"implemented", "current"}:
            issues.append("CAND-004 must be listed as implemented/current in candidates JSON")
    return issues


def _read_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


if __name__ == "__main__":
    sys.exit(main())
