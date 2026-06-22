import json
import os
import shutil
import subprocess
from pathlib import Path

from scripts.check_paper_human_review_policy import check_all

from atlas_agent.backtest.portfolio import (
    ALLOWED_POLICY_RESULT_STATES,
    ALLOWED_REVIEW_POLICY_STATUSES,
    POLICY_RULES,
    build_paper_portfolio_review_pack,
    build_paper_portfolio_review_ledger,
    build_paper_portfolio_review_policy,
    render_portfolio_review_policy_markdown,
    write_portfolio_review_policy_reports,
)

DATA_PATH = Path("data/sample/ohlcv_extended.csv")


def _build_review_pack():
    return build_paper_portfolio_review_pack(
        data_path=str(DATA_PATH),
        symbol="DEMO-SYMBOL",
        strategies=["buy_and_hold", "moving_average_cross"],
    )


def test_policy_builder_with_artifact_paths(tmp_path):
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

    assert policy["artifact_type"] == "paper_human_review_policy"
    assert policy["schema_version"] == 1
    assert policy["release"] == "v0.6.15-planning"
    assert policy["source_release"] == "v0.6.14"
    assert policy["mode"] == "paper"
    assert policy["non_executable"] is True
    assert policy["paper_only"] is True
    assert policy["provider_required"] is False
    assert policy["broker_required"] is False
    assert policy["network_required"] is False
    assert policy["live_submit_enabled"] is False
    assert policy["orders_generated"] is False
    assert policy["notifications_sent"] is False
    assert policy["real_human_approval"] is False
    assert policy["not_financial_advice"] is True
    assert policy["not_live_ready"] is True
    assert policy["source_artifact_types"] == [
        "paper_human_review_pack",
        "paper_human_review_ledger",
    ]
    assert isinstance(policy["source_artifact_digests"]["paper_human_review_pack"], str)
    assert isinstance(policy["source_artifact_digests"]["paper_human_review_ledger"], str)
    assert policy["overall_policy_status"] in ALLOWED_REVIEW_POLICY_STATUSES
    assert policy["gate_summary"] == {
        "paper_follow_up_allowed": True,
        "live_path_blocked": True,
        "broker_submission_allowed": False,
        "provider_execution_allowed": False,
        "notification_sending_allowed": False,
        "real_order_generation_allowed": False,
    }

    policy_results = policy["policy_results"]
    assert len(policy_results) >= 10
    for result in policy_results:
        assert result["state"] in ALLOWED_POLICY_RESULT_STATES



def test_policy_builder_with_build_kwargs():
    policy = build_paper_portfolio_review_policy(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )

    assert policy["artifact_type"] == "paper_human_review_policy"
    assert policy["schema_version"] == 1
    assert policy["source_artifact_types"] == [
        "paper_human_review_pack",
        "paper_human_review_ledger",
    ]
    assert policy["overall_policy_status"] in ALLOWED_REVIEW_POLICY_STATUSES
    for result in policy["policy_results"]:
        assert result["state"] in ALLOWED_POLICY_RESULT_STATES


def test_policy_builder_requires_path_or_kwargs():
    try:
        build_paper_portfolio_review_policy()
    except ValueError:
        return
    raise AssertionError("Expected ValueError when neither path nor kwargs are provided")


def test_policy_is_deterministic():
    policy_one = build_paper_portfolio_review_policy(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold", "moving_average_cross"],
        }
    )
    policy_two = build_paper_portfolio_review_policy(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold", "moving_average_cross"],
        }
    )
    assert policy_one == policy_two


def test_policy_writer_outputs_files(tmp_path):
    policy = build_paper_portfolio_review_policy(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    json_path, md_path = write_portfolio_review_policy_reports(
        policy, output_dir=str(tmp_path)
    )
    assert json_path.exists()
    assert md_path.exists()
    assert json_path.name == "paper-human-review-policy.json"
    assert md_path.name == "paper-human-review-policy.md"

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_policy"


def test_policy_markdown_safety_phrases():
    policy = build_paper_portfolio_review_policy(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    md_text = render_portfolio_review_policy_markdown(policy).lower()
    assert "paper-only" in md_text
    assert "non-executable" in md_text
    assert "not financial advice" in md_text
    assert "not live ready" in md_text
    assert "not live trading approval" in md_text
    assert "not a real human decision" in md_text
    assert "not an executable order" in md_text
    assert "gate summary" in md_text
    assert "policy rules" in md_text
    assert "policy rules and results" in md_text
    assert "paper_follow_up_allowed" in md_text
    assert "live_path_blocked" in md_text
    assert "broker_submission_allowed" in md_text


def test_policy_gate_summary_blocks_live_paths():
    policy = build_paper_portfolio_review_policy(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    summary = policy["gate_summary"]
    assert summary["live_path_blocked"] is True
    assert summary["broker_submission_allowed"] is False
    assert summary["provider_execution_allowed"] is False
    assert summary["notification_sending_allowed"] is False
    assert summary["real_order_generation_allowed"] is False
    assert summary["paper_follow_up_allowed"] is True


def test_policy_real_human_approval_false():
    policy = build_paper_portfolio_review_policy(
        build_kwargs={
            "data_path": str(DATA_PATH),
            "symbol": "DEMO-SYMBOL",
            "strategies": ["buy_and_hold"],
        }
    )
    assert policy["real_human_approval"] is False
    assert policy["safety"]["no_real_human_approval"] is True


def test_policy_source_digests_match_loaded_files(tmp_path):
    pack = _build_review_pack()
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    pack_path = pack_dir / "paper-human-review-pack.json"
    pack_text = json.dumps(pack, sort_keys=True, allow_nan=False)
    pack_path.write_text(pack_text)

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
    ledger_text = json.dumps(ledger, sort_keys=True, allow_nan=False)
    ledger_path.write_text(ledger_text)

    policy = build_paper_portfolio_review_policy(
        review_pack_path=str(pack_path),
        review_ledger_path=str(ledger_path),
    )
    expected_pack_digest = __import__("hashlib").sha256(
        pack_text.encode("utf-8")
    ).hexdigest()
    expected_ledger_digest = __import__("hashlib").sha256(
        ledger_text.encode("utf-8")
    ).hexdigest()
    assert policy["source_artifact_digests"]["paper_human_review_pack"] == expected_pack_digest
    assert policy["source_artifact_digests"]["paper_human_review_ledger"] == expected_ledger_digest



def _run_cli(*args):
    return subprocess.run(
        ["python3.11", "-m", "atlas_agent.cli", "backtest", "portfolio-review-policy", *args],
        capture_output=True,
        text=True,
    )


def test_policy_cli_without_artifacts(tmp_path):
    result = _run_cli(
        "--symbol", "DEMO-SYMBOL",
        "--data", str(DATA_PATH),
        "--strategies", "buy_and_hold,moving_average_cross",
        "--output-dir", str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    json_path = tmp_path / "paper-human-review-policy.json"
    md_path = tmp_path / "paper-human-review-policy.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_policy"
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
    assert data["overall_policy_status"] in ALLOWED_REVIEW_POLICY_STATUSES
    assert data["gate_summary"] == {
        "paper_follow_up_allowed": True,
        "live_path_blocked": True,
        "broker_submission_allowed": False,
        "provider_execution_allowed": False,
        "notification_sending_allowed": False,
        "real_order_generation_allowed": False,
    }
    assert isinstance(data["policy_results"], list)
    for result in data["policy_results"]:
        assert result["state"] in ALLOWED_POLICY_RESULT_STATES


def test_policy_cli_with_artifacts(tmp_path):
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

    output_dir = tmp_path / "policy"
    result = _run_cli(
        "--review-pack", str(pack_path),
        "--review-ledger", str(ledger_path),
        "--output-dir", str(output_dir),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    json_path = output_dir / "paper-human-review-policy.json"
    md_path = output_dir / "paper-human-review-policy.md"
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text())
    assert data["artifact_type"] == "paper_human_review_policy"
    assert data["source_artifact_types"] == [
        "paper_human_review_pack",
        "paper_human_review_ledger",
    ]
    assert len(data["policy_results"]) >= 10


def test_policy_cli_json_output(tmp_path):
    result = _run_cli(
        "--symbol", "DEMO-SYMBOL",
        "--data", str(DATA_PATH),
        "--strategies", "buy_and_hold",
        "--output-dir", str(tmp_path),
        "--json",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    data = json.loads(result.stdout)
    assert data["artifact_type"] == "paper_human_review_policy"
    assert data["mode"] == "paper"
    assert data["non_executable"] is True
    assert data["overall_policy_status"] in ALLOWED_REVIEW_POLICY_STATUSES
    assert data["gate_summary"]["live_path_blocked"] is True
    assert data["gate_summary"]["broker_submission_allowed"] is False
    assert data["gate_summary"]["provider_execution_allowed"] is False
    assert data["gate_summary"]["notification_sending_allowed"] is False
    assert data["gate_summary"]["real_order_generation_allowed"] is False
    assert data["gate_summary"]["paper_follow_up_allowed"] is True


def test_policy_cli_help_includes_command():
    result = subprocess.run(
        ["python3.11", "-m", "atlas_agent.cli", "backtest", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "portfolio-review-policy" in result.stdout


def test_demo_script_passes():
    result = subprocess.run(
        ["bash", "scripts/demo_paper_human_review_policy.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Paper human review policy simulation demo PASS" in result.stdout


def test_checker_passes_on_real_repo_and_json_parses():
    result = subprocess.run(
        ["python3.11", "scripts/check_paper_human_review_policy.py", "--json"],
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
        "docs/paper-human-review-policy.md",
        "scripts/demo_paper_human_review_policy.sh",
        "scripts/check_paper_human_review_policy.py",
        "tests/test_paper_human_review_policy.py",
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
    (root / "pyproject.toml").write_text('version = "0.6.14"\n')
    (root / "src/atlas_agent/__init__.py").write_text('__version__ = "0.6.14"\n')
    os.chmod(root / "scripts/demo_paper_human_review_policy.sh", 0o755)
    return root


def test_checker_does_not_mutate_files(tmp_path):
    root = _checker_root(tmp_path)
    before = _snapshot(root)
    assert check_all(root) == []
    after = _snapshot(root)
    assert before == after


def test_checker_fails_on_forbidden_claim_in_docs(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-policy.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nguaranteed profit\n")
    issues = check_all(root)
    assert any("guaranteed profit" in issue for issue in issues)


def test_checker_fails_on_executable_order_language(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-policy.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\nplace order now\n")
    issues = check_all(root)
    assert any("place order" in issue for issue in issues)


def test_checker_fails_on_live_approval_language(tmp_path):
    root = _checker_root(tmp_path)
    doc_path = root / "docs/paper-human-review-policy.md"
    doc_path.write_text(doc_path.read_text(encoding="utf-8") + "\napproved for live\n")
    issues = check_all(root)
    assert any("approved for live" in issue for issue in issues)


def test_checker_fails_when_demo_missing_non_executable_statement(tmp_path):
    root = _checker_root(tmp_path)
    demo_path = root / "scripts/demo_paper_human_review_policy.sh"
    content = demo_path.read_text(encoding="utf-8").replace("non-executable", "reviewable")
    demo_path.write_text(content)
    issues = check_all(root)
    assert any("non-executable" in issue for issue in issues)


def test_checker_fails_when_demo_missing_no_real_human_approval(tmp_path):
    root = _checker_root(tmp_path)
    demo_path = root / "scripts/demo_paper_human_review_policy.sh"
    content = demo_path.read_text(encoding="utf-8").replace("no real human approval", "reviewer sign-off")
    demo_path.write_text(content)
    issues = check_all(root)
    assert any("no real human approval" in issue for issue in issues)


def test_checker_fails_when_v0615_candidate_doc_missing_cand003(tmp_path):
    root = _checker_root(tmp_path)
    plan_path = root / "docs/releases/v0.6.15-plan.md"
    plan_path.write_text("# v0.6.15 Release Plan\n\nStatus: planning-only.\nCAND-001 and CAND-002 only.\n")
    issues = check_all(root)
    assert any("CAND-003" in issue for issue in issues)


def test_checker_fails_when_cli_command_missing(tmp_path):
    root = _checker_root(tmp_path)
    cli_path = root / "src/atlas_agent/cli.py"
    cli_path.write_text("# placeholder cli file\n")
    issues = check_all(root)
    assert any("portfolio-review-policy" in issue for issue in issues)


def _snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
