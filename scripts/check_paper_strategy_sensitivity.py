#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def check_paper_strategy_sensitivity(json_output: bool = False) -> int:
    issues = []
    
    docs_to_check = [
        "docs/paper-strategy-sensitivity.md",
        "docs/paper-strategy-evaluation.md",
        "docs/paper-provider-isolation.md",
        "docs/autonomous-paper-workflow.md",
        "docs/bounded-live-autonomy-governance.md",
    ]
    
    for doc in docs_to_check:
        if not (ROOT / doc).exists():
            issues.append(f"Missing required doc: {doc}")
            
    demo_script = ROOT / "scripts" / "demo_paper_strategy_sensitivity.sh"
    if not demo_script.exists():
        issues.append("Missing demo script: scripts/demo_paper_strategy_sensitivity.sh")
    else:
        if not os.access(demo_script, os.X_OK):
            issues.append("Demo script must be executable")
        content = demo_script.read_text()
        if "--mode live" in content:
            issues.append("Demo script must not use --mode live")
        if "data/sample" not in content:
            issues.append("Demo script must use sample/synthetic fixture")

    fixture = ROOT / "data" / "sample" / "ohlcv_extended.csv"
    if not fixture.exists():
        issues.append("Missing deterministic fixture: data/sample/ohlcv_extended.csv")

    doc_path = ROOT / "docs" / "paper-strategy-sensitivity.md"
    if doc_path.exists():
        content = doc_path.read_text()
        forbidden_claims = [
            "live ready",
            "production ready",
            "safe to trade live",
            "guaranteed profit",
            "outperforms market"
        ]
        for claim in forbidden_claims:
            if claim.lower() in content.lower():
                issues.append(f"Forbidden claim found in docs: {claim}")
        
        required_topics = [
            "paper-only",
            "offline",
            "not financial advice",
        ]
        for topic in required_topics:
            if topic not in content.lower():
                issues.append(f"Missing required phrasing in docs: {topic}")

    meta_path = ROOT / "docs" / "releases" / "v0.6.13-candidates.md"
    if meta_path.exists() and "v0.6.13 release" in meta_path.read_text().lower():
        issues.append("Candidate document must not claim v0.6.13 is released")

    # Output results
    if json_output:
        print(json.dumps({"status": "fail" if issues else "pass", "issues": issues}, indent=2))
        return 1 if issues else 0

    if issues:
        print("Paper strategy sensitivity check FAILED")
        for issue in issues:
            print(f"  - {issue}")
        return 1
        
    print("Paper strategy sensitivity check PASSED")
    return 0

if __name__ == "__main__":
    json_flag = "--json" in sys.argv
    sys.exit(check_paper_strategy_sensitivity(json_output=json_flag))
