# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_strategy_evaluation.py
# PURPOSE: Verifies paper strategy evaluation behavior and regression
#         expectations.
# DEPS:    hashlib, importlib, json, os, shutil, socket, additional local
#         modules.
# ==============================================================================

"""Tests for paper strategy evaluation (CAND-025).

No real provider or broker calls.
"""

# --- IMPORTS ---

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from atlas_agent.backtest.evaluation import (
    build_paper_strategy_evaluation,
    parse_strategy_parameters,
    render_strategy_evaluation_markdown,
)


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_paper_strategy_evaluation.py"
DEMO_SCRIPT = ROOT / "scripts" / "demo_paper_strategy_evaluation.sh"
PAPER_EVAL_DOC = ROOT / "docs" / "paper-strategy-evaluation.md"

PROVIDER_ENV_KEYS = [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY",
    "KIMI_API_KEY",
    "XAI_API_KEY",
    "GROK_API_KEY",
    "ATLAS_OPENROUTER_API_KEY",
    "ATLAS_OPENAI_API_KEY",
    "ATLAS_ANTHROPIC_API_KEY",
]

FORBIDDEN_DECISIONS = {
    "live_ready",
    "production_ready",
    "safe_to_trade_live",
    "approved_for_live",
    "guaranteed_profit",
    "outperforms_market",
}

ALLOWED_DECISIONS = {"paper_candidate", "needs_more_testing", "rejected"}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _scrubbed_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + (
        f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else ""
    )
    for key in PROVIDER_ENV_KEYS:
        env.pop(key, None)
    return env


def _run_compare(output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "atlas_agent.cli",
            "backtest",
            "compare",
            "--data",
            "data/sample/ohlcv.csv",
            "--symbol",
            "DEMO-SYMBOL",
            "--strategies",
            "buy_and_hold,moving_average_cross,rsi_mean_reversion",
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        env=_scrubbed_env(),
        capture_output=True,
        text=True,
    )


def _run_checker(args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT)]
    if args:
        cmd.extend(args)
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def _load_checker_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_paper_strategy_evaluation", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_paper_strategy_evaluation"] = mod
    spec.loader.exec_module(mod)
    return mod


def _copy_text(tmp_dir: Path, rel: str) -> None:
    src = ROOT / rel
    dst = tmp_dir / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _make_isolated_repo(
    tmp_path: Path,
    *,
    doc_patch: dict[str, tuple[str, str]] | None = None,
    script_patch: dict[str, str] | None = None,
    metadata_patch: dict[str, str] | None = None,
) -> Path:
    tmp_dir = tmp_path / "repo"
    tmp_dir.mkdir()

    for rel in [
        "pyproject.toml",
        "docs/paper-strategy-evaluation.md",
        "docs/paper-provider-isolation.md",
        "docs/autonomous-paper-workflow.md",
        "docs/bounded-live-autonomy-governance.md",
        "docs/releases/v0.6.13-candidate-selection.md",
        "docs/releases/v0.6.13-candidates.md",
        "docs/releases/v0.6.13-candidates.json",
        "docs/releases/v0.6.13-plan.md",
        "docs/releases/release-metadata.json",
        "scripts/release_metadata.py",
        "scripts/demo_paper_strategy_evaluation.sh",
        "src/atlas_agent/cli.py",
        "src/atlas_agent/backtest/evaluation.py",
    ]:
        _copy_text(tmp_dir, rel)

    script_dst = tmp_dir / "scripts" / "demo_paper_strategy_evaluation.sh"
    if script_patch:
        text = script_dst.read_text(encoding="utf-8")
        for old, new in script_patch.items():
            text = text.replace(old, new)
        script_dst.write_text(text, encoding="utf-8")
    os.chmod(script_dst, 0o755)

    if doc_patch:
        for rel, (old, new) in doc_patch.items():
            path = tmp_dir / rel
            path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    if metadata_patch:
        path = tmp_dir / "docs" / "releases" / "release-metadata.json"
        text = path.read_text(encoding="utf-8")
        for old, new in metadata_patch.items():
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    checker_text = SCRIPT.read_text(encoding="utf-8").replace(
        "REPO_ROOT = Path(__file__).resolve().parent.parent",
        f'REPO_ROOT = Path("{tmp_dir}")',
    )
    checker_dst = tmp_dir / "scripts" / "check_paper_strategy_evaluation.py"
    checker_dst.write_text(checker_text, encoding="utf-8")
    os.chmod(checker_dst, 0o755)
    return tmp_dir


def _run_isolated_checker(tmp_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tmp_dir / "scripts" / "check_paper_strategy_evaluation.py")],
        capture_output=True,
        text=True,
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestPaperStrategyEvaluationCommand:
    def test_command_writes_schema_and_markdown(self, tmp_path: Path) -> None:
        result = _run_compare(tmp_path / "out")
        assert result.returncode == 0, result.stdout + result.stderr

        json_path = tmp_path / "out" / "strategy-evaluation.json"
        md_path = tmp_path / "out" / "strategy-evaluation.md"
        assert json_path.exists()
        assert md_path.exists()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["artifact_type"] == "paper_strategy_evaluation"
        assert data["schema_version"] == 1
        assert data["mode"] == "paper"
        assert data["provider_required"] is False
        assert data["broker_required"] is False
        assert data["network_required"] is False
        assert data["live_readiness"] is False
        assert data["not_financial_advice"] is True
        assert data["symbol"] == "DEMO-SYMBOL"
        assert data["data_source"] == "data/sample/ohlcv.csv"
        assert len(data["strategies"]) >= 1

        for item in data["strategies"]:
            assert item["live_ready"] is False
            assert item["provider_required"] is False
            assert item["broker_required"] is False
            assert item["network_required"] is False
            assert item["paper_gate"]["decision"] in ALLOWED_DECISIONS
            assert item["paper_gate"]["decision"] not in FORBIDDEN_DECISIONS
            assert {"total_return", "max_drawdown", "win_rate"} <= set(item["metrics"])

        markdown = md_path.read_text(encoding="utf-8")
        assert "paper-only" in markdown.lower()
        assert "not financial advice" in markdown.lower()
        assert "No gate decision is approval for live trading." in markdown

    def test_ranking_is_deterministic_across_repeated_runs(self, tmp_path: Path) -> None:
        first = _run_compare(tmp_path / "first")
        second = _run_compare(tmp_path / "second")
        assert first.returncode == 0, first.stdout + first.stderr
        assert second.returncode == 0, second.stdout + second.stderr

        first_payload = json.loads((tmp_path / "first" / "strategy-evaluation.json").read_text())
        second_payload = json.loads((tmp_path / "second" / "strategy-evaluation.json").read_text())
        assert first_payload == second_payload
        assert first_payload["ranking"] == second_payload["ranking"]
        assert [item["rank"] for item in first_payload["ranking"]] == [1, 2, 3]

    def test_provider_credentials_not_required(self, tmp_path: Path) -> None:
        result = _run_compare(tmp_path / "out")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "No live trading, broker calls, provider calls, or network calls." in result.stdout

    def test_builder_does_not_use_socket_or_broker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fail_socket(*args: object, **kwargs: object) -> None:
            raise AssertionError("network socket should not be used")

        monkeypatch.setattr(socket, "socket", fail_socket)

        from atlas_agent.brokers.paper import PaperBroker

        def fail_broker(*args: object, **kwargs: object) -> None:
            raise AssertionError("broker should not be constructed")

        monkeypatch.setattr(PaperBroker, "__init__", fail_broker)

        report = build_paper_strategy_evaluation(
            data_path=str(ROOT / "data" / "sample" / "ohlcv.csv"),
            symbol="DEMO-SYMBOL",
            strategies=["moving_average_cross"],
        )
        assert report["provider_required"] is False
        assert report["broker_required"] is False
        assert report["network_required"] is False
        assert report["strategies"][0]["live_ready"] is False


class TestDemoAndChecker:
    def test_demo_script_passes(self) -> None:
        result = subprocess.run(
            ["bash", str(DEMO_SCRIPT)],
            cwd=ROOT,
            env=_scrubbed_env(),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Paper strategy evaluation demo PASS" in result.stdout

    def test_checker_passes_on_repo(self) -> None:
        result = _run_checker()
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASSED" in result.stdout

    def test_checker_json_output_parses(self) -> None:
        result = _run_checker(["--json"])
        assert result.returncode == 0, result.stdout + result.stderr
        data = json.loads(result.stdout)
        assert data["passed"] is True
        meta = json.loads((ROOT / "docs" / "releases" / "release-metadata.json").read_text())
        assert data["package_version"] == meta["source_version"]
        assert data["current_public_tag"] == meta["current_public_release"]
        assert data["next_planned_tag"] == meta["next_planned_release"]
        assert data["pypi_published"] is False
        assert data["errors"] == []

    def test_checker_module_reports_current_repo_pass(self) -> None:
        mod = _load_checker_module()
        result = mod.run_checks(ROOT)
        assert result["passed"] is True

    def test_checker_does_not_mutate_files(self) -> None:
        paths = [
            PAPER_EVAL_DOC,
            DEMO_SCRIPT,
            SCRIPT,
            ROOT / "docs" / "releases" / "v0.6.13-candidates.json",
        ]
        before = {path: _digest(path) for path in paths}
        result = _run_checker()
        after = {path: _digest(path) for path in paths}
        assert result.returncode == 0, result.stdout + result.stderr
        assert before == after


class TestCheckerFailures:
    def test_checker_fails_if_docs_claim_guaranteed_profit(self, tmp_path: Path) -> None:
        tmp = _make_isolated_repo(
            tmp_path,
            doc_patch={
                "docs/paper-strategy-evaluation.md": (
                    "This is not financial advice.",
                    "This is guaranteed profit.",
                )
            },
        )
        result = _run_isolated_checker(tmp)
        assert result.returncode == 1
        assert "guaranteed profit" in result.stdout.lower()

    def test_checker_fails_if_docs_claim_live_ready(self, tmp_path: Path) -> None:
        tmp = _make_isolated_repo(
            tmp_path,
            doc_patch={
                "docs/paper-strategy-evaluation.md": (
                    "not live readiness",
                    "live ready",
                )
            },
        )
        result = _run_isolated_checker(tmp)
        assert result.returncode == 1
        assert "live ready" in result.stdout.lower()

    def test_checker_fails_if_demo_uses_live_mode(self, tmp_path: Path) -> None:
        tmp = _make_isolated_repo(
            tmp_path,
            script_patch={
                "atlas backtest compare \\": "atlas backtest compare \\\n  # --mode live \\",
            },
        )
        result = _run_isolated_checker(tmp)
        assert result.returncode == 1
        assert "--mode live" in result.stdout.lower()

    def test_checker_fails_if_v0613_claimed_released(self, tmp_path: Path) -> None:
        tmp = _make_isolated_repo(
            tmp_path,
            doc_patch={
                "docs/releases/v0.6.13-plan.md": (
                    "planning only",
                    "v0.6.13 is released",
                )
            },
        )
        result = _run_isolated_checker(tmp)
        assert result.returncode == 1
        assert "v0.6.13" in result.stdout.lower()
        assert "released" in result.stdout.lower()

    def test_checker_fails_if_release_metadata_moves_to_next_planned(self, tmp_path: Path, release_identity: dict) -> None:
        current_public = release_identity["current_public_release"]
        next_planned = release_identity["next_planned_release"]
        tmp = _make_isolated_repo(
            tmp_path,
            metadata_patch={f'"current_public_release": "{current_public}"': f'"current_public_release": "{next_planned}"'},
        )
        result = _run_isolated_checker(tmp)
        assert result.returncode == 1
        assert "current_public_release" in result.stdout


def _write_crossing_series(path: Path) -> Path:
    """Write a series whose moving averages cross in both directions."""
    prices = [100, 98, 96, 94, 96, 100, 104, 108, 110, 108,
              104, 100, 96, 94, 96, 100, 105, 110, 114, 118]
    rows = ["date,symbol,open,high,low,close,volume"]
    for index, price in enumerate(prices, start=1):
        rows.append(f"2026-04-{index:02d},ZIG,{price},{price + 1},{price - 1},{price},1000")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


class TestStrategyParameterOverrides:
    """Overrides must reach the engine while the risk gate still applies."""

    def test_override_changes_the_evaluated_run(self, tmp_path: Path) -> None:
        data_path = _write_crossing_series(tmp_path / "crossing.csv")

        baseline = build_paper_strategy_evaluation(
            data_path=data_path,
            symbol="ZIG",
            strategies=["moving_average_cross"],
        )
        # The default allocates all equity, so every order trips a risk limit.
        # A smaller allocation is the only difference between the two runs.
        overridden = build_paper_strategy_evaluation(
            data_path=data_path,
            symbol="ZIG",
            strategies=["moving_average_cross"],
            parameters={"moving_average_cross": {"position_pct": 0.05}},
        )

        assert baseline["strategies"][0]["metrics"]["exposure_time_pct"] == 0.0
        assert overridden["strategies"][0]["metrics"]["exposure_time_pct"] > 0.0

    def test_risk_gate_still_blocks_an_oversized_allocation(self, tmp_path: Path) -> None:
        data_path = _write_crossing_series(tmp_path / "crossing.csv")

        report = build_paper_strategy_evaluation(
            data_path=data_path,
            symbol="ZIG",
            strategies=["moving_average_cross"],
            parameters={"moving_average_cross": {"position_pct": 1.0}},
        )

        entry = report["strategies"][0]
        assert entry["safety_blocker_count"] > 0
        assert entry["risk_manager_enabled"] is True

    def test_a_strategy_without_an_override_keeps_its_defaults(self, tmp_path: Path) -> None:
        data_path = _write_crossing_series(tmp_path / "crossing.csv")

        baseline = build_paper_strategy_evaluation(
            data_path=data_path,
            symbol="ZIG",
            strategies=["buy_and_hold", "moving_average_cross"],
        )
        partial = build_paper_strategy_evaluation(
            data_path=data_path,
            symbol="ZIG",
            strategies=["buy_and_hold", "moving_average_cross"],
            parameters={"moving_average_cross": {"position_pct": 0.05}},
        )

        assert baseline["strategies"][0]["name"] == "buy_and_hold"
        assert baseline["strategies"][0]["metrics"] == partial["strategies"][0]["metrics"]

    def test_out_of_range_override_fails_one_entry_without_aborting(self, tmp_path: Path) -> None:
        data_path = _write_crossing_series(tmp_path / "crossing.csv")

        report = build_paper_strategy_evaluation(
            data_path=data_path,
            symbol="ZIG",
            strategies=["moving_average_cross", "buy_and_hold"],
            parameters={"moving_average_cross": {"short_window": 0}},
        )

        failed = report["strategies"][0]
        assert failed["name"] == "moving_average_cross"
        assert failed["status"] != "evaluated"
        assert report["strategies"][1]["status"] == "evaluated"


class TestComparisonCarriesBenchmarkAndDiagnostics:
    """A comparison must say what each run was measured against, and why."""

    def test_each_entry_reports_its_benchmark(self) -> None:
        report = build_paper_strategy_evaluation(
            data_path=ROOT / "data" / "sample" / "ohlcv.csv",
            symbol="DEMO-SYMBOL",
            strategies=["buy_and_hold", "moving_average_cross"],
        )

        for item in report["strategies"]:
            benchmark = item["benchmark"]
            assert benchmark["benchmark_id"] == "buy_and_hold"
            assert benchmark["return_pct"] is not None
            # Excess return is what makes the comparison meaningful: a ranking
            # without it cannot say whether a strategy beat holding the asset.
            expected = item["metrics"]["total_return_pct"] - benchmark["return_pct"]
            assert benchmark["excess_return_pct"] == pytest.approx(expected)

    def test_each_entry_preserves_its_run_diagnostics(self) -> None:
        report = build_paper_strategy_evaluation(
            data_path=ROOT / "data" / "sample" / "ohlcv.csv",
            symbol="DEMO-SYMBOL",
            strategies=["moving_average_cross"],
        )

        diagnostics = report["strategies"][0]["diagnostics"]
        assert diagnostics["run_id"]
        assert diagnostics["status"] == "completed"
        assert diagnostics["strategy_validation"]["strategy_id"] == "moving_average_cross"
        assert diagnostics["strategy_validation"]["status"] == "valid"

    def test_entries_report_the_parameters_they_ran_with(self) -> None:
        report = build_paper_strategy_evaluation(
            data_path=ROOT / "data" / "sample" / "ohlcv.csv",
            symbol="DEMO-SYMBOL",
            strategies=["moving_average_cross"],
            parameters={"moving_average_cross": {"short_window": 2, "long_window": 6}},
        )

        assert report["strategies"][0]["parameters"] == {
            "short_window": 2,
            "long_window": 6,
        }

    def test_failed_entry_keeps_the_same_shape(self) -> None:
        """A reader must not have to branch on status to read an entry."""
        report = build_paper_strategy_evaluation(
            data_path=ROOT / "data" / "sample" / "ohlcv.csv",
            symbol="DEMO-SYMBOL",
            strategies=["moving_average_cross", "buy_and_hold"],
            parameters={"moving_average_cross": {"short_window": 0}},
        )

        failed, evaluated = report["strategies"]
        assert failed["status"] == "failed"
        assert set(evaluated) - set(failed) == set()
        # The rejected parameter is echoed, because it is why the run failed.
        assert failed["parameters"] == {"short_window": 0}
        assert failed["benchmark"]["return_pct"] is None

    def test_markdown_shows_the_benchmark_columns(self, tmp_path: Path) -> None:
        report = build_paper_strategy_evaluation(
            data_path=ROOT / "data" / "sample" / "ohlcv.csv",
            symbol="DEMO-SYMBOL",
            strategies=["buy_and_hold"],
        )
        markdown = render_strategy_evaluation_markdown(report)

        assert "Benchmark %" in markdown
        assert "Excess %" in markdown


class TestStrategyParametersFlag:
    """`--strategy-parameters` must reach the run or fail loudly."""

    def _run_compare_with_parameters(
        self, output_dir: Path, raw: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "atlas_agent.cli",
                "backtest",
                "compare",
                "--data",
                "data/sample/ohlcv.csv",
                "--symbol",
                "DEMO-SYMBOL",
                "--strategies",
                "moving_average_cross",
                "--strategy-parameters",
                raw,
                "--output-dir",
                str(output_dir),
            ],
            cwd=ROOT,
            env=_scrubbed_env(),
            capture_output=True,
            text=True,
        )

    def test_flag_reaches_the_evaluated_run(self, tmp_path: Path) -> None:
        result = self._run_compare_with_parameters(
            tmp_path / "out",
            '{"moving_average_cross": {"short_window": 2, "long_window": 6}}',
        )
        assert result.returncode == 0, result.stdout + result.stderr

        data = json.loads((tmp_path / "out" / "strategy-evaluation.json").read_text())
        assert data["strategies"][0]["parameters"] == {
            "short_window": 2,
            "long_window": 6,
        }

    def test_malformed_json_fails_instead_of_running_on_defaults(
        self, tmp_path: Path
    ) -> None:
        """Silently ignoring the override would report a run nobody asked for."""
        result = self._run_compare_with_parameters(tmp_path / "out", "{not json")

        assert result.returncode != 0
        assert "not valid JSON" in result.stdout + result.stderr
        assert not (tmp_path / "out" / "strategy-evaluation.json").exists()

    def test_non_object_entry_is_rejected(self, tmp_path: Path) -> None:
        result = self._run_compare_with_parameters(
            tmp_path / "out", '{"moving_average_cross": [2, 6]}'
        )

        assert result.returncode != 0
        assert "must be a JSON object" in result.stdout + result.stderr


class TestParseStrategyParameters:
    def test_none_means_no_overrides(self) -> None:
        assert parse_strategy_parameters(None) is None

    def test_valid_mapping_is_returned(self) -> None:
        assert parse_strategy_parameters('{"buy_and_hold": {"position_pct": 0.5}}') == {
            "buy_and_hold": {"position_pct": 0.5}
        }

    def test_top_level_must_be_an_object(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_strategy_parameters('["buy_and_hold"]')
