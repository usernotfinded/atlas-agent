import json
import sys
from pathlib import Path


def main() -> int:
    try:
        issues = check_all()
    except Exception as exc:
        print(f"Operational error: {exc}", file=sys.stderr)
        return 2

    is_json = "--json" in sys.argv

    if issues:
        if is_json:
            print(json.dumps({"status": "fail", "issues": issues}, indent=2))
        else:
            print("Paper portfolio proposal check FAILED")
            for issue in issues:
                print(f"  - {issue}")
        return 1

    if is_json:
        print(json.dumps({"status": "pass", "issues": []}, indent=2))
    else:
        print("Paper portfolio proposal check PASSED")

    return 0


def check_all() -> list[str]:
    issues: list[str] = []

    # 1. Required files
    required_files = [
        "docs/paper-portfolio-proposal.md",
        "scripts/demo_paper_portfolio_proposal.sh",
        "docs/paper-strategy-scorecard.md",
    ]

    for req in required_files:
        if not Path(req).exists():
            issues.append(f"Required file missing: {req}")

    # 2. Demo script validation
    demo_script = Path("scripts/demo_paper_portfolio_proposal.sh")
    if demo_script.exists():
        content = demo_script.read_text()
        if "--mode live" in content:
            issues.append("Demo script must not use --mode live")
        if "OPENAI_API_KEY" in content and 'export OPENAI_API_KEY=""' not in content:
            issues.append("Demo script must not leak or use real provider credentials")
        if "twine" + " upload" in content:
            issues.append("Demo script must not reference distribution upload")

    # 3. Docs validation
    docs = Path("docs/paper-portfolio-proposal.md")
    if docs.exists():
        content = docs.read_text().lower()
        if "guaranteed profit" in content:
            issues.append("Docs must not claim guaranteed profit")
        if "live ready" in content or "live-ready" in content:
            issues.append("Docs must not claim live ready")
        if "not financial advice" not in content:
            issues.append("Docs must include 'not financial advice'")
        if "paper-only" not in content:
            issues.append("Docs must state it is 'paper-only'")

    # 4. Release metadata and candidate docs
    # Source version check is external, but we can quickly check v0.6.14 claims
    plan_files = [
        "docs/releases/v0.6.14-plan.md",
        "docs/releases/v0.6.14-candidates.md",
        "docs/releases/v0.6.14-candidate-selection.md"
    ]
    for pf in plan_files:
        p = Path(pf)
        if p.exists() and "v0.6.14 is released" in p.read_text().lower():
            issues.append(f"Must not claim v0.6.14 is released in {pf}")

    return issues


if __name__ == "__main__":
    sys.exit(main())
