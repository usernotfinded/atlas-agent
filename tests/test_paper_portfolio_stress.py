# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_portfolio_stress.py
# PURPOSE: Verifies paper portfolio stress behavior and regression expectations.
# DEPS:    json, os, shutil, subprocess, pathlib, atlas_agent, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

import json
import os
import shutil
import subprocess
from pathlib import Path

from atlas_agent.backtest.portfolio import (
    ALLOWED_STRESS_STATUSES,
    STRESS_SCENARIOS,
    build_paper_portfolio_stress,
    write_portfolio_stress_reports,
)
from scripts.check_paper_portfolio_stress import check_all


# --- CONFIGURATION AND CONSTANTS ---

DATA_PATH = Path("data/sample/ohlcv_extended.csv")
FORBIDDEN_LABELS = {
    "live_ready",
    "production_ready",
    "safe_to_trade_live",
    "approved_for_live",
    "guaranteed_profit",
    "outperforms_market",
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_portfolio_stress_command_writes_schema(tmp_path):
    result = subprocess.run(
        [
            "python3.11",
            "-m",
            "atlas_agent.cli",
            "backtest",
            "portfolio-stress",
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
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    json_path = tmp_path / "paper-portfolio-stress.json"
    md_path = tmp_path / "paper-portfolio-stress.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_portfolio_stress"
    assert data["schema_version"] == 1
    assert data["mode"] == "paper"
    assert data["provider_required"] is False
    assert data["broker_required"] is False
    assert data["network_required"] is False
    assert data["live_readiness"] is False
    assert data["not_financial_advice"] is True
    assert data["overall_stress_status"] in ALLOWED_STRESS_STATUSES
    assert {item["scenario"] for item in data["stress_results"]} == set(STRESS_SCENARIOS)


def test_stress_scenarios_are_deterministic(tmp_path):
    report_one = build_paper_portfolio_stress(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )
    report_two = build_paper_portfolio_stress(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )
    assert report_one == report_two

    first_json, _ = write_portfolio_stress_reports(report_one, output_dir=tmp_path / "one")
    second_json, _ = write_portfolio_stress_reports(report_two, output_dir=tmp_path / "two")
    assert first_json.read_text() == second_json.read_text()


def test_stress_statuses_are_allowed_only():
    report = build_paper_portfolio_stress(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
    )
    observed = {report["overall_stress_status"]}
    observed.update(item["status"] for item in report["stress_results"])
    assert observed <= ALLOWED_STRESS_STATUSES
    assert not observed & FORBIDDEN_LABELS


def test_max_stressed_drawdown_constraint_enforced():
    report = build_paper_portfolio_stress(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        max_strategy_weight=0.95,
        max_stressed_drawdown=0.01,
        proposal=_eligible_proposal(weight=0.90, cash=0.10),
    )
    assert report["overall_stress_status"] == "rejected"
    assert any(item["status"] == "rejected" for item in report["stress_results"])


def test_max_single_scenario_loss_constraint_enforced():
    report = build_paper_portfolio_stress(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        max_strategy_weight=0.95,
        max_stressed_drawdown=0.99,
        max_single_scenario_loss=0.01,
        proposal=_eligible_proposal(weight=0.90, cash=0.10),
    )
    assert report["overall_stress_status"] == "rejected"
    assert any("Single-scenario loss" in item["reason"] for item in report["stress_results"])


def test_strategy_weight_and_cash_constraints_preserved():
    report = build_paper_portfolio_stress(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        max_strategy_weight=0.40,
        min_cash_weight=0.10,
        proposal=_eligible_proposal(weight=0.50, cash=0.50),
    )
    assert report["overall_stress_status"] == "rejected"
    assert any(item["constraint"] == "max_strategy_weight" for item in report["constraint_findings"])

    cash_report = build_paper_portfolio_stress(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        max_strategy_weight=0.95,
        min_cash_weight=0.10,
        proposal=_eligible_proposal(weight=0.95, cash=0.05),
    )
    assert cash_report["overall_stress_status"] == "rejected"
    assert any(item["constraint"] == "min_cash_weight" for item in cash_report["constraint_findings"])


def test_live_readiness_false_and_no_provider_or_broker_required():
    report = build_paper_portfolio_stress(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
    )
    assert report["live_readiness"] is False
    assert report["provider_required"] is False
    assert report["broker_required"] is False
    assert report["network_required"] is False
    assert report["safety"]["no_provider_calls"] is True
    assert report["safety"]["no_broker_calls"] is True


def test_demo_script_passes():
    result = subprocess.run(
        ["bash", "scripts/demo_paper_portfolio_stress.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Paper portfolio stress demo PASS" in result.stdout


def test_checker_passes_on_real_repo_and_json_parses():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_portfolio_stress.py", "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data == {"status": "pass", "issues": []}


def test_checker_fails_if_docs_claim_guaranteed_profit(tmp_path):
    root = _checker_root(tmp_path)
    docs = root / "docs/paper-portfolio-stress.md"
    docs.write_text(docs.read_text() + "\nThis claims guaranteed profit.\n")
    issues = check_all(root)
    assert any("guaranteed profit" in issue for issue in issues)


def test_checker_fails_if_docs_claim_live_ready(tmp_path):
    root = _checker_root(tmp_path)
    docs = root / "docs/paper-portfolio-stress.md"
    docs.write_text(docs.read_text() + "\nThis says the portfolio is live ready.\n")
    issues = check_all(root)
    assert any("live ready" in issue for issue in issues)


def test_checker_fails_if_demo_uses_live_mode(tmp_path):
    root = _checker_root(tmp_path)
    demo = root / "scripts/demo_paper_portfolio_stress.sh"
    demo.write_text(demo.read_text() + "\npython3.11 -m atlas_agent.cli run --mode live\n")
    issues = check_all(root)
    assert any("live mode" in issue for issue in issues)


def test_checker_fails_if_v0614_claimed_released(tmp_path):
    root = _checker_root(tmp_path)
    plan = root / "docs/releases/v0.6.14-plan.md"
    plan.write_text(plan.read_text() + "\nv0.6.14 is released.\n")
    issues = check_all(root)
    assert any("v0.6.14 is released" in issue for issue in issues)


def test_checker_does_not_mutate_files(tmp_path):
    root = _checker_root(tmp_path)
    before = _snapshot(root)
    assert check_all(root) == []
    after = _snapshot(root)
    assert before == after


def _eligible_proposal(*, weight: float, cash: float) -> dict:
    return {
        "proposal_status": "paper_portfolio_proposal",
        "allocations": [
            {
                "strategy": "buy_and_hold",
                "scorecard_decision": "paper_follow_up_candidate",
                "paper_weight": weight,
                "reason": "test eligible paper candidate",
            },
            {
                "strategy": "cash",
                "paper_weight": cash,
                "reason": "minimum paper cash reserve",
            },
        ],
        "excluded": [],
    }


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
        "docs/paper-portfolio-stress.md",
        "docs/paper-portfolio-proposal.md",
        "scripts/demo_paper_portfolio_stress.sh",
        "scripts/demo_paper_portfolio_proposal.sh",
        "scripts/check_paper_portfolio_stress.py",
        "scripts/check_paper_portfolio_proposal.py",
        "tests/test_paper_portfolio_stress.py",
        "tests/test_paper_portfolio_proposal.py",
        "docs/releases/v0.6.14-plan.md",
        "docs/releases/v0.6.14-candidates.md",
        "docs/releases/v0.6.14-candidates.json",
    ]:
        source = Path(path)
        destination = root / path
        if source.exists():
            shutil.copy2(source, destination)
        else:
            destination.write_text("placeholder\n")
    (root / "pyproject.toml").write_text('version = "0.6.16"\n')
    (root / "src/atlas_agent/__init__.py").write_text('__version__ = "0.6.16"\n')
    os.chmod(root / "scripts/demo_paper_portfolio_stress.sh", 0o755)
    return root


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
