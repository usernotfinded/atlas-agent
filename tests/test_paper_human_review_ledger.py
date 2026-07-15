# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_human_review_ledger.py
# PURPOSE: Verifies paper human review ledger behavior and regression
#         expectations.
# DEPS:    json, os, shutil, subprocess, pathlib, scripts, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

import json
import os
import shutil
import subprocess
from pathlib import Path

from scripts.check_paper_human_review_ledger import check_all

from atlas_agent.backtest.portfolio import (
    ALLOWED_DECISION_STATUSES,
    ALLOWED_REVIEW_LEDGER_STATUSES,
    build_paper_portfolio_review_pack,
    build_paper_portfolio_review_ledger,
    render_portfolio_review_ledger_markdown,
    write_portfolio_review_ledger_reports,
)

# --- CONFIGURATION AND CONSTANTS ---

DATA_PATH = Path("data/sample/ohlcv_extended.csv")


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _build_review_pack():
    return build_paper_portfolio_review_pack(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )


def test_ledger_builder_with_review_pack_path(tmp_path):
    pack = _build_review_pack()
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack_path = pack_dir / "paper-human-review-pack.json"
    pack_path.write_text(json.dumps(pack, indent=2, sort_keys=True, allow_nan=False))

    ledger = build_paper_portfolio_review_ledger(review_pack_path=str(pack_path))

    assert ledger["artifact_type"] == "paper_human_review_ledger"
    assert ledger["schema_version"] == 1
    assert ledger["release"] == "v0.6.15-planning"
    assert ledger["source_release"] == "v0.6.14"
    assert ledger["mode"] == "paper"
    assert ledger["non_executable"] is True
    assert ledger["paper_only"] is True
    assert ledger["provider_required"] is False
    assert ledger["broker_required"] is False
    assert ledger["network_required"] is False
    assert ledger["live_submit_enabled"] is False
    assert ledger["orders_generated"] is False
    assert ledger["notifications_sent"] is False
    assert ledger["real_human_approval"] is False
    assert ledger["not_financial_advice"] is True
    assert ledger["not_live_ready"] is True
    assert ledger["source_artifact_type"] == "paper_human_review_pack"
    assert isinstance(ledger["source_artifact_digest"], str)
    assert len(ledger["source_artifact_digest"]) == 64
    assert ledger["overall_review_ledger_status"] in ALLOWED_REVIEW_LEDGER_STATUSES
    assert ledger["gate_summary"] == {
        "live_approval_granted": False,
        "broker_submission_allowed": False,
        "paper_follow_up_allowed": True,
    }

    decision_entries = ledger["decision_entries"]
    assert len(decision_entries) == len(pack["review_items"])
    for entry, item in zip(decision_entries, pack["review_items"]):
        assert entry["id"] == f"{item['id']}-decision"
        assert entry["type"] == "paper_decision_entry"
        assert entry["source_item_id"] == item["id"]
        assert entry["source"] == item["source"]
        assert entry["decision_status"] in ALLOWED_DECISION_STATUSES
        assert entry["paper_action"] == item["non_executable_action"]
        assert entry["severity"] == item["severity"]
        assert entry["reason"] == item["reason"]
        assert entry["non_executable"] is True
        assert entry["paper_only"] is True
        assert entry["live_submit_enabled"] is False
        assert entry["broker_submission_allowed"] is False
        assert entry["reviewed_by"] == "simulated_reviewer"



def test_ledger_builder_with_build_kwargs():
    ledger = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )

    assert ledger["artifact_type"] == "paper_human_review_ledger"
    assert ledger["schema_version"] == 1
    assert ledger["source_artifact_type"] == "paper_human_review_pack"
    assert ledger["overall_review_ledger_status"] in ALLOWED_REVIEW_LEDGER_STATUSES
    for entry in ledger["decision_entries"]:
        assert entry["decision_status"] in ALLOWED_DECISION_STATUSES
        assert entry["non_executable"] is True
        assert entry["broker_submission_allowed"] is False


def test_ledger_builder_requires_path_or_kwargs():
    try:
        build_paper_portfolio_review_ledger()
    except ValueError:
        return
    raise AssertionError("Expected ValueError when neither path nor kwargs are provided")


def test_ledger_is_deterministic():
    ledger_one = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold", "moving_average_cross"],
        }
    )
    ledger_two = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold", "moving_average_cross"],
        }
    )
    assert ledger_one == ledger_two


def test_ledger_writer_outputs_files(tmp_path):
    ledger = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    json_path, md_path = write_portfolio_review_ledger_reports(
        ledger, output_dir=str(tmp_path)
    )
    assert json_path.exists()
    assert md_path.exists()
    assert json_path.name == "paper-human-review-ledger.json"
    assert md_path.name == "paper-human-review-ledger.md"

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_ledger"


def test_ledger_markdown_safety_phrases():
    ledger = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    md_text = render_portfolio_review_ledger_markdown(ledger).lower()
    assert "paper-only" in md_text
    assert "non-executable" in md_text
    assert "not financial advice" in md_text
    assert "not live ready" in md_text
    assert "not live approval" in md_text
    assert "not a real human decision" in md_text
    assert "not an executable order" in md_text
    assert "gate summary" in md_text
    assert "decision entries" in md_text
    assert "paper follow up allowed" in md_text


def test_ledger_gate_summary_denies_live_and_broker():
    ledger = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    summary = ledger["gate_summary"]
    assert summary["live_approval_granted"] is False
    assert summary["broker_submission_allowed"] is False
    assert summary["paper_follow_up_allowed"] is True


def test_ledger_real_human_approval_false():
    ledger = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    assert ledger["real_human_approval"] is False
    assert ledger["safety"]["no_real_human_approval"] is True


def test_ledger_source_digest_matches_loaded_file(tmp_path):
    pack = _build_review_pack()
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack_path = pack_dir / "paper-human-review-pack.json"
    json_text = json.dumps(pack, sort_keys=True, allow_nan=False)
    pack_path.write_text(json_text)

    ledger = build_paper_portfolio_review_ledger(review_pack_path=str(pack_path))
    expected_digest = __import__("hashlib").sha256(
        json_text.encode("utf-8")
    ).hexdigest()
    assert ledger["source_artifact_digest"] == expected_digest



def _run_cli(*args):
    return subprocess.run(
        ["python3.11", "-m", "atlas_agent.cli", "backtest", "portfolio-review-ledger", *args],
        capture_output=True,
        text=True,
    )


def test_ledger_cli_without_review_pack(tmp_path):
    result = _run_cli(
        "--symbol", "DEMO-SYMBOL",
        "--data", str(DATA_PATH),
        "--strategies", "buy_and_hold,moving_average_cross",
        "--output-dir", str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    json_path = tmp_path / "paper-human-review-ledger.json"
    md_path = tmp_path / "paper-human-review-ledger.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_ledger"
    assert data["schema_version"] == 1
    assert data["mode"] == "paper"
    assert data["non_executable"] is True
    assert data["paper_only"] is True
    assert data["provider_required"] is False
    assert data["broker_required"] is False
    assert data["network_required"] is False
    assert data["live_submit_enabled"] is False
    assert data["orders_generated"] is False
    assert data["notifications_sent"] is False
    assert data["real_human_approval"] is False
    assert data["overall_review_ledger_status"] in ALLOWED_REVIEW_LEDGER_STATUSES
    assert data["gate_summary"] == {
        "live_approval_granted": False,
        "broker_submission_allowed": False,
        "paper_follow_up_allowed": True,
    }
    assert isinstance(data["decision_entries"], list)
    for entry in data["decision_entries"]:
        assert entry["decision_status"] in ALLOWED_DECISION_STATUSES


def test_ledger_cli_with_review_pack(tmp_path):
    pack = _build_review_pack()
    pack_path = tmp_path / "paper-human-review-pack.json"
    pack_path.write_text(json.dumps(pack, indent=2, sort_keys=True, allow_nan=False))

    output_dir = tmp_path / "ledger"
    result = _run_cli(
        "--review-pack", str(pack_path),
        "--output-dir", str(output_dir),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    json_path = output_dir / "paper-human-review-ledger.json"
    md_path = output_dir / "paper-human-review-ledger.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_ledger"
    assert data["source_artifact_type"] == "paper_human_review_pack"
    assert len(data["decision_entries"]) == len(pack["review_items"])


def test_ledger_cli_json_output(tmp_path):
    result = _run_cli(
        "--symbol", "DEMO-SYMBOL",
        "--data", str(DATA_PATH),
        "--strategies", "buy_and_hold",
        "--output-dir", str(tmp_path),
        "--json",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    data = json.loads(result.stdout)
    assert data["artifact_type"] == "paper_human_review_ledger"
    assert data["mode"] == "paper"
    assert data["non_executable"] is True
    assert data["overall_review_ledger_status"] in ALLOWED_REVIEW_LEDGER_STATUSES
    assert data["gate_summary"]["live_approval_granted"] is False
    assert data["gate_summary"]["broker_submission_allowed"] is False
    assert data["gate_summary"]["paper_follow_up_allowed"] is True


def test_ledger_cli_help_includes_command():
    result = subprocess.run(
        ["python3.11", "-m", "atlas_agent.cli", "backtest", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "portfolio-review-ledger" in result.stdout


def test_demo_script_passes():
    result = subprocess.run(
        ["bash", "scripts/demo_paper_human_review_ledger.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Paper human review ledger demo PASS" in result.stdout


def test_checker_passes_on_real_repo_and_json_parses():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_human_review_ledger.py", "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data == {"status": "pass", "issues": []}


def _checker_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for directory in [
        "docs/releases",
        "scripts",
        "tests",
        "src/atlas_agent",
    ]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    for path in [
        "docs/paper-human-review-ledger.md",
        "scripts/demo_paper_human_review_ledger.sh",
        "scripts/check_paper_human_review_ledger.py",
        "tests/test_paper_human_review_ledger.py",
        "docs/releases/v0.6.15-plan.md",
        "docs/releases/v0.6.15-candidates.md",
        "docs/releases/v0.6.15-candidates.json",
        "src/atlas_agent/cli.py",
    ]:
        source = Path(path)
        destination = root / path
        if source.exists():
            shutil.copy2(source, destination)
        else:
            destination.write_text("placeholder\n")
    (root / "pyproject.toml").write_text('version = "0.6.16"\n')
    (root / "src/atlas_agent/__init__.py").write_text('__version__ = "0.6.16"\n')
    os.chmod(root / "scripts/demo_paper_human_review_ledger.sh", 0o755)
    return root


def test_checker_does_not_mutate_files(tmp_path):
    root = _checker_root(tmp_path)
    before = _snapshot(root)
    assert check_all(root) == []
    after = _snapshot(root)
    assert before == after


def test_checker_fails_on_forbidden_claim_in_docs(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-ledger.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nguaranteed profit\n")
    issues = check_all(root)
    assert any("guaranteed profit" in issue for issue in issues)


def test_checker_fails_on_executable_order_language(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-ledger.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nplace order now\n")
    issues = check_all(root)
    assert any("place order" in issue for issue in issues)


def test_checker_fails_on_live_approval_language(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-ledger.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\napproved for live\n")
    issues = check_all(root)
    assert any("approved for live" in issue for issue in issues)


def test_checker_fails_when_demo_missing_non_executable_statement(tmp_path):
    root = _checker_root(tmp_path)
    demo_path = root / "scripts/demo_paper_human_review_ledger.sh"
    content = demo_path.read_text(encoding="utf-8").replace("non-executable", "reviewable")
    demo_path.write_text(content)
    issues = check_all(root)
    assert any("non-executable" in issue for issue in issues)


def test_checker_fails_when_demo_missing_no_real_human_approval(tmp_path):
    root = _checker_root(tmp_path)
    demo_path = root / "scripts/demo_paper_human_review_ledger.sh"
    content = demo_path.read_text(encoding="utf-8").replace("no real human approval", "reviewer sign-off")
    demo_path.write_text(content)
    issues = check_all(root)
    assert any("no real human approval" in issue for issue in issues)


def test_checker_fails_when_v0615_candidate_doc_missing_cand002(tmp_path):
    root = _checker_root(tmp_path)
    plan_path = root / "docs/releases/v0.6.15-plan.md"
    plan_path.write_text("# v0.6.15 Release Plan\n\nStatus: planning-only.\nCAND-001 only.\n")
    issues = check_all(root)
    assert any("CAND-002" in issue for issue in issues)


def test_checker_fails_when_cli_command_missing(tmp_path):
    root = _checker_root(tmp_path)
    cli_path = root / "src/atlas_agent/cli.py"
    cli_path.write_text("# placeholder cli file\n")
    issues = check_all(root)
    assert any("portfolio-review-ledger" in issue for issue in issues)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
