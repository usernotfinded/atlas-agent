from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import atlas_agent
import pytest
from atlas_agent.cli import main
from atlas_agent.config import get_config


def test_atlas_help_works(capsys) -> None:
    assert main(["--help"]) == 0
    assert "atlas" in capsys.readouterr().out


def test_atlas_package_imports() -> None:
    assert atlas_agent.__name__ == "atlas_agent"


def test_python_module_help_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "atlas_agent.cli", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "atlas" in result.stdout


def test_main_branding_no_legacy_reference() -> None:
    readme = open("README.md", encoding="utf-8").read()

    assert "# Atlas Agent" in readme
    assert ("Omni" + "TradeAI") not in readme


def test_atlas_validate_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["validate"]) == 0
    assert "Workspace initialized missing" in capsys.readouterr().out


def test_config_edit_uses_argv_for_editor_launch(tmp_path, monkeypatch) -> None:
    from atlas_agent.config.paths import get_config_toml_path

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EDITOR", "code --wait")

    with patch("atlas_agent.cli.subprocess.run") as mock_run:
        assert main(["config", "edit"]) == 0

    args, kwargs = mock_run.call_args
    assert args[0] == ["code", "--wait", str(get_config_toml_path())]
    assert kwargs["check"] is False
    assert "shell" not in kwargs


def test_config_edit_does_not_execute_shell_metacharacters(tmp_path, monkeypatch) -> None:
    from atlas_agent.config.paths import get_config_toml_path

    monkeypatch.chdir(tmp_path)
    hacked_path = tmp_path / "hacked"
    monkeypatch.setenv("EDITOR", "code --wait; touch hacked")

    with patch("atlas_agent.cli.subprocess.run") as mock_run:
        assert main(["config", "edit"]) == 0

    args, kwargs = mock_run.call_args
    assert args[0] == [
        "code",
        "--wait;",
        "touch",
        "hacked",
        str(get_config_toml_path()),
    ]
    assert kwargs["check"] is False
    assert kwargs.get("shell", False) is False
    assert not hacked_path.exists()


def _create_cli_pending_order(tmp_path: Path):
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    path = manager.create_pending_order(order)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return manager, order, path, payload


def _write_cli_pending_payload(path: Path, payload: dict) -> None:
    from atlas_agent.execution.approval import _compute_order_hash

    payload["order_hash"] = _compute_order_hash(payload["order"])
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_approve_order_invalid_id_fails_safely(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    code = main(["approve-order", "../secret"])

    captured = capsys.readouterr()
    assert code == 2
    assert "Invalid pending order id" in captured.out
    assert "../secret" not in captured.out
    assert "../secret" not in captured.err
    assert not (tmp_path / "secret.json").exists()


def test_cli_approve_order_valid_v2_succeeds(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 0
    assert "Approved pending order" in captured.out

    payload = json.loads((tmp_path / "pending_orders" / f"{order.id}.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "2"
    assert payload["approved"] is True
    assert payload["status"] == "approved"


def test_cli_approve_order_upgrades_valid_v1_to_v2(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager, _order_to_dict
    from atlas_agent.execution.order import Order
    from datetime import UTC, datetime, timedelta

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    v1_payload = {
        "order": _order_to_dict(order),
        "approved": False,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(v1_payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 0
    assert "Approved pending order" in captured.out

    upgraded = json.loads(path.read_text(encoding="utf-8"))
    assert upgraded["schema_version"] == "2"
    assert upgraded["approved"] is True
    assert upgraded["status"] == "approved"


def test_cli_approve_order_malformed_json_fails_controlled(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    path = manager.path_for(order.id)
    path.write_text("not valid json {{{", encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    # Safe message must not leak raw payload content
    assert "not valid json" not in captured.out
    assert "not valid json" not in captured.err


def test_cli_approve_order_unsupported_schema_fails_controlled(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    path = manager.path_for(order.id)
    path.write_text(json.dumps({"schema_version": "99"}, indent=2), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()


def test_cli_approve_order_hash_mismatch_fails_controlled(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    # Tamper the order payload
    path = manager.path_for(order.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["order"]["quantity"] = 999.0
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    # Must not leak tampered values
    assert "999.0" not in captured.out
    assert "999.0" not in captured.err


def test_cli_approve_order_unsupported_schema_with_fake_secret_does_not_leak(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    path = manager.path_for(order.id)
    path.write_text(json.dumps({"schema_version": "FAKE_API_KEY_12345"}, indent=2), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    assert "FAKE_API_KEY_12345" not in captured.out
    assert "FAKE_API_KEY_12345" not in captured.err


def test_cli_approve_order_non_string_expires_at_fails_controlled(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager, _compute_order_hash, _order_to_dict
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    order_dict = _order_to_dict(order)
    payload = {
        "schema_version": "2",
        "order": order_dict,
        "order_hash": _compute_order_hash(order_dict),
        "approved": False,
        "expires_at": 12345,
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    assert "12345" not in captured.out
    assert "12345" not in captured.err


def test_cli_approve_order_top_level_non_object_json_fails_controlled(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    path = manager.path_for(order.id)
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()


def test_cli_approve_order_invalid_order_fields_fails_controlled(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager, _compute_order_hash, _order_to_dict
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    order_dict = _order_to_dict(order)
    # Remove required field to make it invalid but hash still matches
    del order_dict["side"]
    payload = {
        "schema_version": "2",
        "order": order_dict,
        "order_hash": _compute_order_hash(order_dict),
        "approved": False,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", "1"),
        ("limit_price", "100"),
    ],
)
def test_cli_approve_order_matching_hash_string_numeric_order_fields_fail_controlled(
    tmp_path,
    monkeypatch,
    capsys,
    field: str,
    value: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    _, order, path, payload = _create_cli_pending_order(tmp_path)
    payload["order"][field] = value
    _write_cli_pending_payload(path, payload)

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    assert value not in captured.out
    assert value not in captured.err


def test_cli_approve_order_matching_hash_invalid_order_created_at_fails_controlled(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    _, order, path, payload = _create_cli_pending_order(tmp_path)
    payload["order"]["created_at"] = "not-a-date"
    _write_cli_pending_payload(path, payload)

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    assert "not-a-date" not in captured.out
    assert "not-a-date" not in captured.err


def test_cli_approve_order_missing_status_transitions_fails_controlled(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    _, order, path, payload = _create_cli_pending_order(tmp_path)
    del payload["status_transitions"]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()


def test_cli_approve_order_non_list_status_transitions_fails_controlled(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    _, order, path, payload = _create_cli_pending_order(tmp_path)
    payload["status_transitions"] = {"status": "LEAK_SECRET_TRANSITION"}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    assert "LEAK_SECRET_TRANSITION" not in captured.out
    assert "LEAK_SECRET_TRANSITION" not in captured.err


def test_cli_approve_order_no_raw_values_leak(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager, _compute_order_hash, _order_to_dict
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    order_dict = _order_to_dict(order)
    order_dict["side"] = "LEAK_SECRET_999"
    payload = {
        "schema_version": "2",
        "order": order_dict,
        "order_hash": _compute_order_hash(order_dict),
        "approved": False,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
    }
    path = manager.path_for(order.id)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    assert "LEAK_SECRET_999" not in captured.out
    assert "LEAK_SECRET_999" not in captured.err


def test_cli_approve_order_does_not_generate_client_order_id(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 0

    payload = json.loads((tmp_path / "pending_orders" / f"{order.id}.json").read_text(encoding="utf-8"))
    assert payload["client_order_id"] is None


def test_cli_approve_order_does_not_call_broker_place_order(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    with patch("atlas_agent.cli._broker_for_mode") as mock_broker:
        code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 0
    mock_broker.assert_not_called()


def test_cli_approve_order_does_not_call_live_sync(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    with patch("atlas_agent.brokers.sync.BrokerSyncService") as mock_sync:
        code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 0
    mock_sync.assert_not_called()


def test_cli_approve_order_does_not_call_risk_manager(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    with patch("atlas_agent.risk.manager.RiskManager") as mock_risk:
        code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 0
    mock_risk.assert_not_called()


def test_cli_approve_order_path_traversal_rejected(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    code = main(["approve-order", "../../etc/passwd"])
    captured = capsys.readouterr()
    assert code == 2
    assert "Invalid pending order id" in captured.out
    assert "passwd" not in captured.out
    assert "passwd" not in captured.err


def test_cli_approve_order_does_not_leak_fake_private_values(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    # Tamper with a fake secret value
    path = manager.path_for(order.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["order"]["symbol"] = "FAKE_API_KEY_12345"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["approve-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    # Leaked tampered values must not appear in output
    assert "FAKE_API_KEY_12345" not in captured.out
    assert "FAKE_API_KEY_12345" not in captured.err


def test_atlas_backtest_works(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr() # Clear init output

    assert main(["backtest", "run", "--symbol", "DEMO-SYMBOL", "--data", "data/sample/ohlcv.csv"]) == 0
    assert "backtest result: filled" in capsys.readouterr().out


def test_atlas_run_once_paper_works(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.ai.discipline import write_user_discipline

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr() # Clear init output

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

    assert main(["run-once", "--mode", "paper", "--symbol", "DEMO-SYMBOL"]) == 0
    assert "paper result: filled" in capsys.readouterr().out


def test_atlas_run_once_live_fails_safely_by_default(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    from atlas_agent.ai.discipline import write_user_discipline

    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("LIVE_BROKER", raising=False)
    monkeypatch.chdir(tmp_path)

    main(["init", "."])

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

    assert main(["run-once", "--mode", "live", "--symbol", "DEMO-SYMBOL"]) == 2
    output = capsys.readouterr().out
    assert "live result: rejected" in output
    assert "live trading disabled" in output.lower() or "live trading is not enabled" in output.lower()


def test_atlas_setup_guided_with_mocked_wizard(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    def _fake_wizard(state):
        state.provider = "openai"
        state.model = "gpt-5.5"
        state.credentials_configured = True
        return True

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), patch(
        "atlas_agent.setup.wizard.run_wizard", side_effect=_fake_wizard
    ), patch("builtins.input", side_effect=["1", "AAPL"]):
        code = main(["setup"])

    assert code == 0
    output = capsys.readouterr().out
    assert "Setup readiness summary" in output
    assert "DEMO-SYMBOL" not in output

    config = get_config()
    assert config.model.provider == "openai"
    assert config.model.model == "gpt-5.5"
    assert config.market.symbol == "AAPL"
    assert config.trading_mode == "paper"
    assert config.enable_live_trading is False
    assert (tmp_path / ".atlas" / "discipline.md").exists()
    assert not list((tmp_path / ".atlas" / "backtests").rglob("*.json"))


def test_atlas_setup_secret_hygiene_with_mocked_wizard(tmp_path, monkeypatch, capsys):
    from atlas_agent.config import set_secret

    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    def _fake_wizard(state):
        state.provider = "openrouter"
        state.model = "openai/gpt-5.5"
        state.credentials_configured = True
        set_secret("OPENROUTER_API_KEY", "sk-or-setup-test")
        return True

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), patch(
        "atlas_agent.setup.wizard.run_wizard", side_effect=_fake_wizard
    ), patch("builtins.input", side_effect=["1", "AAPL"]):
        code = main(["setup"])

    assert code == 0
    output = capsys.readouterr().out
    assert "sk-or-setup-test" not in output

    config_toml = (tmp_path / ".atlas" / "config.toml").read_text(encoding="utf-8")
    assert "sk-or-setup-test" not in config_toml

    env_atlas = (tmp_path / ".env.atlas").read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=sk-or-setup-test" in env_atlas


def test_atlas_setup_cancelled_returns_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), patch(
        "atlas_agent.setup.wizard.run_wizard", return_value=False
    ):
        code = main(["setup"])

    assert code == 2
    assert "Setup cancelled." in capsys.readouterr().out


def test_atlas_setup_discipline_requires_confirmation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    def _fake_wizard(state):
        state.provider = "openai"
        state.model = "gpt-5.5"
        state.credentials_configured = True
        return True

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=True), patch(
        "atlas_agent.setup.wizard.run_wizard", side_effect=_fake_wizard
    ), patch("builtins.input", side_effect=["3"]):
        code = main(["setup"])

    assert code == 2
    assert not (tmp_path / ".atlas" / "discipline.md").exists()


def test_atlas_setup_noninteractive_fails_closed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", "--template", "routine-trader"]) == 0
    capsys.readouterr()

    with patch("atlas_agent.setup.wizard.is_interactive", return_value=False):
        code = main(["setup"])

    assert code == 2
    assert "requires an interactive terminal" in capsys.readouterr().out.lower()
