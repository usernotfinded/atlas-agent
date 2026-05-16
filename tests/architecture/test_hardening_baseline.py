from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from atlas_agent.cli import build_parser, main
from atlas_agent.cli_commands import build_core_command_registry
from atlas_agent.cli_context import CLIContext
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


def test_cli_imports_parser_and_registry() -> None:
    parser = build_parser()
    args = parser.parse_args(["memory", "rebuild-index"])
    assert args.command == "memory"
    assert args.memory_command == "rebuild-index"
    assert build_core_command_registry().dispatch


def test_core_command_registry_dispatches_status(tmp_path: Path, capsys) -> None:
    config = _config(tmp_path)
    args = build_parser().parse_args(["status"])
    context = CLIContext(
        args=args,
        config=config,
        resolution=object(),  # type: ignore[arg-type]
        update_checker=lambda: None,
    )

    assert build_core_command_registry().dispatch(context) == 0
    assert "Atlas Agent Status" in capsys.readouterr().out


def test_memory_rebuild_index_cli_contract(tmp_path: Path, capsys) -> None:
    config = _config(tmp_path)
    config.ensure_dirs()
    (config.memory_dir / "trade_journal.md").write_text("alpha thesis\n", encoding="utf-8")

    with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
        assert main(["memory", "rebuild-index"]) == 0

    assert (config.memory_dir / "memory.sqlite").exists()
    assert "Memory search index rebuilt: 1 Markdown files indexed." in capsys.readouterr().out
