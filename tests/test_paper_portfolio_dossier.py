import json
import os
import shutil
import subprocess
from pathlib import Path

from atlas_agent.backtest.portfolio import (
    build_paper_portfolio_dossier,
    write_portfolio_dossier_reports,
)
from scripts.check_paper_portfolio_dossier import check_all

DATA_PATH = Path("data/sample/ohlcv_extended.csv")
ALLOWED_DOSSIER_STATUSES = {
    "paper_dossier_complete",
    "paper_dossier_watchlist",
    "paper_dossier_recheck_required",
    "paper_dossier_rejected",
}
FORBIDDEN_LABELS = {
    "live_ready",
    "production_ready",
    "safe_to_trade_live",
    "approved_for_live",
    "guaranteed_profit",
    "outperforms_market",
}

def test_dossier_command_writes_schema(tmp_path):
    result = subprocess.run(
        [
            "python3.11",
            "-m",
            "atlas_agent.cli",
            "backtest",
            "portfolio-dossier",
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
    json_path = tmp_path / "paper-portfolio-dossier.json"
    md_path = tmp_path / "paper-portfolio-dossier.md"
    manifest_path = tmp_path / "paper-portfolio-evidence-manifest.json"
    assert json_path.exists()
    assert md_path.exists()
    assert manifest_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_portfolio_dossier"
    assert data["schema_version"] == 1
    assert data["mode"] == "paper"
    assert data["provider_required"] is False
    assert data["broker_required"] is False
    assert data["network_required"] is False
    assert data["live_readiness"] is False
    assert data["not_financial_advice"] is True
    assert data["overall_dossier_status"] in ALLOWED_DOSSIER_STATUSES
    assert data["safety"]["no_notifications_sent"] is True

def test_dossier_is_deterministic(tmp_path):
    report_one = build_paper_portfolio_dossier(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )
    report_two = build_paper_portfolio_dossier(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )
    assert report_one == report_two

    first_json, _, _ = write_portfolio_dossier_reports(report_one, output_dir=str(tmp_path / "one"))
    second_json, _, _ = write_portfolio_dossier_reports(report_two, output_dir=str(tmp_path / "two"))
    assert Path(first_json).read_text() == Path(second_json).read_text()

def test_all_outputs_have_live_readiness_false():
    report = build_paper_portfolio_dossier(
        data_path=str(DATA_PATH),
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
    report = build_paper_portfolio_dossier(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold"],
    )
    observed = {report["overall_dossier_status"]}
    assert not observed & FORBIDDEN_LABELS

def test_demo_script_passes():
    result = subprocess.run(
        ["bash", "scripts/demo_paper_portfolio_dossier.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Paper portfolio reviewer dossier demo PASS" in result.stdout

def test_checker_passes_on_real_repo_and_json_parses():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_portfolio_dossier.py", "--json"],
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
        "docs/paper-portfolio-dossier.md",
        "docs/paper-portfolio-recheck-ledger.md",
        "scripts/demo_paper_portfolio_dossier.sh",
        "scripts/demo_paper_portfolio_recheck.sh",
        "scripts/check_paper_portfolio_dossier.py",
        "scripts/check_paper_portfolio_recheck.py",
        "tests/test_paper_portfolio_dossier.py",
        "tests/test_paper_portfolio_recheck.py",
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
    (root / "pyproject.toml").write_text('version = "0.6.13"\n')
    (root / "src/atlas_agent/__init__.py").write_text('__version__ = "0.6.13"\n')
    os.chmod(root / "scripts/demo_paper_portfolio_dossier.sh", 0o755)
    return root

def test_checker_does_not_mutate_files(tmp_path):
    root = _checker_root(tmp_path)
    before = _snapshot(root)
    assert check_all(root) == []
    after = _snapshot(root)
    assert before == after

def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
