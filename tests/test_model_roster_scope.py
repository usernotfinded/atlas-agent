from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig


def _config(tmp_path: Path) -> AtlasConfig:
    return AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        data_path=tmp_path / "data" / "ohlcv.csv",
    )


def test_model_roster_list_json_is_reference_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["models", "list", "--json"]) == 0
    output = capsys.readouterr().out
    assert '"reference_only": true' in output
    assert '"runtime_orchestration": false' in output


def test_runtime_execution_does_not_require_model_roster_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    roster_path = tmp_path / "configs" / "model_roster.yaml"
    roster_path.unlink(missing_ok=True)
    capsys.readouterr()

    assert main(["run-once", "--mode", "paper"]) == 0
    output = capsys.readouterr().out
    assert "paper result:" in output
