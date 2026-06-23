import json
import os
import shutil
import subprocess
from pathlib import Path

from atlas_agent.backtest.portfolio import (
    ALLOWED_REVIEW_ITEM_STATUSES,
    ALLOWED_REVIEW_PACK_STATUSES,
    build_paper_portfolio_review_pack,
    write_portfolio_review_pack_reports,
)
from scripts.check_paper_human_review_pack import check_all

DATA_PATH = Path("data/sample/ohlcv_extended.csv")
FORBIDDEN_LABELS = {
    "live_ready",
    "production_ready",
    "safe_to_trade_live",
    "approved_for_live",
    "guaranteed_profit",
    "outperforms_market",
}


def test_review_pack_command_writes_schema(tmp_path):
    result = subprocess.run(
        [
            "python3.11",
            "-m",
            "atlas_agent.cli",
            "backtest",
            "portfolio-review-pack",
            "--symbol",
            "DEMO-SYMBOL",
            "--data",
            str(DATA_PATH),
            "--strategies",
            "buy_and_hold,moving_average_cross,rsi_mean_reversion",
            "--max-strategy-weight",
            "0.40",
            "--min-cash-weight",
            "0.10",
            "--max-stressed-drawdown",
            "0.25",
            "--max-single-scenario-loss",
            "0.20",
            "--monitor-window",
            "20",
            "--recheck-threshold",
            "0.05",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    json_path = tmp_path / "paper-human-review-pack.json"
    md_path = tmp_path / "paper-human-review-pack.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_pack"
    assert data["schema_version"] == 1
    assert data["release"] == "v0.6.15-planning"
    assert data["source_release"] == "v0.6.14"
    assert data["mode"] == "paper"
    assert data["non_executable"] is True
    assert data["paper_only"] is True
    assert data["provider_required"] is False
    assert data["broker_required"] is False
    assert data["network_required"] is False
    assert data["live_submit_enabled"] is False
    assert data["orders_generated"] is False
    assert data["notifications_sent"] is False
    assert data["not_financial_advice"] is True
    assert data["not_live_ready"] is True
    assert data["overall_review_pack_status"] in ALLOWED_REVIEW_PACK_STATUSES
    assert len(data["review_items"]) >= 1

    for item in data["review_items"]:
        assert item["type"] == "paper_review_item"
        assert item["status"] in ALLOWED_REVIEW_ITEM_STATUSES
        assert item["non_executable_action"] == "paper_only_follow_up"

    md_text = md_path.read_text(encoding="utf-8").lower()
    assert "non-executable" in md_text
    assert "paper-only" in md_text
    assert "no broker submission" in md_text
    assert "no provider calls" in md_text
    assert "no real notifications" in md_text
    assert "no orders generated" in md_text
    assert "no account-specific instructions" in md_text
    assert "no profit guarantees" in md_text
    assert "no absolute safety" in md_text
    assert "no claims that risk is eliminated" in md_text
    assert "no live-readiness claim" in md_text
    assert "no autonomous live trading readiness" in md_text
    assert "human review is required" in md_text


def test_review_pack_is_deterministic(tmp_path):
    report_one = build_paper_portfolio_review_pack(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )
    report_two = build_paper_portfolio_review_pack(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )
    assert report_one == report_two

    first_json, _ = write_portfolio_review_pack_reports(
        report_one, output_dir=str(tmp_path / "one")
    )
    second_json, _ = write_portfolio_review_pack_reports(
        report_two, output_dir=str(tmp_path / "two")
    )
    assert Path(first_json).read_text() == Path(second_json).read_text()


def test_all_outputs_have_live_submit_disabled():
    report = build_paper_portfolio_review_pack(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
    )
    assert report["live_submit_enabled"] is False
    assert report["non_executable"] is True
    assert report["paper_only"] is True
    assert report["provider_required"] is False
    assert report["broker_required"] is False
    assert report["network_required"] is False
    assert report["orders_generated"] is False
    assert report["notifications_sent"] is False
    assert report["safety"]["no_live_trading"] is True
    assert report["safety"]["no_broker_calls"] is True
    assert report["safety"]["no_provider_calls"] is True
    assert report["safety"]["no_live_readiness_claim"] is True
    assert report["safety"]["non_executable"] is True
    assert report["safety"]["paper_only"] is True


def test_no_decision_uses_forbidden_labels():
    report = build_paper_portfolio_review_pack(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_holder"],
    )
    observed = {report["overall_review_pack_status"]}
    assert not observed & FORBIDDEN_LABELS


def test_demo_script_passes():
    result = subprocess.run(
        ["bash", "scripts/demo_paper_human_review_pack.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Paper human review pack demo PASS" in result.stdout


def test_checker_passes_on_real_repo_and_json_parses():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_human_review_pack.py", "--json"],
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
        "docs/paper-human-review-pack.md",
        "scripts/demo_paper_human_review_pack.sh",
        "scripts/check_paper_human_review_pack.py",
        "tests/test_paper_human_review_pack.py",
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
    (root / "pyproject.toml").write_text('version = "0.6.15"\n')
    (root / "src/atlas_agent/__init__.py").write_text('__version__ = "0.6.15"\n')
    os.chmod(root / "scripts/demo_paper_human_review_pack.sh", 0o755)
    return root


def test_checker_does_not_mutate_files(tmp_path):
    root = _checker_root(tmp_path)
    before = _snapshot(root)
    assert check_all(root) == []
    after = _snapshot(root)
    assert before == after


def test_checker_fails_on_forbidden_claim_in_docs(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-pack.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nguaranteed profit\n")
    issues = check_all(root)
    assert any("guaranteed profit" in issue for issue in issues)


def test_checker_fails_on_executable_order_language(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-pack.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nplace order now\n")
    issues = check_all(root)
    assert any("place order" in issue for issue in issues)


def test_checker_fails_on_live_readiness_language(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-pack.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nsafe live trading\n")
    issues = check_all(root)
    assert any("safe live trading" in issue for issue in issues)


def test_checker_fails_when_demo_missing_non_executable_statement(tmp_path):
    root = _checker_root(tmp_path)
    demo_path = root / "scripts/demo_paper_human_review_pack.sh"
    content = demo_path.read_text(encoding="utf-8").replace("non-executable", "reviewable")
    demo_path.write_text(content)
    issues = check_all(root)
    assert any("non-executable" in issue for issue in issues)


def test_checker_fails_when_v0615_candidate_doc_missing_cand001(tmp_path):
    root = _checker_root(tmp_path)
    plan_path = root / "docs/releases/v0.6.15-plan.md"
    plan_path.write_text("# v0.6.15 Release Plan\n\nStatus: planning-only.\n")
    issues = check_all(root)
    assert any("CAND-001" in issue for issue in issues)


def test_checker_fails_when_cli_command_missing(tmp_path):
    root = _checker_root(tmp_path)
    cli_path = root / "src/atlas_agent/cli.py"
    cli_path.write_text("# placeholder cli file\n")
    issues = check_all(root)
    assert any("portfolio-review-pack" in issue for issue in issues)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
