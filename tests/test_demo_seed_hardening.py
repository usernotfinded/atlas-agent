from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.safety.secrets import scan_text_for_secrets


def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def test_demo_seed_creates_synthetic_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["demo", "seed"]) == 0

    output = capsys.readouterr().out
    assert "Demo seed wrote:" in output

    expected = [
        config.memory_dir / "portfolio.md",
        config.memory_dir / "watchlist.md",
        config.memory_dir / "trade_journal.md",
        config.memory_dir / "mistakes.md",
        config.reports_dir / "reflections" / "demo-reflection.md",
        config.memory_dir.parent / "skills" / "proposed" / "avoid_overtrading.md",
    ]
    for path in expected:
        assert path.exists()

    all_text = "\n".join(path.read_text(encoding="utf-8") for path in expected)
    assert "synthetic" in all_text.lower()
    assert scan_text_for_secrets(all_text) == []
    assert re.search(r"\baccount_id\b", all_text, flags=re.IGNORECASE) is None
    assert re.search(r"\b(?:sk-|pk_test_|AKIA|xoxb-|ghp_)", all_text) is None


def test_demo_seed_refuses_workspace_with_possible_real_credentials(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    (tmp_path / ".env").write_text("ALPACA_API_KEY=real-looking\n", encoding="utf-8")

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["demo", "seed"]) == 2

    err = capsys.readouterr().err
    assert "demo seed warning" in err
