"""Tests for the bounded autonomy governance checker.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_bounded_autonomy_governance.py"


def _run_script(args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT)]
    if args:
        cmd.extend(args)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_script_passes_on_repo() -> None:
    """The checker must pass against the current repository state."""
    result = _run_script()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASSED" in result.stdout


def test_json_output() -> None:
    """JSON mode must report success and include version fields."""
    result = _run_script(["--json"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"passed": true' in result.stdout
    assert '"package_version":' in result.stdout
    assert '"current_public_tag":' in result.stdout
    assert '"next_planned_tag":' in result.stdout


def test_required_files_missing(tmp_path: Path) -> None:
    """Missing governance files should produce errors."""
    from scripts import check_bounded_autonomy_governance as checker

    with patch.object(checker, "GOVERNANCE_DOC", tmp_path / "missing.md"), \
         patch.object(checker, "ROADMAP_DOC", tmp_path / "missing2.md"), \
         patch.object(checker, "CANDIDATE_SELECTION_DOC", tmp_path / "missing3.md"):
        errors = checker._check_required_files()
        assert len(errors) == 3
        assert "governance file missing" in errors[0]


def test_governance_doc_required_phrases(tmp_path: Path) -> None:
    """A governance doc missing required phrases must fail."""
    from scripts import check_bounded_autonomy_governance as checker

    gov = tmp_path / "bounded-live-autonomy-governance.md"
    gov.write_text("# Title\n\nSome unrelated text.\n")

    with patch.object(checker, "GOVERNANCE_DOC", gov):
        errors = checker._check_governance_doc()
        assert any("planning-only status" in e for e in errors)
        assert any("non-authorization statement" in e for e in errors)
        assert any("current-implementation truth" in e for e in errors)


def test_governance_doc_passes_with_valid_content(tmp_path: Path) -> None:
    """A valid governance doc should produce no governance errors."""
    from scripts import check_bounded_autonomy_governance as checker

    gov = tmp_path / "bounded-live-autonomy-governance.md"
    gov.write_text(
        "# Bounded Live Autonomy Governance\n\n"
        "> **Status:** planning and governance only. This document does **not**\n"
        "> authorize, implement, or enable autonomous live trading in the current\n"
        "> release.\n\n"
        "Autonomous live trading is **not implemented**.\n\n"
        "## Hard invariants\n\n"
        "1. **Live trading is disabled by default.**\n"
        "2. **Live submit is disabled by default.** `can_submit` is false.\n"
        "3. **Provider output is never execution authority.**\n"
        "4. **Broker execution remains gated.**\n"
        "5. **RiskManager remains deterministic and mandatory.**\n"
        "6. **Kill switch remains mandatory and fail-closed.**\n"
        "7. **Approval queues remain mandatory where applicable.**\n"
        "8. **Audit hash-chain records every decision and submit attempt.**\n"
        "9. **No credentials, secrets, or private financial data in repo.**\n"
        "10. **No profit, no-risk, safe-live-trading, or autonomous-trading-readiness claims.**\n\n"
        "## External gates before any L4-like path\n\n"
        "Before any L4-like path, external review is required.\n\n"
        "L4 is **not a current goal**.\n"
    )

    with patch.object(checker, "GOVERNANCE_DOC", gov):
        errors = checker._check_governance_doc()
        assert errors == []


def test_roadmap_doc_required_phrases(tmp_path: Path) -> None:
    """A roadmap missing the bounded-autonomy status statement must fail."""
    from scripts import check_bounded_autonomy_governance as checker

    roadmap = tmp_path / "autonomy-roadmap.md"
    roadmap.write_text("# Roadmap\n\nThis is a roadmap.\n")

    with patch.object(checker, "ROADMAP_DOC", roadmap):
        errors = checker._check_roadmap_doc()
        assert any("bounded-autonomy status statement" in e for e in errors)
        assert any("missing link to bounded-live-autonomy-governance.md" in e for e in errors)


def test_public_autonomy_claims_detect_positive_claim(tmp_path: Path) -> None:
    """Positive forbidden autonomy claims are flagged."""
    from scripts import check_bounded_autonomy_governance as checker

    doc_dir = tmp_path / "docs"
    doc_dir.mkdir()
    (doc_dir / "unsafe.md").write_text(
        "Our product is autonomous live trading ready today.\n"
    )

    with patch.object(checker, "_SCAN_TARGETS", [doc_dir]):
        errors = checker._check_public_autonomy_claims()
        assert len(errors) == 1
        assert "autonomous live trading ready" in errors[0]


def test_public_autonomy_claims_allow_negative_context(tmp_path: Path) -> None:
    """Negative/disclaimer contexts around forbidden phrases are allowed."""
    from scripts import check_bounded_autonomy_governance as checker

    doc_dir = tmp_path / "docs"
    doc_dir.mkdir()
    (doc_dir / "safe.md").write_text(
        "Autonomous live trading is not implemented and therefore not autonomous live trading ready.\n"
    )

    with patch.object(checker, "_SCAN_TARGETS", [doc_dir]):
        errors = checker._check_public_autonomy_claims()
        assert errors == []


def test_version_planning_only_flags_bad_version(tmp_path: Path) -> None:
    """If the next planned tag already exists locally, the checker must fail."""
    from scripts import check_bounded_autonomy_governance as checker

    with patch.object(checker, "PACKAGE_VERSION", "0.6.24"), \
         patch.object(checker, "CURRENT_PUBLIC_TAG", "v0.6.24"), \
         patch.object(checker, "NEXT_PLANNED_TAG", "v0.6.24"):
        errors = checker._check_version_planning_only()
        assert errors
        assert any("already exists" in e for e in errors)
