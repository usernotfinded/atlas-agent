#!/usr/bin/env python3.11
import sys
import json
import os
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Check CAND-006 paper portfolio replay evidence artifacts.")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    docs_dir = repo_root / "docs"
    scripts_dir = repo_root / "scripts"
    tests_dir = repo_root / "tests"
    
    findings = []
    
    # Check Required Files
    required_files = [
        docs_dir / "paper-portfolio-replay.md",
        scripts_dir / "demo_paper_portfolio_replay.sh",
        tests_dir / "test_paper_portfolio_replay.py"
    ]
    
    for req_file in required_files:
        if not req_file.exists():
            findings.append(f"Required file missing: {req_file.relative_to(repo_root)}")

    # Check Demo Script
    demo_script = scripts_dir / "demo_paper_portfolio_replay.sh"
    if demo_script.exists():
        if not os.access(demo_script, os.X_OK):
            findings.append("demo_paper_portfolio_replay.sh is not executable.")
        content = demo_script.read_text()
        if "--mode live" in content:
            findings.append("demo_paper_portfolio_replay.sh must not use --mode live.")
        if "atlas submit" in content or "atlas execute" in content:
            findings.append("demo_paper_portfolio_replay.sh must not call order submission commands.")
        if "twine " + "upload" in content or "git tag" in content:
            findings.append("demo_paper_portfolio_replay.sh must not create tags or releases.")
        
    # Check Docs
    doc_file = docs_dir / "paper-portfolio-replay.md"
    if doc_file.exists():
        content = doc_file.read_text().lower()
        required_phrases = [
            "paper-only",
            "no-provider",
            "no-broker",
            "not financial advice",
            "no live readiness",
            "no profit guarantee"
        ]
        for phrase in required_phrases:
            if phrase not in content:
                findings.append(f"Doc missing required safety phrase: '{phrase}'")
                
        forbidden_phrases = [
            "guaranteed profit",
            "live ready",
            "production ready",
            "safe to trade live"
        ]
        for phrase in forbidden_phrases:
            if phrase in content:
                findings.append(f"Doc contains forbidden phrase: '{phrase}'")

    if args.json:
        result = {
            "check": "paper_portfolio_replay",
            "passed": len(findings) == 0,
            "findings": findings
        }
        print(json.dumps(result, indent=2))
    else:
        if findings:
            print("check_paper_portfolio_replay.py FAILED:")
            for f in findings:
                print(f" - {f}")
        else:
            print("check_paper_portfolio_replay.py PASSED.")

    sys.exit(1 if findings else 0)

if __name__ == "__main__":
    main()
