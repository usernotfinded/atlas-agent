#!/usr/bin/env python3
"""Static check for paper strategy evaluation (CAND-025).

Deterministic, local-only, read-only. Does not:
- call the network
- call GitHub APIs
- publish, upload, tag, or push
- require credentials
- execute live trading
- call brokers or providers
- mutate files

Exit codes:
  0 = pass
  1 = blocking findings
  2 = operational error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from release_metadata import load_metadata, ReleaseMetadata
except ImportError:
    from scripts.release_metadata import load_metadata, ReleaseMetadata


EXPECTED_SOURCE_VERSION = "0.6.16"
EXPECTED_CURRENT_PUBLIC_TAG = "v0.6.16"
EXPECTED_NEXT_PLANNED_TAG = "v0.6.17"

REQUIRED_FILES = [
    "docs/paper-strategy-evaluation.md",
    "scripts/demo_paper_strategy_evaluation.sh",
    "docs/paper-provider-isolation.md",
    "docs/autonomous-paper-workflow.md",
    "docs/bounded-live-autonomy-governance.md",
]

RELATED_DOCS = [
    "docs/paper-strategy-evaluation.md",
    "docs/paper-provider-isolation.md",
    "docs/autonomous-paper-workflow.md",
    "docs/bounded-live-autonomy-governance.md",
]

REQUIRED_DOC_PHRASES = {
    "docs/paper-strategy-evaluation.md": [
        "v0.6.13 planning-line",
        "paper-only",
        "offline",
        "no-provider",
        "no-broker",
        "no-network",
        "not financial advice",
        "not live readiness",
        "no profit guarantee",
        "paper_candidate",
        "needs_more_testing",
        "rejected",
        "No decision promotes a strategy to live trading",
        "No provider calls",
        "No broker calls",
        "No credentials",
        "No live trading",
        "No autonomous live trading readiness",
        "autonomous-paper-workflow.md",
        "paper-provider-isolation.md",
        "bounded-live-autonomy-governance.md",
        "live-submit-safety-contract.md",
    ],
}

REQUIRED_DEMO_PHRASES = [
    "#!/usr/bin/env bash",
    "set -euo pipefail",
    "backtest compare",
    "data/sample/ohlcv.csv",
    "DEMO-SYMBOL",
    "strategy-evaluation.json",
    "strategy-evaluation.md",
    "paper_strategy_evaluation",
]

FORBIDDEN_SCRIPT_PHRASES = [
    "--mode live",
    "TRADING_MODE=live",
    "ENABLE_LIVE_TRADING=true",
    "enable_live_trading=true",
    "enable_live_submit=true",
    "broker sync",
    "submit-approved-order",
    "approve-order",
    "provider.execute",
    "execute_provider",
    "get_research_provider",
    "research run",
    "curl ",
    "wget ",
    "gh release create",
    "git tag ",
    "twine" + " upload",
    "python -m build",
]

FORBIDDEN_DOC_CLAIMS = [
    "live ready",
    "live-ready",
    "production ready",
    "production-ready trading",
    "safe to trade live",
    "safe live trading",
    "approved for live",
    "approved_for_live",
    "safe_to_trade_live",
    "live_ready",
    "production_ready",
    "guaranteed profit",
    "profit guaranteed",
    "guaranteed returns",
    "outperforms market",
    "beats the market",
    "beat the market",
    "autonomous trading ready",
    "autonomous live trading ready",
    "v0.6.13 is released",
    "released v0.6.13",
    "current public release v0.6.13",
    "tag v0.6.13 created",
    "github release v0.6.13 published",
    "v0.6.13 has been released",
    "pypi published",
    "published to pypi",
]

NEGATIVE_CONTEXT = (
    "not ",
    "does not",
    "never",
    "no ",
    "without",
    "forbid",
    "forbidden",
    "prohibit",
    "prohibited",
    "must not",
    "cannot",
    "not a ",
    "not an ",
    "not yet",
    "not enabled",
    "not released",
    "not implemented",
    "not claimed",
    "out of scope",
    "disabled by default",
    "fail-closed",
)

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bAPCA-[A-Z0-9]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{10,}", re.IGNORECASE),
    re.compile(
        r"\b(?:api[_-]?key|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{10,}",
        re.IGNORECASE,
    ),
]

PROVIDER_KEY_ASSIGNMENT = re.compile(
    r"\b(?:OPENAI|OPENROUTER|ANTHROPIC|GEMINI|GOOGLE|MOONSHOT|KIMI|XAI|GROK)_API_KEY\s*=",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _sentence_around(text: str, start: int, end: int) -> tuple[str, int]:
    s = start
    while s > 0 and text[s - 1] not in ".!?\n":
        s -= 1
    e = end
    while e < len(text) and text[e] not in ".!?\n":
        e += 1
    return text[s:e].strip(), s


def _has_negative_context(text_before_match: str) -> bool:
    compact = _compact(text_before_match)
    if any(marker in compact for marker in NEGATIVE_CONTEXT):
        return True
    tokens = re.sub(r"[^a-z]+", " ", compact).split()
    return any(
        token in {"not", "no", "never", "without", "cannot", "forbidden", "prohibited"}
        for token in tokens[-4:]
    )


def _add(
    checks: list[CheckResult],
    findings: list[str],
    *,
    name: str,
    ok: bool,
    pass_detail: str,
    fail_detail: str,
) -> None:
    if ok:
        checks.append(CheckResult(name, "pass", pass_detail))
    else:
        checks.append(CheckResult(name, "fail", fail_detail))
        findings.append(fail_detail)


def _check_required_files(repo_root: Path, checks: list[CheckResult], findings: list[str]) -> None:
    missing = [rel for rel in REQUIRED_FILES if not (repo_root / rel).exists()]
    _add(
        checks,
        findings,
        name="required_files",
        ok=not missing,
        pass_detail="Required paper strategy evaluation files exist.",
        fail_detail=f"Required files missing: {', '.join(missing)}",
    )


def _check_demo_script(repo_root: Path, checks: list[CheckResult], findings: list[str]) -> None:
    rel = "scripts/demo_paper_strategy_evaluation.sh"
    path = repo_root / rel
    if not path.exists():
        _add(
            checks,
            findings,
            name="demo_script",
            ok=False,
            pass_detail="Demo script exists.",
            fail_detail=f"Demo script missing: {rel}",
        )
        return

    text = _read(path)
    errors: list[str] = []
    if not os.access(path, os.X_OK):
        errors.append("demo script is not executable")
    if not text.startswith("#!/usr/bin/env bash\nset -euo pipefail\n"):
        errors.append("demo script missing safe bash shebang/settings")
    for phrase in REQUIRED_DEMO_PHRASES:
        if phrase not in text:
            errors.append(f"demo script missing required phrase: {phrase}")
    for phrase in FORBIDDEN_SCRIPT_PHRASES:
        if phrase in text:
            errors.append(f"demo script contains forbidden phrase: {phrase}")
    if PROVIDER_KEY_ASSIGNMENT.search(text):
        errors.append("demo script assigns a provider API key variable")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append("demo script contains a secret-like value")

    _add(
        checks,
        findings,
        name="demo_script",
        ok=not errors,
        pass_detail="Demo script is executable and paper/offline scoped.",
        fail_detail="; ".join(errors),
    )


def _check_docs(repo_root: Path, checks: list[CheckResult], findings: list[str]) -> None:
    errors: list[str] = []
    for rel, phrases in REQUIRED_DOC_PHRASES.items():
        path = repo_root / rel
        if not path.exists():
            errors.append(f"missing doc: {rel}")
            continue
        compact_text = _compact(_read(path))
        for phrase in phrases:
            if phrase.lower() not in compact_text:
                errors.append(f"{rel} missing required phrase: {phrase}")

    for rel in RELATED_DOCS:
        path = repo_root / rel
        if not path.exists():
            continue
        text = _read(path)
        lower = text.lower()
        normalized = lower.replace("-", " ")
        for phrase in FORBIDDEN_DOC_CLAIMS:
            for corpus in {lower, normalized}:
                for match in re.finditer(re.escape(phrase.replace("-", " ")), corpus):
                    sentence, sentence_start = _sentence_around(corpus, match.start(), match.end())
                    local_prefix = sentence[: max(0, match.start() - sentence_start)]
                    if not _has_negative_context(local_prefix):
                        errors.append(f"{rel} contains unsafe claim: {phrase}")
                        break

    _add(
        checks,
        findings,
        name="docs",
        ok=not errors,
        pass_detail="Paper strategy docs contain required safety boundaries.",
        fail_detail="; ".join(sorted(set(errors))),
    )


def _check_release_metadata(repo_root: Path, checks: list[CheckResult], findings: list[str]) -> dict[str, Any]:
    metadata_path = repo_root / "docs" / "releases" / "release-metadata.json"
    meta = ReleaseMetadata(load_metadata(metadata_path))

    with (repo_root / "pyproject.toml").open("rb") as handle:
        pyproject = tomllib.load(handle)
    pyproject_version = pyproject.get("project", {}).get("version")

    errors: list[str] = []
    if meta.source_version != EXPECTED_SOURCE_VERSION:
        errors.append(f"source_version expected {EXPECTED_SOURCE_VERSION}, got {meta.source_version}")
    if pyproject_version != EXPECTED_SOURCE_VERSION:
        errors.append(f"pyproject version expected {EXPECTED_SOURCE_VERSION}, got {pyproject_version}")
    if meta.current_public_release != EXPECTED_CURRENT_PUBLIC_TAG:
        errors.append(
            f"current_public_release expected {EXPECTED_CURRENT_PUBLIC_TAG}, got {meta.current_public_release}"
        )
    if meta.next_planned_release != EXPECTED_NEXT_PLANNED_TAG:
        errors.append(
            f"next_planned_release expected {EXPECTED_NEXT_PLANNED_TAG}, got {meta.next_planned_release}"
        )
    if meta.pypi_published is not False:
        errors.append("PyPI must remain unpublished")

    _add(
        checks,
        findings,
        name="release_metadata",
        ok=not errors,
        pass_detail="Release metadata is v0.6.16 public / v0.6.17 planning.",
        fail_detail="; ".join(errors),
    )
    return {
        "package_version": meta.source_version,
        "current_public_tag": meta.current_public_release,
        "next_planned_tag": meta.next_planned_release,
        "pypi_published": meta.pypi_published,
    }


def _check_candidate_docs(repo_root: Path, checks: list[CheckResult], findings: list[str]) -> None:
    errors: list[str] = []
    md_paths = [
        repo_root / "docs" / "releases" / "v0.6.13-candidates.md",
        repo_root / "docs" / "releases" / "v0.6.13-candidates.md",
        repo_root / "docs" / "releases" / "v0.6.13-plan.md",
    ]
    for path in md_paths:
        if not path.exists():
            errors.append(f"missing candidate doc: {path.relative_to(repo_root)}")
            continue
        text = _compact(_read(path))
        if "cand-025" not in text:
            errors.append(f"{path.relative_to(repo_root)} does not list CAND-025")
        if "v0.6.13 is released" in text or "current public release v0.6.13" in text:
            errors.append(f"{path.relative_to(repo_root)} claims v0.6.13 is released")

    candidates_json = repo_root / "docs" / "releases" / "v0.6.13-candidates.json"
    if not candidates_json.exists():
        errors.append("missing docs/releases/v0.6.13-candidates.json")
    else:
        data = json.loads(_read(candidates_json))
        candidates = data.get("candidates", [])
        cand025 = [item for item in candidates if item.get("id") == "CAND-025"]
        if not cand025:
            errors.append("v0.6.13-candidates.json does not list CAND-025")
        else:
            item = cand025[0]
            if item.get("implemented") is not True:
                errors.append("CAND-025 must be marked implemented in v0.6.13-candidates.json")
            if item.get("selected_for_v0613") is not True:
                errors.append("CAND-025 must be selected for v0.6.13 in v0.6.13-candidates.json")
        if data.get("source_version") != "0.6.12":
            errors.append("candidate JSON source_version must remain 0.6.12")
        if data.get("current_public_release") != "v0.6.12":
            errors.append("candidate JSON current_public_release must remain v0.6.12")
        if data.get("next_planned_release") != "v0.6.13":
            errors.append("candidate JSON next_planned_release must remain v0.6.13")
        if data.get("status") != "planning":
            errors.append("candidate JSON status must remain planning")

    _add(
        checks,
        findings,
        name="candidate_docs",
        ok=not errors,
        pass_detail="CAND-025 is recorded as implemented planning work without release claims.",
        fail_detail="; ".join(errors),
    )


def _check_cli_surface(repo_root: Path, checks: list[CheckResult], findings: list[str]) -> None:
    cli_path = repo_root / "src" / "atlas_agent" / "cli.py"
    eval_path = repo_root / "src" / "atlas_agent" / "backtest" / "evaluation.py"
    errors: list[str] = []
    if not cli_path.exists():
        errors.append("src/atlas_agent/cli.py missing")
    else:
        cli_text = _read(cli_path)
        for phrase in ("backtest_compare", "build_paper_strategy_evaluation", "write_strategy_evaluation_reports"):
            if phrase not in cli_text:
                errors.append(f"CLI missing compare wiring phrase: {phrase}")
    if not eval_path.exists():
        errors.append("src/atlas_agent/backtest/evaluation.py missing")
    else:
        eval_text = _read(eval_path)
        for phrase in (
            "paper_strategy_evaluation",
            "provider_required",
            "broker_required",
            "network_required",
            "live_readiness",
            "live_ready",
            "RiskManager blocked",
        ):
            if phrase not in eval_text:
                errors.append(f"evaluation module missing schema/safety phrase: {phrase}")

    _add(
        checks,
        findings,
        name="cli_surface",
        ok=not errors,
        pass_detail="CLI and evaluation module expose the paper strategy matrix.",
        fail_detail="; ".join(errors),
    )


def run_checks(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    checks: list[CheckResult] = []
    findings: list[str] = []

    _check_required_files(repo_root, checks, findings)
    _check_demo_script(repo_root, checks, findings)
    _check_docs(repo_root, checks, findings)
    metadata = _check_release_metadata(repo_root, checks, findings)
    _check_candidate_docs(repo_root, checks, findings)
    _check_cli_surface(repo_root, checks, findings)

    return {
        "passed": not findings,
        "errors": findings,
        "checks": [check.__dict__ for check in checks],
        **metadata,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    args = parser.parse_args(argv)

    try:
        result = run_checks()
    except Exception as exc:
        payload = {
            "passed": False,
            "operational_error": str(exc),
            "errors": [],
            "checks": [],
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Paper strategy evaluation check ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["passed"]:
        print("Paper strategy evaluation check PASSED")
        print(f"  Package version: {result['package_version']}")
        print(f"  Current public tag: {result['current_public_tag']}")
        print(f"  Next planned tag: {result['next_planned_tag']}")
        print(f"  PyPI published: {result['pypi_published']}")
    else:
        print("Paper strategy evaluation check FAILED")
        for error in result["errors"]:
            print(f"  - {error}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
