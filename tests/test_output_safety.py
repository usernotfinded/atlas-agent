"""Output/audit safety regression tests for Atlas Agent.

These tests verify that safety-critical user-facing output and audit payloads
never leak raw exception text, paths, secrets, headers, broker bodies, or raw
pending order payloads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

FORBIDDEN_OUTPUT_FRAGMENTS = [
    "/Users/",
    "/private/var/",
    "LEAKED_SECRET_TOKEN",
    "Authorization:",
    "Bearer abc123",
    "APCA-API-KEY",
    "APCA-API-SECRET",
    "FAKE_API_KEY",
    "LEAKED_PASSWORD",
    "SECRET_TOKEN",
    "broker.example.com",
    "../../",
    "ACCT_SECRET",
    '"secret"',
]


def assert_no_forbidden_output(value: object) -> None:
    text = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in text, (
            f"Forbidden output fragment found: {fragment!r} in {text[:500]}"
        )


def _configured_atlas_config(tmp_path: Path):
    from atlas_agent.config import AtlasConfig
    return AtlasConfig(
        trading_mode="live",
        broker={"provider": "alpaca", "enable_live_trading": True},
        workspace_root=tmp_path,
        pending_orders_dir=tmp_path / "pending_orders",
    )


def _enable_live_trading_in_workspace(tmp_path: Path) -> None:
    """Write broker config to workspace .atlas/config.toml."""
    config_toml = tmp_path / ".atlas" / "config.toml"
    config_toml.parent.mkdir(parents=True, exist_ok=True)
    config_toml.write_text(
        '[broker]\nenable_live_trading = true\nprovider = "alpaca"\n',
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# A. Generic output sanitizer tests
# ---------------------------------------------------------------------------

class TestGenericOutputSanitizer:
    def test_make_safe_runtime_error_never_leaks_raw_exception_text(self) -> None:
        from atlas_agent.runtime_errors import make_safe_runtime_error

        exc = ValueError("/Users/natan/.config/alpaca/secret.json LEAKED_SECRET_TOKEN")
        safe = make_safe_runtime_error(operation="test", exc=exc)
        assert safe.message == "input validation failed"
        assert safe.code == "validation_error"
        assert "LEAKED_SECRET_TOKEN" not in safe.message
        assert "/Users/" not in safe.message

    def test_make_safe_runtime_error_oserror_is_safe(self) -> None:
        from atlas_agent.runtime_errors import make_safe_runtime_error

        exc = OSError("/private/var/folders/secret/path")
        safe = make_safe_runtime_error(operation="test", exc=exc)
        assert safe.message == "transport request failed"
        assert "/private/var/" not in safe.message

    def test_safe_runtime_error_to_dict_no_raw_values(self) -> None:
        from atlas_agent.runtime_errors import SafeRuntimeError

        safe = SafeRuntimeError(code="test_code", operation="test_op", message="safe message")
        d = safe.to_dict()
        assert d == {"code": "test_code", "operation": "test_op", "message": "safe message"}
        assert_no_forbidden_output(d)

    def test_cli_redact_sensitive_text_strips_bearer(self) -> None:
        from atlas_agent.cli import _redact_sensitive_text

        text = "Authorization: Bearer abc123 and some other text"
        redacted = _redact_sensitive_text(text)
        assert "Bearer abc123" not in redacted
        assert "[REDACTED]" in redacted

    def test_cli_redact_sensitive_text_strips_secret_assignment(self) -> None:
        from atlas_agent.cli import _redact_sensitive_text

        text = "API_KEY=FAKE_API_KEY_123 SECRET_TOKEN=LEAKED_PASSWORD_999"
        redacted = _redact_sensitive_text(text)
        assert "FAKE_API_KEY_123" not in redacted
        assert "LEAKED_PASSWORD_999" not in redacted
        assert "[REDACTED]" in redacted


# ---------------------------------------------------------------------------
# B. CLI JSON/text error-envelope safety
# ---------------------------------------------------------------------------

class TestCliErrorEnvelopeSafety:
    def test_config_error_text_does_not_leak_raw_exception(self, tmp_path, monkeypatch, capsys) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from atlas_agent.config.errors import AtlasConfigError
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = AtlasConfigError("/Users/natan/.config/alpaca/secret.json LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.config.get_config", side_effect=unsafe_exc):
            code = main(["config", "show", "--effective"])

        captured = capsys.readouterr()
        assert code != 0
        assert_no_forbidden_output(captured.out)
        assert_no_forbidden_output(captured.err)
        # Must be a static/bounded message, not raw exception
        assert "Configuration error" in captured.err or "Configuration check failed" in captured.err

    def test_config_check_json_does_not_leak_raw_exception(self, tmp_path, monkeypatch, capsys) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from atlas_agent.config.errors import AtlasConfigError
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = AtlasConfigError("/Users/natan/.config/alpaca/secret.json LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.config.get_config", side_effect=unsafe_exc):
            code = main(["config", "check", "--json"])

        captured = capsys.readouterr()
        assert code != 0
        output = captured.out
        # Must be valid JSON
        payload = json.loads(output)
        assert payload["ok"] is False
        assert_no_forbidden_output(payload)
        assert "error" in payload
        assert "config_load_failed" in payload["error"]["code"] or "config_check_failed" in payload["error"]["code"]

    def test_validate_json_with_unsafe_exception_is_sanitized(self, tmp_path, monkeypatch, capsys) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = RuntimeError("/Users/natan/secret/path LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.diagnostics.readiness.run_diagnostics", side_effect=unsafe_exc):
            code = main(["validate", "--json"])

        captured = capsys.readouterr()
        assert code != 0
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert_no_forbidden_output(payload)
        assert payload["error"]["code"] == "validate_failed"

    def test_submit_reconcile_json_with_unsafe_exception_is_sanitized(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = OSError("/Users/natan/secret/path LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.execution.submit_reconcile.run_reconcile", side_effect=unsafe_exc):
            code = main(["submit-approved-order", "some-id", "--reconcile", "--json"])

        captured = capsys.readouterr()
        assert code != 0
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert_no_forbidden_output(payload)

    def test_submit_dry_run_json_with_unsafe_exception_is_sanitized(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = RuntimeError("/Users/natan/secret/path LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.execution.submit_dry_run.run_submit_dry_run", side_effect=unsafe_exc):
            code = main(["submit-approved-order", "some-id", "--dry-run", "--json"])

        captured = capsys.readouterr()
        assert code != 0
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert_no_forbidden_output(payload)

    def test_submit_execution_json_with_unsafe_exception_is_sanitized(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = RuntimeError("/Users/natan/secret/path LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.execution.submit_execution.run_submit_execution", side_effect=unsafe_exc):
            code = main(["submit-approved-order", "some-id", "--json"])

        captured = capsys.readouterr()
        assert code != 0
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert_no_forbidden_output(payload)

    def test_submit_reconcile_text_with_unsafe_exception_is_sanitized(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = OSError("/Users/natan/secret/path LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.execution.submit_reconcile.run_reconcile", side_effect=unsafe_exc):
            code = main(["submit-approved-order", "some-id", "--reconcile"])

        captured = capsys.readouterr()
        assert code != 0
        assert_no_forbidden_output(captured.out)
        assert_no_forbidden_output(captured.err)
        assert "traceback" not in captured.err.lower()
        assert "traceback" not in captured.out.lower()

    def test_submit_dry_run_text_with_unsafe_exception_is_sanitized(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = RuntimeError("/Users/natan/secret/path LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.execution.submit_dry_run.run_submit_dry_run", side_effect=unsafe_exc):
            code = main(["submit-approved-order", "some-id", "--dry-run"])

        captured = capsys.readouterr()
        assert code != 0
        assert_no_forbidden_output(captured.out)
        assert_no_forbidden_output(captured.err)

    def test_submit_execution_text_with_unsafe_exception_is_sanitized(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        config = _configured_atlas_config(tmp_path)
        unsafe_exc = RuntimeError("/Users/natan/secret/path LEAKED_SECRET_TOKEN")

        with patch.object(AtlasConfig, "from_env", return_value=config), \
             patch("atlas_agent.execution.submit_execution.run_submit_execution", side_effect=unsafe_exc):
            code = main(["submit-approved-order", "some-id"])

        captured = capsys.readouterr()
        assert code != 0
        assert_no_forbidden_output(captured.out)
        assert_no_forbidden_output(captured.err)


# ---------------------------------------------------------------------------
# C. Submit execution report safety — broker body/header injection
# ---------------------------------------------------------------------------

class TestSubmitExecutionBrokerBodySafety:
    def test_submit_execution_report_dict_no_forbidden_fragments(self, tmp_path) -> None:
        """Directly test run_submit_execution with unsafe broker error."""
        from atlas_agent.execution.approval import ApprovalManager
        from atlas_agent.execution.order import Order
        from atlas_agent.execution.submit_execution import run_submit_execution
        from atlas_agent.brokers.base import BrokerOperationError
        from atlas_agent.config import AtlasConfig
        from unittest.mock import MagicMock, patch

        _enable_live_trading_in_workspace(tmp_path)

        order = Order(symbol="AAPL", side="buy", quantity=1.0, limit_price=100.0, order_type="limit")
        manager = ApprovalManager(tmp_path / "pending_orders")
        manager.create_pending_order(order)
        manager.approve(order.id)

        mock_broker = MagicMock()
        unsafe_msg = (
            "https://broker.example.com/orders/raw-body "
            "Authorization: Bearer abc123 "
            '{"account_id":"ACCT_SECRET","secret":"abc"}'
        )
        mock_broker.place_order.side_effect = BrokerOperationError(unsafe_msg)

        config = AtlasConfig(
            trading_mode="live",
            broker={"provider": "alpaca", "enable_live_trading": True, "enable_live_submit": True},
            workspace_root=tmp_path,
            pending_orders_dir=tmp_path / "pending_orders",
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

            report = run_submit_execution(
                order_id=order.id,
                config=config,
                approval_manager=manager,
            )

        assert report.ok is False
        d = report.to_dict()
        assert_no_forbidden_output(d)
        # The blocked_reason should be a safe code, not the raw exception text
        assert "broker.example.com" not in d.get("message", "")
        assert "Authorization:" not in d.get("message", "")
        assert "ACCT_SECRET" not in d.get("message", "")


# ---------------------------------------------------------------------------
# D. Audit payload safety
# ---------------------------------------------------------------------------

class TestAuditPayloadSafety:
    def test_live_submit_blocked_exact_keys(self) -> None:
        from atlas_agent.execution.submit_execution import _emit_live_submit_blocked

        allowed_keys = {
            "mode",
            "broker_id",
            "order_id",
            "client_order_id",
            "reason_code",
            "gate",
            "status",
        }
        forbidden_keys = {
            "order",
            "raw_order",
            "payload",
            "broker_response",
            "exception",
            "traceback",
            "path",
            "headers",
            "secret",
        }

        mock_writer = MagicMock()
        _emit_live_submit_blocked(
            mock_writer,
            order_id="order-123",
            client_order_id="cid-abc",
            broker_id="alpaca",
            blocked_reason="can_submit_false",
            gate="can_submit",
        )
        assert mock_writer.write_event.called
        call_args = mock_writer.write_event.call_args
        payload = call_args.kwargs["payload"]
        assert set(payload.keys()) == allowed_keys
        for bad_key in forbidden_keys:
            assert bad_key not in payload
        assert_no_forbidden_output(payload)

    def test_live_submit_attempted_exact_keys(self) -> None:
        from atlas_agent.execution.submit_execution import _emit_live_submit_attempted

        allowed_keys = {
            "mode",
            "broker_id",
            "order_id",
            "client_order_id",
            "status",
        }

        mock_writer = MagicMock()
        _emit_live_submit_attempted(
            mock_writer,
            order_id="order-123",
            client_order_id="cid-abc",
            broker_id="alpaca",
        )
        assert mock_writer.write_event.called
        call_args = mock_writer.write_event.call_args
        payload = call_args.kwargs["payload"]
        assert set(payload.keys()) == allowed_keys
        assert_no_forbidden_output(payload)

    def test_audit_writer_failure_does_not_leak(self) -> None:
        from atlas_agent.execution.submit_execution import _emit_live_submit_blocked

        mock_writer = MagicMock()
        mock_writer.write_event.side_effect = RuntimeError(
            "LEAKED_SECRET_TOKEN /Users/natan/secret"
        )
        # Must not raise
        _emit_live_submit_blocked(
            mock_writer,
            order_id="order-123",
            client_order_id="cid-abc",
            broker_id="alpaca",
            blocked_reason="can_submit_false",
            gate="can_submit",
        )


# ---------------------------------------------------------------------------
# E. Broker ID and client order ID output safety
# ---------------------------------------------------------------------------

class TestIdOutputSafety:
    def test_unsafe_broker_order_id_not_in_reconcile_report(self) -> None:
        from atlas_agent.execution.submit_reconcile import _sanitize_broker_order_id

        assert _sanitize_broker_order_id("/etc/passwd") is None
        assert _sanitize_broker_order_id("API_KEY_123") is None
        assert _sanitize_broker_order_id("safe-broker-id-123") == "safe-broker-id-123"

    def test_unsafe_client_order_id_in_cli_reconcile_is_sanitized(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        from atlas_agent.cli import main
        from atlas_agent.config import AtlasConfig
        from unittest.mock import patch

        monkeypatch.chdir(tmp_path)
        main(["init", "."])
        capsys.readouterr()

        # Write a corrupted pending file with unsafe client_order_id
        pending_dir = tmp_path / "pending_orders"
        unsafe_payload = {
            "schema_version": "2",
            "status": "approved",
            "order_hash": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
            "approved_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2026-01-01T01:00:00+00:00",
            "approval_actor": "test",
            "status_transitions": [],
            "client_order_id": "../../etc/passwd",
            "submit_attempts": [],
        }
        (pending_dir / "unsafe-cid.json").write_text(json.dumps(unsafe_payload), encoding="utf-8")

        config = _configured_atlas_config(tmp_path)
        with patch.object(AtlasConfig, "from_env", return_value=config):
            code = main(["submit-approved-order", "unsafe-cid", "--reconcile", "--json"])

        captured = capsys.readouterr()
        assert code != 0
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert_no_forbidden_output(payload)


# ---------------------------------------------------------------------------
# F. Reconcile drift + broker body injection — meaningful broker lookup tests
# ---------------------------------------------------------------------------

class TestReconcileBrokerLookupSafety:
    """Tests that exercise the actual broker lookup path in run_reconcile."""

    @pytest.fixture
    def _make_v2_pending(self, tmp_path: Path):
        """Return a factory that writes valid v2 pending orders."""
        from atlas_agent.execution.approval import ApprovalManager, _compute_order_hash, _order_to_dict
        from atlas_agent.execution.order import Order

        def _write(order_id: str, status: str = "submit_uncertain", cid: str = "atlas-test-cid"):
            order = Order(symbol="TEST", side="buy", quantity=1.0, limit_price=100.0, confidence=1.0, stop_loss=95.0)
            manager = ApprovalManager(tmp_path / "pending")
            path = manager.path_for(order_id)
            order_dict = _order_to_dict(order)
            now = datetime.now(UTC).isoformat()
            payload = {
                "schema_version": "2",
                "order": order_dict,
                "approved": True,
                "created_at": now,
                "approved_at": now,
                "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
                "approval_actor": "test",
                "order_hash": _compute_order_hash(order_dict),
                "status": status,
                "status_transitions": [
                    {"status": "pending_approval", "at": now, "actor": "system"},
                    {"status": "approved", "at": now, "actor": "test"},
                    {"status": "submit_requested", "at": now, "actor": "submit:cli"},
                ],
                "submit_attempts": [{
                    "attempt_id": "b1d7ed33-8092-4eca-beed-ddef20ae4319",
                    "client_order_id": cid,
                    "status": "submit_requested" if status == "submit_uncertain" else status,
                    "created_at": now,
                    "actor": "submit:cli",
                    "risk_revalidated": True,
                    "sync_revalidated": True,
                    "broker_order_id": None,
                    "error_code": None,
                }],
                "broker_order_id": None,
                "client_order_id": cid,
                "fill_quantity": 0.0,
                "fill_price": None,
                "submitted_at": None,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            return manager, path
        return _write

    def test_reconcile_broker_lookup_never_calls_place_order(
        self, tmp_path, _make_v2_pending
    ) -> None:
        from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
        from atlas_agent.brokers.models import BrokerOrder
        from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
        from atlas_agent.execution.submit_reconcile import run_reconcile

        manager, _ = _make_v2_pending("lookup-no-place", status="submit_uncertain")

        mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
        mock_adapter.get_order_by_client_order_id.return_value = BrokerOrder(
            order_id="broker-123",
            symbol="TEST",
            side="buy",
            quantity=1.0,
            status="open",
        )

        def _mock_resolution(*args, **kwargs):
            return BrokerResolution(
                execution_broker=None,
                sync_provider=mock_adapter,
                status=MagicMock(),
            )

        with patch.object(BrokerResolver, "resolve_sync_provider", side_effect=_mock_resolution):
            report = run_reconcile("lookup-no-place", _FakeConfig(), manager)

        assert report.ok is True
        mock_adapter.get_order_by_client_order_id.assert_called_once()
        place_order_mock = getattr(mock_adapter, "place_order", None)
        assert place_order_mock is None or not place_order_mock.called

    def test_reconcile_broker_lookup_never_calls_resolve_execution_broker(
        self, tmp_path, _make_v2_pending
    ) -> None:
        from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
        from atlas_agent.brokers.models import BrokerOrder
        from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
        from atlas_agent.execution.submit_reconcile import run_reconcile

        manager, _ = _make_v2_pending("lookup-no-resolve", status="submit_uncertain")

        mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
        mock_adapter.get_order_by_client_order_id.return_value = BrokerOrder(
            order_id="broker-123",
            symbol="TEST",
            side="buy",
            quantity=1.0,
            status="open",
        )

        def _mock_resolution(*args, **kwargs):
            return BrokerResolution(
                execution_broker=None,
                sync_provider=mock_adapter,
                status=MagicMock(),
            )

        mock_resolve_execution = MagicMock(side_effect=AssertionError("resolve_execution_broker must not be called"))

        with patch.object(BrokerResolver, "resolve_sync_provider", side_effect=_mock_resolution), \
             patch.object(BrokerResolver, "resolve_execution_broker", mock_resolve_execution):
            report = run_reconcile("lookup-no-resolve", _FakeConfig(), manager)

        assert report.ok is True
        mock_adapter.get_order_by_client_order_id.assert_called_once()
        mock_resolve_execution.assert_not_called()

    def test_reconcile_broker_query_failure_sanitizes_raw_broker_body(
        self, tmp_path, _make_v2_pending
    ) -> None:
        from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
        from atlas_agent.brokers.base import BrokerOperationError
        from atlas_agent.brokers.resolver import BrokerResolver, BrokerResolution
        from atlas_agent.execution.submit_reconcile import run_reconcile

        manager, _ = _make_v2_pending("lookup-unsafe-body", status="submit_uncertain")

        unsafe_msg = (
            "https://broker.example.com/orders/raw-body "
            "Authorization: Bearer abc123 "
            '{"account_id":"ACCT_SECRET","secret":"abc"}'
        )
        mock_adapter = MagicMock(spec=AlpacaBrokerAdapter)
        mock_adapter.get_order_by_client_order_id.side_effect = BrokerOperationError(unsafe_msg)

        def _mock_resolution(*args, **kwargs):
            return BrokerResolution(
                execution_broker=None,
                sync_provider=mock_adapter,
                status=MagicMock(),
            )

        with patch.object(BrokerResolver, "resolve_sync_provider", side_effect=_mock_resolution):
            report = run_reconcile("lookup-unsafe-body", _FakeConfig(), manager)

        assert report.ok is False
        mock_adapter.get_order_by_client_order_id.assert_called_once()
        d = report.to_dict()
        assert_no_forbidden_output(d)
        assert "broker.example.com" not in d.get("message", "")
        assert "Authorization:" not in d.get("message", "")
        assert "ACCT_SECRET" not in d.get("message", "")


class _FakeConfig:
    enable_live_trading = True
    max_position_size = 10000.0
    max_order_notional = 5000.0
    symbol_allowlist = None
    symbol_blocklist = set()
    require_stop_loss_live = True
    pending_orders_dir = Path("pending_orders")
    live_broker = "alpaca"
