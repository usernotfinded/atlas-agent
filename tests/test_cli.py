from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import atlas_agent
import pytest
from atlas_agent.cli import main
from atlas_agent.config import get_config
from atlas_agent.execution.order import Order


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


# ---------------------------------------------------------------------------
# submit-approved-order --dry-run
# ---------------------------------------------------------------------------

def _mock_dry_run_services():
    """Return a context-manager factory that patches all external dry-run services."""
    from unittest.mock import patch

    def _make_sync_result():
        from atlas_agent.risk.models import PortfolioSnapshot
        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        return mock_result

    def _make_risk_decision(allowed: bool = True):
        from atlas_agent.risk.models import RiskDecision
        return RiskDecision(
            allowed=allowed,
            status="requires_approval" if allowed else "blocked",
            reason="All risk checks passed" if allowed else "Risk violations detected",
            violations=[],
            classification="opens_new_position",
        )

    def _make_broker_status(can_sync: bool = True, can_submit: bool = False):
        mock = MagicMock()
        mock.can_sync = can_sync
        mock.can_submit = can_submit
        mock.broker_id = "alpaca"
        mock.to_dict.return_value = {"can_sync": can_sync, "can_submit": can_submit}
        return mock

    def _make_broker_resolution():
        mock = MagicMock()
        mock.sync_provider = MagicMock()
        return mock

    def _make_sync_service():
        from atlas_agent.risk.models import PortfolioSnapshot
        mock_service = MagicMock()
        mock_service.sync.return_value = _make_sync_result()
        mock_service.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )
        return mock_service

    def _make_risk_manager(allowed: bool = True):
        mock = MagicMock()
        mock.evaluate_order.return_value = _make_risk_decision(allowed)
        return mock

    class _Patcher:
        def __init__(self, can_sync=True, can_submit=False, sync_error=None, sync_warnings=None, risk_allowed=True):
            self.can_sync = can_sync
            self.can_submit = can_submit
            self.sync_error = sync_error
            self.sync_warnings = sync_warnings or []
            self.risk_allowed = risk_allowed

        def __enter__(self):
            from contextlib import ExitStack
            self.stack = ExitStack()
            mr = self.stack.enter_context(patch("atlas_agent.execution.submit_dry_run.BrokerResolver"))
            ms = self.stack.enter_context(patch("atlas_agent.execution.submit_dry_run.BrokerSyncService"))
            mv = self.stack.enter_context(patch("atlas_agent.execution.submit_dry_run.validate_live_sync"))
            mri = self.stack.enter_context(patch("atlas_agent.execution.submit_dry_run.RiskManager"))
            mr.return_value.resolve_status.return_value = _make_broker_status(self.can_sync, self.can_submit)
            mr.return_value.resolve_sync_provider.return_value = _make_broker_resolution()
            ms.return_value = _make_sync_service()
            mv.return_value = (self.sync_warnings, self.sync_error)
            mri.return_value = _make_risk_manager(self.risk_allowed)
            return self

        def __exit__(self, *args):
            self.stack.close()
            return False

    return _Patcher


def test_submit_approved_order_without_flags_pending_not_found(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    code = main(["submit-approved-order", "some-id"])
    captured = capsys.readouterr()
    assert code == 2
    assert "pending_order_not_found" in captured.out


def _enable_live_trading_in_workspace(tmp_path: Path) -> None:
    """Write broker config to workspace .atlas/config.toml for dry-run tests."""
    config_toml = tmp_path / ".atlas" / "config.toml"
    config_toml.write_text('[broker]\nenable_live_trading = true\nprovider = "alpaca"\n', encoding="utf-8")


def test_submit_approved_order_dry_run_valid_approved(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with _mock_dry_run_services()(can_sync=True, can_submit=False, risk_allowed=True):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 0
    assert "dry_run_ready" in captured.out or "Dry-run passed" in captured.out


def test_submit_approved_order_dry_run_json_output(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with _mock_dry_run_services()(can_sync=True, can_submit=False, risk_allowed=True):
        code = main(["submit-approved-order", order.id, "--dry-run", "--json"])

    captured = capsys.readouterr()
    assert code == 0
    output = json.loads(captured.out)
    assert output["ok"] is True
    assert "data" in output
    assert output["data"]["status"] == "dry_run_ready"


def test_submit_approved_order_dry_run_does_not_call_broker_place_order(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.cli._broker_for_mode") as mock_broker, \
         _mock_dry_run_services()(can_sync=True, can_submit=False, risk_allowed=True):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    mock_broker.assert_not_called()


def test_submit_approved_order_dry_run_does_not_call_resolve_execution_broker(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_resolve, \
         _mock_dry_run_services()(can_sync=True, can_submit=False, risk_allowed=True):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    mock_resolve.assert_not_called()


def test_submit_approved_order_dry_run_does_not_instantiate_order_router(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.execution.order_router.OrderRouter") as mock_router, \
         _mock_dry_run_services()(can_sync=True, can_submit=False, risk_allowed=True):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    mock_router.assert_not_called()


def test_submit_approved_order_dry_run_does_not_create_pending_files(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    before_files = set((tmp_path / "pending_orders").iterdir())

    with _mock_dry_run_services()(can_sync=True, can_submit=False, risk_allowed=True):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    after_files = set((tmp_path / "pending_orders").iterdir())
    assert before_files == after_files


def test_submit_approved_order_dry_run_does_not_modify_pending_file(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    before = path.read_text(encoding="utf-8")

    with _mock_dry_run_services()(can_sync=True, can_submit=False, risk_allowed=True):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_submit_approved_order_dry_run_rejects_unapproved(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    with _mock_dry_run_services()():
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "not approved" in captured.out.lower()


def test_submit_approved_order_dry_run_rejects_expired(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with _mock_dry_run_services()():
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "expired" in captured.out.lower()


def test_submit_approved_order_dry_run_rejects_tampered_hash(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["order"]["quantity"] = 999.0
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with _mock_dry_run_services()():
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()


def test_submit_approved_order_dry_run_rejects_malformed_json(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    path = manager.path_for(order.id)
    path.write_text("not valid json {{{", encoding="utf-8")

    with _mock_dry_run_services()():
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()


def test_submit_approved_order_dry_run_rejects_already_submitted(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["client_order_id"] = "already-set"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with _mock_dry_run_services()():
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "client_order_id" in captured.out.lower() or "already" in captured.out.lower()


def test_submit_approved_order_dry_run_rejects_live_disabled(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    with _mock_dry_run_services()():
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "live trading" in captured.out.lower()


def test_submit_approved_order_dry_run_rejects_can_sync_false(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with _mock_dry_run_services()(can_sync=False):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "sync" in captured.out.lower()


def test_submit_approved_order_dry_run_rejects_sync_critical_error(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    sync_error = {
        "status": "error",
        "errors": ["live broker sync failed: sync_account_state"],
        "diagnostics": {"failed_operations": ["sync_account_state"]},
    }
    with _mock_dry_run_services()(sync_error=sync_error):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "sync failed" in captured.out.lower()


def test_submit_approved_order_dry_run_proceeds_with_balances_warning(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with _mock_dry_run_services()(
        sync_warnings=[{"operation": "sync_balances", "code": "broker_operation_failed", "broker": "alpaca"}],
        risk_allowed=True,
    ):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 0
    assert "dry_run_ready" in captured.out or "Dry-run passed" in captured.out


def test_submit_approved_order_dry_run_risk_rejection(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with _mock_dry_run_services()(risk_allowed=False):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "risk" in captured.out.lower() or "blocked" in captured.out.lower()


def test_submit_approved_order_dry_run_json_blocked_emits_safe_json(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)

    with _mock_dry_run_services()():
        code = main(["submit-approved-order", order.id, "--dry-run", "--json"])

    captured = capsys.readouterr()
    assert code == 2
    output = json.loads(captured.out)
    assert output["ok"] is False
    assert "error" in output
    assert "not approved" in output["error"]["message"].lower()


def test_submit_approved_order_dry_run_text_no_leak(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["order"]["symbol"] = "LEAK_SECRET_999"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with _mock_dry_run_services()():
        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "LEAK_SECRET_999" not in captured.out
    assert "LEAK_SECRET_999" not in captured.err


def test_submit_approved_order_dry_run_path_traversal_rejected(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    code = main(["submit-approved-order", "../../etc/passwd", "--dry-run"])

    captured = capsys.readouterr()
    assert code == 2
    assert "invalid" in captured.out.lower()
    assert "passwd" not in captured.out
    assert "passwd" not in captured.err


def test_submit_approved_order_dry_run_never_calls_create_pending_order(
    tmp_path, monkeypatch, capsys
) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch.object(
        ApprovalManager, "create_pending_order", side_effect=AssertionError("create_pending_order must not be called")
    ) as mock_create, _mock_dry_run_services()(
        can_sync=True, can_submit=False, risk_allowed=True
    ):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    mock_create.assert_not_called()


def test_submit_approved_order_dry_run_never_calls_approve(
    tmp_path, monkeypatch, capsys
) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch.object(
        ApprovalManager, "approve", side_effect=AssertionError("approve must not be called")
    ) as mock_approve, _mock_dry_run_services()(
        can_sync=True, can_submit=False, risk_allowed=True
    ):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    mock_approve.assert_not_called()


def test_submit_approved_order_dry_run_never_calls_order_router_route(
    tmp_path, monkeypatch, capsys
) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order_router import OrderRouter
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch.object(
        OrderRouter, "route", side_effect=AssertionError("OrderRouter.route must not be called")
    ) as mock_route, _mock_dry_run_services()(
        can_sync=True, can_submit=False, risk_allowed=True
    ):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    mock_route.assert_not_called()


def test_submit_approved_order_dry_run_never_mutates_pending_file_even_if_create_pending_order_is_patched(
    tmp_path, monkeypatch, capsys
) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0)
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    before = path.read_text(encoding="utf-8")

    with patch.object(
        ApprovalManager, "create_pending_order", side_effect=AssertionError("create_pending_order must not be called")
    ) as mock_create, _mock_dry_run_services()(
        can_sync=True, can_submit=False, risk_allowed=True
    ):
        code = main(["submit-approved-order", order.id, "--dry-run"])

    assert code == 0
    mock_create.assert_not_called()
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_broker_resolver_can_submit_remains_false() -> None:
    from atlas_agent.brokers.resolver import BrokerResolver
    from atlas_agent.config import AtlasConfig

    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
    )
    resolver = BrokerResolver(config)
    status = resolver.resolve_status("live")
    assert status.can_submit is False


def test_resolve_execution_broker_live_returns_none() -> None:
    from atlas_agent.brokers.resolver import BrokerResolver
    from atlas_agent.config import AtlasConfig

    config = AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
    )
    resolver = BrokerResolver(config)
    resolution = resolver.resolve_execution_broker("live")
    assert resolution.execution_broker is None


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


# ---------------------------------------------------------------------------
# Batch 4.4 CLI reconcile tests
# ---------------------------------------------------------------------------

def test_submit_approved_order_reconcile_flag_parses() -> None:
    from atlas_agent.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["submit-approved-order", "abc123", "--reconcile"])
    assert args.reconcile is True
    assert args.dry_run is False


def test_submit_approved_order_reconcile_and_dry_run_mutual_exclusion(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    code = main(["submit-approved-order", "test-order", "--dry-run", "--reconcile"])
    captured = capsys.readouterr()
    assert code == 2
    assert "mutually exclusive" in captured.out.lower()


def test_submit_without_dry_run_or_reconcile_still_blocked(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    code = main(["submit-approved-order", "test-order"])
    captured = capsys.readouterr()
    assert code == 2
    assert "pending_order_not_found" in captured.out


def test_cli_submit_approved_order_still_blocks_at_can_submit_false(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    before = path.read_text(encoding="utf-8")

    mock_status = MagicMock()
    mock_status.can_sync = True
    mock_status.can_submit = False
    mock_status.broker_id = "alpaca"

    mock_resolution = MagicMock()
    mock_resolution.sync_provider = MagicMock()

    mock_sync_result = MagicMock()
    mock_sync_result.status = "success"
    mock_sync_result.account = MagicMock()
    mock_sync_result.positions = []
    mock_sync_result.open_orders = []
    mock_sync_result.balances = []
    mock_sync_result.errors = []
    mock_sync_result.diagnostics = {"broker_errors": []}

    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = mock_sync_result
    from atlas_agent.risk.models import PortfolioSnapshot
    mock_sync_service.get_portfolio_snapshot.return_value = PortfolioSnapshot(
        cash=10000, equity=10000, total_exposure=0
    )

    mock_risk_decision = MagicMock()
    mock_risk_decision.allowed = True
    mock_risk_decision.status = "allowed"
    mock_risk_decision.reason = "All risk checks passed"
    mock_risk_decision.violations = []
    mock_risk_decision.classification = "opens_new_position"

    mock_risk_manager = MagicMock()
    mock_risk_manager.evaluate_order.return_value = mock_risk_decision

    mock_ks = MagicMock()
    mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mock_resolver_cls, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as mock_sync_cls, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mock_validate, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mock_risk_cls, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_resolver_cls.return_value.resolve_status.return_value = mock_status
        mock_resolver_cls.return_value.resolve_sync_provider.return_value = mock_resolution
        mock_sync_cls.return_value = mock_sync_service
        mock_validate.return_value = ([], None)
        mock_risk_cls.return_value = mock_risk_manager
        mock_ks_cls.return_value = mock_ks

        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 2
    assert "can_submit_false" in captured.out or "submit remains disabled" in captured.out.lower()
    after = path.read_text(encoding="utf-8")
    assert before == after


# ---------------------------------------------------------------------------
# Batch 4.4.1 CLI reconcile coverage
# ---------------------------------------------------------------------------

def _make_order(**kwargs):
    from atlas_agent.execution.order import Order
    defaults = {
        "symbol": "TEST",
        "side": "buy",
        "quantity": 1.0,
        "limit_price": 100.0,
        "confidence": 1.0,
        "stop_loss": 95.0,
    }
    defaults.update(kwargs)
    return Order(**defaults)


def _write_v2_pending_with_cid(tmp_path: Path, order_id: str, cid: str, status: str = "approved", broker_order_id: str | None = None):
    from atlas_agent.execution.approval import ApprovalManager, _compute_order_hash, _order_to_dict
    from datetime import UTC, datetime, timedelta
    import json

    order = _make_order(id=order_id)
    manager = ApprovalManager(tmp_path / "pending_orders")
    path = manager.path_for(order.id)
    order_dict = _order_to_dict(order)
    now = datetime.now(UTC)
    payload = {
        "schema_version": "2",
        "order": order_dict,
        "approved": True,
        "created_at": now.isoformat(),
        "approved_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
        "approval_actor": "test",
        "order_hash": _compute_order_hash(order_dict),
        "status": status,
        "status_transitions": [
            {"status": "pending_approval", "at": now.isoformat(), "actor": "system"},
            {"status": status, "at": now.isoformat(), "actor": "test"},
        ],
        "submit_attempts": [],
        "broker_order_id": broker_order_id,
        "client_order_id": cid,
        "fill_quantity": 0.0,
        "fill_price": None,
        "submitted_at": None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return manager, path


def _configured_atlas_config(tmp_path: Path):
    from atlas_agent.config import AtlasConfig
    return AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
        workspace_root=tmp_path,
        pending_orders_dir=tmp_path / "pending_orders",
    )


def test_cli_submit_approved_order_reconcile_success_text(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
    from atlas_agent.brokers.models import BrokerOrder
    from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    _write_v2_pending_with_cid(tmp_path, "reconcile-ok", "atlas-ok-deadbeef")

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = BrokerOrder(
        order_id="broker-111",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="filled",
    )

    from atlas_agent.config import AtlasConfig
    config = _configured_atlas_config(tmp_path)
    with patch.object(AtlasConfig, "from_env", return_value=config), \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=BrokerResolution(
             execution_broker=None,
             sync_provider=mock_adapter,
             status=MagicMock(),
         )):
        code = main(["submit-approved-order", "reconcile-ok", "--reconcile"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Reconcile Report" in captured.out
    assert "Broker order" in captured.out
    assert "No duplicate submit" in captured.out or "reconciled" in captured.out.lower()


def test_cli_submit_approved_order_reconcile_success_json(tmp_path, monkeypatch, capsys) -> None:
    import json
    from atlas_agent.cli import main
    from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
    from atlas_agent.brokers.models import BrokerOrder
    from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
    from atlas_agent.config import AtlasConfig
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    _write_v2_pending_with_cid(tmp_path, "reconcile-json", "atlas-json-deadbeef")

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = BrokerOrder(
        order_id="broker-222",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="open",
    )

    config = _configured_atlas_config(tmp_path)
    with patch.object(AtlasConfig, "from_env", return_value=config), \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=BrokerResolution(
             execution_broker=None,
             sync_provider=mock_adapter,
             status=MagicMock(),
         )):
        code = main(["submit-approved-order", "reconcile-json", "--reconcile", "--json"])

    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    data = payload["data"]
    assert data["status"] == "duplicate_reconciled"
    assert data["broker_order_id"] == "broker-222"


def test_cli_submit_approved_order_reconcile_not_found_sanitized(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
    from atlas_agent.brokers.base import BrokerOperationError
    from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
    from atlas_agent.config import AtlasConfig
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    _write_v2_pending_with_cid(tmp_path, "reconcile-notfound", "atlas-notfound-deadbeef")

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = BrokerOperationError("order not found")

    config = _configured_atlas_config(tmp_path)
    with patch.object(AtlasConfig, "from_env", return_value=config), \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=BrokerResolution(
             execution_broker=None,
             sync_provider=mock_adapter,
             status=MagicMock(),
         )):
        code = main(["submit-approved-order", "reconcile-notfound", "--reconcile"])

    captured = capsys.readouterr()
    assert code == 2
    assert "No broker order found" in captured.out
    # Sanitized: no raw fake secrets or payload values
    assert "atlas-notfound-deadbeef" not in captured.out
    assert "atlas-notfound-deadbeef" not in captured.err


def test_cli_submit_approved_order_reconcile_invalid_file_sanitized(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.config import AtlasConfig
    from unittest.mock import patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    # Write a corrupted pending order file
    pending_dir = tmp_path / "pending_orders"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "reconcile-bad.json").write_text("not valid json {{{", encoding="utf-8")

    config = _configured_atlas_config(tmp_path)
    with patch.object(AtlasConfig, "from_env", return_value=config):
        code = main(["submit-approved-order", "reconcile-bad", "--reconcile"])

    captured = capsys.readouterr()
    assert code == 2
    assert "invalid or corrupted" in captured.out.lower()
    # No raw payload leak
    assert "not valid json" not in captured.out
    assert "not valid json" not in captured.err


def test_cli_submit_approved_order_reconcile_duplicate_reconciled_no_broker_query(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
    from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
    from atlas_agent.config import AtlasConfig
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    _write_v2_pending_with_cid(
        tmp_path,
        "reconcile-dup",
        "atlas-dup-deadbeef",
        status="duplicate_reconciled",
        broker_order_id="broker-333",
    )

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.side_effect = AssertionError("must not be called")

    config = _configured_atlas_config(tmp_path)
    with patch.object(AtlasConfig, "from_env", return_value=config), \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=BrokerResolution(
             execution_broker=None,
             sync_provider=mock_adapter,
             status=MagicMock(),
         )):
        code = main(["submit-approved-order", "reconcile-dup", "--reconcile"])

    captured = capsys.readouterr()
    assert code == 0
    assert "already reconciled" in captured.out.lower()
    mock_adapter.get_order_by_client_order_id.assert_not_called()


# ---------------------------------------------------------------------------
# submit-approved-order execution skeleton (no flags)
# ---------------------------------------------------------------------------


def test_submit_approved_order_execution_live_trading_disabled(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    # live trading not enabled in config
    code = main(["submit-approved-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "live_trading_disabled" in captured.out


def test_submit_approved_order_execution_kill_switch_active(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.execution.submit_execution.KillSwitchController") as mock_ks_cls:
        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=True, mode="soft_pause")
        mock_ks_cls.return_value = mock_ks
        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 2
    assert "kill_switch_active" in captured.out


def test_submit_approved_order_execution_invalid_order_id(capsys) -> None:
    code = main(["submit-approved-order", "../../etc/passwd"])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid pending order id" in captured.out.lower()
    assert "../../etc/passwd" not in captured.out
    assert "etc/passwd" not in captured.out


def test_submit_approved_order_execution_invalid_order_id_json(capsys) -> None:
    code = main(["submit-approved-order", "../../etc/passwd", "--json"])
    captured = capsys.readouterr()
    assert code == 2
    output = json.loads(captured.out)
    assert output["ok"] is False
    assert output["error"]["code"] == "submit_blocked"
    assert output["error"]["details"]["blocked_reason"] == "invalid_pending_order_id"
    assert "../../etc/passwd" not in captured.out
    assert "etc/passwd" not in captured.out


def test_submit_approved_order_execution_fake_secret_not_leaked(capsys) -> None:
    # Path-traversal + fake secret combination triggers InvalidApprovalIdError
    code = main(["submit-approved-order", "../../etc/FAKE_API_KEY_12345"])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid pending order id" in captured.out.lower()
    assert "FAKE_API_KEY_12345" not in captured.out
    assert "FAKE_API_KEY" not in captured.out
    assert "etc/passwd" not in captured.out


def test_submit_approved_order_execution_tampered_file_no_secret_leak(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.submit_state import _compute_order_hash

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    # Tamper the file by injecting a fake secret into the payload
    path = manager.path_for(order.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["order_hash"] = "tampered"
    payload["order"]["symbol"] = "SECRET_SYMBOL_999"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    code = main(["submit-approved-order", order.id])
    captured = capsys.readouterr()
    assert code == 2
    assert "invalid_pending_order" in captured.out.lower()
    assert "SECRET_SYMBOL_999" not in captured.out
    assert "tampered" not in captured.out


def test_submit_approved_order_execution_json_output(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = False
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": False}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id, "--json"])

    captured = capsys.readouterr()
    assert code == 2
    output = json.loads(captured.out)
    assert output["ok"] is False
    assert output["error"]["code"] == "submit_blocked"
    assert output["error"]["details"]["blocked_reason"] == "can_submit_false"
    assert output["error"]["details"]["gates"]["can_submit"] == "fail"


def test_submit_approved_order_execution_can_submit_false(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = False
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": False}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 2
    assert "can_submit_false" in captured.out
    assert "All safety gates passed" in captured.out


def test_submit_approved_order_execution_no_place_order_called(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.brokers.alpaca import AlpacaBroker

    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks, \
         patch.object(AlpacaBroker, "place_order", side_effect=AssertionError("place_order must not be called")) as mock_place:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = False
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": False}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 2
    assert "can_submit_false" in captured.out
    mock_place.assert_not_called()


# ---------------------------------------------------------------------------
# Batch 4.7: CLI Pre-Submit Mutation Wiring Behind Hard-Disabled Gate
# ---------------------------------------------------------------------------

def test_cli_default_can_submit_false_no_mutation(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = False
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": False}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 2
    assert "can_submit_false" in captured.out
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_cli_mocked_can_submit_true_mutates_to_submit_requested(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = True
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": True}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 2
    assert "execution_broker_unavailable" in captured.out
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["status"] == "submit_prepare_failed"
    assert loaded["client_order_id"] is not None
    assert loaded.get("submitted_at") is None
    assert loaded.get("broker_order_id") is None


def test_cli_mocked_can_submit_true_text_output_sanitized(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = True
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": True}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 2
    assert "Execution broker is not available." in captured.out
    # No raw API keys or secrets
    assert "ALPACA" not in captured.out or "alpaca" in captured.out.lower()  # "alpaca" is safe broker name
    assert "SECRET" not in captured.out
    assert "API_KEY" not in captured.out


def test_cli_mocked_can_submit_true_json_output_parseable(tmp_path, monkeypatch, capsys) -> None:
    import json
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = True
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": True}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id, "--json"])

    captured = capsys.readouterr()
    assert code == 2
    output = json.loads(captured.out)
    assert output["ok"] is False
    assert output["error"]["code"] == "submit_blocked"
    assert output["error"]["details"]["blocked_reason"] == "execution_broker_unavailable"
    assert output["error"]["details"]["gates"]["can_submit"] == "pass"
    assert output["error"]["details"]["gates"]["execution_broker"] == "unavailable"


def test_cli_dry_run_unchanged(tmp_path, monkeypatch, capsys) -> None:
    import json
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_dry_run.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_dry_run.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_dry_run.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_dry_run.RiskManager") as mri:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = False
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": False}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        code = main(["submit-approved-order", order.id, "--dry-run"])

    captured = capsys.readouterr()
    assert code == 0
    assert "Dry-run passed" in captured.out
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_cli_reconcile_unchanged(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
    from atlas_agent.brokers.models import BrokerOrder
    from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
    from atlas_agent.config import AtlasConfig
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()

    _write_v2_pending_with_cid(tmp_path, "reconcile-unchanged-47", "atlas-recon-47-deadbeef")

    mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
    mock_adapter.get_order_by_client_order_id.return_value = BrokerOrder(
        order_id="broker-47",
        symbol="TEST",
        side="buy",
        quantity=1.0,
        status="filled",
    )

    config = _configured_atlas_config(tmp_path)
    with patch.object(AtlasConfig, "from_env", return_value=config), \
         patch.object(BrokerResolver, "resolve_sync_provider", return_value=BrokerResolution(
             execution_broker=None,
             sync_provider=mock_adapter,
             status=MagicMock(),
         )):
        code = main(["submit-approved-order", "reconcile-unchanged-47", "--reconcile"])

    captured = capsys.readouterr()
    assert code == 0
    assert "duplicate_reconciled" in captured.out.lower() or "reconciled" in captured.out.lower()


# ---------------------------------------------------------------------------
# Batch 4.9: CLI broker submit boundary tests
# ---------------------------------------------------------------------------

def test_cli_production_can_submit_false_still_blocks(tmp_path, monkeypatch, capsys) -> None:
    import json
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)
    path = manager.path_for(order.id)
    before = path.read_text(encoding="utf-8")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = False
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": False}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=None)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id, "--json"])

    captured = capsys.readouterr()
    assert code == 2
    output = json.loads(captured.out)
    assert output["ok"] is False
    assert output["error"]["details"]["blocked_reason"] == "can_submit_false"
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_cli_mocked_can_submit_true_accepted_prints_acknowledged(tmp_path, monkeypatch, capsys) -> None:
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order, OrderResult
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    mock_broker = MagicMock()
    mock_broker.place_order.return_value = OrderResult(
        accepted=True, filled=False, order_id="broker-123", status="new", message="ok"
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = True
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": True}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=mock_broker)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 0
    assert "acknowledged" in captured.out.lower()


def test_cli_mocked_can_submit_true_accepted_json(tmp_path, monkeypatch, capsys) -> None:
    import json
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order, OrderResult
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    mock_broker = MagicMock()
    mock_broker.place_order.return_value = OrderResult(
        accepted=True, filled=False, order_id="broker-123", status="new", message="ok"
    )

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = True
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": True}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=mock_broker)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id, "--json"])

    captured = capsys.readouterr()
    assert code == 0
    output = json.loads(captured.out)
    assert output["ok"] is True
    assert output["data"]["status"] == "acknowledged"


def test_cli_mocked_rejected_returns_failed_safely(tmp_path, monkeypatch, capsys) -> None:
    import json
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order, OrderResult
    from atlas_agent.brokers.base import BrokerOperationError
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    mock_broker = MagicMock()
    mock_broker.place_order.side_effect = BrokerOperationError("broker rejected order")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = True
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": True}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=mock_broker)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id, "--json"])

    captured = capsys.readouterr()
    assert code == 2
    output = json.loads(captured.out)
    assert output["ok"] is False
    assert output["error"]["details"]["blocked_reason"] == "broker_rejected_order"
    assert "broker rejected order." in output["error"]["message"].lower()


def test_cli_mocked_uncertain_returns_reconcile_message(tmp_path, monkeypatch, capsys) -> None:
    import json
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from atlas_agent.brokers.base import BrokerOperationError
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    mock_broker = MagicMock()
    mock_broker.place_order.side_effect = BrokerOperationError("broker unavailable")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = True
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": True}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=mock_broker)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id])

    captured = capsys.readouterr()
    assert code == 2
    assert "--reconcile" in captured.out
    assert "uncertain" in captured.out.lower()


def test_cli_no_raw_secret_path_payload_broker_error_in_output(tmp_path, monkeypatch, capsys) -> None:
    import json
    from atlas_agent.cli import main
    from atlas_agent.execution.approval import ApprovalManager
    from atlas_agent.execution.order import Order
    from atlas_agent.brokers.base import BrokerOperationError
    from unittest.mock import MagicMock, patch

    monkeypatch.chdir(tmp_path)
    main(["init", "."])
    capsys.readouterr()
    _enable_live_trading_in_workspace(tmp_path)

    order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
    manager = ApprovalManager(tmp_path / "pending_orders")
    manager.create_pending_order(order)
    manager.approve(order.id)

    mock_broker = MagicMock()
    mock_broker.place_order.side_effect = BrokerOperationError("broker unavailable")

    with patch("atlas_agent.execution.submit_execution.BrokerResolver") as mr, \
         patch("atlas_agent.execution.submit_execution.BrokerSyncService") as ms, \
         patch("atlas_agent.execution.submit_execution.validate_live_sync") as mv, \
         patch("atlas_agent.execution.submit_execution.RiskManager") as mri, \
         patch("atlas_agent.execution.submit_execution.KillSwitchController") as mks:
        mock_status = MagicMock()
        mock_status.can_sync = True
        mock_status.can_submit = True
        mock_status.broker_id = "alpaca"
        mock_status.to_dict.return_value = {"can_sync": True, "can_submit": True}
        mr.return_value.resolve_status.return_value = mock_status
        mr.return_value.resolve_sync_provider.return_value = MagicMock(sync_provider=MagicMock())
        mr.return_value.resolve_execution_broker.return_value = MagicMock(execution_broker=mock_broker)

        mock_result = MagicMock()
        mock_result.status = "success"
        mock_result.account = MagicMock()
        mock_result.positions = []
        mock_result.open_orders = []
        mock_result.balances = []
        mock_result.errors = []
        mock_result.diagnostics = {"broker_errors": []}
        ms.return_value.sync.return_value = mock_result
        from atlas_agent.risk.models import PortfolioSnapshot
        ms.return_value.get_portfolio_snapshot.return_value = PortfolioSnapshot(
            cash=10000, equity=10000, total_exposure=0
        )

        mv.return_value = ([], None)

        from atlas_agent.risk.models import RiskDecision
        mri.return_value.evaluate_order.return_value = RiskDecision(
            allowed=True,
            status="allowed",
            reason="All risk checks passed",
            violations=[],
            classification="opens_new_position",
        )

        mock_ks = MagicMock()
        mock_ks.status.return_value = MagicMock(enabled=False, mode="normal")
        mks.return_value = mock_ks

        code = main(["submit-approved-order", order.id, "--json"])

    captured = capsys.readouterr()
    assert code == 2
    combined = captured.out + captured.err
    assert "SECRET" not in combined
    assert "API_KEY" not in combined
    assert "password" not in combined.lower()
    assert "FAKE_BROKER_BODY" not in combined
    # No raw broker error text
    assert "broker unavailable" not in combined.lower()
