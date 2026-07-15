# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_paper_trading_guide.py
# PURPOSE: Verifies paper trading guide behavior and regression expectations.
# DEPS:    json, tomllib, pathlib, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from atlas_agent.config import AtlasConfig


# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "paper-trading-guide.md"
DEMO_SCRIPT = ROOT / "scripts" / "demo_paper_workflow.sh"
EXAMPLE_README = ROOT / "examples" / "paper_trading_demo" / "README.md"
EXAMPLE_CONFIG = ROOT / "examples" / "paper_trading_demo" / "config.toml"
CANDIDATES_JSON = ROOT / "docs" / "releases" / "v0.6.11-candidates.json"
CANDIDATES_MD = ROOT / "docs" / "releases" / "v0.6.11-candidates.md"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def test_guide_has_complete_safe_local_workflow() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    required = (
        "Not financial advice",
        "./scripts/demo_paper_workflow.sh",
        "atlas discipline setup --manual --yes",
        "atlas config set market.symbol ATLAS-DEMO",
        "atlas validate",
        "atlas doctor --json",
        "atlas run --mode paper --dry-run --symbol ATLAS-DEMO",
        "data/sample/ohlcv.csv",
        "DEMO-SYMBOL",
        "atlas backtest runs --validate --json",
        "atlas audit verify --all",
        "Trading and simulated trading involve uncertainty",
        "results do not guarantee future performance",
        "preflight-diagnostics.md",
        "reviewer-golden-path.md",
    )
    for phrase in required:
        assert phrase in text


def test_guide_and_example_avoid_live_network_and_secret_instructions() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (GUIDE, EXAMPLE_README, EXAMPLE_CONFIG, DEMO_SCRIPT)
    )
    lower = text.lower()
    forbidden = (
        "--mode live",
        "enable_live_trading = true",
        "enable_live_submit = true",
        "allow_leverage = true",
        "curl ",
        "wget ",
        "requests.",
        "httpx.",
        "socket.",
        "api_key =",
        "secret_key =",
        "password =",
        "token =",
        "without any financial risk",
        "guaranteed profit",
    )
    for phrase in forbidden:
        assert phrase not in lower


def test_example_config_parses_to_fail_closed_defaults() -> None:
    raw = tomllib.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    config = AtlasConfig(**raw)

    assert config.trading_mode == "paper"
    assert config.broker.provider == "none"
    assert config.broker.enable_live_trading is False
    assert config.broker.enable_live_submit is False
    assert config.risk.allow_leverage is False
    assert config.safety.require_order_approval is True
    assert config.audit.redact_secrets is True
    assert config.notifications.enabled is False


def test_demo_script_remains_offline_dry_run_only() -> None:
    text = DEMO_SCRIPT.read_text(encoding="utf-8")

    assert "run_step doctor --json" in text
    assert 'run_step run --mode paper --dry-run --symbol "$DEMO_SYMBOL"' in text
    assert "backtest run" in text
    assert "--mode live" not in text
    assert "curl " not in text
    assert "wget " not in text


def test_only_cand_001_through_007_are_implemented() -> None:
    data = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    candidates = {candidate["id"]: candidate for candidate in data["candidates"]}

    for candidate_id in (
        "CAND-001",
        "CAND-002",
        "CAND-003",
        "CAND-004",
        "CAND-005",
        "CAND-006",
        "CAND-007",
    ):
        assert candidates[candidate_id]["selected_for_v0611"] is True
        assert candidates[candidate_id]["implemented"] is True
    for candidate_id in ("CAND-008", "CAND-009", "CAND-010"):
        assert candidates[candidate_id]["selected_for_v0611"] is False
        assert candidates[candidate_id]["implemented"] is False

    markdown = CANDIDATES_MD.read_text(encoding="utf-8")
    assert "CAND-004** — Paper-trading workflow documentation and safe examples — **implemented**" in markdown
    assert "CAND-005** — Release/checker simplification after v0.6.10 — **implemented**" in markdown
    assert "CAND-007** — User-facing quickstart and reviewer demo consolidation — **implemented**" in markdown
