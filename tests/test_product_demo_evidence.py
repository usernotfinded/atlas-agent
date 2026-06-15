from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEMO_SCRIPT = ROOT / "scripts" / "demo_product_walkthrough.sh"
BUILDER_SCRIPT = ROOT / "scripts" / "build_product_demo_evidence.py"
CHECKER_SCRIPT = ROOT / "scripts" / "check_product_demo_evidence.py"

FORBIDDEN_IMPLEMENTATION_PATTERNS = [
    "curl ",
    "wget ",
    "provider.execute",
    "execute_provider",
    "broker.submit",
    "submit_order",
    "--mode live",
]


def _run_checker(bundle_dir: Path, *, json_output: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(CHECKER_SCRIPT)]
    if json_output:
        cmd.append("--json")
    cmd.append(str(bundle_dir))
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def _build_valid_bundle(tmp_path: Path, *, deterministic: bool = True) -> Path:
    """Create a synthetic demo workspace and run the evidence builder on it."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".atlas").mkdir()
    (workspace / ".atlas" / "config.toml").write_text(
        'trading_mode = "paper"\nbroker.enable_live_trading = false\n',
        encoding="utf-8",
    )
    (workspace / ".atlas" / "discipline.md").write_text(
        "# Safe discipline profile\nManual approval required.\n",
        encoding="utf-8",
    )
    bt_dir = workspace / ".atlas" / "backtests" / "bt-001"
    bt_dir.mkdir(parents=True)
    (bt_dir / "result.json").write_text('{"ok": true}\n', encoding="utf-8")
    (bt_dir / "report.md").write_text("# Backtest report\n", encoding="utf-8")

    out_dir = tmp_path / "evidence"
    out_dir.mkdir()
    outputs = out_dir / "outputs"
    outputs.mkdir()

    (outputs / "validate.txt").write_text(
        "Live trading: Disabled by default.\n"
        "can_submit=false\n"
        "paper mode\n"
        "no credentials loaded\n",
        encoding="utf-8",
    )
    (outputs / "doctor.txt").write_text(
        '{"provider_execution": "locked", "broker_execution": "blocked", '
        '"execution_enabled": false, "network_check": "skipped"}\n',
        encoding="utf-8",
    )
    for name in [
        "init.txt",
        "discipline.txt",
        "config-symbol.txt",
        "paper-dry-run.txt",
        "backtest.txt",
        "backtest-runs.txt",
        "audit.txt",
    ]:
        (outputs / name).write_text("ok\n", encoding="utf-8")

    commands_file = out_dir / "commands.txt"
    commands_file.write_text(
        "init workspace --template routine-trader\n"
        "discipline setup --manual --yes\n"
        "config set market.symbol ATLAS-DEMO\n"
        "validate\n"
        "doctor --json\n"
        "run --mode paper --dry-run --symbol ATLAS-DEMO\n"
        "backtest run --symbol DEMO-SYMBOL --data data/sample/ohlcv.csv\n"
        "backtest runs --validate --json\n"
        "audit verify --all\n",
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        str(BUILDER_SCRIPT),
        "--output-dir",
        str(out_dir),
        "--workspace",
        str(workspace),
        "--commands-file",
        str(commands_file),
    ]
    if deterministic:
        cmd.append("--deterministic")

    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"Builder failed:\n{result.stderr}\n{result.stdout}"
    return out_dir


def test_builder_and_checker_pass_on_valid_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _build_valid_bundle(Path(tmp))
        result = _run_checker(bundle_dir)
        assert result.returncode == 0, (
            f"Checker failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "PASSED" in result.stdout


def test_checker_json_output_on_valid_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _build_valid_bundle(Path(tmp))
        result = _run_checker(bundle_dir, json_output=True)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["passed"] is True
        assert "errors" in data
        assert "warnings" in data
        assert "Product demo evidence check PASSED" in data["summary"]


def test_checker_fails_on_missing_required_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _build_valid_bundle(Path(tmp))
        (bundle_dir / "summary.md").unlink()
        result = _run_checker(bundle_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("summary.md" in err for err in data["errors"])


def test_checker_fails_on_unsafe_json_values() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _build_valid_bundle(Path(tmp))
        evidence_path = bundle_dir / "evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["live_trading_enabled"] = True
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")

        result = _run_checker(bundle_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("live_trading_enabled" in err for err in data["errors"])


def test_checker_fails_on_credential_like_strings() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _build_valid_bundle(Path(tmp))
        summary = bundle_dir / "summary.md"
        summary.write_text(
            summary.read_text(encoding="utf-8")
            + "\nSecret token: sk-abcdefghijklmnopqrstuvwxyz\n",
            encoding="utf-8",
        )
        result = _run_checker(bundle_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("Secret-like pattern" in err for err in data["errors"])


def test_checker_fails_on_forbidden_claims() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle_dir = _build_valid_bundle(Path(tmp))
        summary = bundle_dir / "summary.md"
        summary.write_text(
            summary.read_text(encoding="utf-8") + "\nAtlas provides guaranteed profit.\n",
            encoding="utf-8",
        )
        result = _run_checker(bundle_dir, json_output=True)
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["passed"] is False
        assert any("guaranteed" in err.lower() or "profit" in err.lower() for err in data["errors"])


def test_demo_script_help_and_rejects_unknown_options() -> None:
    help_result = subprocess.run(
        [str(DEMO_SCRIPT), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "Usage:" in help_result.stdout
    assert "--output-dir" in help_result.stdout

    bad_result = subprocess.run(
        [str(DEMO_SCRIPT), "--not-a-real-option"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert bad_result.returncode != 0, "Unknown option should be rejected"
    assert "Unknown option" in bad_result.stderr


@pytest.mark.slow
def test_demo_script_generates_evidence_bundle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "evidence"
        result = subprocess.run(
            [str(DEMO_SCRIPT), "--output-dir", str(out_dir), "--deterministic"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            f"Demo script failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert (out_dir / "evidence.json").exists()
        assert (out_dir / "summary.md").exists()

        evidence = json.loads((out_dir / "evidence.json").read_text(encoding="utf-8"))
        assert evidence["demo_mode"] == "paper/dry-run"
        assert evidence["live_trading_enabled"] is False
        assert evidence["provider_execution"] is False
        assert evidence["broker_execution"] is False
        assert evidence["credentials_loaded"] is False
        assert evidence["network_required"] is False
        for key in [
            "live_trading_disabled",
            "paper_mode",
            "provider_execution_locked",
            "broker_execution_blocked",
            "no_credentials_required",
            "no_network_calls",
        ]:
            assert evidence["safety_checks_summary"][key] is True, key

        check_result = _run_checker(out_dir)
        assert check_result.returncode == 0, (
            f"Evidence checker failed on generated bundle:\n"
            f"stdout:\n{check_result.stdout}\nstderr:\n{check_result.stderr}"
        )


def test_demo_script_implies_no_network_broker_provider_execution() -> None:
    """The demo script must not contain patterns that imply network/provider/broker execution."""
    text = DEMO_SCRIPT.read_text(encoding="utf-8").lower()
    for phrase in FORBIDDEN_IMPLEMENTATION_PATTERNS:
        assert phrase.lower() not in text, (
            f"{DEMO_SCRIPT.name} contains unsafe pattern: {phrase}"
        )
