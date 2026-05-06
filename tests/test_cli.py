from __future__ import annotations

from omni_trade_ai.cli import main


def test_omni_trade_help_works(capsys) -> None:
    assert main(["--help"]) == 0
    assert "omni-trade" in capsys.readouterr().out


def test_omni_trade_validate_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["validate"]) == 0
    assert "Configuration valid" in capsys.readouterr().out


def test_omni_trade_backtest_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["backtest", "--strategy", "moving_average", "--symbol", "BTC-USD"]) == 0
    assert "Backtest complete" in capsys.readouterr().out


def test_omni_trade_run_once_paper_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["run-once", "--mode", "paper"]) == 0
    assert "paper result: filled" in capsys.readouterr().out


def test_omni_trade_run_once_live_fails_safely_by_default(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["run-once", "--mode", "live"]) == 2
    output = capsys.readouterr().out
    assert "live result: rejected" in output
    assert "ENABLE_LIVE_TRADING must be true" in output

