import json
from pathlib import Path

from atlas_agent.backtest.portfolio import (
    ALLOWED_DECISION_STATUSES,
    ALLOWED_REVIEW_LEDGER_STATUSES,
    build_paper_portfolio_review_pack,
    build_paper_portfolio_review_ledger,
    render_portfolio_review_ledger_markdown,
    write_portfolio_review_ledger_reports,
)

DATA_PATH = Path("data/sample/ohlcv_extended.csv")


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
