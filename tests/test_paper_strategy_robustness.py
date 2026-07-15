# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_strategy_robustness.py
# PURPOSE: Verifies paper strategy robustness behavior and regression
#         expectations.
# DEPS:    hashlib, json, shutil, subprocess, sys, pathlib, additional local
#         modules.
# ==============================================================================

# --- IMPORTS ---

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from atlas_agent.backtest.robustness import build_paper_strategy_robustness


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_paper_strategy_robustness.py"
DEMO_SCRIPT = ROOT / "scripts" / "demo_paper_strategy_robustness.sh"
FIXTURES = [
    ROOT / "data" / "sample" / "regimes" / "ohlcv_uptrend.csv",
    ROOT / "data" / "sample" / "regimes" / "ohlcv_downtrend.csv",
    ROOT / "data" / "sample" / "regimes" / "ohlcv_flat.csv",
    ROOT / "data" / "sample" / "regimes" / "ohlcv_volatile.csv",
]
FIXTURE_ARG = ",".join(str(path) for path in FIXTURES)
ALLOWED_STATUSES = {
    "robust_paper_follow_up",
    "regime_sensitive_needs_more_testing",
    "needs_more_testing",
    "rejected",
}
FORBIDDEN_STATUSES = {
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

def _run_robustness(output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "atlas_agent.cli",
            "backtest",
            "robustness",
            "--symbol",
            "DEMO-SYMBOL",
            "--fixtures",
            FIXTURE_ARG,
            "--strategies",
            "buy_and_hold,moving_average_cross,rsi_mean_reversion",
            "--output-dir",
            str(output_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _load_report(output_dir: Path) -> dict:
    return json.loads((output_dir / "strategy-robustness.json").read_text(encoding="utf-8"))


class TestPaperStrategyRobustness:
    def test_cli_generates_schema_valid_artifacts(self, tmp_path: Path) -> None:
        result = _run_robustness(tmp_path / "out")
        assert result.returncode == 0, result.stderr

        json_path = tmp_path / "out" / "strategy-robustness.json"
        markdown_path = tmp_path / "out" / "strategy-robustness.md"
        assert json_path.exists()
        assert markdown_path.exists()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["artifact_type"] == "paper_strategy_robustness"
        assert data["schema_version"] == 1
        assert data["mode"] == "paper"
        assert data["provider_required"] is False
        assert data["broker_required"] is False
        assert data["network_required"] is False
        assert data["live_readiness"] is False
        assert data["not_financial_advice"] is True
        assert data["symbol"] == "DEMO-SYMBOL"
        assert data["safety"]["no_live_trading"] is True
        assert data["safety"]["no_provider_calls"] is True
        assert data["safety"]["no_broker_calls"] is True

    def test_multiple_regimes_strategies_and_variants_are_evaluated(self, tmp_path: Path) -> None:
        result = _run_robustness(tmp_path / "out")
        assert result.returncode == 0, result.stderr
        data = _load_report(tmp_path / "out")

        assert {item["name"] for item in data["regimes"]} == {
            "uptrend",
            "downtrend",
            "flat",
            "volatile",
        }
        assert all(item["row_count"] >= 90 for item in data["regimes"])

        strategies = {item["name"]: item for item in data["strategies"]}
        assert set(strategies) == {
            "buy_and_hold",
            "moving_average_cross",
            "rsi_mean_reversion",
        }
        assert strategies["buy_and_hold"]["variants_evaluated"] == 1
        assert strategies["moving_average_cross"]["variants_evaluated"] >= 3
        assert strategies["rsi_mean_reversion"]["variants_evaluated"] >= 3
        assert len(strategies["moving_average_cross"]["regime_results"]) >= 12

    def test_results_never_use_forbidden_live_or_profit_statuses(self, tmp_path: Path) -> None:
        result = _run_robustness(tmp_path / "out")
        assert result.returncode == 0, result.stderr
        data = _load_report(tmp_path / "out")

        for strategy in data["strategies"]:
            status = strategy["robustness_summary"]["paper_follow_up_status"]
            assert status in ALLOWED_STATUSES
            assert status not in FORBIDDEN_STATUSES
            for item in strategy["regime_results"]:
                assert item["live_ready"] is False
                decision = item["paper_gate"]["decision"]
                assert decision in {"paper_candidate", "needs_more_testing", "rejected"}
                assert decision not in FORBIDDEN_STATUSES

    def test_ranking_and_report_are_deterministic(self, tmp_path: Path) -> None:
        assert _run_robustness(tmp_path / "run1").returncode == 0
        assert _run_robustness(tmp_path / "run2").returncode == 0

        first = _load_report(tmp_path / "run1")
        second = _load_report(tmp_path / "run2")
        assert first["ranking"] == second["ranking"]
        assert first["strategies"] == second["strategies"]

    def test_no_provider_credentials_network_or_broker_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in (
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "MOONSHOT_API_KEY",
            "KIMI_API_KEY",
            "XAI_API_KEY",
            "GROK_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)

        def fail_network(*args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("network must not be called")

        monkeypatch.setattr("socket.create_connection", fail_network)
        report = build_paper_strategy_robustness(
            fixture_paths=FIXTURES,
            symbol="DEMO-SYMBOL",
            strategies=["moving_average_cross"],
        )
        assert report["provider_required"] is False
        assert report["broker_required"] is False
        assert report["network_required"] is False

    def test_demo_script_passes(self) -> None:
        result = subprocess.run(
            ["bash", str(DEMO_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Paper strategy robustness demo PASS" in result.stdout


class TestPaperStrategyRobustnessChecker:
    def test_checker_passes_on_real_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_checker_json_parses(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        data = json.loads(result.stdout)
        assert data["status"] == "pass"
        assert data["valid"] is True

    def test_checker_fails_for_guaranteed_profit_claim(self, tmp_path: Path) -> None:
        repo = _minimal_checker_repo(tmp_path)
        doc = repo / "docs" / "paper-strategy-robustness.md"
        doc.write_text(doc.read_text(encoding="utf-8") + "\nThis has guaranteed profit.\n", encoding="utf-8")
        result = _run_checker(repo)
        assert result.returncode == 1
        assert "guaranteed profit" in result.stdout.lower()

    def test_checker_fails_for_live_ready_claim(self, tmp_path: Path) -> None:
        repo = _minimal_checker_repo(tmp_path)
        doc = repo / "docs" / "paper-strategy-robustness.md"
        doc.write_text(doc.read_text(encoding="utf-8") + "\nThis is live ready.\n", encoding="utf-8")
        result = _run_checker(repo)
        assert result.returncode == 1
        assert "live ready" in result.stdout.lower()

    def test_checker_fails_if_demo_uses_live_mode(self, tmp_path: Path) -> None:
        repo = _minimal_checker_repo(tmp_path)
        demo = repo / "scripts" / "demo_paper_strategy_robustness.sh"
        demo.write_text(demo.read_text(encoding="utf-8") + "\natlas run --mode live\n", encoding="utf-8")
        result = _run_checker(repo)
        assert result.returncode == 1
        assert "--mode live" in result.stdout

    def test_checker_fails_if_v0613_claimed_released(self, tmp_path: Path) -> None:
        repo = _minimal_checker_repo(tmp_path)
        doc = repo / "docs" / "releases" / "v0.6.13-candidates.md"
        doc.write_text(doc.read_text(encoding="utf-8") + "\nv0.6.13 is released.\n", encoding="utf-8")
        result = _run_checker(repo)
        assert result.returncode == 1
        assert "v0.6.13 is released" in result.stdout.lower()

    def test_checker_does_not_mutate_files(self, tmp_path: Path) -> None:
        repo = _minimal_checker_repo(tmp_path)
        before = _tree_hashes(repo)
        result = _run_checker(repo)
        after = _tree_hashes(repo)
        assert result.returncode == 0, result.stdout + result.stderr
        assert before == after


def _run_checker(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )


def _minimal_checker_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for rel in [
        "docs",
        "docs/releases",
        "docs/trust",
        "scripts",
        "data/sample/regimes",
        "src/atlas_agent",
    ]:
        (repo / rel).mkdir(parents=True, exist_ok=True)

    for rel in [
        "docs/paper-strategy-robustness.md",
        "scripts/demo_paper_strategy_robustness.sh",
        "scripts/check_paper_strategy_robustness.py",
        "docs/releases/v0.6.13-candidate-selection.md",
        "docs/releases/v0.6.13-candidates.md",
        "docs/releases/v0.6.13-candidates.json",
        "docs/releases/v0.6.13-plan.md",
    ]:
        src = ROOT / rel
        dst = repo / rel
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        if rel.startswith("scripts/"):
            dst.chmod(0o755)

    for rel in [
        "docs/paper-strategy-evaluation.md",
        "docs/paper-strategy-sensitivity.md",
        "docs/paper-provider-isolation.md",
        "docs/autonomous-paper-workflow.md",
        "docs/bounded-live-autonomy-governance.md",
        "docs/autonomy-roadmap.md",
        "docs/public-launch-readiness.md",
        "docs/reviewer-checklist.md",
        "docs/trust/README.md",
    ]:
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("paper-only offline no-provider no-broker no-network CAND-027 paper strategy robustness\n", encoding="utf-8")

    for fixture in FIXTURES:
        shutil.copy2(fixture, repo / "data" / "sample" / "regimes" / fixture.name)

    (repo / "pyproject.toml").write_text('version = "0.6.24"\n', encoding="utf-8")
    (repo / "src" / "atlas_agent" / "__init__.py").write_text('__version__ = "0.6.24"\n', encoding="utf-8")
    (repo / "docs" / "releases" / "release-metadata.json").write_text(
        json.dumps(
            {
                "source_version": "0.6.24",
                "current_public_release": "v0.6.24",
                "next_planned_release": "v0.6.25",
                "pypi_published": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return repo


def _tree_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = str(path.relative_to(root))
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes
