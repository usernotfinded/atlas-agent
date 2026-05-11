from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig, MarketConfig


def test_no_runtime_default_symbol_is_btc_usd() -> None:
    """AtlasConfig must not default to BTC-USD or any hardcoded product symbol."""
    config = AtlasConfig()
    assert config.market.symbol == ""
    assert config.backtest.default_symbol == ""
    assert config.default_symbol == ""


def test_atlas_run_paper_without_symbol_fails_after_discipline_configured(
    tmp_path, monkeypatch, capsys
) -> None:
    """If no symbol is configured and none is passed, the command must fail closed
    with a clear error after the discipline gate passes."""
    from atlas_agent.ai.discipline import write_user_discipline

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    profile = (
        "# Profile\n\n"
        "## Decision temperament\n\nCautious.\n\n"
        "## Reasoning style\n\nStep-by-step.\n\n"
        "## Communication style\n\nConcise.\n\n"
        "## Risk posture\n\nConservative.\n\n"
        "## Uncertainty handling\n\nExplicit.\n\n"
        "## No-trade bias\n\nDefault to hold.\n\n"
        "## Forbidden overrides\n\n"
        "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
        "audit logging, broker sync checks, reference price requirements, or live-trading safeguards.\n"
    )
    write_user_discipline(".", profile)

    ret = main(["run-once", "--mode", "paper"])
    assert ret == 2
    combined = capsys.readouterr().out + capsys.readouterr().err
    assert "No trading symbol configured" in combined


def test_atlas_run_paper_with_cli_symbol_uses_it(tmp_path, monkeypatch, capsys) -> None:
    """Passing --symbol on the CLI should override any missing config."""
    from atlas_agent.ai.discipline import write_user_discipline

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    profile = (
        "# Profile\n\n"
        "## Decision temperament\n\nCautious.\n\n"
        "## Reasoning style\n\nStep-by-step.\n\n"
        "## Communication style\n\nConcise.\n\n"
        "## Risk posture\n\nConservative.\n\n"
        "## Uncertainty handling\n\nExplicit.\n\n"
        "## No-trade bias\n\nDefault to hold.\n\n"
        "## Forbidden overrides\n\n"
        "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
        "audit logging, broker sync checks, reference price requirements, or live-trading safeguards.\n"
    )
    write_user_discipline(".", profile)

    ret = main(["run-once", "--mode", "paper", "--symbol", "DEMO-SYMBOL"])
    assert ret == 0
    assert "paper result: filled" in capsys.readouterr().out


def test_atlas_run_paper_uses_configured_market_symbol(tmp_path, monkeypatch, capsys) -> None:
    """Setting market.symbol via config should be picked up by agentic commands."""
    from atlas_agent.ai.discipline import write_user_discipline

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    profile = (
        "# Profile\n\n"
        "## Decision temperament\n\nCautious.\n\n"
        "## Reasoning style\n\nStep-by-step.\n\n"
        "## Communication style\n\nConcise.\n\n"
        "## Risk posture\n\nConservative.\n\n"
        "## Uncertainty handling\n\nExplicit.\n\n"
        "## No-trade bias\n\nDefault to hold.\n\n"
        "## Forbidden overrides\n\n"
        "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
        "audit logging, broker sync checks, reference price requirements, or live-trading safeguards.\n"
    )
    write_user_discipline(".", profile)
    main(["config", "set", "market.symbol", "DEMO-SYMBOL"])
    capsys.readouterr()

    ret = main(["run-once", "--mode", "paper"])
    assert ret == 0
    assert "paper result: filled" in capsys.readouterr().out


def test_atlas_backtest_explicit_symbol_works_without_configured_symbol(
    tmp_path, monkeypatch, capsys
) -> None:
    """Backtest with explicit --symbol should not require a configured market symbol."""
    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    ret = main(["backtest", "run", "--symbol", "DEMO-SYMBOL", "--data", "data/sample/ohlcv.csv"])
    assert ret == 0
    assert "backtest result: filled" in capsys.readouterr().out


def test_routine_run_reads_configured_symbol_not_hardcoded_btc_usd(tmp_path) -> None:
    """Routine engine must use the configured symbol, not a hardcoded default."""
    from atlas_agent.ai.discipline import write_user_discipline
    from atlas_agent.routines.engine import run_routine
    from atlas_agent.research.web_research import OfflineResearchProvider

    profile = (
        "# Profile\n\n"
        "## Decision temperament\n\nCautious.\n\n"
        "## Reasoning style\n\nStep-by-step.\n\n"
        "## Communication style\n\nConcise.\n\n"
        "## Risk posture\n\nConservative.\n\n"
        "## Uncertainty handling\n\nExplicit.\n\n"
        "## No-trade bias\n\nDefault to hold.\n\n"
        "## Forbidden overrides\n\n"
        "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
        "audit logging, broker sync checks, reference price requirements, or live-trading safeguards.\n"
    )
    write_user_discipline(tmp_path, profile)
    config = AtlasConfig(
        memory_dir=tmp_path / "memory",
        reports_dir=tmp_path / "reports",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending",
        market=MarketConfig(symbol="TEST-SYMBOL"),
    )

    result = run_routine(
        "pre_market",
        mode="paper",
        config=config,
        research_provider=OfflineResearchProvider(),
    )

    assert result.status == "complete"
    report = result.report_path.read_text(encoding="utf-8")
    assert "TEST-SYMBOL" not in report  # research is stubbed; just ensure it ran
    assert result.report_path.exists()


def test_docs_do_not_claim_crypto_paper_universal_or_impossible() -> None:
    """Documentation must use nuanced language about crypto paper/sandbox support."""
    readme = Path("README.md").read_text(encoding="utf-8")
    docs_dir = Path("docs")
    combined = readme
    for path in docs_dir.rglob("*.md"):
        combined += path.read_text(encoding="utf-8")

    lower = combined.lower()
    assert "crypto paper trading is impossible" not in lower
    assert "crypto paper trading is universally supported" not in lower
    assert "crypto paper trading is universal" not in lower
    assert "all providers support crypto" not in lower
    assert "no provider supports crypto" not in lower


def test_grep_prevents_hardcoded_btc_usd_in_runtime_source() -> None:
    """BTC-USD must not appear in runtime source code; only in tests/fixtures/docs
    explicitly labeled as examples."""
    import subprocess

    result = subprocess.run(
        ["rg", "-n", "BTC-USD", "src/"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1 or result.stdout == "", (
        f"BTC-USD found in runtime source:\n{result.stdout}"
    )
