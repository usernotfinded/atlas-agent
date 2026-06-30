import json
import os
import shutil
import subprocess
from pathlib import Path

from atlas_agent.backtest.portfolio import (
    ALLOWED_MONITORING_STATUSES,
    MONITORING_TRIGGER_TYPES,
    build_paper_portfolio_monitoring,
    write_portfolio_monitoring_reports,
)
from scripts.check_paper_portfolio_monitoring import check_all


DATA_PATH = Path("data/sample/ohlcv_extended.csv")
FORBIDDEN_LABELS = {
    "live_ready",
    "production_ready",
    "safe_to_trade_live",
    "approved_for_live",
    "guaranteed_profit",
    "outperforms_market",
}


def test_monitoring_command_writes_schema(tmp_path):
    result = subprocess.run(
        [
            "python3.11",
            "-m",
            "atlas_agent.cli",
            "backtest",
            "portfolio-monitor",
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
    json_path = tmp_path / "paper-portfolio-monitoring.json"
    md_path = tmp_path / "paper-portfolio-monitoring.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_portfolio_monitoring"
    assert data["schema_version"] == 1
    assert data["mode"] == "paper"
    assert data["provider_required"] is False
    assert data["broker_required"] is False
    assert data["network_required"] is False
    assert data["live_readiness"] is False
    assert data["not_financial_advice"] is True
    assert data["overall_monitoring_status"] in ALLOWED_MONITORING_STATUSES
    assert data["safety"]["no_notifications_sent"] is True


def test_monitoring_windows_are_deterministic(tmp_path):
    report_one = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )
    report_two = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )
    assert report_one == report_two

    first_json, _ = write_portfolio_monitoring_reports(report_one, output_dir=tmp_path / "one")
    second_json, _ = write_portfolio_monitoring_reports(report_two, output_dir=tmp_path / "two")
    assert first_json.read_text() == second_json.read_text()


def test_monitoring_statuses_are_allowed_only():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
    )
    observed = {report["overall_monitoring_status"]}
    observed.update(event["status"] for event in report["monitoring_events"])
    assert observed <= ALLOWED_MONITORING_STATUSES
    assert not observed & FORBIDDEN_LABELS


def test_allocation_drift_trigger_is_deterministic():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        proposal=_eligible_proposal(weight=0.90, cash=0.10),
        stress=_passing_stress(),
    )
    drift_events = [e for e in report["monitoring_events"] if e["trigger"] == "allocation_drift"]
    assert len(drift_events) > 0
    for event in drift_events:
        assert event["status"] in ALLOWED_MONITORING_STATUSES


def test_cash_reserve_trigger_is_deterministic():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        proposal=_eligible_proposal(weight=0.95, cash=0.05),
        stress=_passing_stress(),
    )
    cash_events = [e for e in report["monitoring_events"] if e["trigger"] == "cash_reserve_breach"]
    assert len(cash_events) > 0
    assert all(e["status"] == "rejected" for e in cash_events)


def test_drawdown_breach_trigger_is_deterministic():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        proposal=_eligible_proposal(weight=0.90, cash=0.10),
        stress=_passing_stress(),
    )
    drawdown_events = [e for e in report["monitoring_events"] if e["trigger"] == "drawdown_breach"]
    assert len(drawdown_events) > 0
    for event in drawdown_events:
        assert event["status"] in ALLOWED_MONITORING_STATUSES


def test_stress_watchlist_trigger_is_deterministic():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        proposal=_eligible_proposal(weight=0.90, cash=0.10),
        stress=_watchlist_stress(),
    )
    stress_events = [e for e in report["monitoring_events"] if e["trigger"] == "stress_watchlist"]
    assert len(stress_events) > 0
    assert all(e["status"] == "paper_monitor_watchlist" for e in stress_events)


def test_insufficient_data_trigger():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        monitor_window=9999,
        proposal=_eligible_proposal(weight=0.90, cash=0.10),
        stress=_passing_stress(),
    )
    assert report["overall_monitoring_status"] == "needs_recheck"
    assert any(e["trigger"] == "insufficient_data" for e in report["monitoring_events"])


def test_stale_proposal_triggers_rejection():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
        proposal={
            "proposal_status": "rejected",
            "allocations": [],
            "excluded": [],
        },
        stress=_passing_stress(),
    )
    assert report["overall_monitoring_status"] == "rejected"
    assert any(e["trigger"] == "stale_artifact" for e in report["monitoring_events"])


def test_all_outputs_have_live_readiness_false():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
    )
    assert report["live_readiness"] is False
    assert report["safety"]["no_live_trading"] is True
    assert report["safety"]["no_broker_calls"] is True
    assert report["safety"]["no_provider_calls"] is True
    assert report["safety"]["no_notifications_sent"] is True
    assert report["safety"]["no_live_readiness_claim"] is True


def test_no_decision_uses_forbidden_labels():
    report = build_paper_portfolio_monitoring(
        data_path=DATA_PATH,
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
    )
    observed = {report["overall_monitoring_status"]}
    observed.update(event["status"] for event in report["monitoring_events"])
    assert not observed & FORBIDDEN_LABELS


def test_demo_script_passes():
    result = subprocess.run(
        ["bash", "scripts/demo_paper_portfolio_monitoring.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Paper portfolio monitoring demo PASS" in result.stdout


def test_checker_passes_on_real_repo_and_json_parses():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_portfolio_monitoring.py", "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data == {"status": "pass", "issues": []}


def test_checker_fails_if_docs_claim_guaranteed_profit(tmp_path):
    root = _checker_root(tmp_path)
    docs = root / "docs/paper-portfolio-monitoring.md"
    docs.write_text(docs.read_text() + "\nThis claims guaranteed profit.\n")
    issues = check_all(root)
    assert any("guaranteed profit" in issue for issue in issues)


def test_checker_fails_if_docs_claim_live_ready(tmp_path):
    root = _checker_root(tmp_path)
    docs = root / "docs/paper-portfolio-monitoring.md"
    docs.write_text(docs.read_text() + "\nThis says the portfolio is live ready.\n")
    issues = check_all(root)
    assert any("live ready" in issue for issue in issues)


def test_checker_fails_if_demo_uses_live_mode(tmp_path):
    root = _checker_root(tmp_path)
    demo = root / "scripts/demo_paper_portfolio_monitoring.sh"
    demo.write_text(demo.read_text() + "\npython3.11 -m atlas_agent.cli run --mode live\n")
    issues = check_all(root)
    assert any("live mode" in issue for issue in issues)


def test_checker_fails_if_demo_uses_notification_commands(tmp_path):
    root = _checker_root(tmp_path)
    demo = root / "scripts/demo_paper_portfolio_monitoring.sh"
    demo.write_text(demo.read_text() + "\n# Send gmail notification\n")
    issues = check_all(root)
    assert any("notification" in issue.lower() for issue in issues)


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


def _passing_stress() -> dict:
    return {
        "overall_stress_status": "paper_stress_pass",
    }


def _watchlist_stress() -> dict:
    return {
        "overall_stress_status": "paper_stress_watchlist",
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
        "docs/paper-portfolio-monitoring.md",
        "docs/paper-portfolio-stress.md",
        "docs/paper-portfolio-proposal.md",
        "scripts/demo_paper_portfolio_monitoring.sh",
        "scripts/demo_paper_portfolio_stress.sh",
        "scripts/demo_paper_portfolio_proposal.sh",
        "scripts/check_paper_portfolio_monitoring.py",
        "scripts/check_paper_portfolio_stress.py",
        "scripts/check_paper_portfolio_proposal.py",
        "tests/test_paper_portfolio_monitoring.py",
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
    os.chmod(root / "scripts/demo_paper_portfolio_monitoring.sh", 0o755)
    return root


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
