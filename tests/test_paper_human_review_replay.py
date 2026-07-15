# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_human_review_replay.py
# PURPOSE: Verifies paper human review replay behavior and regression
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

from scripts.check_paper_human_review_replay import check_all

from atlas_agent.backtest.portfolio import (
    ALLOWED_REVIEW_REPLAY_STATUSES,
    build_paper_portfolio_review_pack,
    build_paper_portfolio_review_ledger,
    build_paper_portfolio_review_policy,
    build_paper_portfolio_review_replay,
    render_portfolio_review_replay_markdown,
    write_portfolio_review_replay_reports,
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


def test_replay_builder_with_artifact_paths(tmp_path):
    pack = _build_review_pack()
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack_path = pack_dir / "paper-human-review-pack.json"
    pack_path.write_text(json.dumps(pack, indent=2, sort_keys=True, allow_nan=False))

    ledger = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold", "moving_average_cross"],
        }
    )
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "paper-human-review-ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False))

    policy = build_paper_portfolio_review_policy(
        review_pack_path=str(pack_path),
        review_ledger_path=str(ledger_path),
    )
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    policy_path = policy_dir / "paper-human-review-policy.json"
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True, allow_nan=False))

    replay = build_paper_portfolio_review_replay(
        review_pack_path=str(pack_path),
        review_ledger_path=str(ledger_path),
        review_policy_path=str(policy_path),
    )

    assert replay["artifact_type"] == "paper_human_review_replay"
    assert replay["schema_version"] == 1
    assert replay["release"] == "v0.6.15-planning"
    assert replay["source_release"] == "v0.6.14"
    assert replay["mode"] == "paper"
    assert replay["non_executable"] is True
    assert replay["paper_only"] is True
    assert replay["provider_required"] is False
    assert replay["broker_required"] is False
    assert replay["network_required"] is False
    assert replay["live_submit_enabled"] is False
    assert replay["orders_generated"] is False
    assert replay["notifications_sent"] is False
    assert replay["real_human_approval"] is False
    assert replay["not_financial_advice"] is True
    assert replay["not_live_ready"] is True
    assert replay["source_artifact_types"] == [
        "paper_human_review_pack",
        "paper_human_review_ledger",
        "paper_human_review_policy",
    ]
    assert isinstance(replay["source_artifact_digests"]["paper_human_review_pack"], str)
    assert isinstance(replay["source_artifact_digests"]["paper_human_review_ledger"], str)
    assert isinstance(replay["source_artifact_digests"]["paper_human_review_policy"], str)
    assert replay["overall_replay_status"] in ALLOWED_REVIEW_REPLAY_STATUSES
    assert replay["gate_summary"] == {
        "deterministic_replay_passed": True,
        "paper_chain_intact": True,
        "paper_follow_up_allowed": True,
        "live_path_blocked": True,
        "broker_submission_allowed": False,
        "provider_execution_allowed": False,
        "notification_sending_allowed": False,
        "real_order_generation_allowed": False,
    }

    regression_checks = replay["regression_checks"]
    assert len(regression_checks) >= 10
    for check in regression_checks:
        assert check["passed"] is True

    replayed_artifacts = replay["replayed_artifacts"]
    assert len(replayed_artifacts) == 3
    for artifact in replayed_artifacts:
        assert artifact["artifact_type"] in replay["source_artifact_types"]
        assert artifact["schema_version"] == 1
        assert isinstance(artifact["digest"], str)


def test_replay_builder_with_build_kwargs():
    replay = build_paper_portfolio_review_replay(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )

    assert replay["artifact_type"] == "paper_human_review_replay"
    assert replay["schema_version"] == 1
    assert replay["source_artifact_types"] == [
        "paper_human_review_pack",
        "paper_human_review_ledger",
        "paper_human_review_policy",
    ]
    assert replay["overall_replay_status"] in ALLOWED_REVIEW_REPLAY_STATUSES
    assert len(replay["regression_checks"]) >= 10
    for check in replay["regression_checks"]:
        assert check["passed"] is True


def test_replay_builder_requires_path_or_kwargs():
    try:
        build_paper_portfolio_review_replay()
    except ValueError:
        return
    raise AssertionError("Expected ValueError when neither path nor kwargs are provided")


def test_replay_is_deterministic():
    build_kwargs = {
        "data_path": str(DATA_PATH),
        "symbol": "DEMO-SYMBOL",
        "strategies": ["buy_and_hold", "moving_average_cross"],
    }
    replay_one = build_paper_portfolio_review_replay(build_kwargs=build_kwargs)
    replay_two = build_paper_portfolio_review_replay(build_kwargs=build_kwargs)
    assert replay_one == replay_two


def test_replay_writer_outputs_files(tmp_path):
    replay = build_paper_portfolio_review_replay(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    json_path, md_path = write_portfolio_review_replay_reports(
        replay, output_dir=str(tmp_path)
    )
    assert json_path.exists()
    assert md_path.exists()
    assert json_path.name == "paper-human-review-replay.json"
    assert md_path.name == "paper-human-review-replay.md"

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_replay"


def test_replay_markdown_safety_phrases():
    replay = build_paper_portfolio_review_replay(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    md_text = render_portfolio_review_replay_markdown(replay).lower()
    assert "paper-only" in md_text
    assert "non-executable" in md_text
    assert "not financial advice" in md_text
    assert "not live ready" in md_text
    assert "not live trading approval" in md_text
    assert "not a real human decision" in md_text
    assert "not an executable order" in md_text
    assert "gate summary" in md_text
    assert "regression checks" in md_text
    assert "paper follow up allowed" in md_text
    assert "deterministic replay" in md_text
    assert "paper chain intact" in md_text
    assert "live path blocked" in md_text


def test_replay_gate_summary_blocks_live_paths():
    replay = build_paper_portfolio_review_replay(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    summary = replay["gate_summary"]
    assert summary["deterministic_replay_passed"] is True
    assert summary["paper_chain_intact"] is True
    assert summary["live_path_blocked"] is True
    assert summary["broker_submission_allowed"] is False
    assert summary["provider_execution_allowed"] is False
    assert summary["notification_sending_allowed"] is False
    assert summary["real_order_generation_allowed"] is False
    assert summary["paper_follow_up_allowed"] is True


def test_replay_real_human_approval_false():
    replay = build_paper_portfolio_review_replay(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    assert replay["real_human_approval"] is False
    assert replay["safety"]["no_real_human_approval"] is True


def test_replay_source_digests_match_loaded_files(tmp_path):
    pack = _build_review_pack()
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack_path = pack_dir / "paper-human-review-pack.json"
    pack_path.write_text(json.dumps(pack, indent=2, sort_keys=True, allow_nan=False))
    pack_text = pack_path.read_text(encoding="utf-8")

    ledger = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold", "moving_average_cross"],
        }
    )
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    ledger_path = ledger_dir / "paper-human-review-ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False))
    ledger_text = ledger_path.read_text(encoding="utf-8")

    policy = build_paper_portfolio_review_policy(
        review_pack_path=str(pack_path),
        review_ledger_path=str(ledger_path),
    )
    policy_dir = tmp_path / "policy"
    policy_dir.mkdir()
    policy_path = policy_dir / "paper-human-review-policy.json"
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True, allow_nan=False))
    policy_text = policy_path.read_text(encoding="utf-8")

    replay = build_paper_portfolio_review_replay(
        review_pack_path=str(pack_path),
        review_ledger_path=str(ledger_path),
        review_policy_path=str(policy_path),
    )
    expected_pack_digest = __import__("hashlib").sha256(
        pack_text.encode("utf-8")
    ).hexdigest()
    expected_ledger_digest = __import__("hashlib").sha256(
        ledger_text.encode("utf-8")
    ).hexdigest()
    expected_policy_digest = __import__("hashlib").sha256(
        policy_text.encode("utf-8")
    ).hexdigest()
    assert replay["source_artifact_digests"]["paper_human_review_pack"] == expected_pack_digest
    assert replay["source_artifact_digests"]["paper_human_review_ledger"] == expected_ledger_digest
    assert replay["source_artifact_digests"]["paper_human_review_policy"] == expected_policy_digest


def _run_cli(*args):
    return subprocess.run(
        ["python3.11", "-m", "atlas_agent.cli", "backtest", "portfolio-review-replay", *args],
        capture_output=True,
        text=True,
    )


def test_replay_cli_without_artifacts(tmp_path):
    result = _run_cli(
        "--symbol", "DEMO-SYMBOL",
        "--data", str(DATA_PATH),
        "--strategies", "buy_and_hold,moving_average_cross",
        "--output-dir", str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    json_path = tmp_path / "paper-human-review-replay.json"
    md_path = tmp_path / "paper-human-review-replay.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_replay"
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
    assert data["overall_replay_status"] in ALLOWED_REVIEW_REPLAY_STATUSES
    assert data["gate_summary"] == {
        "deterministic_replay_passed": True,
        "paper_chain_intact": True,
        "paper_follow_up_allowed": True,
        "live_path_blocked": True,
        "broker_submission_allowed": False,
        "provider_execution_allowed": False,
        "notification_sending_allowed": False,
        "real_order_generation_allowed": False,
    }
    assert isinstance(data["regression_checks"], list)
    for check in data["regression_checks"]:
        assert check["passed"] is True


def test_replay_cli_with_artifacts(tmp_path):
    pack = _build_review_pack()
    pack_path = tmp_path / "paper-human-review-pack.json"
    pack_path.write_text(json.dumps(pack, indent=2, sort_keys=True, allow_nan=False))

    ledger = build_paper_portfolio_review_ledger(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold", "moving_average_cross"],
        }
    )
    ledger_path = tmp_path / "paper-human-review-ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False))

    policy = build_paper_portfolio_review_policy(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold", "moving_average_cross"],
        }
    )
    policy_path = tmp_path / "paper-human-review-policy.json"
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True, allow_nan=False))

    output_dir = tmp_path / "replay"
    result = _run_cli(
        "--review-pack", str(pack_path),
        "--review-ledger", str(ledger_path),
        "--review-policy", str(policy_path),
        "--output-dir", str(output_dir),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    json_path = output_dir / "paper-human-review-replay.json"
    md_path = output_dir / "paper-human-review-replay.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_replay"
    assert data["source_artifact_types"] == [
        "paper_human_review_pack",
        "paper_human_review_ledger",
        "paper_human_review_policy",
    ]
    assert len(data["regression_checks"]) >= 10
    assert len(data["replayed_artifacts"]) == 3


def test_replay_cli_json_output(tmp_path):
    result = _run_cli(
        "--symbol", "DEMO-SYMBOL",
        "--data", str(DATA_PATH),
        "--strategies", "buy_and_hold",
        "--output-dir", str(tmp_path),
        "--json",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    data = json.loads(result.stdout)
    assert data["artifact_type"] == "paper_human_review_replay"
    assert data["mode"] == "paper"
    assert data["non_executable"] is True
    assert data["overall_replay_status"] in ALLOWED_REVIEW_REPLAY_STATUSES
    assert data["gate_summary"]["deterministic_replay_passed"] is True
    assert data["gate_summary"]["paper_chain_intact"] is True
    assert data["gate_summary"]["live_path_blocked"] is True
    assert data["gate_summary"]["broker_submission_allowed"] is False
    assert data["gate_summary"]["provider_execution_allowed"] is False
    assert data["gate_summary"]["notification_sending_allowed"] is False
    assert data["gate_summary"]["real_order_generation_allowed"] is False
    assert data["gate_summary"]["paper_follow_up_allowed"] is True


def test_replay_cli_help_includes_command():
    result = subprocess.run(
        ["python3.11", "-m", "atlas_agent.cli", "backtest", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "portfolio-review-replay" in result.stdout


def test_demo_script_passes():
    result = subprocess.run(
        ["bash", "scripts/demo_paper_human_review_replay.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Paper human review replay demo PASS" in result.stdout


def test_checker_passes_on_real_repo_and_json_parses():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_human_review_replay.py", "--json"],
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
        "docs/paper-human-review-replay.md",
        "scripts/demo_paper_human_review_replay.sh",
        "scripts/check_paper_human_review_replay.py",
        "tests/test_paper_human_review_replay.py",
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
    os.chmod(root / "scripts/demo_paper_human_review_replay.sh", 0o755)
    return root


def test_checker_does_not_mutate_files(tmp_path):
    root = _checker_root(tmp_path)
    before = _snapshot(root)
    assert check_all(root) == []
    after = _snapshot(root)
    assert before == after


def test_checker_fails_on_forbidden_claim_in_docs(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-replay.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nguaranteed profit\n")
    issues = check_all(root)
    assert any("guaranteed profit" in issue for issue in issues)


def test_checker_fails_on_executable_order_language(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-replay.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nplace order now\n")
    issues = check_all(root)
    assert any("place order" in issue for issue in issues)


def test_checker_fails_on_live_approval_language(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-replay.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\napproved for live\n")
    issues = check_all(root)
    assert any("approved for live" in issue for issue in issues)


def test_checker_fails_when_demo_missing_non_executable_statement(tmp_path):
    root = _checker_root(tmp_path)
    demo_path = root / "scripts/demo_paper_human_review_replay.sh"
    content = demo_path.read_text(encoding="utf-8").replace("non-executable", "reviewable")
    demo_path.write_text(content)
    issues = check_all(root)
    assert any("non-executable" in issue for issue in issues)


def test_checker_fails_when_demo_missing_no_real_human_approval(tmp_path):
    root = _checker_root(tmp_path)
    demo_path = root / "scripts/demo_paper_human_review_replay.sh"
    content = demo_path.read_text(encoding="utf-8").replace("no real human approval", "reviewer sign-off")
    demo_path.write_text(content)
    issues = check_all(root)
    assert any("no real human approval" in issue for issue in issues)


def test_checker_fails_when_v0615_candidate_doc_missing_cand004(tmp_path):
    root = _checker_root(tmp_path)
    plan_path = root / "docs/releases/v0.6.15-plan.md"
    plan_path.write_text("# v0.6.15 Release Plan\n\nStatus: planning-only.\nCAND-001, CAND-002, and CAND-003 only.\n")
    issues = check_all(root)
    assert any("CAND-004" in issue for issue in issues)


def test_checker_fails_when_cli_command_missing(tmp_path):
    root = _checker_root(tmp_path)
    cli_path = root / "src/atlas_agent/cli.py"
    cli_path.write_text("# placeholder cli file\n")
    issues = check_all(root)
    assert any("portfolio-review-replay" in issue for issue in issues)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
